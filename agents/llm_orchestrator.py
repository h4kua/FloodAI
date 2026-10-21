"""
LLM Orchestrator — Bahasa Indonesia explanation layer for flood predictions.

Takes a structured prediction dict from FloodDecisionPipeline and asks Claude
to produce a citizen-facing + field-officer explanation in Bahasa Indonesia
that is direct, active, and human — not bureaucratic.

On any Claude failure (missing key, timeout, parse error, config error) the
function falls back to a deterministic template so the API endpoint NEVER
crashes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from config.llm_config import LLMConfigError, get_llm_config

_log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 700        # bumped from 600 — richer prompt needs a bit more room
DEFAULT_TIMEOUT_S = 20.0

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
# Design philosophy:
#   1. Positive examples    — show the tone we want
#   2. Negative examples    — explicitly ban bureaucratic register
#   3. Per-status framing   — tell Claude the emotional register per level
#   4. Forbidden words list — Claude respects explicit prohibition lists
#   5. JSON contract last   — keeps the format instruction visually isolated
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Kamu adalah sistem peringatan banjir Jakarta yang berbicara langsung
kepada warga dan petugas lapangan — bukan menulis laporan dinas.

════════════════════════════════════════
ATURAN BAHASA — WAJIB DIIKUTI
════════════════════════════════════════

① KALIMAT PENDEK DAN AKTIF
   - Maksimal 15 kata per kalimat.
   - Gunakan kata kerja aktif: "evakuasi", "tutup", "hubungi", "naikan",
     "buka posko", "cek sensor" — bukan bentuk pasif "-kan" atau "-i".
   - Sebut nama wilayah secara spesifik (gunakan nilai field "lokasi_detail").

② LARANGAN KERAS — jangan gunakan kata-kata ini sama sekali:
   berdasarkan | terdapat | diketahui | dilaksanakan | dikoordinasikan
   diimplementasikan | signifikan | optimal | komprehensif | proaktif
   instansi terkait | mengacu pada | dalam rangka | sehubungan dengan
   perlu diantisipasi | kondisi yang memerlukan | respons komprehensif

③ JANGAN mulai kalimat dengan:
   "Berdasarkan…", "Terdapat…", "Diketahui bahwa…", "Sistem mendeteksi…"

④ NADA PER STATUS — PROPORSIONAL, jangan berlebihan:
   • AMAN    → tenang, singkat. "Tidak perlu khawatir."
               JANGAN sebut evakuasi, tas darurat, atau pindahkan barang.
   • WASPADA → waspada tapi BELUM panik. Hujan deras terjadi tapi AIR BELUM MASUK rumah.
               Langkah: cek drainase, siapkan senter, pantau info RT/RW.
               JANGAN suruh evakuasi. JANGAN suruh pindahkan barang ke lantai atas.
               JANGAN suruh siapkan tas siaga — itu reaksi berlebihan untuk WASPADA.
   • BAHAYA  → ada nyawa yang terancam SEKARANG. Setiap detik penting.
               BARU DI SINI boleh: evakuasi, tas darurat, pindahkan dokumen/barang.
               Gunakan kalimat perintah langsung tanpa basa-basi.

⑤ LOKASI SPESIFIK & KEDALAMAN
   - Selalu sebut nama wilayah/kelurahan/kecamatan yang spesifik (dari field "lokasi_detail").
   - Kalau ada data historis (field "historical_context"), sebutkan estimasi kedalaman
     banjir yang mungkin terjadi. Contoh: "Banjir di sini biasanya 50–100 cm."
   - Sebutkan nama sungai/kali yang relevan jika ada di data.
   - Sebutkan dampak historis singkat jika relevan (berapa jiwa terdampak sebelumnya).

════════════════════════════════════════
CONTOH KALIMAT YANG BENAR ✓
════════════════════════════════════════

STATUS AMAN:
  penjelasan → "Air sungai di Jakarta Utara masih jauh di bawah batas aman.
                Curah hujan rendah dan tidak ada tanda-tanda peningkatan.
                Warga tidak perlu khawatir saat ini."
  tindakan   → ["Pantau sensor curah hujan setiap 30 menit",
                "Pastikan got dan saluran drainase tidak mampet",
                "Catat nomor posko banjir terdekat"]
  petugas    → "Pantau sensor tiap 30 menit — tidak ada aksi darurat."

STATUS WASPADA:
  penjelasan → "Hujan deras turun di Jakarta Timur, terutama sekitar Kec. Jatinegara.
                Air di Kali Ciliwung naik tapi masih di bawah batas siaga.
                Pantau terus info dari RT/RW — belum perlu evakuasi."
  tindakan   → ["Cek saluran air dan drainase di sekitar rumah — pastikan tidak mampet",
                "Siapkan senter dan power bank untuk jaga-jaga listrik padam",
                "Pantau info dari RT/RW dan status sensor tiap 30 menit"]
  petugas    → "Pantau sensor tiap 15 menit, hubungi RT/RW rawan, belum perlu buka posko."
  CATATAN    → Di WASPADA, JANGAN suruh warga evakuasi, pindahkan barang ke lantai atas,
               atau siapkan tas darurat. Itu reaksi berlebihan — simpan untuk BAHAYA.

STATUS BAHAYA:
  penjelasan → "Air Kali Ciliwung sudah melewati batas bahaya di Kampung Melayu.
                Dari data historis, banjir di sini bisa mencapai 1–2 meter.
                Tinggalkan rumah sekarang — pergi ke GOR Jatinegara atau titik evakuasi terdekat."
  tindakan   → ["EVAKUASI sekarang — bawa KTP, obat rutin, dan anak-anak lebih dulu",
                "Jauhi Kali Ciliwung dan saluran air yang sudah meluap",
                "Hubungi 112 atau BPBD 117 jika butuh bantuan evakuasi"]
  petugas    → "Evakuasi paksa Kampung Melayu dan Bidara Cina — air naik cepat, jangan tunda!"

════════════════════════════════════════
CONTOH KALIMAT YANG SALAH ✗ (jangan tiru)
════════════════════════════════════════

  ✗ "Berdasarkan data sensor, terdapat indikasi peningkatan debit air
     yang perlu diantisipasi oleh instansi terkait."
  ✗ "Sistem mendeteksi kondisi yang memerlukan respons komprehensif
     dari seluruh pemangku kepentingan."
  ✗ "Direkomendasikan untuk melaksanakan protokol evakuasi secara
     terkoordinasi dengan pihak berwenang setempat."
  ✗ "Terdapat signifikansi peningkatan curah hujan yang berpotensi
     menimbulkan dampak bagi masyarakat di wilayah terdampak."

════════════════════════════════════════
FORMAT OUTPUT — JSON TANPA MARKDOWN
════════════════════════════════════════

Balas HANYA dengan JSON berikut. Tidak ada teks sebelum atau sesudah JSON.
Tidak ada backtick. Tidak ada markdown. Langsung buka kurung kurawal.

{
  "status_banjir": "AMAN" | "WASPADA" | "BAHAYA",
  "penjelasan": "2–3 kalimat singkat dan langsung untuk warga umum",
  "tindakan": [
    "tindakan konkret pertama — kata kerja aktif, spesifik",
    "tindakan konkret kedua — kata kerja aktif, spesifik",
    "tindakan konkret ketiga — kata kerja aktif, spesifik"
  ],
  "populasi_terdampak": "angka estimasi jiwa jika ada di data, atau null",
  "tingkat_kepercayaan": "persentase kepercayaan sistem, misal 72%",
  "pesan_petugas": "1 kalimat perintah langsung untuk petugas lapangan"
}
"""

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = (
    "status_banjir",
    "penjelasan",
    "tindakan",
    "populasi_terdampak",
    "tingkat_kepercayaan",
    "pesan_petugas",
)

