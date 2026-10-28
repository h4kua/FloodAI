"""
Safe Arrival endpoint (FloodGuard FR8 — Safe Arrival screen).

Public — no API key required, matching /predict/crew-realtime's tier.
Rate-limited by IP. GET /shelters/nearby gives the evacuation page the
nearest shelter candidates from jakarta_shelters.json. The client (frontend
geofence hook or a manual "I've Arrived" button) proposes a shelter arrival,
including the shelter's own coordinates, so this endpoint validates distance
against the shelter coordinates the user actually selected (the page also has
a small offline fallback list with its own ids). Client-only geofencing is
still never trusted for the DB write: the server independently recomputes
the distance via services.shelter_locator's haversine_m before accepting it.

On a valid arrival, in one call: (1) logs the shelter check-in, (2) flips the
family member's status to 'safe' if a family_code was supplied, (3)
auto-posts a 'safe' community report — satisfying FR8's "simultaneously
notify family + post to feed + log checkin" with zero extra round-trips.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.ip_rate_limit import require_ip_rate_limit
from db.community_reports_repository import create_report
from db.family_repository import checkin_member, get_family_id
from db.shelter_checkins_repository import create_checkin
from services.shelter_locator import haversine_m, nearest_shelters

router = APIRouter(tags=["safe-arrival"])

_GEOFENCE_TOLERANCE_M = 250.0


@router.get(
    "/shelters/nearby",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Nearest shelter candidates (schools, places of worship, RW and kelurahan offices).",
)
async def shelters_nearby(
    lat: float = Query(..., ge=-6.6, le=-5.9),
    lon: float = Query(..., ge=106.5, le=107.2),
    limit: int = Query(10, ge=1, le=20),
) -> dict:
    shelters = nearest_shelters(lat, lon, limit=limit, evacuation_only=True)
    return {
        "shelters": shelters,
        "count": len(shelters),
        # Candidates from a community survey, not a list of official BPBD shelters.
        "source": "OpenStreetMap / HOT InAWARE survey",
    }


class ShelterCheckinIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    shelter_id: str = Field(min_length=1, max_length=40)
    shelter_name: str = Field(min_length=1, max_length=160)
    shelter_lat: float
    shelter_lon: float
    lat: float
    lon: float
    auto: bool = True
    family_code: Optional[str] = Field(default=None, min_length=6, max_length=6)


@router.post(
    "/shelters/checkin",
    dependencies=[Depends(require_ip_rate_limit)],
    summary="Confirm arrival at a shelter (geofence auto-trigger or manual button).",
)
async def shelter_checkin(payload: ShelterCheckinIn) -> dict:
    distance_m = haversine_m(payload.lat, payload.lon, payload.shelter_lat, payload.shelter_lon)
    if distance_m > _GEOFENCE_TOLERANCE_M:
        raise HTTPException(status_code=422, detail="outside_geofence")

    shelter_name = payload.shelter_name

    family_id = None
    family_notified = False
    if payload.family_code:
        family_id = await get_family_id(payload.family_code.upper())
        if family_id:
            family_notified = await checkin_member(
                family_code=payload.family_code.upper(),
                device_id=payload.device_id,
                status="safe",
                lat=payload.lat,
                lon=payload.lon,
                location_label=shelter_name,
            )

    checkin = await create_checkin(
        device_id=payload.device_id,
        shelter_id=payload.shelter_id,
        shelter_name=shelter_name,
        lat=payload.lat,
        lon=payload.lon,
        distance_m=distance_m,
        auto=payload.auto,
        family_id=family_id,
    )

    await create_report(
        severity="safe",
        message=f"Arrived safely at {shelter_name}.",
        lat=payload.lat,
        lon=payload.lon,
        device_id=payload.device_id,
        location_label=shelter_name,
    )

    # family_notified lets the UI say "your family was told" only when it's true.
    return {
        "checkin": checkin,
        "shelter_name": shelter_name,
        "distance_m": round(distance_m, 1),
        "family_notified": bool(family_notified),
    }
