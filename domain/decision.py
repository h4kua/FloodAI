"""
Canonical flood-decision authority.

This module collapses the previously-fragmented decision logic (spread across
seven files) into ONE pure function: ``decide()``. Every code path that
changes a final ``risk_level`` lives here. There is no hidden L1.5 or L2.5;
the layering is explicit and the chosen layer is recorded in
``Decision.authority`` for forensic audit.

Decision hierarchy (top wins, evaluated top-to-bottom):

  L0   PHYSICAL       - invalid input -> UNKNOWN/FAIL (non-bypassable)
  L1   SIAGA          - water_level_ratio >= 0.90 anywhere -> DANGER (CRITICAL_HYDROLOGY)
  L1.5 MULTI          - >=2 of {rainfall>=60, water>=0.85, bmkg>=0.80} -> DANGER (COMPOUND_EVENT)
  L2   INTEGRITY      - severe failures (>=HIGH, risk_escalation) -> escalate one level
  L3   ML             - calibrated probability vs adaptive thresholds
  L1.8 HYDRO_FLOOR    - post-ML: ratio>=0.75->WARNING, >=0.60->PRE_ALERT (one-way floor)
  L1.9 OOD_FLOOR      - post-ML: ood<-0.05->PRE_ALERT/70% cap, <-0.10->WARNING/55% cap
  L4   TREND          - sustained upward -> WARNING->DANGER (one-way, asymmetric)

This module has zero dependencies on FastAPI, psycopg2, sklearn, or any
external service. Everything is a pure function over typed dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List, Optional, Tuple

from contracts import (
    DecisionAuthority,
    DecisionReason,
    Driver,
    FailureSeverity,
    RiskLevel,
    SystemStatus,
)
from contracts.vocabulary import resolve_status

# ---------------------------------------------------------------------------
# Inputs (typed, immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerceptionInputs:
    """Outputs of PerceptionAgent that the decision authority cares about."""

    physically_plausible: bool
    completeness: float            # [0, 1]
    freshness_min: float           # minutes since acquisition; -1 = unknown
    max_water_level_ratio: float   # max across stations, [0, 1+ when overtopped]
    rainfall_1h_mm: float          # mm in last hour
    bmkg_max_severity: float       # [0, 1] - peak alert severity score


@dataclass(frozen=True)
class ReasoningInputs:
    """Outputs of ReasoningAgent that the decision authority cares about."""

    probability: float             # calibrated ML probability, [0, 1]
    confidence: float              # base confidence before penalties, [0, 1]
    model_variant: str
    ood_score: float = 0.0         # IsolationForest decision_function; <0 = OOD


@dataclass(frozen=True)
class FailureMode:
    failure_type: str
    severity: FailureSeverity
    risk_escalation: bool
    confidence_penalty: float = 0.0


@dataclass(frozen=True)
class TrendSnapshot:
    """
    Recent decision history for L4 trend extension and L3.7 multi-signal early
    WARNING. All fields except recent_probabilities are optional with safe
    defaults so legacy callers that pass only recent_probabilities still work.
    """

    recent_probabilities: Tuple[float, ...] = ()
    # Extended trend state (used by E3 multi-signal early WARNING + E4 SAFE->PRE_ALERT)
    risk_trend: str = ""               # "increasing" | "stable" | "decreasing" | ""
    trend_strength: float = 0.0        # [0, 1]
    trend_confidence: float = 0.0      # [0, 1]
    rainfall_acc_3h: float = 0.0       # mm accumulated last 3h
    water_level_delta_cur: float = 0.0 # current ratio delta
    data_points: int = 0               # number of prior predictions in buffer

    def sustained_upward(self, *, min_points: int = 3, slope_threshold: float = 0.10) -> bool:
        if len(self.recent_probabilities) < min_points:
            return False
        window = self.recent_probabilities[-min_points:]
        deltas = [b - a for a, b in zip(window[:-1], window[1:])]
        return all(d > 0 for d in deltas) and (window[-1] - window[0]) >= slope_threshold


@dataclass(frozen=True)
class PhysicalSignals:
    """
    Physical-world evidence used to detect ML/physical inconsistency (E9/E12)
    and to suppress ML escalation when input is implausible (E13). Optional;
    omitting it makes those rules no-ops.
    """

    hydrology_max_severity: float = 0.0   # [0, 1] max station SIAGA severity
    rapid_escalation: bool = False        # rapid water-level rise detected
    plausibility_score: float = 1.0       # [0, 1] from PerceptionAgent
    has_critical_violation: bool = False  # hard physical-gate failure


@dataclass(frozen=True)
class AdaptiveThresholds:
    """Operating thresholds for L3 ML classification."""

    pre_alert: float = 0.30
    warning: float = 0.50
    danger: float = 0.75


# ---------------------------------------------------------------------------
# Tuning constants for the ported legacy rules (E3, E4, E9/E12, E13).
# Single place to inspect; mirrored from the legacy decision_engine.py and
# adaptive_threshold.py so behavior is preserved when the engine becomes a
# thin adapter around decide().
# ---------------------------------------------------------------------------
_HYDRO_MIN_PLAUSIBILITY = 0.30        # E13: below this, ML escalation suppressed
_INCONSISTENCY_HYDRO_MIN = 0.75       # E9/E12: ML SAFE + hydrology >= this -> WARNING
_HYDRO_RAPID_SEVERITY = 0.50          # L1.6: rapid rise at this severity -> DANGER
_PRE_ALERT_PROB_FLOOR = 0.12          # E4: below this, even rising trend stays SAFE
_PRE_ALERT_STRENGTH_MIN = 0.30
_PRE_ALERT_CONFIDENCE_MIN = 0.55
_EARLY_WARN_PROB_FLOOR = 0.12         # E3: multi-signal early WARNING gates
_EARLY_WARN_STRENGTH_MIN = 0.35
_EARLY_WARN_CONFIDENCE_MIN = 0.65
_EARLY_WARN_RAIN_3H_MIN = 20.0
_EARLY_WARN_WATER_DELTA_MIN = 0.06
_EARLY_WARN_DATA_POINTS_MIN = 2

# ---------------------------------------------------------------------------
# L1.7 BMKG_SAFETY_FLOOR — non-bypassable WARNING floor for BMKG-severe gaps.
# ---------------------------------------------------------------------------
# Fires when BMKG reports Severe+Observed+Immediate (severity score >= 0.80)
# AND at least one of:
#   (a) measured rainfall is already in the "high" band (>= 20mm/h), which
#       L1.5 alone does not catch (L1.5 needs rainfall >= 60mm/h paired with
#       another extreme signal).
#   (b) the ML model is out-of-distribution AND water-level data is unusable
#       (max_water_level_ratio == 0.0 indicates the hydrology channel is
#       stale / absent). In this state ML SAFE cannot be trusted: the
#       inconsistency-override (L3.3) won't fire either because it needs
#       hydrology_max_severity >= 0.75, which a stale channel can't produce.
#
# When fired, escalates the decision to WARNING with confidence floor 0.50,
# pre-empting L3 ML entirely. Authority = L1_7_BMKG_SAFETY_FLOOR (forensic).
_BMKG_SAFETY_FLOOR_SEVERITY_MIN = 0.80
_BMKG_SAFETY_FLOOR_RAIN_MIN = 20.0
_BMKG_SAFETY_FLOOR_CONFIDENCE_FLOOR = 0.50

# ---------------------------------------------------------------------------
# L1 / L1.8 water-level ratio thresholds — BNPB/BPBD Siaga standard.
# ---------------------------------------------------------------------------
# L1 fires unconditionally (pre-ML); L1.8 is a post-ML one-way floor.
# These constants are the single source of truth for all ratio comparisons.
_WL_DANGER_FLOOR = 0.90    # L1 hard gate  + L1.8 DANGER floor
_WL_WARNING_FLOOR = 0.75   # L1.8 WARNING floor
_WL_PRE_ALERT_FLOOR = 0.60 # L1.8 PRE_ALERT floor

# ---------------------------------------------------------------------------
# L1.9 OOD_FLOOR — conservative risk floor + confidence cap for OOD inputs.
# ---------------------------------------------------------------------------
# IsolationForest decision_function: more negative = further from training dist.
# Two tiers (score is always <= 0 when is_outlier=True):
#   moderate: score < -0.05 → PRE_ALERT floor, confidence capped at 0.70
#   severe:   score < -0.10 → WARNING floor, confidence capped at 0.55
_OOD_MODERATE_SCORE = -0.05
_OOD_SEVERE_SCORE = -0.10
_OOD_MODERATE_CONF_CAP = 0.70
_OOD_SEVERE_CONF_CAP = 0.55


# ---------------------------------------------------------------------------
# Output (typed, immutable)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    risk_level: RiskLevel
    system_status: SystemStatus
    reason: DecisionReason
    authority: DecisionAuthority
    confidence: float
    driver: Driver
    ml_execution_mode: str         # "FULL" | "SHADOW_ONLY"
    is_safe_for_automation: bool
    decision_trace: Tuple[dict, ...] = field(default_factory=tuple)

    def with_(self, **changes) -> "Decision":
        """Immutable update - returns a new Decision with selected fields replaced."""
        return replace(self, **changes)


# ---------------------------------------------------------------------------
# Internal helpers (private - call sites must use ``decide()``)
# ---------------------------------------------------------------------------

_RISK_RANK = {
    RiskLevel.UNKNOWN: 0,
    RiskLevel.SAFE: 1,
    RiskLevel.PRE_ALERT: 2,
    RiskLevel.WARNING: 3,
    RiskLevel.DANGER: 4,
}
_ESCALATE_NEXT = {
    RiskLevel.SAFE: RiskLevel.PRE_ALERT,
    RiskLevel.PRE_ALERT: RiskLevel.WARNING,
    RiskLevel.WARNING: RiskLevel.DANGER,
    RiskLevel.DANGER: RiskLevel.DANGER,
    RiskLevel.UNKNOWN: RiskLevel.UNKNOWN,
}


def _ml_classify(reasoning: ReasoningInputs, thresholds: AdaptiveThresholds) -> RiskLevel:
    p = reasoning.probability
    if p >= thresholds.danger:
        return RiskLevel.DANGER
    if p >= thresholds.warning:
        return RiskLevel.WARNING
    if p >= thresholds.pre_alert:
        return RiskLevel.PRE_ALERT
    return RiskLevel.SAFE


def _escalate_one_level(level: RiskLevel) -> RiskLevel:
    return _ESCALATE_NEXT[level]


def _penalize_confidence(
    base: float,
    failures: List[FailureMode],
    perception: PerceptionInputs,
) -> float:
    """
    Confidence is computed upstream by the centralized confidence engine.

    The canonical decision layer may clamp the score into the public range,
    but it must not apply another stack of penalties.
    """
    return max(0.05, min(1.0, base))


def _resolve_system_status(
    failures: List[FailureMode],
    perception: PerceptionInputs,
) -> SystemStatus:
    """
    Collapse all applicable statuses into one via SYSTEM_STATUS_PRECEDENCE.
    Precedence: PIPELINE_FAILURE > FAIL > CONFLICT > LOW_TRUST > DEGRADED > OK.
    """
    candidates: List[SystemStatus] = [SystemStatus.OK]

    severe = [
        f for f in failures
        if f.severity in (FailureSeverity.HIGH, FailureSeverity.CRITICAL)
    ]
    if any(f.failure_type in ("signal_conflict", "semantic_inconsistency") for f in severe):
        candidates.append(SystemStatus.CONFLICT)
    if any(f.failure_type in ("low_trust", "low_confidence") for f in severe):
        candidates.append(SystemStatus.LOW_TRUST)
    if severe:
        candidates.append(SystemStatus.DEGRADED)
    if perception.freshness_min > 60 or perception.completeness < 0.50:
        candidates.append(SystemStatus.DEGRADED)

    return resolve_status(*candidates)


def _select_driver(perception: PerceptionInputs, reasoning: ReasoningInputs) -> Driver:
    """Pick the dominant Driver based on signal magnitudes (deterministic)."""
    if perception.max_water_level_ratio >= _WL_DANGER_FLOOR:
        return Driver.CRITICAL_HYDROLOGY
    if perception.max_water_level_ratio >= _WL_WARNING_FLOOR:
        return Driver.HYDROLOGY_STRESS
    if perception.rainfall_1h_mm >= 60:
        return Driver.EXTREME_RAINFALL
    if perception.rainfall_1h_mm >= 40:
        return Driver.SUSTAINED_RAINFALL
    if perception.rainfall_1h_mm >= 20:
        return Driver.HIGH_RAINFALL
    if perception.bmkg_max_severity >= 0.80:
        return Driver.BMKG_CONFIRMED_ALERT
    if perception.bmkg_max_severity >= 0.50:
        return Driver.BMKG_FORECAST_ALERT
    if reasoning.probability >= 0.50:
        return Driver.ATMOSPHERIC_BUILDUP
    return Driver.LOW_BACKGROUND_RISK


def _trace(layer: DecisionAuthority, inputs: dict, outputs: dict) -> dict:
    return {"layer": layer.value, "inputs": inputs, "outputs": outputs}


# ---------------------------------------------------------------------------
# Ported legacy rules (E3, E4, E9/E12, E13) -- canonical implementations.
# ---------------------------------------------------------------------------


def _should_suppress_ml_escalation(physical: Optional[PhysicalSignals]) -> bool:
    """
    E13: When physical input is severely implausible, do not let the ML layer
    promote risk above SAFE. Returns True when ML escalation must be capped.
    """
    if physical is None:
        return False
    if physical.has_critical_violation:
        return True
    if physical.plausibility_score < _HYDRO_MIN_PLAUSIBILITY:
        return True
    return False


def _check_inconsistency_override(
    base_risk: RiskLevel,
    physical: Optional[PhysicalSignals],
) -> bool:
    """
    E9/E12: ML returned SAFE but physical hydrology evidence is high enough
    that the disagreement itself is a signal. Forces SAFE -> WARNING.
    Plausibility floor prevents this firing on suspect input (already
    captured by E13 / L0).
    """
    if base_risk != RiskLevel.SAFE or physical is None:
        return False
    if physical.has_critical_violation:
        return False
    if physical.plausibility_score < _HYDRO_MIN_PLAUSIBILITY:
        return False
    return physical.hydrology_max_severity >= _INCONSISTENCY_HYDRO_MIN


def _check_early_warning_convergence(
    base_risk: RiskLevel,
    reasoning: ReasoningInputs,
    trend: TrendSnapshot,
) -> bool:
    """
    E3: SAFE -> WARNING when multiple physical signals converge upward across
    >=2 prior predictions. Requires rising trend AND strong trend confidence
    AND rainfall accumulation AND water-level delta. Pure-data check; no
    false-alarm risk on first-call inputs (data_points=0 fails the gate).
    """
    if base_risk != RiskLevel.SAFE:
        return False
    if reasoning.probability < _EARLY_WARN_PROB_FLOOR:
        return False
    if trend.risk_trend != "increasing":
        return False
    if trend.trend_strength < _EARLY_WARN_STRENGTH_MIN:
        return False
    if trend.trend_confidence < _EARLY_WARN_CONFIDENCE_MIN:
        return False
    if trend.rainfall_acc_3h < _EARLY_WARN_RAIN_3H_MIN:
        return False
    if trend.water_level_delta_cur < _EARLY_WARN_WATER_DELTA_MIN:
        return False
    if trend.data_points < _EARLY_WARN_DATA_POINTS_MIN:
        return False
    return True


def _check_bmkg_safety_floor(
    perception: PerceptionInputs,
    reasoning: ReasoningInputs,
) -> tuple[bool, str]:
    """
    L1.7: BMKG-severe + (high-rainfall OR OOD+stale-TMA) -> WARNING floor.

    Returns ``(fired, sub_rule)`` where ``sub_rule`` is one of
    ``"bmkg_severe_high_rainfall"`` or ``"bmkg_severe_ood_stale_tma"`` when
    fired, and ``""`` otherwise. The sub-rule is recorded in the decision
    trace so operators can see *why* the floor engaged.
    """
    if perception.bmkg_max_severity < _BMKG_SAFETY_FLOOR_SEVERITY_MIN:
        return False, ""
    if perception.rainfall_1h_mm >= _BMKG_SAFETY_FLOOR_RAIN_MIN:
        return True, "bmkg_severe_high_rainfall"
    if reasoning.ood_score < 0.0 and perception.max_water_level_ratio == 0.0:
        return True, "bmkg_severe_ood_stale_tma"
    return False, ""


def _check_pre_alert_trend(
    base_risk: RiskLevel,
    reasoning: ReasoningInputs,
    trend: TrendSnapshot,
) -> bool:
    """
    E4: SAFE -> PRE_ALERT when probability is below SAFE ceiling but a rising
    trend has been established across prior predictions. Asymmetric for
    safety: never downgrades, only upgrades SAFE.
    """
    if base_risk != RiskLevel.SAFE:
        return False
    if reasoning.probability < _PRE_ALERT_PROB_FLOOR:
        return False
    if trend.risk_trend != "increasing":
        return False
    if trend.trend_strength < _PRE_ALERT_STRENGTH_MIN:
        return False
    if trend.trend_confidence < _PRE_ALERT_CONFIDENCE_MIN:
        return False
    return True


# ---------------------------------------------------------------------------
# Public API - the ONLY decision authority
# ---------------------------------------------------------------------------


def decide(
    perception: PerceptionInputs,
    reasoning: ReasoningInputs,
    failures: Optional[List[FailureMode]] = None,
    trend: Optional[TrendSnapshot] = None,
    thresholds: Optional[AdaptiveThresholds] = None,
    physical: Optional[PhysicalSignals] = None,
) -> Decision:
    """
    Compute the final flood Decision from typed inputs.

    Pure function: no I/O, no global state, no side effects. Returns a
    Decision whose ``authority`` field records which L-level fired.

    Layer ordering is mandatory; the first matching layer wins, except for
    L3.3/L3.7/L4 which only re-evaluate when the L3 ML output was SAFE/WARNING.
    """
    failures = failures or []
    trend = trend or TrendSnapshot()
    thresholds = thresholds or AdaptiveThresholds()
    decision_trace: List[dict] = []

    # ------------------------------------------------------------------ L0
    # L0 fires on either: (a) classic invalid input (legacy contract), or
    # (b) E13: physical input so implausible that ML escalation must be
    # suppressed. Both produce UNKNOWN/FAIL — the system has no trustworthy
    # basis on which to act.
    suppress_ml = _should_suppress_ml_escalation(physical)
    if (
        (not perception.physically_plausible)
        or perception.completeness < 0.30
        or suppress_ml
    ):
        decision_trace.append(_trace(
            DecisionAuthority.L0_PHYSICAL,
            inputs={
                "physically_plausible": perception.physically_plausible,
                "completeness": perception.completeness,
                "suppress_ml": suppress_ml,
                "plausibility_score": (
                    physical.plausibility_score if physical is not None else None
                ),
                "has_critical_violation": (
                    physical.has_critical_violation if physical is not None else None
                ),
            },
            outputs={"risk": RiskLevel.UNKNOWN.value, "reason": "INVALID_INPUT"},
        ))
        return Decision(
            risk_level=RiskLevel.UNKNOWN,
            system_status=SystemStatus.FAIL,
            reason=DecisionReason.INVALID_INPUT,
            authority=DecisionAuthority.L0_PHYSICAL,
            confidence=0.0,
            driver=Driver.PIPELINE_ERROR,
            ml_execution_mode="SHADOW_ONLY",
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L1
    if perception.max_water_level_ratio >= _WL_DANGER_FLOOR:
        decision_trace.append(_trace(
            DecisionAuthority.L1_SIAGA,
            inputs={"max_water_level_ratio": perception.max_water_level_ratio},
            outputs={"risk": RiskLevel.DANGER.value, "driver": Driver.CRITICAL_HYDROLOGY.value},
        ))
        return Decision(
            risk_level=RiskLevel.DANGER,
            system_status=_resolve_system_status(failures, perception),
            reason=DecisionReason.PHYSICAL_GATE,
            authority=DecisionAuthority.L1_SIAGA,
            confidence=max(reasoning.confidence, 0.85),
            driver=Driver.CRITICAL_HYDROLOGY,
            ml_execution_mode="FULL",
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L1.5
    extreme_count = sum([
        perception.rainfall_1h_mm >= 60,
        perception.max_water_level_ratio >= 0.85,
        perception.bmkg_max_severity >= 0.80,
    ])
    if extreme_count >= 2:
        decision_trace.append(_trace(
            DecisionAuthority.L1_5_MULTI,
            inputs={
                "rainfall_1h_mm": perception.rainfall_1h_mm,
                "max_water_level_ratio": perception.max_water_level_ratio,
                "bmkg_max_severity": perception.bmkg_max_severity,
                "extreme_count": extreme_count,
            },
            outputs={"risk": RiskLevel.DANGER.value, "driver": Driver.COMPOUND_EVENT.value},
        ))
        return Decision(
            risk_level=RiskLevel.DANGER,
            system_status=_resolve_system_status(failures, perception),
            reason=DecisionReason.MULTI_SIGNAL,
            authority=DecisionAuthority.L1_5_MULTI,
            confidence=max(reasoning.confidence, 0.80),
            driver=Driver.COMPOUND_EVENT,
            ml_execution_mode="FULL",
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L1.6
    # Rapid escalation: moderate water level rising fast overrides to DANGER.
    # Safety-critical: a rapidly rising level at SIAGA 3 is operationally as
    # dangerous as an absolute SIAGA 1 breach — delay costs lives.
    if (
        physical is not None
        and physical.rapid_escalation
        and physical.hydrology_max_severity >= _HYDRO_RAPID_SEVERITY
    ):
        decision_trace.append(_trace(
            DecisionAuthority.L1_SIAGA,
            inputs={
                "rapid_escalation": physical.rapid_escalation,
                "hydrology_max_severity": physical.hydrology_max_severity,
                "threshold": _HYDRO_RAPID_SEVERITY,
            },
            outputs={
                "risk": RiskLevel.DANGER.value,
                "driver": Driver.HYDROLOGY_STRESS.value,
                "override": "rapid_escalation_physical_gate",
            },
        ))
        return Decision(
            risk_level=RiskLevel.DANGER,
            system_status=_resolve_system_status(failures, perception),
            reason=DecisionReason.PHYSICAL_GATE,
            authority=DecisionAuthority.L1_SIAGA,
            confidence=max(reasoning.confidence, 0.80),
            driver=Driver.HYDROLOGY_STRESS,
            ml_execution_mode="FULL",
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L1.7
    # BMKG_SAFETY_FLOOR: non-bypassable WARNING floor that pre-empts ML when
    # BMKG reports Severe+Observed+Immediate alongside either (a) high
    # rainfall or (b) an out-of-distribution ML signal with no usable water
    # level. Closes the gap where ML SAFE + stale TMA + BMKG severe would
    # otherwise fall through every downstream layer.
    fired, sub_rule = _check_bmkg_safety_floor(perception, reasoning)
    if fired:
        decision_trace.append(_trace(
            DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR,
            inputs={
                "bmkg_max_severity": perception.bmkg_max_severity,
                "rainfall_1h_mm": perception.rainfall_1h_mm,
                "max_water_level_ratio": perception.max_water_level_ratio,
                "ood_score": reasoning.ood_score,
                "ml_probability": reasoning.probability,
                "sub_rule": sub_rule,
            },
            outputs={
                "risk": RiskLevel.WARNING.value,
                "reason": DecisionReason.SAFETY_FLOOR.value,
                "override": "bmkg_safety_floor",
            },
        ))
        return Decision(
            risk_level=RiskLevel.WARNING,
            system_status=_resolve_system_status(failures, perception),
            reason=DecisionReason.SAFETY_FLOOR,
            authority=DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR,
            confidence=max(reasoning.confidence, _BMKG_SAFETY_FLOOR_CONFIDENCE_FLOOR),
            driver=Driver.BMKG_CONFIRMED_ALERT,
            ml_execution_mode="FULL",
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L3
    base_risk = _ml_classify(reasoning, thresholds)
    decision_trace.append(_trace(
        DecisionAuthority.L3_ML,
        inputs={
            "probability": reasoning.probability,
            "thresholds": {
                "pre_alert": thresholds.pre_alert,
                "warning": thresholds.warning,
                "danger": thresholds.danger,
            },
        },
        outputs={"risk": base_risk.value},
    ))

    # ------------------------------------------------------------------ L2
    severe = [
        f for f in failures
        if f.risk_escalation and f.severity in (FailureSeverity.HIGH, FailureSeverity.CRITICAL)
    ]
    if severe:
        escalated = _escalate_one_level(base_risk)
        decision_trace.append(_trace(
            DecisionAuthority.L2_INTEGRITY,
            inputs={"severe_failures": [f.failure_type for f in severe]},
            outputs={"risk_before": base_risk.value, "risk_after": escalated.value},
        ))
        base_risk = escalated
        authority = DecisionAuthority.L2_INTEGRITY
        reason = DecisionReason.RISK
    else:
        authority = DecisionAuthority.L3_ML
        reason = DecisionReason.RISK

    system_status = _resolve_system_status(failures, perception)
    confidence = _penalize_confidence(reasoning.confidence, failures, perception)
    driver = _select_driver(perception, reasoning)

    decision = Decision(
        risk_level=base_risk,
        system_status=system_status,
        reason=reason,
        authority=authority,
        confidence=confidence,
        driver=driver,
        ml_execution_mode="FULL",
        is_safe_for_automation=(
            not severe
            and system_status == SystemStatus.OK
            and base_risk not in (RiskLevel.DANGER, RiskLevel.WARNING)
        ),
        decision_trace=tuple(decision_trace),
    )

    # ------------------------------------------------------------------ L3.3
    # E9/E12 INCONSISTENCY OVERRIDE: ML returned SAFE but physical evidence
    # (hydrology severity) is high enough that the disagreement itself is a
    # signal. Forces SAFE -> WARNING. Authority recorded as L2_INTEGRITY
    # because this is fundamentally a "system says one thing, physics says
    # another" gate.
    if _check_inconsistency_override(decision.risk_level, physical):
        decision_trace.append(_trace(
            DecisionAuthority.L2_INTEGRITY,
            inputs={
                "ml_risk": decision.risk_level.value,
                "hydrology_max_severity": physical.hydrology_max_severity,
                "plausibility_score": physical.plausibility_score,
            },
            outputs={
                "risk_before": decision.risk_level.value,
                "risk_after": RiskLevel.WARNING.value,
                "override": "inconsistency",
            },
        ))
        decision = decision.with_(
            risk_level=RiskLevel.WARNING,
            reason=DecisionReason.RISK,
            authority=DecisionAuthority.L2_INTEGRITY,
            driver=Driver.HYDROLOGY_STRESS,
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L3.7
    # E3 MULTI-SIGNAL EARLY WARNING: SAFE -> WARNING when rising trend +
    # rainfall accumulation + water-level delta all converge across >=2 prior
    # predictions. Authority recorded as L1_5_MULTI because it's a
    # compound-signal call.
    if _check_early_warning_convergence(decision.risk_level, reasoning, trend):
        decision_trace.append(_trace(
            DecisionAuthority.L1_5_MULTI,
            inputs={
                "ml_risk": decision.risk_level.value,
                "probability": reasoning.probability,
                "trend_strength": trend.trend_strength,
                "trend_confidence": trend.trend_confidence,
                "rainfall_acc_3h": trend.rainfall_acc_3h,
                "water_level_delta_cur": trend.water_level_delta_cur,
                "data_points": trend.data_points,
            },
            outputs={
                "risk_before": decision.risk_level.value,
                "risk_after": RiskLevel.WARNING.value,
                "override": "early_warning_convergence",
            },
        ))
        decision = decision.with_(
            risk_level=RiskLevel.WARNING,
            reason=DecisionReason.MULTI_SIGNAL,
            authority=DecisionAuthority.L1_5_MULTI,
            driver=Driver.COMPOUND_EVENT,
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L1.8
    # HYDRO_FLOOR: post-ML one-way floor based on BNPB/BPBD water-level ratio.
    # Closes the gap where low ML probability + channel near capacity → SAFE.
    # Only escalates — never downgrades ML output.
    if perception.max_water_level_ratio >= _WL_DANGER_FLOOR:
        _hydro_floor: RiskLevel | None = RiskLevel.DANGER
    elif perception.max_water_level_ratio >= _WL_WARNING_FLOOR:
        _hydro_floor = RiskLevel.WARNING
    elif perception.max_water_level_ratio >= _WL_PRE_ALERT_FLOOR:
        _hydro_floor = RiskLevel.PRE_ALERT
    else:
        _hydro_floor = None

    if _hydro_floor is not None and _RISK_RANK[_hydro_floor] > _RISK_RANK[decision.risk_level]:
        decision_trace.append(_trace(
            DecisionAuthority.L1_8_HYDRO_FLOOR,
            inputs={
                "max_water_level_ratio": perception.max_water_level_ratio,
                "floor_applied": _hydro_floor.value,
                "risk_before": decision.risk_level.value,
            },
            outputs={
                "risk_after": _hydro_floor.value,
                "override": "hydro_floor",
            },
        ))
        decision = decision.with_(
            risk_level=_hydro_floor,
            reason=DecisionReason.SAFETY_FLOOR,
            authority=DecisionAuthority.L1_8_HYDRO_FLOOR,
            driver=_select_driver(perception, reasoning),
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    # ------------------------------------------------------------------ L1.9
    # OOD_FLOOR: IsolationForest out-of-distribution score imposes a minimum
    # risk and confidence ceiling. One-way: only escalates, never downgrades.
    # The floor fires regardless of how the ML layer classified the input;
    # the confidence cap fires even when risk is already at/above the floor.
    if reasoning.ood_score < _OOD_SEVERE_SCORE:
        _ood_risk_floor: RiskLevel | None = RiskLevel.WARNING
        _ood_conf_cap: float | None = _OOD_SEVERE_CONF_CAP
    elif reasoning.ood_score < _OOD_MODERATE_SCORE:
        _ood_risk_floor = RiskLevel.PRE_ALERT
        _ood_conf_cap = _OOD_MODERATE_CONF_CAP
    else:
        _ood_risk_floor = None
        _ood_conf_cap = None

    if _ood_risk_floor is not None or _ood_conf_cap is not None:
        _apply_ood_floor = (
            _ood_risk_floor is not None
            and _RISK_RANK[_ood_risk_floor] > _RISK_RANK[decision.risk_level]
        )
        _apply_ood_cap = (
            _ood_conf_cap is not None
            and decision.confidence > _ood_conf_cap
        )
        if _apply_ood_floor or _apply_ood_cap:
            _ood_new_risk = _ood_risk_floor if _apply_ood_floor else decision.risk_level
            _ood_new_conf = (
                min(decision.confidence, _ood_conf_cap)
                if _apply_ood_cap
                else decision.confidence
            )
            decision_trace.append(_trace(
                DecisionAuthority.L1_9_OOD_FLOOR,
                inputs={
                    "ood_score": reasoning.ood_score,
                    "risk_before": decision.risk_level.value,
                    "confidence_before": round(decision.confidence, 4),
                    "floor": _ood_risk_floor.value if _ood_risk_floor else None,
                    "conf_cap": _ood_conf_cap,
                },
                outputs={
                    "risk_after": _ood_new_risk.value,
                    "confidence_after": round(_ood_new_conf, 4),
                    "override": "ood_floor",
                },
            ))
            decision = decision.with_(
                risk_level=_ood_new_risk,
                confidence=_ood_new_conf,
                reason=(
                    DecisionReason.SAFETY_FLOOR
                    if _apply_ood_floor
                    else decision.reason
                ),
                authority=(
                    DecisionAuthority.L1_9_OOD_FLOOR
                    if _apply_ood_floor
                    else decision.authority
                ),
                is_safe_for_automation=(
                    False if _apply_ood_floor else decision.is_safe_for_automation
                ),
                decision_trace=tuple(decision_trace),
            )

    # ------------------------------------------------------------------ L4
    # Trend extension. Two asymmetric (upward-only) paths:
    #   (a) WARNING -> DANGER on sustained upward (existing).
    #   (b) E4: SAFE -> PRE_ALERT on rising trend with sub-WARNING probability.
    if decision.risk_level == RiskLevel.WARNING and trend.sustained_upward():
        decision_trace.append(_trace(
            DecisionAuthority.L4_TREND,
            inputs={"recent_probabilities": list(trend.recent_probabilities)},
            outputs={
                "risk_before": RiskLevel.WARNING.value,
                "risk_after": RiskLevel.DANGER.value,
            },
        ))
        decision = decision.with_(
            risk_level=RiskLevel.DANGER,
            reason=DecisionReason.TREND_EXTENSION,
            authority=DecisionAuthority.L4_TREND,
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )
    elif _check_pre_alert_trend(decision.risk_level, reasoning, trend):
        decision_trace.append(_trace(
            DecisionAuthority.L4_TREND,
            inputs={
                "probability": reasoning.probability,
                "trend_strength": trend.trend_strength,
                "trend_confidence": trend.trend_confidence,
                "risk_trend": trend.risk_trend,
            },
            outputs={
                "risk_before": RiskLevel.SAFE.value,
                "risk_after": RiskLevel.PRE_ALERT.value,
                "override": "pre_alert_trend",
            },
        ))
        decision = decision.with_(
            risk_level=RiskLevel.PRE_ALERT,
            reason=DecisionReason.TREND_EXTENSION,
            authority=DecisionAuthority.L4_TREND,
            is_safe_for_automation=False,
            decision_trace=tuple(decision_trace),
        )

    return decision
