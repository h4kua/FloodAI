"""Route tests for /reports (no real Supabase connection)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.community_reports import router

# The main app leaves this router off unless COMMUNITY_API_ENABLED=true, so it
# is mounted on a bare app here to keep the route code covered.
app = FastAPI()
app.include_router(router)
client = TestClient(app)
_HEADERS = {"host": "localhost"}


def test_submit_report_success():
    with patch("api.routes.community_reports.create_report", return_value={"id": "r-1", "severity": "alert"}):
        response = client.post(
            "/reports",
            json={"severity": "alert", "message": "Air naik di Kemayoran", "lat": -6.15, "lon": 106.85},
            headers=_HEADERS,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["saved"] is True
    assert body["report"]["id"] == "r-1"


def test_submit_report_rejects_invalid_severity():
    response = client.post(
        "/reports",
        json={"severity": "critical", "message": "test", "lat": -6.15, "lon": 106.85},
        headers=_HEADERS,
    )
    assert response.status_code == 422


def test_list_reports_marks_nearest_as_pinned():
    reports = [
        {"id": "far",  "lat": -6.30, "lon": 106.90, "severity": "alert"},
        {"id": "near", "lat": -6.151, "lon": 106.851, "severity": "safe"},
    ]
    with patch("api.routes.community_reports.list_reports", return_value=reports):
        response = client.get("/reports?near_lat=-6.15&near_lon=106.85", headers=_HEADERS)
    assert response.status_code == 200
    body = response.json()
    pinned = [r for r in body["reports"] if r.get("is_pinned")]
    assert len(pinned) == 1
    assert pinned[0]["id"] == "near"


def test_list_reports_without_near_coords_has_no_pinned_flag():
    reports = [{"id": "a", "lat": -6.2, "lon": 106.8, "severity": "alert"}]
    with patch("api.routes.community_reports.list_reports", return_value=reports):
        response = client.get("/reports", headers=_HEADERS)
    assert response.status_code == 200
    assert "is_pinned" not in response.json()["reports"][0]


def test_list_reports_filters_by_severity():
    with patch("api.routes.community_reports.list_reports", return_value=[]) as mock_list:
        response = client.get("/reports?severity=alert&verified=true", headers=_HEADERS)
    assert response.status_code == 200
    kwargs = mock_list.call_args.kwargs
    assert (kwargs["severity"], kwargs["verified"], kwargs["limit"]) == ("alert", True, 50)


def test_list_reports_only_asks_for_the_last_six_hours():
    from datetime import datetime, timedelta, timezone

    with patch("api.routes.community_reports.list_reports", return_value=[]) as mocked:
        response = client.get("/reports", headers=_HEADERS)
    assert response.status_code == 200
    assert response.json()["max_age_hours"] == 6
    since = datetime.fromisoformat(mocked.call_args.kwargs["since"])
    age = datetime.now(timezone.utc) - since
    assert timedelta(hours=5, minutes=59) < age < timedelta(hours=6, minutes=1)


def test_submit_report_rejects_messages_over_500_characters():
    response = client.post(
        "/reports",
        json={"severity": "alert", "message": "x" * 501, "lat": -6.15, "lon": 106.85},
        headers=_HEADERS,
    )
    assert response.status_code == 422
