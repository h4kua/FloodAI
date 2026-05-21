"""Tests for N2+N3 kelurahan flood history wiring in bnpb_context."""

from __future__ import annotations

from services import bnpb_context as bc


def test_kelurahan_lookup_known():
    h = bc.kelurahan_flood_history("Kampung Melayu")
    assert h
    assert h["event_count"] >= 1
    assert "total_jiwa_terdampak" in h
    assert h["kota"] == "Jakarta Timur"


def test_kelurahan_lookup_unknown_is_empty():
    assert bc.kelurahan_flood_history("Atlantis") == {}
    assert bc.kelurahan_flood_history("") == {}


def test_kota_rollup_known():
    roll = bc._kelurahan_history_for_kota("Jakarta Timur")
    assert "kelurahan_flood_history" in roll
    inner = roll["kelurahan_flood_history"]
    assert inner["kelurahan_count"] >= 1
    assert inner["total_events"] >= 1
    assert inner["worst_kelurahan"]


def test_kota_rollup_unknown_is_empty():
    assert bc._kelurahan_history_for_kota("Atlantis") == {}


def test_to_dict_includes_kelurahan_history_and_preserves_base():
    vc = bc.VulnerabilityContext(0.5, 0.45, "MEDIUM", 2_000_000, 30, "Jakarta Timur", bc.DATA_SOURCE_STATIC)
    d = vc.to_dict()
    assert "kelurahan_flood_history" in d
    assert d["district"] == "Jakarta Timur"
    # earlier additive fields still present
    assert "historical_flood_frequency" in d
    assert "hazard_index_2023" in d
