import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from filelock import FileLock
from filelock import Timeout as FileLockTimeout
from psycopg2.extras import Json

from api.observability import FEATURE_HISTORY_DB_FAILURE_TOTAL
from services.bmkg_filter import filter_jakarta_bmkg_alerts
from services.bmkg_rainfall_context import get_recent_daily_rainfall
from services.constants import (
    BMKG_CERTAINTY_WEIGHTS,
    BMKG_SEVERITY_WEIGHTS,
    BMKG_URGENCY_WEIGHTS,
)
from utils.paths import DEFAULT_REALTIME_SNAPSHOT, PROCESSED_DATA_DIR
from db.psycopg2_connection import pooled_connection

logger = logging.getLogger(__name__)


REALTIME_NATIVE_HISTORY_PATH = PROCESSED_DATA_DIR / "realtime_feature_history.csv"
REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH = PROCESSED_DATA_DIR / "realtime_native_training_bootstrap.csv"

REALTIME_NATIVE_FEATURES = [
    "rainfall_mm",
    "rainfall_3h_proxy_mm",
    "rainfall_lag_1",
    "rainfall_lag_2",
    "rainfall_roll3_mean",
    "humidity_pct",
    "temperature_c",
    "bmkg_severity_score",
    "bmkg_certainty_score",
    "bmkg_urgency_score",
    "bmkg_weighted_score",
    "water_level_ratio",
    "water_level_lag_1",
    "water_level_delta",
    "hydro_meteorological_index",
    "monsoon_season",
]


@dataclass(frozen=True)
class RealtimeNativeFeatures:
    frame: pd.DataFrame
    diagnostics: dict


def _safe_float(value, default=0.0):
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(value):
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _bmkg_category_scores_from_alerts(alerts):
    severity_map = BMKG_SEVERITY_WEIGHTS
    certainty_map = BMKG_CERTAINTY_WEIGHTS
    urgency_map = BMKG_URGENCY_WEIGHTS

    if not alerts:
        return {
            "bmkg_severity_score": 0.0,
            "bmkg_certainty_score": 0.0,
            "bmkg_urgency_score": 0.0,
            "bmkg_weighted_score": 0.0,
        }

    severity_scores = []
    certainty_scores = []
    urgency_scores = []
    weighted_scores = []
    for alert in alerts:
        severity = severity_map.get((alert.get("severity") or "").lower(), 0.4)
        certainty = certainty_map.get((alert.get("certainty") or "").lower(), 0.4)
        urgency = urgency_map.get((alert.get("urgency") or "").lower(), 0.5)
        severity_scores.append(severity)
        certainty_scores.append(certainty)
        urgency_scores.append(urgency)
        weighted_scores.append(severity * certainty * urgency)

    return {
        "bmkg_severity_score": max(severity_scores),
        "bmkg_certainty_score": max(certainty_scores),
        "bmkg_urgency_score": max(urgency_scores),
        "bmkg_weighted_score": min(sum(weighted_scores), 1.0),
    }


def _bmkg_category_scores_from_rainfall(rainfall_mm, rainfall_recent_mm):
    severity = 0.25
    if rainfall_mm >= 80:
        severity = 1.0
    elif rainfall_mm >= 50:
        severity = 0.8
    elif rainfall_mm >= 25:
        severity = 0.5

    certainty = min(max(rainfall_recent_mm / max(rainfall_mm, 1.0), 0.2), 1.0)
    urgency = 1.0 if rainfall_mm >= 50 else 0.75 if rainfall_mm >= 25 else 0.4
    weighted = severity * certainty * urgency
    return {
        "bmkg_severity_score": round(severity, 4),
        "bmkg_certainty_score": round(certainty, 4),
        "bmkg_urgency_score": round(urgency, 4),
        "bmkg_weighted_score": round(weighted, 4),
    }


_STEP_DELTA_MAX_CM = 300.0  # maximum physically plausible change per 15-min interval


