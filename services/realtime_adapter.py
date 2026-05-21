import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from services.awlr_threshold_fetcher import load_cached_thresholds, siaga1_cm_for
from services.bmkg_filter import filter_jakarta_bmkg_alerts
from services.constants import (
    BMKG_CERTAINTY_WEIGHTS,
    BMKG_SEVERITY_WEIGHTS,
    BMKG_URGENCY_WEIGHTS,
)
from services.pintu_air_fetcher import (
    load_cached_pintu_air,
    observation_age_minutes,
)
from utils.paths import CONFIG_DIR, DEFAULT_REALTIME_SNAPSHOT

# Live TMA (Tinggi Muka Air) readings older than this are treated as stale and
# excluded from active signalling — the AWLR thresholds still apply as context.
_TMA_STALE_THRESHOLD_MIN = 120.0

SEVERITY_WEIGHTS = BMKG_SEVERITY_WEIGHTS
CERTAINTY_WEIGHTS = BMKG_CERTAINTY_WEIGHTS
URGENCY_WEIGHTS = BMKG_URGENCY_WEIGHTS

STATUS_NORMALIZATION = {
    "siaga 1": 1.0,
    "siaga 2": 0.8,
    "siaga 3": 0.5,
    "siaga 4": 0.25,
    "normal": 0.0,
}


@dataclass(frozen=True)
class SnapshotFeatures:
    feature_frame: pd.DataFrame
    diagnostics: dict
    data_quality: dict


def _load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_realtime_snapshot(snapshot_path=None):
    snapshot_file = snapshot_path or DEFAULT_REALTIME_SNAPSHOT
    return _load_json(snapshot_file)


def _load_baselines():
    return _load_json(CONFIG_DIR / "realtime_feature_baselines_jakarta.json")


def _safe_float(value, default=0.0):
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_timestamp(timestamp_text):
    if not timestamp_text:
        return datetime.now(timezone.utc)

    normalized = timestamp_text.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _status_score(status_text):
    status = (status_text or "").strip().lower()
    for label, score in STATUS_NORMALIZATION.items():
        if label in status:
            return score
    return 0.0


def _water_gate_ratio(record):
    tinggi_air = _safe_float(record.get("tinggi_air"))
    thresholds = [
        _safe_float(record.get("siaga1")),
        _safe_float(record.get("siaga2")),
        _safe_float(record.get("siaga3")),
        _safe_float(record.get("siaga4")),
    ]
    thresholds = [value for value in thresholds if value > 0]
    reference = max(thresholds) if thresholds else 0.0
    if reference <= 0:
        return 0.0
    return min(tinggi_air / reference, 1.5)


def _select_region(snapshot, baselines):
    poskobanjir_records = snapshot.get("poskobanjir", [])
    jakarta_records = []
    for record in poskobanjir_records:
        region_name = (record.get("file_export") or "").strip()
        if region_name.lower().startswith("jakarta"):
            jakarta_records.append(region_name)

    if jakarta_records:
        counts = pd.Series(jakarta_records).value_counts()
        region_name = counts.index[0]
        return region_name, baselines["regions"].get(region_name, baselines["citywide"]), "regional_baseline"

    return "DKI Jakarta", baselines["citywide"], "citywide_baseline"


def _score_single_alert(alert):
    severity = SEVERITY_WEIGHTS.get((alert.get("severity") or "").lower(), 0.4)
    certainty = CERTAINTY_WEIGHTS.get((alert.get("certainty") or "").lower(), 0.4)
    urgency = URGENCY_WEIGHTS.get((alert.get("urgency") or "").lower(), 0.5)
    score = severity * certainty * urgency
    return {
        "severity_weight": severity,
        "certainty_weight": certainty,
        "urgency_weight": urgency,
        "weighted_score": score,
    }


def _summarize_bmkg_alerts(alerts):
    details = []
    for alert in alerts:
        alert_score = _score_single_alert(alert)
        details.append(
            {
                "headline": alert.get("headline"),
                "severity": alert.get("severity"),
                "certainty": alert.get("certainty"),
                "urgency": alert.get("urgency"),
                **alert_score,
            }
        )

    total_score = sum(item["weighted_score"] for item in details)
    normalized_score = min(total_score, 1.0)
    rainfall_influence_mm = normalized_score * 45.0
    return {
        "alerts": details,
        "total_weighted_score": total_score,
        "normalized_score": normalized_score,
        "rainfall_influence_mm": rainfall_influence_mm,
        "extreme_weather_flag": int(normalized_score >= 0.45),
    }


