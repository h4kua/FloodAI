"""API authentication and lightweight per-key rate limiting."""

from __future__ import annotations
from fastapi import Header, HTTPException, Request
import os
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Header, HTTPException

_WINDOW_SECONDS = 60.0
_DEFAULT_LIMIT = 30
_buckets: dict[str, Deque[float]] = defaultdict(deque)


def _api_keys() -> set[str]:
    return {
        key.strip()
        for key in os.getenv("FLOOD_API_KEYS", "").split(",")
        if key.strip()
    }


def _rate_limit() -> int:
    raw = os.getenv("FLOOD_API_RATE_LIMIT", str(_DEFAULT_LIMIT))
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_LIMIT


def require_api_key(request: Request, x_api_key: str = Header(default="")) -> str:
    """Require a configured API key and enforce a deque-backed rate limit."""
    if request.method == "OPTIONS":
        return ""
    keys = _api_keys()
    if not keys:
        raise HTTPException(status_code=503, detail="api_not_configured")
    if x_api_key not in keys:
        raise HTTPException(status_code=401, detail="invalid_api_key")

    now = time.monotonic()
    bucket = _buckets[x_api_key]
    while bucket and now - bucket[0] > _WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= _rate_limit():
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")
    bucket.append(now)
    return x_api_key
