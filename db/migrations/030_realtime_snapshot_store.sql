-- Migration: 030_realtime_snapshot_store.sql
-- Description: Single-row store for the latest realtime ingestion snapshot, so the
--              dashboard reads fresh data from Supabase instead of an ephemeral
--              static JSON file (which never updates on Railway's filesystem).
--              The periodic refresh job upserts id='latest'; the dashboard reads it.
-- Created: 2026-05-22

BEGIN;

CREATE TABLE IF NOT EXISTS realtime_snapshot_store (
    id          TEXT PRIMARY KEY DEFAULT 'latest',
    snapshot    JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshot_fetched_at
    ON realtime_snapshot_store(fetched_at);

-- The refresh endpoint and dashboard use the anon key over HTTPS/443.
GRANT SELECT, INSERT, UPDATE ON realtime_snapshot_store TO anon;

COMMIT;
