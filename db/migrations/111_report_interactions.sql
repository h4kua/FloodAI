-- Migration: 111_report_interactions.sql
-- Description: Reactions on community reports — a like or dislike per device,
--              comments, and flags for unwanted content. All written by the
--              backend with the anon key (as community_reports, migration 109);
--              devices are the random IDs the web app keeps in localStorage.
--              A report flagged by 3 devices is hidden from the list.
-- Created: 2026-10-27
-- Run once in the Supabase SQL Editor.

BEGIN;

CREATE TABLE IF NOT EXISTS report_votes (
    report_id   UUID NOT NULL REFERENCES community_reports(id) ON DELETE CASCADE,
    device_id   VARCHAR(64) NOT NULL,
    value       SMALLINT NOT NULL CHECK (value IN (-1, 1)),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_id, device_id)
);

CREATE TABLE IF NOT EXISTS report_comments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id   UUID NOT NULL REFERENCES community_reports(id) ON DELETE CASCADE,
    device_id   VARCHAR(64),
    author      VARCHAR(80),
    message     VARCHAR(300) NOT NULL CHECK (length(trim(message)) > 0),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_report_comments_report ON report_comments(report_id, created_at);

CREATE TABLE IF NOT EXISTS report_flags (
    report_id   UUID NOT NULL REFERENCES community_reports(id) ON DELETE CASCADE,
    device_id   VARCHAR(64) NOT NULL,
    reason      VARCHAR(20) NOT NULL CHECK (reason IN ('spam', 'wrong', 'offensive', 'private')),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_id, device_id)
);

-- A vote can be changed or taken back; comments and flags are append-only.
GRANT SELECT, INSERT, UPDATE, DELETE ON report_votes TO anon;
GRANT SELECT, INSERT ON report_comments TO anon;
GRANT SELECT, INSERT ON report_flags TO anon;

COMMIT;
