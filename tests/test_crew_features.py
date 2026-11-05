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


def test_hydrology_context_lists_the_most_critical_dsda_posts_by_name():
    from agents.crew.flood_crew import _build_hydrology_context

    posts = [
        {"nama_pintu_air": "P.A. Manggarai 2", "file_export": "KOTA JAKARTA SELATAN", "tinggi_air": "520",
         "status_siaga": "Status : Normal", "siaga3": "750", "siaga2": "850", "siaga1": "950"},
        {"nama_pintu_air": "P.A. Cengkareng Drain", "file_export": "KOTA JAKARTA BARAT", "tinggi_air": "232",
         "tinggi_air_sebelumnya": "230", "status_siaga": "Status : Siaga 3",
         "siaga3": "190", "siaga2": "270", "siaga1": "310"},
    ]
    lines = [l for l in _build_hydrology_context({"poskobanjir": posts}, {"features": {}}).splitlines() if l.startswith("  - ")]
    assert lines[0] == ("  - P.A. Cengkareng Drain (Jakarta Barat): 232 cm, sebelumnya 230 cm, Siaga 3; "
                        "batas Siaga 3/2/1 = 190/270/310 cm")
    assert lines[1].startswith("  - P.A. Manggarai 2 (Jakarta Selatan): 520 cm, Normal")
    assert "Unknown" not in "\n".join(lines)
