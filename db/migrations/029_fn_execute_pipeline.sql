-- Migration: 029_fn_execute_pipeline.sql
-- Description: Atomic, VPN-safe pipeline-write stored function callable via
--              Supabase RPC (HTTPS/443). Performs the same 6 dependent INSERTs +
--              finalize UPDATE as db.pipeline_writer._run_transaction, in ONE
--              implicit plpgsql transaction (any error -> full rollback via RAISE).
-- Created: 2026-05-22
--
-- Contract (decisions locked with maintainer):
--   * The CALLER (Python) validates + normalizes ALL values before calling this
--     function: system_status/risk_level are already canonical (match DB CHECK
--     constraints), probabilities are in [0,1], and snapshot_hash is precomputed
--     (SHA-256 of the normalized snapshot JSON). This function does NO
--     normalization — it inserts the payload verbatim.
--   * SECURITY DEFINER + GRANT EXECUTE TO anon so the anon key (port 443) can
--     invoke it even when psycopg2 (5432/6543) is blocked. search_path is pinned
--     to public per SECURITY DEFINER hardening.
--
-- Expected payload shape (jsonb), mirroring pipeline_writer column names exactly:
-- {
--   "snapshot":    {"snapshot_hash","fetched_at_utc","first_seen_at","location",
--                   "openweather","poskobanjir","bmkg_alerts"},
--   "pipeline_run":{"execution_mode","started_at","origin","destination",
--                   "api_version","pipeline_version"},
--   "perception":  {"data_freshness_minutes","snapshot_completeness","signal_presence"},
--   "reasoning":   {"probability","confidence_score","model_variant"},
--   "evaluation":  {"system_status","risk_level","probability","confidence_score",
--                   "requires_manual_review"},
--   "decision":    {"system_status","requires_manual_review","decision_reason",
--                   "data_validity","ml_execution_mode","risk_level","probability",
--                   "confidence_score","is_safe_for_automation","decision_timestamp"},
--   "finalize":    {"completed_at","execution_time_ms","final_decision"}
-- }

BEGIN;

