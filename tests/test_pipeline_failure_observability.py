"""
H4 — Pipeline Failure Observability Tests.

Verifies that _emergency_output enriches failure_modes[0]["detail"] with
structured crash metadata, and that callers pass the correct failure_stage.

All tests use mocked pipeline stages — no ML model loading required.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from pipeline.flood_pipeline import FloodDecisionPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pipeline() -> FloodDecisionPipeline:
    return FloodDecisionPipeline()


_MINIMAL_SNAPSHOT: dict = {
    "fetched_at_utc": "2026-01-01T00:00:00+00:00",
    "openweather": {"main": {}, "rain": {}},
    "bmkg_alerts": [],
    "poskobanjir": [],
}


# ---------------------------------------------------------------------------
# A. _emergency_output structure — called directly
# ---------------------------------------------------------------------------


def test_emergency_output_has_required_top_level_fields():
    out = FloodDecisionPipeline._emergency_output("test failure")
    assert out["system_status"] == "PIPELINE_FAILURE"
    assert out["requires_manual_review"] is True
    assert out["is_safe_for_automation"] is False


def test_emergency_output_emergency_mode_in_detail():
    out = FloodDecisionPipeline._emergency_output("test failure")
    detail = out["failure_modes"][0]["detail"]
    assert detail["emergency_mode"] is True


def test_emergency_output_default_failure_stage():
    out = FloodDecisionPipeline._emergency_output("test failure")
    detail = out["failure_modes"][0]["detail"]
    assert detail["failure_stage"] == "unknown"


def test_emergency_output_exception_type_none():
    out = FloodDecisionPipeline._emergency_output("test failure")
    detail = out["failure_modes"][0]["detail"]
    assert detail["exception_type"] == "unknown"


def test_emergency_output_exception_type_captured():
    exc = ValueError("bad sensor")
    out = FloodDecisionPipeline._emergency_output("test failure", exc=exc)
    detail = out["failure_modes"][0]["detail"]
    assert detail["exception_type"] == "ValueError"


def test_emergency_output_named_failure_stage():
    out = FloodDecisionPipeline._emergency_output(
        "test failure", failure_stage="perception"
    )
    detail = out["failure_modes"][0]["detail"]
    assert detail["failure_stage"] == "perception"


def test_emergency_output_replay_correlation_id_is_uuid():
    out = FloodDecisionPipeline._emergency_output("test failure")
    cid = out["failure_modes"][0]["detail"]["replay_correlation_id"]
    parsed = uuid.UUID(cid)
    assert parsed.version == 4


def test_emergency_output_replay_correlation_id_unique_per_call():
    out1 = FloodDecisionPipeline._emergency_output("fail")
    out2 = FloodDecisionPipeline._emergency_output("fail")
    cid1 = out1["failure_modes"][0]["detail"]["replay_correlation_id"]
    cid2 = out2["failure_modes"][0]["detail"]["replay_correlation_id"]
    assert cid1 != cid2


# ---------------------------------------------------------------------------
# B. Deterministic structure — same detail keys regardless of exc type
# ---------------------------------------------------------------------------


def test_emergency_output_deterministic_keys():
    required_detail_keys = {
        "failure_stage",
        "exception_type",
        "replay_correlation_id",
        "emergency_mode",
    }
    for exc in (None, RuntimeError("boom"), KeyError("missing")):
        out = FloodDecisionPipeline._emergency_output("stage failed", exc=exc)
        detail = out["failure_modes"][0]["detail"]
        assert required_detail_keys <= set(detail.keys()), (
            f"Missing keys for exc={exc!r}: {required_detail_keys - set(detail.keys())}"
        )


# ---------------------------------------------------------------------------
# C. Caller wiring — correct failure_stage per pipeline stage
# ---------------------------------------------------------------------------


def _run_with_perception_crash(exc: Exception) -> dict:
    pipeline = _pipeline()
    with patch.object(pipeline._perception, "run", side_effect=exc):
        return pipeline.run(_MINIMAL_SNAPSHOT)


def _run_with_reasoning_crash(exc: Exception) -> dict:
    pipeline = _pipeline()
    mock_perception = MagicMock()
    mock_perception.plausibility = {"has_critical_violation": False}
    with patch.object(pipeline._perception, "run", return_value=mock_perception), \
         patch.object(pipeline._reasoning, "run", side_effect=exc):
        return pipeline.run(_MINIMAL_SNAPSHOT)


def _run_with_evaluation_crash(exc: Exception) -> dict:
    pipeline = _pipeline()
    mock_perception = MagicMock()
    mock_perception.plausibility = {"has_critical_violation": False}
    mock_reasoning = MagicMock()
    with patch.object(pipeline._perception, "run", return_value=mock_perception), \
         patch.object(pipeline._reasoning, "run", return_value=mock_reasoning), \
         patch.object(pipeline._evaluation, "run", side_effect=exc):
        return pipeline.run(_MINIMAL_SNAPSHOT)


def _run_with_action_crash(exc: Exception) -> dict:
    pipeline = _pipeline()
    mock_perception = MagicMock()
    mock_perception.plausibility = {"has_critical_violation": False}
    mock_reasoning = MagicMock()
    mock_evaluation = MagicMock()
    with patch.object(pipeline._perception, "run", return_value=mock_perception), \
         patch.object(pipeline._reasoning, "run", return_value=mock_reasoning), \
         patch.object(pipeline._evaluation, "run", return_value=mock_evaluation), \
         patch.object(pipeline._action, "run", side_effect=exc):
        return pipeline.run(_MINIMAL_SNAPSHOT)


def test_perception_crash_failure_stage():
    out = _run_with_perception_crash(RuntimeError("sensor timeout"))
    detail = out["failure_modes"][0]["detail"]
    assert detail["failure_stage"] == "perception"
    assert detail["exception_type"] == "RuntimeError"
    assert detail["emergency_mode"] is True


def test_reasoning_crash_failure_stage():
    out = _run_with_reasoning_crash(ValueError("feature mismatch"))
    detail = out["failure_modes"][0]["detail"]
    assert detail["failure_stage"] == "reasoning"
    assert detail["exception_type"] == "ValueError"


def test_evaluation_crash_failure_stage():
    out = _run_with_evaluation_crash(KeyError("missing_field"))
    detail = out["failure_modes"][0]["detail"]
    assert detail["failure_stage"] == "evaluation"
    assert detail["exception_type"] == "KeyError"


def test_action_crash_failure_stage():
    out = _run_with_action_crash(TypeError("unexpected type"))
    detail = out["failure_modes"][0]["detail"]
    assert detail["failure_stage"] == "action"
    assert detail["exception_type"] == "TypeError"


# ---------------------------------------------------------------------------
# D. Simulated crash replay — output is structurally stable
# ---------------------------------------------------------------------------


def test_crash_replay_output_always_pipeline_failure():
    for _ in range(2):
        out = _run_with_perception_crash(RuntimeError("db unavailable"))
        assert out["system_status"] == "PIPELINE_FAILURE"
        assert out["requires_manual_review"] is True
        assert out["is_safe_for_automation"] is False


def test_crash_replay_correlation_ids_differ():
    out1 = _run_with_perception_crash(RuntimeError("x"))
    out2 = _run_with_perception_crash(RuntimeError("x"))
    cid1 = out1["failure_modes"][0]["detail"]["replay_correlation_id"]
    cid2 = out2["failure_modes"][0]["detail"]["replay_correlation_id"]
    assert cid1 != cid2


def test_emergency_mode_flag_always_true_on_crash():
    for stage_crash in (
        _run_with_perception_crash,
        _run_with_reasoning_crash,
        _run_with_evaluation_crash,
        _run_with_action_crash,
    ):
        out = stage_crash(Exception("generic"))
        assert out["failure_modes"][0]["detail"]["emergency_mode"] is True
