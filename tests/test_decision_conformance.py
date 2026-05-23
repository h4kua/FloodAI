"""
Phase 3 - Divergence Protection conformance suite.

Locks the L0-L4 decision contract by asserting the canonical adapter
(``app.services.decision_engine.run_decision_engine`` -> ``app.domain.decide``)
produces the AUTHORITATIVE fields the legacy implementation produced for
representative scenarios across every layer.

Phase 6 update: the legacy implementation that this suite was originally
shadow-checking has been deleted (`_legacy_run_decision_engine_unused`
removed from `app/services/decision_engine.py`). The 42 conformance tests
below now stand alone as the executable contract for the canonical
authority — every L-level path, every cross-cutting invariant.

Coverage (per the master prompt):
  * L0   invalid input
  * L1   SIAGA override
  * L1.5 multi-signal
  * L2   escalation
  * L3   normal ML path
  * L3.3 inconsistency override (E9/E12 - new in canonical)
  * L3.7 multi-signal early WARNING (E3 - new in canonical)
  * L4   trend escalation
  * E4   SAFE -> PRE_ALERT (new in canonical)
  * E13  ML suppression on implausible input (new in canonical)
  * PIPELINE_FAILURE / LOW_TRUST / CONFLICT pass-through
  * PRE_ALERT round-trip through writer normalization
  * decision_trace persistence
  * authority serialization
  * RC-1 calibration penalty deactivation
  * Authority -> decision_source mapping completeness
"""

from __future__ import annotations

import pytest

