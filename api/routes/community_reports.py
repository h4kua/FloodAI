"""
Community flood reports endpoint (FloodGuard FR7 — Community Reports screen).

Crowdsourced, geotagged reports with a severity flag (alert/safe). Public —
no API key required, matching /predict/crew-realtime's tier — since requiring
a shared secret for a public reporting form would mean shipping that secret in
the frontend bundle. Rate-limited by IP to prevent spam (api/ip_rate_limit.py).
"""

from __future__ import annotations

import asyncio
import io
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from api.ip_rate_limit import require_ip_rate_limit
from db.community_reports_repository import (
    PHOTO_BUCKET,
    add_comment,
    create_report,
    flag_report,
    get_report,
    list_comments,
    list_reports,
    report_interactions,
    set_vote,
    upload_photo,
)
from services.shelter_locator import haversine_m

router = APIRouter(tags=["community-reports"])

# Reports are unverified first-hand observations: they are shown as such and only
# while they can still describe the present. They never feed the flood status.
REPORT_MAX_AGE = timedelta(hours=6)

# Photos: at most 8 MB in, re-encoded to a JPEG of at most 1280 px on the long
# side. Re-encoding drops all metadata (camera GPS, device) and anything that is
# not a plain image.
PHOTO_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
PHOTO_MAX_SIDE_PX = 1280
# A small file can still decode to a huge bitmap; refuse anything over ~40 MP
# (a 512 MB machine) instead of only warning, as Pillow does by default.
PHOTO_MAX_PIXELS = 40_000_000

# A report flagged by this many devices drops out of the list (migration 111).
FLAG_HIDE_THRESHOLD = 3
# Devices are the random IDs the web app keeps in localStorage.
_DEVICE_ID = dict(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


def _normalise_photo(data: bytes) -> bytes:
    """Decode an uploaded image and re-encode it as a small, metadata-free JPEG."""
    with Image.open(io.BytesIO(data)) as img:
        if img.width * img.height > PHOTO_MAX_PIXELS:
            raise ValueError("image dimensions too large")
        img.load()
        img = img.convert("RGB")
        img.thumbnail((PHOTO_MAX_SIDE_PX, PHOTO_MAX_SIDE_PX))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=80, optimize=True)
    return out.getvalue()


def _photo_url_prefix() -> str:
    """Public URL prefix of the report-photos bucket; reports may only link there."""
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    return f"{base}/storage/v1/object/public/{PHOTO_BUCKET}/"


class CommunityReportIn(BaseModel):
    severity: Literal["alert", "safe"]
    message: str = Field(min_length=1, max_length=500)
    lat: float
    lon: float
    reporter_name: Optional[str] = Field(default=None, max_length=80)
    device_id: Optional[str] = Field(default=None, max_length=64)
    location_label: Optional[str] = Field(default=None, max_length=160)
    photo_url: Optional[str] = Field(default=None, max_length=300)


class VoteIn(BaseModel):
    device_id: str = Field(**_DEVICE_ID)
    value: Literal[-1, 0, 1]  # 0 takes the vote back


class CommentIn(BaseModel):
    device_id: Optional[str] = Field(default=None, **_DEVICE_ID)
    author: Optional[str] = Field(default=None, max_length=80)
    message: str = Field(min_length=1, max_length=300)


class FlagIn(BaseModel):
    device_id: str = Field(**_DEVICE_ID)
    reason: Literal["spam", "wrong", "offensive", "private"]


async def _existing_report(report_id: UUID) -> str:
    rid = str(report_id)
    if await get_report(rid) is None:
        raise HTTPException(status_code=404, detail={"error": "report_not_found"})
    return rid


@router.post(
    "/reports/{report_id}/vote",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Like (1), dislike (-1) or take back (0) this device's vote on a report.",
)
async def vote_report(report_id: UUID, payload: VoteIn) -> dict:
    rid = await _existing_report(report_id)
    if not await set_vote(rid, payload.device_id, payload.value):
        raise HTTPException(status_code=503, detail={"error": "reactions_unavailable"})
    counts = (await report_interactions([rid], payload.device_id)).get(rid, {})
    return {k: counts.get(k, 0) for k in ("likes", "dislikes", "my_vote")}