CREATE OR REPLACE FUNCTION fn_execute_pipeline(payload JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_snapshot_id     UUID;
    v_pipeline_run_id UUID;
    v_perception_id   UUID;
    v_reasoning_id    UUID;
    v_evaluation_id   UUID;
    v_decision_id     UUID;
BEGIN
    -- INSERT 1: snapshots (root) -> snapshot_id
    -- nullif(..., 'null'::jsonb) maps JSON null to SQL NULL for optional jsonb cols.
    INSERT INTO snapshots (
        snapshot_hash, fetched_at_utc, first_seen_at, location,
        openweather, poskobanjir, bmkg_alerts
    )
    VALUES (
        payload->'snapshot'->>'snapshot_hash',
        (payload->'snapshot'->>'fetched_at_utc')::timestamptz,
        (payload->'snapshot'->>'first_seen_at')::timestamptz,
        payload->'snapshot'->>'location',
        nullif(payload->'snapshot'->'openweather', 'null'::jsonb),
        nullif(payload->'snapshot'->'poskobanjir', 'null'::jsonb),
        nullif(payload->'snapshot'->'bmkg_alerts', 'null'::jsonb)
    )
    RETURNING id INTO v_snapshot_id;

    -- INSERT 2: pipeline_runs (needs snapshot_id) -> pipeline_run_id
    INSERT INTO pipeline_runs (
        snapshot_id, execution_mode, started_at,
        origin, destination, api_version, pipeline_version
    )
    VALUES (
        v_snapshot_id,
        payload->'pipeline_run'->>'execution_mode',
        (payload->'pipeline_run'->>'started_at')::timestamptz,
        payload->'pipeline_run'->>'origin',
        payload->'pipeline_run'->>'destination',
        payload->'pipeline_run'->>'api_version',
        payload->'pipeline_run'->>'pipeline_version'
    )
    RETURNING id INTO v_pipeline_run_id;

    -- INSERT 3: perception_results (needs snapshot_id + pipeline_run_id)
    INSERT INTO perception_results (
        snapshot_id, pipeline_run_id,
        data_freshness_minutes, snapshot_completeness, signal_presence
    )
    VALUES (
        v_snapshot_id,
        v_pipeline_run_id,
        (payload->'perception'->>'data_freshness_minutes')::numeric,
        (payload->'perception'->>'snapshot_completeness')::numeric,
        coalesce(payload->'perception'->'signal_presence', '{}'::jsonb)
    )
    RETURNING id INTO v_perception_id;

    -- INSERT 4: reasoning_results (needs perception_id + pipeline_run_id)
    INSERT INTO reasoning_results (
        perception_id, pipeline_run_id,
        probability, confidence_score, model_variant
    )
    VALUES (
        v_perception_id,
        v_pipeline_run_id,
        (payload->'reasoning'->>'probability')::numeric,
        (payload->'reasoning'->>'confidence_score')::numeric,
        payload->'reasoning'->>'model_variant'
    )
    RETURNING id INTO v_reasoning_id;

    -- INSERT 5: evaluation_results (needs reasoning_id + perception_id + pipeline_run_id)
    INSERT INTO evaluation_results (
        reasoning_id, perception_id, pipeline_run_id,
        system_status, risk_level, probability, confidence_score, requires_manual_review
    )
    VALUES (
        v_reasoning_id,
        v_perception_id,
        v_pipeline_run_id,
        payload->'evaluation'->>'system_status',
        payload->'evaluation'->>'risk_level',
        (payload->'evaluation'->>'probability')::numeric,
        (payload->'evaluation'->>'confidence_score')::numeric,
        (payload->'evaluation'->>'requires_manual_review')::boolean
    )
    RETURNING id INTO v_evaluation_id;

    -- INSERT 6: decisions (needs evaluation_id + pipeline_run_id)
    INSERT INTO decisions (
        evaluation_id, pipeline_run_id, system_status, requires_manual_review,
        decision_reason, data_validity, ml_execution_mode, risk_level,
        probability, confidence_score, is_safe_for_automation, decision_timestamp
    )
    VALUES (
        v_evaluation_id,
        v_pipeline_run_id,
        payload->'decision'->>'system_status',
        (payload->'decision'->>'requires_manual_review')::boolean,
        payload->'decision'->>'decision_reason',
        payload->'decision'->>'data_validity',
        payload->'decision'->>'ml_execution_mode',
        payload->'decision'->>'risk_level',
        (payload->'decision'->>'probability')::numeric,
        (payload->'decision'->>'confidence_score')::numeric,
        (payload->'decision'->>'is_safe_for_automation')::boolean,
        (payload->'decision'->>'decision_timestamp')::timestamptz
    )
    RETURNING id INTO v_decision_id;

    -- FINALIZE: update the pipeline_runs row with completion metadata.
    UPDATE pipeline_runs
    SET completed_at      = (payload->'finalize'->>'completed_at')::timestamptz,
        execution_time_ms = (payload->'finalize'->>'execution_time_ms')::integer,
        final_decision    = coalesce(payload->'finalize'->'final_decision', '{}'::jsonb),
        system_status     = payload->'decision'->>'system_status',
        risk_level        = payload->'decision'->>'risk_level',
        confidence_score  = (payload->'decision'->>'confidence_score')::numeric
    WHERE id = v_pipeline_run_id;

    RETURN jsonb_build_object(
        'snapshot_id',     v_snapshot_id,
        'pipeline_run_id', v_pipeline_run_id,
        'perception_id',   v_perception_id,
        'reasoning_id',    v_reasoning_id,
        'evaluation_id',   v_evaluation_id,
        'decision_id',     v_decision_id,
        'status',          'ok'
    );

EXCEPTION WHEN OTHERS THEN
    RAISE;  -- any failure rolls back all 6 inserts + the update atomically.
END;
$$;

-- Anon (and authenticated) callers invoke over HTTPS/443; SECURITY DEFINER runs
-- the body with the function owner's table privileges.
GRANT EXECUTE ON FUNCTION fn_execute_pipeline(JSONB) TO anon;
GRANT EXECUTE ON FUNCTION fn_execute_pipeline(JSONB) TO authenticated;

COMMIT;
