"""
Supabase repository for crowdsourced community flood reports.

Backs the ``community_reports`` table (migration 109). Reports are public and
immutable once posted — anyone can submit without identity setup, and the
`verified` flag is admin-only future work, not touched here.

The supabase-py client is synchronous, so the async public API wraps each call
in ``asyncio.to_thread`` (no sync/async mixing on the event loop).

Neither function raises — failures are logged and surfaced as ``False`` / ``[]``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from db.supabase_client import get_supabase_client

logger = logging.getLogger("flood.community_reports_repository")

_TABLE = "community_reports"


PHOTO_BUCKET = "report-photos"


def _upload_photo_sync(jpeg: bytes) -> Optional[str]:
    """Store a JPEG in the report-photos bucket. Returns its public URL, or None on failure."""
    try:
        client = get_supabase_client()
        name = f"{uuid.uuid4().hex}.jpg"
        bucket = client.storage.from_(PHOTO_BUCKET)
        bucket.upload(name, jpeg, {"content-type": "image/jpeg"})
        return bucket.get_public_url(name).rstrip("?")
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("report_photo_upload_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _create_report_sync(
    *,
    severity: str,
    message: str,
    lat: float,
    lon: float,
    reporter_name: Optional[str] = None,
    device_id: Optional[str] = None,
    location_label: Optional[str] = None,
    photo_url: Optional[str] = None,
) -> Optional[dict]:
    """Insert a new report. Returns the inserted row dict, or None on failure."""
    try:
        client = get_supabase_client()
        payload = {
            "severity": severity,
            "message": message,
            "lat": lat,
            "lon": lon,
            "reporter_name": reporter_name,
            "device_id": device_id,
            "location_label": location_label,
        }
        if photo_url:
            # Only sent with a photo, so reports still save before migration 110.
            payload["photo_url"] = photo_url
        result = client.table(_TABLE).insert(payload).execute()
        rows = result.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("report_create_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _list_reports_sync(
    *,
    severity: Optional[str] = None,
    verified: Optional[bool] = None,
    since: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Return recent reports (created at or after ``since``, ISO-8601), newest first. [] on failure."""
    try:
        client = get_supabase_client()
        query = client.table(_TABLE).select("*")
        if severity is not None:
            query = query.eq("severity", severity)
        if verified is not None:
            query = query.eq("verified", verified)
        if since is not None:
            query = query.gte("created_at", since)
        result = query.order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as exc:  # noqa: BLE001 — repository must never raise.
        logger.warning("report_list_failed error_type=%s error=%s", type(exc).__name__, exc)
        return []


# ── Reactions (migration 111): votes, comments, flags ─────────────────────────


def _get_report_sync(report_id: str) -> Optional[dict]:
    """The report row, or None when it does not exist or cannot be read."""
    try:
        client = get_supabase_client()
        result = client.table(_TABLE).select("id,created_at").eq("id", report_id).limit(1).execute()
        rows = result.data or []
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_get_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _interactions_sync(report_ids: list[str], device_id: Optional[str]) -> dict[str, dict]:
    """Per report: likes, dislikes, comment_count, flags and this device's vote.

    {} when there are no ids or the tables are missing (migration 111 not run),
    so the list still loads without reactions.
    """
    if not report_ids:
        return {}
    try:
        client = get_supabase_client()
        votes = client.table("report_votes").select("report_id,device_id,value").in_("report_id", report_ids).execute().data or []
        comments = client.table("report_comments").select("report_id").in_("report_id", report_ids).execute().data or []
        flags = client.table("report_flags").select("report_id").in_("report_id", report_ids).execute().data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_interactions_failed error_type=%s error=%s", type(exc).__name__, exc)
        return {}
    out = {rid: {"likes": 0, "dislikes": 0, "comment_count": 0, "flags": 0, "my_vote": 0} for rid in report_ids}
    for v in votes:
        row = out.get(v["report_id"])
        if row is None:
            continue
        row["likes" if v["value"] > 0 else "dislikes"] += 1
        if device_id and v["device_id"] == device_id:
            row["my_vote"] = v["value"]
    for c in comments:
        if c["report_id"] in out:
            out[c["report_id"]]["comment_count"] += 1
    for f in flags:
        if f["report_id"] in out:
            out[f["report_id"]]["flags"] += 1
    return out


