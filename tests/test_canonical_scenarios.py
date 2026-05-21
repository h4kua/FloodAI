"""
Canonical scenario harness — Subphase E.

Authority: app.domain.decision.decide() called directly — no adapters, no
legacy shims, no DB, no network.

PIPELINE_FAILURE is not reachable from canonical decide(); it is only
produced by FloodDecisionPipeline._emergency_output() on unhandled agent
crash. Coverage lives in integration tests only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pytest

from contracts import DecisionAuthority, FailureSeverity, RiskLevel, SystemStatus
from domain.decision import (
    AdaptiveThresholds,
    Decision,
    FailureMode,
    PerceptionInputs,
    PhysicalSignals,
    ReasoningInputs,
    TrendSnapshot,
    decide,
)

# ---------------------------------------------------------------------------
# Tiny builder helpers
# ---------------------------------------------------------------------------


def _perc(
    *,
    plausible: bool = True,
    completeness: float = 1.0,
    freshness_min: float = 5.0,
    water_ratio: float = 0.30,
    rain_1h: float = 5.0,
    bmkg: float = 0.10,
) -> PerceptionInputs:
    return PerceptionInputs(
        physically_plausible=plausible,
        completeness=completeness,
        freshness_min=freshness_min,
        max_water_level_ratio=water_ratio,
        rainfall_1h_mm=rain_1h,
        bmkg_max_severity=bmkg,
    )


def _reason(prob: float = 0.10, conf: float = 0.90) -> ReasoningInputs:
    return ReasoningInputs(probability=prob, confidence=conf, model_variant="xgb")


def _fail(
    ftype: str, sev: FailureSeverity, escalate: bool, penalty: float = 0.0
) -> FailureMode:
    return FailureMode(
        failure_type=ftype,
        severity=sev,
        risk_escalation=escalate,
        confidence_penalty=penalty,
    )


def _phys(
    *,
    hydro: float = 0.0,
    rapid: bool = False,
    plausibility: float = 1.0,
    critical: bool = False,
) -> PhysicalSignals:
    return PhysicalSignals(
        hydrology_max_severity=hydro,
        rapid_escalation=rapid,
        plausibility_score=plausibility,
        has_critical_violation=critical,
    )


def _layers(d: Decision) -> List[str]:
    """Ordered layer names from the decision trace."""
    return [step["layer"] for step in d.decision_trace]


def _override_tags(d: Decision) -> List[str]:
    """All override values from trace outputs (preserves order)."""
    return [
        step["outputs"]["override"]
        for step in d.decision_trace
        if "override" in step["outputs"]
    ]


# ---------------------------------------------------------------------------
# Scenario descriptor
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    name: str
    perc: PerceptionInputs
    reason: ReasoningInputs
    expected_risk: str
    expected_status: str
    expected_authority: str
    expected_trace_layers: List[str]
    failures: List[FailureMode] = field(default_factory=list)
    physical: Optional[PhysicalSignals] = None
    trend: Optional[TrendSnapshot] = None
    thresholds: Optional[AdaptiveThresholds] = None
    expected_safe: Optional[bool] = None
    expected_override_tags: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

_SCENARIOS: List[Scenario] = [
    # ── L3 ML baseline ──────────────────────────────────────────────────────
    Scenario(
        name="baseline_safe",
        perc=_perc(),
        reason=_reason(prob=0.10),
        expected_risk="SAFE",
        expected_status="OK",
        expected_authority="L3_ML",
        expected_trace_layers=["L3_ML"],
        expected_safe=True,
    ),
    Scenario(
        name="l3_ml_warning",
        perc=_perc(),
        reason=_reason(prob=0.55),
        expected_risk="WARNING",
        expected_status="OK",
        expected_authority="L3_ML",
        expected_trace_layers=["L3_ML"],
        expected_safe=False,
    ),
    # ── L0 physical gate ────────────────────────────────────────────────────
    Scenario(
        name="l0_invalid_input_implausible",
        perc=_perc(plausible=False),
        reason=_reason(),
        expected_risk="UNKNOWN",
        expected_status="FAIL",
        expected_authority="L0_PHYSICAL",
        expected_trace_layers=["L0_PHYSICAL"],
        expected_safe=False,
    ),
    Scenario(
        name="l0_sensor_corruption_critical_violation",
        perc=_perc(),
        reason=_reason(),
        physical=_phys(critical=True),
        expected_risk="UNKNOWN",
        expected_status="FAIL",
        expected_authority="L0_PHYSICAL",
        expected_trace_layers=["L0_PHYSICAL"],
        expected_safe=False,
    ),
    Scenario(
        name="l0_ood_low_plausibility",
        perc=_perc(),
        reason=_reason(prob=0.85),
        physical=_phys(plausibility=0.20),
        expected_risk="UNKNOWN",
        expected_status="FAIL",
        expected_authority="L0_PHYSICAL",
        expected_trace_layers=["L0_PHYSICAL"],
        expected_safe=False,
    ),
    Scenario(
        name="l0_missing_critical_data_low_completeness",
        perc=_perc(completeness=0.25),
        reason=_reason(),
        expected_risk="UNKNOWN",
        expected_status="FAIL",
        expected_authority="L0_PHYSICAL",
        expected_trace_layers=["L0_PHYSICAL"],
        expected_safe=False,
    ),
    # ── L1 / L1.5 / L1.6 physical escalation ───────────────────────────────
    Scenario(
        name="l1_siaga_absolute_water_level",
        perc=_perc(water_ratio=0.97),
        reason=_reason(prob=0.60),
        expected_risk="DANGER",
        expected_status="OK",
        expected_authority="L1_SIAGA",
        expected_trace_layers=["L1_SIAGA"],
        expected_safe=False,
    ),
    Scenario(
        name="l1_5_multi_signal_compound",
        perc=_perc(rain_1h=65.0, water_ratio=0.87, bmkg=0.85),
        reason=_reason(prob=0.50),
        expected_risk="DANGER",
        expected_status="OK",
        expected_authority="L1_5_MULTI",
        expected_trace_layers=["L1_5_MULTI"],
        expected_safe=False,
    ),
    Scenario(
        name="l1_6_rapid_hydrological_escalation",
        # water_ratio=0.80: below L1 (0.95) and L1.5 (0.85) thresholds
        perc=_perc(water_ratio=0.80, rain_1h=5.0, bmkg=0.10),
        reason=_reason(prob=0.40),
        physical=_phys(rapid=True, hydro=0.55),
        expected_risk="DANGER",
        expected_status="OK",
        expected_authority="L1_SIAGA",
        expected_trace_layers=["L1_SIAGA"],
        expected_safe=False,
        expected_override_tags=["rapid_escalation_physical_gate"],
    ),
    # ── L2 integrity escalation ─────────────────────────────────────────────
    Scenario(
        name="l2_integrity_escalation",
        perc=_perc(),
        reason=_reason(prob=0.10),  # → SAFE; L2 bumps to PRE_ALERT
        failures=[_fail("implausible_input", FailureSeverity.HIGH, escalate=True)],
        expected_risk="PRE_ALERT",
        expected_status="DEGRADED",
        expected_authority="L2_INTEGRITY",
        expected_trace_layers=["L3_ML", "L2_INTEGRITY"],
        expected_safe=False,
    ),
    # ── L3.3 ML/hydrology inconsistency override ────────────────────────────
    Scenario(
        name="l3_3_ml_safe_but_hydro_severe",
        perc=_perc(),
        reason=_reason(prob=0.05),  # → SAFE; L3.3 overrides to WARNING
        physical=_phys(hydro=0.80),
        expected_risk="WARNING",
        expected_status="OK",
        expected_authority="L2_INTEGRITY",
        expected_trace_layers=["L3_ML", "L2_INTEGRITY"],
        expected_safe=False,
    ),
    # ── L3.7 multi-signal early warning convergence ─────────────────────────
    Scenario(
        name="l3_7_early_warning_convergence",
        perc=_perc(),
        reason=_reason(prob=0.15),  # → SAFE; L3.7 overrides to WARNING
        trend=TrendSnapshot(
            risk_trend="increasing",
            trend_strength=0.40,
            trend_confidence=0.70,
            rainfall_acc_3h=25.0,
            water_level_delta_cur=0.08,
            data_points=3,
        ),
        expected_risk="WARNING",
        expected_status="OK",
        expected_authority="L1_5_MULTI",
        expected_trace_layers=["L3_ML", "L1_5_MULTI"],
        expected_safe=False,
    ),
    # ── L4 trend extension ──────────────────────────────────────────────────
    Scenario(
        name="l4_trend_warning_to_danger",
        perc=_perc(),
        reason=_reason(prob=0.55),  # → WARNING; L4 sustained_upward → DANGER
        trend=TrendSnapshot(recent_probabilities=(0.35, 0.50, 0.65)),
        expected_risk="DANGER",
        expected_status="OK",
        expected_authority="L4_TREND",
        expected_trace_layers=["L3_ML", "L4_TREND"],
        expected_safe=False,
    ),
    Scenario(
        name="l4_pre_alert_rising_trend",
        perc=_perc(),
        reason=_reason(prob=0.20),  # → SAFE; E4 rising trend → PRE_ALERT
        trend=TrendSnapshot(
            risk_trend="increasing",
            trend_strength=0.35,
            trend_confidence=0.60,
        ),
        expected_risk="PRE_ALERT",
        expected_status="OK",
        expected_authority="L4_TREND",
        expected_trace_layers=["L3_ML", "L4_TREND"],
        expected_safe=False,
    ),
    # ── Status-only variations (risk level unchanged by non-escalating failures)
    Scenario(
        name="conflicting_signals_conflict_status",
        perc=_perc(),
        reason=_reason(prob=0.10),
        failures=[_fail("signal_conflict", FailureSeverity.HIGH, escalate=False)],
        expected_risk="SAFE",
        expected_status="CONFLICT",
        expected_authority="L3_ML",
        expected_trace_layers=["L3_ML"],
        expected_safe=False,
    ),
    Scenario(
        name="degraded_stale_data",
        perc=_perc(freshness_min=90.0),
        reason=_reason(prob=0.10),
        expected_risk="SAFE",
        expected_status="DEGRADED",
        expected_authority="L3_ML",
        expected_trace_layers=["L3_ML"],
        expected_safe=False,
    ),
    Scenario(
        name="low_trust_operation",
        perc=_perc(),
        reason=_reason(prob=0.10),
        failures=[_fail("low_trust", FailureSeverity.HIGH, escalate=False)],
        expected_risk="SAFE",
        expected_status="LOW_TRUST",
        expected_authority="L3_ML",
        expected_trace_layers=["L3_ML"],
        expected_safe=False,
    ),
]


# ---------------------------------------------------------------------------
# Parametrized scenario tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("s", _SCENARIOS, ids=[s.name for s in _SCENARIOS])
def test_risk_level(s: Scenario) -> None:
    d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
    assert d.risk_level.value == s.expected_risk


@pytest.mark.parametrize("s", _SCENARIOS, ids=[s.name for s in _SCENARIOS])
def test_system_status(s: Scenario) -> None:
    d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
    assert d.system_status.value == s.expected_status


@pytest.mark.parametrize("s", _SCENARIOS, ids=[s.name for s in _SCENARIOS])
def test_authority(s: Scenario) -> None:
    d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
    assert d.authority.value == s.expected_authority


@pytest.mark.parametrize("s", _SCENARIOS, ids=[s.name for s in _SCENARIOS])
def test_trace_layers(s: Scenario) -> None:
    d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
    assert _layers(d) == s.expected_trace_layers


@pytest.mark.parametrize(
    "s",
    [s for s in _SCENARIOS if s.expected_safe is not None],
    ids=[s.name for s in _SCENARIOS if s.expected_safe is not None],
)
def test_safe_for_automation(s: Scenario) -> None:
    d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
    assert d.is_safe_for_automation == s.expected_safe


@pytest.mark.parametrize(
    "s",
    [s for s in _SCENARIOS if s.expected_override_tags is not None],
    ids=[s.name for s in _SCENARIOS if s.expected_override_tags is not None],
)
def test_override_tags(s: Scenario) -> None:
    d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
    assert _override_tags(d) == s.expected_override_tags


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------


def test_decision_is_frozen() -> None:
    d = decide(_perc(), _reason())
    with pytest.raises(AttributeError):
        d.risk_level = RiskLevel.DANGER  # type: ignore[misc]


def test_decision_trace_is_tuple_not_list() -> None:
    d = decide(_perc(), _reason())
    assert isinstance(d.decision_trace, tuple)
    with pytest.raises(AttributeError):
        d.decision_trace.append({"layer": "INJECTED"})  # type: ignore[attr-defined]


def test_no_legacy_markers_in_trace() -> None:
    for s in _SCENARIOS:
        d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
        for step in d.decision_trace:
            assert "-" not in step["layer"], (
                f"Hyphenated (legacy) layer marker in scenario {s.name!r}: {step['layer']!r}"
            )


def test_authority_aligns_with_last_trace_layer() -> None:
    for s in _SCENARIOS:
        d = decide(s.perc, s.reason, s.failures, s.trend, s.thresholds, s.physical)
        layers = _layers(d)
        assert layers, f"Empty trace for scenario {s.name!r}"
        assert d.authority.value == layers[-1], (
            f"Scenario {s.name!r}: authority={d.authority.value!r} "
            f"but last trace layer={layers[-1]!r}"
        )


def test_deterministic_replay() -> None:
    perc = _perc(water_ratio=0.70, rain_1h=30.0, bmkg=0.50)
    reason = _reason(prob=0.45, conf=0.80)
    phys = _phys(rapid=True, hydro=0.55)
    d1 = decide(perc, reason, physical=phys)
    d2 = decide(perc, reason, physical=phys)
    assert d1 == d2