def _validate_step_delta(record: dict) -> dict:
    """
    Flag records whose water level changed by more than _STEP_DELTA_MAX_CM since
    the previous reading. Sets use_delta_in_model=False when flagged so lag/delta
    features are suppressed for this station.
    """
    try:
        cur = _safe_float(record.get("tinggi_air"))
        prev_raw = (
            record.get("tinggi_air_sebelumnya")
            or record.get("tinggi_air_prev")
            or record.get("previous_tinggi_air")
        )
        if prev_raw is None or prev_raw == "":
            record["use_delta_in_model"] = True
            return record
        prev = _safe_float(prev_raw)
        delta = cur - prev
        if abs(delta) > _STEP_DELTA_MAX_CM:
            record["step_delta_flag"] = (
                f"SPIKE: delta {delta:+.0f}cm exceeds threshold {_STEP_DELTA_MAX_CM:.0f}cm"
            )
            record["step_delta_direction"] = "rise" if delta > 0 else "drop"
            record["use_delta_in_model"] = False
            return record
    except (TypeError, ValueError):
        pass
    record["use_delta_in_model"] = True
    return record


def _is_calibrated_station(record: dict) -> bool:
    """
    Return False for stations with placeholder thresholds (siaga1=siaga2=siaga3 equal).
    All-identical thresholds mean the station was never operationally calibrated;
    including them produces near-zero ratios that bias ML toward SAFE.
    Stations with distinct threshold values (even high ones) are kept.
    """
    try:
        s1 = int(float(record.get("siaga1") or 0))
        s2 = int(float(record.get("siaga2") or 0))
        s3 = int(float(record.get("siaga3") or 0))
        if s1 == 0 and s2 == 0 and s3 == 0:
            return False  # No thresholds at all
        if s1 == s2 == s3 and s1 > 0:
            return False  # All identical — placeholder (never operationally set)
        return True
    except (TypeError, ValueError):
        return True


def _valid_jakarta_lat(raw) -> "float | None":
    """Return lat only if it falls within Jakarta admin bounds, else None."""
    try:
        v = float(raw or 0)
        return v if -6.6 <= v <= -5.8 else None
    except (TypeError, ValueError):
        return None


def _valid_jakarta_lon(raw) -> "float | None":
    """Return lon only if it falls within Jakarta admin bounds, else None."""
    try:
        v = float(raw or 0)
        return v if 106.4 <= v <= 107.2 else None
    except (TypeError, ValueError):
        return None


def _is_pump_station(record: dict) -> bool:
    """
    Return True for pumping-infrastructure stations (name starts with "Pompa").
    Their siaga thresholds are OPERATIONAL thresholds for the pump machinery,
    not public flood-warning thresholds. Including them inflates water_level_ratio
    because a pump running above capacity looks like 140%+ flood when it may just
    be tidal backflow or normal pump activation. Canal/gate stations (P.A., P.S.)
    use flood-warning thresholds and are the correct basis for this feature.
    Pump station readings are still captured in diagnostics for visibility.
    """
    name = str(
        record.get("nama_pintu_air") or record.get("wilayah") or ""
    ).strip().upper()
    return name.startswith("POMPA")


def _water_level_ratio_from_records(records):
    best_ratio = 0.0
    for record in (records or []):
        current_level = _safe_float(record.get("tinggi_air"))
        # Skip stations with non-standard datum (negative water levels).
        if current_level < 0:
            continue
        # Skip uncalibrated stations — placeholder thresholds bias ML toward SAFE.
        if not _is_calibrated_station(record):
            continue
        # Skip pump stations — their thresholds are operational (pump capacity),
        # not flood-warning thresholds. One overloaded coastal pump can otherwise
        # push water_level_ratio to 140%+ while all canal stations read normal.
        if _is_pump_station(record):
            continue
        thresholds = [
            _safe_float(record.get("siaga1")),
            _safe_float(record.get("siaga2")),
            _safe_float(record.get("siaga3")),
            _safe_float(record.get("siaga4")),
        ]
        thresholds = [threshold for threshold in thresholds if threshold > 0]
        if not thresholds:
            continue
        ratio = current_level / max(thresholds)
        best_ratio = max(best_ratio, ratio)
    return min(best_ratio, 1.5)


def _get_excluded_stations(records) -> list[dict]:
    """Return stations excluded from model features due to non-standard datum."""
    excluded = []
    for record in (records or []):
        current_level = _safe_float(record.get("tinggi_air"))
        if current_level < 0:
            excluded.append({
                "nama": str(record.get("nama_pintu_air") or record.get("wilayah") or "unknown"),
                "tinggi_air": current_level,
                "exclusion_reason": "non_standard_datum — values outside model training range",
            })
    return excluded


