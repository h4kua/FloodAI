"""Daily kecamatan model: shared features, lag choice, serving state and engine wiring."""

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from realtime_native import daily_features as dfe
from realtime_native import daily_model
from services.adaptive_threshold import AdaptiveThresholder


@pytest.fixture(autouse=True)
def _clean_state():
    daily_model._reset_for_tests()
    yield
    daily_model._reset_for_tests()


def test_post_keys_match_archive_and_live_names():
    live = {"P.A. Manggarai 1": "MANGGARAI", "Bendung Katulampa ": "KATULAMPA", "P.S. Depok 1": "DEPOK",
            "Pompa Yos Sudarso 1": "YOSSUDARSO", "Rumah Pompa Pluit 1": "PLUIT", "P.A. Kaliduri 1": "KALIDURI",
            "Bendung. Cibalok - Gadog 1": "CIBALOKGADOG", "P.S. Krukut Hulu 1": "KRUKUTHULU"}
    for name, key in live.items():
        assert dfe.post_key(name) == key
    for archive in ("YOSSUDARSO1", "KALIDURIKALIJODO", "PLUIT", "ANGKEHULU"):
        assert dfe.post_key(archive) in dfe.RIVER_POSTS
    assert dfe.post_key("P.A. Cengkareng Drain") not in dfe.RIVER_POSTS  # not in the archive
    assert dfe.post_key("P.A. Jembatan Merah 1") not in dfe.RIVER_POSTS  # gate-operated


def test_status_level_reads_feed_text():
    assert dfe.status_level("Status : Siaga 2") == 2
    assert dfe.status_level("NORMAL") == 0
    assert np.isnan(dfe.status_level(None)) and np.isnan(dfe.status_level("?"))


def test_wib_daily_rain_needs_most_half_hours():
    # 2 mm/h for every half-hour of WIB 2026-01-02 (= 2026-01-01 17:00 to 2026-01-02 16:30 UTC).
    idx = pd.date_range("2026-01-01 17:00", periods=48, freq="30min", tz="UTC")
    full = dfe.wib_daily_rain(pd.Series(2.0, index=idx))
    assert full.loc[pd.Timestamp("2026-01-02")] == pytest.approx(48.0)
    short = dfe.wib_daily_rain(pd.Series(2.0, index=idx[:40]))
    assert np.isnan(short.loc[pd.Timestamp("2026-01-02")])


def _posts(day, statuses):
    return [(post, pd.Timestamp(day), s) for post, s in statuses.items()]


def test_city_water_drops_thin_days_and_lags():
    river = sorted(dfe.RIVER_POSTS)
    rows = _posts("2026-01-01", {p: 0 for p in river}) + _posts("2026-01-02", {p: 0 for p in river[:5]})
    rows += _posts("2026-01-03", {**{p: 0 for p in river}, "MANGGARAI": 2, "KATULAMPA": 1})
    rows += [("PASARIKAN", pd.Timestamp("2026-01-03"), 3)]  # coastal: ignored
    city = dfe.city_water_by_day(pd.DataFrame(rows, columns=["post", "date", "status"]))
    assert list(city.index) == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-03")]
    assert city.loc["2026-01-03", "w_max"] == 2 and city.loc["2026-01-03", "w_manggarai"] == 2
    assert city.loc["2026-01-03", "w_frac1"] == pytest.approx(2 / len(river))
    feats = dfe.water_features(city, [pd.Timestamp("2026-01-04"), pd.Timestamp("2026-01-03")])
    assert feats.loc[0, "w_max_d1"] == 2 and np.isnan(feats.loc[0, "w_max_d2"])  # 01-02 too thin
    assert np.isnan(feats.loc[1, "w_max_d1"]) and feats.loc[1, "w_max_d2"] == 0


def test_rain_features_use_rain_through_d_minus_lag():
    idx = pd.date_range("2026-01-01", periods=10, freq="D")
    rain = pd.Series(np.arange(10.0), index=idx)
    f = dfe.rain_features(rain, rain * 2, rain * 3, lag=2)
    day = idx[9]
    assert f.loc[day, "rain_lag"] == 7 and f.loc[day, "rain_3"] == 5 + 6 + 7
    assert f.loc[day, "up_bogor_lag"] == 14 and f.loc[day, "up_bogor_3"] == 2 * (5 + 6 + 7)


