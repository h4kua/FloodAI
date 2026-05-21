"""
Trust modeling — formal composition of system reliability scores.

Motivation:
  The existing system uses a single `confidence_score` that collapses
  multiple independent trust signals into one number, making it impossible
  for operators to understand WHICH factor degraded trust. This module
  formalises trust into three independent factors so that the breakdown
  is fully explainable and actionable.

Three trust factors (weights sum to 1.0):
  1. model_confidence  (0.45) — ML model's self-assessment of decision boundary margin
  2. data_quality      (0.35) — snapshot completeness × freshness, penalised by failures
  3. signal_agreement  (0.20) — coherence between ML model and rule-based baseline

Composite trust < LOW_TRUST_THRESHOLD (0.35) → system cannot be trusted autonomously.

Design invariant:
  Each factor is independently interpretable. Operators see:
    "Trust degraded because data_quality=0.18 (stale + missing sections)"
  Rather than:
    "Confidence is 0.3" with no explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

# Factor weights — must sum to 1.0
_MODEL_CONFIDENCE_WEIGHT = 0.45
_DATA_QUALITY_WEIGHT = 0.35
_SIGNAL_AGREEMENT_WEIGHT = 0.20

# Composite trust below this → LOW_TRUST system status.
LOW_TRUST_THRESHOLD = 0.35

# Per-failure penalties applied to individual factors
_MISSING_DATA_HIGH_PENALTY = 0.10
_OOD_PENALTY = 0.18
_CONFLICT_PENALTY = 0.20
_GAP_AGREEMENT_FACTOR = 0.50   # Gap × factor → agreement reduction


@dataclass
class TrustBreakdown:
    """
    Explainable decomposition of the system's composite trust score.

    All fields are 0.0–1.0 floats. Serialisation-safe via to_dict().
    """
    model_confidence_factor: float   # ML model margin + OOD confidence
    data_quality_factor: float       # Completeness × freshness − failure penalties
    signal_agreement_factor: float   # Cross-check coherence between model and baseline
    composite_trust: float           # Weighted sum of all three factors
    is_low_trust: bool               # True if composite < LOW_TRUST_THRESHOLD
    dominant_trust_issue: str | None  # Weakest factor key, or None if all ≥ 0.50

    def to_dict(self) -> dict:
        return {
            "model_confidence_factor": self.model_confidence_factor,
            "data_quality_factor": self.data_quality_factor,
            "signal_agreement_factor": self.signal_agreement_factor,
            "composite_trust": self.composite_trust,
            "is_low_trust": self.is_low_trust,
            "dominant_trust_issue": self.dominant_trust_issue,
            "factor_weights": {
                "model_confidence": _MODEL_CONFIDENCE_WEIGHT,
                "data_quality": _DATA_QUALITY_WEIGHT,
                "signal_agreement": _SIGNAL_AGREEMENT_WEIGHT,
            },
        }


def compute_trust_breakdown(
    model_confidence: float,
    failure_modes: list[dict],
    baseline_result: dict,
    snapshot_completeness: float,
    data_freshness_minutes: float,
) -> TrustBreakdown:
    """
    Compute the three-factor trust breakdown from available pipeline signals.

    Args:
        model_confidence:       Raw model confidence from ReasoningAgent (0.0–1.0).
        failure_modes:          Failure records from failure_handling.detect_failures().
        baseline_result:        Rule-based baseline comparison from baseline_check.
        snapshot_completeness:  Fraction of expected data sections present (0.0–1.0).
        data_freshness_minutes: Age of the snapshot in minutes.
    """
    model_factor = _compute_model_factor(model_confidence, failure_modes)
    data_factor = _compute_data_quality_factor(
        snapshot_completeness, data_freshness_minutes, failure_modes
    )
    agreement_factor = _compute_signal_agreement_factor(failure_modes, baseline_result)

    composite = round(
        model_factor * _MODEL_CONFIDENCE_WEIGHT
        + data_factor * _DATA_QUALITY_WEIGHT
        + agreement_factor * _SIGNAL_AGREEMENT_WEIGHT,
        4,
    )

    factors = {
        "model_confidence": model_factor,
        "data_quality": data_factor,
        "signal_agreement": agreement_factor,
    }
    weakest = min(factors, key=lambda k: factors[k])
    dominant_issue = weakest if factors[weakest] < 0.50 else None

    return TrustBreakdown(
        model_confidence_factor=model_factor,
        data_quality_factor=data_factor,
        signal_agreement_factor=agreement_factor,
        composite_trust=composite,
        is_low_trust=composite < LOW_TRUST_THRESHOLD,
        dominant_trust_issue=dominant_issue,
    )


# ── Factor computation ────────────────────────────────────────────────────────

def _compute_model_factor(model_confidence: float, failure_modes: list[dict]) -> float:
    """
    Factor 1: Model self-confidence, penalised by OOD detection.

    OOD inputs invalidate the model's confidence estimate because the model
    was not trained on anything resembling the current observation — its
    probability output cannot be trusted even if numerically high.
    """
    base = min(0.95, max(0.0, model_confidence))  # Cap: no prediction is fully certain
    ood_count = sum(1 for f in failure_modes if f.get("type") == "ood_input")
    ood_penalty = min(ood_count * _OOD_PENALTY, 0.45)
    return round(max(0.0, base - ood_penalty), 4)


def _compute_data_quality_factor(
    completeness: float,
    freshness_minutes: float,
    failure_modes: list[dict],
) -> float:
    """
    Factor 2: Data quality = completeness × freshness − failure penalties.

    Freshness score decays with data age.
    High/critical missing-data, stale-data, and implausible-input failures
    each reduce this factor by _MISSING_DATA_HIGH_PENALTY.
    """
    freshness_score = _freshness_to_score(freshness_minutes)
    base = max(0.0, completeness) * freshness_score

    degrading_types = ("missing_data", "stale_data", "implausible_input")
    severe_count = sum(
        1 for f in failure_modes
        if f.get("type") in degrading_types
        and f.get("severity") in ("high", "critical")
    )
    penalty = min(severe_count * _MISSING_DATA_HIGH_PENALTY, 0.50)
    return round(max(0.0, base - penalty), 4)


def _compute_signal_agreement_factor(
    failure_modes: list[dict],
    baseline_result: dict,
) -> float:
    """
    Factor 3: Signal agreement between ML model and rule-based baseline.

    Each detected signal_conflict reduces agreement by _CONFLICT_PENALTY.
    The continuous baseline_disagreement gap further reduces it proportionally.
    """
    conflict_count = sum(1 for f in failure_modes if f.get("type") == "signal_conflict")
    baseline_gap = float(baseline_result.get("baseline_disagreement") or 0.0)

    conflict_penalty = min(conflict_count * _CONFLICT_PENALTY, 0.60)
    gap_penalty = min(baseline_gap * _GAP_AGREEMENT_FACTOR, 0.30)
    return round(max(0.0, 1.0 - conflict_penalty - gap_penalty), 4)


def _freshness_to_score(freshness_minutes: float) -> float:
    """Convert data age (minutes) to a 0.0–1.0 freshness quality score."""
    if freshness_minutes < 0:
        return 0.80    # Unknown age: conservative moderate penalty
    if freshness_minutes <= 10:
        return 1.00
    if freshness_minutes <= 30:
        return 0.90
    if freshness_minutes <= 60:
        return 0.70
    if freshness_minutes <= 120:
        return 0.50
    return 0.30


