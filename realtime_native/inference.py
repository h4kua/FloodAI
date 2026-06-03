import json
import os

import numpy as np

from realtime_native.bundle import load_runtime_bundle
from realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_file,
)
from utils.paths import DEFAULT_REALTIME_SNAPSHOT, REPORTS_DIR


def _load_thresholds() -> dict:
    return dict(load_runtime_bundle().thresholds)


def _classify(probability: float, thresholds: dict) -> str:
    if probability < thresholds["warning"]:
        return "SAFE"
    if probability < thresholds["danger"]:
        return "WARNING"
    return "DANGER"


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

    # Load snapshot to extract forecast (not used for ML, passed through to response)
    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            snapshot_raw = json.load(f)
        bmkg_forecast = snapshot_raw.get("bmkg_forecast") or []
    except Exception:
        bmkg_forecast = []

    engineered = build_realtime_native_features_from_file(
        snapshot_path=snapshot_path, persist_history=persist_history, as_of=as_of,
    )
    features = engineered.frame[REALTIME_NATIVE_FEATURES]
    scaled = scaler.transform(features)
    probability = float(model.predict_proba(scaled)[0, 1])
    ood_score = float(ood_detector.decision_function(scaled)[0])
    ood_label = int(ood_detector.predict(scaled)[0] == -1)
    risk_level = _classify(probability, thresholds)

    result = {
        "model_variant": "realtime_native",
        "probability": probability,
        "risk_level": risk_level,
        "risk_interpretation": _risk_interpretation(risk_level, engineered.diagnostics),
        "recommended_action": _recommended_action(risk_level),
        "risk_thresholds": thresholds,
        "bmkg_forecast": bmkg_forecast,
        "ood_detection": {
            "method": "IsolationForest",
            "score": ood_score,
            "is_outlier": bool(ood_label),
        },
        "features": features.iloc[0].to_dict(),
        "diagnostics": engineered.diagnostics,
        "model_name": model_card.get("model_name"),
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
