"""
FloodAnalysisCrew — Multi-agent CrewAI crew for flood risk analysis.

Three specialized agents collaborate sequentially to produce a Bahasa Indonesia
flood risk report that is richer than the single-pass LLM in llm_orchestrator.py:

  1. AhliCuaca      — Analyzes rainfall, BMKG alerts, atmospheric conditions
  2. AhliHidrologi  — Analyzes water levels, siaga stations, hydrological trends
  3. KoordinatorRisiko — Synthesizes all signals into the final structured report

NEVER raises — falls back to _fallback_crew_output() on any error so the calling
endpoint always returns a valid response.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

# Module-level import so _fallback_crew_output() doesn't hit the import lock
# on every call (deferred imports inside hot fallback paths cause lock contention).
from agents.llm_orchestrator import _fallback_explanation

_log = logging.getLogger(__name__)

# All keys that the coordinator MUST produce — including the expert summaries.
# Absent keys trigger fallback; callers can depend on these always being present.
_REQUIRED_KEYS = (
    "status_banjir",
    "penjelasan",
    "tindakan",
    "populasi_terdampak",
    "tingkat_kepercayaan",
    "pesan_petugas",
    "analisis_cuaca",
    "analisis_hidrologi",
)


# ---------------------------------------------------------------------------
# Context builders — extract relevant fields for each agent's briefing
# ---------------------------------------------------------------------------


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _build_weather_context(snapshot: dict, prediction: dict) -> str:
    features = prediction.get("features") or {}
    ow = (snapshot.get("openweather") or {}).get("main") or {}
    rain_block = (snapshot.get("openweather") or {}).get("rain") or {}

    rain_1h = _safe_float(features.get("rainfall_mm") or rain_block.get("1h"))
    rain_3h = _safe_float(features.get("rainfall_3h_proxy_mm"))
    humidity = _safe_float(features.get("humidity_pct") or ow.get("humidity"))
    temperature = _safe_float(features.get("temperature_c") or ow.get("temp"))
    bmkg_score = _safe_float(features.get("bmkg_weighted_score"))
    monsoon = int(features.get("monsoon_season") or 0)

    alerts = snapshot.get("bmkg_alerts") or []
    alert_lines: list[str] = []
    for a in alerts[:3]:
        if isinstance(a, dict) and a.get("headline"):
            severity = a.get("severity") or "-"
            certainty = a.get("certainty") or "-"
            alert_lines.append(
                f"  - {a['headline']} (Severity: {severity}, Certainty: {certainty})"
            )

    lines = [
        f"Curah hujan 1 jam   : {rain_1h:.1f} mm",
        f"Curah hujan 3 jam   : {rain_3h:.1f} mm",
        f"Kelembaban          : {humidity:.0f}%",
        f"Suhu udara          : {temperature:.1f}°C",
        f"BMKG weighted score : {bmkg_score:.3f}",
        f"Musim hujan aktif   : {'Ya' if monsoon else 'Tidak'}",
    ]
    if alert_lines:
        lines.append("Alert BMKG:")
        lines.extend(alert_lines)

    return "\n".join(lines)


def _build_hydrology_context(snapshot: dict, prediction: dict) -> str:
    features = prediction.get("features") or {}

    water_ratio = _safe_float(features.get("water_level_ratio"))
    water_delta = _safe_float(features.get("water_level_delta"))
    water_lag1 = _safe_float(features.get("water_level_lag_1"))
    hydro_index = _safe_float(features.get("hydro_meteorological_index"))

    stations = snapshot.get("poskobanjir") or []
    station_lines: list[str] = []
    for s in stations[:6]:
        if isinstance(s, dict):
            wilayah = s.get("wilayah") or s.get("station_name") or "Unknown"
            tinggi = s.get("tinggi_air") or s.get("tinggi_air_cm") or 0
            status = s.get("status") or s.get("siaga_level") or "Normal"
            station_lines.append(f"  - {wilayah}: {tinggi} cm ({status})")

    lines = [
        f"Water level ratio   : {water_ratio:.3f}  (>=0.90 = SIAGA kritis)",
        f"Water level delta   : {water_delta:+.3f}  (positif = naik)",
        f"Water level lag-1   : {water_lag1:.3f}",
        f"Hydro-meteor index  : {hydro_index:.3f}",
    ]
    if station_lines:
        lines.append("Data stasiun PDA:")
        lines.extend(station_lines)

    return "\n".join(lines)


def _build_ml_context(prediction: dict) -> str:
    risk_level = prediction.get("risk_level") or "UNKNOWN"
    probability = _safe_float(prediction.get("probability"))
    confidence = _safe_float(prediction.get("confidence_score"))
    driver = prediction.get("dominant_risk_driver") or "unknown"
    interpretation = prediction.get("risk_interpretation") or "-"
    decision_reason = prediction.get("decision_reason") or "-"

    return "\n".join([
        f"Risk level (ML)     : {risk_level}",
        f"Probabilitas banjir : {probability:.3f}  ({probability * 100:.1f}%)",
        f"Confidence score    : {confidence:.3f}",
        f"Dominant driver     : {driver}",
        f"Interpretasi ML     : {interpretation}",
        f"Alasan keputusan    : {decision_reason}",
    ])


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _parse_crew_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _validate_crew_output(data: object) -> dict | None:
    """Return a validated copy of `data`, or None if any required key is missing."""
    if not isinstance(data, dict):
        return None
    for key in _REQUIRED_KEYS:
        if key not in data:
            _log.debug("crew_output_missing_key key=%s", key)
            return None
    tindakan = data.get("tindakan")
    if not isinstance(tindakan, list) or not tindakan:
        return None
    # Work on a copy — never mutate the parsed JSON object in place.
    validated: dict = dict(data)
    validated["tindakan"] = [str(t) for t in tindakan]
    for k in ("status_banjir", "penjelasan", "tingkat_kepercayaan", "pesan_petugas",
              "analisis_cuaca", "analisis_hidrologi"):
        if not isinstance(validated.get(k), str):
            validated[k] = str(validated.get(k) or "")
    validated["status_banjir"] = validated["status_banjir"].upper()
    return validated


def _fallback_crew_output(prediction: dict) -> dict:
    """Deterministic fallback — used when the crew fails or is unavailable."""
    result = _fallback_explanation(prediction)
    result["_crew_fallback"] = True
    result["analisis_cuaca"] = None
    result["analisis_hidrologi"] = None
    return result


# ---------------------------------------------------------------------------
# Core synchronous crew execution
# ---------------------------------------------------------------------------


def run_flood_crew(snapshot: dict, prediction: dict) -> dict:
    """
    Run the 3-agent FloodAnalysisCrew synchronously.
    Designed to be called via asyncio.to_thread from async endpoints.

    Returns a dict guaranteed to contain all _REQUIRED_KEYS.
    Never raises — falls back to deterministic template on any failure.
    """
    try:
        from crewai import Agent, Crew, LLM, Process, Task
    except ImportError as exc:
        _log.warning("crewai_import_failed: %s", exc)
        return _fallback_crew_output(prediction)

    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        _log.warning("crew_groq_key_missing — set GROQ_API_KEY to enable crew analysis")
        return _fallback_crew_output(prediction)

    location = (
        prediction.get("location")
        or (prediction.get("diagnostics") or {}).get("district")
        or "Jakarta"
    )

    try:
        # Use groq/ litellm prefix when available, fall back to openai-compatible path.
        # Both point to the same Groq model — litellm is the preferred routing layer.
        try:
            import litellm  # noqa: F401
            llm_model = "groq/llama-3.3-70b-versatile"
            llm_base_url = None
        except ImportError:
            llm_model = "openai/llama-3.3-70b-versatile"
            llm_base_url = "https://api.groq.com/openai/v1"

        llm_kwargs: dict = {
            "model": llm_model,
            "api_key": groq_api_key,
            "temperature": 0.1,
            "max_tokens": 512,
            "timeout": 20,  # per-request HTTP timeout (seconds)
        }
        if llm_base_url:
            llm_kwargs["base_url"] = llm_base_url

        llm = LLM(**llm_kwargs)

        # --- Agents ---

        weather_agent = Agent(
            role="Ahli Cuaca dan Meteorologi Jakarta",
            goal=(
                "Analisis kondisi cuaca, intensitas hujan, dan alert BMKG secara tepat "
                "untuk mendukung keputusan kesiapsiagaan banjir Jakarta."
            ),
            backstory=(
                "Meteorolog senior BMKG dengan 15 tahun pengalaman memantau cuaca "
                "ekstrem Jakarta. Ahli dalam membaca pola monsun, hujan lokal, dan "
                "menerjemahkan alert BMKG ke implikasi risiko banjir nyata."
            ),
            llm=llm,
            verbose=False,
            allow_delegation=False,
        )

        hydrology_agent = Agent(
            role="Ahli Hidrologi Sungai dan Kanal Jakarta",
            goal=(
                "Analisis ketinggian air, status siaga stasiun PDA, dan tren hidrologi "
                "untuk menilai risiko luapan sungai dan kanal di Jakarta."
            ),
            backstory=(
                "Ahli hidrologi Dinas SDA DKI Jakarta yang memantau lebih dari 100 "
                "stasiun PDA setiap hari. Paham dinamika banjir kiriman, pasang laut, "
                "dan kapasitas Ciliwung, Sunter, Banjir Kanal Barat-Timur."
            ),
            llm=llm,
            verbose=False,
            allow_delegation=False,
        )

        risk_coordinator = Agent(
            role="Koordinator Risiko Banjir Pusdalops BPBD DKI Jakarta",
            goal=(
                "Sintesis analisis cuaca dan hidrologi bersama prediksi model ML "
                "menjadi laporan risiko banjir yang akurat dan actionable "
                "dalam Bahasa Indonesia untuk warga dan petugas lapangan."
            ),
            backstory=(
                "Koordinator Pusdalops BPBD DKI Jakarta yang mengoordinasikan respons "
                "banjir besar 2020 dan 2022. Berpengalaman menerjemahkan data teknis "
                "menjadi peringatan dini yang langsung bisa ditindaklanjuti."
            ),
            llm=llm,
            verbose=False,
            allow_delegation=False,
        )

        # --- Build context strings ---
        weather_ctx = _build_weather_context(snapshot, prediction)
        hydro_ctx = _build_hydrology_context(snapshot, prediction)
        ml_ctx = _build_ml_context(prediction)

        # --- Tasks ---

        weather_task = Task(
            description=(
                f"Analisis kondisi atmosfer di {location} berdasarkan data berikut:\n\n"
                f"{weather_ctx}\n\n"
                "Tulis analisis SINGKAT (2-3 kalimat) dalam Bahasa Indonesia. "
                "Sebutkan intensitas hujan, kondisi kelembaban, dan apakah alert BMKG "
                "memperburuk risiko banjir. Gunakan kalimat aktif yang ringkas."
            ),
            expected_output=(
                "Analisis cuaca 2-3 kalimat dalam Bahasa Indonesia tentang "
                "intensitas hujan, kelembaban, dan penilaian alert BMKG."
            ),
            agent=weather_agent,
        )

        hydrology_task = Task(
            description=(
                f"Analisis kondisi hidrologi di {location} berdasarkan data berikut:\n\n"
                f"{hydro_ctx}\n\n"
                "Tulis analisis SINGKAT (2-3 kalimat) dalam Bahasa Indonesia. "
                "Sebutkan water level ratio, status siaga stasiun-stasiun kritis, "
                "dan tren kenaikan atau penurunan air. Gunakan kalimat aktif yang ringkas."
            ),
            expected_output=(
                "Analisis hidrologi 2-3 kalimat dalam Bahasa Indonesia tentang "
                "water level ratio, status siaga stasiun, dan tren air."
            ),
            agent=hydrology_agent,
            context=[weather_task],
        )

        coordinator_task = Task(
            description=(
                f"Berdasarkan analisis cuaca dan hidrologi dari rekan-rekanmu, "
                f"serta data prediksi model ML berikut:\n\n"
                f"{ml_ctx}\n\n"
                f"Lokasi: {location}\n\n"
                "Buat laporan risiko banjir dalam format JSON. "
                "PENTING: Balas HANYA dengan JSON valid — tidak ada teks sebelum atau sesudah.\n\n"
                "{\n"
                '  "status_banjir": "AMAN" atau "WASPADA" atau "BAHAYA",\n'
                '  "penjelasan": "2-3 kalimat untuk warga — kalimat aktif, sebut nama wilayah",\n'
                '  "tindakan": ["aksi 1", "aksi 2", "aksi 3"],\n'
                '  "populasi_terdampak": "estimasi jiwa atau null",\n'
                '  "tingkat_kepercayaan": "misal 72%",\n'
                '  "pesan_petugas": "1 kalimat perintah untuk petugas lapangan",\n'
                '  "analisis_cuaca": "1 kalimat ringkasan analisis cuaca",\n'
                '  "analisis_hidrologi": "1 kalimat ringkasan analisis hidrologi"\n'
                "}\n\n"
                "Aturan wajib:\n"
                "- status_banjir harus sesuai risk_level: SAFE→AMAN, WARNING/PRE_ALERT→WASPADA, DANGER→BAHAYA\n"
                "- Larang kata: berdasarkan, terdapat, diketahui, signifikan, komprehensif\n"
                "- Kalimat maksimal 15 kata — langsung dan aktif\n"
                "- tindakan pakai kata kerja: evakuasi, siapkan, hubungi, pantau, pindahkan\n"
            ),
            expected_output=(
                "JSON valid dengan kunci: status_banjir, penjelasan, tindakan (list 3 item), "
                "populasi_terdampak, tingkat_kepercayaan, pesan_petugas, analisis_cuaca, analisis_hidrologi."
            ),
            agent=risk_coordinator,
            context=[weather_task, hydrology_task],
        )

        # --- Crew ---
        crew = Crew(
            agents=[weather_agent, hydrology_agent, risk_coordinator],
            tasks=[weather_task, hydrology_task, coordinator_task],
            process=Process.sequential,
            verbose=False,
            tracing=False,  # disable telemetry to avoid outbound connection noise
        )

        result = crew.kickoff()
        raw_output = str(result.raw) if hasattr(result, "raw") else str(result)

        parsed = _parse_crew_json(raw_output)
        validated = _validate_crew_output(parsed)

        if validated is None:
            _log.warning(
                "crew_invalid_output raw_len=%d preview=%r",
                len(raw_output),
                raw_output[:200],
            )
            return _fallback_crew_output(prediction)

        validated["_crew_used"] = True
        return validated

    except Exception as exc:  # noqa: BLE001 — intentional broad catch; must not propagate
        # Log only the error type — not str(exc), which may contain partial API
        # key fragments in Groq/litellm authentication error messages.
        _log.warning("crew_failed error_type=%s", type(exc).__name__)
        if _log.isEnabledFor(logging.DEBUG):
            _log.debug("crew_failed detail", exc_info=True)
        return _fallback_crew_output(prediction)
