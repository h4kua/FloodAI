"""
Route tests for /shelters/checkin (no real Supabase connection).

Uses the real haversine_m from services.shelter_locator (not mocked) to test
the 250m geofence rejection boundary, following the pattern in
tests/test_shelter_locator.py.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
_HEADERS = {"host": "localhost"}

_SHELTER_LAT, _SHELTER_LON = -6.2000, 106.8000


def _payload(*, lat, lon, **overrides):
    base = {
        "device_id": "dev-1",
        "shelter_id": "kemayoran",
        "shelter_name": "GOR Kemayoran",
        "shelter_lat": _SHELTER_LAT,
        "shelter_lon": _SHELTER_LON,
        "lat": lat,
        "lon": lon,
        "auto": True,
    }
    base.update(overrides)
    return base


def test_checkin_within_geofence_succeeds():
    # ~167m offset in latitude — well inside the 250m tolerance.
    near_lat = _SHELTER_LAT - 0.0015
    with patch("api.routes.safe_arrival.create_checkin", return_value={"id": "chk-1"}) as mock_checkin, \
         patch("api.routes.safe_arrival.create_report", return_value={"id": "r-1"}) as mock_report:
        response = client.post("/shelters/checkin", json=_payload(lat=near_lat, lon=_SHELTER_LON), headers=_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["distance_m"] < 250
    assert body["family_notified"] is False  # no family code → nobody was told
    mock_checkin.assert_called_once()
    mock_report.assert_called_once()


def test_checkin_outside_geofence_rejected():
    # ~556m offset in latitude — well outside the 250m tolerance.
    far_lat = _SHELTER_LAT - 0.005
    with patch("api.routes.safe_arrival.create_checkin") as mock_checkin:
        response = client.post("/shelters/checkin", json=_payload(lat=far_lat, lon=_SHELTER_LON), headers=_HEADERS)
    assert response.status_code == 422
    assert response.json()["detail"] == "outside_geofence"
    mock_checkin.assert_not_called()


def test_checkin_with_family_code_notifies_family():
    near_lat = _SHELTER_LAT - 0.0010
    with patch("api.routes.safe_arrival.get_family_id", return_value="family-uuid-1") as mock_get_id, \
         patch("api.routes.safe_arrival.checkin_member", return_value=True) as mock_family_checkin, \
         patch("api.routes.safe_arrival.create_checkin", return_value={"id": "chk-2"}), \
         patch("api.routes.safe_arrival.create_report", return_value={"id": "r-2"}):
        response = client.post(
            "/shelters/checkin",
            json=_payload(lat=near_lat, lon=_SHELTER_LON, family_code="ABCDEF"),
            headers=_HEADERS,
        )
    assert response.status_code == 200
    assert response.json()["family_notified"] is True
    mock_get_id.assert_called_once_with("ABCDEF")
    mock_family_checkin.assert_called_once()
    assert mock_family_checkin.call_args.kwargs["status"] == "safe"


def test_checkin_missing_required_field_rejected():
    payload = _payload(lat=_SHELTER_LAT, lon=_SHELTER_LON)
    del payload["shelter_name"]
    response = client.post("/shelters/checkin", json=payload, headers=_HEADERS)
    assert response.status_code == 422
