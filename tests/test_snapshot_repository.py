"""Unit tests for db/snapshot_repository.py history rows (no real Supabase connection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from db import snapshot_repository as sr

_SNAPSHOT = {
    "fetched_at_utc": "2026-11-05T01:30:53+00:00",
    "summary": {"rain_1h_mm": 0.0, "total_poskobanjir_records": 1},
    "bmkg_alerts": [],
    "bmkg_feed": {"items": ["large feed"]},
    "bmkg_forecast_per_wilayah": {"Jakarta Barat": ["large forecast"]},
    "location": {"lat": -6.2},
    "openweather": {"dt": 1, "main": {"humidity": 61}, "coord": {"lat": -6.2}, "rain": {"1h": 2.0}},
    "poskobanjir": [
        {
            "kode_stasiun": "25",
            "nama_pintu_air": "P.A. Cengkareng",
            "tanggal": "2026-11-05T08:20:00",
            "tinggi_air": "238.1",
            "siaga1": "310",
            "status_siaga": "Status : Siaga 3",
            "cctv_url": "https://example.test/cctv",
            "latitude": "-6.16",
        }
    ],
}


def test_compact_for_history_keeps_observations_and_drops_static_parts():
    compact = sr.compact_for_history(_SNAPSHOT)
    assert compact["fetched_at_utc"] == _SNAPSHOT["fetched_at_utc"]
    assert compact["summary"] == _SNAPSHOT["summary"]
    assert compact["openweather"] == {"dt": 1, "main": {"humidity": 61}, "rain": {"1h": 2.0}}
    post = compact["poskobanjir"][0]
    assert post["tinggi_air"] == "238.1" and post["status_siaga"] == "Status : Siaga 3"
    assert "cctv_url" not in post and "latitude" not in post
    for dropped in ("bmkg_feed", "bmkg_forecast_per_wilayah", "location"):
        assert dropped not in compact


def test_save_history_sync_upserts_row_keyed_by_fetched_at():
    mock_client = MagicMock()
    with patch("db.snapshot_repository.get_supabase_client", return_value=mock_client):
        assert sr._save_history_sync(_SNAPSHOT) is True
    mock_client.table.assert_called_once_with("realtime_snapshot_store")
    row = mock_client.table.return_value.upsert.call_args.args[0]
    assert row["id"] == "history:2026-11-05T01:30:53+00:00"
    assert row["fetched_at"] == _SNAPSHOT["fetched_at_utc"]
    assert row["snapshot"] == sr.compact_for_history(_SNAPSHOT)


def test_save_history_sync_rejects_snapshot_without_timestamp():
    with patch("db.snapshot_repository.get_supabase_client") as get_client:
        assert sr._save_history_sync({"summary": {}}) is False
        assert sr._save_history_sync("not a dict") is False
    get_client.assert_not_called()


def test_save_history_sync_never_raises_on_client_failure():
    with patch("db.snapshot_repository.get_supabase_client", side_effect=RuntimeError("boom")):
        assert sr._save_history_sync(_SNAPSHOT) is False
