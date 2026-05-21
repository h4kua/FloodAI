"""Tests for agentic-response evacuation + infrastructure enrichment."""

from __future__ import annotations

from app.api.main import (
    _enrich_with_evacuation,
    _enrich_with_infrastructure,
    _resolve_location_coords,
)


_MONAS = (-6.1754, 106.8272)
_MONAS_SNAPSHOT = {"openweather": {"coord": {"lat": -6.1754, "lon": 106.8272}}}


def test_warning_result_is_enriched_with_shelter():
    result = {"risk_level": "WARNING", "vulnerability_context": {"district": "Jakarta Pusat"}}
    out = _enrich_with_evacuation(result, _MONAS)
    assert out.get("nearest_shelter") is not None
    assert out["nearest_shelter"]["name"]
    assert out["nearest_shelter"]["distance_km"] >= 0
    assert len(out.get("evacuation_points", [])) >= 1
    # nearest_shelter is mirrored into vulnerability_context
    assert out["vulnerability_context"].get("nearest_shelter") is not None


def test_safe_result_is_not_enriched():
    out = _enrich_with_evacuation({"risk_level": "SAFE"}, _MONAS)
    assert "evacuation_points" not in out
    assert "nearest_shelter" not in out


def test_missing_coords_does_not_break_result():
    result = {"risk_level": "DANGER"}
    out = _enrich_with_evacuation(result, None)
    assert out is result
    assert "evacuation_points" not in out


def test_resolve_coords_prefers_snapshot_coord():
    coords = _resolve_location_coords(_MONAS_SNAPSHOT, {})
    assert coords == (-6.1754, 106.8272)


def test_resolve_coords_falls_back_to_kecamatan_centroid():
    coords = _resolve_location_coords({}, {"mapping_info": {"kecamatan": {"name": "MENTENG"}}})
    assert coords is not None
    lat, lon = coords
    assert -7.0 < lat < -5.5 and 106.0 < lon < 107.5


def test_resolve_coords_falls_back_to_kota_centroid():
    # Bare kota request (no coord, no kecamatan) -> mapped_district centroid.
    coords = _resolve_location_coords({}, {"mapping_info": {"mapped_district": "Jakarta Utara"}})
    assert coords is not None
    lat, lon = coords
    assert -7.0 < lat < -5.5 and 106.0 < lon < 107.5


# ── infrastructure enrichment ───────────────────────────────────────────────

def test_infrastructure_populates_pump_river_schools():
    result = {"risk_level": "DANGER", "vulnerability_context": {"district": "Jakarta Pusat"}}
    out = _enrich_with_infrastructure(result, _MONAS)
    vc = out["vulnerability_context"]
    assert "pump_drainage_score" in vc and 0.0 <= vc["pump_drainage_score"] <= 1.0
    assert "pump_count_within_5km" in vc
    assert "in_river_overflow_zone" in vc and isinstance(vc["in_river_overflow_zone"], bool)
    # top-level list, fields name/kelurahan/distance_km
    assert "vulnerable_facilities_nearby" in out
    for s in out["vulnerable_facilities_nearby"]:
        assert set(s.keys()) == {"name", "kelurahan", "distance_km"}


def test_infrastructure_none_coords_is_noop():
    result = {"risk_level": "DANGER"}
    out = _enrich_with_infrastructure(result, None)
    assert out is result
    assert "vulnerable_facilities_nearby" not in out


def test_infrastructure_does_not_touch_protected_fields():
    result = {"risk_level": "DANGER", "probability": 0.42, "vulnerability_context": {"hazard_index_2023": 1.5}}
    out = _enrich_with_infrastructure(result, _MONAS)
    assert out["risk_level"] == "DANGER"
    assert out["probability"] == 0.42
    assert out["vulnerability_context"]["hazard_index_2023"] == 1.5
