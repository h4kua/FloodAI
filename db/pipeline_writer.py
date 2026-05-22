"""
Transactional psycopg2 writer for the multi-stage AI pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, TypeVar
from uuid import UUID

import psycopg2
from psycopg2.extras import Json, register_uuid
from psycopg2.extensions import connection as PgConnection

from db.psycopg2_connection import (
    Psycopg2ConnectionConfig,
    pooled_connection,
)
from api.observability import DB_RETRY_TOTAL

register_uuid()

logger = logging.getLogger("pipeline")

_T = TypeVar("_T")


class PipelineError(Exception):
    """Base class for pipeline writer failures."""


class ValidationError(PipelineError, ValueError):
    """Raised when payload validation fails before any DB interaction."""


class DatabaseError(PipelineError):
    """Raised when a database operation fails after retries are exhausted."""


_RETRYABLE_DB_ERRORS = (psycopg2.OperationalError, psycopg2.InterfaceError)


def with_retry(
    fn: Callable[[], _T],
    max_attempts: int = 3,
    backoff: float = 0.5,
) -> _T:
    """
    Execute ``fn`` and retry on transient psycopg2 connectivity failures.

    Retries only on ``OperationalError`` and ``InterfaceError`` (e.g. dropped
    connections). Uses exponential backoff: ``sleep = backoff * (2 ** attempt)``.
    On exhaustion, raises ``DatabaseError`` chained from the last exception.
    """
    if max_attempts < 1:
        raise ValidationError("max_attempts must be >= 1")
    last_exc: Optional[BaseException] = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except _RETRYABLE_DB_ERRORS as exc:
            last_exc = exc
            if attempt + 1 >= max_attempts:
                break
            sleep_for = min(8.0, backoff * (2 ** attempt) * random.uniform(0.7, 1.3))
            DB_RETRY_TOTAL.labels("retry").inc()
            logger.warning(
                "stage=db.retry attempt=%d/%d backoff=%.2fs error_type=%s error=%s",
                attempt + 1,
                max_attempts,
                sleep_for,
                type(exc).__name__,
                exc,
            )
            time.sleep(sleep_for)
    DB_RETRY_TOTAL.labels("exhausted").inc()
    raise DatabaseError(
        "DB operation failed after {0} attempts".format(max_attempts)
    ) from last_exc

# IMPORTANT: SystemStatus and RiskLevel values MUST match the PostgreSQL CHECK
# constraints on the corresponding columns (system_status, risk_level) in
# evaluation_results, decisions, and pipeline_runs. If you change a value here,
# you MUST also update the database CHECK constraint in the matching migration.
# This module is the single source of truth.
# Canonical vocabulary — kept in sync with app/contracts/vocabulary.py and the
# DB CHECKs in db/migrations/100_vocabulary_sync.sql. The migration generator
# (scripts/generate_check_constraints.py, planned) will reflect the contracts
# enum into a fresh 100_vocabulary_sync.sql on every change. Until then, this
# block, app/contracts/vocabulary.py, and 100_vocabulary_sync.sql must be
# edited together.
class SystemStatus(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    LOW_TRUST = "LOW_TRUST"
    CONFLICT = "CONFLICT"
    FAIL = "FAIL"
    PIPELINE_FAILURE = "PIPELINE_FAILURE"


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    PRE_ALERT = "PRE_ALERT"
    WARNING = "WARNING"
    DANGER = "DANGER"
    UNKNOWN = "UNKNOWN"


STATUS_ALIASES: Mapping[str, SystemStatus] = {
    # Canonical (identity) entries — every SystemStatus value normalizes to itself.
    "OK": SystemStatus.OK,
    "DEGRADED": SystemStatus.DEGRADED,
    "LOW_TRUST": SystemStatus.LOW_TRUST,
    "CONFLICT": SystemStatus.CONFLICT,
    "FAIL": SystemStatus.FAIL,
    "PIPELINE_FAILURE": SystemStatus.PIPELINE_FAILURE,
    # Legacy aliases preserved for backward compatibility.
    "READY": SystemStatus.OK,
    "SUCCESS": SystemStatus.OK,
    "RUNNING": SystemStatus.DEGRADED,
    "ERROR": SystemStatus.FAIL,
    "FAILED": SystemStatus.FAIL,
}


RISK_LEVEL_ALIASES: Mapping[str, RiskLevel] = {
    # Canonical (identity) entries — every RiskLevel value normalizes to itself.
    "SAFE": RiskLevel.SAFE,
    "PRE_ALERT": RiskLevel.PRE_ALERT,
    "WARNING": RiskLevel.WARNING,
    "DANGER": RiskLevel.DANGER,
    "UNKNOWN": RiskLevel.UNKNOWN,
    # Legacy aliases preserved for backward compatibility.
    "OK": RiskLevel.SAFE,
    "LOW": RiskLevel.SAFE,
    "MEDIUM": RiskLevel.WARNING,
    "WARN": RiskLevel.WARNING,
    "WATCH": RiskLevel.PRE_ALERT,
    "HIGH": RiskLevel.DANGER,
    "CRITICAL": RiskLevel.DANGER,
}


def normalize_status(status: str) -> SystemStatus:
    """
    Normalize an incoming system_status string into a SystemStatus enum.

    Mapping: READY/SUCCESS -> OK, RUNNING -> DEGRADED, ERROR/FAILED -> FAIL.
    Already-valid values pass through. Unknown values raise ValidationError.
    """
    if not isinstance(status, str):
        raise ValidationError(
            "system_status must be a string; received {0!r}".format(
                type(status).__name__
            )
        )

    normalized = STATUS_ALIASES.get(status.strip().upper())
    if normalized is None:
        raise ValidationError(
            "Unknown system_status {0!r}; expected one of {1}".format(
                status, [s.value for s in SystemStatus]
            )
        )

    logger.debug("[STATUS] raw=%s normalized=%s", status, normalized.value)
    return normalized


def normalize_risk_level(value: str) -> RiskLevel:
    """
    Normalize an incoming risk_level string into a RiskLevel enum.

    Aliases: LOW -> SAFE, MEDIUM/WARN -> WARNING, HIGH/CRITICAL -> DANGER.
    Already-valid values pass through. Unknown values raise ValidationError.
    """
    if not isinstance(value, str):
        raise ValidationError(
            "risk_level must be a string; received {0!r}".format(
                type(value).__name__
            )
        )

    normalized = RISK_LEVEL_ALIASES.get(value.strip().upper())
    if normalized is None:
        raise ValidationError(
            "Unknown risk_level {0!r}; expected one of {1}".format(
                value, [r.value for r in RiskLevel]
            )
        )

    logger.debug("[RISK] raw=%s normalized=%s", value, normalized.value)
    return normalized


def _require_unit_interval(value: float, field_name: str) -> float:
    if value is None:
        raise ValidationError("{0} is required".format(field_name))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(
            "{0} must be numeric; received {1!r}".format(field_name, type(value).__name__)
        )
    if not 0.0 <= float(value) <= 1.0:
        raise ValidationError(
            "{0} must be in [0, 1]; received {1!r}".format(field_name, value)
        )
    return float(value)


def _require_non_negative(value: float, field_name: str) -> float:
    if value is None:
        raise ValidationError("{0} is required".format(field_name))
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValidationError(
            "{0} must be numeric; received {1!r}".format(field_name, type(value).__name__)
        )
    if float(value) < 0.0:
        raise ValidationError(
            "{0} must be >= 0; received {1!r}".format(field_name, value)
        )
    return float(value)


def _require_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(
            "{0} must be a bool; received {1!r}".format(field_name, type(value).__name__)
        )
    return value


def _require_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(
            "{0} must be a non-empty string; received {1!r}".format(field_name, value)
        )
    return value


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(
            "{0} must be a mapping; received {1!r}".format(
                field_name, type(value).__name__
            )
        )
    return value


@dataclass(frozen=True)
class PipelineRunConfig:
    """Optional metadata for the pipeline_runs row."""

    execution_mode: str = "production"
    origin: Optional[str] = None
    destination: Optional[str] = None
    api_version: Optional[str] = None
    pipeline_version: Optional[str] = None


@dataclass(frozen=True)
class PerceptionPayload:
    data_freshness_minutes: float
    snapshot_completeness: float
    signal_presence: Mapping[str, Any]


@dataclass(frozen=True)
class ReasoningPayload:
    probability: float
    confidence_score: float
    model_variant: Optional[str] = None


@dataclass(frozen=True)
class EvaluationPayload:
    system_status: str
    risk_level: str
    probability: float
    confidence_score: float
    requires_manual_review: bool


@dataclass(frozen=True)
class DecisionPayload:
    system_status: str
    requires_manual_review: bool
    decision_reason: str
    data_validity: str
    ml_execution_mode: str
    risk_level: str
    probability: float
    confidence_score: float
    is_safe_for_automation: bool


@dataclass(frozen=True)
class PipelineExecutionResult:
    """All generated primary keys from a successful pipeline execution."""

    snapshot_id: UUID
    pipeline_run_id: UUID
    perception_id: UUID
    reasoning_id: UUID
    evaluation_id: UUID
    decision_id: UUID

    def as_dict(self) -> Dict[str, str]:
        """Serialize UUID values for logging or API responses."""
        return {
            "snapshot_id": str(self.snapshot_id),
            "pipeline_run_id": str(self.pipeline_run_id),
            "perception_id": str(self.perception_id),
            "reasoning_id": str(self.reasoning_id),
            "evaluation_id": str(self.evaluation_id),
            "decision_id": str(self.decision_id),
        }


def validate_perception_payload(payload: PerceptionPayload) -> PerceptionPayload:
    """Validate a PerceptionPayload. Returns a safe instance or raises ValidationError."""
    _require_non_negative(payload.data_freshness_minutes, "perception.data_freshness_minutes")
    _require_unit_interval(payload.snapshot_completeness, "perception.snapshot_completeness")
    _require_mapping(payload.signal_presence, "perception.signal_presence")
    return payload


def validate_reasoning_payload(payload: ReasoningPayload) -> ReasoningPayload:
    """Validate a ReasoningPayload. Returns a safe instance or raises ValidationError."""
    _require_unit_interval(payload.probability, "reasoning.probability")
    _require_unit_interval(payload.confidence_score, "reasoning.confidence_score")
    if payload.model_variant is not None and not isinstance(payload.model_variant, str):
        raise ValidationError(
            "reasoning.model_variant must be a string or None; received {0!r}".format(
                type(payload.model_variant).__name__
            )
        )
    return payload


def validate_evaluation_payload(payload: EvaluationPayload) -> EvaluationPayload:
    """
    Validate and normalize an EvaluationPayload.

    Returns a new payload with system_status and risk_level normalized to their
    enum form. Raises ValidationError on any invalid field.
    """
    status = normalize_status(payload.system_status)
    risk = normalize_risk_level(payload.risk_level)
    _require_unit_interval(payload.probability, "evaluation.probability")
    _require_unit_interval(payload.confidence_score, "evaluation.confidence_score")
    _require_bool(payload.requires_manual_review, "evaluation.requires_manual_review")
    return replace(payload, system_status=status, risk_level=risk)


def validate_decision_payload(payload: DecisionPayload) -> DecisionPayload:
    """
    Validate and normalize a DecisionPayload.

    Returns a new payload with system_status and risk_level normalized to their
    enum form. Raises ValidationError on any invalid field.
    """
    status = normalize_status(payload.system_status)
    risk = normalize_risk_level(payload.risk_level)
    _require_unit_interval(payload.probability, "decision.probability")
    _require_unit_interval(payload.confidence_score, "decision.confidence_score")
    _require_bool(payload.requires_manual_review, "decision.requires_manual_review")
    _require_bool(payload.is_safe_for_automation, "decision.is_safe_for_automation")
    _require_non_empty_str(payload.decision_reason, "decision.decision_reason")
    _require_non_empty_str(payload.data_validity, "decision.data_validity")
    _require_non_empty_str(payload.ml_execution_mode, "decision.ml_execution_mode")
    return replace(payload, system_status=status, risk_level=risk)


def execute_pipeline(
    snapshot_input: Mapping[str, Any],
    location: Optional[str],
    perception: PerceptionPayload,
    reasoning: ReasoningPayload,
    evaluation: EvaluationPayload,
    decision: DecisionPayload,
    pipeline_run: Optional[PipelineRunConfig] = None,
    connection: Optional[PgConnection] = None,
    db_config: Optional[Psycopg2ConnectionConfig] = None,
    now: Optional[datetime] = None,
) -> PipelineExecutionResult:
    """
    Persist one complete pipeline execution in a single retry-safe transaction.

    Order of operations:
      1. Pre-flight validation (no DB interaction)
      2. Open connection + transaction (retry-wrapped on transient faults)
      3. Insert all stages in mandatory order
      4. Commit on success; rollback + close on any failure

    Raises:
      ValidationError: any payload field invalid (raised BEFORE the DB is touched)
      DatabaseError:   any psycopg2 failure (transient retries exhausted, or
                       non-retryable DB error wrapped with original context)
    """
    if not isinstance(snapshot_input, Mapping):
        raise ValidationError("snapshot_input must be a mapping")
    if location is not None and not isinstance(location, str):
        raise ValidationError("location must be a string or None")

    perception = validate_perception_payload(perception)
    reasoning = validate_reasoning_payload(reasoning)
    evaluation = validate_evaluation_payload(evaluation)
    decision = validate_decision_payload(decision)

    run_config = pipeline_run or PipelineRunConfig()
    # Single deterministic clock for this persistence call. When the orchestrator
    # injects ``now``, every row stamped here (snapshot.fetched_at_utc, decision
    # timestamp, pipeline_runs.completed_at) uses the same value so replays of
    # the same snapshot produce identical timestamp columns.
    pinned_now: datetime = now if now is not None else datetime.now(timezone.utc)

    # Track attempts so the FIRST attempt may use a caller-provided connection,
    # but every retry MUST acquire a fresh connection — a connection that hit a
    # transient DB error is presumed broken and must never be reused.
    state = {"attempt": 0}

    def _attempt() -> PipelineExecutionResult:
        state["attempt"] += 1
        if state["attempt"] == 1 and connection is not None:
            active = connection
            try:
                return _run_transaction(
                    conn=active,
                    snapshot_input=snapshot_input,
                    location=location,
                    perception=perception,
                    reasoning=reasoning,
                    evaluation=evaluation,
                    decision=decision,
                    run_config=run_config,
                    now=pinned_now,
                )
            except _RETRYABLE_DB_ERRORS:
                _safe_rollback(active)
                raise
            except psycopg2.Error as exc:
                _safe_rollback(active)
                logger.error(
                    "stage=execute_pipeline outcome=db_error error_type=%s error=%s",
                    type(exc).__name__,
                    exc,
                )
                raise DatabaseError(
                    "Pipeline DB write failed: {0}".format(exc)
                ) from exc
            except Exception:
                _safe_rollback(active)
                raise
        with pooled_connection(db_config) as active:
            try:
                return _run_transaction(
                    conn=active,
                    snapshot_input=snapshot_input,
                    location=location,
                    perception=perception,
                    reasoning=reasoning,
                    evaluation=evaluation,
                    decision=decision,
                    run_config=run_config,
                    now=pinned_now,
                )
            except _RETRYABLE_DB_ERRORS:
                _safe_rollback(active)
                raise
            except psycopg2.Error as exc:
                _safe_rollback(active)
                logger.error(
                    "stage=execute_pipeline outcome=db_error error_type=%s error=%s",
                    type(exc).__name__,
                    exc,
                )
                raise DatabaseError(
                    "Pipeline DB write failed: {0}".format(exc)
                ) from exc
            except Exception:
                _safe_rollback(active)
                raise

    return with_retry(_attempt)


def _run_transaction(
    conn: PgConnection,
    snapshot_input: Mapping[str, Any],
    location: Optional[str],
    perception: PerceptionPayload,
    reasoning: ReasoningPayload,
    evaluation: EvaluationPayload,
    decision: DecisionPayload,
    run_config: PipelineRunConfig,
    now: Optional[datetime] = None,
) -> PipelineExecutionResult:
    transaction_started_at = now if now is not None else datetime.now(timezone.utc)
    pipeline_started = time.perf_counter()

    with conn.cursor() as cursor:
        t0 = time.perf_counter()
        snapshot_id = create_snapshot(
            cursor=cursor, snapshot_input=snapshot_input, location=location, now=transaction_started_at,
        )
        logger.info(
            "stage=create_snapshot snapshot_id=%s duration_ms=%d",
            snapshot_id,
            int((time.perf_counter() - t0) * 1000),
        )

        t0 = time.perf_counter()
        pipeline_run_id = create_pipeline_run(
            cursor=cursor,
            snapshot_id=snapshot_id,
            pipeline_run=run_config,
            now=transaction_started_at,
        )
        logger.info(
            "stage=create_pipeline_run snapshot_id=%s pipeline_run_id=%s duration_ms=%d",
            snapshot_id,
            pipeline_run_id,
            int((time.perf_counter() - t0) * 1000),
        )

        t0 = time.perf_counter()
        perception_id = insert_perception(
            cursor=cursor,
            snapshot_id=snapshot_id,
            pipeline_run_id=pipeline_run_id,
            perception=perception,
        )
        logger.info(
            "stage=insert_perception pipeline_run_id=%s perception_id=%s duration_ms=%d",
            pipeline_run_id,
            perception_id,
            int((time.perf_counter() - t0) * 1000),
        )

        t0 = time.perf_counter()
        reasoning_id = insert_reasoning(
            cursor=cursor,
            perception_id=perception_id,
            pipeline_run_id=pipeline_run_id,
            reasoning=reasoning,
        )
        logger.info(
            "stage=insert_reasoning pipeline_run_id=%s reasoning_id=%s duration_ms=%d",
            pipeline_run_id,
            reasoning_id,
            int((time.perf_counter() - t0) * 1000),
        )

        t0 = time.perf_counter()
        evaluation_id = insert_evaluation(
            cursor=cursor,
            reasoning_id=reasoning_id,
            perception_id=perception_id,
            pipeline_run_id=pipeline_run_id,
            evaluation=evaluation,
        )
        logger.info(
            "stage=insert_evaluation pipeline_run_id=%s evaluation_id=%s status=%s risk=%s duration_ms=%d",
            pipeline_run_id,
            evaluation_id,
            _system_status_value(evaluation.system_status),
            _risk_level_value(evaluation.risk_level),
            int((time.perf_counter() - t0) * 1000),
        )

        t0 = time.perf_counter()
        decision_id = insert_decision(
            cursor=cursor,
            evaluation_id=evaluation_id,
            pipeline_run_id=pipeline_run_id,
            decision=decision,
            now=transaction_started_at,
        )
        logger.info(
            "stage=insert_decision pipeline_run_id=%s decision_id=%s status=%s risk=%s duration_ms=%d",
            pipeline_run_id,
            decision_id,
            _system_status_value(decision.system_status),
            _risk_level_value(decision.risk_level),
            int((time.perf_counter() - t0) * 1000),
        )

        t0 = time.perf_counter()
        _finalize_pipeline_run(
            cursor=cursor,
            pipeline_run_id=pipeline_run_id,
            decision=decision,
            run_config=run_config,
            decision_id=decision_id,
            transaction_started_at=transaction_started_at,
            now=transaction_started_at,
        )
        logger.info(
            "stage=finalize_pipeline_run pipeline_run_id=%s duration_ms=%d",
            pipeline_run_id,
            int((time.perf_counter() - t0) * 1000),
        )

    conn.commit()
    logger.info(
        "stage=execute_pipeline outcome=ok pipeline_run_id=%s snapshot_id=%s duration_ms=%d",
        pipeline_run_id,
        snapshot_id,
        int((time.perf_counter() - pipeline_started) * 1000),
    )
    return PipelineExecutionResult(
        snapshot_id=snapshot_id,
        pipeline_run_id=pipeline_run_id,
        perception_id=perception_id,
        reasoning_id=reasoning_id,
        evaluation_id=evaluation_id,
        decision_id=decision_id,
    )


def _safe_rollback(conn: PgConnection) -> None:
    try:
        conn.rollback()
    except Exception as exc:
        logger.warning(
            "stage=db.rollback outcome=swallowed error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )


def _safe_close(conn: PgConnection) -> None:
    try:
        conn.close()
    except Exception as exc:
        logger.warning(
            "stage=db.close outcome=swallowed error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )


def _system_status_value(value: Any) -> str:
    if isinstance(value, SystemStatus):
        return value.value
    return SystemStatus(value).value


def _risk_level_value(value: Any) -> str:
    if isinstance(value, RiskLevel):
        return value.value
    return RiskLevel(value).value


def create_snapshot(
    cursor: Any,
    snapshot_input: Mapping[str, Any],
    location: Optional[str],
    now: Optional[datetime] = None,
) -> UUID:
    """
    Insert one row per acquisition event into ``snapshots`` and return its ID.

    Identity model (post-migration 022_observation_identity.sql):
      * ``observation_id`` (auto-generated server-side via gen_random_uuid())
        is the IMMUTABLE identity of one acquisition event.
      * ``snapshot_hash`` is a NON-UNIQUE deduplication helper for content
        equality lookups; identical content across two ingestion events
        produces TWO rows with the same hash and DIFFERENT observation_ids.
      * ``first_seen_at`` records when this acquisition was first observed
        and is NEVER overwritten — auditors can recover the true ingestion
        timeline regardless of replay/retry behavior.

    There is no ON CONFLICT clause: every call produces a fresh audit row.
    Re-runs are distinguishable; original timestamps are preserved.
    """
    snapshot_hash = _compute_snapshot_hash(snapshot_input)
    fetched_at_utc = now if now is not None else datetime.now(timezone.utc)

    cursor.execute(
        """
        INSERT INTO snapshots (
            snapshot_hash,
            fetched_at_utc,
            first_seen_at,
            location,
            openweather,
            poskobanjir,
            bmkg_alerts
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            snapshot_hash,
            fetched_at_utc,
            fetched_at_utc,
            location,
            _to_jsonb(snapshot_input.get("openweather")),
            _to_jsonb(snapshot_input.get("poskobanjir")),
            _to_jsonb(snapshot_input.get("bmkg_alerts")),
        ),
    )
    return cursor.fetchone()[0]


