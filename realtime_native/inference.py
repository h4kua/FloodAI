import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

from realtime_native.bundle import load_runtime_bundle
from realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_file,
)
from utils.paths import DEFAULT_REALTIME_SNAPSHOT, REPORTS_DIR

_JAKARTA_TZ = timezone(timedelta(hours=7))
_JAKARTA_WILAYAH = ["Jakarta Pusat", "Jakarta Utara", "Jakarta Barat", "Jakarta Selatan", "Jakarta Timur"]
_BMKG_WILAYAH_MAP = {
    "Kota Adm. Jakarta Pusat":   "Jakarta Pusat",
    "Kota Adm. Jakarta Utara":   "Jakarta Utara",
    "Kota Adm. Jakarta Barat":   "Jakarta Barat",
    "Kota Adm. Jakarta Selatan": "Jakarta Selatan",
    "Kota Adm. Jakarta Timur":   "Jakarta Timur",
}


def _load_thresholds() -> dict:
    return dict(load_runtime_bundle().thresholds)


def _classify(probability: float, thresholds: dict) -> str:
    if probability < thresholds["warning"]:
        return "SAFE"
    if probability < thresholds["danger"]:
        return "WARNING"
    return "DANGER"


def _apply_hydro_override(risk_level: str, probability: float, water_level_ratio: float) -> tuple[str, float]:
    """
    Rule-based safety floor that mirrors the L1/L1.8 hierarchy in decision_engine.py.
    The ML model was trained when TMA data was often unavailable, so it underestimates
    risk when water levels are high. These overrides prevent the model from returning
    SAFE when physical sensors indicate otherwise.
    """
    if water_level_ratio >= 1.0:
        # Water above SIAGA-1 danger threshold → always DANGER
        return "DANGER", max(probability, 0.92)
    if water_level_ratio >= 0.90:
        # L1 SIAGA: ratio ≥ 0.90 → at least WARNING
        if risk_level == "SAFE":
            return "WARNING", max(probability, 0.56)
        return risk_level, max(probability, 0.56)
    if water_level_ratio >= 0.75:
        # L1.8 HYDRO_FLOOR: ratio ≥ 0.75 → at least WARNING (mirrors decision_engine.py)
        if risk_level == "SAFE":
            return "WARNING", max(probability, 0.35)
    return risk_level, probability


def _risk_interpretation(risk_level, diagnostics):
    bmkg_source = diagnostics.get("bmkg_source", "no_alert")
    temporal_ready = diagnostics.get("temporal_features_ready", False)
    water_level_records = diagnostics.get("water_level_records", 0)

    if risk_level == "DANGER":
        if bmkg_source == "observed_alerts" and water_level_records > 0:
            return (
                "Risiko tinggi terdeteksi karena sinyal cuaca ekstrem sudah dikonfirmasi alert BMKG "
                "dan diperkuat oleh kondisi tinggi muka air. Ini menunjukkan potensi banjir yang "
                "bukan hanya prediksi statistik, tetapi juga konsisten dengan indikator lapangan."
            )
        return (
            "Risiko tinggi terdeteksi dari kombinasi hujan intens, akumulasi temporal, dan sinyal "
            "hidrologi. Kondisi ini mengindikasikan potensi genangan atau banjir meningkat dalam waktu dekat."
        )
    if risk_level == "WARNING":
        if temporal_ready:
            return (
                "Sistem melihat pola yang mulai mengarah ke banjir, terutama dari akumulasi hujan dan "
                "perubahan kondisi air. Belum berada pada level kritis, tetapi perlu pemantauan lebih rapat."
            )
        return (
            "Ada sinyal kewaspadaan awal dari cuaca dan hidrologi, tetapi bukti temporal belum sepenuhnya kuat. "
            "Status ini cocok untuk siaga operasional, bukan alarm penuh."
        )
    return (
        "Belum ada indikasi kuat banjir dari kombinasi cuaca, alert resmi, dan kondisi air saat ini. "
        "Monitoring tetap diperlukan karena situasi dapat berubah cepat di wilayah urban padat seperti Jakarta."
    )


def _recommended_action(risk_level):
    if risk_level == "DANGER":
        return [
            "Aktifkan koordinasi lintas pihak: BPBD/posko lokal, operator pintu air, dan tim lapangan di titik rawan.",
            "Keluarkan peringatan dini terarah untuk wilayah yang memiliki histori genangan atau elevasi rendah.",
            "Prioritaskan pemeriksaan pintu air, saluran utama, dan titik yang menunjukkan kenaikan muka air tercepat.",
        ]
    if risk_level == "WARNING":
        return [
            "Naikkan frekuensi monitoring BMKG, OpenWeather, dan Posko Banjir agar eskalasi bisa ditangkap lebih cepat.",
            "Siapkan personel siaga terbatas dan verifikasi kondisi drainase, pompa, atau titik limpasan yang sering bermasalah.",
            "Gunakan status ini untuk komunikasi internal dan kesiapan operasional, belum untuk alarm publik penuh.",
        ]
    return [
        "Lanjutkan monitoring rutin dan simpan histori realtime untuk retraining agar model makin akurat dari waktu ke waktu.",
        "Gunakan periode aman ini untuk validasi data, kalibrasi threshold, dan evaluasi kesiapan infrastruktur lokal.",
    ]


