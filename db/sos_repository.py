"""
Supabase repository for SOS dispatch alerts.

Backs `sos_alerts` (migration 108). Real BPBD dispatch integration and SMS
fallback are out of scope for this build (no gateway exists) — this is the
record of what was dispatched from the app.

The supabase-py client is synchronous, so the async public API wraps each call
in `asyncio.to_thread`. Neither function raises — failures are logged and
surfaced as `None` / `[]`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from db.supabase_client import get_supabase_client

logger = logging.getLogger("flood.sos_repository")

_TABLE = "sos_alerts"


def _create_sos_sync(
    *,
    device_id: str,
    name: str,
    phone: str,
    lat: float,
    lon: float,
    family_id: Optional[str] = None,
) -> Optional[dict]:
    try:
        client = get_supabase_client()
        payload = {
            "device_id": device_id,
            "name": name,
            "phone": phone,
            "lat": lat,
            "lon": lon,
            "family_id": family_id,
        }
        result = client.table(_TABLE).insert(payload).execute()
        rows = result.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("sos_create_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _list_recent_sos_sync(limit: int = 20) -> list[dict]:
    try:
        client = get_supabase_client()
        result = client.table(_TABLE).select("*").order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("sos_list_failed error_type=%s error=%s", type(exc).__name__, exc)
        return []


async def create_sos(
    *,
    device_id: str,
    name: str,
    phone: str,
    lat: float,
    lon: float,
    family_id: Optional[str] = None,
) -> Optional[dict]:
    return await asyncio.to_thread(
        _create_sos_sync, device_id=device_id, name=name, phone=phone, lat=lat, lon=lon, family_id=family_id
    )


async def list_recent_sos(limit: int = 20) -> list[dict]:
    return await asyncio.to_thread(_list_recent_sos_sync, limit)