def _load_history(path=REALTIME_NATIVE_HISTORY_PATH):
    if Path(path) != REALTIME_NATIVE_HISTORY_PATH:
        if not Path(path).exists():
            return pd.DataFrame()
        return pd.read_csv(path)
    # Allow operators to disable the history DB read entirely (e.g. when the
    # database is unreachable) so it never consumes the reasoning-stage budget.
    # Still fall back to the local CSV so temporal features aren't zeroed out.
    if os.getenv("FEATURE_HISTORY_DB_ENABLED", "true").lower() == "false":
        if REALTIME_NATIVE_HISTORY_PATH.exists():
            try:
                return pd.read_csv(REALTIME_NATIVE_HISTORY_PATH)
            except Exception:
                pass
        return pd.DataFrame()
    try:
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT observed_at, features
                      FROM realtime_feature_history
                     ORDER BY observed_at DESC, id DESC
                     LIMIT 2000
                    """
                )
                rows = cur.fetchall()
            conn.commit()
    except Exception as exc:
        FEATURE_HISTORY_DB_FAILURE_TOTAL.labels("load").inc()
        logger.warning("feature_builder._load_history: DB read failed - %s", exc)
        # Fallback to local CSV so temporal features survive DB outage
        if REALTIME_NATIVE_HISTORY_PATH.exists():
            try:
                return pd.read_csv(REALTIME_NATIVE_HISTORY_PATH)
            except Exception:
                pass
        return pd.DataFrame()

    records: list[dict] = []
    for observed_at, features in reversed(rows):
        payload = dict(features or {})
        payload.setdefault("timestamp", observed_at.isoformat())
        records.append(payload)
    return pd.DataFrame(records)


def _filter_history_as_of(history: pd.DataFrame, as_of=None) -> pd.DataFrame:
    if as_of is None or history.empty or "timestamp" not in history.columns:
        return history

    timestamps = pd.to_datetime(history["timestamp"], errors="coerce", utc=True)
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    mask = timestamps.notna() & (timestamps <= cutoff)
    return history.loc[mask].reset_index(drop=True)


def _append_history(row, path=REALTIME_NATIVE_HISTORY_PATH):
    if Path(path) != REALTIME_NATIVE_HISTORY_PATH:
        path = Path(path)
        lock_path = path.with_suffix(".lock")
        tmp_path = path.with_suffix(".tmp")
        try:
            with FileLock(lock_path, timeout=10):
                history = _load_history(path)
                updated = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
                updated.tail(2000).to_csv(tmp_path, index=False)
                os.replace(tmp_path, path)
        except FileLockTimeout:
            logger.warning(
                "feature_builder._append_history: lock timeout after 10s - write skipped"
            )
        return
    # Skip the history DB write when disabled (e.g. DB unreachable) so a write
    # timeout never blocks the pipeline.
    if os.getenv("FEATURE_HISTORY_DB_ENABLED", "true").lower() == "false":
        return
    try:
        observed_at = _parse_timestamp(row.get("timestamp"))
        features = {key: value for key, value in row.items() if key != "timestamp"}
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO realtime_feature_history (observed_at, features)
                    VALUES (%s, %s)
                    """,
                    (observed_at, Json(features)),
                )
                cur.execute(
                    """
                    DELETE FROM realtime_feature_history
                     WHERE id NOT IN (
                         SELECT id
                           FROM realtime_feature_history
                          ORDER BY observed_at DESC, id DESC
                          LIMIT 2000
                     )
                    """
                )
            conn.commit()
    except Exception as exc:
        FEATURE_HISTORY_DB_FAILURE_TOTAL.labels("append").inc()
        logger.warning("feature_builder._append_history: DB write failed - %s", exc)


