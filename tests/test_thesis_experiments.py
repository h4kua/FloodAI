"""Helpers of scripts/thesis_experiments.py: Siaga levels and day scoring."""

import pandas as pd

from scripts.thesis_experiments import TMA_TO_FEED, day_metrics, siaga_level

MANGGARAI = {"siaga3": 750.0, "siaga2": 850.0, "siaga1": 950.0}


def test_siaga_level_uses_the_post_limits():
    assert siaga_level(650, MANGGARAI) == 0
    assert siaga_level(750, MANGGARAI) == 1
    assert siaga_level(860, MANGGARAI) == 2
    assert siaga_level(950, MANGGARAI) == 3
    assert siaga_level(float("nan"), MANGGARAI) == 0  # a missing reading never raises a warning


def test_day_metrics_counts_same_day_and_day_before():
    days = pd.date_range("2025-01-01", periods=5)
    warn = pd.Series([True, False, False, True, False], index=days)
    flood = pd.Series([True, True, False, False, False], index=days)
    m = day_metrics(warn, flood)
    assert m["recall"] == 0.5  # only 1 Jan was warned on the day
    assert m["recall_same_or_day_before"] == 1.0  # 2 Jan was warned the day before
    assert m["precision"] == 0.5 and m["false_alarm_days"] == 1


def test_every_mapped_post_has_limits_in_the_feed_file():
    import json

    from scripts.thesis_experiments import SIAGA_JSON

    feed = {p["name"] for p in json.loads(SIAGA_JSON.read_text(encoding="utf-8"))["posts"]}
    assert set(TMA_TO_FEED.values()) <= feed
