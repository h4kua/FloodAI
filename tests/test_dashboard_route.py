"""
Dashboard route tests — updated for the post-audit topology:

* The pipeline is no longer a module-level ``_PIPELINE`` singleton (audit H11);
  it is injected via FastAPI lifespan onto ``app.state.pipeline``. Tests inject
  a stub on that attribute instead of patching a module-level name.
* All routes except /healthz, /readyz require an API key (audit C1). We set
  ``FLOOD_API_KEYS`` before importing the app and send the header on every
  request.
* The 404 error body is now redacted (audit C6) — assert against the redacted
  payload, not the raw exception message.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Configure auth + trusted hosts BEFORE importing the app so module-level
# middleware setup sees them. TestClient sends Host: testserver by default.
os.environ.setdefault("FLOOD_API_KEYS", "test-key")
os.environ.setdefault("FLOOD_API_RATE_LIMIT", "1000")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

from api.main import app  # noqa: E402


MOCK_RESULT = {
    "system_status": "OK",
    "risk_level": "SAFE",
    "confidence_score": 0.84,
    "decision_reason": "RISK",
    "dominant_risk_driver": "rainfall",
    "risk_interpretation": "Low flood risk for the current Jakarta snapshot.",
    "data_freshness_minutes": 4.5,
    "pipeline_version": "agentic-v2.0",
    "model_name": "jakarta-flood-ensemble",
    "safe_route": {"available": True, "reason": "safe roads found", "alternatives_evaluated": 3},
    "failure_modes": [],
    "recommended_action": ["Monitor local radar and field reports."],
    "trend_analysis": {
        "risk_delta_1h": -0.02,
        "risk_trend": "decreasing",
        "water_level_trend": "stable",
        "rainfall_trend": "falling",
        "data_points": 12,
    },
    "shadow_evaluation": {"shadow_threshold_profile": "conservative"},
}

MOCK_SNAPSHOT = {
    "openweather": {"coord": {"lat": -6.21, "lon": 106.85}, "rain": {"1h": 8.4, "3h": 22.5}},
    "poskobanjir": [{"tinggi_air": 120.0}],
}


def _make_pipeline_stub(*, result=None, exc: BaseException | None = None) -> SimpleNamespace:
    def run_from_file(*args, **kwargs):
        if exc is not None:
            raise exc
        return result

    return SimpleNamespace(run_from_file=run_from_file)


@pytest.fixture
def client_with_stub_pipeline():
    """
    Return a factory that opens a TestClient (triggering lifespan), then
    overwrites ``app.state.pipeline`` with the supplied stub. Caller is
    responsible for ``client.__exit__`` so lifespan teardown runs.
    """
    def factory(stub):
        cm = TestClient(app, headers={"host": "testserver"})
        cm.__enter__()
        app.state.pipeline = stub
        return cm

    return factory


def test_demo_route_renders_html(client_with_stub_pipeline):
    stub = _make_pipeline_stub(result=MOCK_RESULT)
    client = client_with_stub_pipeline(stub)
    try:
        with patch("api.dashboard._load_snapshot", return_value=MOCK_SNAPSHOT):
            response = client.get("/demo")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200, response.text
    assert "Jakarta Flood Prediction Demo" in response.text
    assert "SAFE" in response.text
    assert "safe roads found" in response.text


def test_demo_route_missing_snapshot_returns_404(client_with_stub_pipeline):
    stub = _make_pipeline_stub(exc=FileNotFoundError("missing snapshot"))
    client = client_with_stub_pipeline(stub)
    try:
        response = client.get("/demo")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 404
    # Body is intentionally redacted — assert on safe identifiers only.
    assert (
        "snapshot_unavailable" in response.text
        or "Snapshot file not found" in response.text
    )


def test_demo_route_pipeline_failure_logs_correlation_id(client_with_stub_pipeline):
    stub = _make_pipeline_stub(exc=RuntimeError("pipeline exploded"))
    client = client_with_stub_pipeline(stub)
    fake_log = Mock()
    try:
        with patch("api.dashboard._log", fake_log):
            response = client.get("/demo")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 500
    fake_log.error.assert_called_once()
    _, kwargs = fake_log.error.call_args
    assert kwargs["error"] == "pipeline exploded"
    assert kwargs["correlation_id"] in response.text


def test_demo_route_snapshot_failure_shows_degraded_state(client_with_stub_pipeline):
    stub = _make_pipeline_stub(result=MOCK_RESULT)
    client = client_with_stub_pipeline(stub)
    fake_log = Mock()
    try:
        with patch("api.dashboard._load_snapshot", side_effect=OSError("snapshot unreadable")), \
             patch("api.dashboard._query_db_health", return_value={"connected": False}), \
             patch("api.dashboard._log", fake_log):
            response = client.get("/demo")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert "DEGRADED" in response.text
    assert "Snapshot metadata unavailable" in response.text
    fake_log.warning.assert_called_once()
    _, kwargs = fake_log.warning.call_args
    assert kwargs["error"] == "snapshot unreadable"
