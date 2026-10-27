from __future__ import annotations
import asyncio
import json
import os
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.ip_rate_limit import require_chat_rate_limit
from config.llm_config import DEFAULT_GROQ_MODEL
from utils.paths import DEFAULT_REALTIME_SNAPSHOT, REPORTS_DIR

_log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# Groq's free tier allows ~8,000 tokens per minute per model. A request used
# to send ~5,000 prompt tokens, so a second question within a minute hit 429
# and the SDK's retries kept the user waiting. The budgets below keep a
# typical request near 1,500 prompt tokens.
_MAX_HISTORY_MESSAGES = 4
_MAX_HISTORY_CHARS = 400          # per earlier message
_MAX_MESSAGE_CHARS = 1800
_MAX_CONTEXT_CHARS = 1800
_MAX_TOPIC_CHARS = 2200           # knowledge sections picked for the question
_MAX_REPLY_TOKENS = 500
_GROQ_TIMEOUT_S = 20.0
_MAX_RETRY_WAIT_S = 3.0        # one wait on Groq's retry-after before answering "busy"
# Tried in order; Groq rate limits are per model, so the fallback has its own budget.
_FALLBACK_MODEL = "openai/gpt-oss-20b"
_PREDICTION_PATH = REPORTS_DIR / "latest_realtime_native_prediction.json"
_KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "chat_knowledge.txt"

# Knowledge sections (by heading prefix) and the words that make them relevant.
_TOPICS = {
    "SINGKATAN LOKASI": ("pik", "jakut", "jakbar", "jaktim", "jaksel", "jakpus", "kampmel", "kamp mel", "k.melayu",
                         "kalder", "kalidrs", "penjar", "penjrng", "cengkrng", "cengkrg", "padam", "pdmgn", "mangdu",
                         "kalgading", "kel gading", "tpi", "sntr", "bsd", "serpong", "bintaro"),
    "JAKARTA FLOOD GEOGRAPHY": ("utara", "barat", "timur", "selatan", "pusat", "wilayah", "daerah", "kecamatan",
                                "kelurahan", "rawan", "north", "west", "east", "south", "area"),
    "ESTIMASI DURASI": ("lama", "durasi", "surut", "berapa jam", "kapan selesai", "how long", "recede"),
    "TITIK PENGUNGSIAN": ("ngungsi", "pengungsian", "shelter", "evakuasi", "posko", "evacuat"),
    "RT/RW RAWAN": ("rt ", "rw ", "rt/rw", "rt0", "rw0"),
    "LANDMARK JAKARTA": ("mall", "rumah sakit", "rs ", "sekolah", "stasiun", "kampus", "hospital", "school", "landmark"),
    "ESTIMASI JARAK": ("jarak", "jauh", " km", "terdekat", "distance", "nearest"),
    "NAMA JALAN": ("jalan", "jl.", "jl ", "rute", "lewat", "tol", "kawasan", "komplek", "sungai", "kali ", "road",
                   "route", "street", "river"),
    "FITUR WEBSITE": ("fitur", "website", "aplikasi", "cara pakai", "cara kerja", "deflood", "halaman", "tombol",
                      "peta", "laporan", "google maps", "panduan", "feature", "app", "how does", "page", "report"),
    "DATA HISTORIS": ("histori", "sejarah", "pernah", "tahun", "berapa tinggi", "kedalaman", "dalam", "dampak",
                      "history", "deep", "depth", "past"),
}

# Module-level client cache — avoids creating a new HTTP connection pool on
# every request. Re-initialised if the API key changes at runtime (rare but
# possible via hot-reloaded secrets in Fly.io/Railway).
_groq_client: object | None = None
_groq_api_key_cached: str = ""


def _get_groq_client():
    global _groq_client, _groq_api_key_cached
    api_key = os.getenv("GROQ_API_KEY", "")
    if _groq_client is None or api_key != _groq_api_key_cached:
        from groq import Groq

        _groq_client = Groq(api_key=api_key)
        _groq_api_key_cached = api_key
    return _groq_client


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)
    system: str = ""
    context: dict = Field(default_factory=dict)
    lang: str = "id"


