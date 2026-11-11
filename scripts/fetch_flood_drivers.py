#!/usr/bin/env python
"""
Fetch the large-scale and land drivers of Jakarta floods named in the literature, for
scripts/thesis_experiments.py (exploratory; nothing here is served). Cached in data/raw/drivers/.

  omi.1x.txt              MJO, NOAA PSL OLR-based MJO index (OMI), daily 1991 onward
                          https://www.psl.noaa.gov/mjo/mjoindex/omi.1x.txt
  oni.ascii.txt           ENSO, NOAA CPC Oceanic Nino Index, monthly (3-month running mean)
                          https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
  soil_<cell>_2012.json   ERA5-Land soil moisture 0-7 cm and 7-28 cm, hourly, per IMERG cell
                          (Open-Meteo archive, no key)
  wind_<point>_2012.json  ERA5 10 m wind at two sea points north of Jakarta (Karimata Strait,
                          Java Sea): the northerly component is a proxy for cross-equatorial
                          northerly (cold) surges

Usage (repo root):  python scripts/fetch_flood_drivers.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.fetch_imerg_history import build_points  # noqa: E402

OUT = _PROJECT_ROOT / "data" / "raw" / "drivers"
START, END = "2012-12-01", "2025-09-30"
SEA_POINTS = {"karimata": (-2.5, 107.5), "javasea": (-5.0, 107.0)}
_UA = {"User-Agent": "deFlood.ai thesis research script"}


def _get(url: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _archive(lat: float, lon: float, hourly: str) -> dict:
    query = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": START, "end_date": END,
                                    "hourly": hourly, "timezone": "GMT"})
    return json.loads(_get(f"https://archive-api.open-meteo.com/v1/archive?{query}"))["hourly"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, url in (("omi.1x.txt", "https://www.psl.noaa.gov/mjo/mjoindex/omi.1x.txt"),
                      ("oni.ascii.txt", "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt")):
        if not (OUT / name).exists():
            (OUT / name).write_bytes(_get(url))
            print("fetched", name)
    for cell in sorted(set(build_points().values())):
        path = OUT / f"soil_{cell}_{START[:4]}.json"
        if not path.exists():
            lat, lon = (float(v) for v in cell.split("_"))
            path.write_text(json.dumps(_archive(lat, lon, "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm")),
                            encoding="utf-8")
            print("fetched", path.name)
            time.sleep(1)
    for name, (lat, lon) in SEA_POINTS.items():
        path = OUT / f"wind_{name}_{START[:4]}.json"
        if not path.exists():
            path.write_text(json.dumps(_archive(lat, lon, "wind_speed_10m,wind_direction_10m")), encoding="utf-8")
            print("fetched", path.name)
            time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