def _set_vote_sync(report_id: str, device_id: str, value: int) -> bool:
    """value 1 / -1 sets this device's vote; 0 takes it back."""
    try:
        table = get_supabase_client().table("report_votes")
        if value == 0:
            table.delete().eq("report_id", report_id).eq("device_id", device_id).execute()
        else:
            table.upsert({"report_id": report_id, "device_id": device_id, "value": value},
                         on_conflict="report_id,device_id").execute()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_vote_failed error_type=%s error=%s", type(exc).__name__, exc)
        return False


def _list_comments_sync(report_id: str, limit: int = 100) -> Optional[list[dict]]:
    """Oldest first; None on failure."""
    try:
        result = (get_supabase_client().table("report_comments")
                  .select("id,author,message,created_at").eq("report_id", report_id)
                  .order("created_at").limit(limit).execute())
        return result.data or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_comments_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _add_comment_sync(report_id: str, message: str, author: Optional[str], device_id: Optional[str]) -> Optional[dict]:
    try:
        result = get_supabase_client().table("report_comments").insert({
            "report_id": report_id, "message": message, "author": author, "device_id": device_id,
        }).execute()
        rows = result.data or []
        if not rows:
            return None
        row = rows[0]
        return {k: row.get(k) for k in ("id", "author", "message", "created_at")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_comment_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def _flag_report_sync(report_id: str, device_id: str, reason: str) -> bool:
    """One flag per device; flagging again is a no-op."""
    try:
        get_supabase_client().table("report_flags").upsert(
            {"report_id": report_id, "device_id": device_id, "reason": reason},
            on_conflict="report_id,device_id", ignore_duplicates=True,
        ).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_flag_failed error_type=%s error=%s", type(exc).__name__, exc)
        return False


async def get_report(report_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_report_sync, report_id)


async def report_interactions(report_ids: list[str], device_id: Optional[str] = None) -> dict[str, dict]:
    return await asyncio.to_thread(_interactions_sync, report_ids, device_id)


async def set_vote(report_id: str, device_id: str, value: int) -> bool:
    return await asyncio.to_thread(_set_vote_sync, report_id, device_id, value)


async def list_comments(report_id: str) -> Optional[list[dict]]:
    return await asyncio.to_thread(_list_comments_sync, report_id)


async def add_comment(report_id: str, message: str, author: Optional[str], device_id: Optional[str]) -> Optional[dict]:
    return await asyncio.to_thread(_add_comment_sync, report_id, message, author, device_id)


async def flag_report(report_id: str, device_id: str, reason: str) -> bool:
    return await asyncio.to_thread(_flag_report_sync, report_id, device_id, reason)


async def create_report(
    *,
    severity: str,
    message: str,
    lat: float,
    lon: float,
    reporter_name: Optional[str] = None,
    device_id: Optional[str] = None,
    location_label: Optional[str] = None,
    photo_url: Optional[str] = None,
) -> Optional[dict]:
    """Async insert of a new community report. Never raises."""
    return await asyncio.to_thread(
        _create_report_sync,
        severity=severity,
        message=message,
        lat=lat,
        lon=lon,
        reporter_name=reporter_name,
        device_id=device_id,
        location_label=location_label,
        photo_url=photo_url,
    )


async def upload_photo(jpeg: bytes) -> Optional[str]:
    """Async upload of a report photo. Never raises; returns the public URL or None."""
    return await asyncio.to_thread(_upload_photo_sync, jpeg)


async def list_reports(
    *,
    severity: Optional[str] = None,
    verified: Optional[bool] = None,
    since: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Async load of recent reports, newest first. Never raises."""
    return await asyncio.to_thread(
        _list_reports_sync, severity=severity, verified=verified, since=since, limit=limit,
    )