_WARNING_RISK_LEVELS = {"WARNING", "PRE_ALERT"}
_DANGER_RISK_LEVELS  = {"DANGER", "CRITICAL"}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _risk_to_status(risk_level: str) -> str:
    risk = (risk_level or "").upper()
    if risk in _DANGER_RISK_LEVELS:
        return "BAHAYA"
    if risk in _WARNING_RISK_LEVELS:
        return "WASPADA"
    if risk == "SAFE":
        return "AMAN"
    return "WASPADA"  # safe default for unknown values


def _format_confidence(confidence: Any) -> str:
    try:
        pct = round(float(confidence) * 100)
    except (TypeError, ValueError):
        return "0%"
    return f"{pct}%"


def _extract_district(prediction: dict) -> str:
    diagnostics = prediction.get("diagnostics") or {}
    if isinstance(diagnostics, dict):
        district = diagnostics.get("district") or diagnostics.get("location")
        if isinstance(district, str) and district.strip():
            return district
    location = prediction.get("location")
    if isinstance(location, str) and location.strip():
        return location
    return "Jakarta"


def _extract_population(prediction: dict) -> str | None:
    diagnostics = prediction.get("diagnostics") or {}
    if isinstance(diagnostics, dict):
        bnpb = diagnostics.get("bnpb_context") or {}
        if isinstance(bnpb, dict):
            pop = bnpb.get("affected_population") or bnpb.get("population")
            if isinstance(pop, (int, float)) and pop > 0:
                return f"{int(pop):,} jiwa".replace(",", ".")
    return None


