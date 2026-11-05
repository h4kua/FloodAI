"""
Supabase repository for the latest realtime ingestion snapshot.

Backs the ``realtime_snapshot_store`` table (migration 030). The dashboard reads
the latest snapshot from here so it survives Railway's ephemeral filesystem; the
periodic refresh job upserts it. Each saved snapshot also leaves a compact
history row (id 'history:<fetched_at_utc>') for evaluation and later retraining.

The supabase-py client is synchronous, so the async public API wraps each call in
``asyncio.to_thread`` (no sync/async mixing on the event loop). Sync siblings are
exposed for callers already running in a worker thread (e.g. the dashboard, which
renders inside run_in_threadpool).

Neither function raises — failures are logged and surfaced as ``False`` / ``None``.
"""

from __future__ import annotations

import asyncio
import logging

from db.supabase_client import get_supabase_client

logger = logging.getLogger("flood.snapshot_repository")

_TABLE = "realtime_snapshot_store"
_LATEST_ID = "latest"
# History rows share the table (the anon key may already insert there) under
# id 'history:<fetched_at_utc>', so re-saving the same snapshot is a no-op upsert.
_HISTORY_PREFIX = "history:"
# Per-post fields kept in history; the rest (CCTV links, coordinates, export
# labels) is static and makes up most of the 37 KB snapshot.
_POST_FIELDS = (
    "kode_stasiun", "id_pintu_air", "nama_pintu_air", "lokasi", "tanggal",
    "tinggi_air", "siaga1", "siaga2", "siaga3", "siaga4", "status_siaga", "record_status",
)
_OPENWEATHER_FIELDS = ("dt", "main", "wind", "clouds", "rain", "weather")
_SNAPSHOT_FIELDS = (
    "fetched_at_utc", "summary", "bmkg_alerts", "bmkg_daily_rainfall",
    "bmkg_forecast", "source_attribution",
)


def _save_snapshot_sync(snapshot: dict) -> bool:
    """Upsert id='latest'. Returns True on success, False on any failure."""
    if not isinstance(snapshot, dict):
        logger.warning("snapshot_save_rejected reason=not_a_dict type=%s", type(snapshot).__name__)
        return False
    fetched_at = snapshot.get("fetched_at_utc")
    if not fetched_at:
        logger.warning("snapshot_save_rejected reason=missing_fetched_at_utc")
        return False
    try:
        client = get_supabase_client()
        client.table(_TABLE).upsert(
            {
                "id": _LATEST_ID,
                "snapshot": snapshot,
                "fetched_at": fetched_at,
            }
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("snapshot_save_failed error_type=%s error=%s", type(exc).__name__, exc)
        return False


def _load_latest_snapshot_sync() -> dict | None:
    """Return the latest snapshot dict, or None when absent / on any failure."""
    try:
        client = get_supabase_client()
        result = (
            client.table(_TABLE)
            .select("snapshot")
            .eq("id", _LATEST_ID)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None
        snapshot = rows[0].get("snapshot")
        return snapshot if isinstance(snapshot, dict) else None
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("snapshot_load_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def compact_for_history(snapshot: dict) -> dict:
    """The observations needed to rebuild model features later, about 8 KB a row."""
    compact = {key: snapshot.get(key) for key in _SNAPSHOT_FIELDS if key in snapshot}
    weather = snapshot.get("openweather")
    if isinstance(weather, dict):
        compact["openweather"] = {key: weather[key] for key in _OPENWEATHER_FIELDS if key in weather}
    posts = snapshot.get("poskobanjir")
    if isinstance(posts, list):
        compact["poskobanjir"] = [
            {key: post.get(key) for key in _POST_FIELDS if key in post}
            for post in posts
            if isinstance(post, dict)
        ]
    return compact


def _save_history_sync(snapshot: dict) -> bool:
    """Upsert one history row keyed by fetched_at_utc. Returns True on success."""
    if not isinstance(snapshot, dict) or not snapshot.get("fetched_at_utc"):
        logger.warning("history_save_rejected reason=missing_fetched_at_utc")
        return False
    fetched_at = snapshot["fetched_at_utc"]
    try:
        client = get_supabase_client()
        client.table(_TABLE).upsert(
            {
                "id": f"{_HISTORY_PREFIX}{fetched_at}",
                "snapshot": compact_for_history(snapshot),
                "fetched_at": fetched_at,
            }
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("history_save_failed error_type=%s error=%s", type(exc).__name__, exc)
        return False


async def save_history(snapshot: dict) -> bool:
    """Async save of one compact history row. Never raises; returns success bool."""
    return await asyncio.to_thread(_save_history_sync, snapshot)


async def save_snapshot(snapshot: dict) -> bool:
    """Async upsert of the latest snapshot. Never raises; returns success bool."""
    return await asyncio.to_thread(_save_snapshot_sync, snapshot)


async def load_latest_snapshot() -> dict | None:
    """Async load of the latest snapshot. Never raises; returns dict or None."""
    return await asyncio.to_thread(_load_latest_snapshot_sync)
