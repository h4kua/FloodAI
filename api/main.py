from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv
# Load the project-root .env explicitly. dotenv's default search walks up from
# this file's directory and would otherwise pick up app/.env first, which lacks
# FLOOD_API_KEYS. override=False lets process/shell env (e.g. test fixtures and
# deployment env vars) take precedence over the file.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
import asyncio
import os
import hashlib
import hmac
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg2.extras import Json
# Hard dependency: a missing APScheduler must fail loudly at import (no try/except).
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from api.dashboard import build_demo_page
from api.routes.agentic_llm import router as agentic_llm_router
from api.routes.chat import router as chat_router
from api.routes.crew_analysis import router as crew_analysis_router
from api.observability import (
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
    get_logger,
    metrics_response,
)
from api.security import require_api_key
from pipeline.flood_pipeline import FloodDecisionPipeline
from realtime_native.bundle import load_runtime_bundle
from realtime_native.inference import predict_realtime_native
from services.decision_engine import _canonical_default_thresholds
from services.prediction_service import predict_realtime
from db.psycopg2_connection import close_pool, pooled_connection
from utils.paths import DEFAULT_REALTIME_SNAPSHOT

_log = get_logger("flood.api")


# ─── Raw ASGI CORS middleware ────────────────────────────────────────────────
#
# Replaces starlette.middleware.cors.CORSMiddleware, which was rejecting
# preflight OPTIONS with 400 "Disallowed CORS origin" despite allow_origins=["*"].
# This raw ASGI middleware:
#   * Echoes the request Origin (or "*" when absent) so credentialed requests
#     also work.
#   * Short-circuits OPTIONS preflight with a 200 response carrying the full
#     set of CORS headers — never delegates preflight to downstream middleware
#     (TrustedHostMiddleware, routing) where it can be rejected.
#   * Injects Access-Control-* headers onto every other response via a wrapped
#     ``send`` callable, so simple and actual requests are also CORS-safe.
class RawCORSMiddleware:
    """ASGI middleware that unconditionally allows cross-origin requests."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        origin = headers.get("origin", "*")
        req_method = headers.get("access-control-request-method", "*")
        req_headers = headers.get(
            "access-control-request-headers",
            "Authorization, Content-Type, Idempotency-Key, X-Requested-With",
        )

        cors_headers = [
            (b"access-control-allow-origin", origin.encode("latin-1")),
            (b"access-control-allow-credentials", b"true"),
            (b"access-control-allow-methods",
             b"GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"),
            (b"access-control-allow-headers", req_headers.encode("latin-1")),
            (b"access-control-expose-headers",
             b"Content-Type, Deprecation, Sunset, Link, X-Request-ID"),
            (b"access-control-max-age", b"86400"),
            (b"vary", b"Origin"),
        ]

        if scope["method"] == "OPTIONS":
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-length", b"0"),
                    (b"content-type", b"text/plain; charset=utf-8"),
                    *cors_headers,
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                existing = message.get("headers", [])
                reserved = {name for name, _ in cors_headers}
                filtered = [(n, v) for n, v in existing if n.lower() not in reserved]
                message["headers"] = filtered + cors_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _model_to_dict(model: BaseModel) -> dict:
    if hasattr(model, "model_dump"):
        return model.model_dump()  # type: ignore[attr-defined]
    return model.dict()


# ─── Location normalization ───────────────────────────────────────────────────
_VALID_KOTA: frozenset[str] = frozenset({
    "Jakarta Utara",
    "Jakarta Selatan",
    "Jakarta Pusat",
    "Jakarta Timur",
    "Jakarta Barat",
    "Kepulauan Seribu",
})
_DEFAULT_LOCATION = "Jakarta Utara"
_DICT_LOCATION_KEYS = ("district", "city", "kota", "kecamatan", "name")


def _normalize_location(value: object) -> str:
    if isinstance(value, dict):
        raw = ""
        for key in _DICT_LOCATION_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                raw = candidate
                break
    elif isinstance(value, str):
        raw = value
    else:
        return _DEFAULT_LOCATION

    raw = raw.strip()
    if not raw:
        return _DEFAULT_LOCATION

    titled = " ".join(part.capitalize() for part in raw.split())
    if titled in _VALID_KOTA:
        return titled

    try:
        from services.bnpb_context import (
            MAPPING_CONFIDENCE_THRESHOLD,
            map_to_jakarta_district,
        )
        district, confidence = map_to_jakarta_district(raw)
        if district and confidence >= MAPPING_CONFIDENCE_THRESHOLD and district in _VALID_KOTA:
            return district
    except Exception:
        pass

    try:
        _log.info(
            "location_normaliser_fallback",
            input=raw,
            defaulted_to=_DEFAULT_LOCATION,
        )
    except TypeError:
        _log.info(
            "location_normaliser_fallback input=%r defaulted_to=%s",
            raw, _DEFAULT_LOCATION,
        )
    return _DEFAULT_LOCATION


def _is_specific_location(raw: str) -> bool:
    if not isinstance(raw, str):
        return False
    cleaned = raw.strip()
    if not cleaned:
        return False
    titled = " ".join(part.capitalize() for part in cleaned.split())
    if titled in _VALID_KOTA:
        return True
    try:
        from services.bnpb_context import (
            MAPPING_CONFIDENCE_THRESHOLD,
            map_to_jakarta_district,
        )
        district, confidence = map_to_jakarta_district(cleaned)
        if district and confidence >= MAPPING_CONFIDENCE_THRESHOLD:
            return True
    except Exception:
        pass
    return False


class SnapshotIn(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fetched_at_utc": "2026-05-18T11:30:00Z",
                "location": "Jakarta Utara",
                "openweather": {
                    "main": {"temp": 27.9, "humidity": 91},
                    "rain": {"1h": 20},
                    "coord": {"lat": -6.2088, "lon": 106.8456},
                },
                "poskobanjir": [
                    {"wilayah": "Jakarta Utara", "tinggi_air": 120, "status": "Siaga 3"}
                ],
                "bmkg_alerts": [
                    {
                        "headline": "Hujan Lebat Jakarta",
                        "severity": "Moderate",
                        "certainty": "Observed",
                        "urgency": "Immediate",
                    }
                ],
            }
        }
    )

    fetched_at_utc: str = Field(..., min_length=1)
    location: str = _DEFAULT_LOCATION
    location_raw: str | None = None
    openweather: dict = Field(default_factory=dict)
    poskobanjir: list = Field(default_factory=list)
    bmkg_alerts: list = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_location(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        raw = data.get("location")
        if isinstance(raw, dict):
            for key in _DICT_LOCATION_KEYS:
                candidate = raw.get(key)
                if (
                    isinstance(candidate, str)
                    and candidate.strip()
                    and _is_specific_location(candidate)
                ):
                    data.setdefault("location_raw", candidate)
                    break
        elif isinstance(raw, str) and raw.strip() and _is_specific_location(raw):
            data.setdefault("location_raw", raw)

        data["location"] = _normalize_location(raw)
        return data


def _request_budget_s() -> float:
    try:
        return max(30.0, float(os.getenv("FLOOD_REQUEST_BUDGET_S", "60")))
    except ValueError:
        return 60.0


def _truthy_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _prometheus_fail_fast_enabled() -> bool:
    return _truthy_env("FLOOD_FAIL_FAST_PROMETHEUS")


def _configure_prometheus_instrumentation(
    app: FastAPI,
    instrumentator_cls=None,
) -> None:
    try:
        if instrumentator_cls is None:
            from prometheus_fastapi_instrumentator import Instrumentator as instrumentator_cls  # type: ignore[import-not-found]

        instrumentator_cls(excluded_handlers=["/metrics"]).instrument(app)
    except Exception as exc:
        fail_fast = _prometheus_fail_fast_enabled()
        _log.warning(
            "prometheus_instrumentator_disabled",
            error=str(exc),
            fail_fast=fail_fast,
        )
        if fail_fast:
            raise RuntimeError("Prometheus instrumentation initialization failed") from exc


def _register_middleware(app: FastAPI, middleware_cls, **kwargs) -> None:
    try:
        app.add_middleware(middleware_cls, **kwargs)
    except Exception as exc:
        _log.error(
            "middleware_registration_failed",
            middleware=middleware_cls.__name__,
            error=str(exc),
            exc_info=True,
        )
        raise


def _validate_middleware_stack(app: FastAPI) -> None:
    try:
        app.middleware_stack = app.build_middleware_stack()
    except Exception as exc:
        _log.error(
            "middleware_initialization_failed",
            error=str(exc),
            exc_info=True,
        )
        raise


def _log_api_failure(exc: Exception, correlation_id: str) -> None:
    try:
        _log.error(
            "api_failure",
            correlation_id=correlation_id,
            error_type=type(exc).__name__,
            message=str(exc),
            exc_info=True,
        )
        return
    except Exception as log_exc:
        fallback_logger = logging.getLogger("flood.api.fallback")
        try:
            fallback_logger.error(
                "api_failure correlation_id=%s error_type=%s log_error=%s",
                correlation_id,
                type(exc).__name__,
                log_exc,
                exc_info=True,
            )
        except Exception:
            return


def _safe_error_response(exc: Exception, status: int = 500) -> None:
    correlation_id = uuid.uuid4().hex
    _log_api_failure(exc, correlation_id)
    raise HTTPException(
        status_code=status,
        detail={"error": "internal_error", "correlation_id": correlation_id},
    ) from exc


def _reject_non_finite(value: object, path: str = "snapshot") -> None:
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        raise HTTPException(status_code=422, detail=f"{path} contains non-finite float")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_non_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_non_finite(child, f"{path}[{index}]")


def _response_hash(response: dict) -> str:
    encoded = json.dumps(response, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _get_idempotent_response(key: str | None) -> dict | None:
    if not key:
        return None
    try:
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM idempotency_keys
                     WHERE created_at < NOW() - INTERVAL '1 hour'
                    """
                )
                cur.execute(
                    """
                    SELECT response_json
                      FROM idempotency_keys
                     WHERE idempotency_key = %s
                       AND created_at >= NOW() - INTERVAL '1 hour'
                    """,
                    (key,),
                )
                row = cur.fetchone()
            conn.commit()
        return row[0] if row else None
    except Exception as exc:
        # DB unavailable — skip idempotency check rather than blocking prediction.
        _log.warning("idempotency_read_failed key=%s error=%s", key, exc)
        return None


