"""
Smoke tests for POST /predict/agentic/explain and the LLM orchestrator.

Claude is NEVER called in tests — the orchestrator's outbound Anthropic call
is patched to force the deterministic fallback path. The route is exercised
end-to-end through TestClient so route registration, auth dependency, and
response envelope are all verified.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("FLOOD_API_KEYS", "test-key")
os.environ.setdefault("FLOOD_API_RATE_LIMIT", "1000")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

from agents.llm_orchestrator import (  # noqa: E402
    _fallback_explanation,
    explain_flood_prediction,
)
from api.main import app  # noqa: E402

_HEADERS = {"host": "testserver", "X-API-Key": "test-key"}

_MOCK_PREDICTION = {
    "system_status": "OK",
    "risk_level": "SAFE",
    "confidence_score": 0.74,
    "probability": 0.18,
    "decision_reason": "RISK",
    "dominant_risk_driver": "rainfall",
    "risk_interpretation": "Low flood risk for the current Jakarta snapshot.",
    "pipeline_execution_ms": 123.4,
    "location": "Jakarta Selatan",
    "diagnostics": {"district": "Jakarta Selatan", "authority": "BPBD DKI"},
    "recommended_action": ["Monitor sensors"],
    "trend_analysis": {},
    "data_freshness_minutes": 4.0,
}

_VALID_PAYLOAD = {
    "fetched_at_utc": "2026-05-18T11:30:00Z",
    "location": "Jakarta Selatan",
    "openweather": {
        "main": {"temp": 28.0, "humidity": 70},
        "rain": {"1h": 2},
        "coord": {"lat": -6.2615, "lon": 106.8106},
    },
    "poskobanjir": [
        {"wilayah": "Jakarta Selatan", "tinggi_air": 50, "status": "Normal"}
    ],
    "bmkg_alerts": [],
}


def _pipeline_stub(*, result=None, exc: BaseException | None = None) -> SimpleNamespace:
    def run(*args, **kwargs):
        if exc is not None:
            raise exc
        return result

    return SimpleNamespace(run=run)


@pytest.fixture
def explain_client():
    cm = TestClient(app, headers={"host": "testserver"})
    cm.__enter__()
    try:
        yield cm
    finally:
        cm.__exit__(None, None, None)


def test_fallback_explanation_safe_status():
    out = _fallback_explanation({"risk_level": "SAFE", "confidence_score": 0.7})
    assert out["status_banjir"] == "AMAN"
    assert isinstance(out["tindakan"], list) and len(out["tindakan"]) >= 1
    assert out["tingkat_kepercayaan"] == "70%"
    assert isinstance(out["pesan_petugas"], str) and out["pesan_petugas"]


def test_fallback_explanation_danger_status():
    out = _fallback_explanation({"risk_level": "DANGER", "confidence_score": 0.92})
    assert out["status_banjir"] == "BAHAYA"
    assert out["tingkat_kepercayaan"] == "92%"
    assert "EVAKUASI" in " ".join(out["tindakan"]).upper()


def test_fallback_explanation_warning_status():
    out = _fallback_explanation({"risk_level": "WARNING", "confidence_score": 0.55})
    assert out["status_banjir"] == "WASPADA"


def test_explain_uses_fallback_when_claude_unavailable():
    with patch(
        "agents.llm_orchestrator._call_claude_sync",
        side_effect=RuntimeError("simulated_outage"),
    ):
        result = asyncio.run(explain_flood_prediction(_MOCK_PREDICTION))
    assert result["status_banjir"] == "AMAN"
    assert result["tingkat_kepercayaan"] == "74%"
    assert len(result["tindakan"]) >= 1


def test_explain_endpoint_returns_envelope(explain_client):
    app.state.pipeline = _pipeline_stub(result=_MOCK_PREDICTION)

    with patch(
        "agents.llm_orchestrator._call_claude_sync",
        side_effect=RuntimeError("force_fallback"),
    ):
        response = explain_client.post(
            "/predict/agentic/explain",
            json=_VALID_PAYLOAD,
            headers=_HEADERS,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "penjelasan_ai" in body
    assert "data_teknis" in body

    ai = body["penjelasan_ai"]
    for key in (
        "status_banjir",
        "penjelasan",
        "tindakan",
        "populasi_terdampak",
        "tingkat_kepercayaan",
        "pesan_petugas",
    ):
        assert key in ai, f"missing penjelasan_ai.{key}"
    assert ai["status_banjir"] in {"AMAN", "WASPADA", "BAHAYA"}
    assert isinstance(ai["tindakan"], list) and ai["tindakan"]

    teknis = body["data_teknis"]
    assert teknis["risk_level"] == "SAFE"
    assert teknis["district"] == "Jakarta Selatan"
    assert teknis["system_status"] == "OK"
    assert teknis["execution_ms"] == pytest.approx(123.4)


def test_explain_endpoint_requires_api_key(explain_client):
    app.state.pipeline = _pipeline_stub(result=_MOCK_PREDICTION)
    response = explain_client.post(
        "/predict/agentic/explain",
        json=_VALID_PAYLOAD,
        headers={"host": "testserver"},
    )
    assert response.status_code in (401, 403), response.text
