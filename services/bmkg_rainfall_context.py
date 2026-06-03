"""
BMKG daily rainfall context — reads processed bmkg_daily_rainfall.csv and
provides recent rainfall summaries for Jakarta stations.

Used by the feature builder to supplement OpenWeather when current rain = 0mm
but recent BMKG daily totals indicate meaningful recent precipitation.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from api.observability import get_logger

_log = get_logger("flood.bmkg_rainfall_context")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
BMKG_RAINFALL_CSV = _PROJECT_ROOT / "data" / "processed" / "bmkg_daily_rainfall.csv"

# Jakarta station WMO IDs
_JAKARTA_WMO = {"96745", "96741", "96747"}


@lru_cache(maxsize=1)
def _load_rainfall_df() -> Optional[pd.DataFrame]:
    try:
        if not BMKG_RAINFALL_CSV.exists():
            _log.warning("bmkg_rainfall_csv_missing", path=str(BMKG_RAINFALL_CSV))
            return None
        df = pd.read_csv(BMKG_RAINFALL_CSV, parse_dates=["date"])
        df = df[df["wmo_id"].astype(str).isin(_JAKARTA_WMO)].copy()
        _log.info("bmkg_rainfall_loaded", rows=len(df))
        return df
    except Exception as exc:
        _log.warning("bmkg_rainfall_load_failed", error=str(exc))
        return None


def get_recent_daily_rainfall(
    reference_date: Optional[date] = None,
    lookback_days: int = 7,
) -> dict:
    """
    Return a summary of recent BMKG daily rainfall for Jakarta stations.

    Args:
        reference_date: The date to look back from (default: today).
        lookback_days: How many days to look back (default: 7).

    Returns dict with:
        yesterday_mm   — average across stations for the day before reference_date
        last_7d_avg_mm — 7-day average daily rainfall across Jakarta stations
        last_7d_max_mm — maximum single-day total in the window
        last_available_date — most recent date with data (ISO string)
        data_available — True if BMKG data was loadable
    """
    df = _load_rainfall_df()
    if df is None or df.empty:
        return _empty_context()

    if reference_date is None:
        reference_date = date.today()

    cutoff = pd.Timestamp(reference_date - timedelta(days=lookback_days))
    ref_ts = pd.Timestamp(reference_date)
    yesterday_ts = pd.Timestamp(reference_date - timedelta(days=1))

    window = df[(df["date"] >= cutoff) & (df["date"] < ref_ts)].dropna(subset=["rr_mm"])

    if window.empty:
        return _empty_context()

    # Average per day across all stations, then summarise
    daily_avg = window.groupby("date")["rr_mm"].mean()
    last_available = window["date"].max()

    yesterday_data = window[window["date"] == yesterday_ts]
    yesterday_mm = float(yesterday_data["rr_mm"].mean()) if not yesterday_data.empty else None

    # Also try the most recent available day as fallback
    if yesterday_mm is None and not daily_avg.empty:
        yesterday_mm = float(daily_avg.iloc[-1])

    return {
        "yesterday_mm": round(yesterday_mm, 1) if yesterday_mm is not None else None,
        "last_7d_avg_mm": round(float(daily_avg.mean()), 2),
        "last_7d_max_mm": round(float(daily_avg.max()), 1),
        "last_available_date": last_available.date().isoformat() if hasattr(last_available, "date") else str(last_available),
        "data_available": True,
        "lookback_days": lookback_days,
    }


def _empty_context() -> dict:
    return {
        "yesterday_mm": None,
        "last_7d_avg_mm": 0.0,
        "last_7d_max_mm": 0.0,
        "last_available_date": None,
        "data_available": False,
        "lookback_days": 7,
    }
