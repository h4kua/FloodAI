"""
TMA (Tinggi Muka Air) scraper — Jakarta flood-gate water-level ingestion.

Fetches real-time water-height readings from a scraping proxy and degrades
gracefully when the upstream payload is empty, malformed, or unreachable.

Status taxonomy (deliberately narrow):

  OK        — fresh fetch produced ≥1 schema-valid records.
  STALE     — fresh fetch produced no usable records BUT either:
                (a) a cached value still exists and is < ``cache_max_age_min``
                    minutes old (returned as ``source="cache"``), OR
                (b) no cache yet — returned with ``data=[]`` and a clear reason.
              STALE is the EXPECTED status when upstream is silently degraded.
              Downstream consumers MUST treat STALE as low-severity (caller may
              suppress confidence penalty if the cached age is recent).
  DEGRADED  — every fetch attempt raised a transport-level error (timeout,
              connection refused, HTTP 5xx). Distinct from STALE: the upstream
              is reachable + responding, just with empty content.
  INVALID   — the response is corrupt at the protocol level (not JSON, wrong
              container type, NaN/Inf heights, length mismatch). Reserved for
              cases where serving the data would be unsafe; never returned for
              merely missing fields.

This module never raises; every code path returns the dict described in
``fetch_tma_data``'s docstring.

Operator knobs (env vars):

  TMA_PROXY_URL                Override the default proxy URL.
  TMA_TIMEOUT_SECONDS          HTTP timeout per attempt (default 8).
  TMA_MAX_RETRIES              Network-error retries (default 2).
  TMA_RETRY_DELAY_SECONDS      Backoff base (default 2).
  TMA_CACHE_MAX_AGE_MINUTES    Stop serving cached data after this age
                               (default 60; older cache → empty STALE).
  TMA_HEIGHT_MAX_CM            Reject obviously impossible height readings
                               (default 2000; protects against scraper drift).
"""

from __future__ import annotations

import logging
import math
import os
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from api.observability import get_logger

logger = logging.getLogger(__name__)
_log = get_logger("flood.tma_scraper")


# ─── Configuration ────────────────────────────────────────────────────────────

# No default proxy: the previous default pointed at an abandoned third-party
# domain that returned 502. Configure a verified endpoint via TMA_PROXY_URL.
# When unset, fetch_tma_data short-circuits to a STALE/empty response, which
# downstream consumers already treat as "unknown, not invalid".
_DEFAULT_PROXY_URL = ""


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _proxy_url() -> str:
    return os.getenv("TMA_PROXY_URL", _DEFAULT_PROXY_URL)


def _timeout_seconds() -> float:
    return _env_float("TMA_TIMEOUT_SECONDS", 8.0)


def _max_retries() -> int:
    return max(1, _env_int("TMA_MAX_RETRIES", 2))


def _retry_delay_seconds() -> float:
    return _env_float("TMA_RETRY_DELAY_SECONDS", 2.0)


def _cache_max_age() -> timedelta:
    return timedelta(minutes=_env_float("TMA_CACHE_MAX_AGE_MINUTES", 60.0))


def _height_max_cm() -> float:
    return _env_float("TMA_HEIGHT_MAX_CM", 2000.0)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seconds_until_deadline(deadline: datetime | None, *, now: datetime) -> float | None:
    if deadline is None:
        return None
    normalized_deadline = (
        deadline if deadline.tzinfo is not None else deadline.replace(tzinfo=timezone.utc)
    )
    return (normalized_deadline - now).total_seconds()


def _deadline_exceeded_response(
    *,
    deadline: datetime,
    attempt: int,
    max_retries: int,
    last_error: str,
    cache_state: dict | None,
    now: datetime,
) -> dict:
    _log.warning(
        "tma_retry_deadline_exceeded",
        attempt=attempt,
        max_retries=max_retries,
        deadline=deadline.isoformat(),
        last_error=last_error,
    )
    return _degraded_response(
        f"Retry deadline exceeded before attempt {attempt} of {max_retries}. Last error: {last_error}",
        cache_state=cache_state,
        now=now,
    )


# ─── Schema validation ────────────────────────────────────────────────────────