def _clip(value: object, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _safe_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _read_json(path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _static_jakarta_knowledge() -> str:
    return (
        "Operational guardrails: answer as a Jakarta flood assistant; prioritize BPBD/official "
        "instructions; never claim exact street safety without live ground confirmation; for danger "
        "or trapped users give immediate actions and emergency numbers BPBD 117, Basarnas 115, DKI 112.\n"
        "Answer only the user's last message. Name kelurahan, kecamatan or rivers when the data gives them.\n"
        "FORMAT: short paragraphs and bullet lists only; never tables or HTML."
    )


@lru_cache(maxsize=1)
def _knowledge_sections() -> tuple[list[str], list[str]]:
    """(always-sent sections, topic sections) from chat_knowledge.txt."""
    try:
        text = _KNOWLEDGE_PATH.read_text(encoding="utf-8")
    except OSError:
        _log.warning("chat_knowledge_missing: %s", _KNOWLEDGE_PATH)
        return [], []
    body = "\n".join(line for line in text.splitlines() if not line.startswith("# "))
    parts = [p.strip() for p in re.split(r"\n━{5,}\n", body) if p.strip()]
    if len(parts) < 3:
        return parts, []
    return [parts[0], *parts[-2:]], parts[1:-2]


def _knowledge_for(message: str) -> str:
    """The always-sent rules plus the topic sections the question touches.

    A topic counts when one of its trigger words is in the question (weight 3)
    or when longer words of the question appear in its text (place names).
    """
    core, topics = _knowledge_sections()
    msg = f" {message.lower()} "
    words = {w for w in re.findall(r"[a-z]{5,}", msg)}
    scored = []
    for section in topics:
        head = section.splitlines()[0]
        triggers = next((t for prefix, t in _TOPICS.items() if head.startswith(prefix)), ())
        low = section.lower()
        score = 3 * sum(1 for t in triggers if t in msg) + sum(1 for w in words if w in low)
        if score:
            scored.append((score, section))
    picked, used = [], 0
    for _, section in sorted(scored, key=lambda s: -s[0]):
        if used + len(section) <= _MAX_TOPIC_CHARS:
            picked.append(section)
            used += len(section)
    return "\n\n".join(core + picked)


def _sanitize_history(history: list[dict]) -> list[dict]:
    clean: list[dict] = []
    for item in history[-_MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = _clip(item.get("content"), _MAX_HISTORY_CHARS)
        if content:
            clean.append({"role": role, "content": content})
    return clean


def _top_stations(stations: list[dict], limit: int = 5) -> list[dict]:
    def ratio(station: dict) -> float:
        return _safe_float(station.get("ratio")) or 0.0

    result = []
    for station in sorted((s for s in stations if isinstance(s, dict)), key=ratio, reverse=True)[:limit]:
        result.append({
            "name": station.get("nama") or station.get("nama_pintu_air"),
            "area": station.get("lokasi") or station.get("file_export"),
            "status": station.get("status_siaga"),
            "ratio_pct": round(ratio(station) * 100),
            "height": station.get("tinggi_air"),
        })
    return result


# The app's own words for the engine's levels, so answers never show "PRE_ALERT".
_STATUS_WORDS = {
    "SAFE": "Aman (Safe)", "PRE_ALERT": "Waspada (Watch)", "WARNING": "Siaga (Alert)",
    "DANGER": "Bahaya (Danger)", "UNKNOWN": "Tidak diketahui (Unknown)",
}


def _list_value(value: object) -> list:
    return value if isinstance(value, list) else []


def _build_retrieved_context(req: ChatRequest) -> str:
    prediction = _read_json(_PREDICTION_PATH)
    snapshot = _read_json(DEFAULT_REALTIME_SNAPSHOT)
    frontend = req.context if isinstance(req.context, dict) else {}

    features = prediction.get("features") if isinstance(prediction.get("features"), dict) else {}
    diagnostics = prediction.get("diagnostics") if isinstance(prediction.get("diagnostics"), dict) else {}
    stations = frontend.get("stations") or prediction.get("stations") or []
    wilayah = frontend.get("wilayahSummary") or prediction.get("wilayah_summary") or []
    recommended_actions = _list_value(prediction.get("recommended_action"))

    hist_context = {}
    try:
        from services.historical_context_builder import build_chat_historical_context
        district = (diagnostics.get("district") or prediction.get("location") or "Jakarta")
        if isinstance(district, str) and district.strip():
            hist_context = build_chat_historical_context(district)
    except Exception:
        pass

    context = {
        "assistant_mode": "retrieve_then_answer",
        "language": "Indonesian" if req.lang != "en" else "English",
        "frontend_context": {
            "level": frontend.get("level"),
            "riskScore": frontend.get("riskScore"),
            "rainfall_mm_h": frontend.get("rainfall"),
            "waterLevelRatio": frontend.get("waterLevelRatio"),
            "snapshotFetchedAt": frontend.get("snapshotFetchedAt"),
        },
        "latest_model_context": {
            "status": _STATUS_WORDS.get(str(prediction.get("risk_level") or "").upper(), prediction.get("risk_level")),
            "probability_pct": round((_safe_float(prediction.get("probability")) or 0) * 100),
            "rainfall_mm_h": features.get("rainfall_mm"),
            "rainfall_acc_3h": diagnostics.get("rainfall_acc_3h"),
            "rainfall_acc_6h": diagnostics.get("rainfall_acc_6h"),
            "water_level_ratio": features.get("water_level_ratio"),
            "water_level_delta": features.get("water_level_delta"),
            "bmkg_alerts_total": diagnostics.get("bmkg_alerts_total"),
            "snapshot_fetched_at": prediction.get("snapshot_fetched_at"),
            "recommended_action": recommended_actions[:3],
        },
        "top_tma_stations": _top_stations(stations if isinstance(stations, list) else []),
        "wilayah_summary": [
            {
                "wilayah": item.get("wilayah"),
                "worst_status": item.get("worst_status"),
                "tma_count": item.get("tma_count"),
                "forecast": _list_value(item.get("forecast"))[:3],
            }
            for item in (wilayah if isinstance(wilayah, list) else [])[:6]
            if isinstance(item, dict)
        ],
        "historical_flood_data": hist_context if hist_context else None,
        "snapshot_source": {
            "fetched_at_utc": snapshot.get("fetched_at_utc"),
            "records": (snapshot.get("summary") or {}).get("total_poskobanjir_records")
            if isinstance(snapshot.get("summary"), dict)
            else None,
        },
        "instructions": [
            "Use this context only when relevant to the user's question.",
            "If data timestamps are stale, say 'data terakhir' and avoid pretending it is live.",
            "Quote a post's status exactly as given here; never invent a Siaga level.",
        ],
    }
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))[:_MAX_CONTEXT_CHARS]


@router.get("/api/chat/health")
async def chat_health() -> dict:
    """Returns whether the Groq API key is configured."""
    configured = bool(os.getenv("GROQ_API_KEY"))
    return {"groq_configured": configured}


def _build_messages(req: ChatRequest) -> list[dict]:
    # The server owns the system prompt. ``req.system`` from older clients is
    # ignored: it cost ~5,000 tokens a request and let any caller rewrite the prompt.
    system = "\n\n".join([
        _static_jakarta_knowledge(),
        _knowledge_for(req.message),
        "Retrieved realtime context JSON:\n" + _build_retrieved_context(req),
    ])
    return [
        {"role": "system", "content": system},
        *_sanitize_history(req.history),
        {"role": "user", "content": _clip(req.message, _MAX_MESSAGE_CHARS)},
    ]


def _complete(messages: list[dict]) -> str:
    """Ask the primary model, then the fallback when the first fails.

    The fallback covers a rate limit (429), a withdrawn model (404, as with
    llama-3.3-70b-versatile) and provider errors; a bad key (401) does not
    fall back. No SDK retries: a retry waits for Groq's per-minute window and
    kept users waiting 20–40 s; failing fast lets the next model answer.
    """
    client = _get_groq_client().with_options(max_retries=0)
    models = list(dict.fromkeys([os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL), _FALLBACK_MODEL]))

    def ask(model: str) -> str:
        reasoning = model.startswith("openai/gpt-oss")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=_MAX_REPLY_TOKENS + (300 if reasoning else 0),  # gpt-oss also spends tokens reasoning
            timeout=_GROQ_TIMEOUT_S,
            extra_body={"reasoning_effort": "low"} if reasoning else None,
        )
        return response.choices[0].message.content

    for i, model in enumerate(models):
        try:
            return ask(model)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status != 401 and i + 1 < len(models):
                _log.warning("chat_model_failed model=%s status=%s; trying %s", model, status, models[i + 1])
                continue
            # Last model rate limited: Groq often frees the tokens within a
            # second or two, so one short wait beats telling the user "busy".
            wait = _retry_after_seconds(exc)
            if status == 429 and wait is not None and wait <= _MAX_RETRY_WAIT_S:
                time.sleep(wait)
                return ask(model)
            raise


def _retry_after_seconds(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


# Rate-limited per IP: each message spends Groq quota. The frontend falls back
# to its offline knowledge base on errors and says "busy" on 429.
@router.post("/api/chat", dependencies=[Depends(require_chat_rate_limit)])
async def chat_endpoint(req: ChatRequest) -> dict:
    if not os.getenv("GROQ_API_KEY"):
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")
    try:
        # The Groq client is synchronous; run it off the event loop so one slow
        # answer does not stall every other request.
        reply = await asyncio.to_thread(_complete, _build_messages(req))
        return {"reply": reply}
    except Exception as exc:
        if getattr(exc, "status_code", None) == 429:
            _log.warning("chat_rate_limited: %s", exc)
            raise HTTPException(status_code=429, detail="ai_busy") from exc
        _log.error("chat_endpoint_failed: %s", exc)
        raise HTTPException(status_code=500, detail="chat_failed") from exc