def create_pipeline_run(
    cursor: Any,
    snapshot_id: UUID,
    pipeline_run: PipelineRunConfig,
    now: Optional[datetime] = None,
) -> UUID:
    """Insert one row into pipeline_runs and return the generated ID.

    ``now`` (optional) replaces the previous SQL-side ``NOW()`` literal so the
    ``started_at`` column is deterministic for a pinned orchestrator clock.
    """
    started_at = now if now is not None else datetime.now(timezone.utc)
    cursor.execute(
        """
        INSERT INTO pipeline_runs (
            snapshot_id,
            execution_mode,
            started_at,
            origin,
            destination,
            api_version,
            pipeline_version
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            snapshot_id,
            pipeline_run.execution_mode,
            started_at,
            pipeline_run.origin,
            pipeline_run.destination,
            pipeline_run.api_version,
            pipeline_run.pipeline_version,
        ),
    )
    return cursor.fetchone()[0]


def insert_perception(
    cursor: Any,
    snapshot_id: UUID,
    pipeline_run_id: UUID,
    perception: PerceptionPayload,
) -> UUID:
    """Insert one row into perception_results and return the generated ID."""
    cursor.execute(
        """
        INSERT INTO perception_results (
            snapshot_id,
            pipeline_run_id,
            data_freshness_minutes,
            snapshot_completeness,
            signal_presence
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            snapshot_id,
            pipeline_run_id,
            _as_decimal(perception.data_freshness_minutes),
            _as_decimal(perception.snapshot_completeness),
            Json(dict(perception.signal_presence)),
        ),
    )
    return cursor.fetchone()[0]


