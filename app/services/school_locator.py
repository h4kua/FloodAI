"""
Flood-prone school locator.

Reads scripts/build_flood_prone_schools.py output and finds vulnerable
facilities (schools = children) near a coordinate, for evacuation/priority
context. Static-fallback pattern: missing data => empty list.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.api.observability import get_logger
from app.services.shelter_locator import haversine_m

_log = get_logger("flood.school_locator")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHOOLS_PATH = _PROJECT_ROOT / "app" / "data" / "flood_prone_schools.json"


@lru_cache(maxsize=1)
def load_schools() -> tuple[dict, ...]:
    try:
        if not SCHOOLS_PATH.exists():
            _log.warning("schools_file_missing", path=str(SCHOOLS_PATH))
            return ()
        payload = json.loads(SCHOOLS_PATH.read_text(encoding="utf-8"))
        return tuple(
            s for s in payload.get("schools", [])
            if isinstance(s.get("lat"), (int, float)) and isinstance(s.get("lon"), (int, float))
        )
    except (OSError, ValueError) as exc:
        _log.warning("schools_load_failed", error=str(exc))
        return ()


def nearby_schools(
    lat: float,
    lon: float,
    *,
    radius_m: float = 500.0,
    limit: int = 5,
    schools: Optional[tuple[dict, ...]] = None,
) -> list[dict]:
    """Flood-prone schools within ``radius_m``, nearest first."""
    pool = schools if schools is not None else load_schools()
    if not pool:
        return []
    found = []
    for s in pool:
        try:
            d = haversine_m(lat, lon, float(s["lat"]), float(s["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d <= radius_m:
            found.append((d, s))
    found.sort(key=lambda pair: pair[0])
    return [
        {
            "name": s.get("name"),
            "type": "school",
            "jumlah_siswa": s.get("jumlah_siswa"),
            "kelurahan": s.get("kelurahan"),
            "distance_m": round(d, 1),
        }
        for d, s in found[: max(1, limit)]
    ]


if __name__ == "__main__":
    for s in nearby_schools(-6.15357, 106.79081, radius_m=800):
        print(f"{s['distance_m']:>6} m  {s['name']}  (siswa={s['jumlah_siswa']})")
