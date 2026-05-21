"""
Shadow threshold evaluation tests (DATA-2).

Groups:
  A. compute_shadow_evaluation — unit tests for the pure function
  B. Deterministic replay — same input, same output (excluding auto-generated timestamp)
  C. Production fields unchanged — shadow never mutates production outputs
  D. Pipeline integration — result["shadow_evaluation"] present and correct
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.decision_engine import (
    _SHADOW_DANGER_THRESHOLD,
    _SHADOW_WARNING_THRESHOLD,
    _PROD_DANGER_THRESHOLD,
    _PROD_WARNING_THRESHOLD,
    compute_shadow_evaluation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = "2026-01-01T00:00:00+00:00"  # fixed timestamp for deterministic replay


def _shadow(prob: float, prod_risk: str = "SAFE") -> dict:
    return compute_shadow_evaluation(
        prob, production_risk_level=prod_risk, evaluated_at=_TS
    )


# ---------------------------------------------------------------------------
# A. compute_shadow_evaluation — pure function
# ---------------------------------------------------------------------------


def test_shadow_below_both_thresholds():
    r = _shadow(0.05)
    assert r["shadow_warning_triggered"] is False
    assert r["shadow_danger_triggered"] is False
    assert r["shadow_risk_level"] == "SAFE"


def test_shadow_warning_triggered_not_danger():
    r = _shadow(0.15)
    assert r["shadow_warning_triggered"] is True
    assert r["shadow_danger_triggered"] is False
    assert r["shadow_risk_level"] == "WARNING"


def test_shadow_danger_triggered():
    r = _shadow(0.25)
    assert r["shadow_warning_triggered"] is True
    assert r["shadow_danger_triggered"] is True
    assert r["shadow_risk_level"] == "DANGER"


def test_shadow_at_warning_boundary():
    r = _shadow(_SHADOW_WARNING_THRESHOLD)
    assert r["shadow_warning_triggered"] is True
    assert r["shadow_danger_triggered"] is False


def test_shadow_at_danger_boundary():
    r = _shadow(_SHADOW_DANGER_THRESHOLD)
    assert r["shadow_danger_triggered"] is True
    assert r["shadow_risk_level"] == "DANGER"


def test_shadow_probability_stored():
    r = _shadow(0.178)
    assert r["shadow_probability"] == pytest.approx(0.178, abs=1e-4)


def test_shadow_profile_name():
    r = _shadow(0.10)
    assert r["shadow_threshold_profile"] == "conservative"


def test_shadow_threshold_values_stored():
    r = _shadow(0.10)
    assert r["shadow_warning_threshold"] == pytest.approx(_SHADOW_WARNING_THRESHOLD)
    assert r["shadow_danger_threshold"] == pytest.approx(_SHADOW_DANGER_THRESHOLD)


def test_shadow_threshold_delta_correct():
    r = _shadow(0.10)
    expected_delta_w = round(_PROD_WARNING_THRESHOLD - _SHADOW_WARNING_THRESHOLD, 4)
    expected_delta_d = round(_PROD_DANGER_THRESHOLD - _SHADOW_DANGER_THRESHOLD, 4)
    assert r["threshold_delta_warning"] == pytest.approx(expected_delta_w)
    assert r["threshold_delta_danger"] == pytest.approx(expected_delta_d)


def test_shadow_production_risk_level_echoed():
    r = _shadow(0.10, prod_risk="DANGER")
    assert r["production_risk_level"] == "DANGER"


def test_shadow_evaluated_at_stored():
    r = _shadow(0.10)
    assert r["evaluated_at"] == _TS


def test_shadow_all_required_fields_present():
    required = {
        "shadow_warning_triggered",
        "shadow_danger_triggered",
        "shadow_probability",
        "shadow_risk_level",
        "shadow_threshold_profile",
        "shadow_warning_threshold",
        "shadow_danger_threshold",
        "production_risk_level",
        "threshold_delta_warning",
        "threshold_delta_danger",
        "evaluated_at",
    }
    r = _shadow(0.20)
    assert required.issubset(r.keys())


# ---------------------------------------------------------------------------
# B. Deterministic replay
# ---------------------------------------------------------------------------


def test_shadow_deterministic_same_probability():
    r1 = _shadow(0.19)
    r2 = _shadow(0.19)
    for key in ("shadow_warning_triggered", "shadow_danger_triggered",
                "shadow_risk_level", "shadow_probability",
                "threshold_delta_warning", "threshold_delta_danger"):
        assert r1[key] == r2[key], f"non-deterministic field: {key}"


def test_shadow_replay_same_timestamp_identical():
    r1 = compute_shadow_evaluation(0.20, production_risk_level="SAFE", evaluated_at=_TS)
    r2 = compute_shadow_evaluation(0.20, production_risk_level="SAFE", evaluated_at=_TS)
    assert r1 == r2


def test_shadow_different_probability_different_output():
    r1 = _shadow(0.08)
    r2 = _shadow(0.25)
    assert r1["shadow_risk_level"] != r2["shadow_risk_level"]


# ---------------------------------------------------------------------------
# C. Production fields — shadow never mutates them
# ---------------------------------------------------------------------------


def test_shadow_does_not_mutate_production_risk_level():
    prod = {"risk_level": "SAFE", "confidence_score": 0.8}
    shadow = compute_shadow_evaluation(0.20, production_risk_level=prod["risk_level"])
    assert prod["risk_level"] == "SAFE"
    assert "risk_level" not in shadow


def test_shadow_result_has_no_system_status_key():
    r = _shadow(0.30)
    assert "system_status" not in r


def test_shadow_result_has_no_authority_key():
    r = _shadow(0.30)
    assert "authority" not in r


def test_shadow_result_has_no_decision_trace_key():
    r = _shadow(0.30)
    assert "decision_trace" not in r


# ---------------------------------------------------------------------------
# D. Pipeline integration
# ---------------------------------------------------------------------------


def _base_result() -> dict:
    return {
        "risk_level": "SAFE",
        "confidence_score": 0.75,
        "system_status": "OK",
        "requires_manual_review": False,
        "failure_modes": [],
        "decision_reason": "RISK",
        "data_validity": "VALID",
        "ml_execution_mode": "FULL",
        "is_safe_for_automation": True,
        "decision_trace": [],
        "probability": 0.15,
        "dominant_risk_driver": "low_background_risk",
        "risk_interpretation": "No active threat",
    }


def _mock_eval(prob: float):
    from agents.evaluation_agent import EvaluationResult
    m = MagicMock(spec=EvaluationResult)
    m.probability = prob
    m.risk_level = "SAFE"
    m.system_status = "OK"
    m.reasoning = MagicMock()
    m.reasoning.signals = {}
    return m


def _run_pipeline(prob: float) -> dict:
    from pipeline.flood_pipeline import FloodDecisionPipeline
    pipeline = FloodDecisionPipeline(strict_mode=False, persist=False)
    result_base = _base_result()
    result_base["probability"] = prob
    with (
        patch.object(pipeline._perception, "run", return_value=MagicMock(
            plausibility={"has_critical_violation": False}
        )),
        patch.object(pipeline._reasoning, "run", return_value=MagicMock()),
        patch.object(pipeline._evaluation, "run", return_value=_mock_eval(prob)),
        patch.object(pipeline._action, "run", return_value=result_base),
        patch.object(pipeline._routing, "run", return_value={
            "safe_route": {"available": False, "reason": "test"},
            "tma_data": None,
        }),
    ):
        return pipeline.run({"test": True})


def test_pipeline_shadow_evaluation_present():
    result = _run_pipeline(0.15)
    assert "shadow_evaluation" in result


def test_pipeline_production_risk_level_unchanged():
    """probability=0.18 > shadow warning (0.12) but < production warning (0.26)."""
    result = _run_pipeline(0.18)
    assert result["risk_level"] == "SAFE"
    assert result["shadow_evaluation"]["shadow_risk_level"] == "WARNING"
    assert result["shadow_evaluation"]["shadow_warning_triggered"] is True


def test_pipeline_shadow_fields_complete():
    result = _run_pipeline(0.10)
    shadow = result["shadow_evaluation"]
    for field in (
        "shadow_warning_triggered", "shadow_danger_triggered",
        "shadow_probability", "shadow_risk_level", "shadow_threshold_profile",
        "evaluated_at",
    ):
        assert field in shadow, f"missing shadow field: {field}"