def insert_reasoning(
    cursor: Any,
    perception_id: UUID,
    pipeline_run_id: UUID,
    reasoning: ReasoningPayload,
) -> UUID:
    """Insert one row into reasoning_results and return the generated ID."""
    cursor.execute(
        """
        INSERT INTO reasoning_results (
            perception_id,
            pipeline_run_id,
            probability,
            confidence_score,
            model_variant
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            perception_id,
            pipeline_run_id,
            _as_decimal(reasoning.probability),
            _as_decimal(reasoning.confidence_score),
            reasoning.model_variant,
        ),
    )
    return cursor.fetchone()[0]


def insert_evaluation(
    cursor: Any,
    reasoning_id: UUID,
    perception_id: UUID,
    pipeline_run_id: UUID,
    evaluation: EvaluationPayload,
) -> UUID:
    """
    Insert one row into evaluation_results and return the generated ID.

    Caller MUST pass a payload that has been through validate_evaluation_payload.
    """
    cursor.execute(
        """
        INSERT INTO evaluation_results (
            reasoning_id,
            perception_id,
            pipeline_run_id,
            system_status,
            risk_level,
            probability,
            confidence_score,
            requires_manual_review
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            reasoning_id,
            perception_id,
            pipeline_run_id,
            _system_status_value(evaluation.system_status),
            _risk_level_value(evaluation.risk_level),
            _as_decimal(evaluation.probability),
            _as_decimal(evaluation.confidence_score),
            evaluation.requires_manual_review,
        ),
    )
    return cursor.fetchone()[0]


