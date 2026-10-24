from fastapi.testclient import TestClient

from api.main import app


def test_predict_realtime_is_retired_with_successor_link():
    response = TestClient(app).get("/predict/realtime", headers={"host": "localhost"})

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "error": "endpoint_retired",
        "successor": "/predict/realtime-native",
    }
    assert response.headers["Link"] == '</predict/realtime-native>; rel="successor-version"'
