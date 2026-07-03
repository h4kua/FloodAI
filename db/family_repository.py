"""
Supabase repository for family groups and members.

Backs `family_groups` + `family_members` (migration 107). Identity here is a
device-id + human-enterable 6-char family code — no login system exists in
this codebase, so this is the lightweight substitute: the first member creates
a family (server generates the code, retrying on the rare unique-constraint
collision), other members join with that code.

`is_stale` (FR6: max 5 min staleness) is computed at read time in
`list_members`, not stored, so it never drifts out of sync.

The supabase-py client is synchronous, so the async public API wraps each call
in `asyncio.to_thread`. Neither function raises — failures are logged and
surfaced as `None` / `[]` / `False`.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from db.supabase_client import get_supabase_client

logger = logging.getLogger("flood.family_repository")

_GROUPS_TABLE = "family_groups"
_MEMBERS_TABLE = "family_members"
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # excludes O/0, I/1
_CODE_LENGTH = 6
_MAX_CODE_ATTEMPTS = 5
_STALE_AFTER_SECONDS = 5 * 60


def _generate_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def _create_family_sync(*, device_id: str, display_name: str, phone: Optional[str]) -> Optional[dict]:
    """Create a new family group + its first member. Returns {family_code, member_id} or None."""
    client = get_supabase_client()
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = _generate_code()
        try:
            group_result = client.table(_GROUPS_TABLE).insert({"code": code}).execute()
            group_rows = group_result.data or []
            if not group_rows:
                continue
            family_id = group_rows[0]["id"]
            member_result = (
                client.table(_MEMBERS_TABLE)
                .insert({
                    "family_id": family_id,
                    "device_id": device_id,
                    "display_name": display_name,
                    "phone": phone,
                })
                .execute()
            )
            member_rows = member_result.data or []
            if not member_rows:
                return None
            return {"family_code": code, "member_id": member_rows[0]["id"]}
        except Exception as exc:  # noqa: BLE001 — retry on collision, never raise out.
            logger.warning("family_create_attempt_failed error_type=%s error=%s", type(exc).__name__, exc)
            continue
    logger.warning("family_create_failed reason=exhausted_code_attempts")
    return None


def _find_family_id_sync(code: str) -> Optional[str]:
    try:
        client = get_supabase_client()
        result = client.table(_GROUPS_TABLE).select("id").eq("code", code).limit(1).execute()
        rows = result.data or []
        return rows[0]["id"] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("family_lookup_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _join_family_sync(
    *, family_code: str, device_id: str, display_name: str, phone: Optional[str]
) -> Optional[dict]:
    """Join an existing family by code. Returns {family_id, members: [...]} or None if code unknown."""
    family_id = _find_family_id_sync(family_code)
    if family_id is None:
        return None
    try:
        client = get_supabase_client()
        client.table(_MEMBERS_TABLE).upsert(
            {
                "family_id": family_id,
                "device_id": device_id,
                "display_name": display_name,
                "phone": phone,
            },
            on_conflict="family_id,device_id",
        ).execute()
        return {"family_id": family_id, "members": _list_members_sync(family_code)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("family_join_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _list_members_sync(family_code: str) -> list[dict]:
    """Return all members of the family with `code`, newest-seen first, plus computed `is_stale`."""
    family_id = _find_family_id_sync(family_code)
    if family_id is None:
        return []
    try:
        client = get_supabase_client()
        result = (
            client.table(_MEMBERS_TABLE)
            .select("*")
            .eq("family_id", family_id)
            .order("last_seen_at", desc=True)
            .execute()
        )
        members = result.data or []
        now = datetime.now(timezone.utc)
        for m in members:
            last_seen = m.get("last_seen_at")
            is_stale = True
            if last_seen:
                try:
                    seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                    is_stale = (now - seen_dt).total_seconds() > _STALE_AFTER_SECONDS
                except ValueError:
                    is_stale = True
            m["is_stale"] = is_stale
        return members
    except Exception as exc:  # noqa: BLE001
        logger.warning("family_list_members_failed error_type=%s error=%s", type(exc).__name__, exc)
        return []


def _checkin_member_sync(
    *,
    family_code: str,
    device_id: str,
    status: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    location_label: Optional[str] = None,
) -> bool:
    """Update a member's status/location/last_seen_at. Returns True on success."""
    family_id = _find_family_id_sync(family_code)
    if family_id is None:
        return False
    try:
        client = get_supabase_client()
        payload = {
            "family_id": family_id,
            "device_id": device_id,
            "status": status,
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
        }
        if lat is not None:
            payload["lat"] = lat
        if lon is not None:
            payload["lon"] = lon
        if location_label is not None:
            payload["location_label"] = location_label
        client.table(_MEMBERS_TABLE).update(payload).eq("family_id", family_id).eq("device_id", device_id).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("family_checkin_failed error_type=%s error=%s", type(exc).__name__, exc)
        return False


async def get_family_id(family_code: str) -> Optional[str]:
    """Resolve a family code to its internal UUID, or None if the code is unknown."""
    return await asyncio.to_thread(_find_family_id_sync, family_code)


async def create_family(*, device_id: str, display_name: str, phone: Optional[str] = None) -> Optional[dict]:
    return await asyncio.to_thread(_create_family_sync, device_id=device_id, display_name=display_name, phone=phone)


async def join_family(
    *, family_code: str, device_id: str, display_name: str, phone: Optional[str] = None
) -> Optional[dict]:
    return await asyncio.to_thread(
        _join_family_sync, family_code=family_code, device_id=device_id, display_name=display_name, phone=phone
    )


async def list_members(family_code: str) -> list[dict]:
    return await asyncio.to_thread(_list_members_sync, family_code)


async def checkin_member(
    *,
    family_code: str,
    device_id: str,
    status: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    location_label: Optional[str] = None,
) -> bool:
    return await asyncio.to_thread(
        _checkin_member_sync,
        family_code=family_code,
        device_id=device_id,
        status=status,
        lat=lat,
        lon=lon,
        location_label=location_label,
    )
