"""
Supabase repository for shelter arrival check-ins.

Backs `shelter_checkins` (migration 110). Records both geofence-auto-triggered
and manual "I've Arrived" check-ins (FloodGuard FR8 — Safe Arrival screen).

The supabase-py client is synchronous, so the async public API wraps each call
in `asyncio.to_thread`. Neither function raises — failures are logged and
surfaced as `None` / `[]`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from db.supabase_client import get_supabase_client

logger = logging.getLogger("flood.shelter_checkins_repository")

_TABLE = "shelter_checkins"


def _create_checkin_sync(
    *,
    device_id: str,
    shelter_id: str,
    shelter_name: str,
    lat: float,
    lon: float,
    distance_m: float,
    auto: bool,
    family_id: Optional[str] = None,
) -> Optional[dict]:
    try:
        client = get_supabase_client()
        payload = {
            "device_id": device_id,
            "family_id": family_id,
            "shelter_id": shelter_id,
            "shelter_name": shelter_name,
            "lat": lat,
            "lon": lon,
            "distance_m": distance_m,
            "auto": auto,
        }
        result = client.table(_TABLE).insert(payload).execute()
        rows = result.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("checkin_create_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


async def create_checkin(
    *,
    device_id: str,
    shelter_id: str,
    shelter_name: str,
    lat: float,
    lon: float,
    distance_m: float,
    auto: bool,
    family_id: Optional[str] = None,
) -> Optional[dict]:
    return await asyncio.to_thread(
        _create_checkin_sync,
        device_id=device_id,
        shelter_id=shelter_id,
        shelter_name=shelter_name,
        lat=lat,
        lon=lon,
        distance_m=distance_m,
        auto=auto,
        family_id=family_id,
    )
