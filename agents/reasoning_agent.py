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
from services.failure_handling import detect_failures, detect_ood_escalation, detect_sensor_delta_failures

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
        # Model inputs plus the observed water-level ratio and BMKG scores the
        # signals, baseline and decision layers read (not model features).
        "features": _to_native({
            **features_df.iloc[0].to_dict(),
            **engineered.diagnostics.get("observed_context", {}),
        }),
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


def _siaga_int(level_str: str) -> int:
    """Convert 'siaga1'/'siaga2'/'siaga3' string to int 1/2/3; 0 for normal."""
    s = str(level_str or "").lower().strip()
    for n in (1, 2, 3, 4):
        if f"siaga{n}" == s or f"siaga {n}" == s:
            return n
    return 0


def _derive_risk_driver_from_stations(
    hydro,
    *,
    ml_driver: str,
    ood_flag: bool,
    bmkg_upstream: bool,
) -> str:
    """
    Derive dominant_risk_driver from actual station siaga levels.

    When OOD suppresses the ML model, the feature-derived driver is unreliable.
    This function uses the hydrology assessment (actual siaga states) as ground truth
    so the driver always reflects observable physical conditions, not model internals.
    """
    if hydro is None or not getattr(hydro, "stations", None):
        if ood_flag:
            return "ood_precautionary"
        return ml_driver

    stations = hydro.stations
    siaga1 = [s for s in stations if _siaga_int(s.siaga_level) == 1]
    siaga2 = [s for s in stations if _siaga_int(s.siaga_level) == 2]
    siaga3 = [s for s in stations if _siaga_int(s.siaga_level) == 3]

    if siaga1:
        return "critical_coastal_siaga1"
    if siaga2:
        coastal = any(
            "laut" in s.station_name.lower() or "coastal" in s.station_name.lower()
            for s in siaga2
        )
        return "coastal_tidal_siaga2" if coastal else "active_siaga2_stations"
    if len(siaga3) >= 3:
        return "multiple_siaga3_stations"
    if siaga3:
        return "active_siaga3_stations"
    if bmkg_upstream:
        return "upstream_bmkg_alert"
    if ood_flag:
        return "ood_precautionary"
    return ml_driver


def _generate_dynamic_risk_interpretation(
    hydro,
    *,
    ml_interpretation: str,
    ood_flag: bool,
    rain_1h: float,
    failure_modes: list,
) -> str:
    """
    Generate a risk interpretation that names actual elevated stations explicitly.

    Falls back to ml_interpretation when no stations are elevated, so the
    standard ML-derived narrative is still used for SAFE/PRE_ALERT conditions.
    """
    if hydro is None or not getattr(hydro, "stations", None):
        return ml_interpretation

    elevated = [
        s for s in hydro.stations
        if _siaga_int(s.siaga_level) in (1, 2, 3)
    ]
    if not elevated:
        return ml_interpretation

    # Sort by severity (siaga1 first, then 2, then 3) then by water level
    elevated_sorted = sorted(elevated, key=lambda s: (_siaga_int(s.siaga_level), -s.tinggi_air_cm))
    station_summary = ", ".join(
        f"{s.station_name} {s.tinggi_air_cm:.0f}cm (Siaga {_siaga_int(s.siaga_level)})"
        for s in elevated_sorted
    )

    if rain_1h > 0:
        rain_note = f"Rainfall: {rain_1h:.1f}mm/1h."
    else:
        rain_note = "No active rainfall — rise may indicate tidal influence or upstream drainage."

    ood_note = (
        " Model operating outside training distribution — rule engine primary."
        if ood_flag else ""
    )

    # For all Siaga 2 stations, show distance to Siaga 1 threshold explicitly.
    # Always uses tinggi_air_cm (current level) from StationAssessment — never tinggi_air_sebelumnya.
    siaga2_stations = [s for s in elevated if _siaga_int(s.siaga_level) == 2]
    threshold_notes: list[str] = []
    for s in siaga2_stations[:2]:
        siaga1_cm = s.thresholds.get("siaga1", 0.0)
        if siaga1_cm > 0:
            margin = int(siaga1_cm - s.tinggi_air_cm)
            threshold_notes.append(
                f"{s.station_name} at {s.tinggi_air_cm:.0f}cm, "
                f"{margin}cm below Siaga 1 threshold ({siaga1_cm:.0f}cm)"
            )

    # For Siaga 3 stations nearing Siaga 2, add escalation note.
    near_siaga2 = [s for s in elevated if _siaga_int(s.siaga_level) == 3 and s.near_threshold]
    for s in near_siaga2[:1]:
        next_cm = s.thresholds.get(s.next_siaga_level, 0.0)
        if next_cm > 0:
            threshold_notes.append(
                f"{s.station_name} at {s.tinggi_air_cm:.0f}cm, "
                f"{s.near_threshold_margin_cm:.0f}cm below {s.next_siaga_level.replace('siaga', 'Siaga ')} "
                f"threshold ({next_cm:.0f}cm)"
            )

    threshold_note = (" " + ". ".join(threshold_notes) + ".") if threshold_notes else ""

    return (
        f"{len(elevated)} station(s) elevated: {station_summary}. "
        f"{rain_note}{threshold_note} "
        f"Monitor for escalation toward Siaga 1 thresholds.{ood_note}"
    )


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
        sensor_anomalies = getattr(perception, "sensor_anomalies", []) or []
        total_stations = len(
            (perception.snapshot.get("poskobanjir") or [])
            if hasattr(perception, "snapshot")
            else []
        )
        failure_modes.extend(
            detect_sensor_delta_failures(sensor_anomalies, total_stations)
        )
        failure_modes.extend(detect_ood_escalation(ood_detection))

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

        # Override ML-derived driver with actual siaga station states.
        # When OOD suppresses the model, the feature-derived driver is unreliable;
        # the actual station siaga levels are the ground truth.
        hydro = getattr(perception, "hydrology_assessment", None)
        ood_flag = prediction.get("ood_detection", {}).get("is_outlier", False)
        bmkg_upstream = bool(getattr(perception, "bmkg_alerts", None))
        driver = _derive_risk_driver_from_stations(
            hydro, ml_driver=driver, ood_flag=ood_flag, bmkg_upstream=bmkg_upstream
        )
        signals["dominant_driver"] = driver

        context_summary = build_context_summary(
            features,
            diagnostics,
            prediction,
            baseline_result,
            plausibility_score=plausibility_score,
        )
        risk_interpretation = generate_risk_interpretation(signals, failure_modes)

        # Override interpretation dynamically when actual stations are elevated.
        # The ML feature-based interpretation may say "no flood indication" even
        # when siaga stations are active (OOD model cannot be trusted at such moments).
        rain_1h = float(features.get("rainfall_mm") or signals.get("_rainfall_mm") or 0.0)
        risk_interpretation = _generate_dynamic_risk_interpretation(
            hydro=hydro,
            ml_interpretation=risk_interpretation,
            ood_flag=ood_flag,
            rain_1h=rain_1h,
            failure_modes=failure_modes,
        )

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
