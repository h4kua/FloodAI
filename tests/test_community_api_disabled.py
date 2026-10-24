"""The unused community write endpoints are off in the main app by default."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

_HEADERS = {"host": "localhost"}


@pytest.mark.parametrize("method,path", [
    ("post", "/reports"),
    ("post", "/sos"),
    ("get", "/sos/recent"),
    ("post", "/family/create"),
])
def test_community_endpoints_not_registered(method, path):
    response = getattr(TestClient(app), method)(path, headers=_HEADERS)
    assert response.status_code == 404


def test_shelter_checkin_still_registered():
    paths = {route.path for route in app.routes}
    assert "/shelters/checkin" in paths
