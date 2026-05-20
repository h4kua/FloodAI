"""Unit tests for the live water-gate (Pintu Air / TMA) fetcher — no network."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
import requests

from app.services import pintu_air_fetcher as pa


def _features():
    return [
        {
            "attributes": {
                "PINTU_AIR": "P.A. Hek",
                "SUNGAI": "Cipinang",
                "KETINGGIAN_AIR_CM": 220,
                "STATUS_N": "Siaga 3",
                "STATUS_NUM": 1,
                "TANGGAL": "20/05/2026",
                "WAKTU": "14:00",
            }
        },
        {
            "attributes": {
                "PINTU_AIR": "Pompa Kamal Muara",
                "SUNGAI": "Kamal",
                "KETINGGIAN_AIR_CM": 114,
                "STATUS_N": "Normal",
                "STATUS_NUM": 4,
                "TANGGAL": "20/05/2026",
                "WAKTU": "13:30",
            }
        },
        {"attributes": {"PINTU_AIR": "", "KETINGGIAN_AIR_CM": 9}},  # dropped: no name
    ]


def test_parse_observed_at_converts_wib_to_utc():
    iso = pa._parse_observed_at("20/05/2026", "14:00")
    assert iso == "2026-05-20T07:00:00+00:00"  # 14:00 WIB == 07:00 UTC


def test_parse_observed_at_handles_missing_time():
    assert pa._parse_observed_at("20/05/2026", "") == "2026-05-19T17:00:00+00:00"


def test_parse_observed_at_returns_none_on_bad_date():
    assert pa._parse_observed_at("not-a-date", "10:00") is None


@pytest.mark.parametrize(
    "status,score",
    [("Siaga 1", 1.0), ("siaga 2", 0.8), ("Siaga 3", 0.5), ("Normal", 0.0), ("", 0.0)],
)
def test_status_score(status, score):
    assert pa.status_score(status) == score


def test_build_payload_selects_worst_gate_and_drops_unnamed():
    payload = pa._build_payload(_features())
    assert payload["gate_count"] == 2
    assert payload["max_water_level_cm"] == 220.0
    assert payload["max_status"] == "Siaga 3"
    assert payload["max_status_gate"] == "P.A. Hek"
    assert payload["source"] == "jakartasatu_bpbd_data_pintu_air"


def test_fetch_raises_on_empty_features(monkeypatch):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value={"features": []})
    monkeypatch.setattr(pa.requests, "get", Mock(return_value=resp))
    with pytest.raises(ValueError):
        pa.fetch_pintu_air(save=False)


def test_get_falls_back_to_cache(monkeypatch, tmp_path):
    cache = tmp_path / "pintu_air_latest.json"
    cache.write_text(json.dumps({"gate_count": 3, "gates": []}), encoding="utf-8")
    monkeypatch.setattr(pa, "CACHE_PATH", cache)
    monkeypatch.setattr(pa.requests, "get", Mock(side_effect=requests.ConnectionError("down")))
    payload = pa.get_pintu_air()
    assert payload is not None and payload["gate_count"] == 3


def test_observation_age_minutes():
    payload = {"latest_observation_utc": "2026-05-20T07:00:00+00:00"}
    now = datetime(2026, 5, 20, 8, 30, tzinfo=timezone.utc)
    assert pa.observation_age_minutes(payload, now=now) == 90.0


def test_observation_age_minutes_none_when_missing():
    assert pa.observation_age_minutes({}) is None
