"""
Multi-agent flood analysis endpoint.

Runs the full 5-stage FloodDecisionPipeline, then passes the prediction to a
3-agent sequential analysis (AhliCuaca + AhliHidrologi + KoordinatorRisiko)
via direct Groq API calls for a richer multi-perspective Bahasa Indonesia report.

Falls back to deterministic template if Groq is unavailable —
the endpoint never returns 500 because of the LLM layer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from agents.crew.flood_crew import _fallback_crew_output, run_flood_crew
from api.security import require_api_key
from utils.paths import DEFAULT_REALTIME_SNAPSHOT

_log = logging.getLogger(__name__)

router = APIRouter(tags=["crew-analysis"])

# Total wall-clock budget for the three Groq LLM calls.
# Each call has a 20 s HTTP timeout; 45 s covers the full sequential crew.
# Set CREW_TIMEOUT_S env var to tune without a deploy.
_CREW_TIMEOUT_S = float(os.getenv("CREW_TIMEOUT_S", "45"))

# Snapshot-keyed cache for the public /predict/crew-realtime endpoint. The crew
# output only depends on the snapshot, which refreshes every ~15 min, so running
# the 3 Groq LLM calls again for the same snapshot is pure waste — and the
# endpoint is unauthenticated, so without this it could be spammed into cost.
# A single-entry cache keyed on fetched_at_utc covers the only "current" snapshot;
# the lock serializes concurrent first-time builds so the crew runs once, not
# once per click.
_crew_cache: dict = {"key": None, "result": None}
_crew_cache_lock = asyncio.Lock()

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


def _observed_features(prediction: dict) -> dict:
    """
    The pipeline result has no flat `features` dict, but the crew prompts and
    the deterministic fallback both read one. Rebuild the observed rain and
    water-level scalars from the result so the agents see real values instead
    of zeros. Missing values are left out rather than defaulted to 0.
    """
    elevation   = prediction.get("elevation") or {}
    diagnostics = prediction.get("diagnostics") or {}
    trend_state = diagnostics.get("trend_state") or {}
    stations    = (prediction.get("hydrology_assessment") or {}).get("stations") or []
    ratios = [
        float(s["water_level_ratio"])
        for s in stations
        if isinstance(s, dict) and s.get("water_level_ratio") is not None
    ]
    features = {
        "rainfall_mm":          elevation.get("rainfall_1h_mm"),
        "rainfall_3h_proxy_mm": elevation.get("rainfall_3h_mm"),
        "water_level_ratio":    max(ratios) if ratios else None,
        "water_level_delta":    trend_state.get("water_level_delta_cur"),
    }
    return {k: v for k, v in features.items() if v is not None}


async def _run_crew_on_snapshot(
    request: Request,
    snapshot: dict,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
) -> dict:
    """Run pipeline + crew on a pre-validated snapshot dict. Shared by both endpoints."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline_unavailable")

    try:
        prediction = await run_in_threadpool(
            pipeline.run,
            snapshot,
            origin=origin,
            destination=destination,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _log.error("crew_pipeline_failed type=%s", type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=500, detail="pipeline_failed") from exc

    if not prediction.get("features"):
        prediction = {**prediction, "features": _observed_features(prediction)}

    try:
        crew_output = await asyncio.wait_for(
            run_in_threadpool(run_flood_crew, snapshot, prediction),
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


@router.get(
    "/predict/crew-realtime",
    summary="Multi-agent CrewAI analysis on the current live snapshot (no API key required).",
)
async def predict_crew_realtime_endpoint(request: Request) -> dict:
    """
    Run the 3-agent FloodAnalysisCrew on the server's current cached snapshot.

    Unlike /predict/crew-analysis this endpoint:
    - Requires **no API key** — safe to call from the public UI
    - Accepts **no external input** — always uses the latest server-side sensor data
    - Falls back to a deterministic template when CrewAI or Groq is unavailable

    Suitable for the dashboard "Analisis Mendalam" button.
    """
    if not DEFAULT_REALTIME_SNAPSHOT.exists():
        raise HTTPException(status_code=404, detail="snapshot_unavailable")
    try:
        snapshot = json.loads(DEFAULT_REALTIME_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="snapshot_unreadable") from exc

    cache_key = snapshot.get("fetched_at_utc")
    # Fast path: this snapshot has already been analysed — return it without
    # burning three more LLM calls.
    if cache_key and _crew_cache["key"] == cache_key and _crew_cache["result"] is not None:
        return _crew_cache["result"]

    async with _crew_cache_lock:
        # Re-check under the lock: a concurrent request may have just filled it.
        if cache_key and _crew_cache["key"] == cache_key and _crew_cache["result"] is not None:
            return _crew_cache["result"]
        result = await _run_crew_on_snapshot(request, snapshot)
        if cache_key:
            _crew_cache["key"] = cache_key
            _crew_cache["result"] = result
        return result


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

    return await _run_crew_on_snapshot(request, snapshot_dict, origin=origin, destination=destination)
