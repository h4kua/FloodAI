"""
Community flood reports endpoint (FloodGuard FR7 — Community Reports screen).

Crowdsourced, geotagged reports with a severity flag (alert/safe). Public —
no API key required, matching /predict/crew-realtime's tier — since requiring
a shared secret for a public reporting form would mean shipping that secret in
the frontend bundle. Rate-limited by IP to prevent spam (api/ip_rate_limit.py).
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from api.ip_rate_limit import require_ip_rate_limit
from db.community_reports_repository import create_report, list_reports
from services.shelter_locator import haversine_m

router = APIRouter(tags=["community-reports"])


class CommunityReportIn(BaseModel):
    severity: Literal["alert", "safe"]
    message: str = Field(min_length=1, max_length=2000)
    lat: float
    lon: float
    reporter_name: Optional[str] = Field(default=None, max_length=80)
    device_id: Optional[str] = Field(default=None, max_length=64)
    location_label: Optional[str] = Field(default=None, max_length=160)


@router.post(
    "/reports",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Submit a crowdsourced community flood report (no API key required).",
)
async def submit_report(payload: CommunityReportIn) -> dict:
    report = await create_report(
        severity=payload.severity,
        message=payload.message,
        lat=payload.lat,
        lon=payload.lon,
        reporter_name=payload.reporter_name,
        device_id=payload.device_id,
        location_label=payload.location_label,
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
) -> dict:
    reports = await list_reports(severity=severity, verified=verified, limit=limit)

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

    return {"reports": reports, "count": len(reports)}
