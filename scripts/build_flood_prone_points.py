"""
Build the Jakarta flood-prone points dataset.

Input : data/raw/data-titik-rawan-bencana_banjir-komponen-data.xls
        (despite the .xls extension this is an HTML <table>; columns:
         periode_data, wilayah, kecamatan, kelurahan, latitude, longitude)
        Coordinates are stored as integer micro-degrees, e.g.
        latitude "-6214879" -> -6.214879, longitude "106819983" -> 106.819983.
Output: app/data/flood_prone_points.json

Run:
    python scripts/build_flood_prone_points.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "data-titik-rawan-bencana_banjir-komponen-data.xls"
_DST = _PROJECT_ROOT / "app" / "data" / "flood_prone_points.json"

# Jakarta bounding box (sanity guard against malformed coordinates).
_LAT_RANGE = (-7.0, -5.5)
_LON_RANGE = (106.0, 107.5)


def _micro_to_deg(raw: str) -> float | None:
    """Convert an integer micro-degree string ('-6214879') to degrees."""
    text = (raw or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        try:
            return float(text)  # already decimal
        except ValueError:
            return None
    return value / 1_000_000.0


def build() -> dict:
    soup = BeautifulSoup(_SRC.read_text(encoding="utf-8", errors="replace"), "html.parser")
    rows = soup.find_all("tr")
    if not rows:
        return {"_meta": {"point_count": 0}, "points": []}

    header = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    idx = {name: header.index(name) for name in
           ("periode_data", "wilayah", "kecamatan", "kelurahan", "latitude", "longitude")
           if name in header}

    points: list[dict] = []
    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < len(header):
            continue
        lat = _micro_to_deg(cells[idx["latitude"]]) if "latitude" in idx else None
        lon = _micro_to_deg(cells[idx["longitude"]]) if "longitude" in idx else None
        if lat is None or lon is None:
            continue
        if not (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1] and _LON_RANGE[0] <= lon <= _LON_RANGE[1]):
            continue
        points.append(
            {
                "wilayah": cells[idx["wilayah"]] if "wilayah" in idx else "",
                "kecamatan": cells[idx["kecamatan"]] if "kecamatan" in idx else "",
                "kelurahan": cells[idx["kelurahan"]] if "kelurahan" in idx else "",
                "lat": round(lat, 6),
                "lon": round(lon, 6),
            }
        )

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/data-titik-rawan-bencana_banjir-komponen-data.xls (HTML table)",
            "point_count": len(points),
            "coordinate_note": "Source latitude/longitude stored as integer micro-degrees; divided by 1e6.",
        },
        "points": points,
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {payload['_meta']['point_count']} flood-prone points -> {_DST}")
    for p in payload["points"][:3]:
        print(f"  {p['kecamatan']} / {p['kelurahan']}  ({p['lat']}, {p['lon']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