def _estimate_hydrology(weather, bmkg_signal, poskobanjir_records):
    rain_data = weather.get("rain", {})
    rain_1h = _safe_float(rain_data.get("1h"))
    rain_3h = _safe_float(rain_data.get("3h"))
    observed_rainfall = max(rain_1h, rain_3h / 3 if rain_3h else 0.0)

    water_gate_ratio = max((_water_gate_ratio(record) for record in poskobanjir_records), default=0.0)
    status_score = max((_status_score(record.get("status")) for record in poskobanjir_records), default=0.0)
    water_gate_influence_mm = water_gate_ratio * 25.0 + status_score * 10.0

    effective_max_rainfall = observed_rainfall + bmkg_signal["rainfall_influence_mm"] + water_gate_influence_mm
    effective_avg_rainfall = max(
        observed_rainfall,
        observed_rainfall * 0.6 + bmkg_signal["rainfall_influence_mm"] * 0.35 + water_gate_influence_mm * 0.15,
    )

    return {
        "observed_rainfall": observed_rainfall,
        "effective_avg_rainfall": effective_avg_rainfall,
        "effective_max_rainfall": effective_max_rainfall,
        "water_gate_ratio": water_gate_ratio,
        "status_score": status_score,
        "water_gate_influence_mm": water_gate_influence_mm,
    }


def _score_data_quality(weather, poskobanjir_records, alerts, feature_sources):
    observed_fields = {
        "temperature": _safe_float(weather.get("main", {}).get("temp"), None),
        "humidity": _safe_float(weather.get("main", {}).get("humidity"), None),
        "coord_lat": _safe_float(weather.get("coord", {}).get("lat"), None),
        "coord_lon": _safe_float(weather.get("coord", {}).get("lon"), None),
    }
    observed_count = sum(value is not None for value in observed_fields.values())
    weather_score = observed_count / len(observed_fields)
    hydrology_score = 1.0 if poskobanjir_records else 0.4
    alert_score = 1.0 if alerts else 0.6

    source_quality_map = {
        "openweather_observed": 1.0,
        "snapshot_timestamp": 0.95,
        "bmkg_weighted_estimate": 0.75,
        "hydrology_estimate": 0.8,
        "regional_baseline": 0.7,
        "citywide_baseline": 0.55,
        "derived_hybrid": 0.8,
    }
    feature_quality = [source_quality_map.get(source, 0.6) for source in feature_sources.values()]
    feature_quality_score = sum(feature_quality) / max(len(feature_quality), 1)

    overall_score = round(
        weather_score * 0.35 + hydrology_score * 0.25 + alert_score * 0.10 + feature_quality_score * 0.30,
        4,
    )

    return {
        "score": overall_score,
        "weather_completeness": round(weather_score, 4),
        "hydrology_completeness": round(hydrology_score, 4),
        "alert_completeness": round(alert_score, 4),
        "feature_reliability": round(feature_quality_score, 4),
        "feature_sources": feature_sources,
    }


def _build_tma_context(now=None):
    """
    Load the latest live water-gate (TMA) reading from the cached FeatureServer
    pull and combine it with the AWLR SIAGA-1 threshold to compute a ratio.

    Read-only and never raises: returns a dict that is always safe to merge into
    diagnostics. When data is missing or older than ``_TMA_STALE_THRESHOLD_MIN``,
    ``tma_stale`` is True and the live level is not used as an active signal — the
    AWLR threshold remains available as context.
    """
    payload = load_cached_pintu_air()
    if not payload:
        return {
            "tma_available": False,
            "tma_stale": True,
            "tma_water_level_cm": None,
            "tma_status": None,
            "tma_observation_age_minutes": None,
            "tma_water_gate_ratio": None,
            "tma_source": "unavailable",
        }

    age_minutes = observation_age_minutes(payload, now=now)
    is_stale = age_minutes is None or age_minutes > _TMA_STALE_THRESHOLD_MIN

    max_cm = payload.get("max_water_level_cm")
    max_status = payload.get("max_status")
    worst_gate = payload.get("max_status_gate") or ""

    siaga1_cm = siaga1_cm_for(worst_gate) if worst_gate else None
    ratio = None
    if max_cm is not None and siaga1_cm and siaga1_cm > 0:
        ratio = round(min(max_cm / siaga1_cm, 1.5), 4)

    return {
        "tma_available": True,
        "tma_stale": bool(is_stale),
        "tma_water_level_cm": max_cm,
        "tma_status": max_status,
        "tma_status_gate": worst_gate or None,
        "tma_observation_age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
        "tma_gate_count": payload.get("gate_count"),
        "tma_siaga1_threshold_cm": siaga1_cm,
        "tma_water_gate_ratio": ratio,
        "tma_source": payload.get("source", "jakartasatu_bpbd_data_pintu_air"),
    }


