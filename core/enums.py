"""
Central enum module for the flood prediction pipeline.

Single source of truth for every closed enumeration used in the public output
schema. Importing the constants from this module — instead of typing the
literal strings inline — eliminates an entire class of typo / drift bugs.

Each enumeration exposes BOTH:
  * Individual ``Final`` string constants for assignment   (e.g. ``RISK_LEVEL_DANGER``)
  * A ``frozenset`` of all valid values for membership checks (e.g. ``RISK_LEVELS``)

Backward compatibility:
  Values are the exact strings already produced by the system. Replacing inline
  literals with these constants is a pure refactor — no consumer behaviour
  changes.

Usage:
    from core.enums import (
        RISK_LEVEL_DANGER, RISK_LEVELS,
        DECISION_REASON_INVALID_INPUT, DECISION_REASONS,
    )
    risk_level = RISK_LEVEL_DANGER                # exact, IDE-checkable string
    assert risk_level in RISK_LEVELS              # membership check
"""

from __future__ import annotations

from typing import Final, FrozenSet

# Every value below is DERIVED from contracts/vocabulary.py's canonical Enums
# — never retyped as a literal — so this module can no longer drift from the
# single source of truth (a previous version retyped literals here and had
# silently fallen out of sync with the canonical DecisionReason members).
from contracts.vocabulary import (
    DecisionReason as _CanonicalDecisionReason,
    RiskLevel as _CanonicalRiskLevel,
    SystemStatus as _CanonicalSystemStatus,
)

# ─── risk_level ───────────────────────────────────────────────────────────────
RISK_LEVEL_SAFE:      Final[str] = _CanonicalRiskLevel.SAFE.value
RISK_LEVEL_PRE_ALERT: Final[str] = _CanonicalRiskLevel.PRE_ALERT.value
RISK_LEVEL_WARNING:   Final[str] = _CanonicalRiskLevel.WARNING.value
RISK_LEVEL_DANGER:    Final[str] = _CanonicalRiskLevel.DANGER.value
RISK_LEVEL_UNKNOWN:   Final[str] = _CanonicalRiskLevel.UNKNOWN.value

RISK_LEVELS: Final[FrozenSet[str]] = frozenset(r.value for r in _CanonicalRiskLevel)

# ─── system_status ────────────────────────────────────────────────────────────
SYSTEM_STATUS_OK:               Final[str] = _CanonicalSystemStatus.OK.value
SYSTEM_STATUS_DEGRADED:         Final[str] = _CanonicalSystemStatus.DEGRADED.value
SYSTEM_STATUS_LOW_TRUST:        Final[str] = _CanonicalSystemStatus.LOW_TRUST.value
SYSTEM_STATUS_CONFLICT:         Final[str] = _CanonicalSystemStatus.CONFLICT.value
SYSTEM_STATUS_FAIL:             Final[str] = _CanonicalSystemStatus.FAIL.value
SYSTEM_STATUS_PIPELINE_FAILURE: Final[str] = _CanonicalSystemStatus.PIPELINE_FAILURE.value

SYSTEM_STATUSES: Final[FrozenSet[str]] = frozenset(s.value for s in _CanonicalSystemStatus)

# Subset: statuses under which automation is permitted.
# CONFLICT and LOW_TRUST cause guardrail attenuation; PIPELINE_FAILURE bypasses
# ML entirely. OK and DEGRADED are the only "automation-eligible" statuses.
SYSTEM_STATUSES_AUTOMATION_ELIGIBLE: Final[FrozenSet[str]] = frozenset({
    SYSTEM_STATUS_OK,
    SYSTEM_STATUS_DEGRADED,
})

# ─── decision_reason ──────────────────────────────────────────────────────────
DECISION_REASON_RISK:            Final[str] = _CanonicalDecisionReason.RISK.value
DECISION_REASON_INVALID_INPUT:   Final[str] = _CanonicalDecisionReason.INVALID_INPUT.value
DECISION_REASON_FALLBACK:        Final[str] = _CanonicalDecisionReason.FALLBACK.value
DECISION_REASON_PHYSICAL_GATE:   Final[str] = _CanonicalDecisionReason.PHYSICAL_GATE.value
DECISION_REASON_MULTI_SIGNAL:    Final[str] = _CanonicalDecisionReason.MULTI_SIGNAL.value
DECISION_REASON_TREND_EXTENSION: Final[str] = _CanonicalDecisionReason.TREND_EXTENSION.value

DECISION_REASONS: Final[FrozenSet[str]] = frozenset(
    r.value for r in _CanonicalDecisionReason
)

# ─── data_validity ────────────────────────────────────────────────────────────
DATA_VALIDITY_VALID:   Final[str] = "VALID"
DATA_VALIDITY_INVALID: Final[str] = "INVALID"

DATA_VALIDITY_VALUES: Final[FrozenSet[str]] = frozenset({
    DATA_VALIDITY_VALID,
    DATA_VALIDITY_INVALID,
})

# ─── ml_execution_mode ────────────────────────────────────────────────────────
ML_EXECUTION_FULL:        Final[str] = "FULL"
ML_EXECUTION_SHADOW_ONLY: Final[str] = "SHADOW_ONLY"

ML_EXECUTION_MODES: Final[FrozenSet[str]] = frozenset({
    ML_EXECUTION_FULL,
    ML_EXECUTION_SHADOW_ONLY,
})

# ─── decision_source (DecisionResult.decision_source) ─────────────────────────
# The decision-engine layer that produced the final decision. Used internally
# by ActionAgent to derive decision_reason. Centralising the strings prevents
# drift across decision_engine.py and the consumers in ActionAgent.
DECISION_SOURCE_PHYSICAL_OVERRIDE:     Final[str] = "physical_override"
DECISION_SOURCE_SIGNAL_OVERRIDE:       Final[str] = "signal_override"
DECISION_SOURCE_SYSTEM_GUARDRAIL:      Final[str] = "system_guardrail"
DECISION_SOURCE_ML_ADAPTIVE:           Final[str] = "ml_adaptive"
DECISION_SOURCE_TREND_INFORMED:        Final[str] = "trend_informed"
DECISION_SOURCE_INCONSISTENCY_OVERRIDE: Final[str] = "inconsistency_override"
DECISION_SOURCE_INVALID_INPUT_FALLBACK: Final[str] = "invalid_input_fallback"
DECISION_SOURCE_FAILSAFE:              Final[str] = "failsafe"

DECISION_SOURCES: Final[FrozenSet[str]] = frozenset({
    DECISION_SOURCE_PHYSICAL_OVERRIDE,
    DECISION_SOURCE_SIGNAL_OVERRIDE,
    DECISION_SOURCE_SYSTEM_GUARDRAIL,
    DECISION_SOURCE_ML_ADAPTIVE,
    DECISION_SOURCE_TREND_INFORMED,
    DECISION_SOURCE_INCONSISTENCY_OVERRIDE,
    DECISION_SOURCE_INVALID_INPUT_FALLBACK,
    DECISION_SOURCE_FAILSAFE,
    "unknown",  # tolerated default; never produced on a successful run
})
