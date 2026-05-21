"""
Multi-condition reasoning engine for flood risk interpretation.

Avoids single-point-of-failure reasoning — every decision traces multiple
physical mechanisms, not just a single risk_level label.
"""

from __future__ import annotations

# ─── Domain thresholds ────────────────────────────────────────────────────────
# BMKG Indonesia classifies ≥50 mm/h as "ekstrem" for urban flash-flood risk.
RAINFALL_EXTREME_MM = 50.0
# Jakarta drainage capacity degrades noticeably above ~20 mm/h.
RAINFALL_HIGH_MM = 20.0
# 3-point rolling mean >25 mm → soil approaching saturation.
RAINFALL_ROLL3_HIGH = 25.0

# Water-gate siaga thresholds: ratio >0.85 = near overflow (Posko Banjir standard).
WATER_LEVEL_CRITICAL = 0.85
WATER_LEVEL_HIGH = 0.65
# Rise rate >0.07/step signals inflow buildup; lowered from 0.10 for earlier detection.
WATER_DELTA_RISING = 0.07
WATER_DELTA_RAPID = 0.20

# BMKG weighted score = severity × certainty × urgency; >0.70 = confirmed extreme.
BMKG_EXTREME = 0.70
BMKG_MODERATE = 0.35

# Relative humidity >85% means atmosphere is near saturation — amplifies runoff.
HUMIDITY_SATURATION = 85.0

# Hydro-meteorological index empirical 95th percentile from bootstrap training data.
HMI_HIGH = 1.50


# Sensor-derived signals are suppressed when plausibility falls below this threshold.
# BMKG signals are always computed — they originate from an independent external
# agency (BMKG Indonesia) and are not affected by local sensor faults or OOD inputs.
_SENSOR_SIGNAL_TRUST_THRESHOLD = 0.40


