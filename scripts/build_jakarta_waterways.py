"""
Build a compact named-waterways dataset + per-kecamatan nearest-river table.

Input : data/raw/jakarta_waterways.geojson  (1195 LineStrings, OSM-derived;
        properties: name, waterway[river|canal|stream|drain], ...)
        data/bnpb_jakarta_static.json        (kecamatan centroids: lat/lon)
Output: app/data/jakarta_waterways.json

Keeps only NAMED waterways (the rest are unnamed ditches/drains of little value
for a "nearest river" answer) and precomputes the nearest named waterway for
each kecamatan centroid so runtime lookups are O(1) per district.

Run:
    python scripts/build_jakarta_waterways.py
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "jakarta_waterways.geojson"
_STATIC = _PROJECT_ROOT / "data" / "bnpb_jakarta_static.json"
_DST = _PROJECT_ROOT / "app" / "data" / "jakarta_waterways.json"

_M_PER_DEG_LAT = 111_320.0
_JKT_LAT = -6.2  # reference latitude for equirectangular metres


def _xy(lat: float, lon: float) -> tuple[float, float]:
    """Local equirectangular projection to metres (good enough across Jakarta)."""
    x = math.radians(lon) * _M_PER_DEG_LAT * math.cos(math.radians(_JKT_LAT)) / math.radians(1)
    y = lat * _M_PER_DEG_LAT
    return x, y


def _point_seg_dist_m(px, py, ax, ay, bx, by) -> float:
    """Distance (m) from point P to segment AB, all in projected metres."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def _nearest_waterway(lat: float, lon: float, waterways: list[dict]) -> dict | None:
    px, py = _xy(lat, lon)
    best = None
    best_d = float("inf")
    for w in waterways:
        coords = w["coords"]
        for i in range(len(coords) - 1):
            ax, ay = _xy(coords[i][1], coords[i][0])
            bx, by = _xy(coords[i + 1][1], coords[i + 1][0])
            d = _point_seg_dist_m(px, py, ax, ay, bx, by)
            if d < best_d:
                best_d, best = d, w
    if best is None:
        return None
    return {
        "nearest_river": best["name"],
        "waterway_type": best["waterway"],
        "distance_to_river_m": round(best_d, 1),
    }


def build() -> dict:
    raw = json.loads(_SRC.read_text(encoding="utf-8"))
    waterways: list[dict] = []
    for feat in raw.get("features", []):
        props = feat.get("properties", {}) or {}
        name = (props.get("name") or "").strip()
        geom = feat.get("geometry", {}) or {}
        coords = geom.get("coordinates") or []
        if not name or geom.get("type") != "LineString" or len(coords) < 2:
            continue
        waterways.append(
            {
                "name": name,
                "waterway": (props.get("waterway") or "").strip(),
                "coords": [[round(c[0], 5), round(c[1], 5)] for c in coords if len(c) >= 2],
            }
        )

    kecamatan = {}
    try:
        static = json.loads(_STATIC.read_text(encoding="utf-8")).get("kecamatan", {})
    except (OSError, ValueError):
        static = {}
    for kec, rec in static.items():
        lat, lon = rec.get("lat"), rec.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            near = _nearest_waterway(lat, lon, waterways)
            if near:
                kecamatan[kec] = near

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/jakarta_waterways.geojson (OSM) + bnpb_jakarta_static centroids",
            "named_waterway_count": len(waterways),
            "kecamatan_count": len(kecamatan),
        },
        "waterways": waterways,
        "kecamatan_nearest_river": kecamatan,
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {payload['_meta']['named_waterway_count']} named waterways + "
          f"{payload['_meta']['kecamatan_count']} kecamatan nearest-river -> {_DST}")
    sample = list(payload["kecamatan_nearest_river"].items())[:4]
    for kec, n in sample:
        print(f"  {kec:16} -> {n['nearest_river']} ({n['waterway_type']}, {n['distance_to_river_m']} m)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
