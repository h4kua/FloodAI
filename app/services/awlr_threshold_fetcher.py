"""
AWLR (Automatic Water Level Recorder) threshold fetcher.

Fetches the public Jakarta Satu AWLR FeatureServer layer, which publishes the
official SIAGA (alert) thresholds for ~28 water gates across the Jakarta basin,
and normalises the human-readable threshold strings (e.g. ``"> 350 cm"``,
``"250 - 350 cm"``) into machine-usable numbers.

Source (public, no auth):
    https://jakartasatu.jakarta.go.id/server/rest/services/
    Automatic_Water_Level_Recorder_AWLR/FeatureServer/0/query?where=1=1&outFields=*&f=json

SIAGA convention (Indonesian flood alerting):
    SIAGA 1 = most critical (highest water level, e.g. "> 350 cm")
    SIAGA 4 = lowest        (e.g. "< 150 cm")
Therefore the SIAGA_1 lower bound is the per-gate "critical" level used to
compute ``water_level_ratio = water_level_cm / siaga1_cm``.

Design:
    parse_threshold()        — pure function; testable without network.
    fetch_awlr_thresholds()  — network fetch + parse + cache write.
    load_cached_thresholds() — read the last good cache file.
    get_awlr_thresholds()    — main entry: fresh fetch, fall back to cache.

Never raises on a missing network: callers always receive a dict (possibly
sourced from cache) or ``None`` when neither network nor cache is available.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

import requests

from app.api.observability import get_logger

_log = get_logger("flood.awlr_threshold_fetcher")

AWLR_URL = (
    "https://jakartasatu.jakarta.go.id/server/rest/services/"
    "Automatic_Water_Level_Recorder_AWLR/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=json"
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = _PROJECT_ROOT / "data" / "raw" / "awlr_thresholds.json"

_DEFAULT_TIMEOUT_S = 20.0

# Matches an integer/float possibly followed by "cm"; tolerant of extra spaces.
_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)")

ThresholdValue = Union[float, dict, None]


def parse_threshold(raw: object) -> ThresholdValue:
    """
    Normalise a SIAGA threshold string into a number or range.

      "> 350 cm"      -> 350.0          (single lower bound)
      "< 150 cm"      -> 150.0          (single upper bound)
      "250 - 350 cm"  -> {"min": 250.0, "max": 350.0}
      ""/None/garbage -> None

    Single-bound strings collapse to a float (per spec); ranges become a dict.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    numbers = [float(n.replace(",", ".")) for n in _NUMBER_RE.findall(text)]
    if not numbers:
        return None

    # A range is any string carrying two numbers separated by a dash that is
    # not part of a comparison operator (e.g. "200 - 250 cm").
    if len(numbers) >= 2 and "-" in text:
        low, high = sorted(numbers[:2])
        return {"min": low, "max": high}

    return numbers[0]


def _critical_cm(siaga_1: ThresholdValue) -> Optional[float]:
    """Extract the single critical level (cm) from a parsed SIAGA_1 value."""
    if isinstance(siaga_1, (int, float)):
        return float(siaga_1)
    if isinstance(siaga_1, dict):
        # A range here is unusual for SIAGA_1; treat the lower bound as critical.
        return siaga_1.get("min")
    return None


def _normalise_feature(attributes: dict) -> Optional[dict]:
    """Convert one AWLR FeatureServer record into a normalised gate dict."""
    name = (attributes.get("LOK_AWAL") or "").strip()
    if not name:
        return None

    siaga_1 = parse_threshold(attributes.get("SIAGA_1"))
    gate = {
        "name": name,
        "kali": (attributes.get("ALIRAN_KALI") or "").strip(),
        "wadmkk": (attributes.get("WADMKK") or "").strip(),
        "alamat": (attributes.get("ALAMAT") or "").strip(),
        "lat": attributes.get("LAT"),
        "lon": attributes.get("LONG_"),
        "siaga_1": siaga_1,
        "siaga_2": parse_threshold(attributes.get("SIAGA_2")),
        "siaga_3": parse_threshold(attributes.get("SIAGA_3")),
        "siaga_4": parse_threshold(attributes.get("SIAGA_4")),
        "siaga1_cm": _critical_cm(siaga_1),
    }
    return gate


def _build_payload(features: list[dict]) -> dict:
    gates = [g for g in (_normalise_feature(f.get("attributes", {})) for f in features) if g]
    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "jakartasatu_awlr_featureserver",
        "gate_count": len(gates),
        "gates": gates,
    }


def _save_cache(payload: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        _log.warning("awlr_cache_write_failed", error=str(exc), path=str(CACHE_PATH))


def load_cached_thresholds() -> Optional[dict]:
    """Return the last persisted AWLR payload, or ``None`` if unavailable."""
    try:
        if not CACHE_PATH.exists():
            return None
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("awlr_cache_read_failed", error=str(exc), path=str(CACHE_PATH))
        return None


def fetch_awlr_thresholds(*, timeout: float = _DEFAULT_TIMEOUT_S, save: bool = True) -> dict:
    """
    Fetch and parse AWLR thresholds from the live FeatureServer.

    Raises ``requests.RequestException`` on transport failure or ``ValueError``
    on a malformed response. Callers wanting a never-raising path should use
    :func:`get_awlr_thresholds`.
    """
    resp = requests.get(
        AWLR_URL, timeout=timeout, headers={"User-Agent": "JakartaFloodSystem/1.0"}
    )
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("AWLR response contained no features")

    payload = _build_payload(features)
    if payload["gate_count"] == 0:
        raise ValueError("AWLR response parsed to zero usable gates")

    if save:
        _save_cache(payload)
    _log.info("awlr_fetch_ok", gate_count=payload["gate_count"])
    return payload


def get_awlr_thresholds(*, force_refresh: bool = False) -> Optional[dict]:
    """
    Main entry point. Try a fresh fetch; on any failure fall back to the cached
    file. Returns ``None`` only when neither network nor cache yields data.

    ``force_refresh`` is accepted for API symmetry; the function always attempts
    a fresh fetch first and only uses cache on failure.
    """
    try:
        return fetch_awlr_thresholds()
    except (requests.RequestException, ValueError) as exc:
        _log.warning("awlr_fetch_failed_using_cache", error=str(exc))
        cached = load_cached_thresholds()
        if cached is not None:
            return cached
        _log.error("awlr_unavailable", detail="fetch failed and no cache present")
        return None


def siaga1_cm_for(name: str, thresholds: Optional[dict] = None) -> Optional[float]:
    """
    Look up the SIAGA 1 critical level (cm) for a gate by case-insensitive
    substring match on gate name or river (``kali``). Returns ``None`` if no
    match or no threshold data.
    """
    payload = thresholds if thresholds is not None else load_cached_thresholds()
    if not payload:
        return None
    needle = name.strip().lower()
    if not needle:
        return None
    for gate in payload.get("gates", []):
        haystacks = (gate.get("name", ""), gate.get("kali", ""))
        if any(needle in h.lower() or h.lower() in needle for h in haystacks if h):
            value = gate.get("siaga1_cm")
            if isinstance(value, (int, float)):
                return float(value)
    return None


if __name__ == "__main__":
    payload = get_awlr_thresholds(force_refresh=True)
    if payload:
        print(f"Fetched {payload['gate_count']} AWLR gates -> {CACHE_PATH}")
    else:
        print("AWLR thresholds unavailable (no network, no cache).")
