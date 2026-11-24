"""
History for the Riwayat page and the post charts.

- The decision log: one compact row per 15-minute refresh in ``realtime_snapshot_store`` (id
  'decision:<fetched_at_utc>'): the level the site showed, the layer that set it, the learned layer's
  flood chance and the daily model's. Rows before 24 Nov 2026 were rebuilt by
  scripts/backfill_decision_log.py ("source": "replay"); later ones are written live ("live").
- River posts: water level and Siaga status from the 15-minute history rows ('history:<fetched_at>').
- Satellite rain: the daily model's IMERG Early days (``daily_model.rain_summary``).

Reads are cached in memory for a few minutes, so a busy page does not hit Supabase each time. Nothing
here raises into a request: on a failure the part comes back empty.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from realtime_native import daily_features as dfe

logger = logging.getLogger("flood.history")

TABLE = "realtime_snapshot_store"
DECISION_PREFIX = "decision:"
HISTORY_PREFIX = "history:"
CACHE_SECONDS = 300
LEVEL_RANK = {"UNKNOWN": -1, "SAFE": 0, "PRE_ALERT": 1, "WARNING": 2, "DANGER": 3}
_lock = threading.Lock()
_cache: dict = {}


def _client():
    from db.supabase_client import get_supabase_client

    return get_supabase_client()


def _cached(key, loader):
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    value = loader()
    with _lock:
        _cache[key] = (now, value)
    return value


def _reset_cache_for_tests() -> None:
    with _lock:
        _cache.clear()


# ---------------------------------------------------------------- decision log

def compact_decision(result: dict, fetched_at: str, source: str = "live") -> dict:
    """The part of a /predict/realtime-native result the history keeps (~200 bytes)."""
    layer = result.get("decision_layer") or {}
    daily = result.get("daily_model") or {}
    decided = bool(layer.get("decided"))
    return {
        "t": fetched_at,
        "level": result.get("risk_level"),
        "layer": (result.get("decision") or {}).get("layer"),
        "chance": round(float(layer["score"]), 4) if decided and layer.get("score") is not None else None,
        "daily_p": daily.get("city_probability"),
        "lag": daily.get("lag_days"),
        "top": daily.get("top_kecamatan"),
        "source": source,
    }


def save_decisions_sync(rows: list[dict]) -> bool:
    """Upsert decision rows ({t, ...}); True on success. Never raises."""
    if not rows:
        return True
    try:
        payload = [{"id": f"{DECISION_PREFIX}{r['t']}", "snapshot": r, "fetched_at": r["t"]} for r in rows]
        for i in range(0, len(payload), 500):
            _client().table(TABLE).upsert(payload[i:i + 500]).execute()
        return True
    except Exception as exc:  # noqa: BLE001 - history is best-effort
        logger.warning("decision_log_save_failed error_type=%s error=%s", type(exc).__name__, exc)
        return False


def _select_since(prefix: str, columns: str, since: datetime) -> list[dict]:
    rows, offset = [], 0
    while True:
        res = (_client().table(TABLE).select(columns).like("id", f"{prefix}%")
               .gte("fetched_at", since.isoformat()).order("fetched_at").range(offset, offset + 999).execute())
        batch = res.data or []
        rows += batch
        if len(batch) < 1000:
            return rows
        offset += 1000


def load_decisions(days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    def load():
        try:
            return [r["snapshot"] for r in _select_since(DECISION_PREFIX, "fetched_at,snapshot", since)
                    if isinstance(r.get("snapshot"), dict)]
        except Exception as exc:  # noqa: BLE001
            logger.warning("decision_log_load_failed error_type=%s", type(exc).__name__)
            return []

    return _cached(("decisions", days), load)


def warning_periods(decisions: list[dict], min_level: str = "PRE_ALERT", gap_minutes: int = 45) -> list[dict]:
    """Runs of snapshots at or above ``min_level`` (a gap over ``gap_minutes`` ends a run), newest first."""
    periods, current = [], None
    floor, gap = LEVEL_RANK[min_level], pd.Timedelta(minutes=gap_minutes)
    for d in decisions:
        rank = LEVEL_RANK.get(d.get("level"), -1)
        t = pd.Timestamp(d["t"])
        if current and (rank < floor or t - current["_last"] > gap):
            periods.append(current)
            current = None
        if rank < floor:
            continue
        if current is None:
            current = {"start": d["t"], "end": d["t"], "_last": t, "peak_level": d["level"],
                       "peak_chance": d.get("chance"), "snapshots": 0}
        current["end"], current["_last"] = d["t"], t
        current["snapshots"] += 1
        if rank > LEVEL_RANK[current["peak_level"]]:
            current["peak_level"] = d["level"]
        if (d.get("chance") or 0) > (current["peak_chance"] or 0):
            current["peak_chance"] = d.get("chance")
    if current:
        periods.append(current)
    for p in periods:
        p.pop("_last", None)
    return list(reversed(periods))


# ---------------------------------------------------------------- river posts

def _post_rows(days: int) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    def load():
        try:
            return _select_since(HISTORY_PREFIX, "fetched_at,poskobanjir:snapshot->poskobanjir", since)
        except Exception as exc:  # noqa: BLE001
            logger.warning("post_history_load_failed error_type=%s", type(exc).__name__)
            return []

    return _cached(("posts", days), load)


def _num(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def post_series(name: str, days: int) -> dict:
    """Water level (cm) and Siaga band over time for one post, with its Siaga limits."""
    points, limits = [], {}
    for row in _post_rows(days):
        for p in row.get("poskobanjir") or []:
            if isinstance(p, dict) and (p.get("nama_pintu_air") or "").strip() == name.strip():
                level = dfe.status_level(p.get("status_siaga"))
                points.append({"t": row["fetched_at"], "cm": _num(p.get("tinggi_air")),
                               "status": None if math.isnan(level) else int(level)})
                limits = {k: _num(p.get(k)) for k in ("siaga3", "siaga2", "siaga1")}
                break
    return {"name": name, "days": days, "points": points, "limits": limits}


def posts_daily(days: int) -> dict:
    """Highest Siaga band (0 normal .. 3 Siaga 1) per post and WIB day."""
    out: dict = {}
    for row in _post_rows(days):
        day = pd.Timestamp(row["fetched_at"]).tz_convert("Asia/Jakarta").date().isoformat()
        for p in row.get("poskobanjir") or []:
            if not isinstance(p, dict) or _num(p.get("siaga1")) is None:
                continue  # pumps and posts without official limits
            level = dfe.status_level(p.get("status_siaga"))
            if math.isnan(level):
                continue
            name = (p.get("nama_pintu_air") or "").strip()
            per_day = out.setdefault(name, {})
            per_day[day] = max(per_day.get(day, 0), int(level))
    return out


# ---------------------------------------------------------------- page summary

def summary(days: int) -> dict:
    from realtime_native import daily_model

    decisions = load_decisions(days)
    return {
        "days": days,
        "decisions": decisions,
        "periods": warning_periods(decisions),
        "rain": daily_model.rain_summary(days),
        "posts_daily": posts_daily(min(days, 14)),
        "replayed_until": max((d["t"] for d in decisions if d.get("source") == "replay"), default=None),
    }


# ---------------------------------------------------------------- live logging

def log_decision(fetched_at: str) -> dict | None:
    """Run the live prediction once for the snapshot just saved, keep its compact row and pass the
    result to the Telegram alert. Called from the scheduler; never raises."""
    try:
        from realtime_native.inference import predict_realtime_native

        result = predict_realtime_native(persist_history=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("decision_log_predict_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None
    save_decisions_sync([compact_decision(result, fetched_at)])
    try:
        from services import telegram_alerts

        telegram_alerts.maybe_notify(result)
    except Exception as exc:  # noqa: BLE001
        logger.warning("telegram_alert_failed error_type=%s", type(exc).__name__)
    return result
