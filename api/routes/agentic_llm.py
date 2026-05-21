"""
Agentic LLM explanation endpoint.

Wraps the existing FloodDecisionPipeline with a Claude-powered Bahasa
Indonesia explanation layer. The pipeline is invoked via direct in-process
import — no internal HTTP hop — so latency and failure isolation match
the synchronous /predict/agentic endpoint.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from agents.llm_orchestrator import explain_flood_prediction
from api.security import require_api_key

_log = logging.getLogger(__name__)

router = APIRouter(tags=["agentic-llm"])

_EXAMPLE_PAYLOAD = {
    "fetched_at_utc": "2026-05-18T11:30:00Z",
    "location": "Jakarta Utara",
    "openweather": {
        "main": {"temp": 27.9, "humidity": 91},
        "rain": {"1h": 20},
        "coord": {"lat": -6.2088, "lon": 106.8456},
    },
    "poskobanjir": [
        {"wilayah": "Jakarta Utara", "tinggi_air": 120, "status": "Siaga 3"}
    ],
    "bmkg_alerts": [
        {
            "headline": "Hujan Lebat Jakarta",
            "severity": "Moderate",
            "certainty": "Observed",
            "urgency": "Immediate",
        }
    ],
}


def _build_data_teknis(prediction: dict) -> dict:
    diagnostics = prediction.get("diagnostics") or {}
    district = ""
    authority = ""
    if isinstance(diagnostics, dict):
        district = str(diagnostics.get("district") or diagnostics.get("location") or "")
        authority = str(diagnostics.get("authority") or "")
    if not district:
        district = str(prediction.get("location") or "")
    if not authority:
        authority = str(prediction.get("authority") or "")

    return {
        "risk_level": str(prediction.get("risk_level") or "UNKNOWN"),
        "confidence_score": float(prediction.get("confidence_score") or 0.0),
        "system_status": str(prediction.get("system_status") or "UNKNOWN"),
        "district": district,
        "authority": authority,
        "execution_ms": float(prediction.get("pipeline_execution_ms") or 0.0),
    }


@router.post(
    "/predict/agentic/explain",
    dependencies=[Depends(require_api_key)],
    summary="Run agentic flood prediction and explain it in Bahasa Indonesia.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {"example": _EXAMPLE_PAYLOAD}
            }
        }
    },
)
async def predict_agentic_explain_endpoint(
    request: Request,
    snapshot: dict,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
) -> dict:
    """
    Execute the full FloodDecisionPipeline and return a Claude-generated
    Bahasa Indonesia explanation alongside the technical decision data.

    On any Claude failure the response still includes ``penjelasan_ai``
    via a deterministic template fallback — the endpoint never crashes
    because of the LLM.
    """
    from api.main import SnapshotIn, _model_to_dict, _reject_non_finite

    try:
        validated = SnapshotIn.model_validate(snapshot)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid_snapshot: {exc}") from exc

    snapshot_dict = _model_to_dict(validated)
    _reject_non_finite(snapshot_dict)

    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline_unavailable")

    try:
        prediction = await run_in_threadpool(
            pipeline.run,
            snapshot_dict,
            origin=origin,
            destination=destination,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — pipeline errors must surface as 500
        _log.error(
            "agentic_explain_pipeline_failed type=%s msg=%s",
            type(exc).__name__, exc, exc_info=True,
        )
        raise HTTPException(status_code=500, detail="pipeline_failed") from exc

    explanation = await explain_flood_prediction(prediction)

    return {
        "penjelasan_ai": explanation,
        "data_teknis": _build_data_teknis(prediction),
    }
