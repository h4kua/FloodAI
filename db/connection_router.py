"""
Connection router: tries psycopg2 first (low latency), falls back to supabase-py (VPN-safe).
All callers use get_db_transport() to decide which transport to use.

This module is import-light and side-effect free: it does NOT import psycopg2 or
supabase at module load. ``is_psycopg2_available`` performs only a cheap TCP
probe against ``DB_HOST``/``DB_PORT`` so it works even when neither driver is
installed or reachable.
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)


def is_psycopg2_available(timeout: int = 3) -> bool:
    """Quick probe: can we reach the DB on TCP (port 5432/6543)?"""
    import socket

    host = os.getenv("DB_HOST", "")
    port = int(os.getenv("DB_PORT", "6543"))
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_db_transport() -> str:
    """Returns 'psycopg2' or 'supabase' based on network availability."""
    if is_psycopg2_available():
        _log.info("DB transport: psycopg2 (direct TCP)")
        return "psycopg2"
    _log.warning("DB transport: supabase-py (psycopg2 unreachable — VPN/firewall detected)")
    return "supabase"
