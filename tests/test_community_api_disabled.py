"""SOS and family endpoints are off by default; community reports back the Laporan page."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

_HEADERS = {"host": "localhost"}


@pytest.mark.parametrize("method,path", [
    ("post", "/sos"),
    ("get", "/sos/recent"),
    ("post", "/family/create"),
])
def test_community_endpoints_not_registered(method, path):
    response = getattr(TestClient(app), method)(path, headers=_HEADERS)
    assert response.status_code == 404


def test_community_reports_registered_by_default():
    paths = {route.path for route in app.routes}
    assert "/reports" in paths


def test_shelter_checkin_still_registered():
    paths = {route.path for route in app.routes}
    assert "/shelters/checkin" in paths
