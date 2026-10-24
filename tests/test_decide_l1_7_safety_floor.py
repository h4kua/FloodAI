"""
L1.7 BMKG_SAFETY_FLOOR — typed-decide() conformance suite.

Covers the non-bypassable WARNING floor that fires when BMKG reports
Severe+Observed+Immediate (bmkg_max_severity >= 0.80) AND either:
  (a) measured rainfall >= 20mm/h, or
  (b) the ML model is out-of-distribution AND water-level data is unusable
      (max_water_level_ratio == 0.0 indicates stale / absent TMA).

The layer is implemented as a pure check inside ``app.domain.decision.decide``
and emits ``DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR`` with
``DecisionReason.SAFETY_FLOOR``. See app/domain/decision.py L1.7 block.
"""

from __future__ import annotations

from contracts import DecisionAuthority, DecisionReason, RiskLevel
from domain import (
    PerceptionInputs,
    PhysicalSignals,
    ReasoningInputs,
    decide,
)


def _safe_perception(**overrides) -> PerceptionInputs:
    base = dict(
        physically_plausible=True,
        completeness=0.95,
        freshness_min=2.0,
        max_water_level_ratio=0.0,
        rainfall_1h_mm=0.0,
        bmkg_max_severity=0.0,
    )
    base.update(overrides)
    return PerceptionInputs(**base)


def _safe_reasoning(**overrides) -> ReasoningInputs:
    base = dict(
        probability=0.05,
        confidence=0.90,
        model_variant="xgb-v2",
        ood_score=0.10,
    )
    base.update(overrides)
    return ReasoningInputs(**base)


# ---------------------------------------------------------------------------
# Positive cases — floor must fire
# ---------------------------------------------------------------------------


def test_her001_bmkg_severe_with_high_rainfall_forces_warning():
    """BMKG Severe+Observed+Immediate + measured rainfall 25mm/h -> WARNING."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
    )
    assert decision.risk_level == RiskLevel.WARNING
    assert decision.authority == DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR
    assert decision.reason == DecisionReason.SAFETY_FLOOR


def test_her003_bmkg_severe_with_ood_and_stale_tma_forces_warning():
    """BMKG Severe + OOD ML + max_water_level_ratio==0 (stale TMA) -> WARNING."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.90,
            rainfall_1h_mm=8.0,
            max_water_level_ratio=0.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
    )
    assert decision.risk_level == RiskLevel.WARNING
    assert decision.authority == DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR


def test_floor_preempts_ml_safe_output():
    """When the floor fires, L3 ML is never consulted — no L3_ML trace entry."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
    )
    layers = [entry["layer"] for entry in decision.decision_trace]
    assert DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR.value in layers
    assert DecisionAuthority.L3_ML.value not in layers


def test_decision_trace_records_l1_7_layer_with_sub_rule():
    """Trace entry records which sub-rule (high-rainfall vs ood+stale) fired."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
    )
    floor_entries = [
        e for e in decision.decision_trace
        if e["layer"] == DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR.value
    ]
    assert len(floor_entries) == 1
    assert floor_entries[0]["inputs"]["sub_rule"] == "bmkg_severe_high_rainfall"
    assert floor_entries[0]["outputs"]["risk"] == RiskLevel.WARNING.value


def test_floor_does_not_lower_an_ml_danger():
    """The floor raises to WARNING; it must not cap an ML DANGER at WARNING."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.99),
    )
    assert decision.risk_level == RiskLevel.DANGER
    assert decision.authority != DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR


def test_confidence_floor_is_at_least_half():
    """After floor fires, Decision.confidence is at least 0.50 (operator-legible)."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, confidence=0.05, ood_score=-0.045),
    )
    assert decision.confidence >= 0.50


def test_decision_reason_is_safety_floor_after_override():
    """decision_reason cannot drift from risk_level — SAFETY_FLOOR for non-SAFE."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
    )
    assert decision.reason == DecisionReason.SAFETY_FLOOR
    assert decision.risk_level != RiskLevel.SAFE


# ---------------------------------------------------------------------------
# Negative cases — floor must NOT fire
# ---------------------------------------------------------------------------


def test_no_floor_when_bmkg_below_severity_threshold():
    """bmkg_max_severity 0.50 (Moderate) + 25mm rain -> normal ML path, no floor."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.50,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.10),
    )
    assert decision.authority != DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR


def test_no_floor_when_low_rainfall_and_ml_in_distribution():
    """BMKG severe but rainfall low AND ML in-distribution -> no floor."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=8.0,
            max_water_level_ratio=0.0,
        ),
        reasoning=_safe_reasoning(probability=0.10, ood_score=0.20),
    )
    assert decision.authority != DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR


def test_no_floor_when_water_data_fresh_even_if_ood():
    """OOD ML but max_water_level_ratio > 0 (fresh TMA) -> (b) arm does not fire."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=8.0,
            max_water_level_ratio=0.40,
        ),
        reasoning=_safe_reasoning(probability=0.10, ood_score=-0.045),
    )
    assert decision.authority != DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR


# ---------------------------------------------------------------------------
# Layer precedence — higher layers must win over L1.7
# ---------------------------------------------------------------------------


def test_l1_siaga_takes_precedence_over_floor():
    """When water>=0.95, L1 SIAGA -> DANGER, not L1.7 -> WARNING."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
            max_water_level_ratio=0.96,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
    )
    assert decision.risk_level == RiskLevel.DANGER
    assert decision.authority == DecisionAuthority.L1_SIAGA


def test_l1_5_compound_takes_precedence_over_floor():
    """When >=2 extreme signals, L1.5 -> DANGER, not L1.7 -> WARNING."""
    decision = decide(
        perception=_safe_perception(
            bmkg_max_severity=0.95,
            rainfall_1h_mm=65.0,
            max_water_level_ratio=0.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
    )
    assert decision.risk_level == RiskLevel.DANGER
    assert decision.authority == DecisionAuthority.L1_5_MULTI


def test_l0_invalid_input_takes_precedence_over_floor():
    """When perception is implausible, L0 -> UNKNOWN, not L1.7."""
    decision = decide(
        perception=_safe_perception(
            physically_plausible=False,
            bmkg_max_severity=0.95,
            rainfall_1h_mm=25.0,
        ),
        reasoning=_safe_reasoning(probability=0.0, ood_score=-0.045),
        physical=PhysicalSignals(plausibility_score=0.10, has_critical_violation=True),
    )
    assert decision.risk_level == RiskLevel.UNKNOWN
    assert decision.authority == DecisionAuthority.L0_PHYSICAL
