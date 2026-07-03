-- Migration: 109_community_reports.sql
-- Description: Crowdsourced flood condition reports (FloodGuard FR7 — Community
--              Reports screen). Public, anonymous-friendly submission table:
--              reporter_name/device_id are optional so anyone can post a report
--              without any identity setup. Immutable once posted (no UPDATE grant) —
--              the `verified` flag is an admin-only concern out of scope for this build.
-- Created: 2026-07-03

BEGIN;

CREATE TABLE IF NOT EXISTS community_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_name   VARCHAR(80),
    device_id       VARCHAR(64),
    severity        VARCHAR(10) NOT NULL CHECK (severity IN ('alert', 'safe')),
    verified        BOOLEAN NOT NULL DEFAULT FALSE,
    message         TEXT NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    location_label  VARCHAR(160),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_community_reports_created_at ON community_reports(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_community_reports_severity   ON community_reports(severity);

-- Public submission endpoint uses the anon key over HTTPS/443, same pattern as
-- realtime_snapshot_store (migration 030).
GRANT SELECT, INSERT ON community_reports TO anon;

COMMIT;
