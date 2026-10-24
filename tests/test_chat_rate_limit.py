"""Per-IP rate limit on POST /api/chat and client-IP resolution behind Fly.io."""

from __future__ import annotations

from fastapi.testclient import TestClient
from starlette.requests import Request

import api.ip_rate_limit as ip_rate_limit
from api.main import app

_HEADERS = {"host": "localhost"}


def _request(fly_ip: str | None) -> Request:
    headers = [(b"fly-client-ip", fly_ip.encode())] if fly_ip else []
    return Request({"type": "http", "headers": headers, "client": ("10.0.0.1", 4242)})


def test_chat_returns_429_after_limit(monkeypatch):
    monkeypatch.setenv("FLOOD_CHAT_RATE_LIMIT", "2")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)  # handler answers 503 without calling Groq
    ip_rate_limit._chat_buckets.clear()
    client = TestClient(app)
    try:
        codes = [
            client.post("/api/chat", json={"message": "halo"}, headers=_HEADERS).status_code
            for _ in range(3)
        ]
    finally:
        ip_rate_limit._chat_buckets.clear()
    assert codes == [503, 503, 429]


def test_chat_limit_does_not_consume_checkin_buckets(monkeypatch):
    monkeypatch.setenv("FLOOD_CHAT_RATE_LIMIT", "5")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    ip_rate_limit._chat_buckets.clear()
    ip_rate_limit._buckets.clear()
    try:
        TestClient(app).post("/api/chat", json={"message": "halo"}, headers=_HEADERS)
        assert not ip_rate_limit._buckets
    finally:
        ip_rate_limit._chat_buckets.clear()


def test_client_ip_ignores_fly_header_off_fly(monkeypatch):
    monkeypatch.delenv("FLY_APP_NAME", raising=False)
    assert ip_rate_limit.client_ip(_request("1.2.3.4")) == "10.0.0.1"


def test_client_ip_uses_fly_header_on_fly(monkeypatch):
    monkeypatch.setenv("FLY_APP_NAME", "floodai-test")
    assert ip_rate_limit.client_ip(_request("1.2.3.4")) == "1.2.3.4"
    assert ip_rate_limit.client_ip(_request(None)) == "10.0.0.1"