def insert_decision(
    cursor: Any,
    evaluation_id: UUID,
    pipeline_run_id: UUID,
    decision: DecisionPayload,
    now: Optional[datetime] = None,
) -> UUID:
    """
    Insert one row into decisions and return the generated ID.

    Caller MUST pass a payload that has been through validate_decision_payload.
    """
    cursor.execute(
        """
        INSERT INTO decisions (
            evaluation_id,
            pipeline_run_id,
            system_status,
            requires_manual_review,
            decision_reason,
            data_validity,
            ml_execution_mode,
            risk_level,
            probability,
            confidence_score,
            is_safe_for_automation,
            decision_timestamp
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            evaluation_id,
            pipeline_run_id,
            _system_status_value(decision.system_status),
            decision.requires_manual_review,
            decision.decision_reason,
            decision.data_validity,
            decision.ml_execution_mode,
            _risk_level_value(decision.risk_level),
            _as_decimal(decision.probability),
            _as_decimal(decision.confidence_score),
            decision.is_safe_for_automation,
            now if now is not None else datetime.now(timezone.utc),
        ),
    )
    return cursor.fetchone()[0]


def _finalize_pipeline_run(
    cursor: Any,
    pipeline_run_id: UUID,
    decision: DecisionPayload,
    run_config: PipelineRunConfig,
    decision_id: UUID,
    transaction_started_at: datetime,
    now: Optional[datetime] = None,
) -> None:
    """
    Update the existing pipeline_runs row with completion metadata.

    This keeps the single row created in pipeline_runs aligned with the final
    decision outcome while still honoring the one-transaction requirement.
    """
    completed_at = now if now is not None else datetime.now(timezone.utc)
    execution_time_ms = int(
        (completed_at - transaction_started_at).total_seconds() * 1000
    )
    status_value = _system_status_value(decision.system_status)
    risk_value = _risk_level_value(decision.risk_level)
    final_decision = {
        "decision_id": str(decision_id),
        "system_status": status_value,
        "requires_manual_review": decision.requires_manual_review,
        "decision_reason": decision.decision_reason,
        "data_validity": decision.data_validity,
        "ml_execution_mode": decision.ml_execution_mode,
        "risk_level": risk_value,
        "probability": decision.probability,
        "confidence_score": decision.confidence_score,
        "is_safe_for_automation": decision.is_safe_for_automation,
        "pipeline_version": run_config.pipeline_version,
    }

    cursor.execute(
        """
        UPDATE pipeline_runs
        SET completed_at = %s,
            execution_time_ms = %s,
            final_decision = %s,
            system_status = %s,
            risk_level = %s,
            confidence_score = %s
        WHERE id = %s
        """,
        (
            completed_at,
            execution_time_ms,
            Json(final_decision),
            status_value,
            risk_value,
            _as_decimal(decision.confidence_score),
            pipeline_run_id,
        ),
    )


def _compute_snapshot_hash(snapshot_input: Mapping[str, Any]) -> str:
    normalized_input = _normalize_for_hash(snapshot_input)
    normalized_snapshot = json.dumps(
        normalized_input,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )
    return hashlib.sha256(normalized_snapshot.encode("utf-8")).hexdigest()


def _normalize_for_hash(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _normalize_for_hash(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize_for_hash(v) for v in value]
    if isinstance(value, tuple):
        return [_normalize_for_hash(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValidationError("snapshot_input contains NaN or Infinity")
        return round(value, 6)
    if isinstance(value, Decimal):
        as_float = float(value)
        if not math.isfinite(as_float):
            raise ValidationError("snapshot_input contains NaN or Infinity")
        return round(as_float, 6)
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("Object of type {0} is not JSON serializable".format(type(value).__name__))


def _to_jsonb(value: Any) -> Optional[Json]:
    return None if value is None else Json(value)


def _as_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def result_to_dict(result: PipelineExecutionResult) -> Dict[str, str]:
    """Convenience helper for callers that prefer a plain dict response."""
    return result.as_dict()


# ─── VPN-safe Supabase RPC write path ──────────────────────────────────────────
#
# When psycopg2 (port 5432/6543) is blocked, the pipeline write runs through the
# fn_execute_pipeline stored function (migration 029) over Supabase RPC (HTTPS/443).
# The function performs the SAME 6 inserts + finalize UPDATE atomically server-side.
#
# Division of labour (locked with maintainer):
#   * Python validates + normalizes EVERYTHING (status/risk -> canonical, unit
#     intervals, snapshot_hash) here, exactly as execute_pipeline does, then ships
#     a flat JSON payload. The plpgsql function does no normalization — it inserts.
#   * execute_pipeline (psycopg2) is NOT modified and remains the default path.


def _serialize_pipeline_payload(
    snapshot_input: Mapping[str, Any],
    location: Optional[str],
    perception: PerceptionPayload,
    reasoning: ReasoningPayload,
    evaluation: EvaluationPayload,
    decision: DecisionPayload,
    run_config: PipelineRunConfig,
    now: datetime,
) -> Dict[str, Any]:
    """
    Build the normalized JSONB payload consumed by fn_execute_pipeline.

    Runs the SAME validation/normalization as execute_pipeline (so the RPC path
    and the psycopg2 path are byte-for-byte equivalent on the wire), computes the
    snapshot_hash Python-side, and emits canonical enum strings + ISO-8601
    timestamps + plain JSON for the jsonb columns. Mirrors _run_transaction +
    _finalize_pipeline_run field-for-field.
    """
    perception = validate_perception_payload(perception)
    reasoning = validate_reasoning_payload(reasoning)
    evaluation = validate_evaluation_payload(evaluation)
    decision = validate_decision_payload(decision)

    snapshot_hash = _compute_snapshot_hash(snapshot_input)
    fetched_at_iso = now.isoformat()
    status_value = _system_status_value(decision.system_status)
    risk_value = _risk_level_value(decision.risk_level)

    # Identical to _finalize_pipeline_run.final_decision. With a single pinned
    # clock, started_at == completed_at, so execution_time_ms == 0 (matches the
    # psycopg2 path, which derives the same zero from the pinned `now`).
    final_decision = {
        "decision_id": None,  # server fills the real id; kept for shape parity
        "system_status": status_value,
        "requires_manual_review": decision.requires_manual_review,
        "decision_reason": decision.decision_reason,
        "data_validity": decision.data_validity,
        "ml_execution_mode": decision.ml_execution_mode,
        "risk_level": risk_value,
        "probability": float(decision.probability),
        "confidence_score": float(decision.confidence_score),
        "is_safe_for_automation": decision.is_safe_for_automation,
        "pipeline_version": run_config.pipeline_version,
    }

    return {
        "snapshot": {
            "snapshot_hash": snapshot_hash,
            "fetched_at_utc": fetched_at_iso,
            "first_seen_at": fetched_at_iso,
            "location": location,
            "openweather": snapshot_input.get("openweather"),
            "poskobanjir": snapshot_input.get("poskobanjir"),
            "bmkg_alerts": snapshot_input.get("bmkg_alerts"),
        },
        "pipeline_run": {
            "execution_mode": run_config.execution_mode,
            "started_at": fetched_at_iso,
            "origin": run_config.origin,
            "destination": run_config.destination,
            "api_version": run_config.api_version,
            "pipeline_version": run_config.pipeline_version,
        },
        "perception": {
            "data_freshness_minutes": float(perception.data_freshness_minutes),
            "snapshot_completeness": float(perception.snapshot_completeness),
            "signal_presence": dict(perception.signal_presence),
        },
        "reasoning": {
            "probability": float(reasoning.probability),
            "confidence_score": float(reasoning.confidence_score),
            "model_variant": reasoning.model_variant,
        },
        "evaluation": {
            "system_status": _system_status_value(evaluation.system_status),
            "risk_level": _risk_level_value(evaluation.risk_level),
            "probability": float(evaluation.probability),
            "confidence_score": float(evaluation.confidence_score),
            "requires_manual_review": evaluation.requires_manual_review,
        },
        "decision": {
            "system_status": status_value,
            "requires_manual_review": decision.requires_manual_review,
            "decision_reason": decision.decision_reason,
            "data_validity": decision.data_validity,
            "ml_execution_mode": decision.ml_execution_mode,
            "risk_level": risk_value,
            "probability": float(decision.probability),
            "confidence_score": float(decision.confidence_score),
            "is_safe_for_automation": decision.is_safe_for_automation,
            "decision_timestamp": fetched_at_iso,
        },
        "finalize": {
            "completed_at": fetched_at_iso,
            "execution_time_ms": 0,
            "final_decision": final_decision,
        },
    }


def execute_pipeline_supabase(data: dict) -> dict:
    """VPN-safe write path via Supabase RPC (port 443).

    ``data`` is the flat payload produced by ``_serialize_pipeline_payload``.
    Returns the function's JSON result ({snapshot_id, pipeline_run_id, ...,
    status:'ok'}). Raises (never swallows) when the RPC reports no data.
    """
    from db.supabase_client import get_supabase_client

    client = get_supabase_client()
    result = client.rpc("fn_execute_pipeline", {"payload": data}).execute()
    if result.data is None:
        raise RuntimeError(f"fn_execute_pipeline RPC failed: {result}")
    return result.data


def _result_from_rpc(data: dict) -> PipelineExecutionResult:
    """
    Wrap fn_execute_pipeline's JSON result into a PipelineExecutionResult so the
    routed write path returns the SAME type regardless of transport. The function
    returns UUIDs as JSON strings; we parse them back into UUID objects.

    Raises (never swallows) when an expected id is missing or malformed.
    """
    try:
        return PipelineExecutionResult(
            snapshot_id=UUID(str(data["snapshot_id"])),
            pipeline_run_id=UUID(str(data["pipeline_run_id"])),
            perception_id=UUID(str(data["perception_id"])),
            reasoning_id=UUID(str(data["reasoning_id"])),
            evaluation_id=UUID(str(data["evaluation_id"])),
            decision_id=UUID(str(data["decision_id"])),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError(
            "fn_execute_pipeline returned an unexpected shape: {0!r}".format(data)
        ) from exc


def execute_pipeline_routed(
    snapshot_input: Mapping[str, Any],
    location: Optional[str],
    perception: PerceptionPayload,
    reasoning: ReasoningPayload,
    evaluation: EvaluationPayload,
    decision: DecisionPayload,
    pipeline_run: Optional[PipelineRunConfig] = None,
    connection: Optional[PgConnection] = None,
    db_config: Optional[Psycopg2ConnectionConfig] = None,
    now: Optional[datetime] = None,
) -> PipelineExecutionResult:
    """
    Auto-route the pipeline write to psycopg2 (direct TCP) or Supabase RPC
    (HTTPS/443, VPN-safe) based on db.connection_router.get_db_transport().

    Mirrors execute_pipeline's signature exactly and ALWAYS returns a
    PipelineExecutionResult: the psycopg2 branch returns it directly (unchanged
    behaviour); the supabase branch wraps fn_execute_pipeline's JSON result into
    one so callers (e.g. flood_pipeline._persist) can call .as_dict() regardless
    of transport.
    """
    from db.connection_router import get_db_transport

    transport = get_db_transport()
    if transport == "psycopg2":
        return execute_pipeline(
            snapshot_input=snapshot_input,
            location=location,
            perception=perception,
            reasoning=reasoning,
            evaluation=evaluation,
            decision=decision,
            pipeline_run=pipeline_run,
            connection=connection,
            db_config=db_config,
            now=now,
        )

    payload = _serialize_pipeline_payload(
        snapshot_input=snapshot_input,
        location=location,
        perception=perception,
        reasoning=reasoning,
        evaluation=evaluation,
        decision=decision,
        run_config=pipeline_run or PipelineRunConfig(),
        now=now if now is not None else datetime.now(timezone.utc),
    )
    return _result_from_rpc(execute_pipeline_supabase(payload))
