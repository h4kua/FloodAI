-- Migration: 107_family_groups.sql
-- Description: Household groups for FloodGuard FR6 — Family Status screen.
--              No login system exists in this codebase, so identity is a
--              lightweight device-id + human-enterable 6-char family code:
--              the first member creates a family (server generates the code),
--              others join by entering it. `is_stale` (>5 min since last_seen_at,
--              per FR6) is computed at read time by the repository, not stored.
-- Created: 2026-07-03

BEGIN;

CREATE TABLE IF NOT EXISTS family_groups (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code        VARCHAR(6) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS family_members (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id      UUID NOT NULL REFERENCES family_groups(id) ON DELETE CASCADE,
    device_id      VARCHAR(64) NOT NULL,
    display_name   VARCHAR(80) NOT NULL,
    phone          VARCHAR(20),
    status         VARCHAR(12) NOT NULL DEFAULT 'safe'
                     CHECK (status IN ('safe', 'in_transit', 'missing')),
    lat            DOUBLE PRECISION,
    lon            DOUBLE PRECISION,
    location_label VARCHAR(160),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    joined_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (family_id, device_id)
);

CREATE INDEX IF NOT EXISTS idx_family_members_family_id ON family_members(family_id);
CREATE INDEX IF NOT EXISTS idx_family_members_device_id ON family_members(device_id);

GRANT SELECT, INSERT, UPDATE ON family_groups  TO anon;
GRANT SELECT, INSERT, UPDATE ON family_members TO anon;

COMMIT;
