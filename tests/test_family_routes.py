"""Route tests for /family/* (no real Supabase connection)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.family import router

# The main app leaves this router off unless COMMUNITY_API_ENABLED=true, so it
# is mounted on a bare app here to keep the route code covered.
app = FastAPI()
app.include_router(router)
client = TestClient(app)
_HEADERS = {"host": "localhost"}


def test_create_family_success():
    with patch("api.routes.family.create_family", return_value={"family_code": "ABCDEF", "member_id": "m-1"}):
        response = client.post(
            "/family/create",
            json={"device_id": "dev-1", "display_name": "Budi", "phone": "0812"},
            headers=_HEADERS,
        )
    assert response.status_code == 200
    assert response.json()["family_code"] == "ABCDEF"


def test_create_family_failure_returns_503():
    with patch("api.routes.family.create_family", return_value=None):
        response = client.post(
            "/family/create",
            json={"device_id": "dev-1", "display_name": "Budi"},
            headers=_HEADERS,
        )
    assert response.status_code == 503


def test_join_family_unknown_code_returns_404():
    with patch("api.routes.family.join_family", return_value=None):
        response = client.post(
            "/family/join",
            json={"family_code": "ZZZZZZ", "device_id": "dev-2", "display_name": "Sari"},
            headers=_HEADERS,
        )
    assert response.status_code == 404


def test_join_family_uppercases_code():
    with patch("api.routes.family.join_family", return_value={"family_id": "f-1", "members": []}) as mock_join:
        response = client.post(
            "/family/join",
            json={"family_code": "abcdef", "device_id": "dev-2", "display_name": "Sari"},
            headers=_HEADERS,
        )
    assert response.status_code == 200
    assert mock_join.call_args.kwargs["family_code"] == "ABCDEF"


def test_list_family_members():
    with patch("api.routes.family.list_members", return_value=[{"id": "m-1", "is_stale": False}]):
        response = client.get("/family/ABCDEF/members", headers=_HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1


def test_checkin_unknown_family_returns_404():
    with patch("api.routes.family.checkin_member", return_value=False):
        response = client.post(
            "/family/ZZZZZZ/checkin",
            json={"device_id": "dev-1", "status": "safe"},
            headers=_HEADERS,
        )
    assert response.status_code == 404


def test_checkin_rejects_invalid_status():
    response = client.post(
        "/family/ABCDEF/checkin",
        json={"device_id": "dev-1", "status": "unknown_status"},
        headers=_HEADERS,
    )
    assert response.status_code == 422