def _add_temporal_columns(current_row, history):
    if history.empty:
        history = pd.DataFrame(columns=["rainfall_mm", "water_level_ratio"])

    rainfall_history = history["rainfall_mm"].tolist() if "rainfall_mm" in history.columns else []
    water_history = history["water_level_ratio"].tolist() if "water_level_ratio" in history.columns else []

    rainfall_lag_1 = rainfall_history[-1] if len(rainfall_history) >= 1 else current_row["rainfall_3h_proxy_mm"]
    rainfall_lag_2 = rainfall_history[-2] if len(rainfall_history) >= 2 else rainfall_lag_1
    rolling_values = (rainfall_history[-2:] if len(rainfall_history) >= 2 else rainfall_history) + [current_row["rainfall_mm"]]
    rainfall_roll3_mean = sum(rolling_values) / max(len(rolling_values), 1)

    water_level_lag_1 = water_history[-1] if len(water_history) >= 1 else current_row["water_level_ratio"]

    # Guard: if the lag comes from a stale "broken-scraper" period (consecutive 0.0s)
    # the computed delta would be artificially huge and trigger false OOD.
    # Reset lag_1 to current so delta = 0 rather than poisoning the feature vector.
    _MAX_REALISTIC_DELTA = 0.40
    _STALE_LAG_THRESHOLD = 0.05
    current_wlr = current_row["water_level_ratio"]
    if (
        water_level_lag_1 < _STALE_LAG_THRESHOLD
        and current_wlr > _STALE_LAG_THRESHOLD
        and abs(current_wlr - water_level_lag_1) > _MAX_REALISTIC_DELTA
    ):
        water_level_lag_1 = current_wlr

    water_level_delta = current_wlr - water_level_lag_1
    # Clamp delta to physically realistic range for 15-min interval
    water_level_delta = max(-_MAX_REALISTIC_DELTA, min(_MAX_REALISTIC_DELTA, water_level_delta))

    current_row.update(
        {
            "rainfall_lag_1": rainfall_lag_1,
            "rainfall_lag_2": rainfall_lag_2,
            "rainfall_roll3_mean": rainfall_roll3_mean,
            "water_level_lag_1": water_level_lag_1,
            "water_level_delta": water_level_delta,
        }
    )
    return current_row


def _snapshot_history_trend_state(history, current_row):
    if history.empty:
        return {
            "recent_probabilities": [],
            "risk_trend": "insufficient_data",
            "water_level_trend": "insufficient_data",
            "rainfall_trend": "insufficient_data",
            "data_points": 0,
            "risk_delta_1h": 0.0,
            "risk_rate_per_hour": 0.0,
            "trend_strength": 0.0,
            "trend_confidence": 0.0,
            "anomaly_detected": False,
            "anomaly_type": None,
            "trend_basis": "composite_hydro_rainfall",
        }

    recent = history.tail(4).copy()
    current = pd.DataFrame(
        [
            {
                "timestamp": current_row["timestamp"],
                "rainfall_mm": current_row["rainfall_mm"],
                "water_level_ratio": current_row["water_level_ratio"],
            }
        ]
    )
    series = pd.concat([recent, current], ignore_index=True, sort=False)
    series["rainfall_mm"] = pd.to_numeric(series.get("rainfall_mm"), errors="coerce").fillna(0.0)
    series["water_level_ratio"] = pd.to_numeric(
        series.get("water_level_ratio"), errors="coerce"
    ).fillna(0.0)
    composite = (
        (series["rainfall_mm"] / 40.0).clip(lower=0.0, upper=1.0) * 0.55
        + (series["water_level_ratio"] / 0.85).clip(lower=0.0, upper=1.0) * 0.45
    ).round(4)
    recent_scores = composite.tail(3).tolist()

    if len(composite) < 2:
        return {
            "recent_probabilities": recent_scores,
            "risk_trend": "insufficient_data",
            "water_level_trend": "insufficient_data",
            "rainfall_trend": "insufficient_data",
            "data_points": int(len(history)),
            "risk_delta_1h": 0.0,
            "risk_rate_per_hour": 0.0,
            "trend_strength": 0.0,
            "trend_confidence": 0.0,
            "anomaly_detected": False,
            "anomaly_type": None,
            "trend_basis": "composite_hydro_rainfall",
        }

    delta = float(composite.iloc[-1] - composite.iloc[0])
    risk_trend = "stable"
    if delta > 0.08:
        risk_trend = "increasing"
    elif delta < -0.08:
        risk_trend = "decreasing"

    deltas = [b - a for a, b in zip(composite.tolist()[:-1], composite.tolist()[1:])]
    positive = sum(1 for value in deltas if value > 0)
    negative = sum(1 for value in deltas if value < 0)
    majority = max(positive, negative, 0)
    confidence = round(majority / max(len(deltas), 1), 4)

    rainfall_delta = float(series["rainfall_mm"].iloc[-1] - series["rainfall_mm"].iloc[0])
    rainfall_trend = "stable"
    if rainfall_delta > 4.0:
        rainfall_trend = "intensifying"
    elif rainfall_delta < -4.0:
        rainfall_trend = "easing"

    water_delta = float(series["water_level_ratio"].iloc[-1] - series["water_level_ratio"].iloc[0])
    water_trend = "stable"
    if water_delta > 0.04:
        water_trend = "rising"
    elif water_delta < -0.04:
        water_trend = "falling"

    anomaly_type = None
    if any(abs(value) >= 0.20 for value in deltas):
        anomaly_type = "spike"
    elif len(recent_scores) >= 3 and all(
        recent_scores[i + 1] > recent_scores[i] for i in range(len(recent_scores) - 1)
    ):
        anomaly_type = "slow_accumulation"

    return {
        "recent_probabilities": recent_scores,
        "risk_trend": risk_trend,
        "water_level_trend": water_trend,
        "rainfall_trend": rainfall_trend,
        "data_points": int(len(history)),
        # C9 fix: risk_delta_1h uses the same composite score delta as risk_trend
        # so they can never contradict each other.
        "risk_delta_1h": round(delta, 4),
        "risk_rate_per_hour": 0.0,
        "trend_strength": round(min(abs(delta) / 0.40, 1.0), 4),
        "trend_confidence": confidence,
        "anomaly_detected": anomaly_type is not None,
        "anomaly_type": anomaly_type,
        "trend_basis": "composite_hydro_rainfall",
    }


