"""Tests for agentic-response evacuation enrichment (app.api.main helpers)."""

from __future__ import annotations

from app.api.main import _enrich_with_evacuation, _resolve_location_coords


_MONAS_SNAPSHOT = {"openweather": {"coord": {"lat": -6.1754, "lon": 106.8272}}}


def test_warning_result_is_enriched_with_shelter():
    result = {"risk_level": "WARNING", "vulnerability_context": {"district": "Jakarta Pusat"}}
    out = _enrich_with_evacuation(result, _MONAS_SNAPSHOT)
    assert out.get("nearest_shelter") is not None
    assert out["nearest_shelter"]["name"]
    assert out["nearest_shelter"]["distance_km"] >= 0
    assert len(out.get("evacuation_points", [])) >= 1
    # nearest_shelter is mirrored into vulnerability_context
    assert out["vulnerability_context"].get("nearest_shelter") is not None


def test_safe_result_is_not_enriched():
    out = _enrich_with_evacuation({"risk_level": "SAFE"}, _MONAS_SNAPSHOT)
    assert "evacuation_points" not in out
    assert "nearest_shelter" not in out


def test_missing_coords_does_not_break_result():
    # No snapshot coord and no resolvable kecamatan -> result returned unchanged.
    result = {"risk_level": "DANGER"}
    out = _enrich_with_evacuation(result, {"openweather": {}})
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
