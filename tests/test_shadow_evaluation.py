"""
Shadow threshold evaluation tests (DATA-2).

Groups:
  D. Pipeline integration — result["shadow_evaluation"] present and correct
  E. compute_hydro_shadow_evaluation — unit tests for the pure function
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.decision_engine import (
    _SHADOW_HYDRO_DANGER_RATIO,
    _SHADOW_HYDRO_WARNING_RATIO,
    _SHADOW_HYDRO_PRE_ALERT_RATIO,
    _SHADOW_HYDRO_SIAGA3_FLOOR_COUNT,
    compute_hydro_shadow_evaluation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = "2026-01-01T00:00:00+00:00"  # fixed timestamp for deterministic replay


# ---------------------------------------------------------------------------
# D. Pipeline integration (hydro-based shadow)
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


def _make_station(ratio: float, siaga_level: str):
    s = MagicMock()
    s.water_level_ratio = ratio
    s.siaga_level = siaga_level
    return s


def _run_pipeline(prob: float, stations=None) -> dict:
    from pipeline.flood_pipeline import FloodDecisionPipeline
    pipeline = FloodDecisionPipeline(strict_mode=False, persist=False)
    result_base = _base_result()
    result_base["probability"] = prob
    hydro_mock = MagicMock()
    hydro_mock.stations = stations if stations is not None else []
    perception_mock = MagicMock(plausibility={"has_critical_violation": False})
    perception_mock.hydrology_assessment = hydro_mock
    with (
        patch.object(pipeline._perception, "run", return_value=perception_mock),
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


def test_pipeline_shadow_uses_hydro_not_ml_probability():
    """Shadow is hydro-only: same ML prob, different ratio → different shadow risk."""
    result_low_ratio = _run_pipeline(0.18, stations=[_make_station(0.40, "normal")])
    result_high_ratio = _run_pipeline(0.18, stations=[_make_station(0.80, "siaga3")])
    assert result_low_ratio["shadow_evaluation"]["shadow_risk_level"] == "SAFE"
    assert result_high_ratio["shadow_evaluation"]["shadow_risk_level"] == "WARNING"


def test_pipeline_shadow_production_risk_unchanged():
    """Shadow never mutates the production risk_level."""
    result = _run_pipeline(0.18, stations=[_make_station(0.80, "siaga3")])
    assert result["risk_level"] == "SAFE"
    assert result["shadow_evaluation"]["shadow_risk_level"] == "WARNING"


def test_pipeline_shadow_disagreement_adds_failure_mode():
    """2+ level gap (SAFE prod vs WARNING shadow) injects shadow_hydro_disagreement."""
    result = _run_pipeline(0.05, stations=[_make_station(0.80, "siaga3")])
    assert result["shadow_evaluation"]["shadow_danger_triggered"] is True
    failure_types = [f["type"] for f in result["failure_modes"]]
    assert "shadow_hydro_disagreement" in failure_types


def test_pipeline_shadow_no_disagreement_no_failure_mode():
    """When shadow matches production, no extra failure mode is injected."""
    result = _run_pipeline(0.05, stations=[_make_station(0.40, "normal")])
    assert result["shadow_evaluation"]["shadow_danger_triggered"] is False
    failure_types = [f["type"] for f in result["failure_modes"]]
    assert "shadow_hydro_disagreement" not in failure_types


def test_pipeline_shadow_fields_complete():
    result = _run_pipeline(0.10, stations=[_make_station(0.50, "normal")])
    shadow = result["shadow_evaluation"]
    for field in (
        "shadow_warning_triggered", "shadow_danger_triggered",
        "shadow_risk_level", "shadow_max_water_level_ratio",
        "shadow_siaga3_or_above_count", "shadow_threshold_profile",
        "production_risk_level", "shadow_disagreement_levels", "evaluated_at",
    ):
        assert field in shadow, f"missing shadow field: {field}"


# ---------------------------------------------------------------------------
# E. compute_hydro_shadow_evaluation — pure function unit tests
# ---------------------------------------------------------------------------


def _hydro_shadow(ratio: float, siaga3_count: int = 0, prod_risk: str = "SAFE") -> dict:
    return compute_hydro_shadow_evaluation(
        max_water_level_ratio=ratio,
        siaga3_or_above_count=siaga3_count,
        production_risk_level=prod_risk,
        evaluated_at=_TS,
    )


def test_hydro_shadow_safe_below_pre_alert():
    r = _hydro_shadow(0.50)
    assert r["shadow_risk_level"] == "SAFE"
    assert r["shadow_warning_triggered"] is False
    assert r["shadow_danger_triggered"] is False


def test_hydro_shadow_pre_alert_at_boundary():
    r = _hydro_shadow(_SHADOW_HYDRO_PRE_ALERT_RATIO)
    assert r["shadow_risk_level"] == "PRE_ALERT"
    assert r["shadow_warning_triggered"] is False


def test_hydro_shadow_warning_at_boundary():
    r = _hydro_shadow(_SHADOW_HYDRO_WARNING_RATIO)
    assert r["shadow_risk_level"] == "WARNING"
    assert r["shadow_warning_triggered"] is True


def test_hydro_shadow_danger_at_boundary():
    r = _hydro_shadow(_SHADOW_HYDRO_DANGER_RATIO)
    assert r["shadow_risk_level"] == "DANGER"
    assert r["shadow_warning_triggered"] is True


def test_hydro_shadow_siaga3_floor_upgrades_to_warning():
    """<= 3 siaga3+ stations with low ratio → floor at WARNING."""
    r = _hydro_shadow(0.50, siaga3_count=_SHADOW_HYDRO_SIAGA3_FLOOR_COUNT)
    assert r["shadow_risk_level"] == "WARNING"


def test_hydro_shadow_siaga3_floor_does_not_downgrade_danger():
    """siaga3 floor never downgrades DANGER already set by ratio."""
    r = _hydro_shadow(0.92, siaga3_count=_SHADOW_HYDRO_SIAGA3_FLOOR_COUNT)
    assert r["shadow_risk_level"] == "DANGER"


def test_hydro_shadow_disagreement_two_levels():
    """SAFE prod + WARNING shadow = 2 levels → triggered."""
    r = _hydro_shadow(0.80, prod_risk="SAFE")
    assert r["shadow_disagreement_levels"] == 2
    assert r["shadow_danger_triggered"] is True


def test_hydro_shadow_disagreement_one_level_not_triggered():
    """PRE_ALERT prod + WARNING shadow = 1 level → not triggered."""
    r = _hydro_shadow(0.80, prod_risk="PRE_ALERT")
    assert r["shadow_disagreement_levels"] == 1
    assert r["shadow_danger_triggered"] is False


def test_hydro_shadow_disagreement_safe_vs_danger():
    """SAFE prod + DANGER shadow = 3 levels → triggered."""
    r = _hydro_shadow(0.92, prod_risk="SAFE")
    assert r["shadow_disagreement_levels"] == 3
    assert r["shadow_danger_triggered"] is True


def test_hydro_shadow_no_disagreement_when_equal():
    r = _hydro_shadow(0.80, prod_risk="WARNING")
    assert r["shadow_disagreement_levels"] == 0
    assert r["shadow_danger_triggered"] is False


def test_hydro_shadow_deterministic_replay():
    r1 = _hydro_shadow(0.70, siaga3_count=2, prod_risk="SAFE")
    r2 = _hydro_shadow(0.70, siaga3_count=2, prod_risk="SAFE")
    assert r1 == r2


def test_hydro_shadow_profile_name():
    r = _hydro_shadow(0.50)
    assert r["shadow_threshold_profile"] == "hydro_rule"


def test_hydro_shadow_thresholds_stored():
    r = _hydro_shadow(0.50)
    assert r["shadow_hydro_danger_threshold"] == pytest.approx(_SHADOW_HYDRO_DANGER_RATIO)
    assert r["shadow_hydro_warning_threshold"] == pytest.approx(_SHADOW_HYDRO_WARNING_RATIO)
    assert r["shadow_hydro_pre_alert_threshold"] == pytest.approx(_SHADOW_HYDRO_PRE_ALERT_RATIO)


def test_hydro_shadow_does_not_mutate_production():
    prod = {"risk_level": "SAFE"}
    shadow = compute_hydro_shadow_evaluation(
        max_water_level_ratio=0.80,
        siaga3_or_above_count=0,
        production_risk_level=prod["risk_level"],
    )
    assert prod["risk_level"] == "SAFE"
    assert "risk_level" not in shadow
