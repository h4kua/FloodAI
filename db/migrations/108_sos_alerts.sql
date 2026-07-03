-- Migration: 108_sos_alerts.sql
-- Description: SOS dispatch log for FloodGuard FR5 — SOS Emergency screen.
--              Real BPBD dispatch integration and SMS fallback (paper NFR3) are
--              explicitly out of scope for this build (no gateway exists) —
--              this table is the record of what was dispatched from the app.
--              family_id is set when the submitting device has joined a family,
--              so the SOS can also flip that member's status to 'missing'.
-- Created: 2026-07-03

BEGIN;

CREATE TABLE IF NOT EXISTS sos_alerts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id   VARCHAR(64) NOT NULL,
    family_id   UUID REFERENCES family_groups(id) ON DELETE SET NULL,
    name        VARCHAR(80) NOT NULL,
    phone       VARCHAR(20) NOT NULL,
    lat         DOUBLE PRECISION NOT NULL,
    lon         DOUBLE PRECISION NOT NULL,
    status      VARCHAR(16) NOT NULL DEFAULT 'dispatched'
                  CHECK (status IN ('dispatched', 'acknowledged', 'resolved')),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sos_alerts_created_at ON sos_alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sos_alerts_device_id  ON sos_alerts(device_id);

GRANT SELECT, INSERT, UPDATE ON sos_alerts TO anon;

COMMIT;
