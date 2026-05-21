"""
Temporal trend analysis — DB-backed, restart-safe, multi-worker deterministic.

H2A: the process-local deque ring buffer has been replaced with a
PostgreSQL-backed trend_history table. compute_trend() reads from the shared
DB so all workers produce identical results for identical history.

Public API (backward compatible; station_id is keyword-only with a default):
  record_prediction(probability, risk_level, water_level_ratio, rainfall_mm,
                    *, station_id='default') -> None
  compute_trend(*, station_id='default') -> dict
  reset_history(*, station_id='default') -> None

Failure semantics:
  record_prediction DB failure  -> warning logged, write skipped (fail open);
                                   next compute_trend returns insufficient_data.
  compute_trend DB failure      -> returns _insufficient(0) (fail closed —
                                   no invented trend state).
  reset_history DB failure      -> warning logged.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from db.psycopg2_connection import pooled_connection
from db.trend_repository import (
    delete_trend_records,
    get_recent_trend_records,
    insert_trend_record,
)

logger = logging.getLogger(__name__)

_HISTORY_SIZE = 8
_DEFAULT_STATION = "default"

# Trend classification thresholds
_PROB_TREND_THRESHOLD     = 0.08    # Weighted delta to classify increasing/decreasing
_WL_TREND_THRESHOLD       = 0.04    # Water-level ratio delta
_RAINFALL_TREND_THRESHOLD = 4.0     # Rainfall mm delta

# Anomaly detection thresholds
_SPIKE_THRESHOLD       = 0.20   # Single-step probability jump = spike event
_ACCUMULATION_STEPS    = 4      # Consecutive rising steps to flag slow accumulation
_MIN_RATE_HOURS        = 0.005  # ~18 seconds — guard against divide-by-zero


# ── Public API ────────────────────────────────────────────────────────────────

def record_prediction(
    probability: float,
    risk_level: str,
    water_level_ratio: float | None,
    rainfall_mm: float | None,
    *,
    station_id: str = _DEFAULT_STATION,
    observed_at: datetime | None = None,
) -> None:
    """
    Persist a completed prediction snapshot to trend_history.

    ``observed_at`` (optional) pins the row timestamp for deterministic replay.
    When omitted, the current UTC time is used to preserve existing behavior.
    """
    ts = observed_at if observed_at is not None else datetime.now(timezone.utc)
    try:
        with pooled_connection() as conn:
            insert_trend_record(
                conn,
                station_id=station_id,
                observed_at=ts,
                probability=probability,
                risk_level=risk_level,
                water_level_ratio=water_level_ratio,
                rainfall_mm=rainfall_mm,
                max_history=_HISTORY_SIZE,
            )
    except Exception as exc:
        logger.warning("trend_analysis.record_prediction: DB write failed — %s", exc)


def compute_trend(
    *,
    station_id: str = _DEFAULT_STATION,
    as_of: datetime | None = None,
) -> dict:
    """
    Read trend_history from DB and derive trend signals.

    ``as_of`` (optional) restricts the read window to rows strictly older than
    that timestamp. Used by the deterministic-replay path so the trend block
    inside inference does not drift with same-call inserts.

    Returns the same dict structure as before; all prior keys are preserved.
    Returns _insufficient(0) if the DB is unavailable (fail closed).
    """
    try:
        with pooled_connection() as conn:
            history = get_recent_trend_records(
                conn, station_id=station_id, limit=_HISTORY_SIZE, as_of=as_of,
            )
    except Exception as exc:
        logger.warning("trend_analysis.compute_trend: DB read failed — %s", exc)
        return _insufficient(0)

    return _compute_from_records(history)


def reset_history(*, station_id: str = _DEFAULT_STATION) -> None:
    """Delete all trend_history rows for this station. Used in testing."""
    try:
        with pooled_connection() as conn:
            delete_trend_records(conn, station_id=station_id)
    except Exception as exc:
        logger.warning("trend_analysis.reset_history: DB delete failed — %s", exc)


# ── Pure computation (DB-independent, fully testable) ─────────────────────────

def _compute_from_records(history: list[dict]) -> dict:
    """
    Derive rich trend signals from an ordered (oldest-first) record list.

    Pure function — deterministic, no side effects. compute_trend() and
    unit tests both call this directly.
    """
    n = len(history)
    if n < 2:
        return _insufficient(n)

    probs = [h["probability"] for h in history]

    # ── Exponentially-weighted probability trend ─────────────────────────────
    weights = [math.exp(0.5 * (i - (n - 1))) for i in range(n)]
    w_sum = sum(weights)

    w_mean_t = sum(w * i for i, w in enumerate(weights)) / w_sum
    w_mean_p = sum(w * p for w, p in zip(weights, probs)) / w_sum

    numerator = sum(
        w * (i - w_mean_t) * (p - w_mean_p)
        for i, (w, p) in enumerate(zip(weights, probs))
    )
    denominator = sum(w * (i - w_mean_t) ** 2 for i, w in enumerate(weights))
    slope = numerator / denominator if abs(denominator) > 1e-9 else 0.0

    weighted_delta = round(slope * (n - 1), 4)

    # ── Rate of change vs real elapsed time ──────────────────────────────────
    rate_per_hour = _compute_hourly_rate(history)

    # ── Risk trend label ──────────────────────────────────────────────────────
    if weighted_delta > _PROB_TREND_THRESHOLD:
        risk_trend = "increasing"
    elif weighted_delta < -_PROB_TREND_THRESHOLD:
        risk_trend = "decreasing"
    else:
        risk_trend = "stable"

    # ── Trend strength (0.0–1.0) ──────────────────────────────────────────────
    trend_strength = round(min(abs(weighted_delta) / 0.40, 1.0), 4)

    # ── Trend confidence: fraction of consecutive pairs in majority direction ─
    trend_confidence = _directional_consistency(probs)

    # ── Auxiliary signal trends ───────────────────────────────────────────────
    wl_trend = _scalar_trend(
        [h["water_level_ratio"] for h in history],
        _WL_TREND_THRESHOLD,
        ("rising", "falling", "stable"),
    )
    rf_trend = _scalar_trend(
        [h["rainfall_mm"] for h in history],
        _RAINFALL_TREND_THRESHOLD,
        ("intensifying", "easing", "stable"),
    )

    # ── Anomaly detection ─────────────────────────────────────────────────────
    anomaly_type = _detect_anomaly(probs)

    return {
        # Legacy keys preserved for backward compatibility
        "risk_delta_1h": weighted_delta,
        "risk_trend": risk_trend,
        "water_level_trend": wl_trend,
        "rainfall_trend": rf_trend,
        "data_points": n,
        # Enriched keys
        "risk_rate_per_hour": rate_per_hour,
        "trend_strength": trend_strength,
        "trend_confidence": trend_confidence,
        "anomaly_detected": anomaly_type is not None,
        "anomaly_type": anomaly_type,
    }


# ── Internal helpers (unchanged semantics) ────────────────────────────────────

def _insufficient(n: int) -> dict:
    return {
        "risk_delta_1h": 0.0,
        "risk_trend": "insufficient_data",
        "water_level_trend": "insufficient_data",
        "rainfall_trend": "insufficient_data",
        "data_points": n,
        "risk_rate_per_hour": 0.0,
        "trend_strength": 0.0,
        "trend_confidence": 0.0,
        "anomaly_detected": False,
        "anomaly_type": None,
    }


def _compute_hourly_rate(history: list[dict]) -> float:
    """Probability change rate per actual elapsed hour using stored timestamps."""
    try:
        t_old = datetime.fromisoformat(history[0]["timestamp_utc"])
        t_new = datetime.fromisoformat(history[-1]["timestamp_utc"])
        elapsed_hours = max((t_new - t_old).total_seconds() / 3600.0, _MIN_RATE_HOURS)
        delta = history[-1]["probability"] - history[0]["probability"]
        return round(delta / elapsed_hours, 4)
    except (KeyError, ValueError, TypeError):
        return 0.0


def _scalar_trend(
    values: list,
    threshold: float,
    labels: tuple[str, str, str],
) -> str:
    """
    Classify oldest→newest delta as labels[0]/labels[1]/labels[2] (up/down/stable).
    Returns "insufficient_data" if fewer than 2 non-None values exist.
    """
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "insufficient_data"
    delta = clean[-1] - clean[0]
    if delta > threshold:
        return labels[0]
    if delta < -threshold:
        return labels[1]
    return labels[2]


def _directional_consistency(probs: list[float]) -> float:
    """
    Fraction of consecutive pairs going in the majority direction.

    1.0 = all pairs move the same way.
    0.5 = half up half down (no clear trend).
    0.0 = perfectly alternating.
    """
    if len(probs) < 2:
        return 0.0
    deltas = [probs[i + 1] - probs[i] for i in range(len(probs) - 1)]
    positive = sum(1 for d in deltas if d > 0)
    negative = sum(1 for d in deltas if d < 0)
    majority = max(positive, negative)
    return round(majority / len(deltas), 4)


def _detect_anomaly(probs: list[float]) -> str | None:
    """
    Detect two anomaly patterns:

    spike:             Any single consecutive-pair delta >= SPIKE_THRESHOLD.
    slow_accumulation: All ACCUMULATION_STEPS most-recent values form a strict
                       monotone increasing sequence.

    Spike takes priority if both conditions hold.
    """
    if len(probs) < 2:
        return None

    for i in range(len(probs) - 1):
        if abs(probs[i + 1] - probs[i]) >= _SPIKE_THRESHOLD:
            return "spike"

    if len(probs) >= _ACCUMULATION_STEPS:
        tail = probs[-_ACCUMULATION_STEPS:]
        if all(tail[i + 1] > tail[i] for i in range(len(tail) - 1)):
            return "slow_accumulation"

    return None
