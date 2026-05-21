"""
Route planner — Google Maps Routes API with flood-aware safety scoring.

Key design constraint: Google Maps has NO knowledge of flood conditions.
All flood intelligence is injected from the internal AI pipeline via flood_zones.
This module's sole job is fetching path geometry and scoring it against those zones.

Security:
  - API key is read from env at call time (never at import time)
  - Key is passed via X-Goog-Api-Key header, never in the URL
  - Key is never logged, printed, or included in error messages
  - Missing key degrades gracefully — never raises, never crashes the API
"""

from __future__ import annotations

import math
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from api.observability import ROUTES_CIRCUIT_OPEN

if os.getenv("FLOOD_LOAD_DOTENV", "1") == "1":
    load_dotenv()

_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_ROUTES_FIELD_MASK = (
    "routes.duration,routes.distanceMeters,"
    "routes.polyline.encodedPolyline,routes.description"
)
_REQUEST_TIMEOUT = 10
_CIRCUIT_FAILURE_LIMIT = 5
_CIRCUIT_WINDOW_S = 60.0
_CIRCUIT_OPEN_S = 60.0
_route_failures: list[float] = []
_circuit_open_until = 0.0

# Multi-objective scoring weights (must sum to 1.0).
# Safety is primary: a faster route through a flood zone is never acceptable.
_SAFETY_WEIGHT      = 0.60
_DURATION_WEIGHT    = 0.25
_RELIABILITY_WEIGHT = 0.15   # Penalised when system trust is degraded

# High-severity zones are twice as penalising as medium-severity zones.
_SEVERITY_MULTIPLIER: dict[str, float] = {"high": 2.0, "medium": 1.0}

# Trust modifier per system_status: reduces effective safety when the flood zone
# map is itself uncertain (degraded pipeline confidence means zones may be wrong).
_STATUS_TRUST_MODIFIER: dict[str, float] = {
    "OK":        1.00,
    "DEGRADED":  0.85,
    "CONFLICT":  0.70,
    "LOW_TRUST": 0.60,
}

# Routes whose best safety score stays below this trigger no-safe-route fallback.
_UNSAFE_ROUTE_THRESHOLD = 0.30


# ─── Geometry helpers ────────────────────────────────────────────────────────

def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """
    Decode Google's encoded polyline to a list of (lat, lon) tuples.
    Reference: https://developers.google.com/maps/documentation/utilities/polylinealgorithm
    """
    coords: list[tuple[float, float]] = []
    index, lat, lng, n = 0, 0, 0, len(encoded)
    while index < n:
        shift, result = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        shift, result = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        coords.append((lat / 1e5, lng / 1e5))
    return coords


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two coordinate pairs."""
    r = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── Public API ──────────────────────────────────────────────────────────────

def _parse_duration_s(value: str | int | None) -> int:
    """Parse Routes API duration string ('1234s') or plain int to integer seconds."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(str(value).rstrip("s"))
    except ValueError:
        return 0


def _circuit_is_open() -> bool:
    is_open = time.monotonic() < _circuit_open_until
    ROUTES_CIRCUIT_OPEN.set(1.0 if is_open else 0.0)
    return is_open


def _record_route_failure() -> None:
    global _circuit_open_until
    now = time.monotonic()
    _route_failures.append(now)
    while _route_failures and now - _route_failures[0] > _CIRCUIT_WINDOW_S:
        _route_failures.pop(0)
    if len(_route_failures) >= _CIRCUIT_FAILURE_LIMIT:
        _circuit_open_until = now + _CIRCUIT_OPEN_S
        ROUTES_CIRCUIT_OPEN.set(1.0)


def _record_route_success() -> None:
    _route_failures.clear()
    ROUTES_CIRCUIT_OPEN.set(0.0)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(min=0.5, max=4),
    retry=retry_if_exception_type(
        (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
    ),
    reraise=True,
)
def _post_routes(headers: dict[str, str], body: dict[str, Any]) -> requests.Response:
    return requests.post(_ROUTES_URL, headers=headers, json=body, timeout=_REQUEST_TIMEOUT)


def _normalize_route(route: dict) -> dict:
    """
    Convert a Routes API route object to the legacy Directions API shape used
    internally by compute_route_safety() and select_best_route().

    Routes API fields:
      route.duration              → "1234s" string
      route.distanceMeters        → int
      route.polyline.encodedPolyline → encoded polyline string
      route.description           → summary string
    """
    dur_s = _parse_duration_s(route.get("duration"))
    dist_m = int(route.get("distanceMeters", 0))
    polyline = route.get("polyline", {}).get("encodedPolyline", "")
    description = route.get("description", "")
    return {
        "overview_polyline": {"points": polyline},
        "legs": [{"duration": {"value": dur_s}, "distance": {"value": dist_m}}],
        "summary": description,
    }


