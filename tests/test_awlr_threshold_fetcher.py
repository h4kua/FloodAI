"""Unit tests for the AWLR threshold fetcher (no network)."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
import requests

from services import awlr_threshold_fetcher as awlr


# ── parse_threshold ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("> 350 cm", 350.0),
        (">350cm", 350.0),
        ("< 150 cm", 150.0),
        ("250 - 350 cm", {"min": 250.0, "max": 350.0}),
        ("0 - 45 cm", {"min": 0.0, "max": 45.0}),
        ("350 - 250 cm", {"min": 250.0, "max": 350.0}),  # normalises order
        ("", None),
        (None, None),
        ("tidak ada data", None),
    ],
)
def test_parse_threshold(raw, expected):
    assert awlr.parse_threshold(raw) == expected


def test_parse_threshold_handles_comma_decimal():
    assert awlr.parse_threshold("> 12,5 cm") == 12.5


# ── _normalise_feature / _build_payload ─────────────────────────────────────

def _sample_features():
    return [
        {
            "attributes": {
                "LOK_AWAL": "Katulampa",
                "ALIRAN_KALI": "Kali Ciliwung",
                "WADMKK": "Kota Bogor, Jawa Barat",
                "ALAMAT": "Bendung Katulampa",
                "LAT": -6.65,
                "LONG_": 106.83,
                "SIAGA_1": "> 200 cm",
                "SIAGA_2": "150 - 200 cm",
                "SIAGA_3": "80 - 150 cm",
                "SIAGA_4": "< 80 cm",
            }
        },
        {"attributes": {"LOK_AWAL": "", "SIAGA_1": "> 100 cm"}},  # dropped: no name
    ]


def test_build_payload_normalises_and_drops_unnamed():
    payload = awlr._build_payload(_sample_features())
    assert payload["gate_count"] == 1
    assert payload["source"] == "jakartasatu_awlr_featureserver"
    gate = payload["gates"][0]
    assert gate["name"] == "Katulampa"
    assert gate["siaga_1"] == 200.0
    assert gate["siaga1_cm"] == 200.0
    assert gate["siaga_2"] == {"min": 150.0, "max": 200.0}


# ── fetch / cache fallback ──────────────────────────────────────────────────

def test_fetch_raises_on_empty_features(monkeypatch):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value={"features": []})
    monkeypatch.setattr(awlr.requests, "get", Mock(return_value=resp))
    with pytest.raises(ValueError):
        awlr.fetch_awlr_thresholds(save=False)


def test_get_falls_back_to_cache_on_network_error(monkeypatch, tmp_path):
    cache = tmp_path / "awlr_thresholds.json"
    cache.write_text(
        json.dumps({"gate_count": 1, "gates": [{"name": "X", "siaga1_cm": 250.0}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(awlr, "CACHE_PATH", cache)
    monkeypatch.setattr(
        awlr.requests, "get", Mock(side_effect=requests.ConnectionError("down"))
    )
    payload = awlr.get_awlr_thresholds()
    assert payload is not None
    assert payload["gate_count"] == 1


def test_get_returns_none_when_no_network_and_no_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(awlr, "CACHE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(
        awlr.requests, "get", Mock(side_effect=requests.ConnectionError("down"))
    )
    assert awlr.get_awlr_thresholds() is None


# ── siaga1_cm_for ───────────────────────────────────────────────────────────

def test_siaga1_cm_for_matches_by_name_substring():
    payload = {
        "gates": [
            {"name": "PS. Manggarai", "kali": "Kali Ciliwung", "siaga1_cm": 950.0},
            {"name": "PS. Angke Hulu", "kali": "Kali Angke", "siaga1_cm": 350.0},
        ]
    }
    assert awlr.siaga1_cm_for("manggarai", payload) == 950.0
    assert awlr.siaga1_cm_for("Angke", payload) == 350.0
    assert awlr.siaga1_cm_for("nonexistent", payload) is None
