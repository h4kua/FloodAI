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


def _png_bytes(size=(2000, 1000)):
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", size, (30, 90, 160)).save(out, format="PNG")
    return out.getvalue()


def test_photo_is_reencoded_as_small_jpeg_before_upload():
    import io

    from PIL import Image

    stored = {}

    async def fake_upload(jpeg):
        stored["bytes"] = jpeg
        return "https://x.supabase.co/storage/v1/object/public/report-photos/a.jpg"

    with patch("api.routes.community_reports.upload_photo", side_effect=fake_upload):
        response = client.post("/reports/photo", files={"photo": ("banjir.png", _png_bytes(), "image/png")}, headers=_HEADERS)
    assert response.status_code == 200
    assert response.json()["photo_url"].endswith("/report-photos/a.jpg")
    with Image.open(io.BytesIO(stored["bytes"])) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 1280
        assert not img.info.get("exif")


def test_photo_that_is_not_an_image_is_rejected():
    response = client.post("/reports/photo", files={"photo": ("x.jpg", b"not an image", "image/jpeg")}, headers=_HEADERS)
    assert response.status_code == 415


def test_photo_store_down_gives_503():
    with patch("api.routes.community_reports.upload_photo", return_value=None):
        response = client.post("/reports/photo", files={"photo": ("a.png", _png_bytes((10, 10)), "image/png")}, headers=_HEADERS)
    assert response.status_code == 503


def test_report_accepts_only_photos_from_our_bucket(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    body = {"severity": "alert", "message": "Air naik", "lat": -6.15, "lon": 106.85}
    foreign = client.post("/reports", json={**body, "photo_url": "https://evil.example/a.jpg"}, headers=_HEADERS)
    assert foreign.status_code == 422
    ours = "https://x.supabase.co/storage/v1/object/public/report-photos/a.jpg"
    with patch("api.routes.community_reports.create_report", return_value={"id": "r-2"}) as mocked:
        response = client.post("/reports", json={**body, "photo_url": ours}, headers=_HEADERS)
    assert response.status_code == 200
    assert mocked.call_args.kwargs["photo_url"] == ours


def test_photo_with_huge_dimensions_is_refused_before_decoding():
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("1", (8000, 6000)).save(out, format="PNG")  # 48 MP, tiny file
    response = client.post("/reports/photo", files={"photo": ("bomb.png", out.getvalue(), "image/png")}, headers=_HEADERS)
    assert response.status_code == 415
