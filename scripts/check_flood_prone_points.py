#!/usr/bin/env python
"""
Check the BPBD flood-prone points (frontend/src/data/floodProneZones.json) against the
kelurahan they are filed under, and move the misplaced ones.

The BPBD export gives each point a kelurahan and coordinates, and a few coordinates are
wrong: "SRENGSENG, Kembangan" sat at -6.1238 / 106.7159, in Kalideres, 9 km from Srengseng,
so a Cengkareng Drain alert lit up a circle by a river that does not pass there.

Each kelurahan is geocoded once with OpenStreetMap Nominatim (cached in
data/raw/kelurahan_geocode_cache.json, one request per second). A point more than
MAX_KM from its kelurahan's centre is moved to that centre and marked
"relocated": true (the map says its place is estimated); its BPBD coordinates stay in
"bpbd_lat"/"bpbd_lon". Kelurahan Nominatim cannot find are left as they are.
Writes the corrected file and artifacts/reports/flood_prone_point_check.md.

Run:  python scripts/check_flood_prone_points.py
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
POINTS = _ROOT / "frontend" / "src" / "data" / "floodProneZones.json"
CACHE = _ROOT / "data" / "raw" / "kelurahan_geocode_cache.json"
REPORT = _ROOT / "artifacts" / "reports" / "flood_prone_point_check.md"
MAX_KM = 3.0
_UA = "deFlood-thesis-data-check/1.0"


def km(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111.32, (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0])))


def geocode(kelurahan: str, kecamatan: str, wilayah: str, cache: dict) -> list | None:
    key = f"{kelurahan}|{kecamatan}"
    if key in cache:
        return cache[key]
    kota = wilayah.replace("KOTA ADM.", "").replace("KAB. ADM.", "").strip().title()
    query = urllib.parse.urlencode({
        "q": f"{kelurahan.title()}, {kecamatan.title()}, {kota}, Indonesia",
        "format": "json", "limit": 1, "countrycodes": "id",
    })
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{query}", headers={"User-Agent": _UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                hits = json.load(resp)
            break
        except OSError:  # 503 "first byte timeout" and the like: wait and retry
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    time.sleep(1.1)  # Nominatim usage policy: at most one request a second
    cache[key] = [float(hits[0]["lat"]), float(hits[0]["lon"])] if hits else None
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return cache[key]


def main() -> int:
    data = json.loads(POINTS.read_text(encoding="utf-8"))
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    moved, unknown = [], []
    for p in data["points"]:
        lat, lon = p.get("bpbd_lat", p["lat"]), p.get("bpbd_lon", p["lon"])  # re-runs start from BPBD's place
        centre = geocode(p["kelurahan"], p["kecamatan"], p.get("wilayah", ""), cache)
        if centre is None:
            unknown.append(p["kelurahan"])
            continue
        d = km((lat, lon), centre)
        if d > MAX_KM:
            p.update({"bpbd_lat": lat, "bpbd_lon": lon, "lat": round(centre[0], 6), "lon": round(centre[1], 6),
                      "relocated": True})
            moved.append((p["kelurahan"], p["kecamatan"], round(d, 1)))
        else:
            for k in ("bpbd_lat", "bpbd_lon", "relocated"):
                p.pop(k, None)
            p["lat"], p["lon"] = lat, lon
    data["_meta"]["relocated"] = len(moved)
    data["_meta"]["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    POINTS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# BPBD flood-prone points vs their kelurahan", "",
             f"Generated {data['_meta']['checked_at']} by `scripts/check_flood_prone_points.py`. "
             f"{len(data['points'])} points; kelurahan centres from OpenStreetMap Nominatim.", "",
             f"Points more than {MAX_KM:g} km from their own kelurahan, moved to its centre: {len(moved)}", "",
             "| Kelurahan | Kecamatan | Distance from its kelurahan (km) |", "|---|---|---|"]
    lines += [f"| {k.title()} | {c.title()} | {d} |" for k, c, d in sorted(moved, key=lambda m: -m[2])]
    lines += ["", f"Kelurahan Nominatim could not find (left as BPBD gave them): {', '.join(sorted(set(unknown))) or 'none'}"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
