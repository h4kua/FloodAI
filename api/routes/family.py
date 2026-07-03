"""
Family Status endpoints (FloodGuard FR6 — Family Status screen).

No login system exists in this codebase; identity is a device-id + 6-char
family code (db/family_repository.py). Public — no API key required, matching
/predict/crew-realtime's tier. Join/check-in are rate-limited by IP.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.ip_rate_limit import require_ip_rate_limit
from db.family_repository import checkin_member, create_family, join_family, list_members

router = APIRouter(tags=["family"])


class CreateFamilyIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)
    phone: Optional[str] = Field(default=None, max_length=20)


class JoinFamilyIn(BaseModel):
    family_code: str = Field(min_length=6, max_length=6)
    device_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=80)
    phone: Optional[str] = Field(default=None, max_length=20)


class CheckinIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    status: Literal["safe", "in_transit", "missing"]
    lat: Optional[float] = None
    lon: Optional[float] = None
    location_label: Optional[str] = Field(default=None, max_length=160)


@router.post(
    "/family/create",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Create a new family group and register the first member.",
)
async def create_family_endpoint(payload: CreateFamilyIn) -> dict:
    result = await create_family(device_id=payload.device_id, display_name=payload.display_name, phone=payload.phone)
    if result is None:
        raise HTTPException(status_code=503, detail="family_create_failed")
    return result


@router.post(
    "/family/join",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Join an existing family group by its 6-character code.",
)
async def join_family_endpoint(payload: JoinFamilyIn) -> dict:
    result = await join_family(
        family_code=payload.family_code.upper(),
        device_id=payload.device_id,
        display_name=payload.display_name,
        phone=payload.phone,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="family_not_found")
    return result


@router.get(
    "/family/{family_code}/members",
    summary="List all members of a family group with computed staleness.",
)
async def list_family_members_endpoint(family_code: str) -> dict:
    members = await list_members(family_code.upper())
    return {"members": members, "count": len(members)}


@router.post(
    "/family/{family_code}/checkin",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Update a family member's status and last known location.",
)
async def checkin_endpoint(family_code: str, payload: CheckinIn) -> dict:
    ok = await checkin_member(
        family_code=family_code.upper(),
        device_id=payload.device_id,
        status=payload.status,
        lat=payload.lat,
        lon=payload.lon,
        location_label=payload.location_label,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="family_not_found")
    return {"saved": True}