def _store_idempotent_response(key: str | None, response: dict) -> None:
    if not key:
        return
    try:
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO idempotency_keys
                        (idempotency_key, response_hash, response_json, created_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (idempotency_key) DO UPDATE
                        SET response_hash = EXCLUDED.response_hash,
                            response_json = EXCLUDED.response_json,
                            created_at = EXCLUDED.created_at
                    """,
                    (key, _response_hash(response), Json(response)),
                )
            conn.commit()
    except Exception as exc:
        # DB unavailable — best-effort; prediction already succeeded so don't raise.
        _log.warning("idempotency_write_failed key=%s error=%s", key, exc)


async def _bounded_threadpool(fn, *args, **kwargs):
    try:
        return await asyncio.wait_for(
            run_in_threadpool(fn, *args, **kwargs),
            timeout=_request_budget_s(),
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "request_timeout"},
            headers={"Retry-After": "5"},
        ) from exc


# ─── Background snapshot scheduler ─────────────────────────────────────────────
# Module-level singleton so the health check can read scheduler.running. The
# AsyncIOScheduler import is a hard dependency (see top of module) — never wrapped
# in a try/except that would swallow a missing-package ImportError.
scheduler = AsyncIOScheduler(timezone="UTC")

_DEFAULT_REFRESH_INTERVAL_MIN = 15
_REFRESH_INTERVAL_MIN_BOUND = 1
_REFRESH_INTERVAL_MAX_BOUND = 60


def _refresh_interval_minutes() -> int:
    """
    Resolve SNAPSHOT_REFRESH_INTERVAL_MINUTES (default 15). Falls back to 15 with a
    WARNING when the value is invalid: non-int, < 1, or > 60.
    """
    raw = os.getenv("SNAPSHOT_REFRESH_INTERVAL_MINUTES")
    if raw is None:
        return _DEFAULT_REFRESH_INTERVAL_MIN
    try:
        value = int(raw)
    except (TypeError, ValueError):
        _log.warning(
            f"invalid SNAPSHOT_REFRESH_INTERVAL_MINUTES={raw!r} (not an int); "
            f"falling back to {_DEFAULT_REFRESH_INTERVAL_MIN}"
        )
        return _DEFAULT_REFRESH_INTERVAL_MIN
    if not (_REFRESH_INTERVAL_MIN_BOUND <= value <= _REFRESH_INTERVAL_MAX_BOUND):
        _log.warning(
            f"SNAPSHOT_REFRESH_INTERVAL_MINUTES={value} out of range "
            f"[{_REFRESH_INTERVAL_MIN_BOUND}, {_REFRESH_INTERVAL_MAX_BOUND}]; "
            f"falling back to {_DEFAULT_REFRESH_INTERVAL_MIN}"
        )
        return _DEFAULT_REFRESH_INTERVAL_MIN
    return value


async def _scheduled_refresh() -> None:
    """
    Rebuild the realtime snapshot and persist it to Supabase. Never raises — every
    failure is logged so a bad run cannot kill the scheduler or the event loop.
    """
    from db.snapshot_repository import save_snapshot
    from services.snapshot_refresh import build_fresh_snapshot

    started = time.perf_counter()
    _log.info("scheduled_refresh_start")
    try:
        snapshot = await build_fresh_snapshot()
        saved = await save_snapshot(snapshot)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if not saved:
            _log.warning(f"snapshot built but save failed (duration_ms={duration_ms})")
            return
        _log.info(f"scheduled_refresh_finish (duration_ms={duration_ms})")
    except Exception as exc:  # noqa: BLE001 — scheduled job must never raise.
        duration_ms = int((time.perf_counter() - started) * 1000)
        _log.error(
            f"scheduled_refresh_failed error_type={type(exc).__name__} "
            f"error={exc} duration_ms={duration_ms}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    load_runtime_bundle()
    app.state.pipeline = FloodDecisionPipeline(persist=os.getenv("DB_PERSISTENCE_ENABLED", "true").lower() == "true")

    interval_minutes = _refresh_interval_minutes()
    scheduler.add_job(
        _scheduled_refresh,
        "interval",
        minutes=interval_minutes,
        id="snapshot_refresh",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    _log.info(f"snapshot_scheduler_started (interval_minutes={interval_minutes})")
    # Immediate refresh so a fresh Railway deploy updates the snapshot right away
    # instead of waiting a full interval.
    asyncio.create_task(_scheduled_refresh())

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        close_pool()


app = FastAPI(
    title="Jakarta Flood Prediction API",
    version="2.0.0",
    description="Realtime flood prediction with 5-stage agentic decision pipeline and flood-aware routing.",
    lifespan=lifespan,
)

_configure_prometheus_instrumentation(app)

# Middleware registration order matters: Starlette wraps in LIFO, so the LAST
# middleware added is the OUTERMOST one to see the request. RawCORSMiddleware
# is registered LAST so it executes FIRST — short-circuiting OPTIONS preflight
# before TrustedHostMiddleware or any auth dependency can reject it.
_register_middleware(app, RequestIdMiddleware)
_register_middleware(app, SecurityHeadersMiddleware)
_register_middleware(
    app,
    TrustedHostMiddleware,
    allowed_hosts=["*"],
)
_register_middleware(app, RawCORSMiddleware)

app.include_router(agentic_llm_router)
app.include_router(chat_router)
app.include_router(crew_analysis_router)


@app.api_route("/healthz", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
async def liveness() -> dict:
    result: dict = {
        "status": "ok",
        "scheduler": "running" if scheduler.running else "stopped",
    }
    try:
        with open(DEFAULT_REALTIME_SNAPSHOT, encoding="utf-8") as f:
            snap = json.load(f)
        fetched_at_str = snap.get("fetched_at_utc", "")
        if fetched_at_str:
            fetched_dt = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
            age_min = (datetime.now(timezone.utc) - fetched_dt).total_seconds() / 60
            result["snapshot_age_minutes"] = round(age_min, 1)
            result["snapshot_stale"] = age_min > 30
        else:
            result["snapshot_age_minutes"] = None
            result["snapshot_stale"] = True
    except Exception as exc:
        result["snapshot_age_minutes"] = None
        result["snapshot_stale"] = True
        result["snapshot_error"] = type(exc).__name__
    return result


@app.get("/readyz")
async def readiness() -> dict[str, str]:
    try:
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            conn.commit()
        _canonical_default_thresholds()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"not_ready": type(exc).__name__},
        ) from exc


@app.get("/metrics")
async def metrics() -> Response:
    return metrics_response()


# Overall budget for one refresh (build + save); the builder has its own inner cap.
_REFRESH_TIMEOUT_S = 45.0
# Reject refreshes that arrive less than this after the last stored snapshot.
_REFRESH_MIN_INTERVAL_S = 300.0


def _parse_snapshot_ts(value: object) -> Optional[datetime]:
    """Parse an ISO-8601 fetched_at_utc into an aware datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@app.post("/internal/refresh-snapshot")
async def refresh_snapshot(
    x_internal_secret: Optional[str] = Header(default=None),
) -> dict:
    """
    Rebuild the realtime snapshot and upsert it to Supabase (id='latest').

    Auth: header ``X-Internal-Secret`` must equal env ``INTERNAL_SECRET``. When
    ``INTERNAL_SECRET`` is unset the endpoint is disabled (503). Rate-limited to one
    refresh per 5 minutes (checked against the stored snapshot). Bounded to 45s.
    """
    expected = os.getenv("INTERNAL_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="endpoint disabled")
    if not x_internal_secret or not hmac.compare_digest(x_internal_secret, expected):
        raise HTTPException(status_code=401, detail="invalid internal secret")

    from db.snapshot_repository import load_latest_snapshot, save_snapshot
    from services.snapshot_refresh import build_fresh_snapshot, summarize_sources

    # Rate limit: reject if the stored snapshot is younger than the min interval.
    last = await load_latest_snapshot()
    if last:
        prev_ts = _parse_snapshot_ts(last.get("fetched_at_utc"))
        if prev_ts is not None:
            age_s = (datetime.now(timezone.utc) - prev_ts).total_seconds()
            if 0 <= age_s < _REFRESH_MIN_INTERVAL_S:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"snapshot refreshed {int(age_s)}s ago; "
                        f"min interval {int(_REFRESH_MIN_INTERVAL_S)}s"
                    ),
                )

    started = time.perf_counter()
    try:
        snapshot = await asyncio.wait_for(build_fresh_snapshot(), timeout=_REFRESH_TIMEOUT_S)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="snapshot build timed out") from exc

    sources = summarize_sources(snapshot)
    # Only persist when at least one source produced real data, so a failed build
    # never clobbers the last good snapshot in Supabase.
    saved = await save_snapshot(snapshot) if sources["ok"] else False
    duration_ms = int((time.perf_counter() - started) * 1000)

    if not sources["ok"]:
        status = "no_data"
    elif saved:
        status = "ok"
    else:
        status = "save_failed"

    return {
        "status": status,
        "fetched_at": snapshot.get("fetched_at_utc"),
        "sources_ok": sources["ok"],
        "sources_failed": sources["failed"],
        "duration_ms": duration_ms,
    }


