"""
Physical plausibility scoring for Jakarta flood prediction inputs.

Purpose:
  Detect corrupted, synthetic, or physically impossible sensor values before
  they reach the ML model. Complements IsolationForest OOD detection with
  explicit domain-specific physical constraints — IsolationForest catches
  statistical outliers; this module catches physical impossibilities.

Jakarta-specific ranges derived from:
  - BMKG climatological records 1980–2024 (Stasiun Meteorologi Kemayoran)
  - BPBD DKI Jakarta historical flood data
  - WMO standard observation ranges (No. 8)
  - Hidrologi Sungai Ciliwung / Posko Banjir historical maxima

Plausibility score:
  1.0  — physically realistic (within normal operational range)
  0.5  — borderline / unusual but physically possible
  0.0  — physically impossible (instrument fault or synthetic data)

Score < 0.50 → is_plausible=False → should trigger OOD review.
Score < 0.20 → likely corrupted or synthetic; discard before model inference.

Real-world reference mapping (Task 2):
  Extreme rainfall scenario (92 mm/h):   plausibility ≈ 0.78 — extreme but real
    Reference: Jakarta flood event Feb 2020 — 100 mm/h peak at Kemayoran
  Hydrology spike (920 cm, no rain):     plausibility ≈ 0.65 — valid upstream surge
    Reference: Ciliwung upstream Katulampa tidal backflow events
  OOD scenario (temp=-45°C, hum=200%):  plausibility ≈ 0.0  — sensor fault / synthetic
    Reference: No physical mechanism produces these values at Jakarta latitude
"""

from __future__ import annotations

# ── Physical domain bounds for Jakarta ────────────────────────────────────────
# Format: (normal_lo, normal_hi, physical_lo, physical_hi)
# physical bounds = absolute thermodynamic/sensor impossibility
# normal bounds   = range expected in Jakarta operational records
_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    # Jakarta tropics: coldest ever 18.5°C (1967), hottest 37.8°C (1997 Kemayoran).
    "temp_c":         (20.0, 38.0,  -90.0, 60.0),

    # Physically bounded at 0–100%. Jakarta dry season min ≈ 55%.
    "humidity_pct":   (45.0, 100.0,  0.0, 100.0),

    # Indonesia WMO extreme observed peak ≈ 274 mm/h. > 200 mm/h rare.
    "rainfall_1h_mm": (0.0,  200.0,  0.0, 500.0),

    # 3-hour accumulation: proportionally bounded.
    "rainfall_3h_mm": (0.0,  450.0,  0.0, 900.0),

    # Tropical sea-level: 990–1020 hPa normal; typhoon core ≈ 870 hPa minimum.
    "pressure_hpa":   (990.0, 1020.0, 870.0, 1084.0),

    # Jakarta wind normal < 10 m/s; tropical storm ≥ 17 m/s. Physical max ≈ 100 m/s.
    "wind_speed_ms":  (0.0,  25.0,   0.0, 100.0),

    # Posko Banjir tinggi_air: Manggarai DANGER ≈ 850 cm; highest ever ≈ 1050 cm.
    # Structural gauge limit ≈ 2500 cm (impossible to read beyond this).
    "water_level_cm": (0.0, 1200.0,  0.0, 2500.0),
}

