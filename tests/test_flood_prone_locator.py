"""Unit tests for the flood-prone zone locator (synthetic points)."""

from __future__ import annotations

from app.services import flood_prone_locator as fp


_POINTS = (
    {"kecamatan": "TANAH ABANG", "kelurahan": "BENDUNGAN HILIR", "wilayah": "JAKPUS", "lat": -6.2016, "lon": 106.8083},
    {"kecamatan": "MAMPANG", "kelurahan": "BANGKA", "wilayah": "JAKSEL", "lat": -6.2149, "lon": 106.8200},
)


def test_in_zone_true_when_close():
    # ~50 m from Bendungan Hilir.
    assert fp.in_flood_prone_zone(-6.2012, 106.8083, points=_POINTS) is True


def test_in_zone_false_when_far():
    assert fp.in_flood_prone_zone(-6.0, 106.0, points=_POINTS) is False


def test_radius_is_respected():
    # ~1.1 km away -> out at 500 m, in at 2 km.
    assert fp.in_flood_prone_zone(-6.2115, 106.8083, radius_m=500, points=_POINTS) is False
    assert fp.in_flood_prone_zone(-6.2115, 106.8083, radius_m=2000, points=_POINTS) is True


def test_nearest_prone_point_returns_detail():
    near = fp.nearest_prone_point(-6.2012, 106.8083, points=_POINTS)
    assert near is not None
    assert near["kelurahan"] == "BENDUNGAN HILIR"
    assert near["distance_m"] >= 0


def test_empty_pool_is_safe():
    assert fp.in_flood_prone_zone(-6.2, 106.8, points=()) is False
    assert fp.nearest_prone_point(-6.2, 106.8, points=()) is None


def test_missing_file_returns_empty(monkeypatch, tmp_path):
    fp.load_points.cache_clear()
    monkeypatch.setattr(fp, "PRONE_POINTS_PATH", tmp_path / "missing.json")
    assert fp.load_points() == ()
    fp.load_points.cache_clear()