def _split_csv(value: Any) -> list[str]:
    """Accept a comma-separated string or a list; return cleaned string tokens."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def _coerce_height(value: str) -> float | None:
    """Parse one height token. Reject NaN/Inf, out-of-range, non-numeric."""
    try:
        height = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(height) or math.isinf(height):
        return None
    if height < 0.0 or height > _height_max_cm():
        return None
    return height


def _parse_records(raw: dict) -> tuple[list[dict], str | None, str]:
    """
    Convert raw JSON into structured records.

    Returns (records, note, classification) where ``classification`` is one of:
      "ok"      — at least one record successfully parsed.
      "empty"   — required fields are absent/empty (NOT corruption → STALE).
      "invalid" — fields present but the data itself is malformed
                  (length mismatch, all values fail numeric validation).
    """
    times = _split_csv(raw.get("time"))
    heights_raw = _split_csv(raw.get("ketinggian"))

    if not times and not heights_raw:
        return [], "Both 'time' and 'ketinggian' fields are absent or empty.", "empty"
    if not times:
        return [], "Field 'time' is absent or empty.", "empty"
    if not heights_raw:
        return [], "Field 'ketinggian' is absent or empty.", "empty"

    if len(times) != len(heights_raw):
        return (
            [],
            f"Length mismatch: {len(times)} time entries vs {len(heights_raw)} ketinggian entries.",
            "invalid",
        )

    records: list[dict] = []
    skipped = 0
    for raw_time, raw_height in zip(times, heights_raw):
        height = _coerce_height(raw_height)
        if height is None:
            skipped += 1
            continue
        records.append({"time": raw_time, "height_cm": height})

    if not records:
        return (
            [],
            f"All {len(times)} ketinggian values failed numeric validation "
            f"(NaN/Inf/out-of-range/non-numeric).",
            "invalid",
        )

    note = f"{skipped} record(s) skipped (failed numeric validation)." if skipped else None
    return records, note, "ok"


# ─── Response builders ────────────────────────────────────────────────────────


def _build_response(
    status: str,
    reason: str | None,
    source: str,
    data: list[dict],
    *,
    now: datetime | None = None,
    fetched_at: datetime | None = None,
    stale_age_minutes: float | None = None,
) -> dict:
    """
    ``fetched_at`` is the ORIGINAL live-fetch timestamp (preserved across cache
    hits so age is meaningful). ``now`` is the orchestrator clock used for
    age arithmetic when the caller did not supply ``fetched_at`` explicitly.
    """
    ref_now = now if now is not None else datetime.now(timezone.utc)
    real_fetched_at = fetched_at if fetched_at is not None else ref_now
    payload: dict[str, Any] = {
        "status": status,
        "reason": reason,
        "source": source,
        # Scraping-proxy data is always low reliability — operators must know this.
        "reliability": "low",
        "fetched_at": real_fetched_at.isoformat(),
        "served_at": ref_now.isoformat(),
        "data": data,
    }
    if stale_age_minutes is not None:
        payload["stale_age_minutes"] = round(stale_age_minutes, 2)
    return payload


def _cache_age_minutes(cache_state: dict, now: datetime) -> float | None:
    """Minutes since the original live fetch succeeded. None when cache empty."""
    if not cache_state:
        return None
    cached_at = cache_state.get("last_valid_at")
    if not isinstance(cached_at, datetime):
        return None
    if cached_at.tzinfo is None:
        cached_at = cached_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - cached_at).total_seconds() / 60.0)


def _serve_from_cache_if_fresh(
    cache_state: dict | None,
    reason_prefix: str,
    *,
    now: datetime,
) -> dict | None:
    """Return a STALE-from-cache response if cache exists and is within TTL."""
    if not cache_state:
        return None
    last = cache_state.get("last_valid")
    if not isinstance(last, dict):
        return None
    age_min = _cache_age_minutes(cache_state, now)
    if age_min is None:
        return None
    max_age = _cache_max_age()
    if age_min > max_age.total_seconds() / 60.0:
        logger.warning(
            "tma_scraper: cache age %.1f min exceeds TTL %.0f min — discarding cache.",
            age_min,
            max_age.total_seconds() / 60.0,
        )
        return None
    logger.info(
        "tma_scraper: serving STALE from cache (age=%.1f min) — %s",
        age_min,
        reason_prefix,
    )
    return _build_response(
        status="STALE",
        reason=(
            f"{reason_prefix} — serving last valid cached data "
            f"(age={age_min:.1f} min, ttl={max_age.total_seconds() / 60.0:.0f} min)."
        ),
        source="cache",
        data=list(last.get("data") or []),
        now=now,
        fetched_at=cache_state.get("last_valid_at"),
        stale_age_minutes=age_min,
    )


# ─── Failure-path response factories ──────────────────────────────────────────


def _stale_response(
    reason: str,
    *,
    cache_state: dict | None,
    now: datetime,
) -> dict:
    """
    Build a STALE response. Tries cache first; falls back to empty STALE so
    callers can distinguish 'no data yet' from 'corrupt data' (INVALID).
    """
    cached = _serve_from_cache_if_fresh(cache_state, reason_prefix=reason, now=now)
    if cached is not None:
        return cached
    return _build_response(
        status="STALE",
        reason=(
            reason
            + " — no fresh cache available; downstream consumers should treat as unknown, not invalid."
        ),
        source="scraping_proxy",
        data=[],
        now=now,
    )


def _degraded_response(
    reason: str,
    *,
    cache_state: dict | None,
    now: datetime,
) -> dict:
    """Transport-level failure. Prefer cache; otherwise empty DEGRADED."""
    cached = _serve_from_cache_if_fresh(cache_state, reason_prefix=reason, now=now)
    if cached is not None:
        # Even when transport failed, cache hit is reported as STALE because
        # the data we are returning IS stale; the transport failure is the cause.
        return cached
    return _build_response(
        status="DEGRADED",
        reason=reason + " — no cached data available.",
        source="scraping_proxy",
        data=[],
        now=now,
    )


# ─── Poskobanjir fallback ─────────────────────────────────────────────────────


def build_tma_from_poskobanjir(
    stations: list[dict],
    *,
    now: datetime | None = None,
) -> dict:
    """
    Synthesise a TMA-compatible response from poskobanjir station tinggi_air
    readings. Used when TMA_PROXY_URL is not configured so the pipeline can
    continue without firing external_source_unreliable every run.

    Returns status="OK" with source="poskobanjir_fallback" when at least one
    station carries a valid tinggi_air value; status="STALE" when none do.
    The caller (RoutingAgent) is responsible for deciding when to use this
    instead of fetch_tma_data.
    """
    ref_now = now if now is not None else _utcnow()
    records: list[dict] = []
    for station in (stations or []):
        raw = station.get("tinggi_air")
        try:
            height = float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            height = None
        if height is None:
            continue
        if math.isnan(height) or math.isinf(height) or height < 0 or height > _height_max_cm():
            continue
        records.append(
            {
                "time": str(station.get("waktu") or station.get("time") or "N/A"),
                "height_cm": height,
                "station_id": str(station.get("id") or station.get("id_pintu_air") or "?"),
            }
        )

    if not records:
        return _build_response(
            status="STALE",
            reason=(
                "poskobanjir_fallback: no valid tinggi_air readings "
                "found in station data — TMA signals unavailable."
            ),
            source="poskobanjir_fallback",
            data=[],
            now=ref_now,
        )

    return _build_response(
        status="OK",
        reason=f"poskobanjir_fallback: synthesised from {len(records)} station reading(s).",
        source="poskobanjir_fallback",
        data=records,
        now=ref_now,
        fetched_at=ref_now,
    )


# ─── Public API ──────────────────────────────────────────────────────────────


def fetch_tma_data(
    *,
    now: datetime | None = None,
    cache_state: dict | None = None,
    deadline: datetime | None = None,
) -> dict:
    """
    Fetch current water-level readings from the BPBD Jakarta scraping proxy.

    Always returns a valid dict — never raises. Status semantics:

      OK        — fresh, schema-valid data.
      STALE     — upstream returned empty/missing fields; either cached fallback
                  (``source="cache"``, ``stale_age_minutes`` present) or empty
                  (``data=[]``, ``source="scraping_proxy"``).
      DEGRADED  — every transport attempt failed; may include cached fallback.
      INVALID   — fields present but structurally corrupt (length mismatch,
                  every height NaN/Inf/out-of-range). Caller MUST NOT use data.

    Return schema:
    {
        "status":             "OK" | "STALE" | "DEGRADED" | "INVALID",
        "reason":             str | None,                 # None on clean OK
        "source":             "scraping_proxy" | "cache",
        "reliability":        "low",                      # always low for this source
        "fetched_at":         "<ISO-8601 UTC>",           # original live-fetch time
        "served_at":          "<ISO-8601 UTC>",           # this response time
        "stale_age_minutes":  float (only when STALE from cache),
        "data": [
            {"time": "HH:MM", "height_cm": 120.0},
            ...
        ]
    }

    ``cache_state`` is the caller-owned dict that holds last-valid data. We
    store the raw response under ``last_valid`` and the live-fetch timestamp
    under ``last_valid_at`` so age can be reported precisely.
    """
    ref_now = now if now is not None else _utcnow()
    proxy_url = _proxy_url()
    if not proxy_url:
        return _stale_response(
            "no TMA proxy configured — set TMA_PROXY_URL to a verified water-level endpoint",
            cache_state=cache_state,
            now=ref_now,
        )
    max_retries = _max_retries()
    timeout = _timeout_seconds()
    retry_delay = _retry_delay_seconds()
    last_error: str = "unknown error"

    for attempt in range(1, max_retries + 1):
        attempt_now = _utcnow()
        remaining_budget = _seconds_until_deadline(deadline, now=attempt_now)
        if remaining_budget is not None and remaining_budget <= 0:
            return _deadline_exceeded_response(
                deadline=deadline,
                attempt=attempt,
                max_retries=max_retries,
                last_error=last_error,
                cache_state=cache_state,
                now=attempt_now,
            )
        request_timeout = (
            timeout
            if remaining_budget is None
            else max(0.001, min(timeout, remaining_budget))
        )
        try:
            resp = requests.get(
                proxy_url,
                timeout=request_timeout,
                headers={"User-Agent": "JakartaFloodSystem/1.0"},
            )
        except requests.exceptions.Timeout:
            last_error = f"timeout after {request_timeout:.1f}s"
        except requests.exceptions.ConnectionError as exc:
            last_error = f"connection error: {exc}"
        except requests.exceptions.RequestException as exc:
            last_error = f"request exception: {exc}"
        else:
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                if attempt < max_retries:
                    sleep_now = _utcnow()
                    sleep_budget = _seconds_until_deadline(deadline, now=sleep_now)
                    if deadline is not None and sleep_budget is not None and sleep_budget <= retry_delay:
                        return _deadline_exceeded_response(
                            deadline=deadline,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            last_error=last_error,
                            cache_state=cache_state,
                            now=sleep_now,
                        )
                    _time.sleep(retry_delay)
                    continue
            else:
                try:
                    raw = resp.json()
                except ValueError:
                    last_error = "response body is not valid JSON"
                    if attempt < max_retries:
                        sleep_now = _utcnow()
                        sleep_budget = _seconds_until_deadline(deadline, now=sleep_now)
                        if deadline is not None and sleep_budget is not None and sleep_budget <= retry_delay:
                            return _deadline_exceeded_response(
                                deadline=deadline,
                                attempt=attempt + 1,
                                max_retries=max_retries,
                                last_error=last_error,
                                cache_state=cache_state,
                                now=sleep_now,
                            )
                        _time.sleep(retry_delay)
                        continue
                else:
                    if not isinstance(raw, dict):
                        return _build_response(
                            status="INVALID",
                            reason=f"Expected JSON object, got {type(raw).__name__}.",
                            source="scraping_proxy",
                            data=[],
                            now=ref_now,
                        )

                    records, note, classification = _parse_records(raw)

                    if classification == "ok":
                        ok_response = _build_response(
                            status="OK",
                            reason=note,
                            source="scraping_proxy",
                            data=records,
                            now=ref_now,
                            fetched_at=ref_now,
                        )
                        if cache_state is not None:
                            cache_state["last_valid"] = ok_response
                            cache_state["last_valid_at"] = ref_now
                        return ok_response

                    if classification == "empty":
                        logger.warning(
                            "tma_scraper: upstream returned empty fields (%s) — degrading to STALE. "
                            "Inspect proxy URL (%s) and upstream HTML structure.",
                            note,
                            proxy_url,
                        )
                        return _stale_response(
                            note or "upstream returned empty fields",
                            cache_state=cache_state,
                            now=ref_now,
                        )

                    # classification == "invalid"
                    logger.error(
                        "tma_scraper: structurally corrupt response (%s) — returning INVALID.",
                        note,
                    )
                    return _build_response(
                        status="INVALID",
                        reason=note or "structurally corrupt records.",
                        source="scraping_proxy",
                        data=[],
                        now=ref_now,
                    )

        if attempt < max_retries:
            sleep_now = _utcnow()
            sleep_budget = _seconds_until_deadline(deadline, now=sleep_now)
            if deadline is not None and sleep_budget is not None and sleep_budget <= retry_delay:
                return _deadline_exceeded_response(
                    deadline=deadline,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    last_error=last_error,
                    cache_state=cache_state,
                    now=sleep_now,
                )
            _time.sleep(retry_delay)

    logger.warning(
        "tma_scraper: all %d attempts failed. Last error: %s",
        max_retries,
        last_error,
    )
    return _degraded_response(
        f"All {max_retries} fetch attempts failed. Last error: {last_error}",
        cache_state=cache_state,
        now=ref_now,
    )
