"""
Per-IP rate limiting for public endpoints that carry no API key.

Mirrors api/security.py's deque-bucket algorithm, keyed on the client's IP
instead of an API key, since these endpoints (SOS, community reports, family
join, shelter check-in) must stay callable directly from the frontend bundle
without embedding a shared secret.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request

_WINDOW_SECONDS = 60.0
_DEFAULT_LIMIT = 20
_buckets: dict[str, Deque[float]] = defaultdict(deque)


def _rate_limit() -> int:
    raw = os.getenv("FLOOD_IP_RATE_LIMIT", str(_DEFAULT_LIMIT))
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_LIMIT


def require_ip_rate_limit(request: Request) -> str:
    """Enforce a deque-backed per-IP rate limit. Never requires a key."""
    client_ip = request.client.host if request.client else "unknown"

    now = time.monotonic()
    bucket = _buckets[client_ip]
    while bucket and now - bucket[0] > _WINDOW_SECONDS:
        bucket.popleft()
    if not bucket:
        _buckets.pop(client_ip, None)
        bucket = _buckets[client_ip]
    if len(bucket) >= _rate_limit():
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")
    bucket.append(now)
    return client_ip
