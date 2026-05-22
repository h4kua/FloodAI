"""
Supabase repository for the latest realtime ingestion snapshot.

Backs the ``realtime_snapshot_store`` table (migration 030). The dashboard reads
the latest snapshot from here so it survives Railway's ephemeral filesystem; the
periodic refresh job upserts it.

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


async def save_snapshot(snapshot: dict) -> bool:
    """Async upsert of the latest snapshot. Never raises; returns success bool."""
    return await asyncio.to_thread(_save_snapshot_sync, snapshot)


async def load_latest_snapshot() -> dict | None:
    """Async load of the latest snapshot. Never raises; returns dict or None."""
    return await asyncio.to_thread(_load_latest_snapshot_sync)
