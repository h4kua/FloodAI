"""
Shared deque-bucket rate-limiting core.

Used by api/security.py (per-API-key) and api/ip_rate_limit.py (per-IP) — both
need the exact same sliding-window bucket algorithm, differing only in what
they use as the bucket key.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Deque

from fastapi import HTTPException

_WINDOW_SECONDS = 60.0


def enforce_rate_limit(buckets: dict[str, Deque[float]], key: str, limit: int) -> None:
    """
    Prune hits older than the window, raise 429 if `key`'s bucket is already at
    `limit`, otherwise record this hit. Mutates `buckets` in place.
    """
    now = time.monotonic()
    bucket = buckets[key]
    while bucket and now - bucket[0] > _WINDOW_SECONDS:
        bucket.popleft()
    # Prune exhausted buckets so inactive keys don't grow `buckets` unboundedly.
    if not bucket:
        buckets.pop(key, None)
        bucket = buckets[key]
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")
    bucket.append(now)