def extract_signals(features: dict, plausibility_score: float = 1.0) -> dict:
    """
    Derive named boolean/scored risk signals from raw feature values.

    Each signal maps to a distinct physical flood mechanism so downstream
    agents reason about cause, not just correlation.

    plausibility_score gates sensor-derived signals. When it is below
    _SENSOR_SIGNAL_TRUST_THRESHOLD, rainfall and water-level signals are set
    to False so RoutingAgent does not build phantom flood zones from implausible
    inputs (e.g. a sensor reporting 650 mm/h or -45 °C). BMKG signals are always
    computed regardless of local plausibility — BMKG is an independent source.
    """
    rf = features.get("rainfall_mm", 0.0) or 0.0
    rf3h = features.get("rainfall_3h_proxy_mm", 0.0) or 0.0
    roll3 = features.get("rainfall_roll3_mean", 0.0) or 0.0
    humidity = features.get("humidity_pct", 0.0) or 0.0
    bwt = features.get("bmkg_weighted_score", 0.0) or 0.0
    bsev = features.get("bmkg_severity_score", 0.0) or 0.0
    bcert = features.get("bmkg_certainty_score", 0.0) or 0.0
    burgency = features.get("bmkg_urgency_score", 0.0) or 0.0
    wrat = features.get("water_level_ratio", 0.0) or 0.0
    wdelta = features.get("water_level_delta", 0.0) or 0.0
    hmi = features.get("hydro_meteorological_index", 0.0) or 0.0
    monsoon = bool(features.get("monsoon_season", 0))

    sensor_trusted = plausibility_score >= _SENSOR_SIGNAL_TRUST_THRESHOLD

    return {
        # ── Rainfall-driven (suppressed when sensor not trusted) ─────────────
        "extreme_rainfall": sensor_trusted and (rf > RAINFALL_EXTREME_MM or rf3h > 100.0),
        "high_rainfall": sensor_trusted and (rf > RAINFALL_HIGH_MM or roll3 > RAINFALL_ROLL3_HIGH),
        "sustained_rainfall": sensor_trusted and (roll3 > 15.0 and rf > 5.0),
        # ── Hydrology-driven (suppressed when sensor not trusted) ────────────
        "critical_water_level": sensor_trusted and wrat > WATER_LEVEL_CRITICAL,
        "high_water_level": sensor_trusted and wrat > WATER_LEVEL_HIGH,
        "rising_water": sensor_trusted and wdelta > WATER_DELTA_RISING,
        "rapid_rise": sensor_trusted and wdelta > WATER_DELTA_RAPID,
        "hydro_stress": sensor_trusted and (wrat > WATER_LEVEL_HIGH and wdelta > 0.05),
        # ── BMKG alert-driven (always computed — external independent source) ─
        "bmkg_extreme": bwt > BMKG_EXTREME,
        "bmkg_moderate": bwt > BMKG_MODERATE,
        "bmkg_confirmed": bcert > 0.70 and burgency > 0.70,
        # ── Composite (sensor component also gated) ──────────────────────────
        "compound_risk": sensor_trusted and (
            rf > RAINFALL_HIGH_MM and wrat > WATER_LEVEL_HIGH and bwt > BMKG_MODERATE
        ),
        "atmosphere_saturated": sensor_trusted and humidity > HUMIDITY_SATURATION,
        "monsoon_context": monsoon,
        "hmi_high": sensor_trusted and hmi > HMI_HIGH,
        # ── Momentum / early-trend signals (computed from existing feature vector) ──
        # rainfall_trend = current - lag1 (positive = intensifying).
        # Lag values come from feature_builder history; safe, no leakage.
        "rainfall_trend_rising": sensor_trusted and (rf - (features.get("rainfall_lag_1") or rf)) > 8.0,
        "pre_alert_trending": sensor_trusted and (
            (rf - (features.get("rainfall_lag_1") or rf)) > 5.0
            and wdelta > 0.05
            and humidity > 80.0
        ),
        "consistent_buildup": sensor_trusted and (
            roll3 > 10.0 and wdelta > 0.03 and humidity > 72.0
        ),
        # ── Raw scalars (prefixed _ so ActionAgent strips them from public output) ─
        "_rainfall_mm": rf,
        "_water_level_ratio": wrat,
        "_water_delta": wdelta,
        "_bmkg_weighted": bwt,
        # Raw max BMKG severity weight (0.8 for "Severe", 1.0 for "Extreme") —
        # distinct from _bmkg_weighted, which multiplies by certainty/urgency
        # and so dilutes a Severe alert with non-Observed/non-Immediate metadata.
        # Consumed by decision_engine._build_canonical_inputs to drive the L1.7
        # BMKG_SAFETY_FLOOR floor on the raw severity scale, not the product.
        "_bmkg_severity": bsev,
        "_humidity": humidity,
        "_hmi": hmi,
        "_roll3": roll3,
        "_sensor_trusted": sensor_trusted,
    }


def dominant_risk_driver(features: dict, plausibility_score: float = 1.0) -> str:
    """
    Identify which physical subsystem is the primary flood driver.

    Priority (most → least dangerous):
      compound > critical_hydrology > hydrology_stress > bmkg_confirmed
      > extreme_rainfall > sustained_rain > bmkg_forecast > high_rain
      > atmospheric > background

    Compound events top the ladder because multi-hazard overlap is
    exponentially more dangerous than any single mechanism.

    plausibility_score is forwarded to extract_signals so the driver label
    reflects the same gated signals used during classification.
    """
    s = extract_signals(features, plausibility_score=plausibility_score)

    if s["compound_risk"]:
        return "compound_event"
    if s["critical_water_level"]:
        return "critical_hydrology"
    if s["hydro_stress"]:
        return "hydrology_stress"
    if s["bmkg_extreme"] and s["bmkg_confirmed"]:
        return "bmkg_confirmed_alert"
    if s["extreme_rainfall"]:
        return "extreme_rainfall"
    if s["high_rainfall"] and s["sustained_rainfall"]:
        return "sustained_heavy_rainfall"
    if s["bmkg_extreme"]:
        return "bmkg_forecast_alert"
    if s["high_rainfall"]:
        return "high_rainfall"
    if s["bmkg_moderate"] or s["atmosphere_saturated"]:
        return "atmospheric_buildup"
    return "low_background_risk"


