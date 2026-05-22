"""Tests for the psycopg2 ↔ Supabase-RPC pipeline-write router (db/pipeline_writer.py)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

import db.pipeline_writer as pw
from db.pipeline_writer import (
    DecisionPayload,
    EvaluationPayload,
    PerceptionPayload,
    PipelineExecutionResult,
    ReasoningPayload,
    execute_pipeline_routed,
    execute_pipeline_supabase,
)


def _valid_inputs():
    """A complete, valid set of pipeline payloads (passes validate_* unchanged)."""
    snapshot_input = {"openweather": {"temp": 28}, "poskobanjir": None, "bmkg_alerts": []}
    perception = PerceptionPayload(
        data_freshness_minutes=5.0, snapshot_completeness=1.0, signal_presence={"rain": True}
    )
    reasoning = ReasoningPayload(probability=0.4, confidence_score=0.8, model_variant="m1")
    evaluation = EvaluationPayload(
        system_status="OK", risk_level="SAFE", probability=0.4,
        confidence_score=0.8, requires_manual_review=False,
    )
    decision = DecisionPayload(
        system_status="OK", requires_manual_review=False, decision_reason="RISK",
        data_validity="VALID", ml_execution_mode="FULL", risk_level="SAFE",
        probability=0.4, confidence_score=0.8, is_safe_for_automation=True,
    )
    return snapshot_input, perception, reasoning, evaluation, decision


def test_routes_to_psycopg2_when_available(monkeypatch):
    # get_db_transport is imported inside execute_pipeline_routed from its source
    # module, so patch it there.
    monkeypatch.setattr("db.connection_router.get_db_transport", lambda: "psycopg2")
    psy = Mock(return_value="PSYCOPG2_RESULT")
    sup = Mock()
    monkeypatch.setattr(pw, "execute_pipeline", psy)
    monkeypatch.setattr(pw, "execute_pipeline_supabase", sup)

    snapshot_input, perception, reasoning, evaluation, decision = _valid_inputs()
    result = execute_pipeline_routed(
        snapshot_input, None, perception, reasoning, evaluation, decision
    )

    assert result == "PSYCOPG2_RESULT"
    psy.assert_called_once()
    sup.assert_not_called()


def test_routes_to_supabase_when_vpn(monkeypatch):
    monkeypatch.setattr("db.connection_router.get_db_transport", lambda: "supabase")
    rpc_ids = {
        "snapshot_id": "11111111-1111-1111-1111-111111111111",
        "pipeline_run_id": "22222222-2222-2222-2222-222222222222",
        "perception_id": "33333333-3333-3333-3333-333333333333",
        "reasoning_id": "44444444-4444-4444-4444-444444444444",
        "evaluation_id": "55555555-5555-5555-5555-555555555555",
        "decision_id": "66666666-6666-6666-6666-666666666666",
        "status": "ok",
    }
    psy = Mock()
    sup = Mock(return_value=rpc_ids)
    monkeypatch.setattr(pw, "execute_pipeline", psy)
    monkeypatch.setattr(pw, "execute_pipeline_supabase", sup)

    snapshot_input, perception, reasoning, evaluation, decision = _valid_inputs()
    result = execute_pipeline_routed(
        snapshot_input, None, perception, reasoning, evaluation, decision
    )

    # Supabase branch is wrapped into a PipelineExecutionResult so callers get the
    # SAME type as the psycopg2 branch (and .as_dict() keeps working).
    assert isinstance(result, PipelineExecutionResult)
    assert str(result.snapshot_id) == rpc_ids["snapshot_id"]
    assert result.as_dict()["decision_id"] == rpc_ids["decision_id"]
    sup.assert_called_once()
    psy.assert_not_called()
    # The serializer ran for real and produced the contract the SQL function expects.
    payload = sup.call_args.args[0]
    assert set(payload) == {
        "snapshot", "pipeline_run", "perception", "reasoning",
        "evaluation", "decision", "finalize",
    }
    assert payload["snapshot"]["snapshot_hash"]  # computed Python-side
    assert payload["decision"]["system_status"] == "OK"  # canonical, normalized


def test_supabase_path_raises_on_rpc_failure(monkeypatch):
    # rpc(...).execute() returns an object whose .data is None -> must raise.
    fake_exec = Mock()
    fake_exec.execute.return_value = Mock(data=None)
    fake_client = Mock()
    fake_client.rpc.return_value = fake_exec
    monkeypatch.setattr("db.supabase_client.get_supabase_client", lambda: fake_client)

    with pytest.raises(RuntimeError, match="fn_execute_pipeline RPC failed"):
        execute_pipeline_supabase({"payload": "shape-irrelevant"})
