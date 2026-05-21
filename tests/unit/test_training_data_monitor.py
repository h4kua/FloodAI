from services.training_data_monitor import detect_out_of_distribution


def test_detect_out_of_distribution_flags_extreme_values():
    result = detect_out_of_distribution(
        {
            "avg_rainfall": 9999.0,
            "max_rainfall": 9999.0,
            "avg_temperature": 30.0,
            "elevation": 10.0,
            "ndvi": 0.2,
            "slope": 0.1,
            "soil_moisture": 40.0,
            "year": 2026.0,
            "month": 4.0,
            "lat": -6.2,
            "long": 106.8,
            "rainfall_soil_interaction": 99999.0,
            "elevation_risk": 0.09,
            "vegetation_elevation_risk": 0.07,
            "extreme_weather": 1.0,
            "monsoon_season": 0.0,
            "urban_density_risk": 4.0,
        }
    )

    assert result["out_of_distribution_count"] >= 1
    assert len(result["warnings"]) >= 1


def test_detect_out_of_distribution_ignores_year_rollover_feature():
    result = detect_out_of_distribution(
        {
            "year": 2031.0,
            "month": 4.0,
            "avg_rainfall": 30.0,
            "max_rainfall": 60.0,
        }
    )

    assert all(warning["feature"] != "year" for warning in result["warnings"])
