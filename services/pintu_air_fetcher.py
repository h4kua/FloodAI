"""
Live water-gate (Pintu Air / TMA) fetcher.

Replaces the brittle Selenium dashboard scrape with a direct query against the
ArcGIS FeatureServer that backs the Jakarta Satu "Data Pintu Air" panel. Returns
current water-level readings (cm) and SIAGA status per gate as clean JSON — no
browser, no ChromeDriver.

Source (public, no auth):
    https://jakartasatu.jakarta.go.id/server/rest/services/
    BPBD/Data_Pintu_Air/FeatureServer/0/query?where=1=1&outFields=*&f=json

Live fields: PINTU_AIR, SUNGAI, KETINGGIAN_AIR_CM, STATUS_N, STATUS_NUM,
TANGGAL ("DD/MM/YYYY"), WAKTU ("HH:MM", WIB).

Design mirrors awlr_threshold_fetcher: pure parsing, network fetch + cache,
and a never-raising ``get_pintu_air`` entry point with cache fallback.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

from api.observability import get_logger

_log = get_logger("flood.pintu_air_fetcher")

PINTU_AIR_URL = (
    "https://jakartasatu.jakarta.go.id/server/rest/services/"
    "BPBD/Data_Pintu_Air/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=json"
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = _PROJECT_ROOT / "data" / "raw" / "pintu_air_latest.json"

_DEFAULT_TIMEOUT_S = 20.0
_WIB = timezone(timedelta(hours=7))

# Status string -> normalised severity (mirrors realtime_adapter STATUS_NORMALIZATION).
_STATUS_SCORE = {
    "siaga 1": 1.0,
    "siaga 2": 0.8,
    "siaga 3": 0.5,
    "siaga 4": 0.25,
    "normal": 0.0,
}


def _parse_observed_at(tanggal: object, waktu: object) -> Optional[str]:
    """Combine TANGGAL ('DD/MM/YYYY') + WAKTU ('HH:MM') as WIB -> UTC ISO-8601."""
    date_text = str(tanggal or "").strip()
    time_text = str(waktu or "").strip() or "00:00"
    if not date_text:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H.%M"):
        try:
            naive = datetime.strptime(f"{date_text} {time_text}", fmt)
            return naive.replace(tzinfo=_WIB).astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def _safe_float(value: object) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def status_score(status_text: object) -> float:
    """Map a SIAGA status string to a [0, 1] severity score."""
    status = str(status_text or "").strip().lower()
    for label, score in _STATUS_SCORE.items():
        if label in status:
            return score
    return 0.0


def _normalise_gate(attributes: dict) -> Optional[dict]:
    name = (attributes.get("PINTU_AIR") or "").strip()
    if not name:
        return None
    level_cm = _safe_float(attributes.get("KETINGGIAN_AIR_CM"))
    if level_cm is None:
        level_cm = _safe_float(attributes.get("KETINGGIAN_AIR"))
    status = (attributes.get("STATUS_N") or attributes.get("STATUS") or "").strip()
    return {
        "name": name,
        "sungai": (attributes.get("SUNGAI") or "").strip(),
        "water_level_cm": level_cm,
        "status": status,
        "status_num": attributes.get("STATUS_NUM"),
        "observed_at_utc": _parse_observed_at(attributes.get("TANGGAL"), attributes.get("WAKTU")),
    }


def _build_payload(features: list[dict]) -> dict:
    gates = [g for g in (_normalise_gate(f.get("attributes", {})) for f in features) if g]
    levels = [g["water_level_cm"] for g in gates if g["water_level_cm"] is not None]
    observed = [g["observed_at_utc"] for g in gates if g["observed_at_utc"]]
    # The most severe gate by status score, then by level, drives the headline.
    worst = max(
        gates,
        key=lambda g: (status_score(g["status"]), g["water_level_cm"] or 0.0),
        default=None,
    )
    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "jakartasatu_bpbd_data_pintu_air",
        "gate_count": len(gates),
        "latest_observation_utc": max(observed) if observed else None,
        "max_water_level_cm": max(levels) if levels else None,
        "max_status": worst["status"] if worst else None,
        "max_status_gate": worst["name"] if worst else None,
        "gates": gates,
    }


def _save_cache(payload: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        _log.warning("pintu_air_cache_write_failed", error=str(exc), path=str(CACHE_PATH))


def load_cached_pintu_air() -> Optional[dict]:
    """Return the last persisted pintu-air payload, or ``None``."""
    try:
        if not CACHE_PATH.exists():
            return None
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log.warning("pintu_air_cache_read_failed", error=str(exc), path=str(CACHE_PATH))
        return None


def fetch_pintu_air(*, timeout: float = _DEFAULT_TIMEOUT_S, save: bool = True) -> dict:
    """
    Fetch and parse live water-gate readings from the FeatureServer.

    Raises ``requests.RequestException`` / ``ValueError`` on failure; use
    :func:`get_pintu_air` for the never-raising path.
    """
    resp = requests.get(
        PINTU_AIR_URL, timeout=timeout, headers={"User-Agent": "JakartaFloodSystem/1.0"}
    )
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Data Pintu Air response contained no features")
    payload = _build_payload(features)
    if payload["gate_count"] == 0:
        raise ValueError("Data Pintu Air response parsed to zero usable gates")
    if save:
        _save_cache(payload)
    _log.info(
        "pintu_air_fetch_ok",
        gate_count=payload["gate_count"],
        max_status=payload["max_status"],
    )
    return payload


def get_pintu_air(*, force_refresh: bool = False) -> Optional[dict]:
    """Fresh fetch with cache fallback. Returns ``None`` if neither is available."""
    try:
        return fetch_pintu_air()
    except (requests.RequestException, ValueError) as exc:
        _log.warning("pintu_air_fetch_failed_using_cache", error=str(exc))
        cached = load_cached_pintu_air()
        if cached is not None:
            return cached
        _log.error("pintu_air_unavailable", detail="fetch failed and no cache present")
        return None


def observation_age_minutes(payload: dict, *, now: Optional[datetime] = None) -> Optional[float]:
    """Minutes since the most recent gate observation, or ``None`` if unknown."""
    latest = payload.get("latest_observation_utc")
    if not latest:
        return None
    try:
        observed = datetime.fromisoformat(latest)
    except ValueError:
        return None
    ref = now or datetime.now(timezone.utc)
    return max(0.0, (ref - observed).total_seconds() / 60.0)


if __name__ == "__main__":
    payload = get_pintu_air(force_refresh=True)
    if payload:
        print(
            f"Fetched {payload['gate_count']} gates -> {CACHE_PATH}\n"
            f"  max_status={payload['max_status']} "
            f"max_level_cm={payload['max_water_level_cm']} "
            f"latest_obs={payload['latest_observation_utc']}"
        )
    else:
        print("Pintu Air data unavailable (no network, no cache).")
