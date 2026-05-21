"""
ReasoningAgent — Stage 2 of the agentic flood decision pipeline.

Responsibility:
  - Run the realtime-native ML model on the current snapshot
  - Independently compute a rule-based baseline probability
  - Detect data/signal failures
  - Extract multi-condition risk signals
  - Generate an expert-style risk interpretation

Separates "what the model says" from "what the signals say" so the
EvaluationAgent can reconcile them with explicit trust accounting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from realtime_native.bundle import load_runtime_bundle
from realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_snapshot,
)
from services.adaptive_threshold import AdaptiveThresholder
from services.baseline_check import compare_with_baseline
from services.decision_logic import (
    build_context_summary,
    dominant_risk_driver,
    extract_signals,
    generate_risk_interpretation,
)
from services.failure_handling import detect_failures

if TYPE_CHECKING:
    from agents.perception_agent import PerceptionResult


def _to_native(value: Any) -> Any:
    """Recursively convert numpy scalars to Python built-ins for JSON safety."""
    if isinstance(value, dict):
        return {k: _to_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _base_confidence(probability: float, ood_score: float, thresholds: dict) -> float:
    """
    Compute initial model confidence before evaluation-stage trust adjustments.

    The margin term is anchored to the active runtime-native threshold ladder so
    confidence and final risk operate on one canonical boundary set.
    """
    boundaries = [
        float(thresholds["pre_alert"]),
        float(thresholds["warning"]),
        float(thresholds["danger"]),
    ]
    min_dist = min(abs(probability - boundary) for boundary in boundaries)
    ladder_span = max(0.01, float(thresholds["danger"]) - float(thresholds["pre_alert"]))
    margin_score = min(min_dist / ladder_span, 1.0)
    ood_confidence = max(0.0, min(1.0, (ood_score + 0.50) / 0.70))
    return round(margin_score * 0.60 + ood_confidence * 0.40, 4)


_OOD_FLOOR_DEFAULT = 0.6


def _outlier_capped_confidence(
    *,
    confidence: float,
    is_outlier: bool,
    model_card: dict,
) -> tuple[float, bool, float]:
    """
    Apply the model card's ``confidence_floor_on_outlier`` when the OOD
    detector flagged the input. Returns ``(capped_confidence, was_capped,
    floor)`` so the inference response can publish the lineage. Floor source
    is the LIVE model_card at every call — never hardcoded — so a re-export
    that updates the floor is honoured without a process restart.
    """
    if not is_outlier:
        return float(confidence), False, _OOD_FLOOR_DEFAULT
    try:
        floor = float(model_card.get("confidence_floor_on_outlier", _OOD_FLOOR_DEFAULT))
    except (TypeError, ValueError):
        floor = _OOD_FLOOR_DEFAULT
    floor = max(0.0, min(1.0, floor))
    if confidence <= floor:
        return float(confidence), False, floor
    return floor, True, floor


def _run_model(snapshot: dict, *, persist_history: bool = True, as_of=None) -> dict:
    """
    Execute the realtime-native model pipeline on a snapshot dict.

    ``persist_history`` toggles the temporal feature history append.
    ``as_of`` pins snapshot-history reads for deterministic replay.
    """
    bundle = load_runtime_bundle()

    engineered = build_realtime_native_features_from_snapshot(
        snapshot, persist_history=persist_history, as_of=as_of,
    )
    features_df = engineered.frame[REALTIME_NATIVE_FEATURES]
    scaled = bundle.scaler.transform(features_df)

    probability = float(bundle.model.predict_proba(scaled)[0, 1])
    ood_score = float(bundle.ood_detector.decision_function(scaled)[0])
    ood_is_outlier = bool(bundle.ood_detector.predict(scaled)[0] == -1)

    raw_confidence = _base_confidence(probability, ood_score, bundle.thresholds)
    capped_confidence, was_capped, floor = _outlier_capped_confidence(
        confidence=raw_confidence,
        is_outlier=ood_is_outlier,
        model_card=bundle.model_card,
    )

    return {
        "model_variant": "realtime_native",
        "probability": round(probability, 4),
        "confidence_score": round(capped_confidence, 4),
        "ood_detection": {
            "method": "IsolationForest",
            "score": round(ood_score, 4),
            "is_outlier": ood_is_outlier,
            # Audit trail: operators can see whether the published
            # confidence_score was the raw model output or capped by the
            # OOD floor, and which floor value was in effect at the time.
            "raw_confidence": round(raw_confidence, 4),
            "confidence_capped_by_ood_floor": was_capped,
            "confidence_floor_on_outlier": round(floor, 4),
        },
        "features": _to_native(features_df.iloc[0].to_dict()),
        "diagnostics": _to_native(engineered.diagnostics),
        "model_name": bundle.model_card.get(
            "model_name",
            "XGBoost Flood Predictor - Realtime Native",
        ),
    }


@dataclass
class ReasoningResult:
    """Structured output of ReasoningAgent. Passed directly to EvaluationAgent."""

    features: dict
    diagnostics: dict
    prediction: dict
    signals: dict
    dominant_driver: str
    context_summary: dict
    risk_interpretation: str
    failure_modes: list
    baseline_result: dict


class ReasoningAgent:
    """
    Stage 2: Reasoning.

    Orchestrates four independent sub-computations:
      1. ML model inference (realtime-native XGBoost + IsolationForest OOD)
      2. Rule-based baseline estimation (rainfall + hydro physical rules)
      3. Failure detection (missing data, signal conflicts, OOD)
      4. Multi-condition signal extraction and expert narrative generation
    """

    def run(
        self,
        perception: "PerceptionResult",
        *,
        persist_history: bool = True,
        as_of=None,
    ) -> ReasoningResult:
        prediction = _run_model(
            perception.snapshot, persist_history=persist_history, as_of=as_of,
        )
        features = prediction["features"]
        diagnostics = prediction["diagnostics"]
        model_prob = prediction["probability"]
        ood_detection = prediction["ood_detection"]

        baseline_result = compare_with_baseline(model_prob, features)

        failure_modes = detect_failures(
            snapshot=perception.snapshot,
            features=features,
            diagnostics=diagnostics,
            model_prob=model_prob,
            baseline_result=baseline_result,
            ood_detection=ood_detection,
            plausibility=getattr(perception, "plausibility", None),
            now=as_of,
        )

        trend_state: dict = diagnostics.get("trend_state") or {}
        plausibility_score: float = perception.plausibility_score
        adaptive_thresholds = AdaptiveThresholder().build_thresholds(
            failure_modes=failure_modes,
            trend_state=trend_state,
            plausibility_score=plausibility_score,
        )
        prediction["adaptive_classification"] = adaptive_thresholds.to_dict()

        signals = extract_signals(features, plausibility_score=plausibility_score)
        driver = dominant_risk_driver(features, plausibility_score=plausibility_score)
        signals["dominant_driver"] = driver

        context_summary = build_context_summary(
            features,
            diagnostics,
            prediction,
            baseline_result,
            plausibility_score=plausibility_score,
        )
        risk_interpretation = generate_risk_interpretation(signals, failure_modes)

        return ReasoningResult(
            features=features,
            diagnostics=diagnostics,
            prediction=prediction,
            signals=signals,
            dominant_driver=driver,
            context_summary=context_summary,
            risk_interpretation=risk_interpretation,
            failure_modes=failure_modes,
            baseline_result=baseline_result,
        )