from contracts import (
    DecisionAuthority,
    RiskLevel,
    SystemStatus,
)
from domain import (
    AdaptiveThresholds,
    PerceptionInputs,
    PhysicalSignals,
    ReasoningInputs,
    TrendSnapshot,
    decide,
)
from services.decision_engine import (
    DecisionResult,
    _AUTHORITY_TO_SOURCE,
    _build_canonical_inputs,
    run_decision_engine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeHydro:
    def __init__(
        self,
        *,
        severity_score: float = 0.0,
        rapid_escalation: bool = False,
        dominant_station: str = "",
        dominant_siaga: str = "",
    ) -> None:
        self.severity_score = severity_score
        self.rapid_escalation = rapid_escalation
        self.dominant_station = dominant_station
        self.dominant_siaga = dominant_siaga


def _kwargs(**overrides):
    """Build the legacy run_decision_engine kwargs with sane SAFE-baseline defaults."""
    base = dict(
        evaluation_risk_level="SAFE",
        adjusted_confidence=0.91,
        system_status="OK",
        probability=0.10,
        raw_model_confidence=0.91,
        failure_modes=[],
        baseline_result={},
        signals={"rainfall_mm": 8.0, "bmkg_severity": 0.20},
        diagnostics={"trend_state": {}},
        hydrology_assessment=None,
        plausibility_score=0.95,
        has_critical_violation=False,
        trust_breakdown=None,
        adaptive_classification={"effective_danger_threshold": 0.45},
        calibration_ece=None,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# L0 - invalid input
# ---------------------------------------------------------------------------


def test_L0_critical_violation_returns_unknown():
    r = run_decision_engine(**_kwargs(has_critical_violation=True))
    assert isinstance(r, DecisionResult)
    assert r.risk_level == "UNKNOWN"
    assert r.decision_source == "invalid_input_fallback"
    assert r.override_trace["authority"] == "L0_PHYSICAL"


def test_L0_low_plausibility_suppresses_ml():
    r = run_decision_engine(**_kwargs(plausibility_score=0.20, probability=0.85))
    assert r.risk_level == "UNKNOWN"
    assert r.decision_source == "invalid_input_fallback"


def test_L0_high_completeness_does_not_trigger_l0():
    r = run_decision_engine(**_kwargs())
    assert r.risk_level != "UNKNOWN"


# ---------------------------------------------------------------------------
# L1 - SIAGA physical override
# ---------------------------------------------------------------------------


def test_L1_water_level_above_95_forces_danger():
    r = run_decision_engine(
        **_kwargs(
            hydrology_assessment=_FakeHydro(
                severity_score=0.96,
                dominant_station="Manggarai",
                dominant_siaga="siaga1",
            )
        )
    )
    assert r.risk_level == "DANGER"
    assert r.decision_source == "physical_override"
    assert r.override_trace["triggered"] is True
    assert r.override_trace["authority"] == "L1_SIAGA"


def test_L1_water_level_below_95_does_not_force_danger():
    r = run_decision_engine(
        **_kwargs(hydrology_assessment=_FakeHydro(severity_score=0.80))
    )
    # 0.80 falls into L3.3 inconsistency band (>=0.75); not L1.
    assert r.risk_level in ("WARNING", "DANGER")


# ---------------------------------------------------------------------------
# L1.5 - multi-signal compound override
# ---------------------------------------------------------------------------


def test_L1_5_multi_signal_compound_forces_danger():
    r = run_decision_engine(
        **_kwargs(
            probability=0.42,
            signals={"rainfall_mm": 72.0, "bmkg_severity": 0.85},
            hydrology_assessment=_FakeHydro(severity_score=0.86),
        )
    )
    assert r.risk_level == "DANGER"
    # 0.86 < 0.95 so L1 doesn't fire; L1.5 fires from 3 of {rainfall>=60, water>=0.85, bmkg>=0.80}
    assert r.decision_source == "signal_override"
    assert r.override_trace["authority"] == "L1_5_MULTI"


# ---------------------------------------------------------------------------
# L2 - severe failure escalation
# ---------------------------------------------------------------------------


def test_L2_severe_failure_escalates_warning_to_danger():
    r = run_decision_engine(
        **_kwargs(
            probability=0.55,  # L3 -> WARNING (warning thr<=0.30, danger thr=0.75)
            adaptive_classification={"effective_danger_threshold": 0.75},
            failure_modes=[
                {
                    "type": "sensor_corruption",
                    "severity": "high",
                    "risk_escalation": True,
                    "confidence_penalty": 0.0,
                }
            ],
        )
    )
    assert r.risk_level == "DANGER"
    assert r.decision_source == "system_guardrail"


def test_L2_no_severe_failure_does_not_escalate():
    r = run_decision_engine(
        **_kwargs(
            probability=0.55,
            adaptive_classification={"effective_danger_threshold": 0.75},
            failure_modes=[
                {
                    "type": "minor_warning",
                    "severity": "low",
                    "risk_escalation": False,
                    "confidence_penalty": 0.0,
                }
            ],
        )
    )
    assert r.risk_level == "WARNING"
    assert r.decision_source == "ml_adaptive"


# ---------------------------------------------------------------------------
# L3 - ML adaptive
# ---------------------------------------------------------------------------


def test_L3_safe_baseline():
    r = run_decision_engine(**_kwargs())
    assert r.risk_level == "SAFE"
    assert r.decision_source == "ml_adaptive"


def test_L3_warning_via_threshold():
    r = run_decision_engine(
        **_kwargs(
            probability=0.55,
            adaptive_classification={"effective_danger_threshold": 0.75},
        )
    )
    assert r.risk_level == "WARNING"
    assert r.decision_source == "ml_adaptive"


def test_L3_danger_via_threshold():
    r = run_decision_engine(
        **_kwargs(
            probability=0.80,
            adaptive_classification={"effective_danger_threshold": 0.75},
        )
    )
    assert r.risk_level == "DANGER"


def test_L3_pre_alert_via_threshold_band():
    # prob 0.25 is in [pre_alert=0.20, warning<=0.30) for default danger=0.45
    r = run_decision_engine(**_kwargs(probability=0.25))
    assert r.risk_level == "PRE_ALERT"


# ---------------------------------------------------------------------------
# L3.3 - E9/E12 inconsistency override
# ---------------------------------------------------------------------------


def test_L3_3_inconsistency_override_when_ml_safe_but_hydro_severe():
    r = run_decision_engine(
        **_kwargs(
            probability=0.05,
            hydrology_assessment=_FakeHydro(severity_score=0.78),
        )
    )
    assert r.risk_level == "WARNING"
    assert r.decision_source == "system_guardrail"
    assert r.inconsistency_check["detected"] is True
    assert r.override_trace["authority"] == "L2_INTEGRITY"


def test_L3_3_inconsistency_does_not_fire_when_plausibility_low():
    # E13 (low plausibility) takes precedence over E9/E12
    r = run_decision_engine(
        **_kwargs(
            probability=0.05,
            plausibility_score=0.20,
            hydrology_assessment=_FakeHydro(severity_score=0.78),
        )
    )
    assert r.risk_level == "UNKNOWN"
    assert r.decision_source == "invalid_input_fallback"


# ---------------------------------------------------------------------------
# L3.7 - E3 multi-signal early WARNING
# ---------------------------------------------------------------------------


def test_L3_7_multi_signal_early_warning_fires():
    r = run_decision_engine(
        **_kwargs(
            probability=0.13,
            diagnostics={
                "trend_state": {
                    "risk_trend": "increasing",
                    "trend_strength": 0.45,
                    "trend_confidence": 0.70,
                    "rainfall_acc_3h": 22.0,
                    "water_level_delta_cur": 0.08,
                    "data_points": 3,
                }
            },
        )
    )
    assert r.risk_level == "WARNING"
    assert r.decision_source == "signal_override"
    assert r.override_trace["authority"] == "L1_5_MULTI"


def test_L3_7_does_not_fire_with_insufficient_data_points():
    """
    E3 (L3.7) requires data_points >= _EARLY_WARN_DATA_POINTS_MIN. With
    data_points=0 the L3.7 path must NOT mark the authority as L1_5_MULTI.
    Note: E4 (L4 SAFE->PRE_ALERT) may still fire independently because it
    has its own trigger conditions and does not require data_points.
    """
    r = run_decision_engine(
        **_kwargs(
            probability=0.13,
            diagnostics={
                "trend_state": {
                    "risk_trend": "increasing",
                    "trend_strength": 0.45,
                    "trend_confidence": 0.70,
                    "rainfall_acc_3h": 22.0,
                    "water_level_delta_cur": 0.08,
                    "data_points": 0,  # below E3 floor
                }
            },
        )
    )
    # E3 did not fire (authority would be L1_5_MULTI). Result may be SAFE
    # or PRE_ALERT depending on whether E4 fires; neither is L1_5_MULTI.
    assert r.override_trace["authority"] != "L1_5_MULTI", (
        f"L3.7 fired despite data_points=0: authority={r.override_trace['authority']}"
    )
    assert r.risk_level in ("SAFE", "PRE_ALERT")


# ---------------------------------------------------------------------------
# L4 - trend extension (sustained upward + SAFE->PRE_ALERT)
# ---------------------------------------------------------------------------


def test_L4_warning_to_danger_on_sustained_upward():
    r = run_decision_engine(
        **_kwargs(
            probability=0.55,
            adaptive_classification={"effective_danger_threshold": 0.75},
            diagnostics={
                "trend_state": {"recent_probabilities": [0.40, 0.50, 0.65]}
            },
        )
    )
    assert r.risk_level == "DANGER"
    assert r.decision_source == "trend_informed"
    assert r.override_trace["authority"] == "L4_TREND"


def test_E4_safe_to_pre_alert_via_rising_trend():
    # prob 0.15 in [_PRE_ALERT_PROB_FLOOR=0.12, pre_alert=0.20) -> L3 returns SAFE,
    # then L4 SAFE->PRE_ALERT fires because trend conditions are met.
    r = run_decision_engine(
        **_kwargs(
            probability=0.15,
            diagnostics={
                "trend_state": {
                    "risk_trend": "increasing",
                    "trend_strength": 0.32,
                    "trend_confidence": 0.58,
                    "data_points": 2,
                }
            },
        )
    )
    assert r.risk_level == "PRE_ALERT"
    assert r.decision_source == "trend_informed"
    assert r.override_trace["authority"] == "L4_TREND"


def test_E4_does_not_fire_below_prob_floor():
    r = run_decision_engine(
        **_kwargs(
            probability=0.05,  # below _PRE_ALERT_PROB_FLOOR=0.12
            diagnostics={
                "trend_state": {
                    "risk_trend": "increasing",
                    "trend_strength": 0.50,
                    "trend_confidence": 0.80,
                    "data_points": 2,
                }
            },
        )
    )
    assert r.risk_level == "SAFE"


# ---------------------------------------------------------------------------
# PRE_ALERT propagation
# ---------------------------------------------------------------------------


def test_pre_alert_propagates_to_writer_normalization():
    r = run_decision_engine(**_kwargs(probability=0.25))
    assert r.risk_level == "PRE_ALERT"

    from db.pipeline_writer import RiskLevel as WriterRisk
    from db.pipeline_writer import normalize_risk_level

    assert normalize_risk_level(r.risk_level) == WriterRisk.PRE_ALERT


# ---------------------------------------------------------------------------
# decision_trace persistence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,extra_kwargs",
    [
        ("L0", {"has_critical_violation": True}),
        (
            "L1",
            {"hydrology_assessment": _FakeHydro(severity_score=0.96)},
        ),
        ("L3-safe", {}),
        (
            "L3-warning",
            {"probability": 0.55, "adaptive_classification": {"effective_danger_threshold": 0.75}},
        ),
        (
            "L3.3-inconsistency",
            {"probability": 0.05, "hydrology_assessment": _FakeHydro(severity_score=0.78)},
        ),
    ],
)
def test_decision_trace_present_for_every_path(label, extra_kwargs):
    r = run_decision_engine(**_kwargs(**extra_kwargs))
    assert isinstance(r.decision_trace, list)
    assert len(r.decision_trace) >= 1, f"{label}: empty decision_trace"
    assert all(entry.startswith("[L") for entry in r.decision_trace), (
        f"{label}: trace entries missing L-level prefix"
    )


def test_authority_serialized_into_override_trace():
    r = run_decision_engine(**_kwargs())
    assert r.override_trace["authority"] == "L3_ML"


# ---------------------------------------------------------------------------
# system_status pass-through (PIPELINE_FAILURE / LOW_TRUST / CONFLICT)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    ["OK", "DEGRADED", "LOW_TRUST", "CONFLICT", "FAIL", "PIPELINE_FAILURE"],
)
def test_adapter_handles_every_canonical_system_status(status):
    """
    The adapter accepts any canonical SystemStatus from EvaluationAgent
    upstream and produces a structurally valid DecisionResult. system_status
    is set independently by EvaluationAgent (Phase 4 will collapse this);
    the adapter must not crash regardless of the value.
    """
    r = run_decision_engine(**_kwargs(system_status=status))
    assert isinstance(r, DecisionResult)
    assert r.risk_level in {"SAFE", "PRE_ALERT", "WARNING", "DANGER", "UNKNOWN"}
    assert r.decision_source in set(_AUTHORITY_TO_SOURCE.values())


