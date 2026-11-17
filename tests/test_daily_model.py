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


# ---------------------------------------------------------------- GES DISC files

from realtime_native import imerg_client  # noqa: E402

CELLS = ["-6.15_106.85", "-6.65_106.85"]


def _subset_text(values_by_lon):
    rows = [f"precipitation[0][{i}], " + ", ".join(str(v) for v in col) for i, col in enumerate(values_by_lon)]
    return "Dataset: x\n" + "\n".join(rows) + "\nlat, -6.65, -6.55, -6.45, -6.35, -6.25, -6.15\n"


def test_parse_subset_picks_each_cell_from_the_box():
    # Box: lon index 2868 only, lat indices 833 (-6.65) .. 838 (-6.15).
    text = _subset_text([[4.0, 0, 0, 0, 0, -9999.9]])
    got = imerg_client.parse_subset(text, CELLS, lon0=2868, lat0=833)
    assert got["-6.65_106.85"] == 4.0 and np.isnan(got["-6.15_106.85"])


def test_fetch_recent_reads_new_files_once(monkeypatch):
    listing = ('<a href="3B-HHR-E.MS.MRG.3IMERG.20261116-S233000-E235959.1410.V07C.HDF5">'
               '<a href="3B-HHR-E.MS.MRG.3IMERG.20261116-S230000-E232959.1380.V07C.HDF5">')
    calls = []

    def fake_get(url, token, timeout):
        calls.append(url)
        if "/data/" in url:
            return listing if "/320/" in url else ""
        return _subset_text([[1.5, 0, 0, 0, 0, 2.5]])

    monkeypatch.setattr(imerg_client, "_get", fake_get)
    cache = {}
    start, end = pd.Timestamp("2026-11-16 23:00", tz="UTC"), pd.Timestamp("2026-11-17 01:00", tz="UTC")
    got = imerg_client.fetch_recent(CELLS, start, end, token="t", cache=cache)
    assert list(got["-6.15_106.85"]) == [2.5, 2.5] and list(got["-6.65_106.85"]) == [1.5, 1.5]
    assert got["-6.15_106.85"].index[0] == pd.Timestamp("2026-11-16 23:00", tz="UTC")
    opendap = [u for u in calls if "/opendap/" in u]
    assert len(opendap) == 2 and "precipitation[0:0][2868:2868][833:838]" in opendap[0]
    calls.clear()
    imerg_client.fetch_recent(CELLS, start, end, token="t", cache=cache)
    assert not [u for u in calls if "/opendap/" in u]  # cached


def _giovanni(last):
    idx = pd.date_range("2026-11-15 17:00", last, freq="30min", tz="UTC")
    return pd.Series(1.0, index=idx)


def test_recent_files_complete_yesterday(monkeypatch):
    seen = {}

    def fake_recent(cells, start, end, cache=None):
        seen["start"] = start
        idx = pd.date_range(start, end, freq="30min", inclusive="left")
        return {c: pd.Series(2.0, index=idx) for c in cells}

    monkeypatch.setattr(daily_model, "fetch_recent", fake_recent)
    rates = {c: _giovanni("2026-11-16 08:00") for c in CELLS}
    rates[CELLS[1]] = _giovanni("2026-11-16 10:00")
    out = daily_model._with_recent_files(rates, CELLS, pd.Timestamp("2026-11-15 17:00", tz="UTC"),
                                         pd.Timestamp("2026-11-17 05:00", tz="UTC"))
    assert seen["start"] == pd.Timestamp("2026-11-16 08:30", tz="UTC")  # after the earliest last value
    strict = daily_model._strict_days(out[CELLS[0]])
    assert bool(strict.get(pd.Timestamp("2026-11-16"), False))  # WIB 16 Nov now has all 48 half-hours
    assert out[CELLS[1]].loc["2026-11-16 09:00+00:00"] == 1.0  # Giovanni wins where both exist


def test_recent_files_failure_keeps_giovanni(monkeypatch):
    def broken(*a, **k):
        raise imerg_client.ImergUnavailable("GES DISC answered HTTP 503")

    monkeypatch.setattr(daily_model, "fetch_recent", broken)
    rates = {c: _giovanni("2026-11-16 08:00") for c in CELLS}
    out = daily_model._with_recent_files(rates, CELLS, pd.Timestamp("2026-11-15 17:00", tz="UTC"),
                                         pd.Timestamp("2026-11-17 05:00", tz="UTC"))
    assert out is rates


def test_fetch_recent_skips_a_file_not_served_yet(monkeypatch):
    listing = ('<a href="3B-HHR-E.MS.MRG.3IMERG.20261116-S233000-E235959.1410.V07C.HDF5">'
               '<a href="3B-HHR-E.MS.MRG.3IMERG.20261116-S230000-E232959.1380.V07C.HDF5">')

    def fake_get(url, token, timeout):
        if "/data/" in url:
            return listing if "/320/" in url else ""
        return "Error: not ready" if "S233000" in url else _subset_text([[1.5, 0, 0, 0, 0, 2.5]])

    monkeypatch.setattr(imerg_client, "_get", fake_get)
    cache = {}
    got = imerg_client.fetch_recent(CELLS, pd.Timestamp("2026-11-16 23:00", tz="UTC"),
                                    pd.Timestamp("2026-11-17 01:00", tz="UTC"), token="t", cache=cache)
    assert list(got["-6.65_106.85"]) == [1.5] and len(cache) == 1  # the other half-hour is retried later
