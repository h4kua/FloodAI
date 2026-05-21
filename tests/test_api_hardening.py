from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import main, observability
from api.main import app
from api.observability import RequestIdMiddleware


def _request_id_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(RequestIdMiddleware)

    @test_app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    @test_app.get("/handled")
    async def handled() -> None:
        raise HTTPException(status_code=418, detail="teapot")

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    return test_app


def test_security_headers_present_on_success_response():
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"host": "localhost"})

    assert response.status_code == 200
    assert response.headers["Content-Security-Policy"] == "default-src 'self'; style-src 'self' 'unsafe-inline'"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == "geolocation=()"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_security_headers_present_on_not_found_response():
    with TestClient(app) as client:
        response = client.get("/missing", headers={"host": "localhost"})

    assert response.status_code == 404
    assert response.headers["Content-Security-Policy"] == "default-src 'self'; style-src 'self' 'unsafe-inline'"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_prometheus_instrumentation_failure_logs_warning(monkeypatch):
    fake_log = Mock()
    monkeypatch.setattr(main, "_log", fake_log)
    monkeypatch.delenv("FLOOD_FAIL_FAST_PROMETHEUS", raising=False)

    class BrokenInstrumentator:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("instrumentator unavailable")

    main._configure_prometheus_instrumentation(FastAPI(), instrumentator_cls=BrokenInstrumentator)

    fake_log.warning.assert_called_once()
    _, kwargs = fake_log.warning.call_args
    assert kwargs["error"] == "instrumentator unavailable"
    assert kwargs["fail_fast"] is False


def test_prometheus_instrumentation_failure_can_fail_fast(monkeypatch):
    monkeypatch.setenv("FLOOD_FAIL_FAST_PROMETHEUS", "1")

    class BrokenInstrumentator:
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("instrumentator unavailable")

    with pytest.raises(RuntimeError, match="Prometheus instrumentation initialization failed"):
        main._configure_prometheus_instrumentation(FastAPI(), instrumentator_cls=BrokenInstrumentator)


def test_safe_error_response_falls_back_when_structured_logger_fails(monkeypatch):
    fake_log = Mock()
    fake_log.error.side_effect = RuntimeError("logger down")
    fallback_logger = Mock()

    monkeypatch.setattr(main, "_log", fake_log)
    monkeypatch.setattr(main.logging, "getLogger", lambda name=None: fallback_logger)

    with pytest.raises(HTTPException) as exc_info:
        main._safe_error_response(RuntimeError("api boom"), status=503)

    assert exc_info.value.status_code == 503
    fallback_logger.error.assert_called_once()


def test_request_id_header_preserved_on_handled_error():
    client = TestClient(_request_id_test_app())
    response = client.get("/handled", headers={"x-request-id": "req-123"})

    assert response.status_code == 418
    assert response.headers["x-request-id"] == "req-123"


def test_request_id_middleware_logs_exception_context(monkeypatch):
    fake_log = Mock()
    monkeypatch.setattr(observability, "_log", fake_log)

    client = TestClient(_request_id_test_app(), raise_server_exceptions=False)
    response = client.get("/boom", headers={"x-request-id": "req-456"})

    assert response.status_code == 500
    fake_log.exception.assert_called_once()
    _, kwargs = fake_log.exception.call_args
    assert kwargs["request_id"] == "req-456"
    assert kwargs["path"] == "/boom"
    assert kwargs["method"] == "GET"
