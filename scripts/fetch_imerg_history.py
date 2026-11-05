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

Usage (repo root):
    python scripts/fetch_imerg_history.py                  # all cells, 2020-2025
    python scripts/fetch_imerg_history.py --probe          # one day at one cell, to check access
    python scripts/fetch_imerg_history.py --data <id>      # another Giovanni variable id
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
CENTROIDS_CSV = _PROJECT_ROOT / "data" / "processed" / "cleaned_flood_data_jakarta.csv"
OUT_DIR = _PROJECT_ROOT / "data" / "raw" / "imerg"
API_URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"
DEFAULT_DATA_ID = "GPM_3IMERGHH_07_precipitation"
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


def parse_timeseries(text: str) -> pd.Series:
    """Giovanni CSV -> half-hourly precipitation series (UTC index). The body starts with
    key,value metadata lines, then a header row whose first field is the timestamp."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.lower().startswith("timestamp")), None)
    if start is None:
        raise ValueError("no data rows in the response (check the variable id, the bounds or the token)")
    frame = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    frame.columns = ["time", "value"] + list(frame.columns[2:])
    series = pd.Series(pd.to_numeric(frame["value"], errors="coerce").to_numpy(),
                       index=pd.to_datetime(frame["time"], utc=True))
    return series.where(series >= 0)  # fill values are negative


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

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "points.json").write_text(json.dumps(points, indent=2), encoding="utf-8")
    print(f"{len(points)} points -> {len(cells)} IMERG cells")
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