# ---------------------------------------------------------------------------
# RC-1 calibration penalty deactivation
# ---------------------------------------------------------------------------


def test_calibration_penalty_always_zero_RC1():
    r = run_decision_engine(**_kwargs())
    assert r.confidence_adjustment["calibration_penalty"] == 0.0
    assert r.confidence_adjustment["applied"] is False
    assert "RC-1" in r.confidence_adjustment["reason"]


def test_calibration_penalty_zero_even_with_high_ece():
    r = run_decision_engine(**_kwargs(calibration_ece=0.95))
    assert r.confidence_adjustment["calibration_penalty"] == 0.0


# ---------------------------------------------------------------------------
# Authority -> decision_source mapping completeness
# ---------------------------------------------------------------------------


def test_every_decision_authority_has_source_mapping():
    """Every DecisionAuthority enum value must have a legacy decision_source string."""
    expected = set(DecisionAuthority)
    mapped = set(_AUTHORITY_TO_SOURCE.keys())
    missing = expected - mapped
    assert not missing, f"DecisionAuthority values without decision_source mapping: {missing}"


def test_decision_source_values_are_stable():
    """Lock the legacy decision_source string set so consumers don't break."""
    assert set(_AUTHORITY_TO_SOURCE.values()) == {
        "invalid_input_fallback",
        "physical_override",
        "signal_override",
        "bmkg_safety_floor",
        "hydro_floor",
        "system_guardrail",
        "ml_adaptive",
        "trend_informed",
    }


