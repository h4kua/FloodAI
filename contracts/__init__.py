"""
Single source of truth for all flood-domain vocabulary.

Anything that needs to talk about SystemStatus, RiskLevel, Driver,
DecisionReason, DecisionAuthority, FailureSeverity MUST import from
``app.contracts.vocabulary`` — never define a parallel literal or enum
elsewhere. CI gate ``scripts/check_vocabulary_drift.py`` enforces this.
"""

from contracts.vocabulary import (
    DecisionAuthority,
    DecisionReason,
    Driver,
    FailureSeverity,
    RiskLevel,
    SystemStatus,
)

__all__ = [
    "DecisionAuthority",
    "DecisionReason",
    "Driver",
    "FailureSeverity",
    "RiskLevel",
    "SystemStatus",
]
