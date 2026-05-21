"""
EvaluationAgent — Stage 3 of the agentic flood decision pipeline.

Responsibility:
  - Apply failure-mode confidence penalties to the raw model confidence score
  - Apply a data-freshness penalty (tracked separately to avoid double-counting)
  - Determine system_status (OK / DEGRADED / CONFLICT / LOW_TRUST)
  - Optionally escalate risk_level when specific failures warrant it
  - Decide whether human review is required
  - Generate context-aware recommended actions

This stage synthesises ReasoningAgent output into a trust-weighted assessment.
It does not re-run the model or re-interpret signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

_log = logging.getLogger(__name__)

from core.decision_core import UNCERTAINTY_MANUAL_REVIEW_THRESHOLD, DecisionCore, RiskState
from services.confidence_engine import (
    classify_ood_state,
    compute_automation_confidence,
    compute_sensor_reliability,
)
from services.decision_engine import DecisionResult, failsafe_decision, run_decision_engine
from services.decision_logic import generate_recommended_action
from services.bnpb_context import VulnerabilityContext
from services.bnpb_gate import (
    build_conflict_trace,
    build_threshold_trace,
    evaluate_bnpb_status,
)
from services.hydrology_analyzer import HydrologyAssessment
from services.trust_model import (
    TrustBreakdown,
    compute_trust_breakdown,
)

if TYPE_CHECKING:
    from agents.perception_agent import PerceptionResult
    from agents.reasoning_agent import ReasoningResult

# ─── Thresholds ───────────────────────────────────────────────────────────────

# Base confidence threshold below which the system cannot act alone.
MANUAL_REVIEW_CONFIDENCE_THRESHOLD = 0.55

# IRBI-aware dynamic threshold: 0.55 + irbi_score * 0.15, clamped to 0.70.
# Higher IRBI → higher confidence required before skipping manual review.
_IRBI_THRESHOLD_SLOPE = 0.15
_IRBI_THRESHOLD_MAX   = 0.70

# 2+ independent failures → manual review (multiple problems compound uncertainty).
MANUAL_REVIEW_FAILURE_COUNT = 2

# 1+ failure → DEGRADED (not necessarily wrong, but not fully trusted).
DEGRADED_FAILURE_COUNT = 1

# Novelty detection: approximate rolling std of flood probability (~1-sigma).
# Advisory fires when model deviates > 2 std (> 0.30) from baseline at WARNING.
_NOVELTY_ROLLING_STD = 0.15
_NOVELTY_THRESHOLD   = 2.0


@dataclass
class EvaluationResult:
    """Structured output of EvaluationAgent. Passed directly to ActionAgent."""

    system_status: str           # OK | DEGRADED | CONFLICT | LOW_TRUST
    risk_level: str              # Final risk level (may be escalated above model output)
    probability: float
    confidence_score: float      # Adjusted for failure penalties and data freshness
    data_freshness_minutes: float
    dominant_risk_driver: str
    risk_interpretation: str
    recommended_action: list
    failure_modes: list
    baseline_check: dict
    requires_manual_review: bool
    # Full reasoning kept for audit trail — not exposed in public output.
    reasoning: "ReasoningResult"
    # Human-readable reason that triggered manual review. Empty string when False.
    requires_manual_review_reason: str = field(default="")
    # Machine-readable structured trigger metadata. Keys: trigger, value, threshold, reason.
    # Empty dict when requires_manual_review is False.
    requires_manual_review_meta: dict = field(default_factory=dict)
    # Three-factor trust breakdown (Task 5). Default None for backward compatibility.
    trust_breakdown: TrustBreakdown | None = field(default=None)
    # Final decision engine output (Tasks 1–13). Single authoritative decision.
    decision: DecisionResult | None = field(default=None)
    # Hydrology assessment carried forward for ActionAgent serialisation.
    hydrology_assessment: HydrologyAssessment | None = field(default=None)
    # BNPB InaRISK vulnerability context carried forward from PerceptionAgent.
    # None when BNPB data is unavailable. MUST NOT modify risk_level or probability.
    vulnerability_context: VulnerabilityContext | None = field(default=None)
    # District mapping audit trail — always populated from PerceptionResult.
    mapping_info: dict = field(default_factory=dict)
    # Non-None when model probability significantly deviates from baseline at WARNING.
    novelty_advisory: str | None = field(default=None)
    # Whether the BNPB activation gate passed for this prediction.
    # False when: mapping confidence < 0.70, vintage > 365d, system CONFLICT, or no data.
    # RoutingAgent and ActionAgent must check this before applying any BNPB effect.
    bnpb_active: bool = field(default=False)
    # Ordered audit trail for all BNPB gate and influence decisions.
    # Always contains at least one entry (the gate pass/fail reason).
    bnpb_trace: list[str] = field(default_factory=list)
    # Authoritative gate decision from evaluate_bnpb_status().
    # Keys: active (bool), code (str), reason (str), inputs (dict).
    # ALL downstream agents must consume this — no independent re-evaluation permitted.
    bnpb_status: dict = field(default_factory=dict)
    # Quantified BNPB influence on each decision component.
    # applied=False when gate is open but IRBI=0 (no measurable effect).
    bnpb_influence: dict = field(default_factory=dict)
    # Percentage/delta attribution for external audit and explainability reports.
    bnpb_attribution: dict = field(default_factory=dict)
    # Full signal aggregation state from DecisionCore (EXPLAINABILITY ONLY).
    # hazard_score → consistency trace notes only (informational, not actionable).
    # uncertainty_score → may trigger requires_manual_review when > UNCERTAINTY_MANUAL_REVIEW_THRESHOLD.
    # exposure_score and vulnerability_score are for reporting only — never risk_level.
    risk_state: RiskState | None = field(default=None)
    # Plausibility summary surfaced for PostgreSQL queryability and audit.
    # Allows downstream consumers to distinguish predictions made on physically
    # valid sensor data from predictions whose inputs failed the hard physical gate.
    plausibility: dict = field(default_factory=dict)
    # Additive DEM enrichment carried through to ActionAgent output.
    elevation: dict = field(default_factory=dict)


class EvaluationAgent:
    """
    Stage 3: Evaluation.

    Integrates four trust signals into a holistic assessment:
      - Model confidence   (margin from decision boundary + OOD score)
      - Failure penalties  (compute_confidence_penalty from failure list)
      - Freshness penalty  (independent of failure list — avoids double-count)
      - Baseline agreement (large gap → CONFLICT status and review flag)
    """

    def run(
        self,
        reasoning: "ReasoningResult",
        perception: "PerceptionResult",
    ) -> EvaluationResult:
        prediction = reasoning.prediction
        model_prob = prediction["probability"]
        model_confidence = prediction["confidence_score"]
        # ReasoningAgent no longer emits a parallel risk classification.
        # Legacy callers may still provide this key; if absent we use a
        # conservative WARNING seed for the rare failsafe path only.
        model_risk = prediction.get("risk_level") or "WARNING"
        failure_modes = reasoning.failure_modes
        baseline = reasoning.baseline_result

        # ── Confidence adjustment ────────────────────────────────────────────
        ood_assessment = classify_ood_state(prediction.get("ood_detection"))
        sensor_reliability = compute_sensor_reliability(perception, failure_modes)
        adjusted_confidence = model_confidence

        # ── Three-factor trust breakdown (Task 5) ────────────────────────────
        trust_breakdown = compute_trust_breakdown(
            model_confidence=model_confidence,
            failure_modes=failure_modes,
            baseline_result=baseline,
            snapshot_completeness=getattr(perception, "snapshot_completeness", 1.0),
            data_freshness_minutes=perception.data_freshness_minutes,
        )
        adjusted_confidence = compute_automation_confidence(
            model_confidence=model_confidence,
            data_quality=trust_breakdown.data_quality_factor,
            signal_agreement=trust_breakdown.signal_agreement_factor,
            sensor_reliability=sensor_reliability,
            ood_assessment=ood_assessment,
        ).score

        # ── Risk level: defer to canonical decision authority (Phase 5) ──────
        # Pre-engine escalation removed. The canonical decide() called via
        # run_decision_engine() recomputes risk_level from scratch using the
        # L0-L4 hierarchy. L2_INTEGRITY in canonical handles severe-failure
        # escalation that this block previously performed (E5/E6 from the
        # Phase 1 audit). Line ~245 below assigns
        #     final_risk = decision.risk_level
        # after the engine call, so the seed value here is purely informational
        # and any pre-engine mutation would be silently overwritten.
        plausibility_dict = getattr(perception, "plausibility", {}) or {}
        has_critical_violation = bool(plausibility_dict.get("has_critical_violation", False))
        final_risk = model_risk

        features = reasoning.prediction.get("features", {})
        # Direct attribute access — no silent 1.0 default.
        # PerceptionResult.plausibility_score is always set by PerceptionAgent.run().
        # If this raises, the pipeline catches it as PIPELINE_FAILURE rather
        # than silently treating unvalidated data as fully trustworthy.
        _plaus_float = float(perception.plausibility_score)

        # ── System status (uses trust breakdown for improved LOW_TRUST logic) ──
        system_status = self._determine_system_status(
            failure_modes, baseline, adjusted_confidence, trust_breakdown
        )

        # BNPB vulnerability context — carried from PerceptionAgent.
        vuln_context = getattr(perception, "vulnerability_context", None)
        mapping_info = getattr(perception, "mapping_info", {})
        elevation_data = dict(getattr(perception, "elevation", {}) or {})
        elevation_data.setdefault(
            "rainfall_1h_mm",
            float(features.get("rainfall_mm") or reasoning.signals.get("_rainfall_mm") or 0.0),
        )
        elevation_data.setdefault(
            "rainfall_3h_mm",
            float(features.get("rainfall_roll3_mean") or 0.0) * 3.0,
        )
        elevation_data.setdefault(
            "water_level_delta",
            float(reasoning.diagnostics.get("trend_state", {}).get("water_level_delta_cur") or 0.0),
        )

        # ── BNPB activation gate ─────────────────────────────────────────────
        # Single authority: applied AFTER system_status is known (gate uses it).
        # active_vuln is the gated context — None when gate is closed.
        # All downstream BNPB influence uses active_vuln, never raw vuln_context.
        bnpb_status = evaluate_bnpb_status(vuln_context, mapping_info, system_status)
        bnpb_active = bnpb_status["active"]
        active_vuln: VulnerabilityContext | None = vuln_context if bnpb_active else None
        bnpb_trace: list[str] = [bnpb_status["reason"]]

        # ── Final Decision Engine — hierarchical override & full trace ────────
        # Runs after all EvaluationAgent logic so it can see system_status and
        # adjusted_confidence. May further escalate final_risk via the physical
        # override layer (hydrology SIAGA) and applies calibration penalty.
        try:
            decision = run_decision_engine(
                evaluation_risk_level=final_risk,
                adjusted_confidence=adjusted_confidence,
                system_status=system_status,
                probability=model_prob,
                raw_model_confidence=model_confidence,
                failure_modes=failure_modes,
                baseline_result=baseline,
                signals=reasoning.signals,
                diagnostics=reasoning.diagnostics,
                hydrology_assessment=getattr(perception, "hydrology_assessment", None),
                plausibility_score=_plaus_float,
                has_critical_violation=has_critical_violation,
                trust_breakdown=trust_breakdown,
                adaptive_classification=reasoning.prediction.get("adaptive_classification"),
                # Real perception fields — required by canonical L0 invalid-input
                # gate (completeness<0.30) and L2 DEGRADED escalation
                # (freshness>60 or completeness<0.50). Previously hardcoded to
                # 1.0/0.0 inside the adapter, making both gates unreachable.
                perception_completeness=float(
                    getattr(perception, "snapshot_completeness", 1.0) or 1.0
                ),
                data_freshness_minutes=float(perception.data_freshness_minutes),
                elevation_data=elevation_data,
            )
        except Exception as exc:  # noqa: BLE001
            decision = failsafe_decision(
                evaluation_risk_level=final_risk,
                adjusted_confidence=adjusted_confidence,
                error_message=str(exc),
            )

        # Decision engine is the final authority — accept its risk and confidence.
        final_risk         = decision.risk_level
        adjusted_confidence = decision.confidence_score

        # ── Phase 6: canonical-vs-agent system_status alignment ──────────────
        # The canonical decide() in app.domain.decision is the only final
        # authority for system_status. The agent's _determine_system_status
        # remains a provisional, compatibility-only computation used by
        # downstream gates before the canonical decision is available.
        canonical_status = getattr(decision, "system_status", "") or ""
        if canonical_status and canonical_status != system_status:
            _log.warning(
                "system_status divergence: agent=%s canonical=%s "
                "decision_source=%s authority=%s failure_types=%s",
                system_status,
                canonical_status,
                decision.decision_source,
                decision.override_trace.get("authority", ""),
                sorted({f.get("type") for f in failure_modes if isinstance(f, dict)}),
            )
            system_status = canonical_status

        # ── Full DecisionCore signal state (explainability + consistency) ─────
        # Built AFTER the decision engine so override_trace is available.
        # exposure_score and vulnerability_score are EXPLAINABILITY ONLY and must
        # not reach risk_level logic anywhere downstream.
        risk_state = DecisionCore().build_state(
            model_prob=model_prob,
            model_confidence=model_confidence,
            features=features,
            signals={**reasoning.signals, "dominant_driver": reasoning.dominant_driver},
            diagnostics=reasoning.diagnostics,
            trust_breakdown=trust_breakdown,
            vulnerability_context=active_vuln,
            hydrology_assessment=getattr(perception, "hydrology_assessment", None),
            override_trace=decision.override_trace if decision else None,
        )

        # ── Consistency notes — informational only, never actionable ────────────
        # These record an unusual signal combination for audit purposes.
        # Operators MUST act on risk_level (the official decision), not these notes.
        # The likely explanations are included so no ambiguity is left in the trace.
        # INVARIANT: appending to decision_trace does NOT mutate final_risk or
        # system_status — risk semantics are frozen before this block executes.
        if decision is not None:
            if risk_state.hazard_score > 0.8 and final_risk == "SAFE":
                decision.decision_trace.append(
                    f"[CONSISTENCY-NOTE] hazard_score={risk_state.hazard_score:.2f} "
                    f"with risk_level=SAFE — physical override or low ML confidence "
                    f"likely explains this; see decision_source"
                )
            if risk_state.hazard_score < 0.2 and final_risk == "DANGER":
                decision.decision_trace.append(
                    f"[CONSISTENCY-NOTE] hazard_score={risk_state.hazard_score:.2f} "
                    f"with risk_level=DANGER — SIAGA1 physical override is the "
                    f"likely cause; see override_trace"
                )

        # ── Recommended actions (signal-driven, not just risk_level-driven) ──
        signals = {**reasoning.signals, "dominant_driver": reasoning.dominant_driver}
        recommended_action = generate_recommended_action(signals, failure_modes, final_risk)

        # Re-evaluate manual review after engine may have escalated risk.
        # uncertainty_score passed here so the gate is unified in one place —
        # DecisionCore never sets review flags.
        requires_review, review_meta = self._requires_manual_review(
            adjusted_confidence, failure_modes, baseline, final_risk, active_vuln,
            uncertainty_score=risk_state.uncertainty_score,
        )
        review_reason = review_meta.get("reason", "")

        # BNPB threshold trace — emit once, after final_risk is authoritative.
        if active_vuln is not None:
            irbi = active_vuln.effective_irbi_score
            dyn_thresh = min(
                _IRBI_THRESHOLD_MAX,
                MANUAL_REVIEW_CONFIDENCE_THRESHOLD + irbi * _IRBI_THRESHOLD_SLOPE,
            )
            bnpb_trace.append(
                build_threshold_trace(
                    MANUAL_REVIEW_CONFIDENCE_THRESHOLD, irbi, dyn_thresh, active_vuln.district
                )
            )

        # Novelty detection — computed after final_risk is settled.
        # Passes active_vuln so the BNPB+novelty critical advisory can fire.
        novelty_advisory = self._compute_novelty_advisory(
            model_prob, baseline, final_risk, active_vuln
        )

        # BNPB-CONFLICT: high structural vulnerability contradicts SAFE real-time signals.
        # Appended to bnpb_trace here so it propagates into the final output JSON
        # via ActionAgent's "bnpb_trace" field — no separate propagation needed.
        if (
            bnpb_active
            and active_vuln is not None
            and active_vuln.exposure_class in ("HIGH", "VERY_HIGH")
            and final_risk == "SAFE"
            and not any("[BNPB-CONFLICT]" in t for t in bnpb_trace)
        ):
            bnpb_trace.append(build_conflict_trace(active_vuln, final_risk))

        # ── BNPB quantitative influence and attribution ──────────────────────
        # Computed last so final_risk and adjusted_confidence are authoritative.
        # These fields enable external auditors to verify that BNPB had a
        # measurable, traceable effect on each decision component — or confirm
        # that it was present but had zero impact (applied=False).
        if bnpb_active and active_vuln is not None:
            _irbi       = active_vuln.effective_irbi_score
            _irbi_pen   = max(0.70, 1.0 - _irbi * 0.3)
            _rout_pen   = round(1.0 - _irbi_pen, 4)
            _thr_adj    = round(
                min(_IRBI_THRESHOLD_MAX,
                    MANUAL_REVIEW_CONFIDENCE_THRESHOLD + _irbi * _IRBI_THRESHOLD_SLOPE)
                - MANUAL_REVIEW_CONFIDENCE_THRESHOLD,
                4,
            )
            _cls = active_vuln.exposure_class
            _priority_map = {
                ("VERY_HIGH", "DANGER"):  "EVACUATE",
                ("VERY_HIGH", "WARNING"): "PRE_POSITION",
                ("VERY_HIGH", "SAFE"):    "MONITOR_ELEVATED",
                ("HIGH",      "DANGER"):  "ACTIVE_STANDBY",
                ("HIGH",      "WARNING"): "STAGE_RESOURCES",
                ("HIGH",      "SAFE"):    "ROUTINE_ELEVATED",
            }
            _action_pri = _priority_map.get((_cls, final_risk), "STANDARD")
            _applied    = _thr_adj > 0.0 or _rout_pen > 0.0
            bnpb_influence = {
                "threshold_adjustment": _thr_adj,
                "routing_penalty":      _rout_pen,
                "action_priority":      _action_pri,
                "applied":              _applied,
            }
            bnpb_attribution = {
                "routing_impact_pct": round((1.0 - _irbi_pen) * 100, 2),
                "threshold_delta":    _thr_adj,
            }
            if not _applied:
                bnpb_trace.append(
                    "[BNPB-NO-IMPACT] BNPB active but no decision components were affected"
                )
        else:
            bnpb_influence = {
                "threshold_adjustment": 0.0,
                "routing_penalty":      0.0,
                "action_priority":      "NONE",
                "applied":              False,
            }
            bnpb_attribution = {
                "routing_impact_pct": 0.0,
                "threshold_delta":    0.0,
            }

        return EvaluationResult(
            system_status=system_status,
            risk_level=final_risk,
            probability=round(model_prob, 4),
            confidence_score=round(adjusted_confidence, 4),
            data_freshness_minutes=round(perception.data_freshness_minutes, 1),
            dominant_risk_driver=reasoning.dominant_driver,
            risk_interpretation=reasoning.risk_interpretation,
            recommended_action=recommended_action,
            failure_modes=failure_modes,
            baseline_check=baseline,
            requires_manual_review=requires_review,
            requires_manual_review_reason=review_reason,
            requires_manual_review_meta=review_meta,
            reasoning=reasoning,
            trust_breakdown=trust_breakdown,
            decision=decision,
            hydrology_assessment=getattr(perception, "hydrology_assessment", None),
            vulnerability_context=vuln_context,
            mapping_info=mapping_info,
            novelty_advisory=novelty_advisory,
            bnpb_active=bnpb_active,
            bnpb_trace=bnpb_trace,
            bnpb_status=bnpb_status,
            bnpb_influence=bnpb_influence,
            bnpb_attribution=bnpb_attribution,
            risk_state=risk_state,
            plausibility=getattr(perception, "plausibility", {}) or {},
            elevation=elevation_data,
        )

    def _freshness_penalty(self, freshness_minutes: float) -> float:
        """
        Sliding penalty for stale data, tracked separately from failure penalties.

        Brackets (penalty increases with age):
          Unknown (< 0)  : 0.10 flat
          0–15 min       : 0.00 (fresh)
          15–30 min      : 0.00–0.05 (minor)
          30–60 min      : 0.05–0.15 (moderate)
          > 60 min       : up to 0.20 (high)
        """
        if freshness_minutes < 0:
            return 0.10
        if freshness_minutes < 15:
            return 0.0
        if freshness_minutes < 30:
            return round((freshness_minutes - 15) / 15 * 0.05, 4)
        if freshness_minutes < 60:
            return round(0.05 + (freshness_minutes - 30) / 30 * 0.10, 4)
        return round(min(0.20, 0.15 + (freshness_minutes - 60) / 120 * 0.05), 4)

    def _determine_system_status(
        self,
        failures: list,
        baseline: dict,
        confidence: float,
        trust_breakdown: TrustBreakdown | None = None,
    ) -> str:
        """
        Determine system status using both confidence score and composite trust breakdown.

        This method is a backward-compatible provisional status calculation.
        The canonical decision runtime in app.domain.decision is the final
        source of truth for system_status when available.

        Priority order:
          1. CONFLICT — signal conflict + baseline alert (two mechanisms disagree)
          2. LOW_TRUST — composite trust < threshold OR raw confidence critically low
             Composite trust catches cases where confidence looks OK but data quality
             or signal agreement is independently poor.
          3. DEGRADED — any failure present (data quality issue, not full breakdown)
          4. OK — all checks pass
        """
        failure_types = {f.get("type") for f in failures}
        has_signal_conflict = "signal_conflict" in failure_types
        has_baseline_alert = baseline.get("baseline_alert", False)

        # CONFLICT: two independent mechanisms produce contradictory assessments.
        if has_signal_conflict and has_baseline_alert:
            return "CONFLICT"

        # LOW_TRUST: either raw confidence is critically low OR the composite trust
        # breakdown reveals a structural weakness that confidence alone doesn't capture.
        # (e.g. model confidence looks OK but data_quality_factor = 0.1 from missing data)
        composite_low_trust = trust_breakdown is not None and trust_breakdown.is_low_trust
        if confidence < 0.35 or composite_low_trust:
            return "LOW_TRUST"

        if len(failures) >= DEGRADED_FAILURE_COUNT:
            return "DEGRADED"
        return "OK"

    def _requires_manual_review(
        self,
        confidence: float,
        failures: list,
        baseline: dict,
        risk_level: str,
        active_vuln: VulnerabilityContext | None = None,
        uncertainty_score: float = 0.0,
    ) -> tuple[bool, dict]:
        """
        Single authority for all manual-review decisions.

        Six independent conditions (any one is sufficient):
          1. Confidence below IRBI-aware threshold (base 0.55, up to 0.70)
          2. Severe physically implausible input
          3. Two or more independent failure modes
          4. Baseline alert with SAFE label (two mechanisms disagree)
          5. DANGER output (always requires human confirmation)
          6. DecisionCore uncertainty_score above threshold (high epistemic uncertainty)

        Returns (requires_review, meta) where meta is machine-readable:
          {trigger: str, value: float|int|None, threshold: float|int|None, reason: str}
        Empty dict when no review is required.
        Condition 5 receives uncertainty_score from the caller — DecisionCore
        never sets review flags directly. All gate logic lives here.
        """
        if active_vuln is not None:
            irbi = active_vuln.effective_irbi_score
            threshold = min(
                _IRBI_THRESHOLD_MAX,
                MANUAL_REVIEW_CONFIDENCE_THRESHOLD + irbi * _IRBI_THRESHOLD_SLOPE,
            )
        else:
            threshold = MANUAL_REVIEW_CONFIDENCE_THRESHOLD  # 0.55

        if confidence < threshold:
            return True, {
                "trigger": "low_confidence",
                "value": round(confidence, 4),
                "threshold": round(threshold, 4),
                "reason": f"confidence {confidence:.2f} below IRBI-aware threshold {threshold:.2f}",
            }
        severe_implausible = next(
            (
                failure
                for failure in failures
                if failure.get("type") == "implausible_input"
                and failure.get("severity") == "high"
            ),
            None,
        )
        if severe_implausible is not None:
            detail = severe_implausible.get("detail") or {}
            return True, {
                "trigger": "implausible_input",
                "value": detail.get("plausibility_score"),
                "threshold": None,
                "reason": "physically implausible input detected â€” manual sensor validation required",
            }
        if len(failures) >= MANUAL_REVIEW_FAILURE_COUNT:
            return True, {
                "trigger": "failure_count",
                "value": len(failures),
                "threshold": MANUAL_REVIEW_FAILURE_COUNT,
                "reason": f"{len(failures)} independent failure modes detected",
            }
        if baseline.get("baseline_alert") and risk_level == "SAFE":
            return True, {
                "trigger": "baseline_disagreement",
                "value": None,
                "threshold": None,
                "reason": "baseline alert with SAFE label — mechanisms disagree",
            }
        if risk_level == "DANGER":
            return True, {
                "trigger": "danger_level",
                "value": None,
                "threshold": None,
                "reason": "DANGER output always requires human confirmation",
            }
        if uncertainty_score > UNCERTAINTY_MANUAL_REVIEW_THRESHOLD:
            return True, {
                "trigger": "high_uncertainty",
                "value": round(uncertainty_score, 4),
                "threshold": UNCERTAINTY_MANUAL_REVIEW_THRESHOLD,
                "reason": f"uncertainty_score {uncertainty_score:.3f} exceeds threshold {UNCERTAINTY_MANUAL_REVIEW_THRESHOLD}",
            }
        return False, {}

    def _compute_novelty_advisory(
        self,
        model_prob: float,
        baseline: dict,
        risk_level: str,
        active_vuln: VulnerabilityContext | None = None,
    ) -> str | None:
        """
        Return an advisory when model_prob deviates significantly from baseline.

        novelty_score = |model_prob − baseline_prob| / rolling_std (≈ 0.15)

        Trigger conditions (checked in priority order):
          1. novelty > 2.0 AND IRBI HIGH/VERY_HIGH at WARNING → critical advisory
          2. novelty > 2.0 at WARNING → standard elevated urgency advisory
          3. otherwise → None

        BNPB interaction only fires when active_vuln is not None (gate passed).
        Risk levels other than WARNING are handled by the physical override layer.
        """
        if risk_level != "WARNING":
            return None
        baseline_prob = float(baseline.get("baseline_probability") or model_prob)
        novelty_score = abs(model_prob - baseline_prob) / _NOVELTY_ROLLING_STD
        if novelty_score > _NOVELTY_THRESHOLD:
            if (
                active_vuln is not None
                and active_vuln.exposure_class in ("HIGH", "VERY_HIGH")
            ):
                district = active_vuln.district
                pop = active_vuln.affected_population
                return (
                    f"UNUSUAL EVENT in HIGH-VULNERABILITY ZONE ({district}, "
                    f"pop ~{pop:,}) — escalate response urgency immediately. "
                    "Model probability deviates significantly from physical baseline "
                    "in a district with elevated structural flood risk."
                )
            return (
                "This event significantly deviates from recent baseline — "
                "treat with elevated urgency."
            )
        return None
