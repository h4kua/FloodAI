"""Unit tests for the hourly rain experiment helpers (no network, no model training)."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.fetch_imerg_history import cell_id, parse_timeseries, snap
from scripts.hourly_rain_experiment import _dates_in, daily_rain_features


@pytest.mark.parametrize("value, centre", [(-6.27, -6.25), (-6.20, -6.15), (106.85, 106.85), (106.899, 106.85)])
def test_snap_returns_the_imerg_cell_centre(value, centre):
    assert snap(value) == centre


def test_cell_id_is_stable_text():
    assert cell_id(snap(-6.27), snap(106.89)) == "-6.25_106.85"


def test_parse_timeseries_skips_metadata_and_masks_fill_values():
    body = "\n".join([
        "prod_name,GPM_3IMERGHH",
        "param_name,precipitation",
        "unit,mm/hr",
        "Timestamp (UTC),precipitation",
        "2020-01-01T00:00:00,4.0",
        "2020-01-01T00:30:00,-9999.9",
    ])
    series = parse_timeseries(body)
    assert list(series.index) == list(pd.to_datetime(["2020-01-01T00:00:00", "2020-01-01T00:30:00"], utc=True))
    assert series.iloc[0] == 4.0 and pd.isna(series.iloc[1])


def test_parse_timeseries_rejects_an_empty_body():
    with pytest.raises(ValueError):
        parse_timeseries("prod_name,GPM_3IMERGHH\nparam_name,precipitation\n")


@pytest.mark.parametrize("text, days", [
    ("22 Oktober", [22]),
    ("30,31 Oktober", [30, 31]),
    ("17, 29, 30 Oktober", [17, 29, 30]),
    ("4-6 Desember", [4, 5, 6]),
    ("tgl. 31 Februari", []),
    (None, []),
])
def test_dates_in_reads_the_day_numbers(text, days):
    month = 12 if text and "Desember" in text else 10
    if text and "Februari" in text:
        month = 2
    assert [d.day for d in _dates_in(text, 2025, month)] == days


def test_daily_rain_features_use_wib_days_and_rolling_windows():
    # 21:00-23:00 UTC on 31 Dec is 04:00-06:00 WIB on 1 Jan.
    index = pd.date_range("2019-12-31T21:00", periods=3, freq="1h", tz="UTC")
    frame = daily_rain_features(pd.Series([12.0, 6.0, 3.0], index=index))
    day = frame.loc[pd.Timestamp("2020-01-01")]
    assert day["d0"] == 21.0
    assert day["max1h"] == 12.0
    assert day["max3h"] == 21.0
    assert day["hours10"] == 1.0
