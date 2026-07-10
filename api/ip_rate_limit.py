"""
Per-IP rate limiting for public endpoints that carry no API key.

Uses the same deque-bucket core as api/security.py's require_api_key, keyed on
the client's IP instead, since these endpoints (SOS, community reports, family
join, shelter check-in) must stay callable directly from the frontend bundle
without embedding a shared secret.
"""

from __future__ import annotations

import os
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request

from api.rate_limit import enforce_rate_limit

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
    enforce_rate_limit(_buckets, client_ip, _rate_limit())
    return client_ip