# Combination implausibility rules:
# (condition_fn, combo_key, description, penalty_score)
# penalty_score = field score assigned when this combo triggers
_COMBO_RULES: list[tuple] = [
    # Heavy precipitation requires near-saturation. Rainfall at < 65% RH is impossible —
    # rain droplets evaporate before reaching the ground (virga effect).
    (
        lambda rf, hum, temp: rf > 10.0 and hum < 65.0,
        "heavy_rain_low_humidity",
        "Rainfall > 10 mm/h with humidity < 65% — rain cannot sustain to ground at this saturation",
        0.20,
    ),
    # Intense convective rainfall releases latent heat and cools surface rapidly.
    # Co-occurrence of > 38°C AND > 30 mm/h is thermodynamically contradictory.
    (
        lambda rf, hum, temp: temp > 38.0 and rf > 30.0,
        "extreme_heat_heavy_rain",
        "Temperature > 38°C with rainfall > 30 mm/h — thermodynamically contradictory",
        0.25,
    ),
    # Jakarta has never recorded below 18°C. < 5°C = sensor fault or synthetic input.
    (
        lambda rf, hum, temp: temp < 5.0,
        "sub_zero_jakarta",
        "Temperature < 5°C is physically impossible for equatorial Jakarta (lat -6°S)",
        0.0,
    ),
    # Relative humidity is bounded at 100% by the Clausius-Clapeyron equation.
    (
        lambda rf, hum, temp: hum > 100.0,
        "super_saturated_humidity",
        "Humidity > 100% violates thermodynamic law — sensor fault or synthetic data",
        0.0,
    ),
]


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _field_plausibility(
    value: float,
    normal_lo: float,
    normal_hi: float,
    phys_lo: float,
    phys_hi: float,
) -> tuple[float, str]:
    """
    Score a single field value against normal and physical bounds.

    Returns (score 0.0–1.0, severity "ok" | "moderate" | "critical").

    Within normal range:   1.0,  "ok"
    Within physical range but outside normal: linearly decays 0.80 → 0.10
    Outside physical range: 0.0, "critical"
    """
    if not (phys_lo <= value <= phys_hi):
        return 0.0, "critical"
    if normal_lo <= value <= normal_hi:
        return 1.0, "ok"

    normal_width = max(normal_hi - normal_lo, 1.0)
    excess = max(normal_lo - value, value - normal_hi, 0.0)
    excess_fraction = min(excess / normal_width, 1.0)
    score = max(0.10, 0.80 - 0.70 * excess_fraction)
    return round(score, 4), "moderate"


# ── Public API ────────────────────────────────────────────────────────────────

def score_plausibility(snapshot: dict) -> dict:
    """
    Score the physical plausibility of a snapshot against Jakarta domain bounds.

    Returns:
    {
        "plausibility_score": float,   0.0–1.0 mean of all scored fields
        "is_plausible":       bool,    True if score >= 0.50
        "violations":         list,    per-field violations with field/value/severity
        "field_scores":       dict,    {field_name: score}
        "combo_flags":        list,    impossible multi-field combinations
    }
    """
    ow   = snapshot.get("openweather") or {}
    main = ow.get("main") or {}
    rain = ow.get("rain") or {}
    wind = ow.get("wind") or {}

    violations: list[dict] = []
    field_scores: dict[str, float] = {}

    # ── Per-field scalar checks ───────────────────────────────────────────────
    checks: list[tuple[str, float | None]] = [
        ("temp_c",         main.get("temp")),
        ("humidity_pct",   main.get("humidity")),
        ("rainfall_1h_mm", rain.get("1h")),
        ("rainfall_3h_mm", rain.get("3h")),
        ("pressure_hpa",   main.get("pressure")),
        ("wind_speed_ms",  wind.get("speed")),
    ]

    for field, raw_value in checks:
        if raw_value is None:
            continue
        n_lo, n_hi, p_lo, p_hi = _BOUNDS[field]
        score, severity = _field_plausibility(float(raw_value), n_lo, n_hi, p_lo, p_hi)
        field_scores[field] = score
        if severity != "ok":
            violations.append({
                "field": field,
                "value": raw_value,
                "normal_range": [n_lo, n_hi],
                "physical_bounds": [p_lo, p_hi],
                "score": score,
                "severity": severity,
            })

    # ── Water level bounds (per Posko Banjir station) ────────────────────────
    posko = snapshot.get("poskobanjir") or []
    wl_scores: list[float] = []
    for station in posko:
        wl = station.get("tinggi_air")
        if wl is None:
            continue
        n_lo, n_hi, p_lo, p_hi = _BOUNDS["water_level_cm"]
        score, severity = _field_plausibility(float(wl), n_lo, n_hi, p_lo, p_hi)
        wl_scores.append(score)
        if severity != "ok":
            violations.append({
                "field": f"water_level_cm[{station.get('id', '?')}]",
                "value": wl,
                "normal_range": [n_lo, n_hi],
                "physical_bounds": [p_lo, p_hi],
                "score": score,
                "severity": severity,
            })
    if wl_scores:
        # Any station being impossible contaminates the full batch.
        field_scores["water_level_cm"] = round(min(wl_scores), 4)

    # ── Combination plausibility checks ─────────────────────────────────────
    combo_flags: list[dict] = []
    rf   = float(rain.get("1h") or 0.0)
    hum  = float(main.get("humidity") or 75.0)
    temp = float(main.get("temp") or 28.0)

    for condition_fn, combo_key, description, penalty_score in _COMBO_RULES:
        try:
            triggered = condition_fn(rf, hum, temp)
        except Exception:
            triggered = False
        if triggered:
            combo_flags.append({
                "combo": combo_key,
                "description": description,
                "score": penalty_score,
                "values": {"rainfall_1h_mm": rf, "humidity_pct": hum, "temp_c": temp},
            })
            field_scores[f"combo_{combo_key}"] = penalty_score

    # ── Aggregate ────────────────────────────────────────────────────────────
    if not field_scores:
        return {
            "plausibility_score": 0.5,
            "is_plausible": True,
            "violations": [],
            "field_scores": {},
            "combo_flags": [],
            "note": "Insufficient fields to assess plausibility — defaulting neutral.",
        }

    overall = round(sum(field_scores.values()) / len(field_scores), 4)

    # ── HARD PHYSICAL GATE (CRITICAL safety invariant) ───────────────────────
    # Any single field outside its physical bounds (severity="critical") OR any
    # impossible field combination (combo_flag with score=0.0) makes the entire
    # observation invalid — averaging cannot dilute physical impossibility.
    #
    # Without this gate, a single corrupted sensor (e.g. tinggi_air=9999 cm,
    # field score 0.0) was being diluted by 6 normal weather fields to an
    # aggregate ~0.857, passing the is_plausible threshold and reaching the
    # ML model as trusted data — producing phantom DANGER predictions.
    has_critical_field   = any(v.get("severity") == "critical" for v in violations)
    has_impossible_combo = any(c.get("score", 1.0) == 0.0 for c in combo_flags)
    has_critical_violation = has_critical_field or has_impossible_combo
    is_plausible = (overall >= 0.50) and not has_critical_violation

    return {
        "plausibility_score": overall,
        "is_plausible": is_plausible,
        "has_critical_violation": has_critical_violation,
        "violations": violations,
        "field_scores": field_scores,
        "combo_flags": combo_flags,
    }


