"""The crew endpoints rebuild `features` from the pipeline result so the agents
and the deterministic fallback see real rain / water-level values."""

from agents.crew.flood_crew import _fallback_crew_output
from api.routes.crew_analysis import _observed_features

_PREDICTION = {
    "risk_level": "WARNING",
    "elevation": {"rainfall_1h_mm": 0.0, "rainfall_3h_mm": 10.0},
    "diagnostics": {"trend_state": {"water_level_delta_cur": 0.05}},
    "hydrology_assessment": {"stations": [
        {"water_level_ratio": 0.63},
        {"water_level_ratio": 0.09},
        {"name": "no reading"},
    ]},
}


def test_observed_features_reads_pipeline_result():
    assert _observed_features(_PREDICTION) == {
        "rainfall_mm": 0.0,
        "rainfall_3h_proxy_mm": 10.0,
        "water_level_ratio": 0.63,
        "water_level_delta": 0.05,
    }


def test_observed_features_leaves_out_missing_values():
    assert _observed_features({"risk_level": "SAFE"}) == {}


def test_fallback_uses_rebuilt_features():
    prediction = {**_PREDICTION, "features": _observed_features(_PREDICTION)}
    text = _fallback_crew_output(prediction)["penjelasan"].lower()
    assert "tidak hujan" in text
    assert "63% dari batas siaga dan sedang naik" in text