def test_history_rows_become_city_water():
    river = sorted(dfe.RIVER_POSTS)
    snap = [{"nama_pintu_air": f"P.A. {p.title()} 1", "status_siaga": "Status : Normal"} for p in river]
    snap[0]["status_siaga"] = "Status : Siaga 3"
    rows = [{"fetched_at": "2026-11-12T03:00:00+00:00", "poskobanjir": snap},
            {"fetched_at": "2026-11-12T18:00:00+00:00", "poskobanjir": snap[1:]}]  # 01:00 WIB on the 13th
    city = daily_model.city_water_from_rows(rows)
    assert pd.Timestamp("2026-11-12") in city.index and city.loc["2026-11-12", "w_max"] == 1
    assert pd.Timestamp("2026-11-13") in city.index and city.loc["2026-11-13", "w_max"] == 0


def _synthetic_rain(cells, today, mm, complete_through_lag=2):
    days = pd.date_range(today - pd.Timedelta(days=daily_model.RAIN_DAYS), today, freq="D")
    last = today - pd.Timedelta(days=complete_through_lag)
    daily = {c: pd.Series([mm if d <= last else np.nan for d in days], index=days) for c in cells}
    strict = {c: pd.Series([d <= last for d in days], index=days) for c in cells}
    return daily, strict


def test_choose_lag_takes_the_most_recent_complete_day():
    today = pd.Timestamp("2026-01-20")
    daily, strict = _synthetic_rain(["a", "b"], today, 5.0, complete_through_lag=2)
    assert daily_model.choose_lag(daily, strict, today) == 2
    strict["b"][today - pd.Timedelta(days=2)] = False  # one cell short of 48 half-hours
    assert daily_model.choose_lag(daily, strict, today) == 3
    daily, strict = _synthetic_rain(["a"], today, 5.0, complete_through_lag=4)
    with pytest.raises(daily_model.DailyModelUnavailable):
        daily_model.choose_lag(daily, strict, today)


def test_predict_with_served_bundle_ranks_wet_above_dry():
    bundle = daily_model.load_bundle()
    cells = {k["cell"] for k in bundle["kecamatan"].values()} | set(bundle["upstream_cells"].values())
    today = pd.Timestamp("2026-01-20")
    no_water = pd.DataFrame(columns=dfe.WATER_DAY)
    dry = daily_model.predict(*_synthetic_rain(cells, today, 0.0), no_water, today, bundle)
    wet = daily_model.predict(*_synthetic_rain(cells, today, 60.0), no_water, today, bundle)
    assert len(wet["kecamatan"]) == 42 and wet["lag_days"] == 2 and wet["rain_through"] == "2026-01-18"
    assert all(0.0 <= v["probability"] <= 1.0 for v in wet["kecamatan"].values())
    assert wet["city_probability"] > dry["city_probability"]
    thr = wet["thresholds"]
    assert thr["pre_alert"] <= thr["warning"] <= thr["danger"]


def test_current_only_for_its_wib_date():
    daily_model._state = {"date": "2026-11-13", "city_probability": 0.1}
    assert daily_model.current(datetime(2026, 11, 13, 1, 0, tzinfo=timezone.utc)) is not None
    assert daily_model.current(datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)) is None  # 01:00 WIB on the 14th
    assert daily_model.current("2026-11-12T10:00:00+00:00") is None


def test_current_respects_kill_switch(monkeypatch):
    daily_model._state = {"date": daily_model.wib_date().date().isoformat()}
    monkeypatch.setenv("DAILY_MODEL_ENABLED", "false")
    assert daily_model.current() is None


def test_refresh_without_token_keeps_monthly_model(monkeypatch):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    assert daily_model.refresh() is None
    assert daily_model.current() is None


def test_adaptive_thresholds_take_the_daily_base():
    profile = AdaptiveThresholder().build_thresholds([], {}, 0.5, base=(0.05, 0.12, 0.25))
    assert profile.pre_alert_threshold == 0.05
    assert profile.warning_threshold == 0.12
    assert profile.danger_threshold == 0.25


def test_waspada_from_the_daily_model_is_explained():
    from realtime_native.inference import _risk_interpretation

    daily = {"city_level": "PRE_ALERT", "city_probability": 0.1705, "top_kecamatan": "Jatinegara",
             "rain_through": "2026-11-11"}
    text = _risk_interpretation("PRE_ALERT", {}, daily=daily)
    assert "Hujan beberapa hari terakhir" in text and "17% di Kec. Jatinegara" in text
    assert "Rain over the last few days" in _risk_interpretation("PRE_ALERT", {}, lang="en", daily=daily)
    quiet = _risk_interpretation("PRE_ALERT", {}, daily={**daily, "city_level": "SAFE"})
    assert "Hujan beberapa hari" not in quiet
