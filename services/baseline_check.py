"""
Rule-based baseline probability estimation.

The baseline provides an independent sanity-check against the ML model.
When model and baseline significantly disagree, the system flags the gap
for manual review — both can be correct for different reasons (the model
captures non-linear interactions the baseline cannot), but large disagreements
need an explanation before an operator can act with confidence.
"""

from __future__ import annotations

# ─── Physical-domain thresholds ───────────────────────────────────────────────
# Sources: BMKG/BPBD operational guidelines and Jakarta flood historical patterns.

RAINFALL_SAFE_MAX = 5.0           # mm/h: below this, minimal urban runoff
RAINFALL_HIGH_MIN = 20.0          # mm/h: heavy rain, drainage starts struggling
RAINFALL_EXTREME_MIN = 50.0       # mm/h: flash-flood potential in urban Jakarta

WATER_LEVEL_NORMAL_MAX = 0.50     # ratio: routine operation
WATER_LEVEL_ELEVATED_MIN = 0.65   # ratio: elevated concern
WATER_LEVEL_CRITICAL_MIN = 0.85   # ratio: near overflow

BMKG_LOW_MAX = 0.25               # weighted score: low background alert
BMKG_HIGH_MIN = 0.60              # weighted score: high official alert

HYDRO_BASELINE_ALERT_THRESHOLD = 0.50
RAINFALL_BASELINE_ALERT_THRESHOLD = 0.60
# Model-vs-baseline probability gap above which baseline_alert fires.
AGREEMENT_GAP_THRESHOLD = 0.30


def _linear_blend(x: float, low: float, high: float, low_val: float, high_val: float) -> float:
    """
    Linearly interpolate between two value anchors across [low, high].

    Avoids step-function discontinuities that would make small input changes
    produce large unexplained probability jumps.
    """
    if x <= low:
        return low_val
    if x >= high:
        return high_val
    t = (x - low) / (high - low)
    return low_val + t * (high_val - low_val)


def rainfall_baseline(features: dict) -> dict:
    """
    Estimate flood probability from rainfall signals alone using domain rules.

    Three components are weighted and combined:
      - Immediate intensity (1h) — drives acute runoff
      - 3h accumulation          — drives soil saturation and drainage load
      - Rolling mean             — reflects sustained event history

    Humidity and monsoon season are applied as amplifiers, not primary drivers.
    """
    r1h = features.get("rainfall_mm", 0.0) or 0.0
    r3h = features.get("rainfall_3h_proxy_mm", 0.0) or 0.0
    roll3 = features.get("rainfall_roll3_mean", 0.0) or 0.0
    humidity = features.get("humidity_pct", 0.0) or 0.0
    monsoon = bool(features.get("monsoon_season", 0))

    intensity_prob = _linear_blend(r1h, RAINFALL_SAFE_MAX, RAINFALL_EXTREME_MIN, 0.05, 0.75)
    accum_prob = _linear_blend(r3h, 10.0, 100.0, 0.05, 0.70)
    sustained_prob = _linear_blend(roll3, 10.0, 40.0, 0.05, 0.60)

    # Immediate intensity is most dangerous; 3h accumulation second; rolling last.
    base_prob = intensity_prob * 0.45 + accum_prob * 0.35 + sustained_prob * 0.20

    # Near-saturated atmosphere amplifies effective rainfall runoff.
    if humidity > 85.0:
        base_prob = min(base_prob * 1.15, 1.0)

    # Monsoon raises the baseline but does not dominate it.
    if monsoon and base_prob > 0.10:
        base_prob = min(base_prob * 1.10, 1.0)

    return {
        "rainfall_baseline_probability": round(base_prob, 4),
        "components": {
            "intensity_1h": round(intensity_prob, 4),
            "accumulation_3h": round(accum_prob, 4),
            "sustained_rolling": round(sustained_prob, 4),
        },
        "alert": base_prob > RAINFALL_BASELINE_ALERT_THRESHOLD,
    }


def hydro_baseline(features: dict) -> dict:
    """
    Estimate flood probability from hydrological signals.

    Four components, weighted by directness of flood-precursor relationship:
      - Water level ratio  — primary (direct measurement of overflow proximity)
      - Water level delta  — urgency amplifier (rate-of-change adds danger)
      - BMKG score         — official alert as corroborating signal
      - HMI               — hydro-meteorological index (compound coupling)

    Water level dominates because it is the most direct precursor to overflow.
    """
    wrat = features.get("water_level_ratio", 0.0) or 0.0
    wdelta = features.get("water_level_delta", 0.0) or 0.0
    bwt = features.get("bmkg_weighted_score", 0.0) or 0.0
    hmi = features.get("hydro_meteorological_index", 0.0) or 0.0

    level_prob = _linear_blend(wrat, WATER_LEVEL_NORMAL_MAX, WATER_LEVEL_CRITICAL_MIN, 0.05, 0.90)
    # Rising water is more dangerous than a static elevated level.
    delta_prob = _linear_blend(wdelta, 0.0, 0.30, 0.0, 0.40) if wdelta > 0 else 0.0
    alert_prob = _linear_blend(bwt, BMKG_LOW_MAX, BMKG_HIGH_MIN, 0.02, 0.30)
    hmi_prob = _linear_blend(hmi, 0.50, 2.50, 0.02, 0.35)

    base_prob = (
        level_prob * 0.50
        + delta_prob * 0.25
        + alert_prob * 0.15
        + hmi_prob * 0.10
    )

    return {
        "hydro_baseline_probability": round(base_prob, 4),
        "components": {
            "water_level_ratio": round(level_prob, 4),
            "water_level_delta": round(delta_prob, 4),
            "bmkg_support": round(alert_prob, 4),
            "hmi_component": round(hmi_prob, 4),
        },
        "alert": base_prob > HYDRO_BASELINE_ALERT_THRESHOLD,
    }


def compare_with_baseline(model_prob: float, features: dict) -> dict:
    """
    Compare the ML model probability against rule-based baseline estimates.

    The combined baseline weights hydrology slightly higher (0.55) than
    rainfall (0.45) because water_level_ratio is a more direct flood precursor
    than instantaneous rainfall intensity.

    A large disagreement gap does not mean the model is wrong — it means
    the two perspectives need to be reconciled before operational action.
    """
    r_result = rainfall_baseline(features)
    h_result = hydro_baseline(features)

    r_prob = r_result["rainfall_baseline_probability"]
    h_prob = h_result["hydro_baseline_probability"]

    combined = round(r_prob * 0.45 + h_prob * 0.55, 4)
    disagreement = round(abs(model_prob - combined), 4)
    baseline_alert = disagreement > AGREEMENT_GAP_THRESHOLD

    if not baseline_alert:
        agreement_label = "agree"
    elif model_prob > combined:
        agreement_label = "model_higher"
    else:
        agreement_label = "model_lower"

    return {
        "baseline_probability": combined,
        "rainfall_baseline": r_result,
        "hydro_baseline": h_result,
        "baseline_disagreement": disagreement,
        "baseline_alert": baseline_alert,
        "model_vs_baseline": agreement_label,
    }
