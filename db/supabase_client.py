"""
Supabase HTTP client — works on port 443, VPN-safe.
Use this when psycopg2 (port 5432/6543) is unavailable.

The ``supabase`` package is imported lazily inside ``get_supabase_client`` so
this module imports cleanly even when supabase-py is not installed yet — only
callers that actually need the HTTP transport pay the import (and dependency)
cost.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_supabase_client():
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(url, key)
