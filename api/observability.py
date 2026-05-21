"""Logging, request, security-header, and metrics helpers for the API."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

try:
    import structlog
except ImportError:  # pragma: no cover - dependency is declared for production.
    structlog = None  # type: ignore[assignment]

try:
    from prometheus_client import Counter, Gauge, Histogram, CONTENT_TYPE_LATEST, generate_latest
except ImportError:  # pragma: no cover - dependency is declared for production.
    Counter = Gauge = Histogram = None  # type: ignore[assignment]
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"

    def generate_latest() -> bytes:  # type: ignore[no-redef]
        return b""


def configure_logging() -> None:
    """Configure stdlib logging and structlog JSON output when available."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(message)s",
    )
    if structlog is not None:
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level_name, logging.INFO)
            ),
            cache_logger_on_first_use=True,
        )


class _StdlibEventLogger:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    @staticmethod
    def _format_kv(kwargs: dict[str, object]) -> str:
        return " ".join(f"{key}={value!r}" for key, value in kwargs.items())

    def _emit(self, level: str, event: str, *args: object, **kwargs: object) -> None:
        exc_info = kwargs.pop("exc_info", False)
        message = event
        if kwargs:
            message = f"{event} {self._format_kv(kwargs)}"
        getattr(self._logger, level)(message, *args, exc_info=exc_info)

    def debug(self, event: str, *args: object, **kwargs: object) -> None:
        self._emit("debug", event, *args, **kwargs)

    def info(self, event: str, *args: object, **kwargs: object) -> None:
        self._emit("info", event, *args, **kwargs)

    def warning(self, event: str, *args: object, **kwargs: object) -> None:
        self._emit("warning", event, *args, **kwargs)

    def error(self, event: str, *args: object, **kwargs: object) -> None:
        self._emit("error", event, *args, **kwargs)

    def exception(self, event: str, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("exc_info", True)
        self._emit("error", event, *args, **kwargs)


def get_logger(name: str):
    if structlog is None:
        return _StdlibEventLogger(logging.getLogger(name))
    return structlog.get_logger(name)


_log = get_logger("flood.api.observability")


def _counter(name: str, documentation: str, labelnames: tuple[str, ...] = ()):
    if Counter is None:
        return _NoopMetric()
    return Counter(name, documentation, labelnames)


def _gauge(name: str, documentation: str, labelnames: tuple[str, ...] = ()):
    if Gauge is None:
        return _NoopMetric()
    return Gauge(name, documentation, labelnames)


def _histogram(name: str, documentation: str, labelnames: tuple[str, ...] = ()):
    if Histogram is None:
        return _NoopMetric()
    return Histogram(name, documentation, labelnames)


class _NoopMetric:
    def labels(self, *args: object, **kwargs: object) -> "_NoopMetric":
        return self

    def inc(self, amount: float = 1.0) -> None:
        return None

    def set(self, value: float) -> None:
        return None

    def observe(self, value: float) -> None:
        return None


HTTP_REQUESTS_TOTAL = _counter(
    "flood_http_requests_total",
    "HTTP requests by method, path, and status.",
    ("method", "path", "status"),
)
HTTP_REQUEST_SECONDS = _histogram(
    "flood_http_request_seconds",
    "HTTP request duration in seconds.",
    ("method", "path"),
)
BNPB_VINTAGE_FALLBACK_TOTAL = _counter(
    "flood_bnpb_vintage_fallback_total",
    "BNPB records with unknown vintage using configured fallback.",
)
BNPB_DATA_STALE_TOTAL = _counter(
    "flood_bnpb_data_stale_total",
    "BNPB vulnerability contexts suppressed because source data is stale.",
)
BNPB_FETCH_FAILED_TOTAL = _counter(
    "flood_bnpb_fetch_failed_total",
    "BNPB fetch failures by exception type.",
    ("type",),
)
DB_RETRY_TOTAL = _counter(
    "flood_db_retry_total",
    "Database retry attempts by outcome.",
    ("outcome",),
)
PERSISTENCE_FAILED_TOTAL = _counter(
    "flood_persistence_failed_total",
    "Pipeline persistence failures by exception type.",
    ("type",),
)
RESULT_HASH_MISMATCH_TOTAL = _counter(
    "flood_result_hash_mismatch_total",
    "Result hash changed after persistence mutation.",
)
FEATURE_HISTORY_DB_FAILURE_TOTAL = _counter(
    "flood_feature_history_db_failure_total",
    "Realtime feature-history DB failures by operation.",
    ("operation",),
)
ROUTES_CIRCUIT_OPEN = _gauge(
    "flood_routes_circuit_open",
    "Whether the Google Routes circuit breaker is open.",
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
        if structlog is not None:
            structlog.contextvars.bind_contextvars(
                request_id=request_id,
                path=request.url.path,
                method=request.method,
            )
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        except Exception:
            _log.exception(
                "request_failed",
                request_id=request_id,
                path=request.url.path,
                method=request.method,
            )
            raise
        finally:
            duration = time.perf_counter() - started
            status = str(response.status_code if response is not None else 500)
            HTTP_REQUESTS_TOTAL.labels(request.method, request.url.path, status).inc()
            HTTP_REQUEST_SECONDS.labels(request.method, request.url.path).observe(duration)
            if structlog is not None:
                structlog.contextvars.clear_contextvars()
            if response is not None:
                response.headers["x-request-id"] = request_id


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "geolocation=()")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
