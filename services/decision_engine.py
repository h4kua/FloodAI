"""
Final Decision Engine — unified hierarchical decision authority for the flood pipeline.

Enforces strict priority order at every prediction:
  1. Physical Reality  — HydrologyAssessment SIAGA levels override ML/baseline
  2. System Integrity  — CONFLICT/LOW_TRUST trigger conservative guardrails
  3. ML + Adaptive     — calibration-aware probability × context-adjusted threshold
  4. Trend Signals     — anomalies extend the trace; WARNING + rising trend flags urgency

This is the sole decision authority. All escalation, override, and adjustment logic
terminates here. Upstream agents compute inputs; this engine makes the final call
and traces every step completely.

Public API:
    run_decision_engine(**kwargs) → DecisionResult
    write_calibration_cache(ece, brier, n) → None
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

# PHASE 2 DELEGATION: canonical decision authority lives in app.domain.decide().
# This module is now a THIN ADAPTER that builds typed inputs, calls decide(),
# and maps the canonical Decision back into the legacy DecisionResult shape
# that ActionAgent and tests already consume. The legacy escalation body
# below the adapter is preserved as _legacy_run_decision_engine_unused for
# Phase 3 conformance comparison; it is no longer reachable from production.
from contracts import (
    DecisionAuthority,
    Driver as CanonicalDriver,
    RiskLevel,
    SystemStatus,
)
from domain import (
    AdaptiveThresholds,
    FailureMode as CanonicalFailureMode,
    PerceptionInputs,
    PhysicalSignals,
    ReasoningInputs,
    TrendSnapshot,
    decide as canonical_decide,
)
from contracts.vocabulary import FailureSeverity
from realtime_native.bundle import derive_threshold_triplet

_log = logging.getLogger(__name__)


# ─── Canonical-authority -> legacy decision_source mapping ───────────────────
# Maps DecisionAuthority enum (which L-level fired) to the legacy decision_source
# string that ActionAgent and downstream consumers already understand.
_AUTHORITY_TO_SOURCE = {
    DecisionAuthority.L0_PHYSICAL: "invalid_input_fallback",
    DecisionAuthority.L1_SIAGA:    "physical_override",
    DecisionAuthority.L1_5_MULTI:  "signal_override",
    DecisionAuthority.L1_7_BMKG_SAFETY_FLOOR: "bmkg_safety_floor",
    DecisionAuthority.L1_8_HYDRO_FLOOR: "hydro_floor",
    DecisionAuthority.L1_9_OOD_FLOOR:  "ood_floor",
    DecisionAuthority.L2_INTEGRITY: "system_guardrail",
    DecisionAuthority.L3_ML:       "ml_adaptive",
    DecisionAuthority.L4_TREND:    "trend_informed",
}

_FAILURE_SEVERITY_NORMALIZE = {
    "low": FailureSeverity.LOW,
    "medium": FailureSeverity.MEDIUM,
    "high": FailureSeverity.HIGH,
    "critical": FailureSeverity.CRITICAL,
}

# Phase 7 cleanup: legacy override / inconsistency / ECE-penalty thresholds
# removed. They were referenced only by `_legacy_run_decision_engine_unused`,
# which was deleted in Phase 6. Canonical decision authority
# (app.domain.decision) carries its own thresholds (`_HYDRO_MIN_PLAUSIBILITY`,
# `_INCONSISTENCY_HYDRO_MIN`, etc. at the domain level). The calibration
# penalty remains DEACTIVATED at the adapter level (audit RC-1):
# `_decision_to_legacy_result` always sets `calibration_penalty=0.0` and
# `applied=False` regardless of cached ECE — `_load_cached_ece()` is still
# called for trace-observability ECE diagnostic only.

# ─── Canonical default thresholds (shared with realtime inference) ──────────


def _canonical_default_thresholds() -> tuple[float, float, float]:
    """
    Return (pre_alert, warning, danger) — single threshold source of truth.

    Reads the realtime-native threshold file when present so /predict/realtime-native
    and /predict/agentic classify identical probabilities into identical risk_levels.
    Lazy-imported to avoid module-load cost when callers pass explicit thresholds.
    """
    try:
        from realtime_native.inference import _load_thresholds  # local import
        t = _load_thresholds()
        pre_alert = float(t["pre_alert"])
        warning = float(t["warning"])
        danger = float(t["danger"])
    except Exception:  # noqa: BLE001
        normalized = derive_threshold_triplet(danger=0.22)
        pre_alert = normalized["pre_alert"]
        warning = normalized["warning"]
        danger = normalized["danger"]
    return pre_alert, warning, danger


# ─── Calibration cache path ──────────────────────────────────────────────────
_CALIBRATION_CACHE = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "artifacts", "configurations", "calibration_cache.json",
    )
)
_CALIBRATION_CACHE_MAX_AGE_DAYS = 30


def _calibration_mtime() -> float:
    return os.path.getmtime(_CALIBRATION_CACHE) if os.path.exists(_CALIBRATION_CACHE) else 0.0


@lru_cache(maxsize=1)
def _load_cached_ece_for_mtime(cache_mtime: float) -> float:
    """
    Read last-computed ECE from cache file; returns 0.0 if absent or unreadable.

    Warns (once per process) if:
      - Cache file is missing — ECE=0.0 assumed, calibration penalty is inactive.
      - Cache is older than _CALIBRATION_CACHE_MAX_AGE_DAYS — may reflect a
        previous model version. Re-run app/evaluation/calibration.py to refresh.
    Written by app/evaluation/calibration.py (offline tool).
    """
    if not os.path.exists(_CALIBRATION_CACHE):
        _log.warning(
            "calibration_cache.json not found at %s — ECE=0.0 assumed, "
            "no calibration penalty applied. "
            "Run app/evaluation/calibration.py to generate it.",
            _CALIBRATION_CACHE,
        )
        return 0.0
    try:
        with open(_CALIBRATION_CACHE, encoding="utf-8") as fh:
            data = json.load(fh)
        written_at = data.get("written_at")
        if written_at:
            try:
                age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(written_at)).days
                if age_days > _CALIBRATION_CACHE_MAX_AGE_DAYS:
                    _log.warning(
                        "calibration_cache.json is %d days old (model_version=%r) — "
                        "confidence penalties may reflect a stale model. "
                        "Re-run app/evaluation/calibration.py.",
                        age_days,
                        data.get("model_version", "unknown"),
                    )
            except (ValueError, TypeError):
                pass
        ece = float(data.get("ece", 0.0))
        return ece if 0.0 <= ece <= 1.0 else 0.0
    except (OSError, ValueError, KeyError):
        pass
    return 0.0


def _load_cached_ece() -> float:
    return _load_cached_ece_for_mtime(_calibration_mtime())


# ─── Output dataclass ────────────────────────────────────────────────────────

@dataclass
class DecisionResult:
    """
    Authoritative output of the final decision engine.
    Stored on EvaluationResult.decision and serialised by ActionAgent.
    """
    risk_level: str
    confidence_score: float
    # Which hierarchy layer made the final call:
    #   "physical_override" | "system_guardrail" | "ml_adaptive" | "trend_informed"
    decision_source: str
    decision_trace: list[str] = field(default_factory=list)
    decision_trace_struct: list[dict] = field(default_factory=list)
    decision_summary: str = ""
    # One-sentence human-readable explanation based on strongest active signal (Task 10).
    final_reason: str = ""
    override_trace: dict = field(default_factory=dict)
    inconsistency_check: dict = field(default_factory=dict)
    confidence_adjustment: dict = field(default_factory=dict)
    adaptive_threshold: dict = field(default_factory=dict)
    hydrology_narrative: str = ""
    scenario_comparison: dict = field(default_factory=dict)
    # Phase 5 addition: canonical SystemStatus value computed by app.domain.decide().
    # Empty default preserves backward compatibility for callers that construct
    # DecisionResult directly without providing this field. The adapter
    # populates this from canonical Decision.system_status.value so consumers
    # (EvaluationAgent, ActionAgent) can detect divergence between
    # agent-computed and canonical-computed system_status.
    system_status: str = ""


# ─── Public entry point — CANONICAL ADAPTER ──────────────────────────────────
# Phase 2 delegation: this function is now a thin adapter that builds typed
# inputs from the legacy keyword arguments, calls app.domain.decide() as the
# SOLE decision authority, and maps the canonical Decision back into the
# legacy DecisionResult shape that ActionAgent and existing tests consume.
#
# The original 565-LOC escalation body is preserved below as
# _legacy_run_decision_engine_unused for Phase 3 conformance comparison.
# It is no longer reachable from production callers.


def run_decision_engine(
    *,
    evaluation_risk_level: str,
    adjusted_confidence: float,
    system_status: str,
    probability: float,
    raw_model_confidence: float,
    failure_modes: list[dict],
    baseline_result: dict,
    signals: dict,
    diagnostics: dict,
    hydrology_assessment,           # HydrologyAssessment | None (avoids circular import)
    plausibility_score: float = 1.0,
    has_critical_violation: bool = False,
    trust_breakdown=None,           # TrustBreakdown | None
    adaptive_classification: dict | None = None,
    calibration_ece: float | None = None,
    perception_completeness: float = 1.0,
    data_freshness_minutes: float = 0.0,
    elevation_data: dict | None = None,
) -> DecisionResult:
    """
    Adapter around app.domain.decide() — the canonical decision authority.

    Builds typed inputs from the legacy keyword arguments, calls decide(),
    and maps the returned Decision into the legacy DecisionResult shape.
    Never raises — exception path returns failsafe_decision() (conservative
    fallback preserving DecisionResult shape).

    Decision authority hierarchy (now lives entirely in app.domain.decide()):
      L0  PHYSICAL  — invalid input or critical violation -> UNKNOWN/FAIL
      L1  SIAGA     — water_level_ratio >= 0.95 -> DANGER (CRITICAL_HYDROLOGY)
      L1.5 MULTI    — multi-signal compound -> DANGER (COMPOUND_EVENT)
      L2  INTEGRITY — severe failures escalate one level OR
                       inconsistency override (E9/E12)
      L3  ML        — calibrated probability vs adaptive thresholds
      L3.7 NEW      — multi-signal early WARNING (E3)
      L4  TREND     — sustained -> DANGER OR rising-trend SAFE -> PRE_ALERT (E4)
    """
    try:
        kwargs_snapshot = dict(
            evaluation_risk_level=evaluation_risk_level,
            adjusted_confidence=adjusted_confidence,
            system_status=system_status,
            probability=probability,
            raw_model_confidence=raw_model_confidence,
            failure_modes=failure_modes or [],
            baseline_result=baseline_result or {},
            signals=signals or {},
            diagnostics=diagnostics or {},
            hydrology_assessment=hydrology_assessment,
            plausibility_score=plausibility_score,
            has_critical_violation=has_critical_violation,
            trust_breakdown=trust_breakdown,
            adaptive_classification=adaptive_classification,
            calibration_ece=calibration_ece,
            perception_completeness=perception_completeness,
            data_freshness_minutes=data_freshness_minutes,
            elevation_data=elevation_data or {},
        )

        canonical_inputs = _build_canonical_inputs(kwargs_snapshot)
        decision = canonical_decide(**canonical_inputs)
        result = _decision_to_legacy_result(decision, kwargs_snapshot)

        # OOD confidence dampening — applied unconditionally after canonical_decide()
        # because L1/L1.5/L1.7 do early returns that skip L1.9 OOD cap.
        # Formula: confidence * (1 + ood_score); ood_score negative → reduces confidence.
        _ood_score = canonical_inputs["reasoning"].ood_score
        if _ood_score < -0.05 and result.confidence_score > 0.0:
            _cap = 0.55 if _ood_score < -0.10 else 0.70
            _pre_damp = result.confidence_score
            _dampened = round(min(_pre_damp * (1.0 + _ood_score), _cap), 4)
            result.confidence_score = max(0.05, _dampened)
            result.decision_trace.append(
                f"[OOD-DAMP] confidence {_pre_damp:.2f} → {result.confidence_score:.2f} "
                f"(ood_score={_ood_score:.3f}, cap={_cap})"
            )
        adjusted_risk, threshold_delta, reason = _apply_elevation_adjustment(
            result.risk_level,
            kwargs_snapshot.get("elevation_data") or {},
        )
        if reason:
            if adjusted_risk != result.risk_level:
                result.decision_trace.append(
                    f"[ELEVATION] risk {result.risk_level} -> {adjusted_risk}: {reason}"
                )
                result.decision_summary = (
                    f"{result.decision_summary} Elevation-adjusted final risk={adjusted_risk}."
                    if result.decision_summary else f"Elevation-adjusted final risk={adjusted_risk}."
                )
                result.risk_level = adjusted_risk
            else:
                result.decision_trace.append(
                    f"[ELEVATION] threshold_delta={threshold_delta:+.3f}: {reason}"
                )
            result.adaptive_threshold["elevation_adjustment"] = {
                "risk_level": adjusted_risk,
                "threshold_delta": threshold_delta,
                "reason": reason,
            }
            result.final_reason = (
                f"{result.final_reason} | Elevation adjustment: {reason}"
                if result.final_reason else f"Elevation adjustment: {reason}"
            )
        return result
    except Exception as exc:  # noqa: BLE001
        _log.error(
            "run_decision_engine adapter failed: %s: %s — returning failsafe",
            type(exc).__name__,
            exc,
        )
        return failsafe_decision(
            evaluation_risk_level=evaluation_risk_level,
            adjusted_confidence=adjusted_confidence,
            error_message=f"adapter_exception: {type(exc).__name__}: {exc}",
        )


# ─── Adapter helpers ──────────────────────────────────────────────────────────


def _build_canonical_inputs(kw: dict) -> dict:
    """
    Translate the legacy keyword arguments into the typed inputs that
    app.domain.decide() consumes. Conservative on missing fields: defaults
    favor SAFE risk and let the canonical L0/L2 layers escalate when warranted.
    """
    signals = kw.get("signals") or {}
    diagnostics = kw.get("diagnostics") or {}
    trend_state = diagnostics.get("trend_state") or {}
    ac = kw.get("adaptive_classification") or {}
    hydro = kw.get("hydrology_assessment")

    hydro_severity = float(getattr(hydro, "severity_score", 0.0) or 0.0) if hydro else 0.0
    rapid_escalation = bool(getattr(hydro, "rapid_escalation", False)) if hydro else False

    # Real per-station max water-level ratio (cm / SIAGA1_cm). Distinct scale
    # from the aggregate severity_score — L1 SIAGA / L1.5 thresholds operate on
    # this physical ratio, NOT on the normalised severity score.
    station_ratio = 0.0
    if hydro is not None:
        stations = getattr(hydro, "stations", None) or []
        if stations:
            station_ratio = max(
                (float(getattr(s, "water_level_ratio", 0.0) or 0.0) for s in stations),
                default=0.0,
            )
        else:
            station_ratio = max(0.0, min(1.0, hydro_severity))

    plausibility_score = kw.get("plausibility_score", 1.0)
    if isinstance(plausibility_score, dict):
        plausibility_score = float(plausibility_score.get("plausibility_score", 1.0))
    plausibility_score = float(plausibility_score)
    has_critical_violation = bool(kw.get("has_critical_violation", False))

    physical = PhysicalSignals(
        hydrology_max_severity=max(0.0, min(1.0, hydro_severity)),
        rapid_escalation=rapid_escalation,
        plausibility_score=max(0.0, min(1.0, plausibility_score)),
        has_critical_violation=has_critical_violation,
    )

    # Real completeness/freshness from PerceptionAgent — L0 invalid-input gate
    # (completeness < 0.30) and L2 DEGRADED escalation (freshness > 60 or
    # completeness < 0.50) rely on these values, not the upstream hardcoded 1.0/0.0.
    raw_completeness = kw.get("perception_completeness", 1.0)
    try:
        completeness = max(0.0, min(1.0, float(raw_completeness)))
    except (TypeError, ValueError):
        completeness = 1.0
    raw_freshness = kw.get("data_freshness_minutes", 0.0)
    try:
        freshness_min = float(raw_freshness)
    except (TypeError, ValueError):
        freshness_min = -1.0  # unknown sentinel preserved

    # Signals dict uses underscore-prefixed scalars (see decision_logic.extract_signals).
    # Reading the non-prefixed keys previously zeroed rainfall_1h_mm and bmkg_max_severity
    # in every call, making L1.5 COMPOUND_EVENT and rainfall/BMKG drivers unreachable.
    rainfall_1h_mm = float(
        signals.get("_rainfall_mm")
        if signals.get("_rainfall_mm") is not None
        else signals.get("rainfall_mm") or 0.0
    )
    # Source the L1.5/L1.7 BMKG scalar from RAW max severity (0.8 for "Severe",
    # 1.0 for "Extreme") — not the multiplicative weighted score, which
    # collapses any Severe alert without Observed+Immediate metadata to a
    # sub-0.80 value and silently disables the L1.7 BMKG_SAFETY_FLOOR.
    # Fallback chain preserves backward compatibility:
    #   1. _bmkg_severity        (extract_signals scalar — preferred)
    #   2. bmkg_severity_score   (raw features key — bypass path)
    #   3. _bmkg_weighted        (legacy product — last-resort)
    #   4. bmkg_severity         (legacy fallback name)
    _bmkg_sev_raw = signals.get("_bmkg_severity")
    if _bmkg_sev_raw is None:
        _bmkg_sev_raw = signals.get("bmkg_severity_score")
    if _bmkg_sev_raw is None:
        _bmkg_sev_raw = signals.get("_bmkg_weighted")
    if _bmkg_sev_raw is None:
        _bmkg_sev_raw = signals.get("bmkg_severity") or 0.0
    bmkg_max_severity = float(_bmkg_sev_raw)

    perception = PerceptionInputs(
        physically_plausible=not has_critical_violation,
        completeness=completeness,
        freshness_min=freshness_min,
        max_water_level_ratio=max(0.0, station_ratio),
        rainfall_1h_mm=rainfall_1h_mm,
        bmkg_max_severity=max(0.0, min(1.0, bmkg_max_severity)),
    )

    # Extract OOD score from failure_modes (IsolationForest decision_function;
    # negative = out-of-distribution). Required by L1.7 sub-rule (b)
    # "bmkg_severe_ood_stale_tma" — without this, reasoning.ood_score stays at
    # its 0.0 default and that sub-rule can never fire.
    ood_score_value = 0.0
    for f in kw.get("failure_modes") or []:
        if isinstance(f, dict) and f.get("type") == "ood_input":
            detail = f.get("detail") or {}
            try:
                ood_score_value = float(detail.get("ood_score", 0.0))
            except (TypeError, ValueError):
                ood_score_value = 0.0
            break
    if ood_score_value == 0.0:
        diag_ood = (kw.get("diagnostics") or {}).get("ood_detection") or {}
        try:
            ood_score_value = float(diag_ood.get("score", 0.0))
        except (TypeError, ValueError):
            ood_score_value = 0.0

    reasoning = ReasoningInputs(
        probability=float(kw.get("probability") or 0.0),
        confidence=float(kw.get("adjusted_confidence") or 0.0),
        model_variant="realtime_native",
        ood_score=ood_score_value,
    )

    failures: list[CanonicalFailureMode] = []
    for f in kw.get("failure_modes") or []:
        if not isinstance(f, dict):
            continue
        sev_raw = str(f.get("severity") or "low").lower()
        sev = _FAILURE_SEVERITY_NORMALIZE.get(sev_raw, FailureSeverity.LOW)
        failures.append(
            CanonicalFailureMode(
                failure_type=str(f.get("type") or "unknown"),
                severity=sev,
                risk_escalation=bool(f.get("risk_escalation", False)),
                confidence_penalty=float(f.get("confidence_penalty") or 0.0),
            )
        )

    trend = TrendSnapshot(
        recent_probabilities=tuple(trend_state.get("recent_probabilities") or ()),
        risk_trend=str(trend_state.get("risk_trend") or ""),
        trend_strength=float(trend_state.get("trend_strength") or 0.0),
        trend_confidence=float(trend_state.get("trend_confidence") or 0.0),
        rainfall_acc_3h=float(trend_state.get("rainfall_acc_3h") or 0.0),
        water_level_delta_cur=float(trend_state.get("water_level_delta_cur") or 0.0),
        data_points=int(trend_state.get("data_points") or 0),
    )

    # Threshold source unification: when adaptive_classification is absent
    # (failsafe path, plausibility bypass, etc.), fall back to the SAME triplet
    # the realtime inference layer uses. Prevents /predict/realtime-native and
    # /predict/agentic from disagreeing on borderline probabilities.
    _canon_pre, _canon_warn, _canon_danger = _canonical_default_thresholds()

    normalized_thresholds = derive_threshold_triplet(
        danger=float(
            ac.get("danger_threshold")
            or ac.get("effective_danger_threshold")
            or _canon_danger
        ),
        warning=_optional_float(ac.get("warning_threshold")) if ac else _canon_warn,
        pre_alert=_optional_float(ac.get("pre_alert_threshold")) if ac else _canon_pre,
    )
    thresholds = AdaptiveThresholds(
        pre_alert=normalized_thresholds["pre_alert"],
        warning=normalized_thresholds["warning"],
        danger=normalized_thresholds["danger"],
    )

    return {
        "perception": perception,
        "reasoning": reasoning,
        "failures": failures,
        "trend": trend,
        "thresholds": thresholds,
        "physical": physical,
    }


def _decision_to_legacy_result(decision, kw: dict) -> "DecisionResult":
    """
    Map a canonical Decision into the legacy DecisionResult shape that
    ActionAgent and tests already consume.

    Canonical passthrough (Phase G): risk_level from decide() is passed through
    unchanged. The Inv-6 UNKNOWN → WARNING rewrite has been removed — L0 UNKNOWN
    now reaches callers directly. All downstream consumers handle UNKNOWN via
    their existing default branches. system_status=FAIL is the authoritative
    invalid-input indicator.
    """
    decision_source = _AUTHORITY_TO_SOURCE.get(decision.authority, "ml_adaptive")
    risk_for_result = decision.risk_level

    # Convert canonical decision_trace (tuple[dict]) into legacy list[str]
    trace_strings: list[str] = []
    for entry in decision.decision_trace:
        layer = entry.get("layer", "?")
        outputs = entry.get("outputs", {})
        risk_after = outputs.get("risk_after") or outputs.get("risk") or ""
        override = outputs.get("override")
        marker = f"[{layer}]"
        if override:
            marker += f" override={override}"
        if risk_after:
            marker += f" -> {risk_after}"
        trace_strings.append(marker)

    # override_trace: assemble from any L1/L1.5/L2 canonical entries.
    physical_layers = {"L1_SIAGA", "L1_5_MULTI", "L2_INTEGRITY"}
    override_entries = [
        t for t in decision.decision_trace if t.get("layer") in physical_layers
    ]
    physical_override = bool(override_entries)
    last_override = override_entries[-1] if override_entries else None
    override_reason = ""
    if last_override:
        outputs = last_override.get("outputs", {})
        override_reason = outputs.get("override") or outputs.get("driver") or ""

    physical = kw.get("hydrology_assessment")
    hydro_severity = (
        float(getattr(physical, "max_severity", 0.0) or 0.0) if physical else 0.0
    )
    hydro_dominant = (
        str(getattr(physical, "dominant_station", "") or "") if physical else ""
    )
    hydro_siaga = (
        str(getattr(physical, "dominant_siaga", "") or "") if physical else ""
    )

    # ECE logging (deactivated per RC-1 — penalty is always 0.0)
    cached_ece = kw.get("calibration_ece")
    if cached_ece is None:
        cached_ece = _load_cached_ece()
    cached_ece = float(cached_ece or 0.0)

    trace_struct = [
        {
            "step": idx + 1,
            "agent": "decision_engine",
            "event": str(entry.get("layer", "")),
            "outcome": entry.get("outputs", {}).get("risk_after")
            or entry.get("outputs", {}).get("risk")
            or "",
            "confidence": round(decision.confidence, 4),
            "data": dict(entry),
        }
        for idx, entry in enumerate(decision.decision_trace)
    ]

    return DecisionResult(
        risk_level=risk_for_result.value,
        confidence_score=round(decision.confidence, 4),
        # Phase 5: canonical SystemStatus surfaced so callers can compare
        # against the agent's independently-computed system_status.
        system_status=decision.system_status.value,
        decision_source=decision_source,
        decision_trace=trace_strings,
        decision_trace_struct=trace_struct,
        decision_summary=(
            f"{risk_for_result.value} via {decision_source} "
            f"(authority={decision.authority.value}, "
            f"driver={decision.driver.value}, "
            f"confidence={decision.confidence:.2f})"
        ),
        final_reason=(
            f"{risk_for_result.value} — {decision.reason.value} "
            f"(authority={decision.authority.value})"
        ),
        override_trace={
            "triggered": physical_override,
            "reason": override_reason,
            "confidence": decision.confidence if physical_override else "n/a",
            "hydrology_severity": round(hydro_severity, 4),
            "dominant_station": hydro_dominant,
            "dominant_siaga": hydro_siaga,
            "authority": decision.authority.value,
        },
        inconsistency_check={
            "detected": (
                decision.authority == DecisionAuthority.L2_INTEGRITY
                and last_override is not None
                and last_override.get("outputs", {}).get("override") == "inconsistency"
            ),
            "reason": (
                "ML SAFE contradicted by physical hydrology evidence"
                if decision.authority == DecisionAuthority.L2_INTEGRITY
                and last_override is not None
                and last_override.get("outputs", {}).get("override") == "inconsistency"
                else ""
            ),
        },
        confidence_adjustment={
            "calibration_penalty": 0.0,                # RC-1 deactivated
            "calibration_ece": round(cached_ece, 4),
            "applied": False,                          # RC-1 deactivated
            "reason": "calibration penalty deactivated (RC-1)",
            "final_confidence": round(decision.confidence, 4),
        },
        adaptive_threshold=_format_adaptive_threshold(kw.get("adaptive_classification")),
        hydrology_narrative="",                        # legacy narrative deferred
        scenario_comparison={},                         # cosmetic metric removed
    )


# ─── Private helpers ──────────────────────────────────────────────────────────

def _build_decision_summary(
    risk_level: str,
    decision_source: str,
    confidence: float,
    system_status: str,
    hydro_dominant: str,
    hydro_siaga: str,
) -> str:
    if decision_source == "physical_override":
        label = (
            f"{hydro_dominant} ({hydro_siaga.upper()})"
            if hydro_dominant
            else "monitoring station"
        )
        return (
            f"Physical flood conditions at {label} override the ML model — "
            "immediate protective action is required regardless of computational confidence."
        )
    if decision_source == "system_guardrail":
        return (
            f"System integrity is {system_status.lower().replace('_', '-')} — "
            f"risk conservatively classified as {risk_level} "
            "pending independent manual verification."
        )
    if risk_level == "DANGER":
        return (
            f"Multiple independent hazard signals converge on flood danger "
            f"({confidence:.0%} confidence) — immediate protective action required."
        )
    if risk_level == "WARNING":
        return (
            f"Elevated flood risk conditions detected ({confidence:.0%} confidence) — "
            "increase monitoring cadence and activate contingency preparations."
        )
    return (
        f"No active flood threat detected across all monitored channels "
        f"({confidence:.0%} confidence) — routine monitoring is appropriate."
    )


def _format_adaptive_threshold(adaptive_cls: dict | None) -> dict:
    _pre, _warn, _dng = _canonical_default_thresholds()
    if not adaptive_cls:
        return {
            "pre_alert_threshold": _pre,
            "warning_threshold": _warn,
            "danger_threshold": _dng,
            "base_threshold": _dng,
            "net_adjustment": 0.0,
            "adjustment_factors": [],
            "threshold_basis": (
                "Default static thresholds - no context adjustments applied. "
                "Final risk classification is delegated to app.domain.decision.decide()."
            ),
            "classification_basis": "Default static threshold — no context signals available",
        }
    normalized = derive_threshold_triplet(
        danger=float(
            adaptive_cls.get("danger_threshold")
            or adaptive_cls.get("effective_danger_threshold")
            or _dng
        ),
        warning=_optional_float(adaptive_cls.get("warning_threshold")),
        pre_alert=_optional_float(adaptive_cls.get("pre_alert_threshold")),
    )
    threshold_basis = adaptive_cls.get("threshold_basis") or adaptive_cls.get("classification_basis", "")
    return {
        "pre_alert_threshold": normalized["pre_alert"],
        "warning_threshold": normalized["warning"],
        "danger_threshold": normalized["danger"],
        "base_threshold": adaptive_cls.get("base_danger_threshold", _dng),
        "net_adjustment": float(adaptive_cls.get("net_adjustment", 0.0)),
        "adjustment_factors": [
            a.get("reason", "") for a in adaptive_cls.get("adjustments", [])
        ],
        "threshold_basis": threshold_basis,
        "calibration_version": adaptive_cls.get("calibration_version", ""),
        "calibration_source": adaptive_cls.get("calibration_source", ""),
        "classification_basis": adaptive_cls.get("classification_basis", ""),
    }


def _build_hydrology_narrative(
    overall_explanation: str,
    stations: list,
    trend_state: dict,
) -> str:
    if not overall_explanation:
        return (
            "Hydrology data unavailable — physical conditions "
            "cannot be independently assessed."
        )
    parts = [overall_explanation]

    wl_trend = trend_state.get("water_level_trend", "stable")
    if wl_trend == "rising":
        parts.append("Water levels are trending upward across recent observations.")
    elif wl_trend == "falling":
        parts.append(
            "Water levels are declining, suggesting improving hydrological conditions."
        )

    near_stations = [s for s in stations if getattr(s, "near_threshold", False)]
    if near_stations:
        names = ", ".join(
            getattr(s, "station_name", "unknown") for s in near_stations[:2]
        )
        parts.append(
            f"Alert: {names} approaching next alert threshold — "
            "escalation possible within the current prediction window."
        )

    return " ".join(parts)


def _optional_float(value: object) -> float | None:
    if value in ("", None):
        return None
    return float(value)


def _apply_elevation_adjustment(base_risk: str, elevation_data: dict) -> tuple[str, float, str]:
    """
    Apply conservative, additive elevation rules.

    Returns:
      (adjusted_risk, threshold_delta, reason)

    ``threshold_delta`` is informational here: positive values mean "be more
    sensitive to escalation", negative values mean "slight relaxation". Risk
    is never downgraded, and WARNING/DANGER are never reduced.
    """
    if not isinstance(elevation_data, dict) or not elevation_data:
        return base_risk, 0.0, ""

    elevation_m = elevation_data.get("elevation_m")
    try:
        elevation_m = float(elevation_m) if elevation_m is not None else None
    except (TypeError, ValueError):
        elevation_m = None

    rainfall_1h = _coerce_non_negative_float(elevation_data.get("rainfall_1h_mm"))
    rainfall_3h = _coerce_non_negative_float(elevation_data.get("rainfall_3h_mm"))
    water_level_delta = _coerce_non_negative_float(elevation_data.get("water_level_delta"))
    is_local_depression = bool(elevation_data.get("is_local_depression", False))

    threshold_delta = 0.0
    reasons: list[str] = []
    adjusted_risk = base_risk

    has_any_rainfall = rainfall_1h > 0.0 or rainfall_3h > 0.0
    heavy_rainfall = rainfall_1h >= 20.0 or rainfall_3h >= 60.0
    rising_water = water_level_delta > 0.0

    if elevation_m is not None and elevation_m < 0.0 and has_any_rainfall and base_risk == "SAFE":
        adjusted_risk = "PRE_ALERT"
        reasons.append("below sea level with active rainfall")

    if elevation_m is not None and 0.0 <= elevation_m <= 2.0 and heavy_rainfall:
        adjusted_risk = _escalate_risk_level(adjusted_risk)
        reasons.append("0-2 m elevation under heavy rainfall")

    if is_local_depression and rising_water:
        threshold_delta += 0.05
        reasons.append("local depression with rising water")

    if elevation_m is not None and elevation_m > 10.0:
        threshold_delta -= 0.01
        reasons.append("elevation above 10 m")

    if base_risk in ("WARNING", "DANGER") and _risk_rank(adjusted_risk) < _risk_rank(base_risk):
        adjusted_risk = base_risk

    return adjusted_risk, round(threshold_delta, 4), "; ".join(reasons)


def _coerce_non_negative_float(value: object) -> float:
    try:
        coerced = float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, coerced)


def _risk_rank(risk_level: str) -> int:
    return {
        "UNKNOWN": 0,
        "SAFE": 1,
        "PRE_ALERT": 2,
        "WARNING": 3,
        "DANGER": 4,
    }.get(str(risk_level or "").upper(), 0)


def _escalate_risk_level(risk_level: str) -> str:
    normalized = str(risk_level or "").upper()
    if normalized == "SAFE":
        return "PRE_ALERT"
    if normalized == "PRE_ALERT":
        return "WARNING"
    if normalized == "WARNING":
        return "DANGER"
    return "DANGER" if normalized == "DANGER" else risk_level


def _build_scenario_comparison(
    final_confidence: float,
    raw_model_confidence: float,
    baseline_result: dict,
) -> dict:
    """
    Quantify what each pipeline layer contributes versus simpler baselines.

    agentic_system_score : full pipeline after all adjustments
    model_only_score     : raw ML confidence before agentic penalties
    baseline_only_score  : rule-based estimate credibility (1 − disagreement)
    """
    baseline_disagreement = float(baseline_result.get("baseline_disagreement") or 0.0)
    baseline_score        = round(max(0.0, 1.0 - min(baseline_disagreement, 1.0)), 4)
    improvement           = round(final_confidence - raw_model_confidence, 4)

    return {
        "agentic_system_score": round(final_confidence, 4),
        "model_only_score": round(raw_model_confidence, 4),
        "baseline_only_score": baseline_score,
        "agentic_improvement_over_model": improvement,
        "interpretation": (
            "agentic_system_score reflects all pipeline adjustments "
            "(failure penalties, calibration, trust); "
            "model_only_score is raw ML confidence before agentic layers; "
            "baseline_only_score is rule-based estimate agreement (1 − disagreement)."
        ),
    }


def _build_final_reason(
    *,
    risk_level: str,
    decision_source: str,
    hydro_dominant: str,
    hydro_siaga: str,
    hydro_severity: float,
    system_status: str,
    risk_trend: str,
    anomaly_type,
    inconsistency_detected: bool,
    calibration_applied: bool,
    calibration_ece: float,
) -> str:
    """
    One-sentence human-readable reason based on the single strongest active signal.

    Priority: physical override > inconsistency > system guardrail >
              anomaly > trend > calibration > normal assessment.
    """
    if decision_source == "physical_override":
        label = f"{hydro_dominant} ({hydro_siaga.upper()})" if hydro_dominant else "a monitoring station"
        return (
            f"Physical water-level measurements at {label} "
            f"(severity {hydro_severity:.2f}) override the ML model and mandate DANGER classification."
        )
    if inconsistency_detected:
        return (
            "Inconsistency detected: the ML model predicts SAFE but physical and trend signals "
            "show active hazard — treat as WARNING until manually verified."
        )
    if decision_source == "system_guardrail":
        return (
            f"System integrity is {system_status.lower().replace('_', '-')} — "
            "risk classification is conservative until independent verification is complete."
        )
    if anomaly_type == "spike":
        return (
            "A sudden probability spike was detected, consistent with a flash flood or dam release — "
            f"current {risk_level} classification reflects this short-window hazard."
        )
    if anomaly_type == "monotone_increase":
        return (
            "A sustained probability increase indicates slow flood accumulation — "
            f"{risk_level} classification maintained with heightened monitoring cadence."
        )
    if risk_trend == "increasing" and risk_level == "WARNING":
        return (
            "Risk probability is actively increasing — WARNING issued with pre-emptive escalation "
            "readiness advised before conditions reach DANGER threshold."
        )
    if calibration_applied:
        return (
            f"Model confidence reduced by calibration penalty (ECE={calibration_ece:.3f}) — "
            f"final {risk_level} assessment reflects adjusted, more conservative confidence."
        )
    if risk_level == "DANGER":
        return "Multiple hazard signals converge on flood danger — immediate protective action required."
    if risk_level == "WARNING":
        return "Elevated flood risk detected — increase monitoring and activate contingency preparations."
    return "All monitored signals are within normal range — no active flood threat detected."


def failsafe_decision(
    evaluation_risk_level: str = "WARNING",
    adjusted_confidence: float = 0.5,
    error_message: str = "",
) -> DecisionResult:
    """
    Return a conservative DecisionResult when run_decision_engine() raises unexpectedly.

    Never called in healthy operation — exists purely as a crash-safety net.
    """
    reason = "Decision engine failsafe activated"
    if error_message:
        reason = f"{reason}: {error_message}"
    # SAFE is never acceptable on the failsafe path — the engine may have crashed
    # mid-escalation, so the pre-crash risk could be lower than the true answer.
    # DANGER is preserved (already the highest level). WARNING and SAFE both become WARNING.
    _failsafe_risk = "DANGER" if evaluation_risk_level == "DANGER" else "WARNING"
    _failsafe_conf = round(min(float(adjusted_confidence), 0.5), 4)
    return DecisionResult(
        risk_level=_failsafe_risk,
        confidence_score=_failsafe_conf,
        # Failsafe path is by definition degraded — never leak an empty status
        # downstream. Empty would let EvaluationAgent retain its agent-computed
        # status (possibly OK), masking the engine failure.
        system_status="DEGRADED",
        decision_source="system_guardrail",
        decision_trace=[f"[FAILSAFE] {reason}"],
        decision_trace_struct=[{
            "step": 1,
            "agent": "decision_engine",
            "event": "failsafe",
            "outcome": _failsafe_risk,
            "confidence": _failsafe_conf,
            "data": {"reason": reason},
        }],
        decision_summary=(
            "Decision engine encountered an internal error — "
            "conservative risk classification applied. Manual review required."
        ),
        final_reason=reason,
        override_trace={"triggered": False, "reason": reason, "confidence": "n/a"},
        inconsistency_check={"detected": False, "reason": ""},
        # Schema-aligned with healthy-path _decision_to_legacy_result so
        # consumers keying on `calibration_penalty` / `calibration_ece` /
        # `final_confidence` do not KeyError on the failsafe path.
        confidence_adjustment={
            "calibration_penalty": 0.0,
            "calibration_ece": 0.0,
            "applied": False,
            "reason": reason,
            "final_confidence": _failsafe_conf,
        },
        adaptive_threshold=_format_adaptive_threshold(None),
        hydrology_narrative="",
        scenario_comparison={},
    )


# ─── Shadow threshold evaluation (DATA-2) ────────────────────────────────────

_SHADOW_WARNING_THRESHOLD: float = 0.12
_SHADOW_DANGER_THRESHOLD: float = 0.22
_SHADOW_PROFILE_NAME: str = "conservative"

# Production baselines used only for computing threshold_delta in the log.
_PROD_WARNING_THRESHOLD: float = 0.26
_PROD_DANGER_THRESHOLD: float = 0.36


def compute_shadow_evaluation(
    probability: float,
    *,
    production_risk_level: str,
    evaluated_at: str | None = None,
) -> dict:
    """
    Compute shadow threshold evaluation using conservative thresholds.

    Pure function — never reads or modifies any production decision field.
    Returns a dict for inclusion in the pipeline output payload under
    "shadow_evaluation". Pass evaluated_at for deterministic replay; when
    omitted, the current UTC time is used.
    """
    p = float(probability)
    shadow_danger = p >= _SHADOW_DANGER_THRESHOLD
    shadow_warning = p >= _SHADOW_WARNING_THRESHOLD

    if shadow_danger:
        shadow_risk = "DANGER"
    elif shadow_warning:
        shadow_risk = "WARNING"
    else:
        shadow_risk = "SAFE"

    ts = evaluated_at or datetime.now(timezone.utc).isoformat()
    delta_warning = round(_PROD_WARNING_THRESHOLD - _SHADOW_WARNING_THRESHOLD, 4)
    delta_danger = round(_PROD_DANGER_THRESHOLD - _SHADOW_DANGER_THRESHOLD, 4)

    _log.info(
        "shadow_eval current_decision=%s shadow_decision=%s probability=%.4f "
        "threshold_delta_warning=%.4f threshold_delta_danger=%.4f",
        production_risk_level,
        shadow_risk,
        p,
        delta_warning,
        delta_danger,
    )

    return {
        "shadow_warning_triggered": shadow_warning,
        "shadow_danger_triggered": shadow_danger,
        "shadow_probability": round(p, 4),
        "shadow_risk_level": shadow_risk,
        "shadow_threshold_profile": _SHADOW_PROFILE_NAME,
        "shadow_warning_threshold": _SHADOW_WARNING_THRESHOLD,
        "shadow_danger_threshold": _SHADOW_DANGER_THRESHOLD,
        "production_risk_level": production_risk_level,
        "threshold_delta_warning": delta_warning,
        "threshold_delta_danger": delta_danger,
        "evaluated_at": ts,
    }


# ─── Hydrology-only shadow evaluation ────────────────────────────────────────
# Runs a pure hydrology rule-engine in parallel with the ML pipeline.
# Independent of ML probability, OOD score, and confidence engine —
# so when the ML model is wrong, this shadow can still catch the miss.
#
# Decision mirrors L1/L1.8 hydro floors in domain/decision.py:
#   ratio >= 0.90  → DANGER
#   ratio >= 0.75  → WARNING
#   ratio >= 0.60  → PRE_ALERT
#   else           → SAFE
#   FLOOR: >= 3 stations at siaga3 or above → minimum WARNING
#
# ``shadow_danger_triggered`` is True when shadow_risk exceeds production_risk
# by >= 2 levels — indicating the hydrology engine sees materially higher risk
# than the ML pipeline. Added to failure_modes by the pipeline orchestrator.

_SHADOW_HYDRO_PROFILE = "hydro_rule"
_SHADOW_HYDRO_DANGER_RATIO: float = 0.90
_SHADOW_HYDRO_WARNING_RATIO: float = 0.75
_SHADOW_HYDRO_PRE_ALERT_RATIO: float = 0.60
_SHADOW_HYDRO_SIAGA3_FLOOR_COUNT: int = 3
_SHADOW_HYDRO_DISAGREE_LEVELS: int = 2

_HYDRO_SHADOW_RISK_RANK: dict[str, int] = {
    "SAFE": 0, "PRE_ALERT": 1, "WARNING": 2, "DANGER": 3,
}


def compute_hydro_shadow_evaluation(
    *,
    max_water_level_ratio: float,
    siaga3_or_above_count: int,
    production_risk_level: str,
    evaluated_at: str | None = None,
) -> dict:
    """
    Hydrology-only shadow evaluation — independent of the ML pipeline.

    Pure function — never reads or modifies any production decision field.
    Returns a dict for inclusion in the pipeline output payload under
    "shadow_evaluation". Pass evaluated_at for deterministic replay; when
    omitted, the current UTC time is used.
    """
    ratio = float(max_water_level_ratio)
    siaga3_count = int(siaga3_or_above_count)

    if ratio >= _SHADOW_HYDRO_DANGER_RATIO:
        shadow_risk = "DANGER"
    elif ratio >= _SHADOW_HYDRO_WARNING_RATIO:
        shadow_risk = "WARNING"
    elif ratio >= _SHADOW_HYDRO_PRE_ALERT_RATIO:
        shadow_risk = "PRE_ALERT"
    else:
        shadow_risk = "SAFE"

    if (
        siaga3_count >= _SHADOW_HYDRO_SIAGA3_FLOOR_COUNT
        and _HYDRO_SHADOW_RISK_RANK.get(shadow_risk, 0)
        < _HYDRO_SHADOW_RISK_RANK["WARNING"]
    ):
        shadow_risk = "WARNING"

    prod_rank = _HYDRO_SHADOW_RISK_RANK.get(
        str(production_risk_level or "").upper(), 0
    )
    shadow_rank = _HYDRO_SHADOW_RISK_RANK.get(shadow_risk, 0)
    disagreement_levels = shadow_rank - prod_rank
    shadow_danger_triggered = disagreement_levels >= _SHADOW_HYDRO_DISAGREE_LEVELS

    ts = evaluated_at or datetime.now(timezone.utc).isoformat()

    _log.info(
        "hydro_shadow shadow_risk=%s production_risk=%s ratio=%.4f "
        "siaga3_count=%d disagreement_levels=%d triggered=%s",
        shadow_risk,
        production_risk_level,
        ratio,
        siaga3_count,
        disagreement_levels,
        shadow_danger_triggered,
    )

    return {
        "shadow_risk_level": shadow_risk,
        "shadow_warning_triggered": shadow_rank >= _HYDRO_SHADOW_RISK_RANK["WARNING"],
        "shadow_danger_triggered": shadow_danger_triggered,
        "shadow_max_water_level_ratio": round(ratio, 4),
        "shadow_siaga3_or_above_count": siaga3_count,
        "shadow_threshold_profile": _SHADOW_HYDRO_PROFILE,
        "shadow_hydro_danger_threshold": _SHADOW_HYDRO_DANGER_RATIO,
        "shadow_hydro_warning_threshold": _SHADOW_HYDRO_WARNING_RATIO,
        "shadow_hydro_pre_alert_threshold": _SHADOW_HYDRO_PRE_ALERT_RATIO,
        "shadow_siaga3_warning_floor": _SHADOW_HYDRO_SIAGA3_FLOOR_COUNT,
        "production_risk_level": str(production_risk_level),
        "shadow_disagreement_levels": disagreement_levels,
        "evaluated_at": ts,
    }


def write_calibration_cache(
    ece: float,
    brier: float = 0.0,
    n: int = 0,
    model_version: str = "unknown",
    *,
    now: "datetime | None" = None,
) -> None:
    """
    Persist the latest ECE so the decision engine can apply a runtime confidence
    penalty when the model is poorly calibrated. Called by calibration.py.

    Writes: ece, brier, n, model_version, written_at (ISO 8601 UTC).
    written_at and model_version are used by _load_cached_ece() to warn on staleness.
    """
    try:
        os.makedirs(os.path.dirname(_CALIBRATION_CACHE), exist_ok=True)
        tmp_path = _CALIBRATION_CACHE + ".tmp"
        ts = now if now is not None else datetime.now(timezone.utc)
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "ece": round(ece, 6),
                    "brier": round(brier, 6),
                    "n": n,
                    "model_version": model_version,
                    "written_at": ts.isoformat(),
                },
                fh,
            )
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
        # Atomic on POSIX; Windows os.replace replaces an existing target atomically.
        os.replace(tmp_path, _CALIBRATION_CACHE)
        _load_cached_ece_for_mtime.cache_clear()
    except OSError:
        pass