@router.get("/reports/{report_id}/comments", summary="Comments on a report, oldest first.")
async def get_report_comments(report_id: UUID) -> dict:
    comments = await list_comments(str(report_id))
    if comments is None:
        raise HTTPException(status_code=503, detail={"error": "reactions_unavailable"})
    return {"comments": comments, "count": len(comments)}


@router.post(
    "/reports/{report_id}/comments",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Add a comment to a report (no API key required).",
)
async def post_report_comment(report_id: UUID, payload: CommentIn) -> dict:
    rid = await _existing_report(report_id)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail={"error": "empty_comment"})
    author = (payload.author or "").strip() or None
    comment = await add_comment(rid, message, author, payload.device_id)
    if comment is None:
        raise HTTPException(status_code=503, detail={"error": "reactions_unavailable"})
    return {"comment": comment}


@router.post(
    "/reports/{report_id}/flag",
    dependencies=[Depends(require_ip_rate_limit)],
    summary=f"Flag a report as unwanted; {FLAG_HIDE_THRESHOLD} devices hide it.",
)
async def flag_report_endpoint(report_id: UUID, payload: FlagIn) -> dict:
    rid = await _existing_report(report_id)
    if not await flag_report(rid, payload.device_id, payload.reason):
        raise HTTPException(status_code=503, detail={"error": "reactions_unavailable"})
    return {"flagged": True}


@router.post(
    "/reports/photo",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Upload a photo for a community report; returns its public URL.",
)
async def submit_report_photo(photo: UploadFile = File(...)) -> dict:
    data = await photo.read(PHOTO_MAX_UPLOAD_BYTES + 1)
    if len(data) > PHOTO_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail={"error": "photo_too_large"})
    try:
        jpeg = await asyncio.to_thread(_normalise_photo, data)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail={"error": "not_an_image"}) from exc
    url = await upload_photo(jpeg)
    if url is None:
        raise HTTPException(status_code=503, detail={"error": "photo_store_unavailable"})
    return {"photo_url": url}


@router.post(
    "/reports",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Submit a crowdsourced community flood report (no API key required).",
)
async def submit_report(payload: CommunityReportIn) -> dict:
    if payload.photo_url and not payload.photo_url.startswith(_photo_url_prefix()):
        raise HTTPException(status_code=422, detail={"error": "photo_url_not_from_report_photos"})
    report = await create_report(
        severity=payload.severity,
        message=payload.message,
        lat=payload.lat,
        lon=payload.lon,
        reporter_name=payload.reporter_name,
        device_id=payload.device_id,
        location_label=payload.location_label,
        photo_url=payload.photo_url,
    )
    return {"report": report, "saved": report is not None}


@router.get(
    "/reports",
    summary="List community flood reports, newest first (no API key required).",
)
async def get_reports(
    request: Request,
    severity: Optional[Literal["alert", "safe"]] = None,
    verified: Optional[bool] = None,
    near_lat: Optional[float] = Query(default=None),
    near_lon: Optional[float] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    device_id: Optional[str] = Query(default=None, max_length=64),
) -> dict:
    since = (datetime.now(timezone.utc) - REPORT_MAX_AGE).isoformat()
    reports = await list_reports(severity=severity, verified=verified, since=since, limit=limit)

    # Likes, dislikes, comment counts and this device's vote; reports flagged by
    # enough devices drop out. Device IDs are never sent back.
    reactions = await report_interactions([r["id"] for r in reports if r.get("id")], device_id)
    shown = []
    for r in reports:
        r.pop("device_id", None)
        counts = reactions.get(r.get("id"), {})
        if counts.get("flags", 0) >= FLAG_HIDE_THRESHOLD:
            continue
        r.update({k: counts.get(k, 0) for k in ("likes", "dislikes", "comment_count", "my_vote")})
        shown.append(r)
    reports = shown

    if near_lat is not None and near_lon is not None and reports:
        distances = [
            (haversine_m(near_lat, near_lon, r["lat"], r["lon"]), r)
            for r in reports
            if r.get("lat") is not None and r.get("lon") is not None
        ]
        if distances:
            nearest_id = min(distances, key=lambda pair: pair[0])[1]["id"]
            for r in reports:
                r["is_pinned"] = r["id"] == nearest_id

    return {
        "reports": reports,
        "count": len(reports),
        "max_age_hours": int(REPORT_MAX_AGE.total_seconds() // 3600),
    }