# ---------------------------------------------------------------------------
# canonical authority is the runtime authority (no shadow path)
# ---------------------------------------------------------------------------


def test_run_decision_engine_calls_canonical_decide():
    """
    Lock the invariant that run_decision_engine delegates to canonical_decide.
    If a future edit re-introduces the legacy escalation body, this test fails.
    """
    import inspect

    from services import decision_engine as de

    src = inspect.getsource(de.run_decision_engine)
    assert "canonical_decide" in src, "run_decision_engine no longer calls canonical_decide"
    assert "_decision_to_legacy_result" in src, (
        "run_decision_engine no longer maps via _decision_to_legacy_result"
    )


# ---------------------------------------------------------------------------
# canonical decide() direct smoke (independent of adapter)
# ---------------------------------------------------------------------------


def test_canonical_decide_L0_via_completeness():
    perception = PerceptionInputs(
        physically_plausible=True,
        completeness=0.10,
        freshness_min=5.0,
        max_water_level_ratio=0.50,
        rainfall_1h_mm=10.0,
        bmkg_max_severity=0.20,
    )
    reasoning = ReasoningInputs(probability=0.42, confidence=0.91, model_variant="rt")
    d = decide(perception, reasoning)
    assert d.risk_level == RiskLevel.UNKNOWN
    assert d.system_status == SystemStatus.FAIL
    assert d.authority == DecisionAuthority.L0_PHYSICAL


