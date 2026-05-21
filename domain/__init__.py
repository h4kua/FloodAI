"""
Pure-function domain layer.

Modules in this package have NO dependencies on FastAPI, psycopg2, sklearn,
or any external service. They take typed inputs and return typed outputs.
This is the canonical place where the flood-prediction decision is computed.

The agents in ``app/agents/`` are thin wrappers that build the inputs to
these functions and persist the outputs. Anything that *changes* a final
``risk_level`` MUST live in ``app/domain/decision.py``.
"""

from domain.decision import (
    AdaptiveThresholds,
    Decision,
    FailureMode,
    PerceptionInputs,
    PhysicalSignals,
    ReasoningInputs,
    TrendSnapshot,
    decide,
)

__all__ = [
    "AdaptiveThresholds",
    "Decision",
    "FailureMode",
    "PerceptionInputs",
    "PhysicalSignals",
    "ReasoningInputs",
    "TrendSnapshot",
    "decide",
]
