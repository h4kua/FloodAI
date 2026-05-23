"""
FloodDecisionPipeline — Orchestrator for the 5-stage agentic decision pipeline.

Stage flow:
  PerceptionAgent → ReasoningAgent → EvaluationAgent → ActionAgent → RoutingAgent

Each stage is independently testable and fails in isolation — the pipeline
degrades gracefully rather than crashing the API when one stage encounters
an unexpected error.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger(__name__)

from agents.action_agent import ActionAgent
from agents.evaluation_agent import EvaluationAgent
from agents.perception_agent import PerceptionAgent
from agents.reasoning_agent import ReasoningAgent
from agents.routing_agent import RoutingAgent
from core.enums import (
    DATA_VALIDITY_INVALID,
    DECISION_REASON_FALLBACK,
    ML_EXECUTION_SHADOW_ONLY,
    RISK_LEVEL_UNKNOWN,
    SYSTEM_STATUS_PIPELINE_FAILURE,
)
from core.output_contract import (
    OutputContractError,
    safe_fallback_output,
    validate_output_schema,
)
from services.decision_engine import compute_hydro_shadow_evaluation
from utils.paths import DEFAULT_REALTIME_SNAPSHOT
from api.observability import PERSISTENCE_FAILED_TOTAL, RESULT_HASH_MISMATCH_TOTAL

# Hydrology-dominant drivers that lose credibility when TMA data is unreliable.
_HYDRO_DRIVERS = {"critical_hydrology", "hydrology_stress"}
_STAGE_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("FLOOD_STAGE_WORKERS", "4")))


def _stage_timeout(name: str) -> float:
    env_name = f"TIMEOUT_{name.upper()}_S"
    defaults = {
        "perception": 5.0,
        "reasoning": 8.0,
        "evaluation": 5.0,
        "action": 3.0,
        "routing": 10.0,
    }
    try:
        return float(os.getenv(env_name, str(defaults.get(name, 5.0))))
    except ValueError:
        return defaults.get(name, 5.0)


def _run_stage(name: str, fn, *args, **kwargs):
    timeout_s = _stage_timeout(name)
    future = _STAGE_EXECUTOR.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout_s)
    except FutureTimeout as exc:
        future.cancel()
        raise RuntimeError(f"{name} exceeded {timeout_s:.1f}s budget") from exc


def _compute_result_hash(result: dict) -> str:
    audit_copy = {
        key: value
        for key, value in result.items()
        if key not in {"persistence", "persistence_error"}
    }
    encoded = json.dumps(audit_copy, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# ─── Persistence-payload sanitisation ────────────────────────────────────────
#
# The persistence boundary historically failed with ValidationError when the
# upstream pipeline emitted sentinel or non-finite floats:
#   * data_freshness_minutes = -1.0    (PerceptionAgent "unknown freshness")
#   * probability / confidence_score = NaN, +Inf, -Inf
#   * snapshot_completeness = 1.0001   (rounding overshoot)
# These helpers neutralise such values BEFORE they hit pipeline_writer's
# strict validators, while preserving the original sentinel in the public
# response (so consumers can still see "freshness unknown").


def _safe_finite_float(
    value: object,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    default: float = 0.0,
) -> float:
    """
    Coerce *value* to a finite float within [minimum, maximum] (inclusive on
    both ends when supplied). NaN/Inf/None/non-numeric → ``default``;
    out-of-range values are clipped. Booleans are rejected (they would
    otherwise sneak through ``float(True) == 1.0``).
    """
    if isinstance(value, bool):
        return default
    try:
        coerced = float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    if math.isnan(coerced) or math.isinf(coerced):
        return default
    if minimum is not None and coerced < minimum:
        return minimum
    if maximum is not None and coerced > maximum:
        return maximum
    return coerced


_VALIDATION_ERROR_FIELD_RE = re.compile(
    r"^(?P<field>[a-zA-Z0-9_.\[\]]+)\s+(?:must|is\srequired|cannot)\b",
)


def _persistence_error_block(
    exc: BaseException,
    *,
    correlation_id: str,
    verbose: bool,
) -> dict:
    """
    Build the public-facing ``result["persistence_error"]`` dict.

    Always safe to expose: exception class name, parsed field path (when the
    server message follows the "<field> must …" / "<field> is required" /
    "<field> cannot …" convention used by pipeline_writer._require_*), and
    a correlation_id that operators can grep in the structured server log.

    Sensitive content (raw values, full traceback, DB hostnames) lives ONLY
    in the server log unless ``verbose=True`` (gated by
    ``FLOOD_PERSISTENCE_VERBOSE_ERRORS=1``).
    """
    err_type = type(exc).__name__
    raw_message = str(exc) or ""
    field_path: str | None = None
    match = _VALIDATION_ERROR_FIELD_RE.match(raw_message)
    if match:
        field_path = match.group("field")

    block: dict[str, object] = {
        "type": err_type,
        "message": "persistence_failed",
        "correlation_id": correlation_id,
    }
    if field_path:
        block["field"] = field_path
    if verbose:
        # Staging / dev override — surface the full server message so the
        # operator does not need log access.
        block["detail"] = raw_message[:500]
    return block


def _verbose_persistence_errors() -> bool:
    return os.getenv("FLOOD_PERSISTENCE_VERBOSE_ERRORS", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


class FloodDecisionPipeline:
    """
    Orchestrates the 5-stage agentic flood decision pipeline.

    Usage:
        pipeline = FloodDecisionPipeline()
        result = pipeline.run(snapshot)                                    # no routing
        result = pipeline.run(snapshot, origin=..., destination=...)       # with routing
        result = pipeline.run_from_file()                                  # from default snapshot
        result = pipeline.run_from_file(path, origin=..., destination=...) # with routing
    """

    def __init__(self, *, strict_mode: bool = False, persist: bool = True) -> None:
        """
        Args:
            strict_mode: When False (default), an output-contract violation is
                logged and replaced with safe_fallback_output() so downstream
                consumers never see a malformed dict. When True, the
                OutputContractError is re-raised.
            persist: When True (default), each successful pipeline run is
                written to PostgreSQL via db.pipeline_writer.execute_pipeline.
                Persistence is best-effort — DB failures are logged and
                recorded under result["persistence_error"] but never raised
                to the caller. PIPELINE_FAILURE outputs are not persisted
                because intermediate-stage objects do not exist on that path.
        """
        self._perception = PerceptionAgent()
        self._reasoning = ReasoningAgent()
        self._evaluation = EvaluationAgent()
        self._action = ActionAgent()
        self._routing = RoutingAgent()
        self._strict_mode = bool(strict_mode)
        self._persist_enabled = bool(persist)
        # Stateless across requests by design — do NOT cache per-request state
        # on `self` (e.g. last snapshot). Replays must not depend on prior calls.

    def run(
        self,
        snapshot: dict,
        origin: str | None = None,
        destination: str | None = None,
        now: datetime | None = None,
        replay_mode: bool = False,
    ) -> dict:
        """
        Execute the full pipeline on a snapshot dict.

        ``now`` (optional) pins the orchestrator clock for deterministic replay.
        When omitted, a single UTC timestamp is captured at the top of this call
        and threaded through every downstream side effect (trend write, shadow
        evaluation, DB persistence, agent timestamps) so the entire response is
        consistent and reproducible.

        ``replay_mode`` (default False) disables the realtime feature-history
        append so identical snapshot replays read the same lag/trend window and
        therefore produce identical outputs.

        Returns the structured decision report. Guaranteed to return a valid
        dict even if a stage fails — pipeline failures return
        system_status='PIPELINE_FAILURE' with requires_manual_review=True.
        """
        t_start = time.perf_counter()
        now_utc = now if now is not None else datetime.now(timezone.utc)
        # Replay mode disables side-effectful writes that would change between
        # otherwise-identical calls (feature CSV append, trend insert).
        persist_history = not replay_mode

        try:
            perception = _run_stage("perception", self._perception.run, snapshot, now=now_utc)
        except Exception as exc:
            _log.error(
                "STAGE_FAILED stage=perception type=%s msg=%s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return self._emergency_output(
                f"PerceptionAgent failed: {exc}", exc=exc, failure_stage="perception", now=now_utc,
            )

        # ── Early-exit gate: skip ReasoningAgent if critical plausibility violation ──
        # Prevents ReasoningAgent.run() from crashing on impossible input features.
        # Canonical decision still runs and computes risk via L0 physical guard.
        plausibility_dict = getattr(perception, "plausibility", {}) or {}
        has_critical_violation = bool(plausibility_dict.get("has_critical_violation", False))

        if has_critical_violation:
            # Build minimal ReasoningResult with failure_modes pre-populated.
            # EvaluationAgent + canonical decision will handle risk escalation.
            # Skipping ReasoningAgent only avoids the ML predict-step crash on
            # impossible features — the canonical decision MUST still see real
            # hydrology + rainfall + BMKG signals so L1 SIAGA / L1.5 compound
            # can fire on independent physical evidence.
            from agents.reasoning_agent import ReasoningResult
            from services.failure_handling import conflicting_signals
            from realtime_native.feature_builder import _bmkg_category_scores_from_alerts

            _rain = perception.openweather.get("rain") or {}
            _rf_mm = max(float(_rain.get("1h") or 0.0), float(_rain.get("3h") or 0.0) / 3)
            _raw_bmkg_alerts = perception.snapshot.get("bmkg_alerts") or []
            _bmkg_scores = _bmkg_category_scores_from_alerts(
                perception.bmkg_alerts or _raw_bmkg_alerts
            )

            # Real water-level ratio from hydrology stations (independent of ML).
            _hydro = getattr(perception, "hydrology_assessment", None)
            _hydro_max_ratio = 0.0
            if _hydro is not None and getattr(_hydro, "stations", None):
                _hydro_max_ratio = max(
                    (float(getattr(s, "water_level_ratio", 0.0) or 0.0) for s in _hydro.stations),
                    default=0.0,
                )

            _bypass_features = {
                "rainfall_mm": _rf_mm,
                "bmkg_weighted_score": _bmkg_scores["bmkg_weighted_score"],
                "bmkg_severity_score": _bmkg_scores["bmkg_severity_score"],
                "water_level_ratio": _hydro_max_ratio,
                "water_level_delta": 0.0,
                "rainfall_roll3_mean": _rf_mm,
            }
            _conflict_failures = conflicting_signals(_bypass_features, {}, 0.0, {})

            # Underscore-prefixed signals — match decision_logic.extract_signals
            # contract so decision_engine._build_canonical_inputs can read real
            # rainfall/BMKG/water-level scalars rather than zeros.
            _bypass_signals = {
                "_rainfall_mm": _rf_mm,
                "_bmkg_weighted": float(_bmkg_scores["bmkg_weighted_score"]),
                # Raw max BMKG severity weight — drives L1.7 BMKG_SAFETY_FLOOR
                # in the canonical decision adapter. Without this, the bypass
                # path silently falls back to the diluted weighted product.
                "_bmkg_severity": float(_bmkg_scores["bmkg_severity_score"]),
                "_water_level_ratio": _hydro_max_ratio,
                "_sensor_trusted": False,
            }

            # Pull canonical default thresholds so the bypass path classifies
            # any future probability with the same scale as the healthy path.
            from services.decision_engine import _canonical_default_thresholds
            _pre, _warn, _dng = _canonical_default_thresholds()

            reasoning = ReasoningResult(
                features=_bypass_features,
                diagnostics={"trend_state": {}},
                prediction={
                    "probability": 0.0,
                    "confidence_score": 0.0,
                    "risk_level": "UNKNOWN",
                    "ood_detection": {"score": 0.0, "flagged": False},
                    "adaptive_classification": {
                        "pre_alert_threshold": _pre,
                        "warning_threshold": _warn,
                        "danger_threshold": _dng,
                    },
                },
                signals=_bypass_signals,
                dominant_driver="unknown",
                context_summary={},
                risk_interpretation="Pipeline detected critical plausibility violation; canonical decision still consumes independent hydrology/rainfall/BMKG evidence.",
                failure_modes=[{
                    "type": "implausible_input",
                    "severity": "high",
                    "message": "Input data exceeded physical sensor limits or contains impossible values.",
                    "detail": {},
                }] + _conflict_failures,
                baseline_result={},
            )
        else:
            try:
                reasoning = _run_stage(
                    "reasoning",
                    self._reasoning.run,
                    perception, persist_history=persist_history, as_of=now_utc,
                )
            except Exception as exc:
                _log.error(
                    "STAGE_FAILED stage=reasoning type=%s msg=%s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )
                return self._emergency_output(
                    f"ReasoningAgent failed: {exc}", exc=exc, failure_stage="reasoning", now=now_utc,
                )

        try:
            evaluation = _run_stage("evaluation", self._evaluation.run, reasoning, perception)
        except Exception as exc:
            _log.error(
                "STAGE_FAILED stage=evaluation type=%s msg=%s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return self._emergency_output(
                f"EvaluationAgent failed: {exc}", exc=exc, failure_stage="evaluation", now=now_utc,
            )

        try:
            result = _run_stage("action", self._action.run, evaluation, now=now_utc)
        except Exception as exc:
            _log.error(
                "STAGE_FAILED stage=action type=%s msg=%s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return self._emergency_output(
                f"ActionAgent failed: {exc}", exc=exc, failure_stage="action", now=now_utc,
            )

        try:
            routing = _run_stage(
                "routing",
                self._routing.run,
                evaluation,
                origin,
                destination,
                now=now_utc,
                poskobanjir=list(getattr(perception, "poskobanjir", []) or []),
            )
            result["safe_route"] = routing["safe_route"]
            result["tma_data"] = routing["tma_data"]
            if routing.get("tma_failure"):
                result.setdefault("routing_failures", []).append(routing["tma_failure"])
            # Routing's `confidence_adjustment` was previously applied directly
            # to result["confidence_score"]. That was a post-canonical
            # semantic mutation invisible to decision_trace. We now ONLY
            # record the proposed adjustment in the trace and leave the
            # authoritative confidence (from Decision) untouched. Canonical
            # authority is single-source-of-truth.
            _routing_adj = routing.get("confidence_adjustment", 0.0)
            if _routing_adj < 0:
                _trace = result.get("decision_trace") or []
                if isinstance(_trace, list):
                    _trace.append(
                        f"[ROUTING-ADVISORY] proposed confidence_adjustment={_routing_adj:+.4f} "
                        "from TMA degradation — NOT applied (canonical Decision authoritative)."
                    )
                    result["decision_trace"] = _trace
                result["routing_confidence_advisory"] = {
                    "proposed_adjustment": round(_routing_adj, 4),
                    "applied": False,
                    "reason": "canonical Decision authoritative — routing may not mutate confidence_score post-decision",
                }
        except Exception as exc:
            routing_correlation_id = uuid.uuid4().hex
            _log.warning(
                "ROUTING_FAILED id=%s type=%s msg=%s",
                routing_correlation_id,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            result["safe_route"] = {
                "available": False,
                "reason": f"RoutingAgent failed: internal_error correlation_id={routing_correlation_id}",
                "flood_zones_checked": 0,
                "alternatives_evaluated": 0,
            }
            result["tma_data"] = None

        # ── Temporal trend (Task 2) ───────────────────────────────────────────
        # Compute trend from PRIOR history first so the response reflects state
        # observed BEFORE this call, then record the current prediction so the
        # next call can see it. The ``as_of=now_utc`` clamp guarantees the read
        # window is identical on replay.
        trend_state = (reasoning.diagnostics or {}).get("trend_state") or {}
        result["trend_analysis"] = {
            "risk_delta_1h": round(float(trend_state.get("risk_delta_1h") or 0.0), 4),
            "risk_trend": str(trend_state.get("risk_trend") or "insufficient_data"),
            "water_level_trend": str(
                trend_state.get("water_level_trend") or "insufficient_data"
            ),
            "rainfall_trend": str(
                trend_state.get("rainfall_trend") or "insufficient_data"
            ),
            "data_points": int(trend_state.get("data_points") or 0),
            "risk_rate_per_hour": round(
                float(trend_state.get("risk_rate_per_hour") or 0.0), 4
            ),
            "trend_strength": round(float(trend_state.get("trend_strength") or 0.0), 4),
            "trend_confidence": round(
                float(trend_state.get("trend_confidence") or 0.0), 4
            ),
            "anomaly_detected": bool(trend_state.get("anomaly_detected", False)),
            "anomaly_type": trend_state.get("anomaly_type"),
            "source": "realtime_snapshot_history",
        }

        # ── TMA reliability — suppress hydrology-dominant driver (Task 5) ────
        tma_failed = any(
            f.get("type") == "external_source_unreliable"
            for f in (result.get("failure_modes", []) + result.get("routing_failures", []))
        )
        if tma_failed and result.get("dominant_risk_driver") in _HYDRO_DRIVERS:
            result["dominant_risk_driver"] = "hydrology_unverified"
            result["risk_interpretation"] = (
                result.get("risk_interpretation", "")
                + " [RELIABILITY NOTE: Hydrology assessment reduced — TMA water-level"
                " data unavailable. River-level signals cannot be independently verified.]"
            )
            result["system_interpretation"] = (
                "System operating with reduced hydrology reliability — TMA (Tinggi Muka Air) "
                "real-time data source is unavailable. Hydrology-driven risk signals are present "
                "but unverified by live sensor readings. "
                f"Risk: {result.get('risk_level', 'UNKNOWN')} "
                f"({result.get('confidence_score', 0.0):.0%} confidence)."
            )

        # ── Shadow threshold evaluation (DATA-2, hydrology-only, read-only) ────
        # Pure hydrology rule-engine — independent of ML probability, OOD score,
        # and confidence engine. Catches cases where the ML model is wrong and
        # the hydrology signals alone mandate a higher risk level.
        # Never modifies risk_level, system_status, authority, or decision_trace.
        try:
            _shadow_hydro = getattr(perception, "hydrology_assessment", None)
            _shadow_max_ratio = 0.0
            _shadow_siaga3_count = 0
            if _shadow_hydro is not None:
                _shadow_stations = getattr(_shadow_hydro, "stations", None)
                if isinstance(_shadow_stations, list):
                    if _shadow_stations:
                        _shadow_max_ratio = max(
                            (float(getattr(s, "water_level_ratio", 0.0) or 0.0)
                             for s in _shadow_stations),
                            default=0.0,
                        )
                        _shadow_siaga3_count = sum(
                            1 for s in _shadow_stations
                            if str(getattr(s, "siaga_level", "normal") or "normal")
                            in ("siaga1", "siaga2", "siaga3")
                        )
            _shadow_prod_risk = result.get("risk_level", "UNKNOWN")
            _shadow_eval = compute_hydro_shadow_evaluation(
                max_water_level_ratio=_shadow_max_ratio,
                siaga3_or_above_count=_shadow_siaga3_count,
                production_risk_level=_shadow_prod_risk,
                evaluated_at=now_utc.isoformat(),
            )
            result["shadow_evaluation"] = _shadow_eval
            if _shadow_eval.get("shadow_danger_triggered"):
                _gap = _shadow_eval.get("shadow_disagreement_levels", 0)
                result["failure_modes"].append({
                    "type": "shadow_hydro_disagreement",
                    "severity": "high",
                    "message": (
                        f"Shadow hydrology model disagrees with production decision "
                        f"(shadow={_shadow_eval['shadow_risk_level']}, "
                        f"production={_shadow_prod_risk}, gap={_gap} levels). "
                        "Pure hydrology rules indicate higher flood risk than ML pipeline."
                    ),
                    "risk_escalation": False,
                    "confidence_penalty": 0.0,
                    "detail": {
                        "shadow_risk": _shadow_eval["shadow_risk_level"],
                        "production_risk": _shadow_prod_risk,
                        "disagreement_levels": _gap,
                        "max_water_level_ratio": _shadow_max_ratio,
                        "siaga3_or_above_count": _shadow_siaga3_count,
                    },
                })
        except Exception as _shadow_exc:
            _log.warning("shadow_evaluation failed (non-fatal): %s", _shadow_exc)
            result["shadow_evaluation"] = {
                "shadow_threshold_profile": "hydro_rule",
                "error": str(_shadow_exc),
            }

        result["pipeline_execution_ms"] = round(
            (time.perf_counter() - t_start) * 1000, 1
        )
        result["pipeline_version"] = "agentic-v2.0"

        # ── Final output contract gate (MANDATORY) ──────────────────────────
        # Last-line defence: if any code path between PerceptionAgent and here
        # has produced a malformed or internally inconsistent output, replace
        # it with a safe-fallback dict so downstream consumers never see
        # silently corrupt data. The contract is verified once at this single
        # boundary point — no consumer needs to re-validate.
        #
        # Observability:
        #   1. The error is logged with full structured context — operators
        #      see every fallback even if the API consumer only sees the dict.
        #   2. The fallback dict carries a `contract_violation` block AND a
        #      `[L5-CONTRACT-FAILURE]` trace marker, so the failure cannot be
        #      silently masked downstream.
        #   3. In strict_mode the exception is re-raised — used by tests,
        #      debug runs, and CI to make a contract regression a hard fail.
        try:
            validate_output_schema(result)
        except OutputContractError as exc:
            error_type = type(exc).__name__
            _log.error(
                "OUTPUT_CONTRACT_VIOLATION error_type=%s message=%s "
                "system_status=%r risk_level=%r decision_reason=%r "
                "data_validity=%r ml_execution_mode=%r is_safe_for_automation=%r "
                "decision_source=%r",
                error_type,
                str(exc),
                result.get("system_status"),
                result.get("risk_level"),
                result.get("decision_reason"),
                result.get("data_validity"),
                result.get("ml_execution_mode"),
                result.get("is_safe_for_automation"),
                result.get("decision_source"),
            )
            if self._strict_mode:
                raise
            return safe_fallback_output(
                str(exc),
                error_type=error_type,
                original_result=result,
                now=now_utc,
            )

        # ── PostgreSQL persistence (audit-authoritative) ────────────────────
        # MUST happen after contract validation so we never persist a malformed
        # row. PIPELINE_FAILURE outputs ARE now persisted — they are the most
        # important rows for forensics. _persist() escalates DB failures to
        # system_status=DEGRADED instead of swallowing them.
        if self._persist_enabled:
            result_hash_before_persist = _compute_result_hash(result)
            self._persist(
                snapshot, perception, reasoning, evaluation, result,
                origin, destination, now_utc,
            )
            result_hash_after_persist = _compute_result_hash(result)
            if result_hash_before_persist != result_hash_after_persist:
                RESULT_HASH_MISMATCH_TOTAL.inc()
                _log.error(
                    "RESULT_HASH_MISMATCH before=%s after=%s",
                    result_hash_before_persist,
                    result_hash_after_persist,
                )
        return result

    def run_from_file(
        self,
        snapshot_path: Path | str | None = None,
        origin: str | None = None,
        destination: str | None = None,
        now: datetime | None = None,
        replay_mode: bool = False,
    ) -> dict:
        """Load snapshot JSON from disk and run the full pipeline."""
        path = Path(snapshot_path) if snapshot_path else DEFAULT_REALTIME_SNAPSHOT
        with open(path, encoding="utf-8") as fh:
            snapshot = json.load(fh)
        return self.run(
            snapshot, origin=origin, destination=destination, now=now, replay_mode=replay_mode,
        )

    def _persist(
        self,
        snapshot: dict,
        perception,
        reasoning,
        evaluation,
        result: dict,
        origin: str | None,
        destination: str | None,
        now_utc: datetime | None = None,
    ) -> None:
        """
        Best-effort write of all 6 stage rows to PostgreSQL via pipeline_writer.

        Failures are logged and surfaced under result["persistence_error"] but
        NEVER raised — a DB outage must not break the prediction response.
        """
        try:
            from db.pipeline_writer import (
                DecisionPayload,
                EvaluationPayload,
                PerceptionPayload,
                PipelineRunConfig,
                ReasoningPayload,
                execute_pipeline_routed,
            )

            location = snapshot.get("location") if isinstance(snapshot, dict) else None
            signal_presence = (
                getattr(perception, "signal_presence", None)
                or result.get("signals", {})
                or {}
            )

            # Sanitize floats at the persistence boundary so upstream
            # sentinels (-1.0 = "unknown freshness"), NaN/Inf, and tiny
            # rounding overshoots never reach pipeline_writer's strict
            # _require_unit_interval / _require_non_negative checks. The
            # ORIGINAL values remain in ``result`` for the API response.
            freshness_raw = result.get("data_freshness_minutes")
            freshness_persist = _safe_finite_float(
                freshness_raw,
                minimum=0.0,
                maximum=None,
                # -1.0 sentinel collapses to 0.0 (DB column is NOT NULL with
                # >=0 CHECK). Operators looking for "unknown freshness" must
                # consume the API response field, not the row.
                default=0.0,
            )
            completeness_persist = _safe_finite_float(
                getattr(perception, "snapshot_completeness", 1.0),
                minimum=0.0,
                maximum=1.0,
                default=1.0,
            )
            probability_persist = _safe_finite_float(
                result.get("probability"),
                minimum=0.0,
                maximum=1.0,
                default=0.0,
            )
            confidence_persist = _safe_finite_float(
                result.get("confidence_score"),
                minimum=0.0,
                maximum=1.0,
                default=0.0,
            )

            perception_payload = PerceptionPayload(
                data_freshness_minutes=freshness_persist,
                snapshot_completeness=completeness_persist,
                signal_presence=dict(signal_presence) if signal_presence else {},
            )
            reasoning_payload = ReasoningPayload(
                probability=probability_persist,
                confidence_score=confidence_persist,
                model_variant=result.get("model_name"),
            )
            evaluation_payload = EvaluationPayload(
                system_status=result["system_status"],
                risk_level=result["risk_level"],
                probability=probability_persist,
                confidence_score=confidence_persist,
                requires_manual_review=bool(result.get("requires_manual_review", False)),
            )
            decision_payload = DecisionPayload(
                system_status=result["system_status"],
                requires_manual_review=bool(result.get("requires_manual_review", False)),
                decision_reason=result.get("decision_reason") or "RISK",
                data_validity=result.get("data_validity") or "VALID",
                ml_execution_mode=result.get("ml_execution_mode") or "FULL",
                risk_level=result["risk_level"],
                probability=probability_persist,
                confidence_score=confidence_persist,
                is_safe_for_automation=bool(result.get("is_safe_for_automation", False)),
            )
            ids = execute_pipeline_routed(
                snapshot_input=snapshot,
                location=location,
                perception=perception_payload,
                reasoning=reasoning_payload,
                evaluation=evaluation_payload,
                decision=decision_payload,
                pipeline_run=PipelineRunConfig(
                    execution_mode="production",
                    origin=origin,
                    destination=destination,
                    api_version="v1",
                    pipeline_version=result.get("pipeline_version", "agentic-v2.0"),
                ),
                now=now_utc,
            )
            result["persistence"] = ids.as_dict()
        except Exception as exc:
            # Persistence failure is a system failure. Escalate
            # system_status from OK to DEGRADED (preserve already-severe
            # values) and surface the error in the response so operators see
            # it. Silent persistence loss is not acceptable in production.
            correlation_id = uuid.uuid4().hex
            _log.error(
                "PERSISTENCE_FAILED correlation_id=%s type=%s msg=%s "
                "system_status_before=%s",
                correlation_id,
                type(exc).__name__,
                exc,
                result.get("system_status"),
                exc_info=True,
            )
            PERSISTENCE_FAILED_TOTAL.labels(type(exc).__name__).inc()
            result["persistence_error"] = _persistence_error_block(
                exc,
                correlation_id=correlation_id,
                verbose=_verbose_persistence_errors(),
            )
            if result.get("system_status") in (None, "OK"):
                result["system_status"] = "DEGRADED"

    @staticmethod
    def _emergency_output(
        reason: str,
        *,
        exc: Exception | None = None,
        failure_stage: str = "unknown",
        now: datetime | None = None,
    ) -> dict:
        """
        Fallback when a stage raises an unhandled exception.

        Always returns a structurally valid response so the FastAPI endpoint
        never produces an opaque 500 — operators always receive actionable context.
        Accepts ``now`` so emergency-path ``timestamp_utc`` matches the
        orchestrator clock for deterministic replay.

        ``replay_correlation_id`` is a deterministic UUIDv5 derived from
        (now, failure_stage, reason) so identical inputs at the same pinned
        clock produce identical correlation ids.
        """
        ts = now if now is not None else datetime.now(timezone.utc)
        correlation_id = str(uuid.uuid4())
        crash_detail: dict = {
            "failure_stage": failure_stage,
            "exception_type": type(exc).__name__ if exc is not None else "unknown",
            "replay_correlation_id": correlation_id,
            "emergency_mode": True,
        }
        return {
            "system_status": SYSTEM_STATUS_PIPELINE_FAILURE,
            "requires_manual_review": True,
            # Disambiguation layer — same contract as ActionAgent output.
            # Logically consistent: PIPELINE_FAILURE → FALLBACK → SHADOW_ONLY
            # → INVALID → not safe for automation.
            "decision_reason": DECISION_REASON_FALLBACK,
            "data_validity": DATA_VALIDITY_INVALID,
            "ml_execution_mode": ML_EXECUTION_SHADOW_ONLY,
            "is_safe_for_automation": False,
            "risk_level": RISK_LEVEL_UNKNOWN,
            "probability": 0.0,
            "confidence_score": 0.0,
            "dominant_risk_driver": "pipeline_error",
            "risk_interpretation": (
                f"Pipeline failure: {reason}. "
                "Automated assessment is unavailable — manual evaluation required."
            ),
            "recommended_action": [
                "IMMEDIATE: Automated prediction system is offline. "
                "Conduct manual flood assessment using field personnel and direct sensor readings."
            ],
            "failure_modes": [
                {
                    "type": "pipeline_error",
                    "severity": "critical",
                    "message": reason,
                    "detail": crash_detail,
                }
            ],
            "baseline_check": {
                "baseline_probability": 0.0,
                "rainfall_baseline": {},
                "hydro_baseline": {},
                "baseline_disagreement": 0.0,
                "baseline_alert": False,
                "model_vs_baseline": "unknown",
            },
            "data_freshness_minutes": -1.0,
            "signals": {},
            "diagnostics": {},
            "timestamp_utc": ts.isoformat(),
            "pipeline_version": "agentic-v2.0",
            "model_name": "unknown",
        }
