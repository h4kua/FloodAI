"""
Output schema and consistency validation for the flood prediction pipeline.

This module is the single, authoritative gatekeeper that runs immediately
before a pipeline result is returned to the caller. It enforces three things:

  1. **Enum correctness** — every closed-enumeration field
     (``risk_level``, ``system_status``, ``decision_reason``,
     ``data_validity``, ``ml_execution_mode``) must hold a value from the
     central enum module.

  2. **Required field presence** — the contractual top-level keys must exist
     and have valid types.

  3. **Cross-field consistency** — the 9 invariants of the disambiguation
     layer must hold. Any contradiction (e.g. ``data_validity == INVALID``
     paired with ``decision_reason == RISK``) is a hard error.

Failure mode is intentionally non-raising at the pipeline boundary: if a final
output ever fails validation, the pipeline must still return a structurally
valid dict — but a *safe-fallback* dict that downstream consumers cannot
mistake for a real prediction. This means a bug in the decision layer can
never produce silently malformed output.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.enums import (
    DATA_VALIDITY_INVALID,
    DATA_VALIDITY_VALID,
    DATA_VALIDITY_VALUES,
    DECISION_REASON_FALLBACK,
    DECISION_REASON_INVALID_INPUT,
    DECISION_REASON_RISK,
    DECISION_REASONS,
    ML_EXECUTION_FULL,
    ML_EXECUTION_MODES,
    ML_EXECUTION_SHADOW_ONLY,
    RISK_LEVEL_UNKNOWN,
    RISK_LEVEL_WARNING,
    RISK_LEVELS,
    SYSTEM_STATUS_PIPELINE_FAILURE,
    SYSTEM_STATUSES,
    SYSTEM_STATUSES_AUTOMATION_ELIGIBLE,
)

_log = logging.getLogger(__name__)


class OutputContractError(Exception):
    """Raised internally by the validators. Never propagated out of the pipeline."""


# ──────────────────────────────────────────────────────────────────────────────
# Decision-meta block validation
# ──────────────────────────────────────────────────────────────────────────────

def validate_decision_meta(
    *,
    decision_reason: str,
    data_validity: str,
    ml_execution_mode: str,
    is_safe_for_automation: bool,
    risk_level: str,
    system_status: str,
) -> None:
    """
    Enforce the 9 consistency invariants between the four decision-meta fields,
    plus their interaction with risk_level and system_status.

    Raises OutputContractError on any violation. The caller is expected to
    convert the failure into a safe-fallback output, never to surface it raw.
    """
    # ── Enum correctness ──────────────────────────────────────────────────
    if decision_reason not in DECISION_REASONS:
        raise OutputContractError(
            f"decision_reason={decision_reason!r} is not a valid enum value. "
            f"Allowed: {sorted(DECISION_REASONS)}"
        )
    if data_validity not in DATA_VALIDITY_VALUES:
        raise OutputContractError(
            f"data_validity={data_validity!r} is not a valid enum value. "
            f"Allowed: {sorted(DATA_VALIDITY_VALUES)}"
        )
    if ml_execution_mode not in ML_EXECUTION_MODES:
        raise OutputContractError(
            f"ml_execution_mode={ml_execution_mode!r} is not a valid enum value. "
            f"Allowed: {sorted(ML_EXECUTION_MODES)}"
        )
    if risk_level not in RISK_LEVELS:
        raise OutputContractError(
            f"risk_level={risk_level!r} is not a valid enum value."
        )
    if system_status not in SYSTEM_STATUSES:
        raise OutputContractError(
            f"system_status={system_status!r} is not a valid enum value."
        )
    if not isinstance(is_safe_for_automation, bool):
        raise OutputContractError(
            f"is_safe_for_automation must be bool, got {type(is_safe_for_automation).__name__}"
        )

    # ── Cross-field invariants ────────────────────────────────────────────
    # Inv-1: INVALID data ⇒ never safe for automation
    if data_validity == DATA_VALIDITY_INVALID and is_safe_for_automation:
        raise OutputContractError(
            "Inv-1: data_validity=INVALID but is_safe_for_automation=True"
        )
    # Inv-2: INVALID data ⇒ decision_reason in {INVALID_INPUT, FALLBACK}
    if data_validity == DATA_VALIDITY_INVALID and decision_reason == DECISION_REASON_RISK:
        raise OutputContractError(
            "Inv-2: data_validity=INVALID but decision_reason=RISK"
        )
    # Inv-3: INVALID data ⇒ ML in shadow
    if data_validity == DATA_VALIDITY_INVALID and ml_execution_mode == ML_EXECUTION_FULL:
        raise OutputContractError(
            "Inv-3: data_validity=INVALID but ml_execution_mode=FULL"
        )
    # Inv-4: INVALID_INPUT ⇒ data_validity=INVALID
    if decision_reason == DECISION_REASON_INVALID_INPUT and data_validity != DATA_VALIDITY_INVALID:
        raise OutputContractError(
            "Inv-4: decision_reason=INVALID_INPUT but data_validity != INVALID"
        )
    # Inv-5: INVALID_INPUT ⇒ ml_execution_mode=SHADOW_ONLY
    if decision_reason == DECISION_REASON_INVALID_INPUT and ml_execution_mode != ML_EXECUTION_SHADOW_ONLY:
        raise OutputContractError(
            "Inv-5: decision_reason=INVALID_INPUT but ml_execution_mode != SHADOW_ONLY"
        )
    # Inv-6: INVALID_INPUT ⇒ canonical invalid-input risk placeholder.
    # The authoritative runtime now surfaces UNKNOWN; WARNING is still accepted
    # for backward compatibility with older fallback payloads.
    if (
        decision_reason == DECISION_REASON_INVALID_INPUT
        and risk_level not in {RISK_LEVEL_UNKNOWN, RISK_LEVEL_WARNING}
    ):
        raise OutputContractError(
            f"Inv-6: decision_reason=INVALID_INPUT but risk_level={risk_level!r}"
        )
    # Inv-7: FALLBACK ⇒ system_status=PIPELINE_FAILURE
    if decision_reason == DECISION_REASON_FALLBACK and system_status != SYSTEM_STATUS_PIPELINE_FAILURE:
        raise OutputContractError(
            f"Inv-7: decision_reason=FALLBACK but system_status={system_status!r}"
        )
    # Inv-8: RISK ⇒ data_validity=VALID
    if decision_reason == DECISION_REASON_RISK and data_validity != DATA_VALIDITY_VALID:
        raise OutputContractError(
            f"Inv-8: decision_reason=RISK but data_validity={data_validity!r}"
        )
    # Inv-9: is_safe_for_automation=True ⇒ all green
    if is_safe_for_automation:
        if (
            data_validity != DATA_VALIDITY_VALID
            or decision_reason != DECISION_REASON_RISK
            or ml_execution_mode != ML_EXECUTION_FULL
            or system_status not in SYSTEM_STATUSES_AUTOMATION_ELIGIBLE
        ):
            raise OutputContractError(
                "Inv-9: is_safe_for_automation=True but one or more of "
                "(data_validity, decision_reason, ml_execution_mode, system_status) "
                "is not in the automation-eligible state"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Output schema validation
# ──────────────────────────────────────────────────────────────────────────────

# Required top-level keys for any pipeline output (happy or emergency path).
_REQUIRED_KEYS_BASE: frozenset[str] = frozenset({
    "risk_level",
    "confidence_score",
    "system_status",
    "requires_manual_review",
    "failure_modes",
    "decision_reason",
    "data_validity",
    "ml_execution_mode",
    "is_safe_for_automation",
})

# Additional required keys when system_status != PIPELINE_FAILURE.
_REQUIRED_KEYS_HAPPY: frozenset[str] = frozenset({
    "decision_trace",
    "probability",
    "dominant_risk_driver",
    "risk_interpretation",
})


def validate_output_schema(result: dict[str, Any]) -> None:
    """
    Validate the final pipeline output dict immediately before return.

    Raises OutputContractError on any of:
      - missing required key
      - wrong type on a required scalar
      - confidence_score outside [0, 1]
      - cross-field consistency invariant violation

    The caller (FloodDecisionPipeline.run) is responsible for catching this
    and substituting a safe-fallback dict so the pipeline never returns
    a malformed object.
    """
    if not isinstance(result, dict):
        raise OutputContractError(f"output is not a dict: {type(result).__name__}")

    required = set(_REQUIRED_KEYS_BASE)
    if result.get("system_status") != SYSTEM_STATUS_PIPELINE_FAILURE:
        required |= _REQUIRED_KEYS_HAPPY

    missing = required - result.keys()
    if missing:
        raise OutputContractError(f"output missing required keys: {sorted(missing)}")

    confidence = result.get("confidence_score")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        raise OutputContractError(
            f"confidence_score must be a number in [0, 1], got {confidence!r}"
        )
    if not isinstance(result.get("requires_manual_review"), bool):
        raise OutputContractError("requires_manual_review must be bool")
    if not isinstance(result.get("failure_modes"), list):
        raise OutputContractError("failure_modes must be a list")

    validate_decision_meta(
        decision_reason=result["decision_reason"],
        data_validity=result["data_validity"],
        ml_execution_mode=result["ml_execution_mode"],
        is_safe_for_automation=result["is_safe_for_automation"],
        risk_level=result["risk_level"],
        system_status=result["system_status"],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Safe fallback
# ──────────────────────────────────────────────────────────────────────────────

def safe_fallback_output(
    reason: str,
    *,
    error_type: str = "OutputContractError",
    original_result: dict[str, Any] | None = None,
    now: "datetime | None" = None,
) -> dict[str, Any]:
    """
    A minimal, contractually-valid pipeline output used when validation fails.

    By construction this dict satisfies ``validate_output_schema`` — using it
    means a contract bug never produces silently malformed output. Downstream
    consumers see ``decision_reason=FALLBACK``, ``data_validity=INVALID``,
    ``is_safe_for_automation=False`` and a failure record explaining the cause.

    Observability (always present on this code path, ABSENT elsewhere):
      * ``contract_violation`` — structured diagnostic block with the error
        type, message, and (optionally) a snapshot of the offending fields.
        PostgreSQL queries can use ``WHERE contract_violation IS NOT NULL``
        to find every internal-logic regression that ever fired.
      * ``decision_trace`` — first entry is ``[L5-CONTRACT-FAILURE]`` so the
        failure shows up in the same trace consumers already read.

    Args:
        reason: Human-readable description of the validation failure.
        error_type: Exception class name (e.g. ``"OutputContractError"``).
        original_result: Optionally, the malformed dict so a snapshot of the
            offending fields is preserved for forensics. Stored under
            ``contract_violation.original_snapshot`` if provided.
    """
    contract_violation: dict[str, Any] = {
        "triggered": True,
        "error_type": error_type,
        "message": reason,
    }
    if original_result is not None:
        # Audit-grade snapshot only — full dict belongs in logs, not in every record.
        contract_violation["original_snapshot"] = {
            k: original_result.get(k)
            for k in (
                "risk_level",
                "system_status",
                "decision_reason",
                "data_validity",
                "ml_execution_mode",
                "is_safe_for_automation",
                "decision_source",
                "confidence_score",
            )
            if k in original_result
        }

    trace = [
        f"[L5-CONTRACT-FAILURE] {error_type}: {reason}",
        "[L5-CONTRACT-FAILURE] Pipeline output failed schema/invariant validation. "
        "Safe-fallback dict substituted to prevent malformed output reaching "
        "downstream consumers. Investigate the offending decision path.",
    ]

    return {
        "system_status": SYSTEM_STATUS_PIPELINE_FAILURE,
        "requires_manual_review": True,
        "decision_reason": DECISION_REASON_FALLBACK,
        "data_validity": DATA_VALIDITY_INVALID,
        "ml_execution_mode": ML_EXECUTION_SHADOW_ONLY,
        "is_safe_for_automation": False,
        "risk_level": RISK_LEVEL_UNKNOWN,
        "probability": 0.0,
        "confidence_score": 0.0,
        "dominant_risk_driver": "output_contract_violation",
        "risk_interpretation": (
            f"Output schema validation failed: {reason}. "
            "Returning safe-fallback dict to prevent malformed output from "
            "reaching downstream consumers. Investigate the offending decision path."
        ),
        "recommended_action": [
            "IMMEDIATE: Pipeline produced an inconsistent output schema. "
            "Manual flood assessment required while the contract violation is investigated."
        ],
        "failure_modes": [{
            "type": "output_contract_violation",
            "severity": "critical",
            "message": reason,
            "detail": {"error_type": error_type},
        }],
        "decision_trace": trace,
        "contract_violation": contract_violation,
        "baseline_check": {
            "baseline_probability": 0.0,
            "rainfall_baseline": {},
            "hydro_baseline": {},
            "baseline_disagreement": 0.0,
            "baseline_alert": False,
            "model_vs_baseline": "unknown",
        },
        "data_freshness_minutes": -1.0,
        "signals": {},
        "diagnostics": {},
        "timestamp_utc": (now if now is not None else datetime.now(timezone.utc)).isoformat(),
        "pipeline_version": "agentic-v2.0",
        "model_name": "unknown",
    }
