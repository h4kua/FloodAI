"""
Centralized automation-confidence calculation.

This module is the sole authority for modifying confidence_score on the live
agentic path. It composes independent factors deterministically so the score
does not collapse from stacked penalties applied in multiple layers.
"""

from __future__ import annotations

from dataclasses import dataclass


_OOD_PENALTIES = {
    "INLIER": 0.00,
    "BORDERLINE": 0.05,
    "ANOMALOUS": 0.10,
    "SEVERE_ANOMALOUS": 0.20,
}


@dataclass(frozen=True)
class OODAssessment:
    state: str
    penalty: float
    raw_score: float
    is_outlier: bool


@dataclass(frozen=True)
class ConfidenceResult:
    score: float
    model_confidence: float
    data_quality: float
    signal_agreement: float
    sensor_reliability: float
    ood_state: str
    ood_penalty: float

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "model_confidence": self.model_confidence,
            "data_quality": self.data_quality,
            "signal_agreement": self.signal_agreement,
            "sensor_reliability": self.sensor_reliability,
            "ood_state": self.ood_state,
            "ood_penalty": self.ood_penalty,
        }


def classify_ood_state(ood_detection: dict | None) -> OODAssessment:
    payload = ood_detection or {}
    raw_score = float(payload.get("score") or 0.0)
    is_outlier = bool(payload.get("is_outlier"))

    if not is_outlier and raw_score >= 0.05:
        return OODAssessment("INLIER", _OOD_PENALTIES["INLIER"], raw_score, False)
    if not is_outlier and raw_score >= -0.05:
        return OODAssessment("BORDERLINE", _OOD_PENALTIES["BORDERLINE"], raw_score, False)
    if raw_score >= -0.15:
        return OODAssessment("ANOMALOUS", _OOD_PENALTIES["ANOMALOUS"], raw_score, is_outlier)
    return OODAssessment(
        "SEVERE_ANOMALOUS",
        _OOD_PENALTIES["SEVERE_ANOMALOUS"],
        raw_score,
        is_outlier,
    )


def compute_sensor_reliability(perception, failure_modes: list[dict]) -> float:
    """
    Deterministic sensor-health estimate derived from live snapshot structure.

    Absence of a BMKG alert is not a reliability issue; absence of the alert
    section itself is already captured in completeness/failure handling.
    """
    signal_presence = getattr(perception, "signal_presence", {}) or {}
    plausibility = getattr(perception, "plausibility", {}) or {}
    freshness = float(getattr(perception, "data_freshness_minutes", -1.0))

    reliability = 1.0
    if not signal_presence.get("has_temperature"):
        reliability -= 0.08
    if not signal_presence.get("has_humidity"):
        reliability -= 0.08
    if not (signal_presence.get("has_rainfall_1h") or signal_presence.get("has_rainfall_3h")):
        reliability -= 0.10
    if not signal_presence.get("has_water_levels"):
        reliability -= 0.18
    if freshness < 0:
        reliability -= 0.10
    elif freshness > 60:
        reliability -= 0.15
    elif freshness > 30:
        reliability -= 0.08

    if plausibility.get("has_critical_violation"):
        reliability -= 0.35

    if any(f.get("type") == "external_source_unreliable" for f in failure_modes):
        reliability -= 0.20

    return round(max(0.05, min(1.0, reliability)), 4)


def compute_automation_confidence(
    *,
    model_confidence: float,
    data_quality: float,
    signal_agreement: float,
    sensor_reliability: float,
    ood_assessment: OODAssessment,
) -> ConfidenceResult:
    score = (
        0.40 * _clamp01(model_confidence)
        + 0.20 * _clamp01(data_quality)
        + 0.20 * _clamp01(signal_agreement)
        + 0.20 * _clamp01(sensor_reliability)
        - ood_assessment.penalty
    )
    score = round(min(0.98, max(0.05, score)), 4)
    return ConfidenceResult(
        score=score,
        model_confidence=round(_clamp01(model_confidence), 4),
        data_quality=round(_clamp01(data_quality), 4),
        signal_agreement=round(_clamp01(signal_agreement), 4),
        sensor_reliability=round(_clamp01(sensor_reliability), 4),
        ood_state=ood_assessment.state,
        ood_penalty=round(ood_assessment.penalty, 4),
    )


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
