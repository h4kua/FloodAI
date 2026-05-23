"""
RoutingAgent — Stage 5 of the agentic flood decision pipeline.

Activates when:
  - origin + destination are both provided (always routes, regardless of risk level)
  - risk_level >= WARNING and no coords provided (returns flood advisory, no map route)

Google Maps provides path geometry only. All flood intelligence comes from the
internal pipeline signals via build_flood_zones. Google Maps has no awareness
of flood conditions.

TMA data fetch is always attempted (non-blocking). Failures degrade confidence
by _TMA_DEGRADED_PENALTY but never block routing.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from services.data_ingestion.tma_scraper import build_tma_from_poskobanjir, fetch_tma_data
from services.flood_zones import build_flood_zones
from services.routing.route_planner import compute_route_safety, get_routes, select_best_route

if TYPE_CHECKING:
    from agents.evaluation_agent import EvaluationResult

_log = logging.getLogger(__name__)

_AUTO_ROUTING_LEVELS = {"WARNING", "DANGER"}
_TMA_DEGRADED_PENALTY = 0.05


def _tma_stale_grace_minutes() -> float:
    """
    Cached-but-still-fresh window. STALE responses inside this window do NOT
    incur a confidence penalty — the data is acknowledged old but operationally
    equivalent to fresh for the prediction horizon we publish.
    """
    try:
        return float(os.getenv("TMA_STALE_GRACE_MINUTES", "30"))
    except (TypeError, ValueError):
        return 30.0

# System trust modifier for multi-objective route scoring (Task 4).
# Reduces effective safety scores when the flood zone map is itself uncertain
# due to pipeline degradation — a CONFLICT or LOW_TRUST pipeline means the
# zone boundaries may be wrong, so reported safety must be discounted.
_SYSTEM_TRUST_MODIFIER: dict[str, float] = {
    "OK":        1.00,
    "DEGRADED":  0.85,
    "CONFLICT":  0.70,
    "LOW_TRUST": 0.60,
}


class RoutingAgent:
    """
    Stage 5: Routing.

    Integrates flood-zone geometry with Google Maps path selection to recommend
    the safest available route given current flood conditions.
    """

    def __init__(self) -> None:
        # Per-instance TMA last-valid cache (replaces former module-global in
        # tma_scraper). The orchestrator owns one RoutingAgent per
        # FloodDecisionPipeline instance, so this is request-scoped enough for
        # the demo target and eliminates the cross-request shared state.
        self._tma_cache_state: dict = {}

    def run(
        self,
        evaluation: "EvaluationResult",
        origin: str | None,
        destination: str | None,
        *,
        now: "datetime | None" = None,
        poskobanjir: "list[dict] | None" = None,
    ) -> dict:
        """
        Execute routing stage.

        Args:
            evaluation:   Output of EvaluationAgent (Stage 3).
            origin:       Free-text origin (passed directly to Google Maps).
            destination:  Free-text destination (passed directly to Google Maps).

        Returns a dict with keys:
            safe_route            — route summary or advisory/unavailable record
            tma_data              — raw TMA fetch result (status, reliability, data)
            tma_failure           — failure record if TMA degraded/invalid, else None
            confidence_adjustment — negative float; applied to pipeline confidence
        """
        reasoning = evaluation.reasoning
        signals = reasoning.signals
        features = reasoning.prediction.get("features", {})
        risk_level = evaluation.risk_level

        flood_zones = build_flood_zones(features, signals)

        # IRBI score is extracted for route scoring only — zone geometry is NOT
        # modified. Flood zone boundaries reflect real hydrology; IRBI affects
        # routing priority (effective safety score), not flood existence.
        #
        # STRICT SEPARATION: composite_trust (system reliability) and irbi_score
        # (vulnerability priority) are kept as independent factors — never merged.
        # Formula: route_score = base_score × composite_trust × irbi_penalty
        #
        # Hard gate: when bnpb_active=False, vuln is set to None so that NO
        # downstream BNPB path can partially execute on stale/invalid data.
        # Consume the authoritative gate decision from EvaluationAgent.
        # No independent re-evaluation — single-source-of-truth architecture.
        bnpb_status = getattr(evaluation, "bnpb_status", {})
        vuln = getattr(evaluation, "vulnerability_context", None)
        if not bnpb_status.get("active", False):
            vuln = None  # Hard gate — no partial BNPB execution allowed downstream
        bnpb_active = vuln is not None
        irbi_score = vuln.effective_irbi_score if vuln is not None else 0.0
        system_status = evaluation.system_status
        # composite_trust: system data reliability — falls back to categorical
        # approximation from _SYSTEM_TRUST_MODIFIER when TrustBreakdown is unavailable.
        composite_trust = (
            evaluation.trust_breakdown.composite_trust
            if evaluation.trust_breakdown is not None
            else _SYSTEM_TRUST_MODIFIER.get(system_status, 1.00)
        )

        tma_result = fetch_tma_data(now=now, cache_state=self._tma_cache_state)
        # When no proxy is configured and fetch returned STALE/empty, synthesise
        # a TMA-compatible response from the poskobanjir station readings.
        # These already carry per-station tinggi_air values with the same semantics.
        # The fallback returns source="poskobanjir_fallback" so _tma_failure_record
        # treats it as OK and does NOT emit external_source_unreliable.
        if (
            tma_result.get("status") == "STALE"
            and not os.getenv("TMA_PROXY_URL", "")
            and poskobanjir
        ):
            fallback = build_tma_from_poskobanjir(poskobanjir, now=now)
            if fallback.get("status") == "OK":
                tma_result = fallback
                _log.info(
                    "tma_poskobanjir_fallback stations=%d",
                    len(fallback.get("data") or []),
                )
        tma_failure = self._tma_failure_record(tma_result)
        confidence_adjustment = -_TMA_DEGRADED_PENALTY if tma_failure else 0.0
        has_coords = bool(origin and destination)

        if not has_coords and risk_level not in _AUTO_ROUTING_LEVELS:
            return {
                "safe_route": _route_skipped(
                    f"Risk level is {risk_level} — route planning not required."
                ),
                "tma_data": tma_result,
                "tma_failure": tma_failure,
                "confidence_adjustment": confidence_adjustment,
            }

        if not has_coords:
            return {
                "safe_route": _route_advisory(risk_level, flood_zones),
                "tma_data": tma_result,
                "tma_failure": tma_failure,
                "confidence_adjustment": confidence_adjustment,
            }

        routes_result = get_routes(origin, destination)  # type: ignore[arg-type]
        if not routes_result["ok"]:
            return {
                "safe_route": _route_unavailable(routes_result["error"]),
                "tma_data": tma_result,
                "tma_failure": tma_failure,
                "confidence_adjustment": confidence_adjustment,
            }

        candidate_routes = routes_result["routes"]
        danger_constraint_applied = False
        if risk_level == "DANGER":
            filtered, danger_constraint_applied = _filter_danger_routes(candidate_routes, flood_zones)
            candidate_routes = filtered

        # composite_trust = system reliability factor (data quality).
        # irbi_score      = structural vulnerability priority (independent of trust).
        # They are passed as separate arguments — never merged — so route_planner
        # applies: effective_safety = raw_safety × composite_trust × irbi_penalty.
        safe_route = select_best_route(
            candidate_routes,
            flood_zones,
            system_trust_modifier=composite_trust,
            irbi_score=irbi_score,
        )
        # Unconditional routing trace — always present so callers can audit
        # whether BNPB influenced scores or was suppressed.
        if bnpb_active and irbi_score > 0.0 and vuln is not None:
            irbi_penalty = max(0.70, 1.0 - irbi_score * 0.3)
            safe_route["bnpb_route_trace"] = (
                f"[BNPB-ROUTING] district={vuln.district} | "
                f"IRBI={irbi_score:.2f} → irbi_penalty={irbi_penalty:.3f} | "
                f"composite_trust={composite_trust:.3f} → trust_modifier={composite_trust:.3f} | "
                f"final_route_score = base × {composite_trust:.3f} × {irbi_penalty:.3f}"
            )
        else:
            skip_code = bnpb_status.get("code", "NOT_APPLICABLE")
            safe_route["bnpb_route_trace"] = (
                f"[BNPB-ROUTING-SKIPPED] code={skip_code} — routing unaffected"
            )
        safe_route = _enrich_route(safe_route, system_status, risk_level, flood_zones, danger_constraint_applied)
        return {
            "safe_route": safe_route,
            "tma_data": tma_result,
            "tma_failure": tma_failure,
            "confidence_adjustment": confidence_adjustment,
        }

    def _tma_failure_record(self, tma_result: dict) -> dict | None:
        """
        Build a failure record for the TMA fetch result.

        Status → action matrix:

          OK        → None (no failure).
          STALE     → if cached + age < TMA_STALE_GRACE_MINUTES → None
                      (cache is recent enough that the prediction horizon is
                      unaffected; no confidence penalty applied).
                    → otherwise → "medium" severity, normal penalty.
          DEGRADED  → "medium" severity, normal penalty (transport failure).
          INVALID   → "high" severity, normal penalty (corrupt data).

        Other status strings default to None (safe).
        """
        status = (tma_result.get("status") or "OK").upper()

        if status == "OK":
            return None

        if status == "STALE":
            stale_age = tma_result.get("stale_age_minutes")
            grace = _tma_stale_grace_minutes()
            try:
                stale_age_float = float(stale_age) if stale_age is not None else None
            except (TypeError, ValueError):
                stale_age_float = None
            if (
                tma_result.get("source") == "cache"
                and stale_age_float is not None
                and stale_age_float < grace
            ):
                _log.info(
                    "tma_scraper: STALE cache age=%.1f min < grace=%.1f min — "
                    "suppressing external_source_unreliable failure.",
                    stale_age_float,
                    grace,
                )
                return None
            severity = "medium"
            message = (
                "TMA scraping proxy returned STALE data — using cached or empty fallback; "
                "real-time water-level signals are unverified."
            )
        elif status == "DEGRADED":
            severity = "medium"
            message = (
                "TMA scraping proxy is degraded (transport failure) — real-time water-level "
                "data cannot be independently verified. Hydrology signals have reduced confidence."
            )
        elif status == "INVALID":
            severity = "high"
            message = (
                "TMA scraping proxy returned structurally invalid data — "
                "data discarded. Hydrology signals have reduced confidence."
            )
        else:
            return None

        return {
            "type": "external_source_unreliable",
            "severity": severity,
            "message": message,
            "detail": {
                "source": tma_result.get("source", "unknown"),
                "reason": tma_result.get("reason", ""),
                "reliability": tma_result.get("reliability", "low"),
                "tma_status": status,
                "stale_age_minutes": tma_result.get("stale_age_minutes"),
            },
            "confidence_penalty": _TMA_DEGRADED_PENALTY,
        }


# ─── Danger-level route filtering ────────────────────────────────────────────

def _filter_danger_routes(
    routes: list[dict], flood_zones: list[dict], safety_threshold: float = 0.90
) -> tuple[list[dict], bool]:
    """
    For DANGER risk: enforce hard avoidance of high-severity zones.

    Returns (filtered_routes, constraint_was_binding).
    constraint_was_binding=True means no fully clean route existed — caller
    must add an explicit warning in the route output.
    """
    high_zones = [z for z in flood_zones if z.get("severity") == "high"]
    if not high_zones:
        return routes, False

    clean = [r for r in routes if compute_route_safety(r, high_zones) >= safety_threshold]
    if clean:
        return clean, False
    # No clean alternative — return all routes but flag the constraint
    return routes, True


# ─── Route enrichment (confidence + advisory) ────────────────────────────────

def _enrich_route(
    route: dict,
    system_status: str,
    risk_level: str,
    flood_zones: list[dict],
    danger_constraint_applied: bool,
) -> dict:
    """
    Attach confidence, advisory, and decision_explanation to a select_best_route result.

    confidence:          "high" | "medium" | "low"
    advisory:            human-readable caveats about route trustworthiness
    decision_explanation: concise trade-off summary (Task 9)
    """
    try:
        return _enrich_route_impl(route, system_status, risk_level, flood_zones, danger_constraint_applied)
    except Exception:  # noqa: BLE001
        route.setdefault("confidence", "low")
        route.setdefault("advisory", "Route enrichment failed — treat with caution.")
        route.setdefault("decision_explanation", "Route enrichment unavailable.")
        return route


def _enrich_route_impl(
    route: dict,
    system_status: str,
    risk_level: str,
    flood_zones: list[dict],
    danger_constraint_applied: bool,
) -> dict:
    if not route.get("available"):
        route.setdefault("confidence", "low")
        route.setdefault("advisory", None)
        route.setdefault("decision_explanation", "No safe route available.")
        return route

    safety = route.get("safety_score", 0.0) or 0.0
    advisory_parts: list[str] = []

    # Confidence tier
    if system_status == "LOW_TRUST":
        confidence = "low"
        route["safety_score"] = round(max(0.0, safety - 0.10), 4)
        advisory_parts.append(
            "System confidence is LOW — route safety estimate is less reliable than usual. "
            "Independent local knowledge recommended before travel."
        )
    elif safety >= 0.90 and system_status == "OK":
        confidence = "high"
    elif safety >= 0.70:
        confidence = "medium"
    else:
        confidence = "low"

    # DANGER hard-constraint advisory
    if danger_constraint_applied:
        advisory_parts.append(
            "WARNING: All available routes pass through high-severity flood zones. "
            "DANGER-level conditions are active — travel strongly discouraged. "
            "If travel is essential, use route with least flood exposure and monitor conditions continuously."
        )
    elif risk_level == "DANGER":
        high_avoided = sum(1 for z in flood_zones if z.get("severity") == "high")
        if high_avoided:
            advisory_parts.append(
                f"DANGER-level routing: {high_avoided} high-severity zone(s) strictly avoided. "
                "Route was selected under hard-avoidance constraint."
            )

    # Medium exposure advisory
    if safety < 0.70 and not danger_constraint_applied:
        medium_zones = sum(1 for z in flood_zones if z.get("severity") == "medium")
        advisory_parts.append(
            f"Route passes near {medium_zones} medium-severity flood zone(s). "
            "Exercise caution and allow extra travel time."
        )

    route["confidence"] = confidence
    route["advisory"] = " ".join(advisory_parts) if advisory_parts else None
    route["decision_explanation"] = _build_decision_explanation(
        route, flood_zones, danger_constraint_applied
    )
    return route


def _build_decision_explanation(
    route: dict,
    flood_zones: list[dict],
    danger_constraint_applied: bool,
) -> str:
    """
    One-sentence trade-off explanation for the selected route (Task 9).

    Explains the safety-vs-time trade-off and zone avoidance in plain language.
    """
    safety       = route.get("safety_score", 0.0) or 0.0
    alternatives = route.get("alternatives_evaluated", 1)
    high_zones   = sum(1 for z in flood_zones if z.get("severity") == "high")
    medium_zones = sum(1 for z in flood_zones if z.get("severity") == "medium")
    all_zones    = high_zones + medium_zones

    if danger_constraint_applied:
        return (
            f"No flood-free route found — all {alternatives} candidate(s) cross active "
            f"flood zones ({high_zones} high-severity). Least-risk option selected; "
            "travel not recommended."
        )

    if safety >= 0.90:
        zone_desc = f"{all_zones} active flood zone(s)" if all_zones else "all detected flood zones"
        return (
            f"Selected route fully avoids {zone_desc} "
            f"— optimal safety among {alternatives} alternative(s)."
        )

    if safety >= 0.70:
        return (
            f"Best available route ({safety:.0%} safety score) minimises exposure "
            f"across {high_zones} high-risk and {medium_zones} medium-risk zone(s) "
            f"among {alternatives} alternative(s)."
        )

    return (
        f"All {alternatives} route(s) have limited flood safety "
        f"(best: {safety:.0%}) — active flooding detected across "
        f"{high_zones} high-severity zone(s). Proceed only if essential."
    )


# ─── Simple unavailable helpers ──────────────────────────────────────────────

def _route_skipped(reason: str) -> dict:
    return {
        "available": False,
        "distance_km": None,
        "eta_minutes": None,
        "safety_score": None,
        "combined_score": None,
        "summary": None,
        "confidence": None,
        "advisory": None,
        "reason": reason,
        "flood_zones_checked": 0,
        "alternatives_evaluated": 0,
    }


def _route_unavailable(reason: str | None) -> dict:
    return {
        "available": False,
        "distance_km": None,
        "eta_minutes": None,
        "safety_score": None,
        "combined_score": None,
        "summary": None,
        "confidence": None,
        "advisory": None,
        "reason": reason or "Routing service unavailable.",
        "flood_zones_checked": 0,
        "alternatives_evaluated": 0,
    }


def _route_advisory(risk_level: str, flood_zones: list[dict]) -> dict:
    """
    Advisory returned when risk >= WARNING but no coordinates were given.

    Tells the caller how many zones are active and prompts for coordinates.
    """
    high = sum(1 for z in flood_zones if z.get("severity") == "high")
    medium = sum(1 for z in flood_zones if z.get("severity") == "medium")
    return {
        "available": False,
        "distance_km": None,
        "eta_minutes": None,
        "safety_score": None,
        "combined_score": None,
        "summary": None,
        "confidence": None,
        "advisory": (
            f"{len(flood_zones)} active flood zone(s): {high} high-severity, {medium} medium-severity. "
            "Supply 'origin' and 'destination' for a concrete flood-safe route recommendation."
        ),
        "reason": (
            f"Risk level {risk_level} detected — flood-zone avoidance is active. "
            "Provide 'origin' and 'destination' query parameters for a routed recommendation."
        ),
        "flood_zones_checked": len(flood_zones),
        "alternatives_evaluated": 0,
    }
