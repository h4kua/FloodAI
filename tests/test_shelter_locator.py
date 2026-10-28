"""Unit tests for the shelter locator (no file I/O — synthetic shelters)."""

from __future__ import annotations

from services import shelter_locator as sl


_SHELTERS = (
    {"name": "GOR Otista", "lat": -6.225, "lon": 106.866, "capacity_raw": ">500", "capacity_est": 500, "amenity": "sports"},
    {"name": "SDN Palmerah", "lat": -6.200, "lon": 106.790, "capacity_raw": "100-500", "capacity_est": 300, "amenity": "school"},
    {"name": "Masjid (no capacity)", "lat": -6.300, "lon": 106.900, "capacity_raw": "", "capacity_est": None, "amenity": "place_of_worship"},
)


def test_haversine_known_distance():
    # ~1.11 km per 0.01 deg latitude.
    d = sl.haversine_m(-6.20, 106.80, -6.21, 106.80)
    assert 1050 < d < 1150


def test_nearest_shelter_picks_closest():
    result = sl.nearest_shelter(-6.226, 106.867, shelters=_SHELTERS)
    assert result is not None
    assert result["name"] == "GOR Otista"
    assert result["capacity"] == ">500"
    assert result["distance_m"] >= 0


def test_nearest_shelters_sorted_and_limited():
    results = sl.nearest_shelters(-6.20, 106.79, limit=2, shelters=_SHELTERS)
    assert len(results) == 2
    assert results[0]["name"] == "SDN Palmerah"
    assert results[0]["distance_m"] <= results[1]["distance_m"]


def test_require_capacity_filters_out_uncapacitied():
    near = sl.nearest_shelter(-6.301, 106.901, require_capacity=True, shelters=_SHELTERS)
    assert near is not None
    assert near["name"] != "Masjid (no capacity)"


def test_empty_pool_returns_none():
    assert sl.nearest_shelter(-6.2, 106.8, shelters=()) is None
    assert sl.nearest_shelters(-6.2, 106.8, shelters=()) == []


def test_load_shelters_missing_file_returns_empty(monkeypatch, tmp_path):
    sl.load_shelters.cache_clear()
    monkeypatch.setattr(sl, "SHELTERS_PATH", tmp_path / "missing.json")
    assert sl.load_shelters() == ()
    sl.load_shelters.cache_clear()


def test_shelter_kind_from_tags():
    assert sl.shelter_kind({"amenity": "place_of_worship", "building": "mosque"}) == "mosque"
    assert sl.shelter_kind({"amenity": "", "building": "community_group_office"}) == "rw_office"
    assert sl.shelter_kind({"amenity": "school", "building": ""}) == "school"
    assert sl.shelter_kind({"amenity": "hospital", "building": "school"}) == "hospital"
    assert sl.shelter_kind({"amenity": "", "building": "yes"}) == "other"


def test_evacuation_only_drops_hospitals():
    pool = _SHELTERS + ({"name": "RS Dekat", "lat": -6.2001, "lon": 106.7901, "capacity_raw": "", "capacity_est": None,
                         "amenity": "hospital", "building": "hospital"},)
    assert sl.nearest_shelter(-6.2001, 106.7901, shelters=pool)["name"] == "RS Dekat"
    near = sl.nearest_shelter(-6.2001, 106.7901, evacuation_only=True, shelters=pool)
    assert near["name"] == "SDN Palmerah"
    assert near["kind"] == "school"


def test_same_place_listed_twice_is_returned_once():
    pool = (
        {"name": "SDN 08 Pagi", "lat": -6.2000, "lon": 106.8000, "capacity_est": 300, "amenity": "school"},
        {"name": "SDN 08 Pagi ", "lat": -6.2003, "lon": 106.8002, "capacity_est": 300, "amenity": "school"},
        {"name": "Masjid Baru", "lat": -6.2010, "lon": 106.8000, "capacity_est": 100, "amenity": "place_of_worship"},
    )
    names = [s["name"] for s in sl.nearest_shelters(-6.2, 106.8, limit=3, shelters=pool)]
    assert names == ["SDN 08 Pagi", "Masjid Baru"]
