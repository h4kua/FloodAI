import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

from agents.perception_agent import PerceptionAgent
from agents.reasoning_agent import _base_confidence, _outlier_capped_confidence
from realtime_native.bundle import load_runtime_bundle
from realtime_native.feature_builder import (
    REALTIME_NATIVE_FEATURES,
    build_realtime_native_features_from_file,
    build_realtime_native_features_per_kecamatan,
    scored_station_records,
)
from realtime_native.station_kecamatan import STATION_KECAMATAN
from realtime_native.wilayah import JAKARTA_WILAYAH as _JAKARTA_WILAYAH, record_wilayah
from services.adaptive_threshold import AdaptiveThresholder
from services.baseline_check import compare_with_baseline
from services.decision_engine import run_decision_engine
from services.decision_logic import extract_signals
from services.failure_handling import compute_confidence_penalty, detect_failures, detect_ood_escalation
from services.hydrology_analyzer import analyze_hydrology
from services.plausibility_check import score_plausibility
from utils.paths import DEFAULT_REALTIME_SNAPSHOT, REPORTS_DIR

_JAKARTA_TZ = timezone(timedelta(hours=7))
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


# Same sections PerceptionAgent counts for snapshot completeness.
_EXPECTED_SNAPSHOT_SECTIONS = ("fetched_at_utc", "openweather", "poskobanjir", "bmkg_alerts")