def _is_history_stale(history: "pd.DataFrame", now: datetime, stale_hours: float = 24.0) -> bool:
    """Return True when the most recent history entry is older than stale_hours."""
    if history.empty or "timestamp" not in history.columns:
        return True
    try:
        last_ts = pd.to_datetime(history["timestamp"].iloc[-1], utc=True)
        now_ts = pd.Timestamp(now).tz_convert("UTC") if now.tzinfo else pd.Timestamp(now, tz="UTC")
        return (now_ts - last_ts).total_seconds() / 3600 > stale_hours
    except Exception:
        return True


def build_realtime_native_features_from_snapshot(snapshot, persist_history=True, *, as_of=None):
    """
    Build the realtime-native feature frame from a snapshot dict.

    ``persist_history=False`` activates *replay mode*: the realtime feature
    history CSV is NOT appended to, so lag features for identical replays
    remain identical. ``as_of`` (optional datetime) is forwarded to
    ``compute_trend`` so the embedded trend_state also reads a fixed window
    rather than current wall-clock state.
    """
    timestamp = _parse_timestamp(snapshot.get("fetched_at_utc"))
    weather = snapshot.get("openweather", {})
    main_weather = weather.get("main", {})
    rain_data = weather.get("rain", {})
    poskobanjir_records = snapshot.get("poskobanjir") or []
    raw_alerts = snapshot.get("bmkg_alerts") or []
    alerts = filter_jakarta_bmkg_alerts(raw_alerts)

    rainfall_mm = max(
        _safe_float(rain_data.get("1h")),
        _safe_float(rain_data.get("3h")) / 3 if rain_data.get("3h") is not None else 0.0,
    )
    rainfall_3h_proxy_mm = max(_safe_float(rain_data.get("3h")), rainfall_mm * 3)
    humidity_pct = _safe_float(main_weather.get("humidity"), 75.0)
    temperature_c = _safe_float(main_weather.get("temp"), 30.0)
    # Step-delta spike detection — annotate records before any feature use.
    # Stations with spikes get use_delta_in_model=False; their current level
    # is still used but delta/lag features are suppressed to avoid contamination.
    poskobanjir_records = [_validate_step_delta(dict(r)) for r in poskobanjir_records]
    spike_flagged = [
        {
            "nama": str(r.get("nama_pintu_air") or r.get("wilayah") or "unknown"),
            "delta_cm": abs(
                _safe_float(r.get("tinggi_air"))
                - _safe_float(
                    r.get("tinggi_air_sebelumnya")
                    or r.get("tinggi_air_prev")
                    or r.get("previous_tinggi_air")
                )
            ),
            "direction": r.get("step_delta_direction", "unknown"),
        }
        for r in poskobanjir_records
        if not r.get("use_delta_in_model", True)
    ]

    excluded_stations = _get_excluded_stations(poskobanjir_records)
    valid_records = [r for r in poskobanjir_records if _safe_float(r.get("tinggi_air")) >= 0]
    # Count uncalibrated stations for data quality reporting
    uncalibrated_count = sum(
        1 for r in valid_records if not _is_calibrated_station(r)
    )
    # Pump stations excluded from ratio (operational thresholds, not flood thresholds)
    pump_stations_excluded = [
        {
            "nama": str(r.get("nama_pintu_air") or r.get("wilayah") or "unknown"),
            "tinggi_air": _safe_float(r.get("tinggi_air")),
        }
        for r in valid_records
        if _is_pump_station(r) and _is_calibrated_station(r)
    ]
    water_level_ratio = _water_level_ratio_from_records(poskobanjir_records)
    bmkg_scores = _bmkg_category_scores_from_alerts(alerts)

    current_row = {
        "timestamp": timestamp.isoformat(),
        "rainfall_mm": rainfall_mm,
        "rainfall_3h_proxy_mm": rainfall_3h_proxy_mm,
        "humidity_pct": humidity_pct,
        "temperature_c": temperature_c,
        "water_level_ratio": water_level_ratio,
        "monsoon_season": int(timestamp.month in [11, 12, 1, 2, 3]),
        **bmkg_scores,
    }

    history = _filter_history_as_of(_load_history(), as_of=as_of)
    current_row = _add_temporal_columns(current_row, history)

    # ── BMKG daily rainfall context ─────────────────────────────────────────
    # When OpenWeather reports 0mm and feature history is stale, seed lag
    # features from BMKG daily totals so the model sees recent precipitation
    # that explains rising TMA levels (time-lag between rain and river rise).
    bmkg_daily_ctx: dict = {}
    history_stale = _is_history_stale(history, timestamp)
    try:
        bmkg_daily_ctx = get_recent_daily_rainfall(reference_date=timestamp.date())
        if rainfall_mm == 0.0 and history_stale and bmkg_daily_ctx.get("data_available"):
            _bmkg_avg = bmkg_daily_ctx.get("last_7d_avg_mm") or 0.0
            if _bmkg_avg > 0.0:
                _hourly_seed = round(_bmkg_avg / 24.0, 3)
                current_row["rainfall_lag_1"] = max(
                    current_row.get("rainfall_lag_1", 0.0), _hourly_seed
                )
                current_row["rainfall_lag_2"] = max(
                    current_row.get("rainfall_lag_2", 0.0), _hourly_seed
                )
                rolling = [
                    current_row["rainfall_mm"],
                    current_row["rainfall_lag_1"],
                    current_row["rainfall_lag_2"],
                ]
                current_row["rainfall_roll3_mean"] = round(sum(rolling) / len(rolling), 3)
    except Exception as _bmkg_exc:
        logger.debug("bmkg_daily_context_failed (non-fatal): %s", _bmkg_exc)

    current_row["hydro_meteorological_index"] = (
        current_row["rainfall_roll3_mean"] * (humidity_pct / 100.0) * (1 + water_level_ratio)
    )

    # Momentum features computed from past data only (no leakage).
    # rainfall_lag_1 is 0-history fallback set by _add_temporal_columns.
    _rf_lag1 = current_row.get("rainfall_lag_1", current_row["rainfall_mm"])
    _rf_lag2 = current_row.get("rainfall_lag_2", _rf_lag1)
    trend_state = _snapshot_history_trend_state(history, current_row)
    diagnostics = {
        "history_rows_used": int(len(history)),
        "history_stale": history_stale,
        "bmkg_daily_context": bmkg_daily_ctx,
        "temporal_features_ready": len(history) >= 2,
        "bmkg_source": "observed_alerts" if alerts else "no_alert",
        "bmkg_alerts_total": len(raw_alerts),
        "bmkg_alerts_used": len(alerts),
        "bmkg_alerts_filtered_out": max(len(raw_alerts) - len(alerts), 0),
        "water_level_records": len(poskobanjir_records),
        "data_quality_report": {
            "excluded_stations": excluded_stations,
            "exclusion_reason": "Non-standard datum — values outside model training range",
            "stations_used_in_model": len(valid_records),
            "stations_total": len(poskobanjir_records),
            # Spike detection results (step-delta > 300cm per 15-min interval)
            "spike_flagged_stations": spike_flagged,
            # Stations with placeholder thresholds excluded from water_level_ratio
            "uncalibrated_stations_excluded_from_ratio": uncalibrated_count,
            # Pump stations excluded from ratio (operational, not flood-warning thresholds)
            "pump_stations_excluded_from_ratio": pump_stations_excluded,
        },
        # Momentum scalars (top-level for direct diagnostics consumers).
        "rainfall_trend_mm_h": round(current_row["rainfall_mm"] - _rf_lag1, 4),
        "rainfall_acc_3h": round(current_row.get("rainfall_3h_proxy_mm", 0.0), 4),
        "rainfall_acc_6h": round(current_row["rainfall_mm"] + _rf_lag1 + _rf_lag2, 4),
        "water_level_trend": round(current_row.get("water_level_delta", 0.0), 4),
        "trend_source": "realtime_feature_history",
        # Real per-station DSDADKI readings — sorted by siaga ratio descending.
        # Includes all calibrated, non-pump stations with positive siaga1 threshold.
        # status_siaga is the raw string from DSDADKI ("Siaga 3", "Normal", etc.).
        "stations_summary": sorted(
            [
                {
                    "nama": str(r.get("nama_pintu_air") or r.get("wilayah") or ""),
                    "lokasi": str(r.get("lokasi") or ""),
                    "wilayah": str(r.get("file_export") or ""),
                    "tinggi_air": _safe_float(r.get("tinggi_air")),
                    "siaga1": _safe_float(r.get("siaga1")),
                    "siaga2": _safe_float(r.get("siaga2")),
                    "siaga3": _safe_float(r.get("siaga3")),
                    "ratio": round(
                        _safe_float(r.get("tinggi_air")) / max(_safe_float(r.get("siaga1")), 1),
                        3,
                    ),
                    "status_siaga": str(r.get("status_siaga") or "Normal"),
                    # Validated coordinates — None when outside Jakarta bounds or zero
                    "lat": _valid_jakarta_lat(r.get("latitude")),
                    "lon": _valid_jakarta_lon(r.get("longitude")),
                }
                for r in valid_records
                if _is_calibrated_station(r)
                and not _is_pump_station(r)
                and _safe_float(r.get("siaga1")) > 0
            ],
            key=lambda x: x["ratio"],
            reverse=True,
        )[:20],
        "trend_state": {
            **trend_state,
            "rainfall_acc_3h": round(current_row.get("rainfall_3h_proxy_mm", 0.0), 4),
            "rainfall_trend_mm_h": round(current_row["rainfall_mm"] - _rf_lag1, 4),
            "water_level_delta_cur": round(current_row.get("water_level_delta", 0.0), 4),
        },
    }

    if persist_history:
        _append_history(
            {
                "timestamp": current_row["timestamp"],
                "rainfall_mm": current_row["rainfall_mm"],
                "water_level_ratio": current_row["water_level_ratio"],
            }
        )

    feature_row = {name: current_row[name] for name in REALTIME_NATIVE_FEATURES}
    return RealtimeNativeFeatures(frame=pd.DataFrame([feature_row]), diagnostics=diagnostics)


