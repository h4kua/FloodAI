"""
Failure detection and system-integrity checks.

Failures are structurally distinct from model uncertainty — they represent
problems with the data pipeline or signal coherence that must be surfaced
explicitly so operators can decide whether to trust the output.

Each failure record contains a `confidence_penalty` that the EvaluationAgent
applies to the raw model confidence score.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.plausibility_check import plausibility_failure_record, sensor_fault_failure_record
from services.constants import (
    BMKG_CERTAINTY_WEIGHTS,
    BMKG_SEVERITY_WEIGHTS,
    BMKG_URGENCY_WEIGHTS,
)

# Data older than 30 minutes is stale for Jakarta flood operations.
# Flood events in Jakarta's low-lying areas develop within 20–30 minutes
# of extreme rainfall onset, so 30 min is the maximum acceptable latency.
DATA_STALENESS_THRESHOLD_MINUTES = 30.0

# BMKG weighted score considered "active" (not just background noise).
BMKG_ACTIVE_MIN = 0.50
# Rainfall below this is effectively zero at sensor resolution.
RAINFALL_NEAR_ZERO_MM = 1.0

# Rolling-mean threshold above which we expect a hydro response.
RAINFALL_ROLL3_HYDRO_RESPONSE = 25.0
# If rain is sustained but water level is very low, spatial mismatch is likely.
WATER_RATIO_LOW = 0.20

# Water rises without rain above this rate = upstream or tidal anomaly.
WATER_DELTA_ANOMALOUS = 0.15

# Gap between model probability and rule-based baseline that triggers conflict flag.
MODEL_BASELINE_GAP_CONFLICT = 0.30


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _raw_bmkg_weighted_score(snapshot: dict) -> float:
    weighted_total = 0.0
    for alert in snapshot.get("bmkg_alerts") or []:
        severity = BMKG_SEVERITY_WEIGHTS.get((alert.get("severity") or "").lower(), 0.4)
        certainty = BMKG_CERTAINTY_WEIGHTS.get((alert.get("certainty") or "").lower(), 0.4)
        urgency = BMKG_URGENCY_WEIGHTS.get((alert.get("urgency") or "").lower(), 0.5)
        weighted_total += severity * certainty * urgency
    return min(weighted_total, 1.0)


def _fallback_conflict_features(snapshot: dict, features: dict) -> dict:
    openweather = snapshot.get("openweather") or {}
    rain = openweather.get("rain") or {}
    poskobanjir = snapshot.get("poskobanjir") or []

    rainfall_mm = _safe_float(features.get("rainfall_mm"))
    if rainfall_mm <= 0.0:
        rainfall_mm = max(
            _safe_float(rain.get("1h")),
            _safe_float(rain.get("3h")) / 3.0,
        )

    rainfall_roll3_mean = _safe_float(features.get("rainfall_roll3_mean"))
    if rainfall_roll3_mean <= 0.0:
        rainfall_roll3_mean = rainfall_mm

    bmkg_weighted_score = _safe_float(features.get("bmkg_weighted_score"))
    if bmkg_weighted_score <= 0.0:
        bmkg_weighted_score = _raw_bmkg_weighted_score(snapshot)

    water_level_ratio = _safe_float(features.get("water_level_ratio"))
    if water_level_ratio <= 0.0:
        ratios: list[float] = []
        for record in poskobanjir:
            current = _safe_float(record.get("tinggi_air"))
            thresholds = [
                _safe_float(record.get("siaga1")),
                _safe_float(record.get("siaga2")),
                _safe_float(record.get("siaga3")),
                _safe_float(record.get("siaga4")),
            ]
            thresholds = [threshold for threshold in thresholds if threshold > 0.0]
            if thresholds:
                ratios.append(current / max(thresholds))
        water_level_ratio = max(ratios, default=0.0)

    return {
        **features,
        "rainfall_mm": rainfall_mm,
        "rainfall_roll3_mean": rainfall_roll3_mean,
        "bmkg_weighted_score": bmkg_weighted_score,
        "water_level_ratio": water_level_ratio,
    }


def snapshot_missing_or_stale(snapshot: dict, *, now: "datetime | None" = None) -> list[dict]:
    """
    Check snapshot timestamp and required section completeness.

    ``now`` (optional) pins the reference clock used for staleness comparison
    so identical replays produce identical failure_modes.

    Returns a list of failure dicts — empty list if everything is healthy.
    """
    failures: list[dict] = []
    ref_now = now if now is not None else datetime.now(timezone.utc)

    # ── Timestamp / freshness ────────────────────────────────────────────────
    fetched_at = snapshot.get("fetched_at_utc")
    if fetched_at is None:
        failures.append(
            {
                "type": "missing_data",
                "severity": "high",
                "message": (
                    "Snapshot lacks fetched_at_utc timestamp — "
                    "data currency cannot be verified."
                ),
                "confidence_penalty": 0.15,
                "risk_escalation": False,
                "detail": {"field": "fetched_at_utc", "value": None},
            }
        )
    else:
        try:
            snapshot_dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
            age_minutes = (ref_now - snapshot_dt).total_seconds() / 60.0
            if age_minutes > DATA_STALENESS_THRESHOLD_MINUTES:
                # Penalty scales linearly up to 0.20 at 150 minutes, then caps.
                penalty = round(min(0.20, age_minutes / 150.0), 4)
                failures.append(
                    {
                        "type": "stale_data",
                        "severity": "medium" if age_minutes < 60 else "high",
                        "message": (
                            f"Snapshot is {age_minutes:.1f} min old — exceeds "
                            f"{DATA_STALENESS_THRESHOLD_MINUTES:.0f}-min freshness threshold."
                        ),
                        "confidence_penalty": penalty,
                        "risk_escalation": False,
                        "detail": {
                            "age_minutes": round(age_minutes, 1),
                            "threshold_minutes": DATA_STALENESS_THRESHOLD_MINUTES,
                        },
                    }
                )
        except (ValueError, TypeError):
            failures.append(
                {
                    "type": "missing_data",
                    "severity": "medium",
                    "message": (
                        f"Cannot parse fetched_at_utc '{fetched_at}' — staleness check skipped."
                    ),
                    "confidence_penalty": 0.10,
                    "risk_escalation": False,
                    "detail": {"field": "fetched_at_utc", "value": str(fetched_at)},
                }
            )

    # ── Required sections ────────────────────────────────────────────────────
    required: dict[str, tuple[str, float]] = {
        "openweather": ("OpenWeather weather data", 0.10),
        "poskobanjir": ("Posko Banjir water-level records", 0.10),
        "bmkg_alerts": ("BMKG meteorological alerts", 0.05),
    }
    for key, (label, penalty) in required.items():
        section = snapshot.get(key)
        if section is None:
            failures.append(
                {
                    "type": "missing_data",
                    "severity": "high",
                    "message": f"Snapshot missing required section '{key}' ({label}).",
                    "confidence_penalty": penalty,
                    "risk_escalation": False,
                    "detail": {"section": key},
                }
            )
        elif isinstance(section, list) and len(section) == 0:
            failures.append(
                {
                    "type": "missing_data" if key != "bmkg_alerts" else "bmkg_detail_unavailable",
                    "severity": "low" if key == "bmkg_alerts" else "medium",
                    "message": (
                        f"BMKG detail fetch failed — alert details unavailable. "
                        f"bmkg_feed may contain raw feed items."
                        if key == "bmkg_alerts"
                        else f"Section '{key}' is empty — {label} unavailable."
                    ),
                    "confidence_penalty": round(penalty / 2, 4),
                    "risk_escalation": False,
                    "detail": {"section": key, "count": 0},
                }
            )

    # ── Core weather fields ──────────────────────────────────────────────────
    main = (snapshot.get("openweather") or {}).get("main") or {}
    if not main.get("temp") and not main.get("humidity"):
        failures.append(
            {
                "type": "missing_data",
                "severity": "medium",
                "message": (
                    "OpenWeather 'main' block missing temperature and humidity — "
                    "atmospheric assessment is incomplete."
                ),
                "confidence_penalty": 0.08,
                "risk_escalation": False,
                "detail": {"section": "openweather.main"},
            }
        )

    return failures


def conflicting_signals(
    features: dict,
    diagnostics: dict,
    model_prob: float,
    baseline_result: dict,
) -> list[dict]:
    """
    Detect physically implausible or contradictory signal combinations.

    Conflicts don't prove the data is wrong — they mean the system cannot
    distinguish between a sensor gap, a forecast-vs-observed discrepancy,
    or a genuinely complex meteorological event.
    """
    failures: list[dict] = []

    rf = features.get("rainfall_mm", 0.0) or 0.0
    bwt = features.get("bmkg_weighted_score", 0.0) or 0.0
    wrat = features.get("water_level_ratio", 0.0) or 0.0
    wdelta = features.get("water_level_delta", 0.0) or 0.0
    roll3 = features.get("rainfall_roll3_mean", 0.0) or 0.0

    # Conflict 1: BMKG extreme but near-zero observed rainfall.
    # Possible causes: forecast-only alert, localized cell, or missing rain gauge.
    if bwt > BMKG_ACTIVE_MIN and rf < RAINFALL_NEAR_ZERO_MM:
        failures.append(
            {
                "type": "signal_conflict",
                "severity": "medium",
                "message": (
                    f"BMKG weighted score {bwt:.2f} indicates an active alert, "
                    f"but observed rainfall is {rf:.1f} mm/h (near zero). "
                    "Possible: forecast-only alert, localized cell, or missing rain-gauge data."
                ),
                "confidence_penalty": 0.12,
                "risk_escalation": False,
                "detail": {"bmkg_weighted": bwt, "rainfall_mm": rf},
            }
        )

    # Conflict 2: Sustained heavy rainfall with no hydro response.
    # Could indicate spatial mismatch between rain gauge and water station.
    if roll3 > RAINFALL_ROLL3_HYDRO_RESPONSE and wrat < WATER_RATIO_LOW:
        failures.append(
            {
                "type": "signal_conflict",
                "severity": "low",
                "message": (
                    f"Sustained heavy rainfall (3h mean {roll3:.1f} mm) without a "
                    f"corresponding water-level response (ratio {wrat:.2f}). "
                    "Possible: spatial mismatch, functioning drainage, or sensor not in flood zone."
                ),
                "confidence_penalty": 0.08,
                "risk_escalation": False,
                "detail": {"rainfall_roll3_mean": roll3, "water_level_ratio": wrat},
            }
        )

    # Conflict 3: Rapid water rise without active rainfall.
    # risk_escalation=True: rising water without rain may signal upstream dam release
    # or tidal backflow — operationally important even if model says SAFE.
    if wdelta > WATER_DELTA_ANOMALOUS and rf < RAINFALL_NEAR_ZERO_MM:
        failures.append(
            {
                "type": "signal_conflict",
                "severity": "high",
                "message": (
                    f"Water level rising rapidly (Δ{wdelta:.2f}/step) without active rainfall. "
                    "Possible: upstream surge, tidal backflow, drainage blockage, or sensor drift."
                ),
                "confidence_penalty": 0.10,
                "risk_escalation": True,
                "detail": {"water_level_delta": wdelta, "rainfall_mm": rf},
            }
        )

    # Conflict 4: Large gap between ML model and rule-based baseline.
    baseline_prob = baseline_result.get("baseline_probability")
    baseline_gap = baseline_result.get("baseline_disagreement", 0.0)
    if baseline_prob is not None and baseline_gap > MODEL_BASELINE_GAP_CONFLICT:
        direction = "higher" if model_prob > baseline_prob else "lower"
        # Only escalate when baseline signals danger but model says safe.
        escalate = baseline_result.get("baseline_alert", False) and model_prob < 0.40
        failures.append(
            {
                "type": "signal_conflict",
                "severity": "high" if baseline_gap > 0.30 else "medium",
                "message": (
                    f"Model probability ({model_prob:.2f}) is {direction} than the "
                    f"rule-based baseline ({baseline_prob:.2f}) by {baseline_gap:.2f}. "
                    "Manual review required before operational action."
                ),
                "confidence_penalty": 0.15,
                "risk_escalation": escalate,
                "detail": {
                    "model_prob": model_prob,
                    "baseline_prob": baseline_prob,
                    "gap": baseline_gap,
                },
            }
        )

    return failures


def detect_ood_failures(ood_detection: dict) -> list[dict]:
    """
    Convert IsolationForest OOD output into a failure record.

    Separated from conflicting_signals because OOD comes from model inference,
    not from the snapshot or baseline comparison.
    """
    if not ood_detection.get("is_outlier"):
        return []

    ood_score = ood_detection.get("score", 0.0)
    # OOD input is always HIGH — model reliability is compromised regardless of score magnitude.
    severity = "high"
    return [
        {
            "type": "ood_input",
            "severity": severity,
            "message": (
                f"Input features flagged as out-of-distribution by IsolationForest "
                f"(score={ood_score:.3f}). Model was not trained on conditions resembling "
                "the current observation."
            ),
            "confidence_penalty": 0.12,
            "risk_escalation": False,
            "detail": {"ood_score": ood_score, "method": "IsolationForest"},
        }
    ]


def detect_failures(
    snapshot: dict,
    features: dict,
    diagnostics: dict,
    model_prob: float,
    baseline_result: dict,
    ood_detection: dict,
    plausibility: dict | None = None,
    *,
    now: "datetime | None" = None,
) -> list[dict]:
    """
    Master failure detection — aggregates all failure types into one list.

    Each record includes a `confidence_penalty` for downstream confidence adjustment
    and a `risk_escalation` flag that can override the model's risk_level.

    ``now`` (optional) is threaded into time-comparison checks so identical
    replays produce identical failure_modes.
    """
    failures: list[dict] = []
    failures.extend(snapshot_missing_or_stale(snapshot, now=now))
    plausibility_failure = (
        plausibility_failure_record(plausibility)
        if isinstance(plausibility, dict)
        else None
    )
    if plausibility_failure is not None:
        failures.append(plausibility_failure)
    sensor_fault = (
        sensor_fault_failure_record(plausibility)
        if isinstance(plausibility, dict)
        else None
    )
    if sensor_fault is not None:
        failures.append(sensor_fault)
    failures.extend(
        conflicting_signals(
            _fallback_conflict_features(snapshot, features),
            diagnostics,
            model_prob,
            baseline_result,
        )
    )
    failures.extend(detect_ood_failures(ood_detection))
    return failures


_MASS_FAULT_FRACTION = 0.50


_OOD_ESCALATION_MODERATE = -0.05  # L1.9 moderate tier (PRE_ALERT floor)
_OOD_ESCALATION_SEVERE = -0.10    # L1.9 severe tier (WARNING floor)


def detect_ood_escalation(ood_detection: dict) -> list[dict]:
    """
    Return an ood_escalation failure record when the IsolationForest score
    crosses the moderate (-0.05) or severe (-0.10) threshold.

    Distinct from detect_ood_failures() (binary is_outlier flag): this function
    uses the continuous score so partial OOD states are captured. The failure
    record is for operator transparency only — the actual risk floor and
    confidence cap are enforced by L1.9 in domain/decision.py.
    """
    payload = ood_detection or {}
    score = float(payload.get("score", 0.0))

    if score >= _OOD_ESCALATION_MODERATE:
        return []

    tier = "severe" if score < _OOD_ESCALATION_SEVERE else "moderate"
    floor_label = "WARNING" if tier == "severe" else "PRE_ALERT"
    return [
        {
            "type": "ood_escalation",
            "severity": "high",
            "message": (
                f"OOD {tier} (IsolationForest score={score:.3f}): model is operating "
                f"outside its training distribution. "
                f"Risk floor {floor_label} applied; confidence capped."
            ),
            "confidence_penalty": 0.0,
            "risk_escalation": False,
            "detail": {"ood_score": score, "tier": tier, "floor": floor_label},
        }
    ]


def detect_sensor_delta_failures(
    sensor_anomalies: list[dict],
    total_stations: int,
) -> list[dict]:
    """
    Return a HIGH failure record when >50% of stations have implausible
    water-level deltas (rate-of-change spike). Returns an empty list otherwise.

    Called after detect_failures() in ReasoningAgent so the HIGH record
    is included in failure_modes before EvaluationAgent applies penalties.
    """
    if not sensor_anomalies or total_stations == 0:
        return []

    fraction = len(sensor_anomalies) / total_stations
    if fraction <= _MASS_FAULT_FRACTION:
        return []

    anomalous_ids = [a.get("station", "?") for a in sensor_anomalies]
    return [
        {
            "type": "mass_sensor_failure",
            "severity": "high",
            "message": (
                f"{len(sensor_anomalies)}/{total_stations} stations "
                f"({100 * fraction:.0f}%) report implausible water-level deltas. "
                "Confidence degraded; output requires manual review."
            ),
            "confidence_penalty": 0.15,
            "risk_escalation": False,
            "detail": {
                "affected_stations": anomalous_ids,
                "anomaly_count": len(sensor_anomalies),
                "total_stations": total_stations,
                "fraction": round(fraction, 4),
                "sensor_anomalies": sensor_anomalies,
            },
        }
    ]


def compute_confidence_penalty(failures: list[dict]) -> float:
    """
    Sum all confidence penalties from detected failures.

    Capped at 0.45 so confidence never collapses to zero from data issues
    alone — the model's inherent signal still contributes to the score.
    """
    total = sum(f.get("confidence_penalty", 0.0) for f in failures)
    return round(min(total, 0.45), 4)


def has_risk_escalation(failures: list[dict]) -> bool:
    """True if any failure requires the final risk_level to be escalated."""
    return any(f.get("risk_escalation", False) for f in failures)


# ── Physical danger thresholds for multi-channel escalation check ─────────────
_ESCALATION_RAIN_MM = 50.0
_ESCALATION_BMKG_SCORE = 0.70
_ESCALATION_WATER_RATIO = 0.85
_ESCALATION_PLAUSIBILITY_MIN = 0.50


def has_danger_escalation(
    signals: dict,
    features: dict,
    plausibility_score: float,
) -> bool:
    """
    Physical safety override: force DANGER when 2+ independent hazard
    channels are simultaneously extreme AND input is physically plausible.

    Layer 2 of the two-layer DANGER detection approach. Layer 1
    (adaptive_threshold.py) lowers the probability threshold based on
    context; Layer 2 fires regardless of probability when raw physical
    signals are unambiguously extreme.

    Hazard channels:
      - Extreme rainfall: max_rainfall >= 50 mm
      - Extreme BMKG signal: bmkg_weighted_score >= 0.70
      - High water levels: water_level_ratio >= 0.85
    """
    if plausibility_score < _ESCALATION_PLAUSIBILITY_MIN:
        return False

    max_rain = float(features.get("max_rainfall") or signals.get("max_rainfall") or 0.0)
    bmkg = float(
        features.get("bmkg_weighted_score")
        or signals.get("bmkg_weighted_score")
        or 0.0
    )
    water_ratio = float(
        features.get("water_level_ratio")
        or signals.get("water_level_ratio")
        or 0.0
    )

    active_channels = sum([
        max_rain >= _ESCALATION_RAIN_MM,
        bmkg >= _ESCALATION_BMKG_SCORE,
        water_ratio >= _ESCALATION_WATER_RATIO,
    ])
    return active_channels >= 2