def _snapshot_freshness_minutes(snapshot: dict, now=None) -> float:
    """Minutes since the snapshot was fetched; -1.0 when unknown (as PerceptionAgent)."""
    try:
        fetched = datetime.fromisoformat(str(snapshot["fetched_at_utc"]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return -1.0
    ref = now or datetime.now(timezone.utc)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return (ref - fetched).total_seconds() / 60.0


def _live_decision(snapshot, engineered, probability, ood_detection, thresholds, model_card, *, now=None):
    """
    Final citywide risk from the canonical L0–L4 decision engine, the same
    authority /predict/agentic uses. The model probability is one input; the
    water-level, BMKG, OOD and data-quality layers can raise the level (or
    return UNKNOWN on unusable input). Returns (DecisionResult, failure_modes).
    """
    diagnostics = {**engineered.diagnostics, "ood_detection": ood_detection}
    features = {
        **engineered.frame[REALTIME_NATIVE_FEATURES].iloc[0].to_dict(),
        **engineered.diagnostics.get("observed_context", {}),
    }
    plausibility = score_plausibility(snapshot)
    plausibility_score = float(plausibility.get("plausibility_score", 1.0))
    baseline = compare_with_baseline(probability, features)
    failures = detect_failures(
        snapshot=snapshot,
        features=features,
        diagnostics=diagnostics,
        model_prob=probability,
        baseline_result=baseline,
        ood_detection=ood_detection,
        plausibility=plausibility,
        now=now,
    )
    failures.extend(detect_ood_escalation(ood_detection))
    adaptive = AdaptiveThresholder().build_thresholds(
        failure_modes=failures,
        trend_state=diagnostics.get("trend_state") or {},
        plausibility_score=plausibility_score,
    )
    confidence, _, _ = _outlier_capped_confidence(
        confidence=_base_confidence(probability, ood_detection["score"], thresholds),
        is_outlier=ood_detection["is_outlier"],
        model_card=model_card,
    )
    present = sum(1 for s in _EXPECTED_SNAPSHOT_SECTIONS if snapshot.get(s) is not None)
    # Scored posts only: pump and uncalibrated stations have no flood thresholds.
    # The rise rate comes from each post's own previous reading, as in
    # PerceptionAgent, not from the feature history (months old after downtime).
    posts = scored_station_records(snapshot.get("poskobanjir"))
    hydrology = analyze_hydrology(
        posts, water_level_delta=PerceptionAgent()._extract_water_level_delta(snapshot, posts),
    )
    decision = run_decision_engine(
        evaluation_risk_level=_classify(probability, thresholds),
        adjusted_confidence=max(0.05, confidence - compute_confidence_penalty(failures)),
        system_status="OK",
        probability=probability,
        raw_model_confidence=confidence,
        failure_modes=failures,
        baseline_result=baseline,
        signals=extract_signals(features, plausibility_score=plausibility_score),
        diagnostics=diagnostics,
        hydrology_assessment=hydrology,
        plausibility_score=plausibility_score,
        has_critical_violation=bool(plausibility.get("has_critical_violation", False)),
        adaptive_classification=adaptive.to_dict(),
        perception_completeness=present / len(_EXPECTED_SNAPSHOT_SECTIONS),
        data_freshness_minutes=_snapshot_freshness_minutes(snapshot, now),
    )
    return decision, failures


_STATION_KECAMATAN = STATION_KECAMATAN


def _clean_siaga(raw: str) -> str:
    s = raw.replace("Status :", "").replace("Status:", "").strip()
    return s if s else raw


def _station_location_label(station: dict) -> str:
    nama = station.get("nama", "")
    geo = _STATION_KECAMATAN.get(nama)
    if geo:
        return f"{nama} (Kec. {geo['kecamatan']}, {geo['area']})"
    lokasi = station.get("lokasi") or ""
    # The canonical area (realtime_native/wilayah.py) corrects posts DSDA files
    # under the wrong city; the raw file_export is only a fallback.
    wilayah = station.get("wilayah_jakarta") or station.get("wilayah") or ""
    if lokasi and wilayah:
        return f"{nama} ({lokasi}, {wilayah})"
    if wilayah:
        return f"{nama} ({wilayah})"
    return nama


def _risk_interpretation(risk_level, diagnostics, wilayah_summary=None, lang="id"):
    """Plain-language reading of the level, in Indonesian (default) or English."""
    en = lang == "en"

    def tr(id_text, en_text):
        return en_text if en else id_text

    bmkg_source = diagnostics.get("bmkg_source", "no_alert")
    temporal_ready = diagnostics.get("temporal_features_ready", False)
    water_level_records = diagnostics.get("water_level_records", 0)
    stations = diagnostics.get("stations_summary") or []

    if risk_level == "UNKNOWN":
        return tr(
            "Data saat ini belum cukup atau tidak wajar untuk menilai risiko banjir secara otomatis. "
            "Ikuti informasi resmi BPBD DKI Jakarta dan BMKG sampai data pulih.",
            "The current data is too sparse or implausible to judge the flood risk automatically. "
            "Follow official updates from BPBD DKI Jakarta and BMKG until the data is back.",
        )

    elevated = [s for s in stations if "Siaga" in s.get("status_siaga", "")]
    elevated.sort(key=lambda s: s.get("ratio", 0), reverse=True)
    top_station = elevated[0] if elevated else None

    normal_wilayah = []
    alert_wilayah = []
    if wilayah_summary:
        for w in wilayah_summary:
            if w.get("worst_rank", 0) >= 2:
                alert_wilayah.append(w)
            elif w.get("tma_count", 0) > 0:
                normal_wilayah.append(w)

    if top_station:
        label = _station_location_label(top_station)
        siaga = _clean_siaga(top_station["status_siaga"])
        height = f"{top_station.get('tinggi_air', 0):.0f} cm"

    if risk_level == "DANGER":
        loc_context = ""
        if top_station:
            loc_context = tr(f" Stasiun {label} mencatat {siaga} dengan TMA {height}.",
                             f" Post {label} reads {siaga} at {height}.")
        if bmkg_source == "observed_alerts" and water_level_records > 0:
            return tr(
                f"Risiko tinggi terdeteksi - sinyal cuaca ekstrem dikonfirmasi alert BMKG "
                f"dan diperkuat kondisi muka air.{loc_context} "
                "Potensi banjir konsisten dengan indikator lapangan, bukan hanya prediksi statistik.",
                f"High risk - extreme weather confirmed by a BMKG alert and backed by the water levels.{loc_context} "
                "The flood risk matches what the posts measure, not only a statistical forecast.",
            )
        return tr(
            f"Risiko tinggi dari kombinasi hujan intens, akumulasi temporal, dan sinyal hidrologi.{loc_context} "
            "Potensi genangan atau banjir meningkat dalam waktu dekat.",
            f"High risk from heavy rain, rain building up over time and the water levels together.{loc_context} "
            "Waterlogging or flooding is getting more likely soon.",
        )

    if risk_level == "WARNING":
        loc_context = ""
        if top_station:
            ratio = f"{top_station.get('ratio', 0):.0%}"
            loc_context = tr(f" {label} di {siaga} (TMA {height}, rasio {ratio} ambang Siaga 1).",
                             f" {label} is at {siaga} ({height}, {ratio} of its Siaga 1 level).")
        elif alert_wilayah:
            names = ", ".join(w["wilayah"] for w in alert_wilayah[:2])
            loc_context = tr(f" Area terdampak: {names}.", f" Areas affected: {names}.")
        if temporal_ready:
            return tr(
                f"Pola mulai mengarah ke banjir dari akumulasi hujan dan perubahan kondisi air.{loc_context} "
                "Belum kritis, tetapi perlu pemantauan lebih rapat.",
                f"Rain building up and changing water levels are starting to point towards flooding.{loc_context} "
                "Not critical yet, but it needs closer watching.",
            )
        return tr(
            f"Sinyal kewaspadaan awal dari cuaca dan hidrologi, bukti temporal belum sepenuhnya kuat.{loc_context} "
            "Cocok untuk siaga operasional, bukan alarm penuh.",
            f"Early warning signs from the weather and the rivers; the trend is not yet clear.{loc_context} "
            "A reason to be ready, not a full alarm.",
        )

    if risk_level == "PRE_ALERT":
        loc_context = ""
        if top_station:
            loc_context = tr(f" {label} mencatat {siaga}.", f" {label} reads {siaga}.")
        return tr(
            f"Ada sinyal awal di atas kondisi normal dari muka air, cuaca, atau data yang tidak biasa.{loc_context} "
            "Belum mengarah ke banjir, tetapi perlu diwaspadai dan dipantau lebih sering.",
            f"Early signs above normal from the water levels, the weather or unusual data.{loc_context} "
            "Not heading for a flood yet, but worth watching more often.",
        )

    monitored_areas = []
    if normal_wilayah:
        monitored_areas = [w["wilayah"] for w in normal_wilayah[:3]]
    loc_context = ""
    if monitored_areas:
        areas = ", ".join(monitored_areas)
        loc_context = tr(f" Sensor di {areas} terpantau normal.", f" Posts in {areas} read normal.")
    elif water_level_records > 0:
        loc_context = tr(f" {water_level_records} stasiun TMA terpantau dalam batas aman.",
                         f" {water_level_records} water-level posts are within safe limits.")
    elevated_note = ""
    if top_station:
        elevated_note = tr(f" Catatan: {label} tercatat {siaga} (TMA {height}) - pantau perkembangan.",
                           f" Note: {label} reads {siaga} ({height}) - keep an eye on it.")
    return tr(
        f"Belum ada indikasi kuat banjir dari kombinasi cuaca, alert resmi, dan kondisi air saat ini.{loc_context}"
        f"{elevated_note} "
        "Monitoring tetap diperlukan karena situasi dapat berubah cepat di wilayah urban padat seperti Jakarta.",
        f"No strong sign of flooding from the weather, official alerts and water levels right now.{loc_context}"
        f"{elevated_note} "
        "Keep checking: conditions can change fast in a dense city like Jakarta.",
    )


def _titlecase_name(name: str) -> str:
    """Normalize all-caps kelurahan/kecamatan names from BNPB records."""
    return " ".join(w.capitalize() for w in (name or "").split())


def _kelurahan_targeted_actions(risk_level: str, wilayah_summary: list) -> list[str]:
    """
    Build kelurahan-specific action items by joining the live worst-affected
    districts (from realtime TMA siaga ranks) with the BNPB 2014-2023
    historical top-kelurahan list. Returns [] when no district crosses the
    siaga threshold for the current risk_level or when bundled history is
    unavailable.

    Threshold per risk_level:
      DANGER  → worst_rank >= 2 (Siaga 3 or worse — evacuation-language enriched)
      WARNING, PRE_ALERT → worst_rank >= 3 (Siaga 2 or worse — monitoring-language only)
      SAFE, UNKNOWN → never enriched (proportional tone)
    """
    if risk_level not in ("PRE_ALERT", "WARNING", "DANGER") or not wilayah_summary:
        return []
    threshold = 2 if risk_level == "DANGER" else 3
    candidates = [
        w for w in wilayah_summary
        if isinstance(w, dict) and w.get("worst_rank", 0) >= threshold
    ]
    if not candidates:
        return []
    candidates.sort(key=lambda w: w.get("worst_rank", 0), reverse=True)

    try:
        from services.historical_context_builder import build_chat_historical_context
    except Exception:
        return []

    targeted: list[str] = []
    for w in candidates[:2]:
        district = w.get("wilayah", "")
        ctx = build_chat_historical_context(district)
        if not ctx:
            continue
        top_kel = ctx.get("top_kelurahan") or []
        names = [_titlecase_name(k.get("name", "")) for k in top_kel[:3] if k.get("name")]
        if not names:
            continue
        max_depth = ctx.get("max_depth_cm") or 0
        kel_phrase = ", ".join(names)
        if risk_level == "DANGER":
            targeted.append(
                f"Prioritaskan evakuasi dan tim lapangan di {district} — kelurahan {kel_phrase} "
                f"adalah titik historis paling rawan (maks {max_depth:.0f} cm)."
            )
        else:  # WARNING / PRE_ALERT
            targeted.append(
                f"Pra-posisi pemantauan di {district} — kelurahan {kel_phrase} "
                "paling sering banjir secara historis. Belum perlu evakuasi."
            )
    return targeted


def _recommended_action(risk_level, wilayah_summary=None):
    if risk_level == "DANGER":
        base = [
            "Aktifkan koordinasi lintas pihak: BPBD/posko lokal, operator pintu air, dan tim lapangan di titik rawan.",
            "Keluarkan peringatan dini terarah untuk wilayah yang memiliki histori genangan atau elevasi rendah.",
            "Prioritaskan pemeriksaan pintu air, saluran utama, dan titik yang menunjukkan kenaikan muka air tercepat.",
        ]
    elif risk_level == "WARNING":
        base = [
            "Naikkan frekuensi monitoring BMKG, OpenWeather, dan Posko Banjir agar eskalasi bisa ditangkap lebih cepat.",
            "Siapkan personel siaga terbatas dan verifikasi kondisi drainase, pompa, atau titik limpasan yang sering bermasalah.",
            "Gunakan status ini untuk komunikasi internal dan kesiapan operasional, belum untuk alarm publik penuh.",
        ]
    elif risk_level == "PRE_ALERT":
        base = [
            "Pantau pembaruan muka air dan cuaca lebih sering; status dapat naik bila hujan berlanjut.",
            "Periksa kesiapan drainase, pompa, dan jalur informasi di titik yang sering tergenang.",
        ]
    elif risk_level == "UNKNOWN":
        return [
            "Data belum memadai untuk penilaian otomatis — ikuti informasi resmi BPBD DKI Jakarta dan BMKG.",
            "Periksa sumber data (Posko Banjir, BMKG, OpenWeather) dan muat ulang snapshot.",
        ]
    else:
        base = [
            "Lanjutkan monitoring rutin dan simpan histori realtime untuk retraining agar model makin akurat dari waktu ke waktu.",
            "Gunakan periode aman ini untuk validasi data, kalibrasi threshold, dan evaluasi kesiapan infrastruktur lokal.",
        ]

    # Targeted recommendations land FIRST so operators see them before the
    # generic playbook. Defensive — never crash live prediction on history-lookup failure.
    try:
        targeted = _kelurahan_targeted_actions(risk_level, wilayah_summary or [])
    except Exception:
        targeted = []
    return targeted + base


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
        w = record_wilayah(rec.get("nama_pintu_air"), rec.get("file_export"))
        if w:
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
    snapshot_raw: dict = {}
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

    # Additive per-kecamatan breakdown — does NOT influence the citywide
    # probability/risk_level above. Fail-open: a broken breakdown must never
    # take down the primary prediction.
    try:
        district_risk_breakdown = predict_per_kecamatan(snapshot_raw) if snapshot_raw else {}
    except Exception:
        district_risk_breakdown = {}

    engineered = build_realtime_native_features_from_file(
        snapshot_path=snapshot_path, persist_history=persist_history, as_of=as_of,
    )
    features = engineered.frame[REALTIME_NATIVE_FEATURES]
    scaled = scaler.transform(features)
    probability = float(model.predict_proba(scaled)[0, 1])
    ood_score = float(ood_detector.decision_function(scaled)[0])
    ood_detection = {
        "method": "IsolationForest",
        "score": ood_score,
        "is_outlier": bool(ood_detector.predict(scaled)[0] == -1),
    }
    model_risk_level = _classify(probability, thresholds)
    decision, failure_modes = _live_decision(
        snapshot_raw, engineered, probability, ood_detection, thresholds, model_card, now=as_of,
    )
    risk_level = decision.risk_level

    result = {
        "model_variant": "realtime_native",
        # Raw model probability; the final level comes from the decision engine.
        "probability": probability,
        "risk_level": risk_level,
        "confidence_score": decision.confidence_score,
        # Which layer set the level and why — the model's own view is kept so
        # the UI and audits can see when a safety floor overrode it.
        "decision": {
            "layer": decision.override_trace.get("authority", ""),
            "source": decision.decision_source,
            "reason": decision.final_reason,
            "system_status": decision.system_status,
            "model_risk_level": model_risk_level,
            "failure_modes": [f.get("type") for f in failure_modes],
            "trace": decision.decision_trace,
        },
        "risk_interpretation": _risk_interpretation(risk_level, engineered.diagnostics, wilayah_summary),
        "risk_interpretation_en": _risk_interpretation(risk_level, engineered.diagnostics, wilayah_summary, lang="en"),
        "recommended_action": _recommended_action(risk_level, wilayah_summary),
        "risk_thresholds": thresholds,
        # ISO-8601 UTC timestamp when the sensor snapshot was built.
        # Lets the frontend show "Data sensor dari XX:XX WIB" so users know
        # how fresh the underlying TMA/BMKG/OpenWeather data actually is.
        "snapshot_fetched_at": snapshot_fetched_at,
        "bmkg_forecast": bmkg_forecast,
        "ood_detection": ood_detection,
        "features": {**features.iloc[0].to_dict(), **engineered.diagnostics.get("observed_context", {})},
        "diagnostics": engineered.diagnostics,
        "model_name": model_card.get("model_name"),
        # Real DSDADKI station readings — sourced directly from sensor snapshot,
        # NOT derived from ML model output. Empty list when no stations are active.
        "stations": engineered.diagnostics.get("stations_summary", []),
        "wilayah_summary": wilayah_summary,
        "openweather_current": openweather_current,
        "openweather_wilayah": openweather_wilayah,
        # Per-kecamatan ML probability — additive, does not affect risk_level/
        # probability above. {} when no station maps to any active kecamatan.
        "district_risk_breakdown": district_risk_breakdown,
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


def predict_per_kecamatan(snapshot: dict) -> dict[str, dict]:
    """
    Score every kecamatan that has at least one active, mapped water-level
    station in this snapshot, using the same trained model/threshold bundle as
    the citywide prediction — additive capability, does not touch or replace
    predict_realtime_native()'s citywide risk_level/probability.

    Kecamatan with zero mapped/active stations are omitted (never fabricated).
    """
    model, scaler, _ood_detector, _model_card, thresholds = _load_assets()

    results: dict[str, dict] = {}
    kecamatan_names = sorted({geo["kecamatan"] for geo in STATION_KECAMATAN.values()})
    for kecamatan in kecamatan_names:
        engineered = build_realtime_native_features_per_kecamatan(snapshot, kecamatan)
        if engineered is None:
            continue
        features = engineered.frame[REALTIME_NATIVE_FEATURES]
        scaled = scaler.transform(features)
        probability = float(model.predict_proba(scaled)[0, 1])
        risk_level = _classify(probability, thresholds)
        results[kecamatan] = {
            "probability": round(probability, 4),
            "risk_level": risk_level,
            "stations_used": engineered.diagnostics["stations_used"],
        }
    return results
