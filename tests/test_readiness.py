"""/readyz checks what the live endpoint depends on: the snapshot store and the thresholds."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app

_HEADERS = {"host": "localhost"}


def test_ready_when_snapshot_store_answers(monkeypatch):
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    with patch("db.supabase_client.get_supabase_client", return_value=MagicMock()):
        response = TestClient(app).get("/readyz", headers=_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_not_ready_when_snapshot_store_fails(monkeypatch):
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    with patch("db.supabase_client.get_supabase_client", side_effect=RuntimeError("no supabase")):
        response = TestClient(app).get("/readyz", headers=_HEADERS)
    assert response.status_code == 503
    assert response.json()["detail"] == {"not_ready": "RuntimeError"}


def test_postgres_pool_not_required_when_persistence_is_off(monkeypatch):
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    with patch("db.supabase_client.get_supabase_client", return_value=MagicMock()), \
         patch("api.main.pooled_connection", side_effect=AssertionError("pool must not be used")):
        response = TestClient(app).get("/readyz", headers=_HEADERS)
    assert response.status_code == 200
