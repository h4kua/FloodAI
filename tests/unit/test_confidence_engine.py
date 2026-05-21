from services.confidence_engine import (
    classify_ood_state,
    compute_automation_confidence,
)
from services.decision_engine import _apply_elevation_adjustment, run_decision_engine


def _decision_kwargs(**overrides):
    base = dict(
        evaluation_risk_level="SAFE",
        adjusted_confidence=0.68,
        system_status="OK",
        probability=0.10,
        raw_model_confidence=0.91,
        failure_modes=[
            {
                "type": "signal_conflict",
                "severity": "medium",
                "risk_escalation": False,
                "confidence_penalty": 0.12,
            }
        ],
        baseline_result={},
        signals={"rainfall_mm": 8.0, "bmkg_severity": 0.20},
        diagnostics={"trend_state": {}},
        hydrology_assessment=None,
        plausibility_score=0.95,
        has_critical_violation=False,
        trust_breakdown=None,
        adaptive_classification={"effective_danger_threshold": 0.75},
        calibration_ece=None,
        perception_completeness=0.92,
        data_freshness_minutes=75.0,
    )
    base.update(overrides)
    return base


def test_confidence_engine_matches_target_formula():
    ood = classify_ood_state({"score": -0.02, "is_outlier": False})
    result = compute_automation_confidence(
        model_confidence=0.70,
        data_quality=0.80,
        signal_agreement=0.60,
        sensor_reliability=0.75,
        ood_assessment=ood,
    )

    expected = 0.40 * 0.70 + 0.20 * 0.80 + 0.20 * 0.60 + 0.20 * 0.75 - 0.05
    assert result.score == round(expected, 4)
    assert result.ood_state == "BORDERLINE"


def test_classify_ood_state_marks_severe_anomalous():
    result = classify_ood_state({"score": -0.30, "is_outlier": True})

    assert result.state == "SEVERE_ANOMALOUS"
    assert result.penalty == 0.20


def test_decision_engine_does_not_apply_second_confidence_penalty():
    result = run_decision_engine(**_decision_kwargs())

    assert result.confidence_score == 0.68


def test_elevation_adjustment_promotes_safe_below_sea_level_with_rain():
    adjusted_risk, threshold_delta, reason = _apply_elevation_adjustment(
        "SAFE",
        {
            "elevation_m": -0.8,
            "rainfall_1h_mm": 3.0,
            "is_local_depression": False,
            "water_level_delta": 0.0,
        },
    )

    assert adjusted_risk == "PRE_ALERT"
    assert threshold_delta == 0.0
    assert "below sea level" in reason


def test_elevation_adjustment_never_downgrades_warning_or_danger():
    for risk_level in ("WARNING", "DANGER"):
        adjusted_risk, _, _ = _apply_elevation_adjustment(
            risk_level,
            {
                "elevation_m": 15.0,
                "rainfall_1h_mm": 0.0,
                "is_local_depression": False,
                "water_level_delta": 0.0,
            },
        )
        assert adjusted_risk == risk_level
