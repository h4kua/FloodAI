from __future__ import annotations
import json
import os
import logging
from functools import lru_cache
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.ip_rate_limit import require_chat_rate_limit
from config.llm_config import DEFAULT_GROQ_MODEL
from utils.paths import DEFAULT_REALTIME_SNAPSHOT, REPORTS_DIR

_log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

_MAX_HISTORY_MESSAGES = 10
_MAX_MESSAGE_CHARS = 1800
_MAX_SYSTEM_CHARS = 12000
_MAX_CONTEXT_CHARS = 5000
_PREDICTION_PATH = REPORTS_DIR / "latest_realtime_native_prediction.json"

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
        "or trapped users give immediate actions and emergency numbers BPBD 117, Basarnas 115, DKI 112.\n\n"
        "PROPORTIONAL TONE — match urgency to actual risk level:\n"
        "- AMAN/Normal: calm, brief. Do NOT mention evacuation, emergency bags, or moving belongings.\n"
        "- WASPADA/Warning: alert but NOT panicking. Rain is heavy but water has NOT entered homes yet. "
        "Suggest: check drains, prepare flashlight, monitor RT/RW updates. "
        "Do NOT suggest evacuation, packing emergency bags, or moving valuables upstairs — that's overreacting.\n"
        "- BAHAYA/Danger: lives at risk NOW. Only here: evacuation, emergency bags, move documents.\n\n"
        "LOCATION SPECIFICITY: always mention specific kelurahan, kecamatan, or river names when available.\n"
        "DEPTH ESTIMATES: when historical data is available, mention typical flood depths (e.g. '50-100 cm').\n"
        "HISTORICAL CONTEXT: reference past flood frequency and impact when it helps the user understand risk."
    )


def _sanitize_history(history: list[dict]) -> list[dict]:
    clean: list[dict] = []
    for item in history[-_MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = _clip(item.get("content"), _MAX_MESSAGE_CHARS)
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
            "risk_level": prediction.get("risk_level"),
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
            "Give next actions before explanation for emergency-sounding messages.",
            "When mentioning flood risk, reference historical_flood_data for depth estimates and affected areas.",
            "Be PROPORTIONAL: WASPADA means alert, NOT panic. Don't suggest evacuation for WASPADA status.",
            "BREVITY: match answer length to question complexity. Simple question = 1-2 sentences. Do NOT pad with unrequested context.",
        ],
    }
    return json.dumps(context, ensure_ascii=False, separators=(",", ":"))[:_MAX_CONTEXT_CHARS]


@router.get("/api/chat/health")
async def chat_health() -> dict:
    """Returns whether the Groq API key is configured."""
    configured = bool(os.getenv("GROQ_API_KEY"))
    return {"groq_configured": configured}


# Rate-limited per IP: each message spends Groq quota. The frontend falls back
# to its offline knowledge base on 429.
@router.post("/api/chat", dependencies=[Depends(require_chat_rate_limit)])
async def chat_endpoint(req: ChatRequest) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")
    try:
        client = _get_groq_client()
        messages = []
        system_parts = [_static_jakarta_knowledge()]
        if req.system:
            system_parts.append(_clip(req.system, _MAX_SYSTEM_CHARS))
        system_parts.append("Retrieved realtime context JSON:\n" + _build_retrieved_context(req))
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.extend(_sanitize_history(req.history))
        messages.append({"role": "user", "content": _clip(req.message, _MAX_MESSAGE_CHARS)})
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=800,
            timeout=28.0,
        )
        return {"reply": response.choices[0].message.content}
    except Exception as exc:
        _log.error("chat_endpoint_failed: %s", exc)
        raise HTTPException(status_code=500, detail="chat_failed") from exc
