"""Route tests for /sos and /sos/recent (no real Supabase connection)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.sos import router

# The main app leaves this router off unless COMMUNITY_API_ENABLED=true, so it
# is mounted on a bare app here to keep the route code covered.
app = FastAPI()
app.include_router(router)
client = TestClient(app)
_HEADERS = {"host": "localhost"}


def _payload(**overrides):
    base = {
        "device_id": "dev-1",
        "name": "Budi Santoso",
        "phone": "081234567890",
        "lat": -6.2,
        "lon": 106.8,
    }
    base.update(overrides)
    return base


def test_dispatch_sos_without_family_code():
    with patch("api.routes.sos.create_sos", return_value={"id": "sos-1", "status": "dispatched"}) as mock_create:
        response = client.post("/sos", json=_payload(), headers=_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["dispatched"] is True
    assert body["sos"]["id"] == "sos-1"
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["family_id"] is None


def test_dispatch_sos_with_family_code_flips_own_status_to_missing():
    with patch("api.routes.sos.get_family_id", return_value="family-uuid-1") as mock_get_id, \
         patch("api.routes.sos.checkin_member", return_value=True) as mock_checkin, \
         patch("api.routes.sos.create_sos", return_value={"id": "sos-2"}):
        response = client.post("/sos", json=_payload(family_code="ABCDEF"), headers=_HEADERS)
    assert response.status_code == 200
    mock_get_id.assert_called_once_with("ABCDEF")
    mock_checkin.assert_called_once()
    assert mock_checkin.call_args.kwargs["status"] == "missing"


def test_dispatch_sos_on_behalf_of_member_skips_self_checkin():
    with patch("api.routes.sos.get_family_id", return_value="family-uuid-1"), \
         patch("api.routes.sos.checkin_member") as mock_checkin, \
         patch("api.routes.sos.create_sos", return_value={"id": "sos-3"}):
        response = client.post(
            "/sos",
            json=_payload(family_code="ABCDEF", on_behalf_of_member_id="missing-member-id"),
            headers=_HEADERS,
        )
    assert response.status_code == 200
    mock_checkin.assert_not_called()


def test_dispatch_sos_reports_not_dispatched_when_repository_fails():
    with patch("api.routes.sos.create_sos", return_value=None):
        response = client.post("/sos", json=_payload(), headers=_HEADERS)
    assert response.status_code == 200
    assert response.json()["dispatched"] is False


def test_get_recent_sos():
    with patch("api.routes.sos.list_recent_sos", return_value=[{"id": "sos-1"}]):
        response = client.get("/sos/recent", headers=_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["alerts"][0]["id"] == "sos-1"


def test_dispatch_sos_rejects_missing_required_field():
    payload = _payload()
    del payload["phone"]
    response = client.post("/sos", json=payload, headers=_HEADERS)
    assert response.status_code == 422
