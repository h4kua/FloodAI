"""The live endpoint (/predict/realtime-native) takes its level from the L0–L4 decision engine."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from realtime_native.bundle import load_runtime_bundle
from realtime_native.feature_builder import build_realtime_native_features_from_snapshot
from realtime_native.inference import _live_decision, predict_realtime_native
from services.plausibility_check import score_plausibility

FETCHED = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
NOW = FETCHED + timedelta(minutes=5)
MODEL_SAYS_SAFE = 0.01


def _post(level, prev=None, *, s1=3100, s2=2700, s3=1900, name="P.A. Cengkareng Drain"):
    # DSDA reports millimetres: Siaga 1 = 3100 is 310 cm.
    return {
        "nama_pintu_air": name,
        "tinggi_air": level,
        "tinggi_air_sebelumnya": level if prev is None else prev,
        "siaga1": s1, "siaga2": s2, "siaga3": s3,
        "status_siaga": "Status : Normal",
        "file_export": "Jakarta Barat",
    }


def _snapshot(posts, *, rain_1h=0.0, alerts=None):
    return {
        "fetched_at_utc": FETCHED.isoformat(),
        "openweather": {
            "main": {"temp": 28.0, "humidity": 85, "pressure": 1008},
            "rain": {"1h": rain_1h},
            "wind": {"speed": 2.0},
        },
        "poskobanjir": posts,
        "bmkg_alerts": alerts or [],
    }


def _decide(snapshot, probability=MODEL_SAYS_SAFE, engineered=None):
    bundle = load_runtime_bundle()
    engineered = engineered or build_realtime_native_features_from_snapshot(
        snapshot, persist_history=False, as_of=NOW,
    )
    ood = {"method": "IsolationForest", "score": 0.05, "is_outlier": False}
    decision, _ = _live_decision(
        snapshot, engineered, probability, ood, dict(bundle.thresholds), bundle.model_card, now=NOW,
    )
    return decision


def test_post_at_siaga_3_gives_watch_even_when_the_model_says_safe():
    decision = _decide(_snapshot([_post(2008)]))  # ratio 0.65
    assert decision.risk_level == "PRE_ALERT"


def test_post_above_ninety_percent_of_siaga_1_gives_danger():
    decision = _decide(_snapshot([_post(2900)]))  # ratio 0.94
    assert decision.risk_level == "DANGER"
    assert decision.override_trace["authority"] == "L1_SIAGA"


def test_severe_bmkg_alert_with_heavy_rain_gives_at_least_warning():
    alert = {
        "severity": "Severe", "certainty": "Observed", "urgency": "Immediate",
        "area_desc": "DKI Jakarta", "headline": "Hujan lebat disertai petir",
    }
    decision = _decide(_snapshot([_post(500)], rain_1h=25.0, alerts=[alert]))
    assert decision.risk_level in {"WARNING", "DANGER"}


def test_missing_sections_give_unknown():
    snapshot = {"fetched_at_utc": FETCHED.isoformat()}
    decision = _decide(snapshot)
    assert decision.risk_level == "UNKNOWN"
    assert decision.system_status == "FAIL"


def test_pump_stations_do_not_set_the_level():
    pump = _post(5800, s1=6000, s2=5500, s3=5000, name="Pompa Yos Sudarso 1")  # ratio 0.97
    decision = _decide(_snapshot([_post(500), pump]))
    assert decision.risk_level == "SAFE"


def test_stale_history_delta_is_not_read_as_a_rapid_rise():
    # After downtime the feature history's last row can be months old, so the
    # model's water_level_delta is large. The feed's own previous reading says
    # the post is flat, so the rapid-rise rule must not fire.
    snapshot = _snapshot([_post(2008, prev=2008)])
    engineered = build_realtime_native_features_from_snapshot(snapshot, persist_history=False, as_of=NOW)
    engineered.frame.loc[0, "water_level_delta"] = 0.6
    decision = _decide(snapshot, engineered=engineered)
    assert decision.risk_level == "PRE_ALERT"


def test_millimetre_feed_is_physically_plausible():
    # Manggarai at 5174 mm (Siaga 1 = 9500 mm) is a normal reading, not 51 m of water.
    plausibility = score_plausibility(_snapshot([_post(5174, s1=9500, s2=8500, s3=7500, name="P.A. Manggarai 2")]))
    assert plausibility["is_plausible"]
    assert plausibility["station_faults"] == []


def test_reading_far_above_its_own_siaga_1_is_still_quarantined():
    plausibility = score_plausibility(_snapshot([_post(9999, s1=950, s2=850, s3=750)]))
    assert len(plausibility["station_faults"]) == 1


def test_observed_context_reaches_the_decision_inputs():
    engineered = build_realtime_native_features_from_snapshot(
        _snapshot([_post(2008)]), persist_history=False, as_of=NOW,
    )
    observed = engineered.diagnostics["observed_context"]
    assert observed["water_level_ratio"] == pytest.approx(2008 / 3100, abs=1e-3)
    assert "bmkg_severity_score" in observed


def test_endpoint_reports_the_engine_level_and_the_model_view(tmp_path, monkeypatch):
    import realtime_native.inference as inference

    monkeypatch.setattr(inference, "REPORTS_DIR", tmp_path / "reports")
    snapshot_path = tmp_path / "clean" / "realtime_snapshot.json"
    snapshot_path.parent.mkdir()
    snapshot_path.write_text(json.dumps(_snapshot([_post(2008)])), encoding="utf-8")

    result = predict_realtime_native(snapshot_path, persist_history=False, as_of=NOW)

    # A post at Siaga 3 never reads as SAFE, whatever the model says.
    assert result["risk_level"] in {"PRE_ALERT", "WARNING", "DANGER"}
    assert result["decision"]["model_risk_level"] in {"SAFE", "WARNING", "DANGER"}
    assert result["decision"]["layer"]
    assert result["features"]["water_level_ratio"] == pytest.approx(2008 / 3100, abs=1e-3)
    assert result["risk_interpretation"]
