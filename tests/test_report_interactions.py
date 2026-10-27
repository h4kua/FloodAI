"""Likes/dislikes, comments and flags on community reports (no real Supabase)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.ip_rate_limit as ip_rate_limit
from api.routes.community_reports import FLAG_HIDE_THRESHOLD, router

app = FastAPI()
app.include_router(router)
client = TestClient(app)
_HEADERS = {"host": "localhost"}
_RID = "2f1c3b8e-6a3d-4c55-9b0a-1e2d3c4b5a69"
_DEVICE = "device-1234abcd"
_MOD = "api.routes.community_reports"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    ip_rate_limit._buckets.clear()
    yield
    ip_rate_limit._buckets.clear()


def _exists():
    return patch(f"{_MOD}.get_report", return_value={"id": _RID})


def test_list_adds_counts_and_this_devices_vote_and_hides_device_ids():
    reports = [{"id": _RID, "lat": -6.2, "lon": 106.8, "severity": "alert", "device_id": "someone-else-123"}]
    counts = {_RID: {"likes": 4, "dislikes": 1, "comment_count": 2, "flags": 0, "my_vote": 1}}
    with patch(f"{_MOD}.list_reports", return_value=reports), \
         patch(f"{_MOD}.report_interactions", return_value=counts) as interactions:
        body = client.get(f"/reports?device_id={_DEVICE}", headers=_HEADERS).json()
    (report,) = body["reports"]
    assert (report["likes"], report["dislikes"], report["comment_count"], report["my_vote"]) == (4, 1, 2, 1)
    assert "device_id" not in report
    assert interactions.call_args.args == ([_RID], _DEVICE)


def test_list_hides_reports_flagged_by_enough_devices():
    reports = [{"id": _RID, "lat": -6.2, "lon": 106.8, "severity": "alert"},
               {"id": "other", "lat": -6.2, "lon": 106.8, "severity": "safe"}]
    counts = {_RID: {"flags": FLAG_HIDE_THRESHOLD}}
    with patch(f"{_MOD}.list_reports", return_value=reports), patch(f"{_MOD}.report_interactions", return_value=counts):
        body = client.get("/reports", headers=_HEADERS).json()
    assert [r["id"] for r in body["reports"]] == ["other"]
    assert body["reports"][0]["likes"] == 0  # no reactions yet (or migration 111 not run)


def test_vote_sets_and_returns_the_new_counts():
    with _exists(), patch(f"{_MOD}.set_vote", return_value=True) as set_vote, \
         patch(f"{_MOD}.report_interactions", return_value={_RID: {"likes": 1, "dislikes": 0, "my_vote": 1}}):
        res = client.post(f"/reports/{_RID}/vote", json={"device_id": _DEVICE, "value": 1}, headers=_HEADERS)
    assert res.status_code == 200
    assert res.json() == {"likes": 1, "dislikes": 0, "my_vote": 1}
    assert set_vote.call_args.args == (_RID, _DEVICE, 1)


def test_vote_value_must_be_minus_one_zero_or_one():
    res = client.post(f"/reports/{_RID}/vote", json={"device_id": _DEVICE, "value": 5}, headers=_HEADERS)
    assert res.status_code == 422


def test_vote_on_a_missing_report_is_404():
    with patch(f"{_MOD}.get_report", return_value=None):
        res = client.post(f"/reports/{_RID}/vote", json={"device_id": _DEVICE, "value": -1}, headers=_HEADERS)
    assert res.status_code == 404


def test_report_id_must_be_a_uuid():
    res = client.post("/reports/not-a-uuid/vote", json={"device_id": _DEVICE, "value": 1}, headers=_HEADERS)
    assert res.status_code == 422


def test_comment_is_trimmed_and_saved():
    saved = {"id": "c1", "author": "Rina", "message": "Masih banjir 30 cm", "created_at": "2026-10-27T10:00:00Z"}
    with _exists(), patch(f"{_MOD}.add_comment", return_value=saved) as add:
        res = client.post(f"/reports/{_RID}/comments",
                          json={"message": "  Masih banjir 30 cm  ", "author": " Rina ", "device_id": _DEVICE},
                          headers=_HEADERS)
    assert res.status_code == 200
    assert res.json()["comment"] == saved
    assert add.call_args.args == (_RID, "Masih banjir 30 cm", "Rina", _DEVICE)


def test_blank_or_long_comments_are_refused():
    with _exists():
        blank = client.post(f"/reports/{_RID}/comments", json={"message": "   "}, headers=_HEADERS)
        long = client.post(f"/reports/{_RID}/comments", json={"message": "x" * 301}, headers=_HEADERS)
    assert (blank.status_code, long.status_code) == (422, 422)


def test_comments_are_listed_and_a_missing_table_gives_503():
    rows = [{"id": "c1", "author": None, "message": "Sudah surut", "created_at": "2026-10-27T10:00:00Z"}]
    with patch(f"{_MOD}.list_comments", return_value=rows):
        assert client.get(f"/reports/{_RID}/comments").json() == {"comments": rows, "count": 1}
    with patch(f"{_MOD}.list_comments", return_value=None):
        assert client.get(f"/reports/{_RID}/comments").status_code == 503


def test_flag_needs_a_known_reason():
    with _exists(), patch(f"{_MOD}.flag_report", return_value=True) as flag:
        ok = client.post(f"/reports/{_RID}/flag", json={"device_id": _DEVICE, "reason": "wrong"}, headers=_HEADERS)
        bad = client.post(f"/reports/{_RID}/flag", json={"device_id": _DEVICE, "reason": "because"}, headers=_HEADERS)
    assert ok.json() == {"flagged": True}
    assert flag.call_args.args == (_RID, _DEVICE, "wrong")
    assert bad.status_code == 422