def build_realtime_native_features_from_file(
    snapshot_path=DEFAULT_REALTIME_SNAPSHOT,
    persist_history=True,
    *,
    as_of=None,
):
    path = Path(snapshot_path)
    if not path.exists():
        # Local file missing — try Supabase cached snapshot before giving up.
        # This handles fresh clones and Railway ephemeral-filesystem restarts before
        # the first scheduled refresh completes.
        try:
            from db.snapshot_repository import _load_latest_snapshot_sync
            cached = _load_latest_snapshot_sync()
            if cached and isinstance(cached, dict) and cached.get("fetched_at_utc"):
                logger.info(
                    "feature_builder: local snapshot missing, using Supabase cache "
                    "(fetched_at=%s)", cached.get("fetched_at_utc"),
                )
                return build_realtime_native_features_from_snapshot(
                    cached, persist_history=persist_history, as_of=as_of,
                )
        except Exception as _supabase_exc:
            logger.warning("feature_builder: Supabase fallback failed — %s", _supabase_exc)
        raise FileNotFoundError(f"Snapshot not found: {snapshot_path}")
    with open(snapshot_path, "r", encoding="utf-8") as file:
        snapshot = json.load(file)
    return build_realtime_native_features_from_snapshot(
        snapshot, persist_history=persist_history, as_of=as_of,
    )


