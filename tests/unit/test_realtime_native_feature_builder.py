import pandas as pd

from realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_snapshot,
)


def test_build_realtime_native_features_from_snapshot_contains_temporal_columns():
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 31.2, "humidity": 84},
            "rain": {"1h": 15.0, "3h": 36.0},
        },
        "bmkg_alerts": [
            {
                "severity": "Severe",
                "certainty": "Likely",
                "urgency": "Immediate",
                "area_desc": "Jakarta Timur",
            }
        ],
        "poskobanjir": [
            {
                "tinggi_air": "6400",
                "siaga1": "9500",
                "siaga2": "8500",
                "siaga3": "7500",
                "siaga4": "1",
            }
        ],
    }

    engineered = build_realtime_native_features_from_snapshot(snapshot, persist_history=False)

    assert list(engineered.frame.columns) == REALTIME_NATIVE_FEATURES
    assert engineered.frame.iloc[0]["rainfall_roll3_mean"] >= 0
    assert engineered.frame.iloc[0]["water_level_ratio"] >= 0
    assert engineered.frame.iloc[0]["bmkg_weighted_score"] > 0


def test_build_realtime_native_features_filters_non_jakarta_alerts():
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 31.2, "humidity": 84},
            "rain": {"1h": 15.0, "3h": 36.0},
        },
        "bmkg_alerts": [
            {
                "severity": "Severe",
                "certainty": "Likely",
                "urgency": "Immediate",
                "area_desc": "Jakarta Timur",
            },
            {
                "severity": "Extreme",
                "certainty": "Observed",
                "urgency": "Immediate",
                "area_desc": "Jambi",
            },
        ],
        "poskobanjir": [],
    }

    engineered = build_realtime_native_features_from_snapshot(snapshot, persist_history=False)

    assert engineered.diagnostics["bmkg_alerts_total"] == 2
    assert engineered.diagnostics["bmkg_alerts_used"] == 1
    assert engineered.diagnostics["bmkg_alerts_filtered_out"] == 1


def test_snapshot_history_trend_state_uses_feature_history(monkeypatch):
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 31.2, "humidity": 84},
            "rain": {"1h": 18.0, "3h": 45.0},
        },
        "bmkg_alerts": [],
        "poskobanjir": [
            {
                "tinggi_air": "7600",
                "siaga1": "9500",
                "siaga2": "8500",
                "siaga3": "7500",
                "siaga4": "1",
            }
        ],
    }
    history = pd.DataFrame(
        [
            {"timestamp": "2026-04-18T08:00:00+00:00", "rainfall_mm": 6.0, "water_level_ratio": 0.35},
            {"timestamp": "2026-04-18T09:00:00+00:00", "rainfall_mm": 11.0, "water_level_ratio": 0.55},
        ]
    )
    monkeypatch.setattr("realtime_native.feature_builder._load_history", lambda path=None: history)

    engineered = build_realtime_native_features_from_snapshot(snapshot, persist_history=False)
    trend_state = engineered.diagnostics["trend_state"]

    assert trend_state["data_points"] == 2
    assert trend_state["risk_trend"] == "increasing"
    assert engineered.diagnostics["trend_source"] == "realtime_feature_history"


def test_snapshot_history_trend_state_respects_as_of_cutoff(monkeypatch):
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 31.2, "humidity": 84},
            "rain": {"1h": 12.0, "3h": 30.0},
        },
        "bmkg_alerts": [],
        "poskobanjir": [],
    }
    history = pd.DataFrame(
        [
            {"timestamp": "2026-04-18T08:00:00+00:00", "rainfall_mm": 6.0, "water_level_ratio": 0.30},
            {"timestamp": "2026-04-18T11:00:00+00:00", "rainfall_mm": 40.0, "water_level_ratio": 0.90},
        ]
    )
    monkeypatch.setattr("realtime_native.feature_builder._load_history", lambda path=None: history)

    engineered = build_realtime_native_features_from_snapshot(
        snapshot,
        persist_history=False,
        as_of=pd.Timestamp("2026-04-18T10:00:00+00:00"),
    )

    assert engineered.diagnostics["history_rows_used"] == 1
    assert engineered.diagnostics["trend_state"]["data_points"] == 1
