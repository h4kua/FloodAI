"""
Pump-house locator — drainage-infrastructure proximity for Jakarta.

Reads the dataset built by scripts/build_jakarta_pump_houses.py and answers
"which pump houses are near this location, and how much drainage capacity sits
within range?". Static-fallback pattern: missing data => empty / 0.0.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from api.observability import get_logger
from services.shelter_locator import haversine_m

_log = get_logger("flood.pump_locator")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUMPS_PATH = _PROJECT_ROOT / "data" / "bundled" / "jakarta_pump_houses.json"

# The source ``total_kapasitas`` column has inconsistent units across rows
# (values span ~0.07 to 75+), so SUMMING capacity is not meaningful. The
# drainage signal is therefore based on pump-house COUNT density, which is a
# consistent, well-defined quantity. This many pumps within 2 km maps to a
# full drainage score of 1.0.
_PUMP_COUNT_FULL_SCORE = 30.0


@lru_cache(maxsize=1)
def load_pumps() -> tuple[dict, ...]:
    try:
        if not PUMPS_PATH.exists():
            _log.warning("pumps_file_missing", path=str(PUMPS_PATH))
            return ()
        payload = json.loads(PUMPS_PATH.read_text(encoding="utf-8"))
        return tuple(
            p for p in payload.get("pumps", [])
            if isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lon"), (int, float))
        )
    except (OSError, ValueError) as exc:
        _log.warning("pumps_load_failed", error=str(exc))
        return ()


def get_nearest_pump_houses(
    lat: float,
    lon: float,
    *,
    radius_km: float = 3.0,
    limit: int = 5,
    pumps: Optional[tuple[dict, ...]] = None,
) -> list[dict]:
    """Pump houses within ``radius_km``, nearest first (capped at ``limit``)."""
    pool = pumps if pumps is not None else load_pumps()
    if not pool:
        return []
    radius_m = radius_km * 1000.0
    found = []
    for p in pool:
        try:
            d = haversine_m(lat, lon, float(p["lat"]), float(p["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d <= radius_m:
            found.append((d, p))
    found.sort(key=lambda pair: pair[0])
    return [
        {
            "name": p.get("name"),
            "distance_m": round(d, 1),
            "total_capacity": p.get("total_capacity"),
            "jumlah_pompa": p.get("jumlah_pompa"),
            "kecamatan": p.get("kecamatan"),
        }
        for d, p in found[: max(1, limit)]
    ]


def pump_drainage_capacity(
    lat: float,
    lon: float,
    *,
    radius_km: float = 2.0,
    pumps: Optional[tuple[dict, ...]] = None,
) -> dict:
    """
    Sum pump capacity within ``radius_km`` and normalise to a [0, 1] drainage
    score. Higher score = more nearby drainage = mitigating factor (advisory
    only; never alters risk_level/probability).
    """
    pool = pumps if pumps is not None else load_pumps()
    radius_m = radius_km * 1000.0
    total_cap = 0.0
    count = 0
    for p in pool:
        try:
            d = haversine_m(lat, lon, float(p["lat"]), float(p["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d <= radius_m:
            count += 1
            cap = p.get("total_capacity")
            if isinstance(cap, (int, float)):
                total_cap += cap
    score = min(count / _PUMP_COUNT_FULL_SCORE, 1.0) if count > 0 else 0.0
    return {
        "pump_count_within_radius": count,
        # Raw sum kept for reference only — source units are inconsistent.
        "total_capacity_within_radius_raw": round(total_cap, 3),
        "drainage_score": round(score, 4),
        "drainage_score_basis": "pump_count_density",
        "radius_km": radius_km,
    }


if __name__ == "__main__":
    print("near Tebet:", pump_drainage_capacity(-6.2265, 106.864))
    print("nearest:", get_nearest_pump_houses(-6.2265, 106.864, limit=3))
