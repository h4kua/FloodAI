"""Unit tests for db/family_repository.py (no real Supabase connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from db import family_repository as fr


def test_generate_code_length_and_alphabet():
    code = fr._generate_code()
    assert len(code) == fr._CODE_LENGTH
    assert all(c in fr._CODE_ALPHABET for c in code)
    # Ambiguous characters must never appear.
    assert not any(c in code for c in "O0I1")


def test_create_family_sync_retries_on_collision_then_succeeds():
    mock_client = MagicMock()
    # First insert attempt raises (simulated unique-constraint collision),
    # second attempt succeeds.
    mock_client.table.return_value.insert.return_value.execute.side_effect = [
        Exception("duplicate code"),
        MagicMock(data=[{"id": "family-uuid-1"}]),
        MagicMock(data=[{"id": "member-uuid-1"}]),
    ]
    with patch("db.family_repository.get_supabase_client", return_value=mock_client):
        result = fr._create_family_sync(device_id="dev-1", display_name="Budi", phone="0812")
    assert result == {"family_code": result["family_code"], "member_id": "member-uuid-1"}
    assert len(result["family_code"]) == fr._CODE_LENGTH


def test_create_family_sync_gives_up_after_max_attempts():
    mock_client = MagicMock()
    mock_client.table.return_value.insert.return_value.execute.side_effect = Exception("always fails")
    with patch("db.family_repository.get_supabase_client", return_value=mock_client):
        result = fr._create_family_sync(device_id="dev-1", display_name="Budi", phone=None)
    assert result is None


def test_find_family_id_sync_returns_none_when_not_found():
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    with patch("db.family_repository.get_supabase_client", return_value=mock_client):
        assert fr._find_family_id_sync("ZZZZZZ") is None


def test_join_family_sync_returns_none_for_unknown_code():
    with patch("db.family_repository._find_family_id_sync", return_value=None):
        result = fr._join_family_sync(family_code="ZZZZZZ", device_id="dev-2", display_name="Sari", phone=None)
    assert result is None


def test_repository_functions_never_raise_on_client_failure():
    with patch("db.family_repository.get_supabase_client", side_effect=RuntimeError("boom")):
        assert fr._find_family_id_sync("ABCDEF") is None
        assert fr._list_members_sync("ABCDEF") == []
        assert fr._checkin_member_sync(family_code="ABCDEF", device_id="dev-1", status="safe") is False
