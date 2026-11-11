"""Cleaning helpers of scripts/dsda_history.py (DSDA water levels 2016-2021)."""

import math

import pandas as pd

from scripts.dsda_history import parse_time, post_key, status_level


def test_post_names_from_different_years_share_one_key():
    assert post_key("P.A. MANGGARAI") == post_key("PS. MANGGARAI") == "MANGGARAI"
    assert post_key("PS. KATULAMPA (HULU)") == post_key("Bendung. Katulampa") == "KATULAMPA"
    assert post_key("P.A. ANCOL FLUSING") == post_key("FLUSHING ANCOL") == "ANCOLFLUSHING"
    assert post_key("P.A. ISTIQAL") == "ISTIQLAL"


def test_official_status_in_both_spellings():
    assert status_level("STATUS : SIAGA 3") == status_level("SIAGA 3") == 1
    assert status_level("SIAGA 1") == 3 and status_level("NORMAL") == 0
    assert math.isnan(status_level(None)) and math.isnan(status_level("RUSAK"))


def test_three_date_formats_and_empty_dates():
    assert parse_time("01/02/2018 03:10") == pd.Timestamp("2018-02-01 03:10")  # day first
    assert parse_time("2017-08-02 14:00:00") == pd.Timestamp("2017-08-02 14:00")
    assert parse_time("15/03/2019") == pd.Timestamp("2019-03-15")
    assert parse_time(None) is None and parse_time("0000-00-00 00:00:00") is None
