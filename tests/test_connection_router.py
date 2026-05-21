"""Tests for the psycopg2 ↔ supabase transport router (db/connection_router.py)."""

from __future__ import annotations

from db.connection_router import get_db_transport


def test_supabase_fallback(monkeypatch):
    # psycopg2 unreachable (VPN blocks 5432/6543) -> route to supabase HTTP.
    monkeypatch.setattr(
        "db.connection_router.is_psycopg2_available", lambda timeout=3: False
    )
    assert get_db_transport() == "supabase"


def test_psycopg2_preferred(monkeypatch):
    # Direct TCP reachable -> prefer low-latency psycopg2.
    monkeypatch.setattr(
        "db.connection_router.is_psycopg2_available", lambda timeout=3: True
    )
    assert get_db_transport() == "psycopg2"
