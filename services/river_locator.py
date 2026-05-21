"""
River locator — nearest named waterway lookup for Jakarta.

Reads the dataset built by scripts/build_jakarta_waterways.py:
  * a runtime point->river lookup (nearest_river) for arbitrary coordinates, and
  * a precomputed per-kecamatan table (nearest_river_for_kecamatan) for the
    common pipeline path.

Static-fallback pattern: missing/unreadable data yields empty results (None),
never an exception.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

from api.observability import get_logger

_log = get_logger("flood.river_locator")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
WATERWAYS_PATH = _PROJECT_ROOT / "data" / "bundled" / "jakarta_waterways.json"

_M_PER_DEG_LAT = 111_320.0
_JKT_LAT = -6.2


def _xy(lat: float, lon: float) -> tuple[float, float]:
    x = math.radians(lon) * _M_PER_DEG_LAT * math.cos(math.radians(_JKT_LAT)) / math.radians(1)
    y = lat * _M_PER_DEG_LAT
    return x, y


def _point_seg_dist_m(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


@lru_cache(maxsize=1)
def _load() -> dict:
    """Load the waterways dataset once. Returns {} on any failure."""
    try:
        if not WATERWAYS_PATH.exists():
            _log.warning("waterways_file_missing", path=str(WATERWAYS_PATH))
            return {}
        return json.loads(WATERWAYS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("waterways_load_failed", error=str(exc))
        return {}


def nearest_river_for_kecamatan(name: str) -> Optional[dict]:
    """Precomputed nearest river for a kecamatan (by exact uppercased name)."""
    if not name:
        return None
    table = _load().get("kecamatan_nearest_river", {})
    return table.get(name.strip().upper()) or table.get(name.strip())


def nearest_river(lat: float, lon: float) -> Optional[dict]:
    """
    Compute the nearest named waterway to (lat, lon) at runtime.
    Returns {nearest_river, waterway_type, distance_to_river_m} or None.
    """
    waterways = _load().get("waterways", [])
    if not waterways:
        return None
    px, py = _xy(lat, lon)
    best, best_d = None, float("inf")
    for w in waterways:
        coords = w.get("coords", [])
        for i in range(len(coords) - 1):
            ax, ay = _xy(coords[i][1], coords[i][0])
            bx, by = _xy(coords[i + 1][1], coords[i + 1][0])
            d = _point_seg_dist_m(px, py, ax, ay, bx, by)
            if d < best_d:
                best_d, best = d, w
    if best is None:
        return None
    return {
        "nearest_river": best.get("name"),
        "waterway_type": best.get("waterway"),
        "distance_to_river_m": round(best_d, 1),
    }


if __name__ == "__main__":
    print("Monas:", nearest_river(-6.1754, 106.8272))
    print("Pasar Rebo (precomputed):", nearest_river_for_kecamatan("PASAR REBO"))
