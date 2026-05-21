"""
BNPB Jakarta kecamatan-level mapper.

Pulls the four BNPB InaRISK Jakarta dashboard GeoJSON endpoints, filters to
DKI Jakarta (PROVNO=31, fallback bbox), and exposes:

  * ``get_kecamatan(name)`` — case-insensitive alias lookup
  * ``get_kecamatan_by_coords(lat, lon)`` — nearest-centroid lookup,
    capped at ``_MAX_RADIUS_KM``
  * ``get_jakarta_index()`` — async cached singleton (24 h TTL)
  * ``save_static_fallback()`` / ``load_static_fallback()`` — on-disk cache

Complements the existing kotamadya-level ``app.services.bnpb_context``:
this module resolves at kecamatan granularity (44 + 2 records) and feeds
its ``kabkot`` field into the kotamadya-level vulnerability gate. The two
modules do not overlap — they answer different questions:

  bnpb_context       : "Given a kabkot string, what is the IRBI score?"
  bnpb_jakarta_mapper: "Given a free-form name OR (lat, lon), which
                       kecamatan is this — and which kabkot owns it?"

Failure semantics
-----------------
Every public function NEVER raises. Network / parser failures fall through
to the bundled static JSON at ``data/bnpb_jakarta_static.json``. The
``get_jakarta_index`` async loader guarantees a non-empty index — if the
disk fallback is also missing, a one-line warning is logged and an empty
dict is returned (callers handle gracefully via the kabkot=UNKNOWN /
vulnerability_score=0.5 contract).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx

from services.bnpb_context import get_vulnerability_context
from services.dem_elevation import get_elevation


logger = logging.getLogger(__name__)


# ─── Endpoints ────────────────────────────────────────────────────────────────

_ENDPOINTS: dict[str, str] = {
    # GeoJSON FeatureCollection of kabupaten/kota points (NAMOBJ at kabkot level).
    "kabupaten_kota": "https://inarisk.bnpb.go.id/dashboard_jakarta/data/Ibukota_Kabupaten_rbi.json",
    # Provincial capital point (single feature; useful for province sanity-check).
    "provinsi":       "https://inarisk.bnpb.go.id/dashboard_jakarta/data/Ibukota_Provinsi_rbi.json",
    # Per-kecamatan centroids — the primary source for our index.
    "kecamatan":      "https://inarisk.bnpb.go.id/dashboard_jakarta/data/Ibukota_Kecamatan_rbi.json",
    # Index of API URLs the dashboard itself uses. May be non-GeoJSON.
    "api_links":      "https://inarisk.bnpb.go.id/dashboard_jakarta/data/LINK_API_KAB_KOTA.json",
}

_TIMEOUT_SECONDS = float(os.getenv("BNPB_MAPPER_TIMEOUT_S", "8.0"))
_CACHE_TTL_SECONDS = float(os.getenv("BNPB_MAPPER_CACHE_TTL_S", str(24 * 3600)))
_MAX_RADIUS_KM = float(os.getenv("BNPB_MAPPER_MAX_RADIUS_KM", "5.0"))


# ─── Jakarta filter ───────────────────────────────────────────────────────────

JAKARTA_BBOX: dict[str, float] = {
    "lat_min": -6.37, "lat_max": -6.07,
    "lon_min": 106.65, "lon_max": 107.00,
}

# BPS kabkot codes for the 6 DKI Jakarta administrative units. Used as the
# AUTHORITATIVE Jakarta filter because the live BNPB inarisk endpoint also
# carries Jabodetabek neighbours (Depok 3276, Bekasi 3275, Tangerang 3671,
# Tangsel 3674 …) whose centroids fall inside the Jakarta bbox — a pure
# bbox filter would silently pollute the index with non-Jakarta kecamatan.
_JAKARTA_IDKAB: frozenset[int] = frozenset({3101, 3171, 3172, 3173, 3174, 3175})


def _in_jakarta_bbox(lat: float, lon: float) -> bool:
    return (
        JAKARTA_BBOX["lat_min"] <= lat <= JAKARTA_BBOX["lat_max"]
        and JAKARTA_BBOX["lon_min"] <= lon <= JAKARTA_BBOX["lon_max"]
    )


def _is_jakarta_feature(props: dict[str, Any], coords: list) -> bool:
    """
    Multi-key DKI Jakarta classifier. A feature is kept iff:
      1. ``PROVNO == "31"``                              → strong evidence
      2. ``IDKAB`` ∈ ``_JAKARTA_IDKAB``                  → strong evidence
      3. PROVNO missing AND IDKAB missing AND bbox hit   → weak fallback
    Features carrying explicit non-Jakarta codes (e.g. PROVNO=32 / IDKAB=3275)
    are REJECTED even when their centroid falls inside the Jakarta bbox —
    Jabodetabek is contiguous and bbox alone is not specific enough.
    """
    provno = str(props.get("PROVNO") or "").strip()
    if provno == "31":
        return True
    if provno and provno != "31":
        return False  # Explicit non-Jakarta province → reject.

    try:
        idkab = int(props.get("IDKAB") or 0)
    except (TypeError, ValueError):
        idkab = 0
    if idkab in _JAKARTA_IDKAB:
        return True
    if idkab and idkab not in _JAKARTA_IDKAB:
        return False  # Explicit non-Jakarta kabkot → reject.

    # PROVNO and IDKAB both missing — last-resort bbox check.
    if len(coords) >= 2:
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            return False
        return _in_jakarta_bbox(lat, lon)
    return False


# ─── Static fallback ──────────────────────────────────────────────────────────

_DEFAULT_STATIC_PATH = Path(
    os.getenv(
        "BNPB_MAPPER_STATIC_PATH",
        str(Path(__file__).resolve().parents[1] / "data" / "bnpb_jakarta_static.json"),
    )
)


def load_static_fallback(path: Path | str = _DEFAULT_STATIC_PATH) -> dict[str, dict[str, Any]]:
    """
    Read the on-disk kecamatan index. Returns ``{}`` (rather than raising)
    when the file is missing or malformed.
    """
    p = Path(path)
    if not p.exists():
        logger.warning("bnpb_mapper: static fallback missing at %s", p)
        return {}
    try:
        with open(p, "r", encoding="utf-8-sig") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("bnpb_mapper: static fallback unreadable at %s: %s", p, exc)
        return {}

    raw_kec = payload.get("kecamatan") or {}
    return _materialise_index(raw_kec)


def save_static_fallback(
    index: dict[str, dict[str, Any]],
    *,
    path: Path | str = _DEFAULT_STATIC_PATH,
    now: datetime | None = None,
) -> Path:
    """
    Atomic write of the current index to ``path``. Stamps ``generated_at``
    with the supplied or current UTC clock for replay/staleness audits.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    ref_now = now if now is not None else datetime.now(timezone.utc)
    serialisable = {
        "_meta": {
            "schema_version": "1",
            "generated_at": ref_now.isoformat().replace("+00:00", "Z"),
            "source": "inarisk.bnpb.go.id (live fetch)",
            "provno": "31",
            "review_cadence_days": 365,
        },
        "kecamatan": {
            name: {
                "kabkot": rec.get("kabkot", "UNKNOWN"),
                "idkec":  rec.get("idkec", 0),
                "idkab":  rec.get("idkab", 0),
                "lat":    rec.get("lat", 0.0),
                "lon":    rec.get("lon", 0.0),
                "remark": rec.get("remark"),
            }
            for name, rec in index.items()
        },
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(serialisable, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return p


def _materialise_index(raw_kec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Normalise a raw kecamatan dict (from either fallback or fetch) into the
    canonical in-memory shape. Adds an ``aliases`` list per record so the
    name-lookup path can hit case / prefix variants without recomputing.
    """
    index: dict[str, dict[str, Any]] = {}
    for raw_name, rec in raw_kec.items():
        if not isinstance(rec, dict):
            continue
        upper_name = str(raw_name or "").strip().upper()
        if not upper_name:
            continue
        try:
            lat = float(rec.get("lat") or 0.0)
            lon = float(rec.get("lon") or 0.0)
        except (TypeError, ValueError):
            lat, lon = 0.0, 0.0
        index[upper_name] = {
            "kabkot": str(rec.get("kabkot") or "UNKNOWN").strip().upper(),
            "idkec":  int(rec.get("idkec") or 0),
            "idkab":  int(rec.get("idkab") or 0),
            "lat":    lat,
            "lon":    lon,
            "remark": rec.get("remark"),
            "aliases": _build_aliases(upper_name),
        }
    return index


def _build_aliases(upper_name: str) -> list[str]:
    """
    Precompute the alias forms ``get_kecamatan`` will accept for a name.
    Cheap to store; eliminates per-call string churn.
    """
    title = " ".join(part.capitalize() for part in upper_name.split())
    return list({upper_name, upper_name.lower(), title, title.replace(" ", "_")})


# ─── Live fetch ───────────────────────────────────────────────────────────────


async def fetch_all_endpoints(
    *,
    timeout: float = _TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """
    Fetch all four BNPB endpoints concurrently with per-request timeout.
    Failed endpoints are logged at WARN and yield ``None`` in the result
    dict so the parser can fall back to the disk index for missing pieces.
    """
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = {
            label: asyncio.create_task(_safe_get(client, url))
            for label, url in _ENDPOINTS.items()
        }
        for label, task in tasks.items():
            try:
                results[label] = await task
            except Exception as exc:  # noqa: BLE001 — defensive: per-endpoint quarantine
                logger.warning(
                    "bnpb_mapper: endpoint %s failed (%s) — falling back.",
                    label, exc,
                )
                results[label] = None
    return results


async def _safe_get(client: httpx.AsyncClient, url: str) -> Any:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        logger.warning("bnpb_mapper: %s → %s", url, exc)
        return None
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("bnpb_mapper: %s returned non-JSON (%s)", url, exc)
        return None


def _features_in_jakarta(payload: Any) -> Iterable[dict[str, Any]]:
    """
    Yield feature dicts for kecamatan inside DKI Jakarta. Accepts:
      * GeoJSON FeatureCollection (``payload["features"]``)
      * Bare list of features
      * ``None`` (yields nothing)

    Filter rule per spec:
      1. ``properties.PROVNO == "31"``
      2. Fallback: coordinate within ``JAKARTA_BBOX``
    """
    if payload is None:
        return
    if isinstance(payload, dict):
        features = payload.get("features") or []
    elif isinstance(payload, list):
        features = payload
    else:
        return

    for feat in features:
        if not isinstance(feat, dict):
            continue
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if _is_jakarta_feature(props, coords):
            yield feat


def _build_index_from_fetch(fetch_result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Materialise the kecamatan index from the per-endpoint fetch result.
    The ``kecamatan`` endpoint is the primary source; the kabupaten /
    provinsi endpoints supply the ``kabkot`` enrichment when the
    kecamatan record carries an empty KABKOT field.
    """
    raw_kec: dict[str, dict[str, Any]] = {}
    for feat in _features_in_jakarta(fetch_result.get("kecamatan")):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [0.0, 0.0]
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except (TypeError, ValueError):
            lat, lon = 0.0, 0.0

        name = str(props.get("KECAMATAN") or props.get("NAMOBJ") or "").strip()
        if not name:
            continue
        raw_kec[name.upper()] = {
            "kabkot": str(props.get("KABKOT") or "").strip().upper() or "UNKNOWN",
            "idkec":  int(props.get("IDKEC") or 0),
            "idkab":  int(props.get("IDKAB") or 0),
            "lat":    lat,
            "lon":    lon,
            "remark": props.get("REMARK"),
        }

    if not raw_kec:
        logger.warning("bnpb_mapper: live fetch produced 0 Jakarta kecamatan — empty result.")
    return _materialise_index(raw_kec)


# ─── Cached singleton ─────────────────────────────────────────────────────────

_cache: dict[str, Any] = {"index": {}, "fetched_at": 0.0}
_cache_lock = asyncio.Lock()


def _cache_fresh() -> bool:
    return (
        bool(_cache.get("index"))
        and (time.monotonic() - float(_cache.get("fetched_at", 0.0)) < _CACHE_TTL_SECONDS)
    )


async def get_jakarta_index() -> dict[str, dict[str, Any]]:
    """
    Return the cached kecamatan index, fetching fresh data when the cache
    is empty or older than ``_CACHE_TTL_SECONDS``.

    Lookup ladder:
      1. In-memory cache (24 h TTL by default).
      2. Live BNPB endpoints (concurrent fetch).
      3. ``data/bnpb_jakarta_static.json`` (bundled fallback).

    The contract is "never return null". When all three sources fail we
    log an error and return ``{}`` — callers' kabkot=UNKNOWN /
    vulnerability_score=0.5 default kicks in downstream.
    """
    if _cache_fresh():
        return _cache["index"]

    async with _cache_lock:
        # Double-check under the lock in case another coroutine refreshed.
        if _cache_fresh():
            return _cache["index"]

        try:
            fetched = await fetch_all_endpoints()
            index = _build_index_from_fetch(fetched)
            if index:
                _cache["index"] = index
                _cache["fetched_at"] = time.monotonic()
                # Best-effort persist so the next cold start has fresh data.
                try:
                    save_static_fallback(index)
                except OSError as exc:
                    logger.warning("bnpb_mapper: cache flush to disk failed: %s", exc)
                return index
            logger.warning(
                "bnpb_mapper: live fetch produced empty index — using static fallback."
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError, OSError) as exc:
            logger.warning(
                "bnpb_mapper: live fetch raised (%s) — using static fallback.", exc
            )

        # Static fallback path.
        static = load_static_fallback()
        if static:
            _cache["index"] = static
            _cache["fetched_at"] = time.monotonic()
            return static

        logger.error(
            "bnpb_mapper: all sources exhausted — returning empty index. "
            "Callers will see kabkot=UNKNOWN / vulnerability_score=0.5 default."
        )
        return {}


def get_jakarta_index_sync() -> dict[str, dict[str, Any]]:
    """
    Synchronous accessor — returns whatever is currently in the in-memory
    cache, or the bundled static fallback when the cache is empty. Used by
    the sync lookup helpers (``get_kecamatan`` etc.) so they don't require
    an event loop. Does NOT trigger a live fetch.
    """
    if _cache.get("index"):
        return _cache["index"]
    static = load_static_fallback()
    if static:
        _cache["index"] = static
        _cache["fetched_at"] = time.monotonic()
    return _cache.get("index") or {}


# ─── Public lookup helpers ────────────────────────────────────────────────────


_SHORTHAND_KABKOT = {
    "JAK-UT":  "JAKARTA UTARA",
    "JAKUT":   "JAKARTA UTARA",
    "JAK-SEL": "JAKARTA SELATAN",
    "JAKSEL":  "JAKARTA SELATAN",
    "JAK-PUS": "JAKARTA PUSAT",
    "JAKPUS":  "JAKARTA PUSAT",
    "JAK-BAR": "JAKARTA BARAT",
    "JAKBAR":  "JAKARTA BARAT",
    "JAK-TIM": "JAKARTA TIMUR",
    "JAKTIM":  "JAKARTA TIMUR",
}


def _normalise_query(name: str) -> str:
    """
    Strip whitespace, drop ``KEL.`` / ``KEC.`` / ``KECAMATAN`` / ``KELURAHAN``
    prefixes, expand a handful of common short forms (``Jak-Ut`` → ``Jakarta
    Utara``), and uppercase. Returns the empty string for falsy / non-str
    input so the caller's branch falls cleanly through to ``None``.
    """
    if not isinstance(name, str):
        return ""
    cleaned = name.strip()
    if not cleaned:
        return ""

    upper = cleaned.upper()
    for prefix in ("KEL.", "KELURAHAN", "KEC.", "KECAMATAN"):
        if upper.startswith(prefix):
            upper = upper[len(prefix):].strip()
    return _SHORTHAND_KABKOT.get(upper, upper)


def get_kecamatan(name: str) -> dict[str, Any] | None:
    """
    Case-insensitive lookup with prefix stripping and short-form
    expansion. Returns the kecamatan record (or ``None``) — never raises.

    The lookup happens against the in-memory cache; call
    ``await get_jakarta_index()`` once during startup to populate it.
    Falls back to the bundled static JSON when the cache is cold.
    """
    query = _normalise_query(name)
    if not query:
        return None

    index = get_jakarta_index_sync()
    if not index:
        return None

    # Exact match on kecamatan name.
    if query in index:
        return _record_with_name(index, query)

    # A bare kabkot ("JAKARTA UTARA", "Jak-Ut") deliberately does NOT pick
    # an arbitrary kecamatan — that would silently mis-attribute decisions
    # to one of several valid kecamatan. Callers wanting kabkot-level data
    # should use bnpb_context.get_vulnerability_context() instead.
    if query in {rec["kabkot"] for rec in index.values()}:
        return None

    # Substring match — last-resort, sorted by name length descending so
    # the most specific candidate wins. Skips when the query is too short
    # to be unambiguous (e.g. bare "JAKARTA").
    if len(query) < 5:
        return None
    candidates = [k for k in index if query in k or k in query]
    if not candidates:
        return None
    best = sorted(candidates, key=lambda k: -len(k))[0]
    return _record_with_name(index, best)


def _record_with_name(
    index: dict[str, dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    """Return the record under ``key`` annotated with its canonical name."""
    record = dict(index[key])
    record["name"] = key
    # Additive enrichment: nearest named waterway for this kecamatan, from the
    # precomputed table. Defensive — never blocks a mapping if data is absent.
    try:
        from services.river_locator import nearest_river_for_kecamatan

        near = nearest_river_for_kecamatan(key)
        if near:
            record["nearest_river"] = near.get("nearest_river")
            record["waterway_type"] = near.get("waterway_type")
            record["distance_to_river_m"] = near.get("distance_to_river_m")
    except Exception:  # noqa: BLE001 — enrichment is best-effort
        pass
    return record


def get_kecamatan_by_coords(
    lat: float,
    lon: float,
    *,
    max_radius_km: float = _MAX_RADIUS_KM,
) -> dict[str, Any] | None:
    """
    Find the nearest kecamatan centroid to ``(lat, lon)``. Returns ``None``
    when the point is outside the Jakarta bbox OR when the nearest
    centroid is more than ``max_radius_km`` away. Never raises.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not _in_jakarta_bbox(lat_f, lon_f):
        return None

    index = get_jakarta_index_sync()
    if not index:
        return None

    best_key: str | None = None
    best_km: float = math.inf
    for key, record in index.items():
        try:
            dist = _haversine_km(lat_f, lon_f, float(record["lat"]), float(record["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if dist < best_km:
            best_km = dist
            best_key = key

    if best_key is None or best_km > max_radius_km:
        return None
    record = _record_with_name(index, best_key)
    record["distance_km"] = round(best_km, 4)
    return record


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two (lat, lon) pairs."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_vulnerability_with_elevation(
    kecamatan_name: str,
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """
    Blend BNPB structural vulnerability with DEM-derived elevation risk.

    Formula:
      0.6 * bnpb_score + 0.4 * elevation_risk_score
    """
    try:
        kecamatan_record = get_kecamatan(kecamatan_name) or get_kecamatan_by_coords(lat, lon)
        district_query = str(kecamatan_name or "").strip()
        if kecamatan_record is not None:
            kabkot = str(kecamatan_record.get("kabkot") or "").strip()
            if kabkot and kabkot != "UNKNOWN":
                district_query = " ".join(part.capitalize() for part in kabkot.split())

        vuln_context, mapping_info = get_vulnerability_context(district_query)
        bnpb_score = float(vuln_context.effective_irbi_score) if vuln_context is not None else 0.5

        elevation = get_elevation(lat, lon)
        elevation_m = elevation.get("elevation_m")
        elevation_risk_score = _elevation_risk_score(elevation_m)
        combined_score = round((0.6 * bnpb_score) + (0.4 * elevation_risk_score), 4)

        return {
            "combined_score": combined_score,
            "bnpb_score": round(bnpb_score, 4),
            "elevation_risk_score": round(elevation_risk_score, 4),
            "district": getattr(vuln_context, "district", None),
            "mapping_info": mapping_info,
            "kecamatan": kecamatan_record.get("name") if kecamatan_record else None,
            "elevation_m": elevation_m,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "get_vulnerability_with_elevation(%r, %r, %r) failed: %s",
            kecamatan_name,
            lat,
            lon,
            exc,
        )
        return {
            "combined_score": 0.5,
            "bnpb_score": 0.5,
            "elevation_risk_score": 0.5,
            "district": None,
            "mapping_info": {
                "input_location": kecamatan_name,
                "mapped_district": None,
                "confidence": 0.0,
            },
            "kecamatan": None,
            "elevation_m": None,
        }


def _elevation_risk_score(elevation_m: float | None) -> float:
    if elevation_m is None:
        return 0.5
    if elevation_m < 0.0:
        return 1.0
    if elevation_m <= 2.0:
        return 0.85
    if elevation_m <= 5.0:
        return 0.65
    if elevation_m <= 10.0:
        return 0.40
    return 0.20


# ─── CLI smoke-test ───────────────────────────────────────────────────────────


async def _cli_smoke() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    index = await get_jakarta_index()
    print(json.dumps({
        "kecamatan_count":  len(index),
        "sample_lookup":    get_kecamatan("Penjaringan"),
        "alias_lookup":     get_kecamatan("kec. tanjung priok"),
        "shorthand_lookup": get_kecamatan("Jak-Ut"),
        "coord_lookup":     get_kecamatan_by_coords(-6.1211, 106.7942),
        "out_of_bbox":      get_kecamatan_by_coords(-7.5, 110.0),
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(_cli_smoke()))
