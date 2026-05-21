from __future__ import annotations

from domain import AdaptiveThresholds
from services.adaptive_threshold import AdaptiveThresholder
from services.decision_engine import (
    _build_canonical_inputs,
    _canonical_default_thresholds,
)


def test_adaptive_thresholder_returns_thresholds_only() -> None:
    payload = AdaptiveThresholder().build_thresholds(
        failure_modes=[{"type": "signal_conflict"}],
        trend_state={
            "risk_trend": "increasing",
            "trend_strength": 0.50,
            "trend_confidence": 0.80,
            "anomaly_detected": True,
            "anomaly_type": "spike",
            "risk_rate_per_hour": 0.08,
        },
        plausibility_score=0.95,
    ).to_dict()

    # Threshold unification (audit C1 — SSOT): base pre_alert is now sourced
    # from _canonical_default_thresholds() rather than the removed legacy 0.20
    # literal; the assertion follows the canonical helper too.
    canonical_pre_alert, _, _ = _canonical_default_thresholds()
    assert "risk_level" not in payload
    assert payload["pre_alert_threshold"] == canonical_pre_alert
    assert payload["warning_threshold"] <= payload["danger_threshold"]
    assert payload["classification_basis"] == payload["threshold_basis"]


def test_build_canonical_inputs_prefers_explicit_threshold_triplet() -> None:
    result = _build_canonical_inputs(
        {
            "signals": {"rainfall_mm": 0.0, "bmkg_severity": 0.0},
            "diagnostics": {"trend_state": {}},
            "adaptive_classification": {
                "pre_alert_threshold": 0.22,
                "warning_threshold": 0.34,
                "danger_threshold": 0.51,
                "effective_danger_threshold": 0.45,
            },
            "hydrology_assessment": None,
            "plausibility_score": 0.9,
            "has_critical_violation": False,
            "probability": 0.3,
            "adjusted_confidence": 0.8,
            "failure_modes": [],
        }
    )

    thresholds = result["thresholds"]
    assert isinstance(thresholds, AdaptiveThresholds)
    assert thresholds.pre_alert == 0.22
    assert thresholds.warning == 0.34
    assert thresholds.danger == 0.51
