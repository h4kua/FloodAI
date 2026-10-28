"""
Shelter locator — nearest evacuation point lookup for Jakarta.

Loads the compact shelter dataset built by scripts/build_jakarta_shelters.py and
answers "what is the nearest shelter to this lat/lon?" using a haversine
distance. Follows the project's static-fallback pattern: if the data file is
missing or unreadable, loaders return empty results and log a warning instead
of raising — callers degrade gracefully (no shelter recommendation).
"""

from __future__ import annotations

import heapq
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

from api.observability import get_logger

_log = get_logger("flood.shelter_locator")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHELTERS_PATH = _PROJECT_ROOT / "data" / "bundled" / "jakarta_shelters.json"

_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def load_shelters() -> tuple[dict, ...]:
    """
    Load shelters once and cache. Returns an empty tuple on any failure
    (missing file, bad JSON) so callers never crash on absent static data.
    """
    try:
        if not SHELTERS_PATH.exists():
            _log.warning("shelters_file_missing", path=str(SHELTERS_PATH))
            return ()
        payload = json.loads(SHELTERS_PATH.read_text(encoding="utf-8"))
        shelters = payload.get("shelters", [])
        usable = tuple(
            s for s in shelters
            if isinstance(s.get("lat"), (int, float)) and isinstance(s.get("lon"), (int, float))
        )
        _log.info("shelters_loaded", count=len(usable))
        return usable
    except (OSError, ValueError) as exc:
        _log.warning("shelters_load_failed", error=str(exc), path=str(SHELTERS_PATH))
        return ()


_BUILDING_KINDS = {
    "school": "school", "kindergarten": "school",
    "mosque": "mosque", "church": "church", "temple": "temple",
    "community_group_office": "rw_office",
    "village_office": "village_office", "subdistrict_office": "subdistrict_office",
    "government_office": "government", "government": "government", "townhall": "government",
    "hospital": "hospital",
}
_AMENITY_KINDS = {
    "shelter": "shelter", "school": "school", "kindergarten": "school",
    "place_of_worship": "worship", "community_centre": "community_centre",
    "social_facility": "social_facility", "townhall": "government",
    "hospital": "hospital", "clinic": "clinic", "courthouse": "courthouse",
}
# Not places to wait out a flood: they serve the sick or the courts.
_NOT_EVACUATION_KINDS = frozenset({"hospital", "clinic", "courthouse"})
_DUPLICATE_RADIUS_M = 150.0


def shelter_kind(shelter: dict) -> str:
    """One short type for a shelter candidate, from its OSM amenity and building tags."""
    amenity = (shelter.get("amenity") or "").strip()
    building = (shelter.get("building") or "").strip()
    if amenity in ("hospital", "clinic", "courthouse", "shelter"):
        return _AMENITY_KINDS[amenity]
    return _BUILDING_KINDS.get(building) or _AMENITY_KINDS.get(amenity) or "other"


def _to_result(shelter: dict, distance_m: float) -> dict:
    return {
        "id": shelter.get("id"),
        "name": shelter.get("name"),
        "kelurahan": shelter.get("kelurahan"),
        "address": shelter.get("address") or None,
        "lat": shelter.get("lat"),
        "lon": shelter.get("lon"),
        "capacity": shelter.get("capacity_raw") or None,
        "capacity_est": shelter.get("capacity_est"),
        "amenity": shelter.get("amenity") or None,
        "kind": shelter_kind(shelter),
        "distance_m": round(distance_m, 1),
        "distance_km": round(distance_m / 1000.0, 2),
    }


def _haversine_safe(lat: float, lon: float, shelter: dict) -> Optional[float]:
    try:
        return haversine_m(lat, lon, float(shelter["lat"]), float(shelter["lon"]))
    except (KeyError, TypeError, ValueError):
        return None


def nearest_shelters(
    lat: float,
    lon: float,
    *,
    limit: int = 3,
    require_capacity: bool = False,
    evacuation_only: bool = False,
    shelters: Optional[tuple[dict, ...]] = None,
) -> list[dict]:
    """
    Return up to ``limit`` nearest shelters to (lat, lon), nearest first.

    ``require_capacity`` keeps only shelters with a parsed capacity estimate;
    ``evacuation_only`` drops hospitals, clinics and courts.
    Returns an empty list when no shelter data is available.
    """
    pool = shelters if shelters is not None else load_shelters()
    if not pool:
        return []
    candidates = [
        s for s in pool
        if (not require_capacity or s.get("capacity_est"))
        and (not evacuation_only or shelter_kind(s) not in _NOT_EVACUATION_KINDS)
    ]
    limit = max(1, limit)
    scored = [(_haversine_safe(lat, lon, s), i, s) for i, s in enumerate(candidates)]
    nearest = heapq.nsmallest(limit * 2, (t for t in scored if t[0] is not None))
    # The survey lists some places twice (same name, a few metres apart): keep one.
    kept: list[tuple[float, dict]] = []
    for d, _, s in nearest:
        name = (s.get("name") or "").strip().lower()
        if any(name == (k.get("name") or "").strip().lower()
               and haversine_m(s["lat"], s["lon"], k["lat"], k["lon"]) <= _DUPLICATE_RADIUS_M
               for _, k in kept):
            continue
        kept.append((d, s))
        if len(kept) == limit:
            break
    return [_to_result(s, d) for d, s in kept]


def nearest_shelter(
    lat: float,
    lon: float,
    *,
    require_capacity: bool = False,
    evacuation_only: bool = False,
    shelters: Optional[tuple[dict, ...]] = None,
) -> Optional[dict]:
    """Return the single nearest shelter, or ``None`` when no data is available."""
    results = nearest_shelters(
        lat, lon, limit=1, require_capacity=require_capacity,
        evacuation_only=evacuation_only, shelters=shelters,
    )
    return results[0] if results else None


if __name__ == "__main__":
    # Quick smoke test against central Jakarta (Monas).
    for s in nearest_shelters(-6.1754, 106.8272, limit=3):
        print(f"{s['distance_km']:>5} km  {s['name']}  (cap={s['capacity']})")