def _feature_float(features: dict, key: str) -> float | None:
    try:
        value = features.get(key)
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _describe_observed_conditions(prediction: dict) -> str:
    """
    One factual sentence about rain and river level, built only from the
    prediction's own features. Returns "" when the data is missing, so the
    fallback text never claims rain or rising water the sensors don't show.
    """
    features = prediction.get("features") or {}
    if not isinstance(features, dict):
        return ""
    rain  = _feature_float(features, "rainfall_mm")
    ratio = _feature_float(features, "water_level_ratio")
    delta = _feature_float(features, "water_level_delta")

    parts: list[str] = []
    if rain is not None:
        if rain >= 20:
            parts.append(f"hujan deras ({rain:.0f} mm/jam)")
        elif rain >= 5:
            parts.append(f"hujan sedang ({rain:.0f} mm/jam)")
        elif rain > 0:
            parts.append("hujan ringan")
        else:
            parts.append("saat ini tidak hujan")
    if ratio is not None:
        water = f"air sungai {ratio * 100:.0f}% dari batas siaga"
        if delta is not None and delta > 0.015:
            water += " dan sedang naik"
        elif delta is not None and delta < -0.015:
            water += " dan mulai turun"
        parts.append(water)

    if not parts:
        return ""
    sentence = ", ".join(parts)
    return sentence[0].upper() + sentence[1:] + "."


# ---------------------------------------------------------------------------
# Deterministic fallback — never calls Claude
# ---------------------------------------------------------------------------


