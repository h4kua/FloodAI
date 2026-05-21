"""
The ONLY place in the codebase where flood-domain enums are defined.

Every layer (writer, migrations, API contract, evaluation harness, tests)
imports from here. Migrations CHECK constraints are auto-generated from these
enums by ``scripts/generate_check_constraints.py``. Adding a value here is
the only way to add a value anywhere.
"""

from __future__ import annotations

from enum import Enum


class SystemStatus(str, Enum):
    """
    Pipeline-level health for a single decision.

    Precedence (most → least severe): PIPELINE_FAILURE > FAIL > CONFLICT >
    LOW_TRUST > DEGRADED > OK. The decision engine resolves status by taking
    the most-severe applicable value via ``resolve_status``.
    """

    OK = "OK"
    DEGRADED = "DEGRADED"
    LOW_TRUST = "LOW_TRUST"
    CONFLICT = "CONFLICT"
    FAIL = "FAIL"
    PIPELINE_FAILURE = "PIPELINE_FAILURE"


class RiskLevel(str, Enum):
    """
    Final flood risk produced by the decision engine.

    PRE_ALERT sits between SAFE and WARNING — used when ML probability is
    above the watch threshold but below the alert threshold; surfaced to
    operators as "monitor", not "act".
    """

    SAFE = "SAFE"
    PRE_ALERT = "PRE_ALERT"
    WARNING = "WARNING"
    DANGER = "DANGER"
    UNKNOWN = "UNKNOWN"


class DecisionReason(str, Enum):
    """Why this risk_level was produced."""

    RISK = "RISK"
    INVALID_INPUT = "INVALID_INPUT"
    FALLBACK = "FALLBACK"
    PHYSICAL_GATE = "PHYSICAL_GATE"
    MULTI_SIGNAL = "MULTI_SIGNAL"
    TREND_EXTENSION = "TREND_EXTENSION"
    SAFETY_FLOOR = "SAFETY_FLOOR"


class Driver(str, Enum):
    """Dominant signal that drove the risk_level."""

    EXTREME_RAINFALL = "extreme_rainfall"
    SUSTAINED_RAINFALL = "sustained_heavy_rainfall"
    HIGH_RAINFALL = "high_rainfall"
    ATMOSPHERIC_BUILDUP = "atmospheric_buildup"
    BMKG_CONFIRMED_ALERT = "bmkg_confirmed_alert"
    BMKG_FORECAST_ALERT = "bmkg_forecast_alert"
    CRITICAL_HYDROLOGY = "critical_hydrology"
    HYDROLOGY_STRESS = "hydrology_stress"
    HYDROLOGY_UNVERIFIED = "hydrology_unverified"
    COMPOUND_EVENT = "compound_event"
    LOW_BACKGROUND_RISK = "low_background_risk"
    PIPELINE_ERROR = "pipeline_error"


class DecisionAuthority(str, Enum):
    """
    Which layer of the L0–L4 hierarchy actually produced the final decision.

    Replaces the misleading ``_decision_authority="EvaluationAgent"`` string.
    Every persisted decision row carries the L-level for forensics.
    """

    L0_PHYSICAL = "L0_PHYSICAL"
    L1_SIAGA = "L1_SIAGA"
    L1_5_MULTI = "L1_5_MULTI"
    L1_7_BMKG_SAFETY_FLOOR = "L1_7_BMKG_SAFETY_FLOOR"
    L2_INTEGRITY = "L2_INTEGRITY"
    L3_ML = "L3_ML"
    L4_TREND = "L4_TREND"


class FailureSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Precedence used by ``resolve_status`` when multiple statuses apply at once.
# Ordered most-severe → least-severe.
SYSTEM_STATUS_PRECEDENCE: tuple[SystemStatus, ...] = (
    SystemStatus.PIPELINE_FAILURE,
    SystemStatus.FAIL,
    SystemStatus.CONFLICT,
    SystemStatus.LOW_TRUST,
    SystemStatus.DEGRADED,
    SystemStatus.OK,
)


def resolve_status(*statuses: SystemStatus) -> SystemStatus:
    """Return the most-severe SystemStatus from the inputs (default OK)."""
    if not statuses:
        return SystemStatus.OK
    rank = {s: i for i, s in enumerate(SYSTEM_STATUS_PRECEDENCE)}
    return min(statuses, key=lambda s: rank[s])
