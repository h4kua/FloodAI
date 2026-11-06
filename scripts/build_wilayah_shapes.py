"""Build the outlines of Jakarta's five mainland kota for the home map's weather layer.

Each outline comes from OpenStreetMap through Nominatim (polygon_threshold
simplifies it server side), is rounded to 4 decimals (~10 m) and written to
frontend/src/data/wilayahShapes.json, keyed by the names the frontend uses
(Utara, Barat, Pusat, Selatan, Timur). Kepulauan Seribu is left out: the map
does not show it.

    python scripts/build_wilayah_shapes.py
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "frontend" / "src" / "data" / "wilayahShapes.json"
_UA = "deFlood-thesis-data-check/1.0"
KOTA = {
    "Utara": "Jakarta Utara",
    "Barat": "Jakarta Barat",
    "Pusat": "Jakarta Pusat",
    "Selatan": "Jakarta Selatan",
    "Timur": "Jakarta Timur",
}


def fetch(name: str) -> dict:
    query = urllib.parse.urlencode({
        "q": f"{name}, DKI Jakarta, Indonesia", "format": "jsonv2", "limit": 5,
        "polygon_geojson": 1, "polygon_threshold": 0.0008,
    })
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{query}", headers={"User-Agent": _UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                hits = json.load(res)
            break
        except OSError:
            if attempt == 2:
                raise
            time.sleep(5)
    for hit in hits:
        if hit.get("geojson", {}).get("type") in ("Polygon", "MultiPolygon") and hit.get("category") == "boundary":
            return hit["geojson"]
    raise SystemExit(f"no boundary polygon for {name}")


def rings(geometry: dict) -> list:
    """Outer rings as [[lat, lon], ...], largest first; islands under 1 km² dropped."""
    polys = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    out = []
    for poly in polys:
        ring = [[round(lat, 4), round(lon, 4)] for lon, lat in poly[0]]
        # Shoelace area in degrees² (~ 1.2e10 m² per degree² at Jakarta's latitude).
        area = abs(sum(a[1] * b[0] - b[1] * a[0] for a, b in zip(ring, ring[1:]))) / 2
        if area * 1.2e10 >= 1e6:
            out.append((area, ring))
    return [ring for _, ring in sorted(out, reverse=True)]


def build() -> None:
    shapes = {}
    for key, name in KOTA.items():
        shapes[key] = rings(fetch(name))
        print(key, [len(r) for r in shapes[key]])
        time.sleep(1.1)  # Nominatim: at most one request a second
    OUT.write_text(json.dumps(shapes, separators=(",", ":")), encoding="utf-8")
    print(f"-> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build()