def build_bootstrap_training_dataset(
    input_path=PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv",
    output_path=REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
):
    df = pd.read_csv(input_path).copy()
    df["timestamp"] = pd.to_datetime(
        df["year"].astype(int).astype(str) + "-" + df["month"].astype(int).astype(str) + "-01",
        errors="coerce",
    )
    df = df.sort_values(["jakarta_region", "name_3", "timestamp"]).reset_index(drop=True)

    # Bootstrap features: transparan bahwa beberapa field adalah proxy sampai histori realtime observasional tersedia.
    df["rainfall_mm"] = pd.to_numeric(df["max_rainfall"], errors="coerce")
    df["rainfall_3h_proxy_mm"] = df["rainfall_mm"] * 1.8
    df["humidity_pct"] = (
        pd.to_numeric(df["soil_moisture"], errors="coerce") * 1.75
        + pd.to_numeric(df["avg_rainfall"], errors="coerce") * 0.18
    ).clip(45, 100)
    df["temperature_c"] = pd.to_numeric(
        df["avg_temperature"] if "avg_temperature" in df.columns else pd.Series(dtype=float),
        errors="coerce",
    ).fillna(28.5)

    rainfall_recent = pd.to_numeric(df["avg_rainfall"], errors="coerce")
    bmkg_proxy = df.apply(
        lambda row: _bmkg_category_scores_from_rainfall(
            rainfall_mm=_safe_float(row["rainfall_mm"]),
            rainfall_recent_mm=_safe_float(row["avg_rainfall"]),
        ),
        axis=1,
    )
    bmkg_proxy_df = pd.DataFrame(list(bmkg_proxy))
    df = pd.concat([df, bmkg_proxy_df], axis=1)

    water_level_ratio = (
        pd.to_numeric(df["max_rainfall"], errors="coerce") / pd.to_numeric(df["max_rainfall"], errors="coerce").quantile(0.95)
    ).clip(0, 1.5)
    df["water_level_ratio"] = water_level_ratio

    group_keys = ["jakarta_region", "name_3"]
    df["rainfall_lag_1"] = df.groupby(group_keys)["rainfall_mm"].shift(1)
    df["rainfall_lag_2"] = df.groupby(group_keys)["rainfall_mm"].shift(2)
    df["rainfall_roll3_mean"] = (
        df.groupby(group_keys)["rainfall_mm"]
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=group_keys, drop=True)
    )
    df["water_level_lag_1"] = df.groupby(group_keys)["water_level_ratio"].shift(1)
    df["water_level_delta"] = df["water_level_ratio"] - df["water_level_lag_1"]
    df["hydro_meteorological_index"] = (
        df["rainfall_roll3_mean"] * (df["humidity_pct"] / 100.0) * (1 + df["water_level_ratio"])
    )
    df["monsoon_season"] = df["month"].astype(int).isin([11, 12, 1, 2, 3]).astype(int)

    df["rainfall_lag_1"] = df["rainfall_lag_1"].fillna(df["rainfall_mm"])
    df["rainfall_lag_2"] = df["rainfall_lag_2"].fillna(df["rainfall_lag_1"])
    df["water_level_lag_1"] = df["water_level_lag_1"].fillna(df["water_level_ratio"])
    df["water_level_delta"] = df["water_level_delta"].fillna(0.0)

    df["feature_provenance"] = "bootstrap_proxy"

    selected_columns = [
        "timestamp",
        "jakarta_region",
        "name_3",
        *REALTIME_NATIVE_FEATURES,
        "banjir",
        "feature_provenance",
    ]
    output_df = df[selected_columns]
    output_df.to_csv(output_path, index=False)
    return output_df
