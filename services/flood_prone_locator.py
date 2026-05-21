"""
Flood-prone zone locator.

Answers "is this coordinate within N metres of a known flood-prone point?" using
the dataset built by scripts/build_flood_prone_points.py. Static-fallback
pattern: missing data => not-in-zone / None, never an exception.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from api.observability import get_logger
from services.shelter_locator import haversine_m

_log = get_logger("flood.flood_prone_locator")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRONE_POINTS_PATH = _PROJECT_ROOT / "data" / "bundled" / "flood_prone_points.json"
RIVER_ZONES_PATH = _PROJECT_ROOT / "data" / "bundled" / "river_flood_zones.json"

# A coordinate within this radius of a recorded prone point is "in zone".
DEFAULT_RADIUS_M = 500.0


@lru_cache(maxsize=1)
def load_points() -> tuple[dict, ...]:
    """Load flood-prone points once. Returns () on any failure."""
    try:
        if not PRONE_POINTS_PATH.exists():
            _log.warning("flood_prone_file_missing", path=str(PRONE_POINTS_PATH))
            return ()
        payload = json.loads(PRONE_POINTS_PATH.read_text(encoding="utf-8"))
        return tuple(
            p for p in payload.get("points", [])
            if isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float))
        )
    except (OSError, ValueError) as exc:
        _log.warning("flood_prone_load_failed", error=str(exc))
        return ()


def nearest_prone_point(
    lat: float, lon: float, *, points: Optional[tuple[dict, ...]] = None
) -> Optional[dict]:
    """Return the nearest flood-prone point with its distance, or None."""
    pool = points if points is not None else load_points()
    if not pool:
        return None
    best, best_d = None, float("inf")
    for p in pool:
        try:
            d = haversine_m(lat, lon, float(p["lat"]), float(p["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d < best_d:
            best_d, best = d, p
    if best is None:
        return None
    return {
        "kecamatan": best.get("kecamatan"),
        "kelurahan": best.get("kelurahan"),
        "wilayah": best.get("wilayah"),
        "distance_m": round(best_d, 1),
    }


def in_flood_prone_zone(
    lat: float,
    lon: float,
    *,
    radius_m: float = DEFAULT_RADIUS_M,
    points: Optional[tuple[dict, ...]] = None,
) -> bool:
    """True if (lat, lon) is within ``radius_m`` of any flood-prone point."""
    nearest = nearest_prone_point(lat, lon, points=points)
    return bool(nearest and nearest["distance_m"] <= radius_m)


@lru_cache(maxsize=1)
def _load_river_zones() -> dict:
    try:
        if not RIVER_ZONES_PATH.exists():
            return {}
        return json.loads(RIVER_ZONES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("river_zones_load_failed", error=str(exc))
        return {}


def river_overflow_zone(
    *, kecamatan: Optional[str] = None, kelurahan: Optional[str] = None
) -> dict:
    """
    Whether an administrative area is a recorded river-overflow flood zone.
    This source is NAME-based (no coordinates), so callers pass kecamatan and/or
    kelurahan names. Returns in_river_overflow_zone + the affected river(s).
    """
    data = _load_river_zones()
    rivers: set[str] = set()
    in_zone = False
    if kelurahan:
        rec = data.get("by_kelurahan", {}).get(kelurahan.strip().upper())
        if rec:
            in_zone = True
            rivers.update(rec.get("rivers", []))
    if kecamatan:
        rec = data.get("by_kecamatan", {}).get(kecamatan.strip().upper())
        if rec:
            in_zone = True
            rivers.update(rec.get("rivers", []))
    ordered = sorted(rivers)
    return {
        "in_river_overflow_zone": in_zone,
        "affected_rivers": ordered,
        "affected_river": ordered[0] if ordered else None,
    }


if __name__ == "__main__":
    # Bendungan Hilir is a recorded prone point — a nearby coordinate is in-zone.
    print("near Benhil:", in_flood_prone_zone(-6.2016, 106.8083))
    print("open sea:", in_flood_prone_zone(-6.0, 106.0))
    print("Cengkareng overflow:", river_overflow_zone(kecamatan="CENGKARENG"))
