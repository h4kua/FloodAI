-- Migration: 028_create_idempotency_keys.sql
-- Description: Request-idempotency cache backing api.main._get_idempotent_response /
--              _store_idempotent_response (1-hour TTL on created_at).
-- Created: 2026-05-22
-- Note: BACKFILL — the table already exists in the live Supabase database but was
--       created out-of-band (no prior migration). This migration brings version
--       control into parity so a fresh environment rebuilt from migrations alone
--       provisions the table. CREATE TABLE IF NOT EXISTS makes it a safe no-op
--       against the existing table; it is non-destructive and idempotent.

BEGIN;

CREATE TABLE IF NOT EXISTS idempotency_keys (
    -- Client-supplied Idempotency-Key header; ON CONFLICT target in api/main.py.
    idempotency_key     TEXT PRIMARY KEY,

    -- SHA-256 of the cached response body (api.main._response_hash).
    response_hash       TEXT NOT NULL,

    -- Full cached response payload replayed on a repeated key.
    response_json       JSONB NOT NULL,

    -- Drives the 1-hour TTL: DELETE WHERE created_at < NOW() - INTERVAL '1 hour'
    -- and the freshness guard on SELECT.
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- created_at is the predicate for both the TTL sweep and the freshness SELECT.
CREATE INDEX IF NOT EXISTS idx_idempotency_keys_created_at
    ON idempotency_keys (created_at);

COMMENT ON TABLE idempotency_keys IS
    'Request-idempotency cache (1-hour TTL) backing api.main idempotent responses.';

COMMIT;
