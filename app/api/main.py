from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv
# Load the project-root .env explicitly. dotenv's default search walks up from
# this file's directory and would otherwise pick up app/.env first, which lacks
# FLOOD_API_KEYS. override=False lets process/shell env (e.g. test fixtures and
# deployment env vars) take precedence over the file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
import asyncio
import hashlib
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from psycopg2.extras import Json

from app.api.dashboard import build_demo_page
from app.api.routes.agentic_llm import router as agentic_llm_router
from app.api.observability import (
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
    get_logger,
    metrics_response,
)
from app.api.security import require_api_key
from app.pipeline.flood_pipeline import FloodDecisionPipeline
from app.realtime_native.bundle import load_runtime_bundle
from app.realtime_native.inference import predict_realtime_native
from app.services.decision_engine import _canonical_default_thresholds
from app.services.prediction_service import predict_realtime
from db.psycopg2_connection import close_pool, pooled_connection

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
        from app.services.bnpb_context import (
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
        from app.services.bnpb_context import (
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
        return 15.0


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


def _store_idempotent_response(key: str | None, response: dict) -> None:
    if not key:
        return
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    load_runtime_bundle()
    app.state.pipeline = FloodDecisionPipeline()
    try:
        yield
    finally:
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


@app.get("/healthz")
@app.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


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


def _resolve_location_coords(snapshot_dict: dict, result: dict) -> "tuple[float, float] | None":
    """
    Best-effort (lat, lon) for the assessed location. Prefers the snapshot's
    OpenWeather coordinate; falls back to the mapped kecamatan centroid. Returns
    None when neither is available. Never raises.
    """
    coord = ((snapshot_dict.get("openweather") or {}).get("coord") or {})
    lat, lon = coord.get("lat"), coord.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    try:
        from app.services.bnpb_jakarta_mapper import get_kecamatan

        kec_name = ((result.get("mapping_info") or {}).get("kecamatan") or {}).get("name")
        if kec_name:
            rec = get_kecamatan(kec_name) or {}
            klat, klon = rec.get("lat"), rec.get("lon")
            if isinstance(klat, (int, float)) and isinstance(klon, (int, float)):
                return float(klat), float(klon)
    except Exception:  # noqa: BLE001 — enrichment must never break the response
        return None
    return None


def _enrich_with_evacuation(result: dict, snapshot_dict: dict) -> dict:
    """
    Add nearest-shelter / evacuation_points to an agentic result when risk is
    elevated and a location coordinate is resolvable. Additive and defensive:
    on any failure the result is returned unchanged.
    """
    try:
        if result.get("risk_level") not in _EVACUATION_RISK_LEVELS:
            return result
        coords = _resolve_location_coords(snapshot_dict, result)
        if coords is None:
            return result
        from app.services.shelter_locator import nearest_shelters

        shelters = nearest_shelters(coords[0], coords[1], limit=3, require_capacity=True)
        if not shelters:
            return result
        result["evacuation_points"] = shelters
        result["nearest_shelter"] = shelters[0]
        vuln = result.get("vulnerability_context")
        if isinstance(vuln, dict):
            vuln["nearest_shelter"] = shelters[0]

        # Vulnerable facilities (flood-prone schools = children) within 500 m.
        try:
            from app.services.school_locator import nearby_schools

            schools = nearby_schools(coords[0], coords[1], radius_m=500.0, limit=5)
            if schools:
                result["vulnerable_facilities_nearby"] = schools
        except Exception:  # noqa: BLE001 — best-effort enrichment
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
        result = _enrich_with_evacuation(result, snapshot_dict)
        await _bounded_threadpool(_store_idempotent_response, idempotency_key, result)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="snapshot_unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        _safe_error_response(exc)
