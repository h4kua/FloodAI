"""Tests for Batch-2 integrations: schools, river-overflow zones, 2023 hazard."""

from __future__ import annotations

from app.services import school_locator as sk
from app.services import flood_prone_locator as fp
from app.services import bnpb_context as bc


# ── N8: school locator ──────────────────────────────────────────────────────
_SCHOOLS = (
    {"name": "SDN A", "lat": -6.1536, "lon": 106.7908, "jumlah_siswa": 300, "kelurahan": "X"},
    {"name": "SDN B", "lat": -6.2000, "lon": 106.8000, "jumlah_siswa": 100, "kelurahan": "Y"},
)


def test_nearby_schools_within_radius():
    out = sk.nearby_schools(-6.1536, 106.7908, radius_m=500, schools=_SCHOOLS)
    assert out and out[0]["name"] == "SDN A"
    assert out[0]["type"] == "school"


def test_nearby_schools_empty_pool():
    assert sk.nearby_schools(-6.2, 106.8, schools=()) == []


# ── N9: river overflow zones ────────────────────────────────────────────────
def test_river_overflow_known_kecamatan():
    out = fp.river_overflow_zone(kecamatan="Cengkareng")
    assert out["in_river_overflow_zone"] is True
    assert out["affected_river"]


def test_river_overflow_unknown_is_false():
    out = fp.river_overflow_zone(kecamatan="NoSuchKecamatanXYZ")
    assert out["in_river_overflow_zone"] is False
    assert out["affected_river"] is None


# ── N10: 2023 hazard index in VulnerabilityContext ──────────────────────────
def test_hazard_2023_known_kota():
    h = bc._hazard_2023_for("Jakarta Barat")
    assert "hazard_index_2023" in h
    assert "hazard_category_2023" in h


def test_hazard_2023_unknown_kota_empty():
    assert bc._hazard_2023_for("Atlantis") == {}


def test_vulnerability_to_dict_has_hazard_and_historical():
    vc = bc.VulnerabilityContext(0.5, 0.45, "MEDIUM", 1_000_000, 30, "Jakarta Timur", bc.DATA_SOURCE_STATIC)
    d = vc.to_dict()
    assert "hazard_index_2023" in d
    assert "historical_flood_frequency" in d
    # base contract preserved
    assert d["district"] == "Jakarta Timur"
