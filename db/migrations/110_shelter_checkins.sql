-- Migration: 110_shelter_checkins.sql
-- Description: Shelter arrival log for FloodGuard FR8 — Safe Arrival screen.
--              shelter_id references data/bundled/jakarta_shelters.json's `id`
--              field — no FK constraint since shelters live in a static JSON
--              file, not a DB table (matches services/shelter_locator.py's
--              existing pattern). `auto` distinguishes geofence-triggered
--              check-ins from the manual "I've Arrived" fallback button.
-- Created: 2026-07-03

BEGIN;

CREATE TABLE IF NOT EXISTS shelter_checkins (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id     VARCHAR(64) NOT NULL,
    family_id     UUID REFERENCES family_groups(id) ON DELETE SET NULL,
    shelter_id    VARCHAR(20) NOT NULL,
    shelter_name  VARCHAR(160) NOT NULL,
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    distance_m    DOUBLE PRECISION NOT NULL,
    auto          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shelter_checkins_device_id  ON shelter_checkins(device_id);
CREATE INDEX IF NOT EXISTS idx_shelter_checkins_created_at ON shelter_checkins(created_at DESC);

GRANT SELECT, INSERT ON shelter_checkins TO anon;

COMMIT;
