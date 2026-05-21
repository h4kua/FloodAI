from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app


def test_predict_realtime_sets_deprecation_headers():
    payload = {
        "risk_level": "SAFE",
        "probability": 0.1,
        "confidence_score": 0.8,
        "timestamp": "2026-05-17T00:00:00+00:00",
    }

    with patch("api.main.predict_realtime", return_value=payload):
        response = TestClient(app).get("/predict/realtime", headers={"host": "localhost"})

    assert response.status_code == 200
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Sunset"] == "Mon, 30 Jun 2026 00:00:00 GMT"
    assert response.headers["Link"] == '</predict/realtime-native>; rel="successor-version"'
    assert response.json()["timestamp"] == payload["timestamp"]
