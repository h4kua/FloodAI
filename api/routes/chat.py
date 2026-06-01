from __future__ import annotations
import os
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from groq import Groq

_log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    system: str = ""

@router.post("/api/chat")
async def chat_endpoint(req: ChatRequest) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY not configured")
    try:
        client = Groq(api_key=api_key)
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.extend(req.history)
        messages.append({"role": "user", "content": req.message})
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=512,
        )
        return {"reply": response.choices[0].message.content}
    except Exception as exc:
        _log.error("chat_endpoint_failed: %s", exc)
        raise HTTPException(status_code=500, detail="chat_failed") from exc