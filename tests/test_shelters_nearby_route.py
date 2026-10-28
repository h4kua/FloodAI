"""Route tests for GET /shelters/nearby (synthetic shelters, no file I/O)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
_HEADERS = {"host": "localhost"}

_POOL = (
    {"id": "A", "name": "SDN 01", "lat": -6.2250, "lon": 106.8660, "capacity_raw": ">500", "capacity_est": 500,
     "amenity": "school", "building": "school", "address": "Jl. Satu"},
    {"id": "B", "name": "Masjid Al-Ikhlas", "lat": -6.2300, "lon": 106.8700, "capacity_raw": "100-500",
     "capacity_est": 300, "amenity": "place_of_worship", "building": "mosque", "address": ""},
    {"id": "C", "name": "RS Terdekat", "lat": -6.2244, "lon": 106.8667, "capacity_raw": "", "capacity_est": None,
     "amenity": "hospital", "building": "hospital", "address": ""},
)


def test_nearby_returns_nearest_first_without_hospitals():
    with patch("services.shelter_locator.load_shelters", return_value=_POOL):
        response = client.get("/shelters/nearby", params={"lat": -6.2244, "lon": 106.8667, "limit": 5}, headers=_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["shelters"]] == ["A", "B"]
    assert body["shelters"][0]["kind"] == "school"
    assert body["shelters"][0]["address"] == "Jl. Satu"
    assert body["shelters"][1]["address"] is None
    assert body["count"] == 2
    assert body["shelters"][0]["distance_m"] <= body["shelters"][1]["distance_m"]


def test_nearby_rejects_points_outside_jakarta():
    response = client.get("/shelters/nearby", params={"lat": -7.8, "lon": 110.4}, headers=_HEADERS)
    assert response.status_code == 422


def test_nearby_limits_results():
    with patch("services.shelter_locator.load_shelters", return_value=_POOL):
        response = client.get("/shelters/nearby", params={"lat": -6.2244, "lon": 106.8667, "limit": 1}, headers=_HEADERS)
    assert response.json()["count"] == 1
    assert client.get("/shelters/nearby", params={"lat": -6.2, "lon": 106.8, "limit": 50}, headers=_HEADERS).status_code == 422


def test_nearby_on_real_data_has_local_candidates():
    response = client.get("/shelters/nearby", params={"lat": -6.2244, "lon": 106.8667}, headers=_HEADERS)
    shelters = response.json()["shelters"]
    assert len(shelters) == 10
    assert shelters[0]["distance_km"] < 1.0
    assert all(s["kind"] not in ("hospital", "clinic", "courthouse") for s in shelters)