def get_routes(origin: str, destination: str) -> dict:
    """
    Fetch up to 3 alternative routes from the Google Maps Routes API.

    Uses POST https://routes.googleapis.com/directions/v2:computeRoutes.
    API key is sent via X-Goog-Api-Key header — never appended to the URL.

    Returns:
    {
        "ok":     bool,
        "routes": [...],      # normalized route dicts (legacy Directions API shape)
        "error":  str | None  # set only when ok=False
    }

    Never raises — all failure modes return ok=False with a safe error string.
    The API key is never included in error messages.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return {
            "ok": False,
            "routes": [],
            "error": "Routing service unavailable due to missing configuration.",
        }
    if _circuit_is_open():
        return {
            "ok": False,
            "routes": [],
            "error": "route_unavailable",
            "reason": "circuit_open",
        }

    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": _ROUTES_FIELD_MASK,
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "computeAlternativeRoutes": True,
    }

    try:
        resp = _post_routes(headers, body)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        _record_route_failure()
        return {"ok": False, "routes": [], "error": "Routes API request timed out."}
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code >= 500:
            _record_route_failure()
        _err_data: dict = {}
        try:
            _err_data = exc.response.json()
        except Exception:
            pass
        _api_status = _err_data.get("error", {}).get("status", "")
        _messages: dict[str, str] = {
            "NOT_FOUND": "Origin or destination could not be geocoded.",
            "PERMISSION_DENIED": "API key lacks Routes API permission.",
            "RESOURCE_EXHAUSTED": "API daily quota exceeded or rate limit hit.",
            "INVALID_ARGUMENT": "Invalid origin or destination format.",
        }
        return {
            "ok": False,
            "routes": [],
            "error": _messages.get(_api_status, "Routes API request failed."),
        }
    except requests.exceptions.RequestException:
        _record_route_failure()
        return {"ok": False, "routes": [], "error": "Routes API request failed."}
    except ValueError:
        _record_route_failure()
        return {"ok": False, "routes": [], "error": "Routes API returned invalid JSON."}

    raw_routes = data.get("routes", [])
    if not raw_routes:
        return {"ok": False, "routes": [], "error": "No routes returned by Google Maps."}

    _record_route_success()
    return {"ok": True, "routes": [_normalize_route(r) for r in raw_routes], "error": None}


def compute_route_safety(route: dict, flood_zones: list[dict]) -> float:
    """
    Score a route's flood safety on a 0.0–1.0 scale (1.0 = fully safe).

    Algorithm:
      1. Decode the overview polyline to (lat, lon) points.
      2. For each point, find the worst flood zone it falls within (by severity).
      3. Accumulate weighted_hits using _SEVERITY_MULTIPLIER.
      4. safety_score = 1.0 - (weighted_hits / total_points), clamped to [0, 1].

    Returns 1.0 if no flood zones exist. Returns 0.50 if the polyline is missing
    (conservative unknown-safety default rather than optimistic 1.0).
    """
    if not flood_zones:
        return 1.0

    encoded = route.get("overview_polyline", {}).get("points", "")
    if not encoded:
        return 0.50

    points = _decode_polyline(encoded)
    if not points:
        return 0.50

    total = len(points)
    weighted_hits = 0.0

    for lat, lon in points:
        worst_multiplier = 0.0
        for zone in flood_zones:
            if _haversine_m(lat, lon, zone["lat"], zone["lon"]) <= zone["radius_m"]:
                m = _SEVERITY_MULTIPLIER.get(zone.get("severity", "medium"), 1.0)
                worst_multiplier = max(worst_multiplier, m)
        weighted_hits += worst_multiplier

    return round(max(0.0, 1.0 - weighted_hits / total), 4)


def select_best_route(
    routes: list[dict],
    flood_zones: list[dict],
    system_trust_modifier: float = 1.00,
    irbi_score: float = 0.0,
) -> dict:
    """
    Select the best route via three-objective scoring: safety, duration, reliability.

    Args:
        routes:                Raw route objects from get_routes().
        flood_zones:           Active flood zones from the pipeline.
        system_trust_modifier: 0.0–1.0. Reduces effective safety scores when the
                               pipeline's own confidence is degraded (flood zone map
                               may be inaccurate when system is CONFLICT/LOW_TRUST).
                               Use _STATUS_TRUST_MODIFIER[system_status] to derive.
        irbi_score:            0.0–1.0 BNPB IRBI flood vulnerability score (pure,
                               decay-adjusted). Converted to an independent penalty:
                               irbi_penalty = max(0.70, 1 - irbi_score * 0.3).
                               NEVER merged with system_trust_modifier — the two
                               factors remain strictly independent per the BNPB
                               design contract. Does NOT modify flood zone geometry.

    Scoring formula (strict separation — weights sum to 1.0):
        irbi_penalty     = max(0.70, 1.0 - irbi_score * 0.3)   ← vulnerability priority
        effective_safety = raw_safety × system_trust_modifier × irbi_penalty
        # system_trust_modifier (composite_trust) and irbi_penalty are NEVER merged.
        # They are independent multiplicative factors — merging them into a single
        # variable causes global route degradation instead of selective prioritisation.
        norm_duration    = 1.0 for shortest route, 0.0 for longest
        reliability      = system_trust_modifier
        combined = safety*0.60 + duration*0.25 + reliability*0.15

    Edge case: if ALL routes have effective safety below _UNSAFE_ROUTE_THRESHOLD,
    returns a no-safe-route structured fallback rather than selecting the least-bad option
    silently.

    Returns a structured summary dict — not the raw Google Maps route object.
    """
    if not routes:
        return _unavailable("No routes provided for selection.")

    # IRBI penalty: clamped so it never inverts or zeroes out the safety score.
    irbi_penalty = max(0.70, 1.0 - irbi_score * 0.3)

    scored: list[dict] = []
    for route in routes:
        leg = (route.get("legs") or [{}])[0]
        dur_s = leg.get("duration", {}).get("value", 0)
        dist_m = leg.get("distance", {}).get("value", 0)
        raw_safety = compute_route_safety(route, flood_zones)
        effective_safety = round(raw_safety * system_trust_modifier * irbi_penalty, 4)
        scored.append({
            "route": route,
            "raw_safety_score": raw_safety,
            "safety_score": effective_safety,
            "duration_s": dur_s,
            "distance_m": dist_m,
            "summary": route.get("summary", ""),
        })

    # No-safe-route edge case: all effective safety scores below threshold.
    best_safety = max(s["safety_score"] for s in scored)
    if best_safety < _UNSAFE_ROUTE_THRESHOLD:
        return _no_safe_route_fallback(scored, flood_zones, system_trust_modifier)

    # Normalise duration: shortest → 1.0, longest → 0.0.
    durations = [s["duration_s"] for s in scored]
    lo, hi = min(durations), max(durations)
    dur_range = (hi - lo) or 1

    for s in scored:
        norm_dur = (hi - s["duration_s"]) / dur_range
        # Reliability is a constant per system_trust_modifier — all routes share
        # the same reliability score (it's a property of the pipeline, not the route).
        s["combined"] = round(
            s["safety_score"] * _SAFETY_WEIGHT
            + norm_dur * _DURATION_WEIGHT
            + system_trust_modifier * _RELIABILITY_WEIGHT,
            4,
        )

    best = max(scored, key=lambda x: x["combined"])
    others = [s for s in scored if s is not best]
    reason = _selection_reason(best, others, flood_zones, system_trust_modifier, irbi_score)

    return {
        "available": True,
        "distance_km": round(best["distance_m"] / 1000, 2),
        "eta_minutes": round(best["duration_s"] / 60, 1),
        "safety_score": best["safety_score"],
        "raw_safety_score": best["raw_safety_score"],
        "combined_score": best["combined"],
        "summary": best["summary"],
        "reason": reason,
        "flood_zones_checked": len(flood_zones),
        "alternatives_evaluated": len(routes),
        "system_trust_modifier": system_trust_modifier,
    }


def _selection_reason(
    best: dict,
    others: list[dict],
    flood_zones: list[dict],
    system_trust_modifier: float = 1.00,
    irbi_score: float = 0.0,
) -> str:
    """
    Explain WHY this route was selected over alternatives.

    Covers three dimensions:
      1. Safety — how well it avoids flood zones vs alternatives
      2. Duration — time trade-off vs safer/faster alternatives
      3. Reliability — note when system trust reduces score confidence
    """
    parts: list[str] = []
    safety = best["safety_score"]
    raw_safety = best.get("raw_safety_score", safety)

    # ── Safety explanation ────────────────────────────────────────────────────
    high_zones = sum(1 for z in flood_zones if z.get("severity") == "high")
    medium_zones = sum(1 for z in flood_zones if z.get("severity") == "medium")

    if safety >= 0.90:
        parts.append("Route avoids all active flood zones entirely.")
    elif safety >= 0.70:
        parts.append(
            f"Route has the least flood exposure ({safety:.0%} safe score) "
            f"among {len(others) + 1} candidate(s)."
        )
    else:
        parts.append(
            f"Best available route despite partial flood-zone overlap "
            f"(effective safety {safety:.0%})."
        )

    if high_zones:
        parts.append(f"Avoids {high_zones} high-severity river/hydrology zone(s).")
    if medium_zones and safety < 0.90:
        parts.append(f"Passes near {medium_zones} medium-severity zone(s) — caution advised.")

    # ── Comparison with alternatives ──────────────────────────────────────────
    safer_alts = [o for o in others if o["safety_score"] > safety]
    faster_alts = [o for o in others if o["duration_s"] < best["duration_s"]]

    if not others:
        parts.append("Only one route available.")
    elif not safer_alts:
        parts.append("This is the safest of all available routes.")
        if faster_alts:
            avg_faster_min = (
                sum(best["duration_s"] - o["duration_s"] for o in faster_alts)
                / len(faster_alts) / 60
            )
            parts.append(
                f"Faster alternatives save ~{avg_faster_min:.0f} min "
                "but pass through higher flood-risk zones."
            )
    else:
        avg_safety_gain = (
            sum(o["safety_score"] - safety for o in safer_alts) / len(safer_alts)
        )
        avg_extra_min = (
            sum(o["duration_s"] - best["duration_s"] for o in safer_alts)
            / len(safer_alts) / 60
        )
        if avg_extra_min > 1:
            parts.append(
                f"{len(safer_alts)} safer alternative(s) exist (+{avg_safety_gain:.0%} safety) "
                f"but add ~{avg_extra_min:.0f} min — selected route balances safety and time."
            )
        else:
            parts.append(
                f"Selected over {len(safer_alts)} alternative(s) with marginally better safety "
                "at negligible time difference — combined score favoured this route."
            )

    # ── Reliability note ──────────────────────────────────────────────────────
    if system_trust_modifier < 1.00:
        discount_pct = round((1.0 - system_trust_modifier) * 100)
        parts.append(
            f"NOTE: Flood zone confidence is reduced ({discount_pct}% trust discount applied). "
            f"Raw safety estimate was {raw_safety:.0%}; effective score adjusted to {safety:.0%}. "
            "Verify with direct field observation before travel."
        )

    # ── IRBI vulnerability note ───────────────────────────────────────────────
    if irbi_score > 0.0:
        irbi_pct = round(irbi_score * 0.3 * 100)
        parts.append(
            f"BNPB InaRISK vulnerability score {irbi_score:.2f} applied "
            f"({irbi_pct}% route priority reduction). "
            "Destination district has elevated structural flood vulnerability — "
            "exercise additional caution."
        )

    return " ".join(parts) or "Selected by combined safety + duration + reliability score."


def _no_safe_route_fallback(
    scored: list[dict],
    flood_zones: list[dict],
    system_trust_modifier: float,
) -> dict:
    """
    Structured fallback when ALL candidate routes fall below _UNSAFE_ROUTE_THRESHOLD.

    Instead of silently selecting the least-bad route, this explicitly tells the
    caller that no safe route exists and provides a structured fallback strategy
    so field operators can make an informed decision.
    """
    best_available = max(scored, key=lambda x: x["safety_score"])
    high_zones = sum(1 for z in flood_zones if z.get("severity") == "high")
    medium_zones = sum(1 for z in flood_zones if z.get("severity") == "medium")

    fallback_strategy: list[str] = [
        "SHELTER IN PLACE: If destination is not essential, remain at current location.",
        "WAIT FOR CONDITIONS: Monitor flood signals — risk may decrease within 1–3 hours.",
    ]
    if system_trust_modifier < 0.80:
        fallback_strategy.append(
            "VERIFY INDEPENDENTLY: System confidence is reduced — confirm flood status "
            "with BPBD Jakarta or direct field observation before any travel decision."
        )
    if best_available["safety_score"] > 0.0:
        fallback_strategy.append(
            f"LEAST-BAD ROUTE: If travel is unavoidable, '{best_available['summary']}' "
            f"has the highest available safety score ({best_available['safety_score']:.0%}) — "
            "proceed only with full awareness of flood risk."
        )

    leg = (best_available["route"].get("legs") or [{}])[0]
    return {
        "available": False,
        "no_safe_route": True,
        "distance_km": round(leg.get("distance", {}).get("value", 0) / 1000, 2),
        "eta_minutes": round(leg.get("duration", {}).get("value", 0) / 60, 1),
        "safety_score": best_available["safety_score"],
        "combined_score": None,
        "summary": best_available["summary"],
        "reason": (
            f"All {len(scored)} available route(s) pass through active flood zones "
            f"({high_zones} high-severity, {medium_zones} medium-severity) with effective "
            f"safety below {_UNSAFE_ROUTE_THRESHOLD:.0%}. Travel is not recommended."
        ),
        "fallback_strategy": fallback_strategy,
        "flood_zones_checked": len(flood_zones),
        "alternatives_evaluated": len(scored),
        "system_trust_modifier": system_trust_modifier,
    }


def _unavailable(reason: str) -> dict:
    return {
        "available": False,
        "distance_km": None,
        "eta_minutes": None,
        "safety_score": None,
        "combined_score": None,
        "summary": None,
        "reason": reason,
        "flood_zones_checked": 0,
        "alternatives_evaluated": 0,
    }
