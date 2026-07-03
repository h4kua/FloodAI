"""
SOS Emergency endpoints (FloodGuard FR5 — SOS Emergency screen).

Public — no API key required, matching /predict/crew-realtime's tier, since
this must be callable directly from the frontend during an emergency without
embedding a shared secret. Rate-limited by IP. If the submitting device has
joined a family, the alert also flips that family member's status to
'missing' so Family Status reflects it automatically (FR6 integration).

Real BPBD dispatch integration and SMS fallback (paper NFR3) are explicitly
out of scope — this endpoint only logs the alert for this build.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.ip_rate_limit import require_ip_rate_limit
from db.family_repository import checkin_member, get_family_id
from db.sos_repository import create_sos, list_recent_sos

router = APIRouter(tags=["sos"])


class SosIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=1, max_length=20)
    lat: float
    lon: float
    family_code: Optional[str] = Field(default=None, min_length=6, max_length=6)
    on_behalf_of_member_id: Optional[str] = None


@router.post(
    "/sos",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Dispatch an SOS alert with location, name, and phone (no API key required).",
)
async def dispatch_sos(payload: SosIn) -> dict:
    family_id = None
    if payload.family_code:
        family_id = await get_family_id(payload.family_code.upper())
        # Flip the submitting device's own status to 'missing' so Family Status
        # reflects the SOS automatically. Skipped for on-behalf-of submissions
        # (payload.device_id is the *caller*, not the missing member — the
        # target member's status is already 'missing', which is why the
        # "SOS for {name}" button was shown in the first place).
        if family_id and not payload.on_behalf_of_member_id:
            await checkin_member(
                family_code=payload.family_code.upper(),
                device_id=payload.device_id,
                status="missing",
                lat=payload.lat,
                lon=payload.lon,
            )

    alert = await create_sos(
        device_id=payload.device_id,
        name=payload.name,
        phone=payload.phone,
        lat=payload.lat,
        lon=payload.lon,
        family_id=family_id,
    )
    return {"sos": alert, "dispatched": alert is not None}


@router.get(
    "/sos/recent",
    summary="List recent SOS alerts (debug/admin view, no API key required).",
)
async def get_recent_sos(limit: int = 20) -> dict:
    alerts = await list_recent_sos(limit=limit)
    return {"alerts": alerts, "count": len(alerts)}
