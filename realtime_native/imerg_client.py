"""
GPM IMERG point time series from NASA's Giovanni time-series API, for the daily kecamatan model.

Needs an Earthdata user token in the environment (EARTHDATA_TOKEN); it is sent as a bearer header
and never logged. scripts/fetch_imerg_history.py uses the same parser for the training archive.
"""

from __future__ import annotations

import io
import os

import pandas as pd
import requests

API_URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"
EARLY_DATA_ID = "GPM_3IMERGHHE_07_precipitation"


class ImergUnavailable(RuntimeError):
    """No token, refused token, or no usable answer from Giovanni."""


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


def fetch_rate(cell: str, start: pd.Timestamp, end: pd.Timestamp, *, data_id: str = EARLY_DATA_ID,
               token: str | None = None, timeout: float = 60.0) -> pd.Series:
    """Half-hourly rate for one 0.1-degree cell ('lat_lon' of its centre) between two UTC times."""
    token = (token if token is not None else os.getenv("EARTHDATA_TOKEN", "")).strip()
    if not token:
        raise ImergUnavailable("EARTHDATA_TOKEN is not set")
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
