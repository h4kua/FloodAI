"""
ActionAgent — Stage 4 (final) of the agentic flood decision pipeline.

Responsibility: transform EvaluationResult into the canonical structured JSON
decision report (TASK 4 output format).

Pure formatting stage — no new decisions are made here. Keeping formatting
separate from reasoning means the output schema can evolve independently from
the decision logic without touching any agent that reasons about risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from core.enums import (
    DATA_VALIDITY_INVALID,
    DATA_VALIDITY_VALID,
    DECISION_REASON_FALLBACK,
    DECISION_REASON_INVALID_INPUT,
    DECISION_REASON_RISK,
    DECISION_SOURCE_INVALID_INPUT_FALLBACK,
    ML_EXECUTION_FULL,
    ML_EXECUTION_SHADOW_ONLY,
    SYSTEM_STATUS_PIPELINE_FAILURE,
    SYSTEM_STATUSES_AUTOMATION_ELIGIBLE,
)
from core.output_contract import validate_decision_meta


if TYPE_CHECKING:
    from agents.evaluation_agent import EvaluationResult
    from evaluation.historical_evaluator import HistoricalContext

# Only these fields from each failure dict are safe to expose publicly.
_PUBLIC_FAILURE_FIELDS = {"type", "severity", "message", "detail"}

# Saturation control: suppress repeated BNPB advisories for the same district
# within this window. Alert fatigue is a safety risk in disaster operations.
_ADVISORY_SUPPRESS_SECONDS = 30 * 60  # 30 minutes
# NOTE: Previously a module-global dict. Replaced by per-call injected state so
# the agent is request-scoped, deterministic on replay, and safe across workers.
# Callers may pass an explicit `bnpb_suppression_state` dict into ActionAgent.run
# (e.g. backed by Redis in production). When omitted, suppression is disabled —
# safer than silently re-issuing duplicates from a stale per-worker dict.


_HISTORICAL_ESCALATION_RISK_LEVELS = {"WARNING", "DANGER"}
_HISTORICAL_ESCALATION_THRESHOLD = 0.6

# Decision trust framing thresholds.
# Must remain in sync with evaluation_agent constants:
#   _TRUST_MED_CONFIDENCE  == MANUAL_REVIEW_CONFIDENCE_THRESHOLD (0.55)
#   _TRUST_HIGH_CONFIDENCE == LOW_TRUST boundary used in _determine_system_status (0.70)
_TRUST_HIGH_CONFIDENCE = 0.70
_TRUST_MED_CONFIDENCE  = 0.55


def _build_historical_explanation(
    risk_level: str,
    ctx: "HistoricalContext | None",
) -> str:
    """
    Return escalation message when historical severity warrants increased priority.

    Does NOT alter risk_level or probability — purely advisory text.
    Returns empty string when conditions are not met.
    """
    if ctx is None or not ctx.is_known_event:
        return ""
    if risk_level not in _HISTORICAL_ESCALATION_RISK_LEVELS:
        return ""
    if ctx.historical_severity < _HISTORICAL_ESCALATION_THRESHOLD:
        return ""
    return (
        f"This area has a history of severe flooding "
        f"(severity={ctx.historical_severity:.2f}, class={ctx.severity_class}). "
        "Increase response priority."
    )


class ActionAgent:
    """
    Stage 4: Action.

    Packages EvaluationResult into the canonical output format.
    All fields are always present regardless of system_status, so callers
    can parse the response without conditional handling.
    """

    def run(
        self,
        evaluation: "EvaluationResult",
        historical_context: "HistoricalContext | None" = None,
        *,
        now: "datetime | None" = None,
        bnpb_suppression_state: "dict[str, float] | None" = None,
    ) -> dict:
        """
        Transform EvaluationResult into the canonical output dict.

        historical_context is used only in offline evaluation (historical_demo.py).
        FloodDecisionPipeline never passes it; fields that depend on it
        (historical_context, decision_explanation) are always null in the live pipeline.

        ``now`` (optional) — orchestrator-pinned clock used for the ``timestamp_utc``
        field and BNPB advisory saturation. When omitted, wall-clock is used.
        ``bnpb_suppression_state`` (optional) — caller-supplied dict of
        district → epoch-seconds for the 30-minute advisory throttle. When
        omitted, suppression is skipped (no module-global fallback).
        """
        ts = now if now is not None else datetime.now(timezone.utc)
        reasoning = evaluation.reasoning
        baseline  = evaluation.baseline_check
        dec       = evaluation.decision  # DecisionResult | None
        # Consume the authoritative gate decision from EvaluationAgent.
        # BNPB-CONFLICT is generated only by EvaluationAgent — not duplicated here.
        bnpb_status = getattr(evaluation, "bnpb_status", {})
        raw_vuln = getattr(evaluation, "vulnerability_context", None)
        vuln = raw_vuln if bnpb_status.get("active", False) else None
        bnpb_active = vuln is not None

        # Carry forward the audit trail built by EvaluationAgent.
        bnpb_trace = list(getattr(evaluation, "bnpb_trace", []))

        # Prepend BNPB advisory. Returns (actions, suppression_trace | None).
        # suppression_trace is non-None when the 30-min TTL is still active.
        recommended_action, suppression_trace = self._prepend_bnpb_advisory(
            evaluation.recommended_action,
            vuln,
            evaluation.risk_level,
            now_ts=ts.timestamp(),
            suppression_state=bnpb_suppression_state,
        )
        if suppression_trace:
            bnpb_trace.append(suppression_trace)

        return {
            # ── Decision authority (top-level — unambiguous for all consumers) ─
            # _authoritative_fields lists the ONLY fields that represent the official
            # decision. All other fields are explainability, trace, or audit metadata.
            "_decision_authority": "EvaluationAgent",
            "_authoritative_fields": ["risk_level", "confidence_score", "requires_manual_review"],

            # ── System health ────────────────────────────────────────────────
            "system_status": evaluation.system_status,
            "requires_manual_review": evaluation.requires_manual_review,
            # ── Disambiguation layer (computed together for guaranteed consistency) ──
            # All four fields below are produced by a single helper to make logical
            # drift impossible. Downstream consumers MAY rely on these contracts:
            #
            #   decision_reason      — why this decision was issued
            #     "RISK"          → normal data-driven risk assessment
            #     "INVALID_INPUT" → L0 guard fired; risk_level is a conservative
            #                       placeholder, not a real-world risk estimate
            #     "FALLBACK"      → pipeline crashed; emergency dict returned
            #
            #   data_validity        — single authoritative input integrity verdict
            #     "VALID"   → no critical physical violations, no severe implausible_input
            #     "INVALID" → at least one critical violation OR severe implausible_input
            #
            #   ml_execution_mode    — was the ML output authoritative for this decision?
            #     "FULL"        → ML probability/risk shaped the decision (possibly with
            #                     L2 guardrail attenuation)
            #     "SHADOW_ONLY" → ML output computed for trace/audit only; not used to
            #                     determine final risk_level (L0 invalid-input guard or
            #                     pipeline failure)
            #
            #   is_safe_for_automation — single bool downstream automation contract
            #     True iff data_validity=VALID AND decision_reason=RISK AND
            #            system_status in {OK, DEGRADED} AND no high/critical failures
            **self._compute_decision_meta(evaluation),
            "requires_manual_review_reason": getattr(evaluation, "requires_manual_review_reason", ""),
            # Structured machine-readable trigger — use this for integrations, not the string above.
            "manual_review": self._format_manual_review(evaluation),

            # ── Core prediction ──────────────────────────────────────────────
            "risk_level": evaluation.risk_level,
            "probability": evaluation.probability,
            "confidence_score": evaluation.confidence_score,
            # Human-readable trust framing — derived from confidence_score and
            # uncertainty_score only. Answers "should this decision be trusted?"
            "decision_confidence_context": self._build_decision_confidence_context(
                evaluation.confidence_score,
                getattr(getattr(evaluation, "risk_state", None), "uncertainty_score", 0.0),
            ),

            # ── Human-optimised decision summary (Task 12) ───────────────────
            "decision_summary": dec.decision_summary if dec else "",
            "final_reason": dec.final_reason if dec else "",

            # ── C1: Decision override transparency ───────────────────────────
            "decision_override_reason": self._build_override_reason(evaluation),
            "confidence_basis": self._build_confidence_basis(evaluation),
            "uncertainty_flags": self._build_uncertainty_flags(evaluation),

            # ── Explainability ───────────────────────────────────────────────
            "dominant_risk_driver": evaluation.dominant_risk_driver,
            "risk_interpretation": evaluation.risk_interpretation,

            # ── Decision ─────────────────────────────────────────────────────
            "recommended_action": recommended_action,

            # ── BNPB InaRISK vulnerability context ───────────────────────────
            # Display the context whenever it was resolved, INDEPENDENT of the
            # BNPB activation gate. The gate (bnpb_status.active) still governs
            # whether BNPB *influences* the decision (advisory + thresholds via
            # `vuln`); it must not blank out the informational context, which
            # also carries the Batch-2 enrichment fields (hazard_index_2023,
            # historical/kelurahan flood history). bnpb_status/bnpb_influence in
            # this same output show whether it actually influenced the decision.
            "vulnerability_context": raw_vuln.to_dict() if raw_vuln else None,
            "elevation": getattr(evaluation, "elevation", {}) or None,

            # ── Decision hierarchy trace (Tasks 10, 11) ──────────────────────
            "decision_source": dec.decision_source if dec else "unknown",
            "decision_trace": dec.decision_trace if dec else [],
            "decision_trace_struct": dec.decision_trace_struct if dec else [],

            # ── Adaptive threshold transparency (Task 4) ─────────────────────
            "adaptive_threshold": dec.adaptive_threshold if dec else {},

            # ── Calibration-aware confidence adjustment (Task 3) ─────────────
            "confidence_adjustment": dec.confidence_adjustment if dec else {},

            # ── Physical override trace (Task 7) ─────────────────────────────
            "override_trace": dec.override_trace if dec else {},

            # ── Cross-layer inconsistency detection (Task 2) ─────────────────
            "inconsistency_check": dec.inconsistency_check if dec else {},

            # ── Scenario comparison: agentic vs model-only vs baseline (Task 8)
            "scenario_comparison": dec.scenario_comparison if dec else {},

            # ── Hydrology narrative injected into output (Task 5) ────────────
            "hydrology_narrative": dec.hydrology_narrative if dec else "",

            # ── Structured hydrology assessment ──────────────────────────────
            "hydrology_assessment": self._safe_to_dict(evaluation.hydrology_assessment),

            # ── Physical plausibility audit (PostgreSQL queryability) ────────
            # Compact summary of the hard physical gate. Allows audit queries to
            # distinguish predictions made on physically valid sensor data from
            # those whose inputs failed the gate (has_critical_violation=True).
            "plausibility_assessment": self._format_plausibility(evaluation.plausibility),

            # ── Sensor anomaly transparency ──────────────────────────────────
            # Stations excluded from feature extraction due to implausible
            # water-level deltas (rate-of-change spikes). Empty list when clean.
            "sensor_anomalies": list(getattr(evaluation, "sensor_anomalies", []) or []),
            # Stations excluded because their tanggal was > STATION_STALE_HOURS old
            # relative to snapshot fetched_at_utc. Empty list when all stations are fresh.
            "stale_stations": list(getattr(evaluation, "stale_stations", []) or []),

            # ── Failure transparency ─────────────────────────────────────────
            "failure_modes": self._format_failures(evaluation.failure_modes),

            # ── Baseline comparison ──────────────────────────────────────────
            "baseline_check": {
                "baseline_probability": round(
                    baseline.get("baseline_probability", 0.0), 4
                ),
                "rainfall_baseline": baseline.get("rainfall_baseline", {}),
                "hydro_baseline": baseline.get("hydro_baseline", {}),
                "baseline_disagreement": round(
                    baseline.get("baseline_disagreement", 0.0), 4
                ),
                "baseline_alert": baseline.get("baseline_alert", False),
                "model_vs_baseline": baseline.get("model_vs_baseline", "unknown"),
            },

            # ── Data observability ───────────────────────────────────────────
            "data_freshness_minutes": evaluation.data_freshness_minutes,
            "signals": self._format_public_signals(reasoning.signals),
            "diagnostics": reasoning.diagnostics,

            # ── Trust breakdown (Task 5) ─────────────────────────────────────
            "trust_breakdown": self._safe_to_dict(evaluation.trust_breakdown),

            # ── System self-interpretation ───────────────────────────────────
            "system_interpretation": self._generate_system_interpretation(evaluation),

            # ── BNPB district mapping audit trail ────────────────────────────
            # Always present — allows callers to audit which Jakarta district
            # was matched and at what confidence. Falls back to a structured
            # empty record when PerceptionAgent received no location data or
            # mapping confidence was below the 0.70 threshold.
            "mapping_info": evaluation.mapping_info or {
                "input_location": "",
                "mapped_district": None,
                "confidence": 0.0,
            },

            # ── Novelty advisory ─────────────────────────────────────────────
            # Non-null when the model probability deviates > 2σ (≈ 0.30) from
            # the rule-based baseline probability at WARNING risk level.
            # Null at all other risk levels or when deviation is within normal range.
            "novelty_advisory": evaluation.novelty_advisory,

            # ── BNPB activation gate + influence audit trail ─────────────────
            # Ordered list of [BNPB-ACTIVE]/[BNPB-SKIPPED] and [BNPB] entries.
            # First entry is always the gate pass/fail reason. Subsequent entries
            # record each IRBI-based influence (threshold raise, route penalty,
            # or BNPB-CONFLICT when vulnerability contradicts real-time signals).
            "bnpb_trace": bnpb_trace,

            # ── BNPB quantitative decision influence ─────────────────────────
            # Applied components and their magnitude — proves BNPB is not decorative.
            # applied=False when gate open but IRBI=0 (measurable zero effect).
            "bnpb_influence": getattr(evaluation, "bnpb_influence", {}),

            # ── BNPB attribution for external explainability audit ────────────
            # routing_impact_pct = (1 − irbi_penalty) × 100
            # threshold_delta    = irbi-raised confidence threshold − base threshold
            "bnpb_attribution": getattr(evaluation, "bnpb_attribution", {}),

            # ── BNPB gate inputs snapshot ────────────────────────────────────
            # Reproduces the exact inputs that drove the gate decision so any
            # external auditor can re-derive active/code/reason independently.
            "bnpb_status": getattr(evaluation, "bnpb_status", {}),

            # ── Signal aggregation state (DecisionCore — EXPLAINABILITY ONLY) ──
            # hazard_score → consistency trace notes only (informational).
            # uncertainty_score → may have triggered requires_manual_review (see reason field).
            # exposure_score and vulnerability_score are for reporting only —
            # they did NOT influence risk_level or probability.
            "risk_state": self._format_risk_state(getattr(evaluation, "risk_state", None), evaluation.risk_level),

            # ── Historical ground-truth context (post-prediction only) ────────
            # Populated by callers that have already run lookup_guarded().
            # Does NOT affect risk_level or probability — enrichment only.
            "historical_context": (
                {
                    "is_known_event": historical_context.is_known_event,
                    "historical_severity": historical_context.historical_severity,
                    "severity_class": historical_context.severity_class,
                    "event_count": historical_context.event_count,
                }
                if historical_context is not None
                else None
            ),
            "decision_explanation": _build_historical_explanation(
                evaluation.risk_level, historical_context
            ),

            # ── Metadata ─────────────────────────────────────────────────────
            # pipeline_version is injected by FloodDecisionPipeline after this
            # method returns — do not set it here. timestamp_utc derives from
            # the orchestrator-pinned `now` for deterministic replay.
            "timestamp_utc": ts.isoformat(),
            "model_name": reasoning.prediction.get("model_name", "unknown"),
        }

    def _prepend_bnpb_advisory(
        self,
        actions: list,
        vuln,
        risk_level: str,
        *,
        now_ts: float | None = None,
        suppression_state: "dict[str, float] | None" = None,
    ) -> tuple[list, str | None]:
        """
        Prepend BNPB InaRISK advisory to the action list.

        Returns:
            (enriched_actions, suppression_trace)

            suppression_trace is a non-None [BNPB-SUPPRESSED] string when the
            30-minute TTL is still active — caller must append it to bnpb_trace.

        Saturation guard is now stateless by default: it only fires when the
        caller injects ``suppression_state`` (a dict keyed by district to the
        epoch-seconds of the last advisory) and an explicit ``now_ts``. This
        removes the previous module-global mutable dict and makes replays
        deterministic.

        Safety contracts:
          - NEVER modifies risk_level or probability.
          - Templates are strictly gated by risk_level:
              SAFE    → monitoring guidance only — no deployment language
              WARNING → pre-positioning only — explicit "do NOT deploy" clause
              DANGER  → execution permitted — phased deployment with commander approval
        """
        if vuln is None:
            return list(actions), None

        district = vuln.district

        # Saturation guard only when caller provides both the clock and state.
        if suppression_state is not None and now_ts is not None:
            last_sent = suppression_state.get(district, 0.0)
            if now_ts - last_sent < _ADVISORY_SUPPRESS_SECONDS:
                suppression_trace = (
                    f"[BNPB-SUPPRESSED] Advisory already issued within 30 minutes "
                    f"for {district} — duplicate suppressed"
                )
                return list(actions), suppression_trace
            suppression_state[district] = now_ts

        pop  = vuln.affected_population
        irbi = vuln.irbi_flood_score
        cls  = vuln.exposure_class

        # Base advisory — always emitted when gate is open.
        base = (
            f"[BNPB InaRISK] {district} — IRBI flood score {irbi:.2f} ({cls}), "
            f"affected population ~{pop:,}. "
            "Coordinate with Dinas Penanggulangan Bencana setempat before any field movement."
        )
        prepended = [base]

        # Tier-specific advisory: template is selected by BOTH exposure class AND risk_level.
        # This is the only place where execution language is permitted (DANGER only).
        if cls == "VERY_HIGH":
            if risk_level == "DANGER":
                prepended.append(
                    f"[BNPB VERY HIGH + DANGER] {district} — initiate phased evacuation "
                    f"using pre-positioned resources. Population at risk ~{pop:,}. "
                    "Confirm all field deployments with incident commander before movement."
                )
            elif risk_level == "WARNING":
                prepended.append(
                    f"[BNPB VERY HIGH + WARNING] {district} — pre-position evacuation "
                    "assets within 30 minutes. Do NOT deploy unless escalation to DANGER "
                    "is confirmed. Monitor drainage every 15 minutes."
                )
            else:  # SAFE
                prepended.append(
                    f"[BNPB VERY HIGH + SAFE] {district} — maintain increased monitoring "
                    "frequency (every 30 minutes). No deployment required. "
                    "Alert readiness: STANDBY only."
                )

        elif cls == "HIGH":
            if risk_level == "DANGER":
                prepended.append(
                    f"[BNPB HIGH + DANGER] {district} — place emergency personnel on "
                    f"active standby. Affected population ~{pop:,}. "
                    "Initiate RT/RW liaison for real-time drainage overflow confirmation."
                )
            elif risk_level == "WARNING":
                prepended.append(
                    f"[BNPB HIGH + WARNING] {district} — stage resources for rapid "
                    f"response. Affected population ~{pop:,}. "
                    "Do not execute without escalation confirmation."
                )
            else:  # SAFE
                prepended.append(
                    f"[BNPB HIGH + SAFE] {district} — routine monitoring adequate. "
                    f"Population ~{pop:,} in elevated structural risk zone. "
                    "No operational action required at this time."
                )

        return prepended + list(actions), None

    def _generate_system_interpretation(self, evaluation: "EvaluationResult") -> str:
        """
        Produce a plain-language summary of the system's current operational state.

        Written for operators who need to quickly understand WHY the system is
        in its current state, not just WHAT the state is.
        """
        status = evaluation.system_status
        risk = evaluation.risk_level
        conf = evaluation.confidence_score
        failures = evaluation.failure_modes
        driver = evaluation.dominant_risk_driver
        failure_types = {f.get("type") for f in failures}

        if status == "PIPELINE_FAILURE":
            return (
                "System failure: automated flood assessment is unavailable. "
                "All pipeline stages must be restored before predictions can be trusted."
            )

        if status == "LOW_TRUST":
            reasons: list[str] = []
            if conf < 0.35:
                reasons.append(f"model confidence critically low ({conf:.0%})")
            if "signal_conflict" in failure_types:
                reasons.append("ML model and rule-based baseline disagree significantly")
            reason_str = " and ".join(reasons) or f"overall confidence below operational threshold ({conf:.0%})"
            return (
                f"Low-trust assessment: {reason_str}. "
                "Risk estimate is indicative only — independent manual verification required before any field action."
            )

        if status == "CONFLICT":
            return (
                f"Signal conflict detected: internal ML model and rule-based physical baseline produce "
                f"contradictory risk assessments. Current determination is {risk}, but opposing signals "
                "are present. Cross-reference with direct sensor readings before acting."
            )

        if status == "DEGRADED":
            degraded_from: list[str] = []
            if "missing_data" in failure_types:
                degraded_from.append("missing data source(s)")
            if "stale_data" in failure_types:
                degraded_from.append("stale sensor data exceeding freshness threshold")
            if "ood_input" in failure_types:
                degraded_from.append("out-of-distribution input features")
            if "external_source_unreliable" in failure_types:
                degraded_from.append("TMA water-level proxy unavailable")
            cause = ", ".join(degraded_from) or "reduced data quality"
            return (
                f"System operating in DEGRADED mode due to {cause}. "
                f"Risk assessment ({risk}) carries reduced confidence ({conf:.0%}). "
                "Maintain elevated operational readiness and validate with field observations."
            )

        # OK status — describe the dominant physical mechanism clearly
        driver_desc = driver.replace("_", " ")
        risk_sentences = {
            "SAFE": f"All monitored signals are within normal operational range. No active flood mechanism detected. Routine monitoring is appropriate.",
            "WARNING": f"Elevated risk from {driver_desc}. Early-warning conditions are active — verify with field teams and increase monitoring cadence.",
            "DANGER": f"High flood risk driven by {driver_desc}. Immediate protective action required — do not wait for further confirmation.",
        }
        base = risk_sentences.get(risk, f"Risk level {risk} detected via {driver_desc}.")
        return f"{base} System confidence: {conf:.0%}."

    def _format_failures(self, failures: list) -> list:
        """Strip internal fields (confidence_penalty, risk_escalation) from output."""
        return [
            {k: v for k, v in f.items() if k in _PUBLIC_FAILURE_FIELDS}
            for f in failures
        ]

    def _compute_decision_meta(self, evaluation: "EvaluationResult") -> dict:
        """
        Compute decision_reason, data_validity, ml_execution_mode and
        is_safe_for_automation as a single coherent block.

        These four fields are logically coupled — computing them in one place
        with shared inputs makes drift impossible and the consistency
        invariants enforceable by inspection. Any future change must add
        new disqualifying conditions HERE, not in scattered consumers.

        Consistency invariants enforced by construction:
          1. data_validity == "INVALID" ⇒ is_safe_for_automation is False
          2. data_validity == "INVALID" ⇒ decision_reason ∈ {INVALID_INPUT, FALLBACK}
          3. data_validity == "INVALID" ⇒ ml_execution_mode == "SHADOW_ONLY"
          4. decision_reason == "INVALID_INPUT" ⇒ data_validity == "INVALID"
          5. decision_reason == "INVALID_INPUT" ⇒ ml_execution_mode == "SHADOW_ONLY"
          6. decision_reason == "FALLBACK"      ⇒ system_status == "PIPELINE_FAILURE"
          7. decision_reason == "FALLBACK"      ⇒ ml_execution_mode == "SHADOW_ONLY"
          8. decision_reason == "RISK"          ⇒ data_validity == "VALID"
          9. is_safe_for_automation True        ⇒ all of the above plus no high/critical failures
        """
        # ── Inputs ─────────────────────────────────────────────────────────
        decision = getattr(evaluation, "decision", None)
        decision_source = getattr(decision, "decision_source", "") if decision else ""

        plausibility = getattr(evaluation, "plausibility", {}) or {}
        has_critical_violation = bool(plausibility.get("has_critical_violation", False))

        failure_modes = evaluation.failure_modes or []
        has_severe_implausible = any(
            f.get("type") == "implausible_input"
            and f.get("severity") in ("high", "critical")
            for f in failure_modes
        )
        has_high_severity_failure = any(
            f.get("severity") in ("high", "critical") for f in failure_modes
        )
        system_status = evaluation.system_status

        # ── data_validity (authoritative input integrity verdict) ──────────
        if has_critical_violation or has_severe_implausible:
            data_validity = DATA_VALIDITY_INVALID
        else:
            data_validity = DATA_VALIDITY_VALID

        # ── decision_reason (why this decision was issued) ─────────────────
        if system_status == SYSTEM_STATUS_PIPELINE_FAILURE:
            decision_reason = DECISION_REASON_FALLBACK
        elif decision_source == DECISION_SOURCE_INVALID_INPUT_FALLBACK:
            decision_reason = DECISION_REASON_INVALID_INPUT
        else:
            decision_reason = DECISION_REASON_RISK

        # ── ml_execution_mode (was ML authoritative?) ──────────────────────
        if decision_reason in (DECISION_REASON_INVALID_INPUT, DECISION_REASON_FALLBACK):
            ml_execution_mode = ML_EXECUTION_SHADOW_ONLY
        else:
            ml_execution_mode = ML_EXECUTION_FULL

        # ── is_safe_for_automation (single bool downstream contract) ───────
        # All of the following must hold for True:
        #   - data integrity is intact (data_validity=VALID)
        #   - decision came from real-data risk assessment (decision_reason=RISK)
        #   - ML actually drove the decision (ml_execution_mode=FULL)
        #   - system is operating cleanly (status in OK/DEGRADED only)
        #   - no high/critical severity failures of ANY type
        is_safe_for_automation = (
            data_validity == DATA_VALIDITY_VALID
            and decision_reason == DECISION_REASON_RISK
            and ml_execution_mode == ML_EXECUTION_FULL
            and system_status in SYSTEM_STATUSES_AUTOMATION_ELIGIBLE
            and not has_high_severity_failure
        )

        # ── Runtime invariant enforcement ─────────────────────────────────
        # Cross-field consistency is verified HERE, not just at test time. Any
        # future regression that breaks an invariant raises OutputContractError
        # which the pipeline boundary converts into a safe-fallback output —
        # never silently malformed data.
        validate_decision_meta(
            decision_reason=decision_reason,
            data_validity=data_validity,
            ml_execution_mode=ml_execution_mode,
            is_safe_for_automation=is_safe_for_automation,
            risk_level=evaluation.risk_level,
            system_status=system_status,
        )

        return {
            "decision_reason": decision_reason,
            "data_validity": data_validity,
            "ml_execution_mode": ml_execution_mode,
            "is_safe_for_automation": is_safe_for_automation,
        }

    def _format_plausibility(self, plausibility: dict | None) -> dict:
        """
        Compact public summary of the physical plausibility gate.

        Drops the verbose violations/field_scores/combo_flags arrays — those
        are already represented (where relevant) in the implausible_input
        failure_modes record. Keeps only the audit-grade scalars needed to
        query and trust a stored prediction.
        """
        p = plausibility or {}
        n_critical = sum(
            1 for v in p.get("violations", []) if v.get("severity") == "critical"
        )
        n_combo_flags = len(p.get("combo_flags", []))
        return {
            "score": round(float(p.get("plausibility_score", 1.0)), 4),
            "is_plausible": bool(p.get("is_plausible", True)),
            "has_critical_violation": bool(p.get("has_critical_violation", False)),
            "n_critical_violations": n_critical,
            "n_combo_flags": n_combo_flags,
            # Audit-grade quarantine list: which stations were excluded for
            # reporting a physically impossible water level. Needed so a stored
            # prediction is queryable for per-station faults (PostgreSQL audit)
            # and so consumers can distinguish a quarantined station from a
            # snapshot-wide critical violation.
            "quarantined_stations": list(p.get("quarantined_stations") or []),
        }

    def _format_public_signals(self, signals: dict) -> dict:
        """Strip raw scalar keys (prefixed _) — internal to decision_logic only."""
        return {k: v for k, v in signals.items() if not k.startswith("_")}

    def _format_risk_state(self, risk_state, risk_level: str = "") -> dict | None:
        """
        Serialise DecisionCore RiskState for output.

        Returns None when risk_state is unavailable (e.g. pipeline failure path).
        Injects authority/explainability labels and an interpretation layer so
        no raw score appears without context — preventing shadow decision logic
        by consumers who might otherwise act on hazard_score directly.
        """
        if risk_state is None:
            return None
        try:
            d = risk_state.to_dict()
            d["_semantic_role"] = "explainability"
            d["_decision_authority"] = "decision_engine"
            d["_explainability_only"] = True
            d["_non_authoritative_fields"] = [
                "hazard_score", "exposure_score",
                "vulnerability_score", "composite_signal_strength",
            ]
            d["composite_signal_formula"] = "0.6*hazard + 0.2*exposure + 0.2*vulnerability"
            d["explainability_context"] = self._build_explainability_context(d, risk_level)
            return d
        except Exception:  # noqa: BLE001
            return None

    def _format_manual_review(self, evaluation: "EvaluationResult") -> dict:
        """
        Structured machine-readable manual review block.

        trigger names: low_confidence | failure_count | baseline_disagreement |
                       danger_level | high_uncertainty | (empty when not required)
        """
        meta = getattr(evaluation, "requires_manual_review_meta", {})
        return {
            "required": evaluation.requires_manual_review,
            "trigger": meta.get("trigger"),
            "value": meta.get("value"),
            "threshold": meta.get("threshold"),
            "reason": meta.get("reason", ""),
        }

    def _build_explainability_context(self, risk_state_dict: dict, risk_level: str) -> dict:
        """
        Maps each dimension score against the official risk_level to produce both
        machine-readable enum fields and a human-readable interpretation string.
        Prevents operators from treating hazard_score as a second decision signal.

        Enum fields (all derived — no new signals introduced):
          hazard_level       — low | medium | high   (score < 0.33 / 0.33–0.67 / ≥ 0.67)
          decision_alignment — aligned | overridden | neutral
            aligned   = hazard direction matches risk_level
            overridden = known physical/system condition explains the divergence
            neutral   = moderate score range; score does not commit either direction
          consistency_status — consistent | physical_override | non_blocking_anomaly
          consistency_derived_from — always "hazard_vs_risk_level" (not a new signal)
        """
        hazard = risk_state_dict.get("hazard_score", 0.0)
        override = risk_state_dict.get("override_flag", False)

        if override:
            hazard_interp = "physical override active — SIAGA1 threshold breached; score forced to 1.0"
            consistency = "physical_override"
        elif hazard > 0.7 and risk_level == "SAFE":
            hazard_interp = (
                "high but consistent with SAFE decision — "
                "low ML confidence or OOD data reduced model weight; see decision_trace"
            )
            consistency = "non_blocking_anomaly"
        elif hazard < 0.2 and risk_level == "DANGER":
            hazard_interp = (
                "low but DANGER is correct — SIAGA1 physical override or "
                "failure escalation drove the decision, not ML probability"
            )
            consistency = "physical_override"
        elif hazard >= 0.5 and risk_level in ("WARNING", "DANGER"):
            hazard_interp = "elevated — consistent with decision"
            consistency = "consistent"
        elif hazard < 0.5 and risk_level == "SAFE":
            hazard_interp = "low — consistent with SAFE decision"
            consistency = "consistent"
        else:
            hazard_interp = f"score {hazard:.2f} with risk_level={risk_level}"
            consistency = "consistent"

        # Enum derivation — fully deterministic from hazard float and consistency string above.
        hazard_level = "high" if hazard >= 0.67 else ("medium" if hazard >= 0.33 else "low")
        if consistency in ("physical_override", "non_blocking_anomaly"):
            decision_alignment = "overridden"
        elif hazard_level == "medium":
            decision_alignment = "neutral"
        else:
            decision_alignment = "aligned"

        return {
            "hazard_level": hazard_level,
            "hazard_level_definition": {"low": "<0.33", "medium": "0.33-0.67", "high": ">=0.67"},
            "decision_alignment": decision_alignment,
            "decision_alignment_basis": (
                "overridden when consistency_status in (physical_override, non_blocking_anomaly); "
                "neutral when hazard_level=medium; aligned otherwise"
            ),
            "consistency_status": consistency,
            "consistency_derived_from": "hazard_vs_risk_level",
            "hazard_interpretation": hazard_interp,
            "_definition_note": (
                "thresholds and rules in this block are derived from the same constants "
                "used in computation — no separate documentation source"
            ),
        }

    def _build_decision_confidence_context(
        self, confidence_score: float, uncertainty_score: float
    ) -> dict:
        """
        Maps confidence_score and uncertainty_score to an operator-facing trust level.

        Boundaries mirror evaluation_agent constants (see module-level _TRUST_* constants).
        No new logic — this is a display mapping only.

        trust_level enum: high | medium | low
        """
        if confidence_score >= _TRUST_HIGH_CONFIDENCE and uncertainty_score <= 0.65:
            return {
                "trust_level": "high",
                "interpretation": (
                    "decision is reliable; confidence is well above operational threshold "
                    "with low epistemic uncertainty"
                ),
            }
        if confidence_score >= _TRUST_MED_CONFIDENCE:
            return {
                "trust_level": "medium",
                "interpretation": (
                    "decision meets operational threshold; "
                    "proceed with heightened awareness"
                ),
            }
        return {
            "trust_level": "low",
            "interpretation": (
                "decision requires human verification; "
                "confidence is below operational threshold"
            ),
        }

    def _build_override_reason(self, evaluation: "EvaluationResult") -> str:
        """
        Explain why the final decision may diverge from raw ML probability.
        Surfaces OOD suppression, sensor contamination, and rule-based overrides.
        """
        dec = evaluation.decision
        model_prob = evaluation.probability
        risk = evaluation.risk_level
        failure_types = {f.get("type") for f in evaluation.failure_modes}
        parts: list[str] = []

        ood_failures = [f for f in evaluation.failure_modes if f.get("type") in ("ood_input", "ood_escalation")]
        if ood_failures:
            ood_score = (ood_failures[0].get("detail") or {}).get("ood_score", 0.0)
            parts.append(
                f"XGBoost probability ({model_prob:.2f}) suppressed — "
                f"OOD flag active (IsolationForest score {ood_score:.3f}, model operating "
                "outside training distribution)."
            )

        dq = evaluation.reasoning.diagnostics.get("data_quality_report", {})
        excluded = dq.get("excluded_stations", [])
        if excluded:
            names = ", ".join(s.get("nama", "?") for s in excluded)
            parts.append(
                f"Sensor contamination suspected: {len(excluded)} station(s) excluded "
                f"({names}) — non-standard datum values outside model training range."
            )

        if dec and dec.decision_source not in ("ml_adaptive", "trend_informed"):
            source_map = {
                "physical_override": "SIAGA water-level threshold breached",
                "signal_override": "multi-signal compound event",
                "bmkg_safety_floor": "BMKG severe alert + active conditions",
                "hydro_floor": "hydrology post-ML floor applied",
                "ood_floor": "OOD floor applied",
                "system_guardrail": "system integrity guardrail",
            }
            reason = source_map.get(dec.decision_source, dec.decision_source)
            parts.append(f"Rule-based engine activated: {reason} → {risk} applied.")

        return " ".join(parts) if parts else ""

    def _build_confidence_basis(self, evaluation: "EvaluationResult") -> str:
        """Return the source of confidence: 'model', 'rule_engine', or 'ood_dampened'."""
        dec = evaluation.decision
        if not dec:
            return "unknown"
        ood_active = any(f.get("type") in ("ood_input", "ood_escalation") for f in evaluation.failure_modes)
        if ood_active:
            return "ood_dampened"
        if dec.decision_source in ("physical_override", "signal_override", "bmkg_safety_floor",
                                    "hydro_floor", "ood_floor"):
            return "rule_engine"
        return "model"

    def _build_uncertainty_flags(self, evaluation: "EvaluationResult") -> list[str]:
        """List all factors that increase uncertainty in this prediction."""
        flags: list[str] = []
        for f in evaluation.failure_modes:
            ftype = f.get("type", "")
            detail = f.get("detail") or {}
            if ftype == "ood_input":
                score = detail.get("ood_score", 0.0)
                flags.append(
                    f"ood_input: IsolationForest score {score:.3f} "
                    "(model operating outside training distribution)"
                )
            elif ftype == "ood_escalation":
                flags.append(f"ood_escalation: {f.get('message', 'OOD moderate/severe')}")
            elif ftype == "signal_conflict":
                flags.append(f"signal_conflict: {f.get('message', '')}")
            elif ftype == "stale_data":
                flags.append(f"stale_data: {f.get('message', 'data freshness exceeded')}")

        dq = evaluation.reasoning.diagnostics.get("data_quality_report", {})
        excluded = dq.get("excluded_stations", [])
        if excluded:
            names = ", ".join(s.get("nama", "?") for s in excluded)
            flags.append(f"sensor_contamination: {len(excluded)} station(s) excluded ({names})")

        stale = getattr(evaluation, "stale_stations", [])
        for s in (stale or []):
            flags.append(
                f"stale_data: {s.get('name', '?')} last updated "
                f"{s.get('hours_stale', '?')}h ago, status {s.get('status', '?')}"
            )

        model_prob = evaluation.probability
        baseline_prob = evaluation.baseline_check.get("baseline_probability", 0.0)
        gap = abs(model_prob - baseline_prob)
        if gap > 0.25:
            flags.append(
                f"model_rule_gap: XGBoost {model_prob:.2f} vs rule-based {baseline_prob:.2f} "
                f"(gap {gap:.2f})"
            )

        return flags

    def _safe_to_dict(self, obj) -> dict | None:
        """Call obj.to_dict() if obj is not None; return None on any failure."""
        if obj is None:
            return None
        try:
            return obj.to_dict()
        except Exception:  # noqa: BLE001
            return None
