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

④ NADA PER STATUS — ikuti register emosi berikut:
   • AMAN    → tenang, singkat, tidak lebay. Warga tidak perlu khawatir.
   • WASPADA → waspada tapi belum panik. Hujan deras sedang mendekat.
               Beri tahu warga apa yang harus disiapkan sekarang.
   • BAHAYA  → ada nyawa yang terancam saat ini. Setiap detik penting.
               Gunakan kalimat perintah langsung tanpa basa-basi.

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
  penjelasan → "Hujan deras sedang terjadi dan air di Kanal Barat mulai naik.
                Belum berbahaya, tapi bisa berubah cepat dalam 1–2 jam ke depan.
                Siapkan diri dan pantau terus pengumuman."
  tindakan   → ["Siapkan tas siaga berisi dokumen penting dan obat-obatan",
                "Pindahkan barang berharga ke lantai atas sekarang",
                "Hubungi ketua RT jika air mulai masuk halaman"]
  petugas    → "Buka posko, hubungi RT/RW rawan, siap evakuasi dalam 15 menit."

STATUS BAHAYA:
  penjelasan → "Air sudah melewati batas bahaya di Jakarta Utara.
                Tinggalkan rumah sekarang — jangan tunggu air masuk.
                Pergi ke titik evakuasi terdekat."
  tindakan   → ["EVAKUASI sekarang — bawa dokumen, obat, dan anak-anak",
                "Jauhi saluran air, got, dan kali yang meluap",
                "Hubungi 112 jika butuh bantuan evakuasi"]
  petugas    → "Evakuasi paksa di RW rawan — air naik cepat, jangan tunda!"

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

    if status == "BAHAYA":
        penjelasan = (
            f"Air sudah melewati batas bahaya di {district}. "
            "Tinggalkan rumah sekarang — jangan tunggu air masuk. "
            "Pergi ke titik evakuasi terdekat."
        )
        tindakan = [
            "EVAKUASI sekarang — bawa dokumen, obat, dan anak-anak terlebih dahulu",
            "Jauhi saluran air, got terbuka, dan bantaran kali yang meluap",
            "Hubungi 112 atau posko BPBD jika butuh bantuan evakuasi",
        ]
        pesan_petugas = (
            f"Evakuasi paksa di {district} — air naik cepat, jangan tunda!"
        )

    elif status == "WASPADA":
        penjelasan = (
            f"Hujan deras terjadi dan air di {district} mulai naik. "
            "Belum berbahaya, tapi bisa berubah cepat dalam 1–2 jam ke depan. "
            "Siapkan diri dan pantau terus pengumuman."
        )
        tindakan = [
            "Siapkan tas siaga berisi dokumen penting, obat-obatan, dan pakaian ganti",
            "Pindahkan barang berharga dan elektronik ke lantai atas sekarang",
            "Hubungi ketua RT segera jika air mulai masuk halaman rumah",
        ]
        pesan_petugas = (
            f"Buka posko {district}, hubungi RT/RW rawan, siap evakuasi dalam 15 menit."
        )

    else:  # AMAN
        penjelasan = (
            f"Air sungai di {district} masih jauh di bawah batas aman. "
            "Curah hujan rendah dan tidak ada tanda-tanda peningkatan risiko. "
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
    rather than writing generic location-free sentences.
    """
    district = _extract_district(prediction)
    safe_fields = {
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

    cfg    = get_llm_config(require=["anthropic"])
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
