"""
Smoke test for FloodDecisionPipeline end-to-end output structure.

Verifies that the pipeline returns a structurally valid response with all
required top-level keys, regardless of the current snapshot values.
"""

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from pipeline.flood_pipeline import FloodDecisionPipeline
from utils.paths import DEFAULT_REALTIME_SNAPSHOT

_REQUIRED_KEYS = {
    "risk_level",
    "probability",
    "confidence_score",
    "requires_manual_review",
    "dominant_risk_driver",
    "risk_interpretation",
    "recommended_action",
    "failure_modes",
    "pipeline_version",
    "pipeline_execution_ms",
    "_decision_authority",
}

_VALID_RISK_LEVELS = {"SAFE", "PRE_ALERT", "WARNING", "DANGER", "UNKNOWN"}


def _minimal_snapshot() -> dict:
    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "location": "Jakarta Selatan",
        "openweather": {
            "name": "Jakarta",
            "main": {"temp": 30.0, "humidity": 80.0, "pressure": 1010.0},
            "rain": {"1h": 2.0, "3h": 6.0},
            "wind": {"speed": 3.0},
        },
        "poskobanjir": [
            {
                "id": "manggarai",
                "name": "Manggarai",
                "tinggi_air": 300.0,
                "siaga1": 950.0,
                "siaga2": 850.0,
                "siaga3": 750.0,
                "siaga4": 650.0,
            }
        ],
        "bmkg_alerts": [],
    }


@pytest.fixture(scope="module", autouse=True)
def _provision_realtime_snapshot():
    path = DEFAULT_REALTIME_SNAPSHOT
    parent = path.parent
    placeholders_promoted: list = []
    original_contents: str | None = None

    chain: list = []
    cursor = parent
    while cursor != cursor.parent:
        if cursor.exists() and not cursor.is_dir():
            if cursor.stat().st_size == 0:
                chain.append(cursor)
            else:
                break
        cursor = cursor.parent
    for stray in chain:
        stray.unlink()
        placeholders_promoted.append(stray)

    parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        original_contents = path.read_text(encoding="utf-8")

    path.write_text(json.dumps(_minimal_snapshot(), indent=2), encoding="utf-8")
    yield

    try:
        if original_contents is not None:
            path.write_text(original_contents, encoding="utf-8")
        elif path.exists():
            path.unlink()
    except OSError:
        pass

    for stray in placeholders_promoted:
        try:
            if stray.exists() and stray.is_dir():
                try:
                    stray.rmdir()
                except OSError:
                    continue
            stray.touch()
        except OSError:
            pass


def test_pipeline_returns_required_keys():
    result = FloodDecisionPipeline(persist=False).run_from_file(replay_mode=True)
    missing = _REQUIRED_KEYS - result.keys()
    assert not missing, f"Pipeline output missing keys: {missing}"


def test_pipeline_risk_level_is_valid():
    result = FloodDecisionPipeline(persist=False).run_from_file(replay_mode=True)
    assert result["risk_level"] in _VALID_RISK_LEVELS


def test_pipeline_probability_is_bounded():
    result = FloodDecisionPipeline(persist=False).run_from_file(replay_mode=True)
    assert 0.0 <= result["probability"] <= 1.0


def test_pipeline_confidence_score_is_bounded():
    result = FloodDecisionPipeline(persist=False).run_from_file(replay_mode=True)
    assert 0.0 <= result["confidence_score"] <= 1.0


def test_pipeline_decision_authority_is_evaluation_agent():
    result = FloodDecisionPipeline(persist=False).run_from_file(replay_mode=True)
    assert result["_decision_authority"] == "EvaluationAgent"


def test_pipeline_version_is_agentic():
    result = FloodDecisionPipeline(persist=False).run_from_file(replay_mode=True)
    assert result["pipeline_version"] == "agentic-v2.0"


def test_pipeline_trend_analysis_comes_from_snapshot_history(monkeypatch):
    history = pd.DataFrame(
        [
            {"timestamp": "2026-04-18T08:00:00+00:00", "rainfall_mm": 4.0, "water_level_ratio": 0.20},
            {"timestamp": "2026-04-18T09:00:00+00:00", "rainfall_mm": 9.0, "water_level_ratio": 0.35},
        ]
    )
    monkeypatch.setattr("realtime_native.feature_builder._load_history", lambda path=None: history)

    result = FloodDecisionPipeline(persist=False).run(_minimal_snapshot(), replay_mode=True)

    assert result["trend_analysis"]["source"] == "realtime_snapshot_history"
    assert result["trend_analysis"]["risk_trend"] == result["diagnostics"]["trend_state"]["risk_trend"]
