"""
CrewAI multi-agent flood analysis endpoint.

Runs the full 5-stage FloodDecisionPipeline, then passes the prediction to a
3-agent CrewAI crew (AhliCuaca + AhliHidrologi + KoordinatorRisiko) for a
richer multi-perspective Bahasa Indonesia analysis.

Falls back to deterministic template if CrewAI or Groq is unavailable —
the endpoint never returns 500 because of the LLM layer.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from agents.crew.flood_crew import _fallback_crew_output, run_flood_crew
from api.security import require_api_key

_log = logging.getLogger(__name__)

router = APIRouter(tags=["crew-analysis"])

# Total wall-clock budget for the three Groq LLM calls.
# Each call has a 20 s HTTP timeout; 45 s covers the full sequential crew.
# Set CREW_TIMEOUT_S env var to tune without a deploy.
_CREW_TIMEOUT_S = float(os.getenv("CREW_TIMEOUT_S", "45"))

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


@router.post(
    "/predict/crew-analysis",
    dependencies=[Depends(require_api_key)],
    summary="Multi-agent CrewAI flood analysis in Bahasa Indonesia.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {"example": _EXAMPLE_PAYLOAD}
            }
        }
    },
)
async def predict_crew_analysis_endpoint(
    request: Request,
    snapshot: dict,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
) -> dict:
    """
    Run the full FloodDecisionPipeline (5 stages), then pass the prediction
    to a 3-agent CrewAI crew for a richer Bahasa Indonesia analysis:

    - **AhliCuaca**: analyzes rainfall, BMKG alerts, atmospheric conditions
    - **AhliHidrologi**: analyzes water levels, siaga stations, hydrological trends
    - **KoordinatorRisiko**: synthesizes all signals into the final JSON report

    Response fields:
    - `analisis_crew`: structured report with status, explanation, actions, officer
      message, plus `analisis_cuaca` and `analisis_hidrologi` from each expert agent
    - `data_teknis`: raw ML decision data (risk_level, probability, confidence, etc.)

    On any Groq/crew failure the response still includes `analisis_crew` via a
    deterministic template fallback — the endpoint never returns 500 for LLM errors.
    """
    # Deferred import avoids a circular import at module load time
    # (api.main imports this router; importing SnapshotIn at top level would
    # create a cycle). This matches the pattern used in agentic_llm.py.
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
    except Exception as exc:  # noqa: BLE001
        _log.error(
            "crew_analysis_pipeline_failed type=%s",
            type(exc).__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="pipeline_failed") from exc

    # Run the crew with an overall wall-clock timeout.
    # Each LLM call already has a 20 s per-request HTTP timeout inside
    # run_flood_crew; this outer guard prevents thread-pool starvation if Groq
    # is slow to close the connection after the HTTP timeout fires.
    try:
        crew_output = await asyncio.wait_for(
            run_in_threadpool(run_flood_crew, snapshot_dict, prediction),
            timeout=_CREW_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        _log.warning("crew_timeout_exceeded after %.0fs — using fallback", _CREW_TIMEOUT_S)
        crew_output = _fallback_crew_output(prediction)

    diagnostics = prediction.get("diagnostics") or {}
    location = (
        prediction.get("location")
        or diagnostics.get("district")
        or diagnostics.get("location")
        or ""
    )

    return {
        "analisis_crew": crew_output,
        "data_teknis": {
            "risk_level": str(prediction.get("risk_level") or "UNKNOWN"),
            "probability": float(prediction.get("probability") or 0.0),
            "confidence_score": float(prediction.get("confidence_score") or 0.0),
            "dominant_risk_driver": str(prediction.get("dominant_risk_driver") or ""),
            "system_status": str(prediction.get("system_status") or "UNKNOWN"),
            "location": location,
            "pipeline_execution_ms": float(prediction.get("pipeline_execution_ms") or 0.0),
        },
    }
