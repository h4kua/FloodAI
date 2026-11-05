#!/usr/bin/env python
"""
Build frontend/src/data/postRivers.json: for each DSDA water-level post, the river it measures
as map lines, so a clicked post can light up its river in blue with the post at the centre.

Inputs:
  data/bundled/awlr_stations.json      post name, coordinates and river(s) ("kali", e.g.
                                       "Kali Cengkareng Drain & Kali Angke")
  data/raw/jakarta_waterways.geojson   OpenStreetMap waterways in and around Jakarta

A waterway belongs to a post's river when their names match after dropping "Kali"/"Sungai",
spaces and case ("Ci Liwung" = "Ciliwung"; aliases below). Only the stretch within
RADIUS_KM of the post is kept; an upstream post outside Jakarta (Katulampa, Depok) has no
stretch that close, so its river's whole Jakarta course is kept instead. Lines are thinned
(Douglas-Peucker, about 15 m) and rounded to 5 decimals.

Run:  python scripts/build_post_rivers.py
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
STATIONS = _ROOT / "data" / "bundled" / "awlr_stations.json"
WATERWAYS = _ROOT / "data" / "raw" / "jakarta_waterways.geojson"
OUT = _ROOT / "frontend" / "src" / "data" / "postRivers.json"
RADIUS_KM = 10.0
TOLERANCE_DEG = 0.00015
# Different spellings of the same river in the DSDA list and in OpenStreetMap.
ALIASES = {
    "banjirkanalbarat": "kanalbanjirbarat",
    "banjirkanaltimur": "kanalbanjirtimur",
    "ciliwunggunungsahari": "ciliwunggajahmada",
    "duriledeng": "duri",
    "cidengsiantar": "cideng",
}
SKIP = {"laut", "waduk pluit", "anak kali ciliwung"}


def river_key(name: str) -> str:
    text = re.sub(r"\b(kali|sungai|river)\b", "", (name or "").lower())
    key = re.sub(r"[^a-z0-9]", "", text)
    return ALIASES.get(key, key)


def post_key(name: str) -> str:
    """'P.A. Marina Ancol 1 (Laut)' -> 'marinaancol'; the frontend applies the same rule."""
    text = re.sub(r"\(.*?\)", "", (name or "").lower())
    text = re.sub(r"\b(p\.?\s*a\.?|ps\.?|pompa|bendung|baru|bubble)\b", " ", text)
    return re.sub(r"[^a-z]", "", text)


def km(a, b) -> float:
    dlat = (a[0] - b[0]) * 111.32
    dlon = (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def thin(points: list, tol: float) -> list:
    """Douglas-Peucker on [lat, lon] points."""
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dx, dy) or 1e-12
    far, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = abs(dy * (points[i][0] - a[0]) - dx * (points[i][1] - a[1])) / norm
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [a, b]
    return thin(points[: idx + 1], tol)[:-1] + thin(points[idx:], tol)


def build() -> dict:
    stations = json.loads(STATIONS.read_text(encoding="utf-8"))["stations"]
    features = json.loads(WATERWAYS.read_text(encoding="utf-8"))["features"]
    by_river: dict[str, list] = {}
    for f in features:
        names = [f["properties"].get(k) for k in ("name", "alt_name", "name:en")]
        coords = [[lat, lon] for lon, lat in f["geometry"]["coordinates"]]
        for key in {river_key(n) for n in names if n}:
            by_river.setdefault(key, []).append(coords)

    out = {}
    for s in stations:
        rivers = [r.strip() for r in re.split(r"&", s.get("kali") or "") if r.strip()]
        rivers = [r for r in rivers if r.lower() not in SKIP]
        centre = [s["lat"], s["lon"]]
        lines, matched = [], []
        for river in rivers:
            pieces = by_river.get(river_key(river), [])
            if not pieces:
                continue
            near = [p for p in pieces if any(km(centre, q) <= RADIUS_KM for q in p)]
            lines += near or pieces
            matched.append(river)
        if not lines:
            continue
        out[post_key(s["station_name"])] = {
            "post": s["station_name"],
            "rivers": matched,
            "lines": [[[round(lat, 5), round(lon, 5)] for lat, lon in thin(line, TOLERANCE_DEG)] for line in lines],
        }
    return out


def main() -> int:
    out = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    stations = json.loads(STATIONS.read_text(encoding="utf-8"))["stations"]
    missing = [s["station_name"] for s in stations if post_key(s["station_name"]) not in out]
    print(f"{len(out)} posts with river lines -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    for key, v in out.items():
        print(f"  {v['post']}: {', '.join(v['rivers'])} ({len(v['lines'])} lines)")
    print("no river line:", missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
