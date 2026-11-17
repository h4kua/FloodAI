"""
GPM IMERG Early rain for the daily kecamatan model, from two NASA sources:

- Giovanni's time-series API (fetch_rate): one request per cell for any period, but it serves Early
  about 28 h after the rain. scripts/fetch_imerg_history.py built the training archive from it.
- The half-hourly Early files at GES DISC (fetch_recent): about 4.5 h after the rain, read through
  OPeNDAP as a few grid cells around Jakarta per file. Same values as Giovanni (checked 2026-11-17 on
  all 9 model cells, every half-hour of 15 Nov), so they fill the hours Giovanni does not have yet.

Both need an Earthdata user token in the environment (EARTHDATA_TOKEN); it is sent as a bearer header
and never logged.
"""

from __future__ import annotations

import io
import os
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

API_URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"
EARLY_DATA_ID = "GPM_3IMERGHHE_07_precipitation"
GESDISC = "https://gpm1.gesdisc.eosdis.nasa.gov"
EARLY_DIR = "GPM_L3/GPM_3IMERGHHE.07/{year}/{doy:03d}/"
FILE_RE = re.compile(r"3B-HHR-E\.MS\.MRG\.3IMERG\.(\d{8})-S(\d{6})-E\d{6}\.\d{4}\.V\w+\.HDF5")
GRID_LON0, GRID_LAT0, GRID_STEP = -179.95, -89.95, 0.1  # centres of the 3600 x 1800 grid


class ImergUnavailable(RuntimeError):
    """No token, refused token, or no usable answer from Giovanni or GES DISC."""


def parse_timeseries(text: str) -> pd.Series:
    """Giovanni CSV -> half-hourly precipitation rate in mm/h (UTC index). The body starts with
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


def _token(token: str | None) -> str:
    token = (token if token is not None else os.getenv("EARTHDATA_TOKEN", "")).strip()
    if not token:
        raise ImergUnavailable("EARTHDATA_TOKEN is not set")
    return token


def fetch_rate(cell: str, start: pd.Timestamp, end: pd.Timestamp, *, data_id: str = EARLY_DATA_ID,
               token: str | None = None, timeout: float = 60.0) -> pd.Series:
    """Half-hourly rate for one 0.1-degree cell ('lat_lon' of its centre) between two UTC times."""
    token = _token(token)
    lat, lon = (float(x) for x in cell.split("_"))
    params = {"data": data_id, "location": f"[{lat},{lon}]",
              "time": f"{start:%Y-%m-%dT%H:%M:%S}/{end:%Y-%m-%dT%H:%M:%S}"}
    try:
        resp = requests.get(API_URL, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    except requests.RequestException as exc:
        raise ImergUnavailable(f"Giovanni request failed: {type(exc).__name__}") from exc
    if resp.status_code in (401, 403):
        raise ImergUnavailable(f"Earthdata refused the token (HTTP {resp.status_code})")
    if resp.status_code != 200 or not resp.text.strip():
        raise ImergUnavailable(f"Giovanni answered HTTP {resp.status_code}")
    try:
        return parse_timeseries(resp.text)
    except ValueError as exc:
        raise ImergUnavailable(str(exc)) from exc


# ---------------------------------------------------------------- GES DISC files

def _get(url: str, token: str, timeout: float) -> str:
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=timeout)
    except requests.RequestException as exc:
        raise ImergUnavailable(f"GES DISC request failed: {type(exc).__name__}") from exc
    if resp.status_code in (401, 403):
        raise ImergUnavailable(f"Earthdata refused the token (HTTP {resp.status_code})")
    if resp.status_code == 404:
        return ""  # day directory not created yet
    if resp.status_code != 200:
        raise ImergUnavailable(f"GES DISC answered HTTP {resp.status_code}")
    return resp.text


def list_early_files(day: pd.Timestamp, token: str, timeout: float = 60.0) -> dict[pd.Timestamp, str]:
    """{half-hour start (UTC): file name} of the Early files of one UTC day."""
    url = f"{GESDISC}/data/" + EARLY_DIR.format(year=day.year, doy=day.dayofyear)
    found = {}
    for m in FILE_RE.finditer(_get(url, token, timeout)):
        found[pd.Timestamp(m.group(1) + m.group(2), tz="UTC")] = m.group(0)
    return found


def _index(value: float, origin: float) -> int:
    return int(round((value - origin) / GRID_STEP))


def parse_subset(text: str, cells: list[str], lon0: int, lat0: int) -> dict[str, float]:
    """OPeNDAP ASCII of precipitation[0][lon0:..][lat0:..] -> {cell: mm/h} (fill values -> NaN)."""
    grid = [[float(x) for x in line.split(",")[1:]] for line in text.splitlines() if line.startswith("precipitation[")]
    if not grid:
        raise ImergUnavailable("GES DISC subset had no precipitation rows")
    out = {}
    for cell in cells:
        lat, lon = (float(x) for x in cell.split("_"))
        value = grid[_index(lon, GRID_LON0) - lon0][_index(lat, GRID_LAT0) - lat0]
        out[cell] = value if value >= 0 else float("nan")
    return out


def fetch_recent(cells: list[str], start: pd.Timestamp, end: pd.Timestamp, *, token: str | None = None,
                 cache: dict | None = None, timeout: float = 60.0, workers: int = 4) -> dict[str, pd.Series]:
    """Half-hourly rate per cell from the GES DISC Early files whose half-hour starts in [start, end)
    (UTC). ``cache`` ({half-hour: {cell: rate}}) keeps files already read; Early files do not change."""
    token = _token(token)
    cache = {} if cache is None else cache
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    lats = [float(c.split("_")[0]) for c in cells]
    lons = [float(c.split("_")[1]) for c in cells]
    lon0, lon1 = _index(min(lons), GRID_LON0), _index(max(lons), GRID_LON0)
    lat0, lat1 = _index(min(lats), GRID_LAT0), _index(max(lats), GRID_LAT0)
    wanted = {}
    for day in pd.date_range(start.floor("D"), end.floor("D"), freq="D"):
        for ts, name in list_early_files(day, token, timeout).items():
            if start <= ts < end and ts not in cache:
                wanted[ts] = name

    def one(item):
        ts, name = item
        url = (f"{GESDISC}/opendap/" + EARLY_DIR.format(year=ts.year, doy=ts.dayofyear) + name
               + f".ascii?precipitation[0:0][{lon0}:{lon1}][{lat0}:{lat1}]")
        return ts, parse_subset(_get(url, token, timeout), cells, lon0, lat0)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ts, values in pool.map(one, sorted(wanted.items())):
            cache[ts] = values
    stamps = sorted(ts for ts in cache if start <= ts < end)
    return {c: pd.Series([cache[ts].get(c, np.nan) for ts in stamps], index=pd.DatetimeIndex(stamps), dtype=float)
            for c in cells}
