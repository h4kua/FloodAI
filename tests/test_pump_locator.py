"""Unit tests for the pump-house locator (synthetic pumps)."""

from __future__ import annotations

from services import pump_locator as pl


_PUMPS = tuple(
    {"name": f"P{i}", "lat": -6.2000 + i * 0.001, "lon": 106.8000, "total_capacity": 1.0,
     "jumlah_pompa": 2, "kecamatan": "TEST"}
    for i in range(10)
)


def test_get_nearest_pump_houses_within_radius_sorted():
    out = pl.get_nearest_pump_houses(-6.2000, 106.8000, radius_km=1.0, pumps=_PUMPS)
    assert out
    # nearest first
    assert out[0]["distance_m"] <= out[-1]["distance_m"]
    assert all(r["distance_m"] <= 1000 for r in out)


def test_drainage_capacity_count_based():
    d = pl.pump_drainage_capacity(-6.2000, 106.8000, radius_km=2.0, pumps=_PUMPS)
    assert d["pump_count_within_radius"] >= 1
    assert 0.0 <= d["drainage_score"] <= 1.0
    assert d["drainage_score_basis"] == "pump_count_density"


def test_empty_pool_is_safe():
    assert pl.get_nearest_pump_houses(-6.2, 106.8, pumps=()) == []
    d = pl.pump_drainage_capacity(-6.2, 106.8, pumps=())
    assert d["drainage_score"] == 0.0
    assert d["pump_count_within_radius"] == 0


def test_far_location_has_zero_drainage():
    d = pl.pump_drainage_capacity(-6.5, 107.2, radius_km=1.0, pumps=_PUMPS)
    assert d["pump_count_within_radius"] == 0
    assert d["drainage_score"] == 0.0


def test_missing_file_returns_empty(monkeypatch, tmp_path):
    pl.load_pumps.cache_clear()
    monkeypatch.setattr(pl, "PUMPS_PATH", tmp_path / "missing.json")
    assert pl.load_pumps() == ()
    pl.load_pumps.cache_clear()
