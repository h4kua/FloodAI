"""
Per-IP rate limiting for public endpoints that carry no API key.

Uses the same deque-bucket core as api/security.py's require_api_key, keyed on
the client's IP instead, since these endpoints (shelter check-in, chatbot, and
the optional community endpoints) must stay callable directly from the
frontend bundle without embedding a shared secret.
"""

from __future__ import annotations

import os
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request

from api.rate_limit import enforce_rate_limit

_DEFAULT_LIMIT = 20
_DEFAULT_CHAT_LIMIT = 10
_buckets: dict[str, Deque[float]] = defaultdict(deque)
# The chatbot gets its own buckets: every message spends LLM quota, and chat
# traffic must not eat into the shelter check-in allowance (or vice versa).
_chat_buckets: dict[str, Deque[float]] = defaultdict(deque)


def _env_limit(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def client_ip(request: Request) -> str:
    """
    The caller's IP. On Fly.io the TCP peer is Fly's edge proxy, so every
    request would share one bucket; the proxy puts the real address in
    ``Fly-Client-IP``. That header is trusted only when running on Fly
    (``FLY_APP_NAME`` is set by the platform), never locally, where a client
    could set it to dodge the limit.
    """
    if os.getenv("FLY_APP_NAME"):
        fly_ip = request.headers.get("fly-client-ip", "").strip()
        if fly_ip:
            return fly_ip
    return request.client.host if request.client else "unknown"


def require_ip_rate_limit(request: Request) -> str:
    """Enforce a deque-backed per-IP rate limit. Never requires a key."""
    ip = client_ip(request)
    enforce_rate_limit(_buckets, ip, _env_limit("FLOOD_IP_RATE_LIMIT", _DEFAULT_LIMIT))
    return ip


def require_chat_rate_limit(request: Request) -> str:
    """Per-IP limit for ``POST /api/chat`` (default 10 messages per minute)."""
    ip = client_ip(request)
    enforce_rate_limit(_chat_buckets, ip, _env_limit("FLOOD_CHAT_RATE_LIMIT", _DEFAULT_CHAT_LIMIT))
    return ip