@app.get("/demo", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def demo_dashboard(
    request: Request,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
) -> HTMLResponse:
    return await _bounded_threadpool(
        build_demo_page,
        pipeline=request.app.state.pipeline,
        origin=origin,
        destination=destination,
    )


@app.get("/predict/realtime")
async def predict_realtime_endpoint(response: Response) -> dict:
    try:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Mon, 30 Jun 2026 00:00:00 GMT"
        response.headers["Link"] = '</predict/realtime-native>; rel="successor-version"'
        return await _bounded_threadpool(predict_realtime)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        _safe_error_response(exc)


@app.get("/predict/realtime-native")
async def predict_realtime_native_endpoint() -> dict:
    try:
        return await _bounded_threadpool(predict_realtime_native)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        _safe_error_response(exc)


_EVACUATION_RISK_LEVELS = {"WARNING", "DANGER"}


@lru_cache(maxsize=1)
def _kota_centroids() -> dict:
    """
    Average kecamatan centroid per kota, derived from the offline BNPB index
    (static fallback — no DB/network). Returns {} on any failure.
    """
    try:
        from services.bnpb_jakarta_mapper import get_jakarta_index_sync

        index = get_jakarta_index_sync() or {}
    except Exception:  # noqa: BLE001
        return {}
    acc: dict[str, list[float]] = {}
    for rec in index.values():
        kab = str(rec.get("kabkot") or "").strip().upper()
        lat, lon = rec.get("lat"), rec.get("lon")
        if kab and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            a = acc.setdefault(kab, [0.0, 0.0, 0.0])
            a[0] += float(lat)
            a[1] += float(lon)
            a[2] += 1
    return {k: (v[0] / v[2], v[1] / v[2]) for k, v in acc.items() if v[2]}


def _kota_centroid(kota: object) -> "tuple[float, float] | None":
    if not kota:
        return None
    return _kota_centroids().get(str(kota).strip().upper())


def _resolve_location_coords(snapshot_dict: dict, result: dict) -> "tuple[float, float] | None":
    """
    Best-effort (lat, lon) for the assessed location, in priority order:
      1. snapshot openweather.coord
      2. mapped kecamatan centroid
      3. mapped kota (mapped_district) centroid — handles bare-kota requests
         like "Jakarta Utara" that have no kecamatan match.
    Returns None only when none resolve. Never raises.
    """
    coord = ((snapshot_dict.get("openweather") or {}).get("coord") or {})
    lat, lon = coord.get("lat"), coord.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    try:
        from services.bnpb_jakarta_mapper import get_kecamatan

        kec_name = ((result.get("mapping_info") or {}).get("kecamatan") or {}).get("name")
        if kec_name:
            rec = get_kecamatan(kec_name) or {}
            klat, klon = rec.get("lat"), rec.get("lon")
            if isinstance(klat, (int, float)) and isinstance(klon, (int, float)):
                return float(klat), float(klon)
    except Exception:  # noqa: BLE001 — fall through to the kota-level fallback
        pass
    # Kota-level fallback uses the pipeline's mapped_district; if that is absent
    # fall back to the raw snapshot location ONLY when it is a specific, valid
    # place — never the synthetic default — so an absent location does not
    # fabricate a centroid.
    kota = (result.get("mapping_info") or {}).get("mapped_district")
    if not kota:
        raw_loc = snapshot_dict.get("location")
        if _is_specific_location(raw_loc):
            kota = _normalize_location(raw_loc)
    return _kota_centroid(kota)


def _enrich_with_evacuation(result: dict, coords: "tuple[float, float] | None") -> dict:
    """
    Add nearest-shelter / evacuation_points to an agentic result when risk is
    elevated and a location coordinate is available. ``coords`` is resolved once
    by the caller. Additive and defensive: on any failure the result is
    returned unchanged.
    """
    try:
        if result.get("risk_level") not in _EVACUATION_RISK_LEVELS:
            return result
        if coords is None:
            return result
        from services.shelter_locator import nearest_shelters

        # Prefer shelters with a known capacity; fall back to nearest regardless
        # of capacity so the field is never empty when coordinates resolve.
        shelters = nearest_shelters(coords[0], coords[1], limit=3, require_capacity=True)
        if not shelters:
            shelters = nearest_shelters(coords[0], coords[1], limit=3, require_capacity=False)
        if not shelters:
            return result
        result["evacuation_points"] = shelters
        result["nearest_shelter"] = shelters[0]
        vuln = result.get("vulnerability_context")
        if isinstance(vuln, dict):
            vuln["nearest_shelter"] = shelters[0]
    except Exception:  # noqa: BLE001 — never let enrichment break the prediction
        return result
    return result


# Pump density that maps to a full drainage score of 1.0 (count / 10, capped).
_PUMP_FULL_SCORE_COUNT = 10.0
_PUMP_RADIUS_M = 5000.0
_SCHOOL_RADIUS_M = 3000.0


def _enrich_with_infrastructure(result: dict, coords: "tuple[float, float] | None") -> dict:
    """
    Populate infrastructure context from local JSON datasets via haversine only
    (no Supabase / external calls). Reuses the already-resolved ``coords``.

      * pump_drainage_score      -> vulnerability_context  (pumps within 5 km,
                                     score = min(count / 10, 1.0))
      * in_river_overflow_zone   -> vulnerability_context  (coords -> nearest
                                     kecamatan centroid -> river-overflow set;
                                     the source has no point geometry, so this
                                     is a name join driven by the coordinate)
      * vulnerable_facilities_nearby -> top-level list of schools within 3 km
                                     ({name, kelurahan, distance_km})

    Additive and defensive; never alters risk_level/probability/etc.
    """
    if coords is None:
        return result
    lat, lon = coords
    try:
        from services.shelter_locator import haversine_m

        vuln = result.get("vulnerability_context")

        # ── pump_drainage_score (pumps within 5 km) ──────────────────────────
        try:
            from services.pump_locator import load_pumps

            count = 0
            for p in load_pumps():
                plat, plon = p.get("lat"), p.get("lon")
                if isinstance(plat, (int, float)) and isinstance(plon, (int, float)) \
                        and haversine_m(lat, lon, plat, plon) <= _PUMP_RADIUS_M:
                    count += 1
            score = round(min(count / _PUMP_FULL_SCORE_COUNT, 1.0), 4)
            if isinstance(vuln, dict):
                vuln["pump_drainage_score"] = score
                vuln["pump_count_within_5km"] = count
        except Exception:  # noqa: BLE001
            pass

        # ── in_river_overflow_zone (coord -> kecamatan -> overflow set) ──────
        try:
            from services.bnpb_jakarta_mapper import get_kecamatan_by_coords
            from services.flood_prone_locator import river_overflow_zone

            kec = get_kecamatan_by_coords(lat, lon) or {}
            kec_name = kec.get("name")
            ro = river_overflow_zone(kecamatan=kec_name) if kec_name else {
                "in_river_overflow_zone": False, "affected_river": None,
            }
            if isinstance(vuln, dict):
                vuln["in_river_overflow_zone"] = bool(ro.get("in_river_overflow_zone"))
                vuln["affected_river"] = ro.get("affected_river")
        except Exception:  # noqa: BLE001
            pass

        # ── vulnerable_facilities_nearby (schools within 3 km) ───────────────
        try:
            from services.school_locator import nearby_schools

            schools = nearby_schools(lat, lon, radius_m=_SCHOOL_RADIUS_M, limit=10)
            result["vulnerable_facilities_nearby"] = [
                {
                    "name": s.get("name"),
                    "kelurahan": s.get("kelurahan"),
                    "distance_km": round((s.get("distance_m") or 0.0) / 1000.0, 2),
                }
                for s in schools
            ]
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001 — never let enrichment break the prediction
        return result
    return result


@app.post("/predict/agentic", dependencies=[Depends(require_api_key)])
async def predict_agentic_endpoint(
    request: Request,
    snapshot: SnapshotIn,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    try:
        cached = await _bounded_threadpool(_get_idempotent_response, idempotency_key)
        if cached is not None:
            return cached

        snapshot_dict = _model_to_dict(snapshot)
        _reject_non_finite(snapshot_dict)
        result = await _bounded_threadpool(
            request.app.state.pipeline.run,
            snapshot_dict,
            origin=origin,
            destination=destination,
        )
        # Resolve the location coordinate ONCE, then reuse it for every
        # geospatial enrichment (evacuation + infrastructure).
        coords = _resolve_location_coords(snapshot_dict, result)
        result = _enrich_with_evacuation(result, coords)
        result = _enrich_with_infrastructure(result, coords)
        await _bounded_threadpool(_store_idempotent_response, idempotency_key, result)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        _safe_error_response(exc)
