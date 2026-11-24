"""History endpoints for the Riwayat page, the decision log and the Telegram alert rule."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from realtime_native import daily_model
from services import history_service, telegram_alerts


@pytest.fixture(autouse=True)
def _clean():
    history_service._reset_cache_for_tests()
    daily_model._reset_for_tests()
    yield
    history_service._reset_cache_for_tests()
    daily_model._reset_for_tests()


def test_compact_decision_keeps_the_chance_only_when_the_layer_decided():
    result = {"risk_level": "PRE_ALERT", "decision": {"layer": "L3_LEARNED"},
              "decision_layer": {"score": 0.4392, "decided": True},
              "daily_model": {"city_probability": 0.07, "lag_days": 1, "top_kecamatan": "Jatinegara"}}
    row = history_service.compact_decision(result, "2026-11-17T13:30:00+00:00")
    assert row == {"t": "2026-11-17T13:30:00+00:00", "level": "PRE_ALERT", "layer": "L3_LEARNED", "chance": 0.4392,
                   "daily_p": 0.07, "lag": 1, "top": "Jatinegara", "source": "live"}
    ruled = history_service.compact_decision({**result, "decision_layer": {"score": 0.9, "decided": False}}, "t")
    assert ruled["chance"] is None


def _d(t, level, chance=None):
    return {"t": t, "level": level, "chance": chance}


def test_warning_periods_join_consecutive_snapshots_and_split_on_gaps():
    ds = [_d("2026-11-10T00:00:00+00:00", "SAFE"), _d("2026-11-10T00:15:00+00:00", "PRE_ALERT", 0.25),
          _d("2026-11-10T00:30:00+00:00", "WARNING", 0.7), _d("2026-11-10T00:45:00+00:00", "PRE_ALERT", 0.3),
          _d("2026-11-10T01:00:00+00:00", "SAFE"), _d("2026-11-10T05:00:00+00:00", "PRE_ALERT", 0.22)]
    periods = history_service.warning_periods(ds)
    assert len(periods) == 2  # newest first
    assert periods[1]["start"] == "2026-11-10T00:15:00+00:00" and periods[1]["end"] == "2026-11-10T00:45:00+00:00"
    assert periods[1]["peak_level"] == "WARNING" and periods[1]["peak_chance"] == 0.7 and periods[1]["snapshots"] == 3
    gap = [_d("2026-11-10T00:00:00+00:00", "PRE_ALERT"), _d("2026-11-10T03:00:00+00:00", "PRE_ALERT")]
    assert len(history_service.warning_periods(gap)) == 2  # a 3-hour hole ends a period


ROWS = [
    {"fetched_at": "2026-11-16T23:00:00+00:00", "poskobanjir": [
        {"nama_pintu_air": "P.A. Manggarai 1", "tinggi_air": "780", "siaga3": "750", "siaga2": "850", "siaga1": "950",
         "status_siaga": "Status : Siaga 3"},
        {"nama_pintu_air": "Pompa Cideng 1", "tinggi_air": "10", "status_siaga": "Normal"}]},
    {"fetched_at": "2026-11-17T03:00:00+00:00", "poskobanjir": [
        {"nama_pintu_air": "P.A. Manggarai 1", "tinggi_air": "700", "siaga3": "750", "siaga2": "850", "siaga1": "950",
         "status_siaga": "Status : Normal"}]},
]


def test_post_series_and_daily_bands(monkeypatch):
    monkeypatch.setattr(history_service, "_post_rows", lambda days: ROWS)
    series = history_service.post_series("P.A. Manggarai 1", 2)
    assert [p["cm"] for p in series["points"]] == [780.0, 700.0]
    assert [p["status"] for p in series["points"]] == [1, 0]
    assert series["limits"] == {"siaga3": 750.0, "siaga2": 850.0, "siaga1": 950.0}
    daily = history_service.posts_daily(2)
    assert daily == {"P.A. Manggarai 1": {"2026-11-17": 1}}  # both readings are 17 Nov in WIB; the pump has no limits


def test_rain_summary_from_the_daily_model_cache():
    bundle = daily_model.load_bundle()
    cells = sorted({k["cell"] for k in bundle["kecamatan"].values()} | set(bundle["upstream_cells"].values()))
    idx = pd.date_range("2026-11-14", "2026-11-16", freq="D")
    daily = {c: pd.Series([1.0, np.nan, 3.0], index=idx) for c in cells}
    daily[cells[0]] = pd.Series([5.0, np.nan, 9.0], index=idx)
    daily_model._rain_cache.update(fetched=None, start=None, daily=daily, strict={},
                                   today={c: {"00:00": 0.5, "00:30": 0.5} for c in cells})
    out = daily_model.rain_summary(14)
    assert [d["date"] for d in out["days"]] == ["2026-11-14", "2026-11-16"]  # the empty day is left out
    assert out["days"][1]["jakarta_max"] == 9.0 and out["today"]["jakarta_mean"] == 1.0 and out["today"]["through"] == "00:30"
    daily_model._reset_for_tests()
    assert daily_model.rain_summary(14) is None


def test_endpoints(monkeypatch):
    from api.main import app

    monkeypatch.setattr(history_service, "summary", lambda days: {"days": days, "decisions": []})
    monkeypatch.setattr(history_service, "post_series", lambda name, days: {"name": name, "days": days, "points": []})
    client = TestClient(app)
    assert client.get("/history/summary?days=7").json() == {"days": 7, "decisions": []}
    assert client.get("/history/post?name=P.A.%20Manggarai%201&days=2").json()["name"] == "P.A. Manggarai 1"
    assert client.get("/history/summary?days=90").status_code == 422


def test_telegram_message_rules():
    msg = telegram_alerts.decide_message
    assert "naik ke SIAGA" in msg("WARNING", "PRE_ALERT", "x", "WARNING")
    assert "naik ke BAHAYA" in msg("DANGER", "WARNING", "x", "WARNING")
    assert msg("PRE_ALERT", "SAFE", "x", "WARNING") is None  # below the announced level
    assert msg("WARNING", "WARNING", "x", "WARNING") is None  # no change
    assert "turun ke Waspada" in msg("PRE_ALERT", "DANGER", "x", "WARNING")
    assert msg("UNKNOWN", "SAFE", "x", "WARNING") is None


def test_telegram_sends_once_and_remembers(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@c")
    state, sent = {"level": "SAFE"}, []
    monkeypatch.setattr(telegram_alerts, "_load_last", lambda: state["level"])
    monkeypatch.setattr(telegram_alerts, "_save_last", lambda level: state.update(level=level))
    monkeypatch.setattr(telegram_alerts, "send", lambda text: sent.append(text) or True)
    result = {"risk_level": "WARNING", "risk_interpretation": "Siaga. ..."}
    assert telegram_alerts.maybe_notify(result) and len(sent) == 1
    assert telegram_alerts.maybe_notify(result) is None and len(sent) == 1  # same level: quiet
    monkeypatch.setattr(telegram_alerts, "send", lambda text: False)
    state["level"] = "SAFE"
    assert telegram_alerts.maybe_notify(result) is None and state["level"] == "SAFE"  # failed send: retried later


def test_telegram_off_without_config(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert telegram_alerts.maybe_notify({"risk_level": "DANGER"}) is None
