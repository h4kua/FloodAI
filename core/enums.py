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

# Phase 6: derive the legacy frozensets from the canonical vocabulary so a
# future addition to app/contracts/vocabulary.py auto-propagates here without
# manual edit. Scalar string constants below are kept inline for back-compat
# with consumers that import them by name (e.g. RISK_LEVEL_DANGER).
from contracts.vocabulary import (
    DecisionReason as _CanonicalDecisionReason,
    RiskLevel as _CanonicalRiskLevel,
    SystemStatus as _CanonicalSystemStatus,
)

# ─── risk_level ───────────────────────────────────────────────────────────────
RISK_LEVEL_SAFE:      Final[str] = "SAFE"
RISK_LEVEL_PRE_ALERT: Final[str] = "PRE_ALERT"
RISK_LEVEL_WARNING:   Final[str] = "WARNING"
RISK_LEVEL_DANGER:    Final[str] = "DANGER"
RISK_LEVEL_UNKNOWN:   Final[str] = "UNKNOWN"

RISK_LEVELS: Final[FrozenSet[str]] = frozenset(r.value for r in _CanonicalRiskLevel)

# ─── system_status ────────────────────────────────────────────────────────────
SYSTEM_STATUS_OK:               Final[str] = "OK"
SYSTEM_STATUS_DEGRADED:         Final[str] = "DEGRADED"
SYSTEM_STATUS_LOW_TRUST:        Final[str] = "LOW_TRUST"
SYSTEM_STATUS_CONFLICT:         Final[str] = "CONFLICT"
SYSTEM_STATUS_FAIL:             Final[str] = "FAIL"
SYSTEM_STATUS_PIPELINE_FAILURE: Final[str] = "PIPELINE_FAILURE"

SYSTEM_STATUSES: Final[FrozenSet[str]] = frozenset(s.value for s in _CanonicalSystemStatus)

# Subset: statuses under which automation is permitted.
# CONFLICT and LOW_TRUST cause guardrail attenuation; PIPELINE_FAILURE bypasses
# ML entirely. OK and DEGRADED are the only "automation-eligible" statuses.
SYSTEM_STATUSES_AUTOMATION_ELIGIBLE: Final[FrozenSet[str]] = frozenset({
    SYSTEM_STATUS_OK,
    SYSTEM_STATUS_DEGRADED,
})

# ─── decision_reason ──────────────────────────────────────────────────────────
# Scalar constants kept inline for back-compat (consumers do
# `from core.enums import DECISION_REASON_FALLBACK`). The frozenset is
# derived from canonical so it auto-tracks future additions.
DECISION_REASON_RISK:            Final[str] = "RISK"
DECISION_REASON_INVALID_INPUT:   Final[str] = "INVALID_INPUT"
DECISION_REASON_FALLBACK:        Final[str] = "FALLBACK"
DECISION_REASON_PHYSICAL_GATE:   Final[str] = "PHYSICAL_GATE"
DECISION_REASON_MULTI_SIGNAL:    Final[str] = "MULTI_SIGNAL"
DECISION_REASON_TREND_EXTENSION: Final[str] = "TREND_EXTENSION"

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