def _siaga_rank(status_str: str) -> int:
    s = (status_str or "").lower()
    if "siaga 1" in s: return 4
    if "siaga 2" in s: return 3
    if "siaga 3" in s: return 2
    return 0


def _parse_bmkg_cuaca_per_wilayah(cuaca_path: Path) -> dict:
    """Read bmkg_cuaca.json and return upcoming forecasts keyed by wilayah name."""
    now_utc = datetime.now(timezone.utc)
    result: dict = {}
    try:
        with open(cuaca_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return result
    for area in data.get("data", []):
        lokasi = area.get("lokasi", {})
        if lokasi.get("adm1") != "31":
            continue
        wilayah = _BMKG_WILAYAH_MAP.get(lokasi.get("kotkab", ""))
        if not wilayah:
            continue
        entries = []
        for item in area.get("cuaca", []):
            dt_str = item.get("local_datetime", "")
            try:
                utc_dt = datetime.fromisoformat(dt_str).replace(tzinfo=_JAKARTA_TZ)
            except (ValueError, AttributeError):
                continue
            if utc_dt >= now_utc:
                entries.append({
                    "local_datetime": dt_str,
                    "weather_desc": item.get("weather_desc", ""),
                    "tmin": item.get("tmin"),
                    "tmax": item.get("tmax"),
                    "humin": item.get("humin"),
                    "humax": item.get("humax"),
                })
        entries.sort(key=lambda x: x["local_datetime"])
        result[wilayah] = entries[:4]
    return result


def _build_wilayah_summary(poskobanjir_records: list, bmkg_per_wilayah: dict) -> list:
    """Aggregate TMA stations and BMKG forecast per Jakarta wilayah."""
    tma_by_wilayah: dict = {w: [] for w in _JAKARTA_WILAYAH}
    for rec in poskobanjir_records:
        w = rec.get("file_export", "")
        if w in tma_by_wilayah:
            tma_by_wilayah[w].append(rec)

    summary = []
    for w in _JAKARTA_WILAYAH:
        stations = tma_by_wilayah[w]
        forecast = bmkg_per_wilayah.get(w, [])
        ranks = [_siaga_rank(s.get("status_siaga", "")) for s in stations]
        worst = max(ranks) if ranks else 0
        worst_label = {4: "Siaga 1", 3: "Siaga 2", 2: "Siaga 3"}.get(worst, "Normal")
        summary.append({
            "wilayah": w,
            "tma_count": len(stations),
            "siaga1_count": sum(1 for r in ranks if r >= 4),
            "siaga2_count": sum(1 for r in ranks if r == 3),
            "siaga3_count": sum(1 for r in ranks if r == 2),
            "worst_status": worst_label,
            "worst_rank": worst,
            "forecast": forecast[:3],
        })
    return summary


def _parse_ow_entry(ow_raw: dict) -> dict:
    """Extract relevant fields dari satu OWM current weather response."""
    return {
        "temp":         ow_raw.get("main", {}).get("temp"),
        "feels_like":   ow_raw.get("main", {}).get("feels_like"),
        "pressure":     ow_raw.get("main", {}).get("pressure"),
        "humidity":     ow_raw.get("main", {}).get("humidity"),
        "wind_speed":   ow_raw.get("wind", {}).get("speed"),
        "wind_deg":     ow_raw.get("wind", {}).get("deg"),
        "wind_gust":    ow_raw.get("wind", {}).get("gust"),
        "clouds":       ow_raw.get("clouds", {}).get("all"),
        "visibility":   ow_raw.get("visibility"),
        "weather_main": (ow_raw.get("weather") or [{}])[0].get("main"),
        "weather_desc": (ow_raw.get("weather") or [{}])[0].get("description"),
        "weather_icon": (ow_raw.get("weather") or [{}])[0].get("icon"),
        "rainfall_1h":  (ow_raw.get("rain") or {}).get("1h", 0.0),
    }


def _load_assets() -> tuple:
    bundle = load_runtime_bundle()
    return (
        bundle.model,
        bundle.scaler,
        bundle.ood_detector,
        bundle.model_card,
        dict(bundle.thresholds),
    )


def predict_realtime_native(
    snapshot_path=DEFAULT_REALTIME_SNAPSHOT,
    *,
    persist_history: bool = True,
    as_of=None,
):
    """
    ``persist_history=False`` + a pinned ``as_of`` together enable deterministic
    replay: no CSV append, trend window pinned to ``as_of``.
    """
    model, scaler, ood_detector, model_card, thresholds = _load_assets()

    # Load snapshot to extract forecast and freshness timestamp.
    # Neither is used for ML; both are passed through to the response so the
    # frontend can show when sensor data was actually collected.
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot_raw = json.load(f)
        bmkg_forecast = snapshot_raw.get("bmkg_forecast") or []
        snapshot_fetched_at = snapshot_raw.get("fetched_at_utc") or ""
        poskobanjir_records = snapshot_raw.get("poskobanjir") or []
    except Exception:
        bmkg_forecast = []
        snapshot_fetched_at = ""
        poskobanjir_records = []

    # Build per-wilayah summary: read bmkg_cuaca.json directly (freshest source)
    cuaca_path = Path(snapshot_path).parent.parent / "raw" / "bmkg_cuaca.json"
    bmkg_per_wilayah = _parse_bmkg_cuaca_per_wilayah(cuaca_path)

    raw_dir = Path(snapshot_path).parent.parent / "raw"

    # Read OpenWeather current data (pusat — untuk WeatherCurrentCard fallback)
    openweather_current: dict = {}
    try:
        with open(raw_dir / "openweather_current.json", "r", encoding="utf-8") as f:
            ow_raw = json.load(f)
        openweather_current = _parse_ow_entry(ow_raw)
    except Exception:
        pass

    # Read OpenWeather per-wilayah data (5 kota administrasi)
    openweather_wilayah: dict = {}
    try:
        with open(raw_dir / "openweather_wilayah.json", "r", encoding="utf-8") as f:
            ow_wilayah_raw = json.load(f)
        for wilayah, ow in ow_wilayah_raw.items():
            openweather_wilayah[wilayah] = _parse_ow_entry(ow)
    except Exception:
        pass
    wilayah_summary = _build_wilayah_summary(poskobanjir_records, bmkg_per_wilayah)

    engineered = build_realtime_native_features_from_file(
        snapshot_path=snapshot_path, persist_history=persist_history, as_of=as_of,
    )
    features = engineered.frame[REALTIME_NATIVE_FEATURES]
    scaled = scaler.transform(features)
    probability = float(model.predict_proba(scaled)[0, 1])
    ood_score = float(ood_detector.decision_function(scaled)[0])
    ood_label = int(ood_detector.predict(scaled)[0] == -1)
    risk_level = _classify(probability, thresholds)

    water_level_ratio = float(features.iloc[0].get("water_level_ratio", 0.0))
    risk_level, probability = _apply_hydro_override(risk_level, probability, water_level_ratio)

    # Suppress false-positive OOD when water level explains the anomaly.
    # Model was trained before real TMA data existed (ratio mostly 0.0);
    # ratios >= 0.75 fall outside training distribution but are not true
    # operational outliers — the hydro override already accounts for them.
    if ood_label and water_level_ratio >= 0.75:
        ood_label = 0

    result = {
        "model_variant": "realtime_native",
        "probability": probability,
        "risk_level": risk_level,
        "risk_interpretation": _risk_interpretation(risk_level, engineered.diagnostics),
        "recommended_action": _recommended_action(risk_level),
        "risk_thresholds": thresholds,
        # ISO-8601 UTC timestamp when the sensor snapshot was built.
        # Lets the frontend show "Data sensor dari XX:XX WIB" so users know
        # how fresh the underlying TMA/BMKG/OpenWeather data actually is.
        "snapshot_fetched_at": snapshot_fetched_at,
        "bmkg_forecast": bmkg_forecast,
        "ood_detection": {
            "method": "IsolationForest",
            "score": ood_score,
            "is_outlier": bool(ood_label),
        },
        "features": features.iloc[0].to_dict(),
        "diagnostics": engineered.diagnostics,
        "model_name": model_card.get("model_name"),
        # Real DSDADKI station readings — sourced directly from sensor snapshot,
        # NOT derived from ML model output. Empty list when no stations are active.
        "stations": engineered.diagnostics.get("stations_summary", []),
        "wilayah_summary": wilayah_summary,
        "openweather_current": openweather_current,
        "openweather_wilayah": openweather_wilayah,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _report_path = REPORTS_DIR / "latest_realtime_native_prediction.json"
    _tmp_path = _report_path.with_suffix(_report_path.suffix + ".tmp")
    # Atomic write: serialize to a sibling tempfile then os.replace so a crash
    # mid-write leaves the previous valid file in place and never a truncated JSON.
    with open(_tmp_path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.flush()
        try:
            os.fsync(file.fileno())
        except OSError:
            pass
    os.replace(_tmp_path, _report_path)

    return json.loads(json.dumps(result, default=lambda value: float(value) if isinstance(value, np.generic) else value))
