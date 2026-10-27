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