def generate_risk_interpretation(signals: dict, failures: list[dict]) -> str:
    """
    Produce expert-style risk narrative from multi-signal context.

    Output reads like a hydrologist's field note, not a template alert.
    Failure context is appended when data quality is degraded.
    """
    failure_types = {f.get("type") for f in failures}
    driver = signals.get("dominant_driver", "low_background_risk")
    parts: list[str] = []

    if driver == "compound_event":
        parts.append(
            "Compound event detected: concurrent extreme rainfall, elevated water level, "
            "and official BMKG alerts are mutually reinforcing. Multi-hazard overlap "
            "elevates actual flood risk well beyond any single indicator threshold."
        )
    elif driver == "critical_hydrology":
        wrat = signals.get("_water_level_ratio", 0.0)
        parts.append(
            f"Water level critically elevated (ratio {wrat:.2f}), approaching or exceeding "
            "the operational overflow threshold. Even moderate additional rainfall may trigger "
            "inundation — hydrological buffer is nearly exhausted."
        )
    elif driver == "hydrology_stress":
        wdelta = signals.get("_water_delta", 0.0)
        wrat = signals.get("_water_level_ratio", 0.0)
        parts.append(
            f"Hydrological stress active: water level rising at Δ{wdelta:.2f}/step "
            f"with current ratio {wrat:.2f}. Rising trend under ongoing rainfall accumulation "
            "indicates increasing flood potential within the next 1–2 observation cycles."
        )
    elif driver == "bmkg_confirmed_alert":
        parts.append(
            "BMKG official alert confirmed with high certainty and immediate urgency. "
            "This represents an operationally significant warning from the national "
            "meteorological agency, indicating observed or imminent severe weather."
        )
    elif driver == "extreme_rainfall":
        rf = signals.get("_rainfall_mm", 0.0)
        parts.append(
            f"Extreme rainfall ({rf:.1f} mm/h) exceeds the 50 mm/h BMKG threshold "
            "associated with flash-flood risk in Jakarta's urban drainage system. "
            "Surface runoff generation likely outpaces drainage capacity at this intensity."
        )
    elif driver == "sustained_heavy_rainfall":
        roll = signals.get("_roll3", 0.0)
        parts.append(
            f"Sustained heavy rainfall (rolling mean {roll:.1f} mm) is progressively "
            "saturating soil and increasing surface runoff across multiple observation "
            "intervals. Cumulative loading elevates risk beyond any single-reading assessment."
        )
    elif driver == "bmkg_forecast_alert":
        parts.append(
            "BMKG forecast alert is active but certainty and urgency are not yet fully "
            "confirmed by observed indicators. Risk is elevated based on meteorological "
            "modelling; awaiting observational confirmation from gauges and water-level sensors."
        )
    elif driver == "atmospheric_buildup":
        h = signals.get("_humidity", 0.0)
        parts.append(
            f"Atmospheric saturation ({h:.0f}% relative humidity) with an active BMKG "
            "advisory indicates conditions primed for rainfall intensification. Current "
            "gauge readings may understate total precipitation potential."
        )
    else:
        parts.append(
            "Multi-source signals are within normal operating range. No immediate flood "
            "indication from rainfall intensity, official alerts, or current water conditions. "
            "Continued routine monitoring is appropriate."
        )

    if signals.get("monsoon_context"):
        parts.append(
            "Note: system is operating during monsoon season — baseline risk is "
            "inherently elevated and lower warning thresholds apply."
        )
    if "missing_data" in failure_types:
        parts.append(
            "Caveat: one or more input data sources are missing — this interpretation "
            "reflects partial observability."
        )
    if "signal_conflict" in failure_types:
        parts.append(
            "Caveat: conflicting signals detected across data sources. "
            "Manual cross-verification is recommended before operational action."
        )
    if "ood_input" in failure_types:
        parts.append(
            "Caveat: input features are partially outside the model's training distribution. "
            "Treat the probability estimate with additional caution."
        )

    return " ".join(parts)


