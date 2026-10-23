"""
Pytest session-level fixtures.

Sets test-time env vars BEFORE any test module imports the FastAPI app.
Required because ``app.api.main`` reads ``FLOOD_API_KEYS`` and
``ALLOWED_HOSTS`` at module-load time (when middleware is registered).
"""

from __future__ import annotations

import os

# Auth + rate limit — must exist before app import so /demo, /metrics, and
# /predict/* dependencies don't return 503 api_not_configured during tests.
os.environ.setdefault("FLOOD_API_KEYS", "test-key")
os.environ.setdefault("FLOOD_API_RATE_LIMIT", "10000")

# Force pytest to allow TestClient's default host even if the outer shell has
# a stricter ALLOWED_HOSTS value set.
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"

# CORS is irrelevant for in-process tests but keep parity with prod default.
os.environ.setdefault("CORS_ORIGINS", "")

# Never run the real snapshot scraper from a TestClient lifespan: it fetches
# from the network, overwrites poskobanjir/data, and its subprocess pipes
# outlive the test on Windows (pytest then fails on "I/O operation on closed pipe").
os.environ["SNAPSHOT_SCHEDULER_ENABLED"] = "false"
