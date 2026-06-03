from __future__ import annotations
import os
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from groq import Groq

_log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# Module-level client cache — avoids creating a new HTTP connection pool on
# every request. Re-initialised if the API key changes at runtime (rare but
# possible via hot-reloaded secrets in Fly.io/Railway).
_groq_client: Groq | None = None
_groq_api_key_cached: str = ""


def _get_groq_client() -> Groq:
    global _groq_client, _groq_api_key_cached
    api_key = os.getenv("GROQ_API_KEY", "")
    if _groq_client is None or api_key != _groq_api_key_cached:
        _groq_client = Groq(api_key=api_key)
        _groq_api_key_cached = api_key
    return _groq_client


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    system: str = ""


@router.get("/api/chat/health")
async def chat_health() -> dict:
    """Returns whether the Groq API key is configured."""
    configured = bool(os.getenv("GROQ_API_KEY"))
    return {"groq_configured": configured}


@router.post("/api/chat")
async def chat_endpoint(req: ChatRequest) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")
    try:
        client = _get_groq_client()
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend(req.history)
        messages.append({"role": "user", "content": req.message})
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=1200,
            timeout=25.0,
        )
        return {"reply": response.choices[0].message.content}
    except Exception as exc:
        _log.error("chat_endpoint_failed: %s", exc)
        raise HTTPException(status_code=500, detail="chat_failed") from exc
