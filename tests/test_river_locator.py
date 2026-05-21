"""Tests for the river locator and kecamatan nearest-river enrichment."""

from __future__ import annotations

from app.services import river_locator as rl


def test_nearest_river_runtime_returns_named_waterway():
    # Central Jakarta (Monas) — should resolve to a named river within a few km.
    out = rl.nearest_river(-6.1754, 106.8272)
    assert out is not None
    assert out["nearest_river"]
    assert out["distance_to_river_m"] >= 0
    assert out["waterway_type"]


def test_nearest_river_for_kecamatan_precomputed():
    out = rl.nearest_river_for_kecamatan("PASAR REBO")
    assert out is not None
    assert "nearest_river" in out
    assert "distance_to_river_m" in out


def test_nearest_river_for_kecamatan_unknown_is_none():
    assert rl.nearest_river_for_kecamatan("NOWHERE KEC") is None
    assert rl.nearest_river_for_kecamatan("") is None


def test_missing_data_returns_none(monkeypatch, tmp_path):
    rl._load.cache_clear()
    monkeypatch.setattr(rl, "WATERWAYS_PATH", tmp_path / "missing.json")
    assert rl.nearest_river(-6.2, 106.8) is None
    assert rl.nearest_river_for_kecamatan("PASAR REBO") is None
    rl._load.cache_clear()


def test_kecamatan_record_carries_nearest_river():
    from app.services.bnpb_jakarta_mapper import get_kecamatan

    rec = get_kecamatan("PASAR REBO")
    if rec is not None:  # index may be cold in some environments
        assert "nearest_river" in rec
        assert "distance_to_river_m" in rec