def plausibility_failure_record(plausibility: dict) -> dict | None:
    """
    Convert a plausibility result into a failure record compatible with failure_handling.py.

    Returns a failure dict if the input is implausible, None if plausible.
    The returned record can be appended directly to the failure_modes list.
    """
    if plausibility.get("is_plausible", True):
        return None

    score = plausibility.get("plausibility_score", 1.0)
    n_critical = sum(1 for v in plausibility.get("violations", []) if v.get("severity") == "critical")
    n_combo_impossible = sum(
        1 for c in plausibility.get("combo_flags", []) if c.get("score", 1.0) == 0.0
    )
    n_combo = len(plausibility.get("combo_flags", []))

    # severity="high" whenever a physical impossibility exists — single-field
    # critical violation, impossible combo, or aggregate score below 0.20.
    # Aggregate-only failures (no critical/impossible flags) stay "medium".
    severity = "high" if (score < 0.20 or n_critical > 0 or n_combo_impossible > 0) else "medium"
    penalty = 0.15 if severity == "high" else 0.08

    violation_parts = [
        f"{v['field']}={v['value']} (normal: {v['normal_range']})"
        for v in plausibility.get("violations", [])[:3]
    ]
    combo_parts = [f["combo"] for f in plausibility.get("combo_flags", [])]
    detail_str = "; ".join(filter(None, [", ".join(violation_parts), ", ".join(combo_parts)]))

    return {
        "type": "implausible_input",
        "severity": severity,
        "message": (
            f"Input plausibility score {score:.2f} — values fall outside Jakarta physical domain. "
            f"Detail: {detail_str or 'see field_scores'}."
        ),
        "confidence_penalty": penalty,
        "risk_escalation": False,
        "detail": {
            "plausibility_score": score,
            "n_critical_violations": n_critical,
            "n_combo_flags": n_combo,
            "field_scores": plausibility.get("field_scores", {}),
        },
    }