def adapt_snapshot_to_features(snapshot):
    baselines = _load_baselines()
    region_name, region_profile, region_source = _select_region(snapshot, baselines)
    weather = snapshot.get("openweather", {})
    raw_alerts = snapshot.get("bmkg_alerts", [])
    alerts = filter_jakarta_bmkg_alerts(raw_alerts)
    poskobanjir_records = snapshot.get("poskobanjir", [])
    timestamp = _parse_timestamp(snapshot.get("fetched_at_utc"))

    bmkg_signal = _summarize_bmkg_alerts(alerts)
    hydrology = _estimate_hydrology(weather, bmkg_signal, poskobanjir_records)
    main_weather = weather.get("main", {})

    avg_temperature = _safe_float(main_weather.get("temp"), baselines["citywide"]["avg_temperature"])
    humidity = _safe_float(main_weather.get("humidity"), region_profile["soil_moisture"])
    lat = _safe_float(weather.get("coord", {}).get("lat"), region_profile["lat"])
    lon = _safe_float(weather.get("coord", {}).get("lon"), region_profile["long"])

    elevation = region_profile["elevation"]
    ndvi = region_profile["ndvi"]
    slope = region_profile["slope"]
    max_rainfall = hydrology["effective_max_rainfall"]
    avg_rainfall = min(max_rainfall, max(hydrology["effective_avg_rainfall"], 0.0))
    soil_moisture = float(region_profile["soil_moisture"])
    month = timestamp.month

    row = {
        "avg_rainfall": avg_rainfall,
        "max_rainfall": max_rainfall,
        "avg_temperature": avg_temperature,
        "elevation": elevation,
        "ndvi": ndvi,
        "slope": slope,
        "soil_moisture": soil_moisture,
        "month": month,
        "lat": lat,
        "long": lon,
        "rainfall_soil_interaction": max_rainfall * soil_moisture,
        "elevation_risk": 1 / (elevation + 1),
        "vegetation_elevation_risk": (1 - ndvi) * (1 / (elevation + 1)),
        "extreme_weather": int(max_rainfall >= 35 or bmkg_signal["extreme_weather_flag"] == 1),
        "monsoon_season": int(month in [11, 12, 1, 2, 3]),
        "urban_density_risk": (1 - ndvi) / (slope + 0.1),
    }

    feature_sources = {
        "avg_rainfall": "derived_hybrid",
        "max_rainfall": "derived_hybrid",
        "avg_temperature": "openweather_observed" if weather.get("main", {}).get("temp") is not None else "citywide_baseline",
        "elevation": region_source,
        "ndvi": region_source,
        "slope": region_source,
        "soil_moisture": region_source,
        "month": "snapshot_timestamp",
        "lat": "openweather_observed" if weather.get("coord", {}).get("lat") is not None else region_source,
        "long": "openweather_observed" if weather.get("coord", {}).get("lon") is not None else region_source,
        "rainfall_soil_interaction": "derived_hybrid",
        "elevation_risk": region_source,
        "vegetation_elevation_risk": region_source,
        "extreme_weather": "bmkg_weighted_estimate",
        "monsoon_season": "snapshot_timestamp",
        "urban_density_risk": region_source,
    }
    data_quality = _score_data_quality(weather, poskobanjir_records, alerts, feature_sources)

    tma_context = _build_tma_context(now=timestamp)

    diagnostics = {
        "selected_region": region_name,
        **tma_context,
        "baseline_profile": region_profile,
        "bmkg_alert_count": len(alerts),
        "bmkg_alerts_total": len(raw_alerts),
        "bmkg_alerts_filtered_out": max(len(raw_alerts) - len(alerts), 0),
        "bmkg_weighted_signal": bmkg_signal,
        "poskobanjir_record_count": len(poskobanjir_records),
        "observed_rainfall_mm": hydrology["observed_rainfall"],
        "water_gate_ratio": hydrology["water_gate_ratio"],
        "poskobanjir_status_score": hydrology["status_score"],
        "water_gate_influence_mm": hydrology["water_gate_influence_mm"],
        "adapter_strategy": {
            "geospatial_features": "regional baseline anchored to training distribution",
            "hydrometeorology": "hybrid estimation from OpenWeather + BMKG CAP + Posko Banjir",
            "trade_off": "Kompatibilitas model lama dipertahankan sambil menjaga soil moisture tetap sebagai baseline regional statis.",
        },
        "adapter_notes": [
            "Feature geospasial yang tidak tersedia realtime tetap diberi baseline regional agar inferensi stabil.",
            "Alert BMKG non-Jakarta dibuang sebelum scoring agar snapshot nasional tidak mencemari inferensi Jakarta.",
            "BMKG kini dipakai sebagai weighted hazard signal berbasis severity, certainty, dan urgency.",
            "Output menyertakan kualitas data agar estimasi tidak disalahartikan sebagai observasi penuh.",
        ],
    }

    return SnapshotFeatures(
        feature_frame=pd.DataFrame([row]),
        diagnostics=diagnostics,
        data_quality=data_quality,
    )