def test_canonical_decide_L1_5_compound_event():
    # water_ratio=0.88: above L1.5 water threshold (0.85) but below L1 (0.90)
    perception = PerceptionInputs(
        physically_plausible=True,
        completeness=0.96,
        freshness_min=5.0,
        max_water_level_ratio=0.88,
        rainfall_1h_mm=72.0,
        bmkg_max_severity=0.85,
    )
    reasoning = ReasoningInputs(probability=0.42, confidence=0.91, model_variant="rt")
    d = decide(perception, reasoning)
    assert d.risk_level == RiskLevel.DANGER
    assert d.authority == DecisionAuthority.L1_5_MULTI


def test_canonical_decide_threshold_validator():
    """AdaptiveThresholds must support pre_alert <= warning <= danger ordering."""
    t = AdaptiveThresholds(pre_alert=0.20, warning=0.30, danger=0.75)
    assert t.pre_alert <= t.warning <= t.danger


# ---------------------------------------------------------------------------
# build_canonical_inputs sanity (private helper, but contract-critical)
# ---------------------------------------------------------------------------


def test_build_canonical_inputs_produces_ordered_thresholds():
    inputs = _build_canonical_inputs(_kwargs())
    t = inputs["thresholds"]
    assert t.pre_alert <= t.warning <= t.danger, (
        f"adapter produced invalid threshold ordering: {t}"
    )


def test_build_canonical_inputs_handles_empty_signals():
    inputs = _build_canonical_inputs(
        _kwargs(signals={}, diagnostics={}, hydrology_assessment=None)
    )
    assert isinstance(inputs["perception"], PerceptionInputs)
    assert isinstance(inputs["reasoning"], ReasoningInputs)
    assert isinstance(inputs["physical"], PhysicalSignals)
    assert isinstance(inputs["trend"], TrendSnapshot)
