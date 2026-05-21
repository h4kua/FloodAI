"""
BNPB InaRISK activation gate — single-source-of-truth, audit-grade.

Central authority for ALL BNPB influence decisions.

Design contract (enforced here, not in calling agents):
  - evaluate_bnpb_status() is THE ONLY authority that computes BNPB status.
    It returns a structured dict {active, code, reason} covering every case.
  - EvaluationAgent calls evaluate_bnpb_status() once and stores the result in
    EvaluationResult.bnpb_status. ALL downstream agents consume that stored result.
  - No agent may independently re-evaluate the gate. No hidden gate logic exists
    outside this module.
  - composite_trust (system reliability) and irbi_score (vulnerability priority)
    are KEPT SEPARATE and NEVER merged into a single modifier.
  - build_*_trace() helpers produce deterministic audit strings.

Status codes and their semantics:
  ACTIVE           — gate open; live InaRISK API data drives the IRBI value.
  STATIC_FALLBACK  — gate open; bundled static JSON drives the IRBI value
                     (live API unreachable). Operationally equivalent to
                     ACTIVE for routing / threshold purposes; flagged so
                     operators can tell it is bundled-curated, not live.
  DEFAULT          — gate open; district mapped to Jakarta but no record
                     in either source — mid-band IRBI=0.5 stamped.
  NOT_APPLICABLE   — location outside Jakarta or mapping confidence < 0.70
  STALE            — IRBI survey data older than 365 days
  CONFLICT_BLOCKED — system_status == "CONFLICT"; adding IRBI would compound contradiction
  SKIPPED          — generic fallback (should not be reached with complete checks)

BNPB MUST NOT modify: probability, risk_level.
BNPB ONLY affects: prioritisation, sensitivity thresholds, operational guidance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.bnpb_context import VulnerabilityContext

_MAX_VINTAGE_DAYS = 365

# Allowed canonical Jakarta kota — any other district is out of scope.
# Includes Kepulauan Seribu (6th DKI Jakarta administrative unit, BPS code
# 3101) so the static fallback record published in
# ``app/data/bnpb_jakarta_fallback.json`` opens the gate when the API
# input maps cleanly to it.
_VALID_DISTRICTS: frozenset[str] = frozenset({
    "Jakarta Pusat",
    "Jakarta Utara",
    "Jakarta Barat",
    "Jakarta Selatan",
    "Jakarta Timur",
    "Kepulauan Seribu",
})

# IRBI contribution to effective_trust suppression.
# effective_trust = composite_trust × (1 − irbi_score × _IRBI_TRUST_WEIGHT)
_IRBI_TRUST_WEIGHT = 0.20

# Floor: effective_trust never drops below this so routing scores stay meaningful.
_EFFECTIVE_TRUST_FLOOR = 0.40


def evaluate_bnpb_status(
    vuln_context: "VulnerabilityContext | None",
    mapping_info: dict,
    system_status: str,
) -> dict:
    """
    Single-source-of-truth BNPB activation decision.

    Called ONCE by EvaluationAgent. The result is stored in
    EvaluationResult.bnpb_status and consumed by all downstream agents.
    No other code may independently compute the gate decision.

    Returns a dict with three keys:
        active  — bool: True only when BNPB influence is permitted
        code    — str: machine-readable status (ACTIVE | NOT_APPLICABLE |
                       STALE | CONFLICT_BLOCKED | SKIPPED)
        reason  — str: human-readable trace entry starting with a [BNPB-*] tag

    Never raises. All failure modes return active=False with an explanatory reason.
    """
    # ── Shared inputs snapshot — included in every return for external audit ──
    mapping_confidence = float(mapping_info.get("confidence") or 0.0)
    input_loc          = mapping_info.get("input_location", "")
    inputs = {
        "district":            vuln_context.district if vuln_context is not None else "",
        "mapping_confidence":  round(mapping_confidence, 4),
        "data_vintage_days":   vuln_context.data_vintage_days if vuln_context is not None else 0,
        "system_status":       system_status,
    }

    # ── Mapping confidence gate (checked first, independent of vuln_context) ──
    # Any positive-but-uncertain confidence below 0.70 indicates an ambiguous
    # district assignment; accepting it would silently use the wrong IRBI values.
    if 0.0 < mapping_confidence < 0.70:
        return {
            "active": False,
            "code":   "NOT_APPLICABLE",
            "reason": (
                f"[BNPB-NOT-APPLICABLE] Mapping confidence {mapping_confidence:.2f} "
                f"< 0.70 for '{input_loc}' — district assignment ambiguous, "
                "BNPB data rejected"
            ),
            "inputs": inputs,
        }

    # ── No vulnerability context ──────────────────────────────────────────────
    if vuln_context is None:
        return {
            "active": False,
            "code":   "NOT_APPLICABLE",
            "reason": (
                "[BNPB-NOT-APPLICABLE] Vulnerability data unavailable "
                "(API failure, stale cache, or location outside Jakarta scope)"
            ),
            "inputs": inputs,
        }

    # ── District outside Jakarta ──────────────────────────────────────────────
    if vuln_context.district not in _VALID_DISTRICTS:
        return {
            "active": False,
            "code":   "NOT_APPLICABLE",
            "reason": (
                f"[BNPB-NOT-APPLICABLE] District '{vuln_context.district}' is outside "
                "the five recognised Jakarta kota — BNPB data rejected"
            ),
            "inputs": inputs,
        }

    # ── Stale survey data ─────────────────────────────────────────────────────
    if vuln_context.data_vintage_days > _MAX_VINTAGE_DAYS:
        return {
            "active": False,
            "code":   "STALE",
            "reason": (
                f"[BNPB-SKIPPED] Data stale ({vuln_context.data_vintage_days} days "
                f"> {_MAX_VINTAGE_DAYS} day limit) — BNPB influence disabled"
            ),
            "inputs": inputs,
        }

    # ── System conflict — adding IRBI would compound contradictory signals ────
    if system_status == "CONFLICT":
        return {
            "active": False,
            "code":   "CONFLICT_BLOCKED",
            "reason": (
                "[BNPB-SKIPPED] System status CONFLICT — BNPB adjustments "
                "suppressed to avoid compounding contradictory signals"
            ),
            "inputs": inputs,
        }

    # ── Gate open ─────────────────────────────────────────────────────────────
    # Status code reflects the data lineage so operators and downstream
    # automation can tell whether the IRBI value rode on live API data
    # (ACTIVE), bundled static fallback (STATIC_FALLBACK), or a synthetic
    # mid-band default for a mapped-but-unknown district (DEFAULT).
    irbi = vuln_context.effective_irbi_score
    source = getattr(vuln_context, "data_source", "api")
    code_by_source = {
        "api":             "ACTIVE",
        "static_fallback": "STATIC_FALLBACK",
        "default":         "DEFAULT",
    }
    code = code_by_source.get(source, "ACTIVE")
    tag = f"[BNPB-{code}]"
    return {
        "active": True,
        "code":   code,
        "reason": (
            f"{tag} district={vuln_context.district}, "
            f"IRBI={irbi:.2f}, exposure={vuln_context.exposure_class}, "
            f"vintage={vuln_context.data_vintage_days}d, "
            f"data_source={source}"
        ),
        "inputs": inputs,
    }


def is_bnpb_active(
    vuln_context: "VulnerabilityContext | None",
    system_status: str,
) -> bool:
    """
    DEPRECATED — agents must not call this directly.

    Kept for reference only. Use EvaluationResult.bnpb_status["active"] in
    all agents. Calling this independently creates a second gate decision that
    can diverge from the authoritative result stored in EvaluationResult.
    """
    return (
        vuln_context is not None
        and vuln_context.data_vintage_days <= _MAX_VINTAGE_DAYS
        and system_status != "CONFLICT"
    )


def check_bnpb_gate(
    vuln_context: "VulnerabilityContext | None",
    mapping_info: dict,
    system_status: str,
) -> tuple[bool, str]:
    """
    Thin wrapper around evaluate_bnpb_status() for backward compatibility.

    Prefer evaluate_bnpb_status() for new code — it returns the full
    structured dict including the machine-readable status code.
    """
    result = evaluate_bnpb_status(vuln_context, mapping_info, system_status)
    return result["active"], result["reason"]


def compute_effective_trust(
    composite_trust: float,
    irbi_score: float,
) -> float:
    """
    DEPRECATED for routing use — kept for backward compatibility only.

    Merging composite_trust and irbi_score into a single modifier causes global
    route score degradation rather than selective prioritisation.  Routing must
    apply composite_trust and irbi_penalty as independent multiplicative factors:

        route_score = base_score × composite_trust × irbi_penalty
        irbi_penalty = max(0.70, 1 - irbi_score * 0.30)

    This function may still be used for non-routing trust calculations where
    composite suppression is explicitly required.
    """
    raw = composite_trust * (1.0 - irbi_score * _IRBI_TRUST_WEIGHT)
    return round(max(_EFFECTIVE_TRUST_FLOOR, min(1.0, raw)), 4)


def build_threshold_trace(
    base_threshold: float,
    irbi_score: float,
    final_threshold: float,
    district: str,
) -> str:
    """Audit string for an IRBI-raised manual review threshold."""
    return (
        f"[BNPB] IRBI={irbi_score:.2f} ({district}) → "
        f"manual review threshold raised from {base_threshold:.2f} "
        f"→ {final_threshold:.2f}"
    )


def build_route_trace(
    irbi_score: float,
    irbi_penalty: float,
    composite_trust: float,
    district: str,
) -> str:
    """
    Audit string showing composite_trust and irbi_penalty as separate factors.

    Formula: route_score = base_score × composite_trust × irbi_penalty
    """
    net_multiplier = round(composite_trust * irbi_penalty, 4)
    return (
        f"[BNPB] Route scoring: composite_trust={composite_trust:.2f} "
        f"× irbi_penalty={irbi_penalty:.2f} (IRBI={irbi_score:.2f}) "
        f"→ net_multiplier={net_multiplier:.2f} for {district}"
    )


def build_conflict_trace(vuln: "VulnerabilityContext", risk_level: str) -> str:
    """
    Trace entry when high structural vulnerability contradicts stable real-time signals.

    Fired when: BNPB gate open AND exposure HIGH/VERY_HIGH AND risk_level == SAFE.
    Signals that BNPB is advisory-only — no operational escalation is warranted.
    """
    return (
        f"[BNPB-CONFLICT] {vuln.district} IRBI={vuln.effective_irbi_score:.2f} "
        f"({vuln.exposure_class}) — structural vulnerability is elevated but "
        f"real-time signals show {risk_level}. "
        "BNPB advisory applies; no operational escalation warranted."
    )
