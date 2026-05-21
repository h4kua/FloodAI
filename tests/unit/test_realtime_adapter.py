from services.realtime_adapter import adapt_snapshot_to_features


def test_adapt_snapshot_to_features_builds_expected_feature_columns():
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 30.5, "humidity": 82},
            "coord": {"lat": -6.2, "lon": 106.8},
            "rain": {"1h": 12.0},
        },
        "bmkg_alerts": [
            {
                "headline": "Hujan sedang hingga lebat",
                "severity": "Severe",
                "certainty": "Likely",
                "urgency": "Immediate",
                "area_desc": "Jakarta Selatan",
            },
            {
                "headline": "Hujan lebat di Jambi",
                "severity": "Extreme",
                "certainty": "Observed",
                "urgency": "Immediate",
                "area_desc": "Jambi",
            },
        ],
        "poskobanjir": [
            {
                "file_export": "Jakarta Selatan",
                "status": "Status : Siaga 3",
                "tinggi_air": "6400",
                "siaga1": "9500",
                "siaga2": "8500",
                "siaga3": "7500",
                "siaga4": "1",
            }
        ],
    }

    adapted = adapt_snapshot_to_features(snapshot)
    row = adapted.feature_frame.iloc[0]

    assert row["avg_rainfall"] >= 0
    assert row["max_rainfall"] >= row["avg_rainfall"]
    assert row["soil_moisture"] > 0
    assert "year" not in adapted.feature_frame.columns
    assert row["extreme_weather"] in (0, 1)
    assert adapted.diagnostics["selected_region"] == "Jakarta Selatan"
    assert adapted.data_quality["score"] > 0
    assert adapted.diagnostics["bmkg_weighted_signal"]["normalized_score"] > 0
    assert adapted.diagnostics["bmkg_alerts_total"] == 2
    assert adapted.diagnostics["bmkg_alerts_filtered_out"] == 1


def test_adapt_snapshot_to_features_marks_citywide_baseline_when_region_missing():
    snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 31.0, "humidity": 75},
            "coord": {"lat": -6.21, "lon": 106.84},
        },
        "bmkg_alerts": [],
        "poskobanjir": [],
    }

    adapted = adapt_snapshot_to_features(snapshot)

    assert adapted.diagnostics["selected_region"] == "DKI Jakarta"
    assert adapted.data_quality["feature_sources"]["elevation"] == "citywide_baseline"
    assert adapted.data_quality["score"] < 1.0


def test_adapt_snapshot_to_features_keeps_static_soil_moisture_baseline():
    base_snapshot = {
        "fetched_at_utc": "2026-04-18T10:00:00+00:00",
        "openweather": {
            "main": {"temp": 30.5, "humidity": 45},
            "coord": {"lat": -6.2, "lon": 106.8},
            "rain": {"1h": 2.0},
        },
        "bmkg_alerts": [],
        "poskobanjir": [{"file_export": "Jakarta Selatan", "tinggi_air": "100"}],
    }
    stressed_snapshot = {
        **base_snapshot,
        "openweather": {
            "main": {"temp": 30.5, "humidity": 98},
            "coord": {"lat": -6.2, "lon": 106.8},
            "rain": {"1h": 40.0},
        },
        "bmkg_alerts": [
            {
                "headline": "Hujan lebat Jakarta Selatan",
                "severity": "Extreme",
                "certainty": "Observed",
                "urgency": "Immediate",
                "area_desc": "Jakarta Selatan",
            }
        ],
        "poskobanjir": [
            {
                "file_export": "Jakarta Selatan",
                "status": "Status : Siaga 2",
                "tinggi_air": "8400",
                "siaga1": "9500",
                "siaga2": "8500",
                "siaga3": "7500",
                "siaga4": "1",
            }
        ],
    }

    base = adapt_snapshot_to_features(base_snapshot)
    stressed = adapt_snapshot_to_features(stressed_snapshot)

    assert base.feature_frame.iloc[0]["soil_moisture"] == stressed.feature_frame.iloc[0]["soil_moisture"]
