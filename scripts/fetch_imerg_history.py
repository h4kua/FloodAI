#!/usr/bin/env python
"""
Download GPM IMERG Final half-hourly rainfall (GPM_3IMERGHH V07, 0.1 degree) as point time
series for the Jakarta kecamatan and two upstream Ciliwung points, December 2019 to 2025-09-30
(the last V07B month). Exploratory input for scripts/hourly_rain_experiment.py; nothing is served.

Source: NASA GES DISC "Giovanni in the Cloud: Time Series" API (it replaced the Hydrology
Data Rods service in late 2025). It needs a free Earthdata login: create a user token at
https://urs.earthdata.nasa.gov (Generate Token) and put it in .env as EARTHDATA_TOKEN=...
The token is read from the environment and never printed.

Each kecamatan centroid (data/processed/cleaned_flood_data_jakarta.csv) is snapped to the
centre of its IMERG cell, so neighbouring kecamatan share one download. Raw CSVs are cached
per cell and year in data/raw/imerg/ (gitignored); data/raw/imerg/points.json maps kecamatan
to cells.

--early fetches IMERG Early (GPM_3IMERGHHE, the near-real-time run the website reads) from Dec 2012
to yesterday into data/raw/imerg_early/, the training rain of scripts/train_daily_live_model.py.

Usage (repo root):
    python scripts/fetch_imerg_history.py                  # all cells, 2020-2025
    python scripts/fetch_imerg_history.py --early          # IMERG Early, Dec 2012 to yesterday
    python scripts/fetch_imerg_history.py --probe          # one day at one cell, to check access
    python scripts/fetch_imerg_history.py --data <id>      # another Giovanni variable id
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from realtime_native.imerg_client import EARLY_DATA_ID, parse_timeseries  # noqa: E402,F401  (re-exported)

CENTROIDS_CSV = _PROJECT_ROOT / "data" / "processed" / "cleaned_flood_data_jakarta.csv"
OUT_DIR = _PROJECT_ROOT / "data" / "raw" / "imerg"
API_URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"
DEFAULT_DATA_ID = "GPM_3IMERGHH_07_precipitation"
EARLY_DIR = _PROJECT_ROOT / "data" / "raw" / "imerg_early"
YEARS = range(2019, 2026)  # 2019 = December only, the lead-in days for 1 Jan 2020
FIRST_DAY = {2019: "2019-12-01T00:00:00"}
LAST_V07B = "2025-09-30T23:59:59"
# Upstream Ciliwung: Katulampa (Bogor) and Depok, where most Jakarta river floods start.
UPSTREAM = {"upstream_bogor": (-6.63, 106.84), "upstream_depok": (-6.40, 106.83)}


def snap(value: float) -> float:
    """Centre of the 0.1-degree IMERG cell that holds ``value`` (cells span x.x0 to x.x0 + 0.1)."""
    return round(math.floor(value * 10) / 10 + 0.05, 2)


def cell_id(lat: float, lon: float) -> str:
    return f"{lat:.2f}_{lon:.2f}"


def build_points() -> dict[str, str]:
    """{kecamatan slug or upstream name: cell id}."""
    centroids = pd.read_csv(CENTROIDS_CSV).groupby("name_3")[["lat", "long"]].first()
    points = {name: cell_id(snap(row.lat), snap(row.long)) for name, row in centroids.iterrows()}
    points.update({name: cell_id(snap(lat), snap(lon)) for name, (lat, lon) in UPSTREAM.items()})
    return points


def fetch(token: str, cell: str, start: str, end: str, data_id: str) -> str:
    lat, lon = (float(x) for x in cell.split("_"))
    params = {"data": data_id, "location": f"[{lat},{lon}]", "time": f"{start}/{end}"}
    for attempt in range(3):
        resp = requests.get(API_URL, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=300)
        if resp.status_code == 200 and resp.text.strip():
            return resp.text
        if resp.status_code in (401, 403):
            raise SystemExit(f"Earthdata refused the token (HTTP {resp.status_code}); "
                             "check EARTHDATA_TOKEN and that GES DISC is an authorized app.")
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"{cell} {start}: HTTP {resp.status_code} {resp.text[:200]!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--data", default=DEFAULT_DATA_ID, help="Giovanni variable id")
    parser.add_argument("--probe", action="store_true", help="fetch one day at one cell and stop")
    parser.add_argument("--history", action="store_true",
                        help="also fetch Dec 2012 to Nov 2019 (BPBD dated events 2013-2019), cached as <cell>_<year>h.csv")
    parser.add_argument("--early", action="store_true",
                        help="fetch IMERG Early (near real time) Dec 2012 to yesterday into data/raw/imerg_early/ instead")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
    except ImportError:
        pass
    token = os.getenv("EARTHDATA_TOKEN", "").strip()
    if not token:
        print("EARTHDATA_TOKEN is not set (.env). Create a token at https://urs.earthdata.nasa.gov.")
        return 1

    points = build_points()
    cells = sorted(set(points.values()))
    if args.probe:
        text = fetch(token, points["kramatjati"], "2020-01-01T00:00:00", "2020-01-01T23:59:59", args.data)
        series = parse_timeseries(text)
        print(f"probe ok: {len(series)} half-hours, total {series.sum() * 0.5:.1f} mm on 2020-01-01 UTC")
        return 0

    if args.early:
        # IMERG Early (about half a day behind real time) is what a live service can read, and it differs
        # from Final (upstream Bogor 2024: 11.1 vs 8.9 mm a day), so the live daily model is trained on Early.
        EARLY_DIR.mkdir(parents=True, exist_ok=True)
        today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        spans = {2012: ("2012-12-01T00:00:00", "2012-12-31T23:59:59"),
                 **{y: (f"{y}-01-01T00:00:00", f"{y}-12-31T23:59:59") for y in range(2013, today.year)},
                 today.year: (f"{today.year}-01-01T00:00:00", f"{(today - pd.Timedelta(days=1)):%Y-%m-%d}T23:59:59")}
        for cell in cells:
            for year, (start, end) in spans.items():
                out = EARLY_DIR / f"{cell}_{year}.csv"
                if out.exists() and year != today.year:
                    continue
                text = fetch(token, cell, start, end, EARLY_DATA_ID)
                rows = len(parse_timeseries(text))
                out.write_text(text, encoding="utf-8")
                print(f"  {cell} {year} (early): {rows} half-hours", flush=True)
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "points.json").write_text(json.dumps(points, indent=2), encoding="utf-8")
    print(f"{len(points)} points -> {len(cells)} IMERG cells")
    if args.history:
        # The "h" files end where the regular cache starts (the 2019 file holds December only).
        spans = {2012: ("2012-12-01T00:00:00", "2012-12-31T23:59:59"),
                 **{y: (f"{y}-01-01T00:00:00", f"{y}-12-31T23:59:59") for y in range(2013, 2019)},
                 2019: ("2019-01-01T00:00:00", "2019-11-30T23:59:59")}
        for cell in cells:
            for year, (start, end) in spans.items():
                out = OUT_DIR / f"{cell}_{year}h.csv"
                if out.exists():
                    continue
                text = fetch(token, cell, start, end, args.data)
                rows = len(parse_timeseries(text))
                out.write_text(text, encoding="utf-8")
                print(f"  {cell} {year} (history): {rows} half-hours", flush=True)
    for cell in cells:
        for year in YEARS:
            out = OUT_DIR / f"{cell}_{year}.csv"
            if out.exists():
                continue
            end = LAST_V07B if year == 2025 else f"{year}-12-31T23:59:59"
            text = fetch(token, cell, FIRST_DAY.get(year, f"{year}-01-01T00:00:00"), end, args.data)
            rows = len(parse_timeseries(text))  # fail before caching a bad body
            out.write_text(text, encoding="utf-8")
            print(f"  {cell} {year}: {rows} half-hours")
    return 0


if __name__ == "__main__":
    sys.exit(main())
