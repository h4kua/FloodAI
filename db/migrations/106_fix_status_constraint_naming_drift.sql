-- Migration: 106_fix_status_constraint_naming_drift.sql
-- Description: Fixes constraint-naming drift that blocked persistence of
--              CONFLICT / LOW_TRUST decisions, plus two latent enum gaps in
--              migration 100.
--
--   1. evaluation_results carries an ORPHAN constraint named `chk_eval_status`
--      that only allows the legacy 4-value system_status set
--      ('OK','DEGRADED','FAIL','PIPELINE_FAILURE'). It was created directly in
--      Supabase and is NOT managed by any migration file, so 100's
--      `eval_status_chk` rewrite never touched it. Result: every CONFLICT /
--      LOW_TRUST decision raised
--          23514 violates check constraint "chk_eval_status"
--      and silently failed to persist (best-effort _persist swallows it).
--
--   2. decisions_reason_chk (migration 100) omitted 'SAFETY_FLOOR' — one of the
--      7 canonical DecisionReason values — so L1.7 safety-floor decisions could
--      not be written.
--
--   3. decisions_authority_chk (migration 100) omitted the L1_7 / L1_8 / L1_9
--      authorities added to the canonical DecisionAuthority enum.
--
-- Source of truth: contracts/vocabulary.py.
-- Created: 2026-06-19
-- Idempotent (DROP IF EXISTS + ADD inside DO/EXCEPTION). Safe to re-run.

BEGIN;

-- ===========================================================================
-- 1. evaluation_results.system_status — drop BOTH the orphan `chk_eval_status`
--    and the managed `eval_status_chk`, then re-add the canonical 6-value check
--    under the managed name so future migrations own it.
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE evaluation_results DROP CONSTRAINT IF EXISTS chk_eval_status;
    ALTER TABLE evaluation_results DROP CONSTRAINT IF EXISTS eval_status_chk;
    ALTER TABLE evaluation_results ADD CONSTRAINT eval_status_chk
        CHECK (system_status IN
               ('OK','DEGRADED','LOW_TRUST','CONFLICT','FAIL','PIPELINE_FAILURE'));
EXCEPTION WHEN others THEN NULL; END $$;

-- ===========================================================================
-- 2. decisions.decision_reason — add the missing 'SAFETY_FLOOR' value so the
--    full 7-value canonical DecisionReason enum is accepted.
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS chk_decisions_reason;
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_reason_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_reason_chk
        CHECK (decision_reason IN
               ('RISK','INVALID_INPUT','FALLBACK','PHYSICAL_GATE',
                'MULTI_SIGNAL','TREND_EXTENSION','SAFETY_FLOOR'));
EXCEPTION WHEN others THEN NULL; END $$;

-- ===========================================================================
-- 3. decisions._decision_authority — add the L1.7 / L1.8 / L1.9 floors so the
--    full 9-value canonical DecisionAuthority enum is accepted.
-- ===========================================================================
DO $$ BEGIN
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS chk_decisions_authority;
    ALTER TABLE decisions DROP CONSTRAINT IF EXISTS decisions_authority_chk;
    ALTER TABLE decisions ADD CONSTRAINT decisions_authority_chk
        CHECK (_decision_authority IS NULL OR _decision_authority IN
               ('L0_PHYSICAL','L1_SIAGA','L1_5_MULTI','L1_7_BMKG_SAFETY_FLOOR',
                'L1_8_HYDRO_FLOOR','L1_9_OOD_FLOOR','L2_INTEGRITY','L3_ML','L4_TREND'));
EXCEPTION WHEN others THEN NULL; END $$;

COMMIT;