def generate_recommended_action(
    signals: dict,
    failures: list[dict],
    risk_level: str,
) -> list[str]:
    """
    Produce a prioritized, signal-driven action list.

    Actions are derived from specific physical signals rather than risk_level alone,
    ensuring appropriate recommendations even when model probability is near a
    classification boundary or signals partially contradict each other.
    """
    actions: list[str] = []
    failure_types = {f.get("type") for f in failures}
    driver = signals.get("dominant_driver", "low_background_risk")

    # ── Immediate safety ─────────────────────────────────────────────────────
    if signals.get("critical_water_level") or driver == "critical_hydrology":
        actions.append(
            "IMMEDIATE: Activate evacuation protocols for flood-prone zones "
            "near water-monitoring stations exceeding threshold ratio."
        )
        actions.append("IMMEDIATE: Notify emergency response teams for standby deployment.")

    if signals.get("compound_risk") or driver == "compound_event":
        actions.append(
            "IMMEDIATE: Issue multi-agency emergency coordination alert — "
            "compound flood event conditions are active."
        )
        actions.append(
            "IMMEDIATE: Restrict access to historically flooded corridors "
            "pending field assessment."
        )

    if signals.get("bmkg_confirmed") and signals.get("bmkg_extreme"):
        actions.append(
            "HIGH PRIORITY: Cross-reference BMKG alert details with water-gate operations. "
            "Confirm gate opening status and spillway capacity."
        )

    # ── Operational readiness ────────────────────────────────────────────────
    if signals.get("rising_water"):
        wdelta = signals.get("_water_delta", 0.0)
        actions.append(
            f"Increase water-level monitoring to 15-minute intervals — "
            f"current rise rate Δ{wdelta:.2f}/step requires close tracking."
        )

    if signals.get("extreme_rainfall") or signals.get("high_rainfall"):
        actions.append(
            "Inspect and clear urban drainage inlets in flood-prone districts. "
            "High-intensity rainfall may overwhelm standard drainage capacity."
        )

    if signals.get("sustained_rainfall"):
        actions.append(
            "Alert downstream basin coordinators — sustained rainfall accumulation "
            "will likely propagate as a downstream surge within 1–3 hours."
        )

    if signals.get("atmosphere_saturated"):
        actions.append(
            "High atmospheric humidity indicates additional rainfall likely even if current "
            "BMKG alert intensity appears moderate. Maintain elevated operational readiness."
        )

    if risk_level in ("DANGER", "WARNING"):
        actions.append(
            "Deploy field verification teams to the top 3 flood-prone areas "
            "for ground-truth validation of sensor readings."
        )

    if signals.get("hmi_high"):
        actions.append(
            "Hydrological-meteorological index elevated — coordinate with BPBD for "
            "pre-emptive resource staging at high-risk districts."
        )

    # ── Data quality / failure response ─────────────────────────────────────
    if "missing_data" in failure_types:
        actions.append(
            "DATA: Restore missing sensor feeds immediately. "
            "Current assessment operates under reduced observability."
        )
    if "signal_conflict" in failure_types:
        actions.append(
            "DATA: Manually review conflicting sensor readings before issuing public advisories."
        )
    if "stale_data" in failure_types:
        actions.append(
            "DATA: Refresh data pipeline — snapshot exceeds acceptable staleness threshold."
        )

    # ── Safe-state fallback ──────────────────────────────────────────────────
    if not actions:
        actions.append("Continue standard monitoring cadence. No immediate intervention required.")
        actions.append(
            "Validate sensor uptime and confirm snapshot refresh pipeline is running on schedule."
        )

    return actions


def build_context_summary(
    features: dict,
    diagnostics: dict,
    prediction: dict,
    baseline: dict,
    plausibility_score: float = 1.0,
) -> dict:
    """Assemble all contextual signals into a unified summary for downstream agents."""
    s = extract_signals(features, plausibility_score=plausibility_score)
    driver = dominant_risk_driver(features, plausibility_score=plausibility_score)
    s["dominant_driver"] = driver

    return {
        "signals": s,
        "dominant_risk_driver": driver,
        "model_probability": prediction.get("probability", 0.0),
        "model_risk_level": prediction.get("risk_level", "UNKNOWN"),
        "baseline_probability": baseline.get("baseline_probability", 0.0),
        "baseline_alert": baseline.get("baseline_alert", False),
        "diagnostics": diagnostics,
        "ood_is_outlier": prediction.get("ood_detection", {}).get("is_outlier", False),
    }
