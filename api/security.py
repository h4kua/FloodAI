"""API authentication and lightweight per-key rate limiting."""

from __future__ import annotations

import os
from collections import defaultdict, deque
from typing import Deque

from fastapi import Header, HTTPException, Request

from api.rate_limit import enforce_rate_limit

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

    enforce_rate_limit(_buckets, x_api_key, _rate_limit())
    return x_api_key
