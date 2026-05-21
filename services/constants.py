"""
Shared BMKG alert scoring weights used across both the legacy and agentic stacks.

These values encode BMKG Indonesia's severity/certainty/urgency taxonomy for
CAP-format weather alerts. Both realtime_adapter (legacy stack) and
feature_builder (realtime-native/agentic stack) must use identical weights so
risk scores are comparable across all three prediction endpoints.
"""

BMKG_SEVERITY_WEIGHTS: dict[str, float] = {
    "minor": 0.25,
    "moderate": 0.5,
    "severe": 0.8,
    "extreme": 1.0,
}

BMKG_CERTAINTY_WEIGHTS: dict[str, float] = {
    "possible": 0.35,
    "likely": 0.7,
    "observed": 1.0,
}

BMKG_URGENCY_WEIGHTS: dict[str, float] = {
    "future": 0.4,
    "expected": 0.75,
    "immediate": 1.0,
    "past": 0.2,
    "unknown": 0.5,
}