def _fallback_explanation(prediction: dict) -> dict:
    """
    Return a hard-coded, register-appropriate Bahasa Indonesia explanation
    derived purely from the prediction's risk_level. Used when Claude is
    unavailable or returns an invalid response.
    """
    risk_level = str(prediction.get("risk_level") or "UNKNOWN").upper()
    status     = _risk_to_status(risk_level)
    confidence = _format_confidence(prediction.get("confidence_score"))
    district   = _extract_district(prediction)
    population = _extract_population(prediction)
    observed   = _describe_observed_conditions(prediction)
    observed   = f" {observed}" if observed else ""

    hist_depth = ""
    try:
        from services.historical_context_builder import build_chat_historical_context
        hist = build_chat_historical_context(district)
        if hist and hist.get("avg_depth_cm"):
            avg = hist["avg_depth_cm"]
            mx = hist.get("max_depth_cm", 0)
            hist_depth = f" Dari data historis, banjir di sini biasanya {avg:.0f}–{mx:.0f} cm."
    except Exception:
        pass

    if status == "BAHAYA":
        penjelasan = (
            f"Risiko banjir di {district} sangat tinggi.{observed} "
            f"Tinggalkan rumah sekarang — jangan tunggu air masuk.{hist_depth} "
            "Pergi ke titik evakuasi terdekat."
        )
        tindakan = [
            "EVAKUASI sekarang — bawa KTP, obat rutin, dan anak-anak lebih dulu",
            "Jauhi saluran air, got terbuka, dan bantaran kali yang meluap",
            "Hubungi 112 atau BPBD 117 jika butuh bantuan evakuasi",
        ]
        pesan_petugas = (
            f"Evakuasi paksa di {district} — air naik cepat, jangan tunda!"
        )

    elif status == "WASPADA":
        penjelasan = (
            f"Ada tanda risiko banjir di {district}.{observed} "
            "Belum berbahaya, tapi bisa berubah dalam 1–2 jam ke depan. "
            "Pantau terus info dari RT/RW — belum perlu evakuasi."
        )
        tindakan = [
            "Cek saluran air dan drainase di sekitar rumah — pastikan tidak mampet",
            "Siapkan senter dan power bank untuk jaga-jaga listrik padam",
            "Pantau info dari RT/RW dan status sensor tiap 30 menit",
        ]
        pesan_petugas = (
            f"Pantau sensor {district} tiap 15 menit, hubungi RT/RW rawan — belum perlu buka posko."
        )

    else:  # AMAN
        penjelasan = (
            f"Kondisi di {district} aman.{observed} "
            "Warga tidak perlu khawatir saat ini."
        )
        tindakan = [
            "Pantau sensor curah hujan setiap 30 menit via aplikasi BPBD",
            "Pastikan got dan saluran drainase di sekitar rumah tidak mampet",
            "Catat dan simpan nomor posko banjir terdekat untuk jaga-jaga",
        ]
        pesan_petugas = (
            "Pantau sensor tiap 30 menit — tidak ada aksi darurat yang diperlukan."
        )

    return {
        "status_banjir":       status,
        "penjelasan":          penjelasan,
        "tindakan":            tindakan,
        "populasi_terdampak":  population,
        "tingkat_kepercayaan": confidence,
        "pesan_petugas":       pesan_petugas,
    }


# ---------------------------------------------------------------------------
# Claude response parsing & validation
# ---------------------------------------------------------------------------


def _parse_claude_json(text: str) -> dict | None:
    """Extract JSON from Claude's raw text, tolerating minor formatting noise."""
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _validate_explanation_shape(payload: object) -> dict | None:
    """
    Ensure the parsed JSON has all required keys and correct types.
    Coerces minor type mismatches; returns None if the shape is fundamentally wrong.
    """
    if not isinstance(payload, dict):
        return None
    for key in _REQUIRED_KEYS:
        if key not in payload:
            return None

    tindakan = payload.get("tindakan")
    if not isinstance(tindakan, list) or not tindakan:
        return None
    payload["tindakan"] = [str(item) for item in tindakan]

    for str_key in ("status_banjir", "penjelasan", "tingkat_kepercayaan", "pesan_petugas"):
        if not isinstance(payload[str_key], str):
            payload[str_key] = str(payload[str_key])

    payload["status_banjir"] = payload["status_banjir"].upper()

    pop = payload.get("populasi_terdampak")
    if pop is not None and not isinstance(pop, str):
        payload["populasi_terdampak"] = str(pop)

    return payload


# ---------------------------------------------------------------------------
# User message builder
# ---------------------------------------------------------------------------


