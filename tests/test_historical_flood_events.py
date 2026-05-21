"""Tests for per-district historical flood enrichment in bnpb_context."""

from __future__ import annotations

from app.services import bnpb_context as bc
from app.services.bnpb_context import VulnerabilityContext


def _vc(district: str) -> VulnerabilityContext:
    return VulnerabilityContext(
        irbi_flood_score=0.5,
        effective_irbi_score=0.45,
        exposure_class="MEDIUM",
        affected_population=1_000_000,
        data_vintage_days=30,
        district=district,
        data_source=bc.DATA_SOURCE_STATIC,
    )


def test_historical_for_known_district_has_expected_fields():
    hist = bc._historical_for("Jakarta Timur")
    assert "historical_flood_frequency" in hist
    assert "avg_severity_historical" in hist
    assert 0.0 <= hist["historical_flood_frequency"] <= 1.0
    assert 0.0 <= hist["avg_severity_historical"] <= 1.0


def test_historical_for_unknown_district_is_empty():
    assert bc._historical_for("Atlantis") == {}
    assert bc._historical_for("") == {}


def test_to_dict_merges_historical_without_dropping_base_fields():
    out = _vc("Jakarta Selatan").to_dict()
    # Base contract preserved.
    for key in ("irbi_score", "effective_irbi_score", "exposure_class",
                "population", "district", "data_vintage_days", "data_source"):
        assert key in out
    # Additive historical fields present for a known district.
    assert "historical_flood_frequency" in out


def test_to_dict_unknown_district_keeps_base_contract_only():
    out = _vc("Atlantis").to_dict()
    assert "historical_flood_frequency" not in out
    assert out["district"] == "Atlantis"