def _build_user_message(prediction: dict) -> str:
    """
    Serialise the subset of prediction fields that Claude needs.
    Includes `lokasi_detail` so Claude uses the specific district name
    rather than writing generic location-free sentences. Also includes
    historical flood context (depths, rivers, affected kelurahan) so the
    explanation is grounded in real data.
    """
    district = _extract_district(prediction)
    safe_fields: dict[str, Any] = {
        "lokasi_detail":          district,
        "risk_level":             prediction.get("risk_level"),
        "confidence_score":       prediction.get("confidence_score"),
        "probability":            prediction.get("probability"),
        "dominant_risk_driver":   prediction.get("dominant_risk_driver"),
        "risk_interpretation":    prediction.get("risk_interpretation"),
        "decision_reason":        prediction.get("decision_reason"),
        "trend_analysis":         prediction.get("trend_analysis"),
        "recommended_action":     prediction.get("recommended_action"),
        "data_freshness_minutes": prediction.get("data_freshness_minutes"),
    }
    try:
        from services.historical_context_builder import build_historical_briefing
        hist = build_historical_briefing(district)
        if hist:
            safe_fields["historical_context"] = hist
    except Exception:
        pass
    return json.dumps(safe_fields, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Synchronous Claude call (run inside asyncio.to_thread)
# ---------------------------------------------------------------------------


def _call_claude_sync(
    user_content: str,
    *,
    model: str,
    max_tokens: int,
) -> str:
    from anthropic import Anthropic

    cfg    = get_llm_config()
    client = Anthropic(
        api_key=cfg.require_anthropic(),
        timeout=DEFAULT_TIMEOUT_S,
        max_retries=2,
    )
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Synchronous Groq call (OpenAI-compatible; run inside asyncio.to_thread)
# ---------------------------------------------------------------------------


def _call_groq_sync(
    prompt: str,
    system: str = "",
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
    )
    model = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if max_tokens is None:
        max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,  # low for consistent JSON output
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Provider dispatcher — routes to Groq (default) or Anthropic
# ---------------------------------------------------------------------------


def _call_llm_sync(
    user_content: str,
    *,
    model: str,
    max_tokens: int,
) -> str:
    """
    Route the synchronous LLM call based on LLM_PROVIDER ("groq" | "anthropic").

    Groq is the default. The Anthropic ``model`` is only meaningful on the
    anthropic branch; the groq branch uses GROQ_MODEL. Both paths receive the
    same SYSTEM_PROMPT and max_tokens for output parity.
    """
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    if provider == "groq":
        return _call_groq_sync(user_content, system=SYSTEM_PROMPT, max_tokens=max_tokens)
    return _call_claude_sync(user_content, model=model, max_tokens=max_tokens)


# ---------------------------------------------------------------------------
# Public async entry point
# ---------------------------------------------------------------------------


async def explain_flood_prediction(prediction: dict) -> dict:
    """
    Ask Claude to translate a raw flood prediction dict into a Bahasa
    Indonesia citizen-facing explanation.

    Returns a dict with six guaranteed keys:
        status_banjir, penjelasan, tindakan, populasi_terdampak,
        tingkat_kepercayaan, pesan_petugas

    NEVER raises — falls back to _fallback_explanation() on any error.
    """
    if not isinstance(prediction, dict):
        prediction = {}

    model = os.getenv("ANTHROPIC_EXPLAIN_MODEL", DEFAULT_MODEL)
    try:
        max_tokens = int(os.getenv("ANTHROPIC_EXPLAIN_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))
    except ValueError:
        max_tokens = DEFAULT_MAX_TOKENS

    try:
        user_content = _build_user_message(prediction)
        raw_text     = await asyncio.to_thread(
            _call_llm_sync, user_content, model=model, max_tokens=max_tokens
        )
        parsed    = _parse_claude_json(raw_text)
        validated = _validate_explanation_shape(parsed)
        if validated is None:
            _log.warning(
                "claude_explain_invalid_shape model=%s raw_len=%d",
                model, len(raw_text or ""),
            )
            return _fallback_explanation(prediction)
        return validated

    except LLMConfigError as exc:
        _log.warning("claude_explain_config_error: %s", exc)
        return _fallback_explanation(prediction)
    except ImportError as exc:
        _log.warning("claude_explain_sdk_missing: %s", exc)
        return _fallback_explanation(prediction)
    except Exception as exc:  # noqa: BLE001 — intentional broad catch; must not propagate
        _log.warning(
            "claude_explain_failed error_type=%s msg=%s",
            type(exc).__name__, exc,
        )
        return _fallback_explanation(prediction)
