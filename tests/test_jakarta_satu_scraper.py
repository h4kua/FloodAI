"""
Jakarta Satu scraper tests (DATA-1).

All tests target pure parser functions — no Selenium, no DB, no network.
The Selenium layer (scrape_raw / scrape_all / _build_driver) requires a live
browser and is covered by: python scripts/run_jakarta_satu_ingest.py --dry-run

Test groups:
  A. parse_water_gates — realistic text, edge cases, empty input
  B. parse_rt_impact   — realistic text, edge cases, empty input
  C. parse_area_impact — normal values, missing, malformed
  D. Graceful missing-panel handling
  E. Deterministic normalisation
  F. DB repository wiring with mock connection
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from unittest.mock import Mock

import pytest

from services.jakarta_satu_scraper import (
    AffectedRT,
    JakartaSatuSnapshot,
    OutOfBandOnlyError,
    WaterGateReading,
    parse_area_impact,
    parse_rt_impact,
    parse_water_gates,
    scrape_all,
)


# ---------------------------------------------------------------------------
# Synthetic panel texts
# ---------------------------------------------------------------------------

_WATER_GATES_TEXT = """\
Data Pintu Air
MANGGARAI
850 cm
Siaga 2
KATULAMPA
310 cm
Siaga 3
DEPOK
192 cm
Normal
PESANGGRAHAN
48 cm
Normal
"""

_WATER_GATES_NO_CM = """\
Data Pintu Air
MANGGARAI
850
Siaga 2
KATULAMPA
310
Normal
"""

_WATER_GATES_MIXED_CASE = """\
Data Pintu Air
Manggarai
850 cm
siaga 2
Katulampa
310 cm
NORMAL
"""

_RT_TEXT = """\
Daftar RT Terdampak Banjir
001/002 Cipinang Melayu Jakarta Timur
003/001 Cawang Jakarta Timur
005/004 Penjaringan Jakarta Utara
002/003 Kel. Pejaten Timur Jakarta Selatan
"""

_RT_TEXT_COMPACT = """\
Daftar RT Terdampak Banjir
1/2 Cipinang Melayu Jakarta Timur
10/3 Cawang Jakarta Timur
"""

_AREA_TEXT = """\
Luas Wilayah Terdampak Banjir = Luas Area Seluruh RT Terdampak (km²)
2.47
"""

_AREA_COMMA = "Luas Wilayah Terdampak Banjir\n3,15\n"
_AREA_WITH_UNIT = "Luas Wilayah Terdampak Banjir\n5.20 km²\n"


# ---------------------------------------------------------------------------
# A. parse_water_gates
# ---------------------------------------------------------------------------


def test_water_gates_parses_gate_names():
    gates, _ = parse_water_gates(_WATER_GATES_TEXT)
    names = [g.gate_name for g in gates]
    assert "MANGGARAI" in names
    assert "KATULAMPA" in names


def test_water_gates_extracts_level_cm():
    gates, _ = parse_water_gates(_WATER_GATES_TEXT)
    manggarai = next(g for g in gates if g.gate_name == "MANGGARAI")
    assert manggarai.water_level_cm == pytest.approx(850.0)


def test_water_gates_extracts_status():
    gates, _ = parse_water_gates(_WATER_GATES_TEXT)
    manggarai = next(g for g in gates if g.gate_name == "MANGGARAI")
    assert "siaga" in manggarai.status.lower() or "2" in manggarai.status


def test_water_gates_parses_without_cm_suffix():
    gates, _ = parse_water_gates(_WATER_GATES_NO_CM)
    manggarai = next((g for g in gates if g.gate_name == "MANGGARAI"), None)
    assert manggarai is not None
    assert manggarai.water_level_cm == pytest.approx(850.0)


def test_water_gates_case_insensitive_status():
    gates, _ = parse_water_gates(_WATER_GATES_MIXED_CASE)
    statuses = [g.status.lower() for g in gates]
    assert any("siaga" in s or "normal" in s for s in statuses)


def test_water_gates_empty_returns_empty_with_warning():
    gates, warnings = parse_water_gates("")
    assert gates == []
    assert any("empty" in w.lower() for w in warnings)


def test_water_gates_whitespace_only_returns_empty():
    gates, warnings = parse_water_gates("   \n  \t  ")
    assert gates == []
    assert len(warnings) > 0


def test_water_gates_header_only_no_gates():
    gates, warnings = parse_water_gates(
        "Data Pintu Air\nNama Pintu Air\nTinggi\nStatus\n"
    )
    assert gates == []
    assert len(warnings) > 0


def test_water_gates_no_crash_on_garbage():
    gates, warnings = parse_water_gates("xyz 999999\n!!@#$%\n\x00\x01")
    assert isinstance(gates, list)
    assert isinstance(warnings, list)


def test_water_gates_raw_line_preserved():
    gates, _ = parse_water_gates(_WATER_GATES_TEXT)
    for g in gates:
        assert isinstance(g.raw_line, str) and len(g.raw_line) > 0


def test_water_gates_multiple_entries():
    gates, _ = parse_water_gates(_WATER_GATES_TEXT)
    assert len(gates) >= 3


def test_water_gates_returns_correct_type():
    gates, _ = parse_water_gates(_WATER_GATES_TEXT)
    for g in gates:
        assert isinstance(g, WaterGateReading)


# ---------------------------------------------------------------------------
# B. parse_rt_impact
# ---------------------------------------------------------------------------


def test_rt_parses_multiple_entries():
    rts, _ = parse_rt_impact(_RT_TEXT)
    assert len(rts) >= 3


def test_rt_identifier_zero_padded():
    rts, _ = parse_rt_impact(_RT_TEXT)
    ids = [r.rt_identifier for r in rts]
    assert "001/002" in ids


def test_rt_compact_ids_zero_padded():
    rts, _ = parse_rt_impact(_RT_TEXT_COMPACT)
    ids = [r.rt_identifier for r in rts]
    assert "001/002" in ids
    assert "010/003" in ids


def test_rt_extracts_wilayah():
    rts, _ = parse_rt_impact(_RT_TEXT)
    wilayahs = [r.wilayah.lower() for r in rts]
    assert any("timur" in w for w in wilayahs)
    assert any("utara" in w for w in wilayahs)


def test_rt_kel_prefix_stripped():
    rts, _ = parse_rt_impact(_RT_TEXT)
    for r in rts:
        assert not r.kelurahan.lower().startswith("kel.")


def test_rt_empty_returns_empty_with_warning():
    rts, warnings = parse_rt_impact("")
    assert rts == []
    assert any("empty" in w.lower() for w in warnings)


def test_rt_no_rt_patterns_returns_warning():
    rts, warnings = parse_rt_impact("Daftar RT Terdampak Banjir\nno RT entries here\n")
    assert rts == []
    assert len(warnings) > 0


def test_rt_no_crash_on_garbage():
    rts, warnings = parse_rt_impact("!!@#$%^&*()\n\x00\x01")
    assert isinstance(rts, list)
    assert isinstance(warnings, list)


def test_rt_raw_line_preserved():
    rts, _ = parse_rt_impact(_RT_TEXT)
    for r in rts:
        assert "/" in r.raw_line


def test_rt_returns_correct_type():
    rts, _ = parse_rt_impact(_RT_TEXT)
    for r in rts:
        assert isinstance(r, AffectedRT)


# ---------------------------------------------------------------------------
# C. parse_area_impact
# ---------------------------------------------------------------------------


def test_area_parses_standard_decimal():
    area, warnings = parse_area_impact(_AREA_TEXT)
    assert area == pytest.approx(2.47)
    assert warnings == []


def test_area_parses_comma_decimal():
    area, _ = parse_area_impact(_AREA_COMMA)
    assert area == pytest.approx(3.15)


def test_area_parses_with_unit_suffix():
    area, _ = parse_area_impact(_AREA_WITH_UNIT)
    assert area == pytest.approx(5.20)


def test_area_empty_returns_none_with_warning():
    area, warnings = parse_area_impact("")
    assert area is None
    assert any("empty" in w.lower() for w in warnings)


def test_area_header_only_returns_none_with_warning():
    area, warnings = parse_area_impact(
        "Luas Wilayah Terdampak Banjir = Luas Area Seluruh RT Terdampak (km²)\n"
    )
    assert area is None
    assert len(warnings) > 0


def test_area_zero_not_returned():
    area, _ = parse_area_impact("Luas\n0\n")
    assert area is None


def test_area_implausible_large_rejected():
    area, _ = parse_area_impact("Luas\n99999\n")
    assert area is None


def test_area_no_crash_on_garbage():
    area, warnings = parse_area_impact("!!! no numbers ???")
    assert area is None
    assert isinstance(warnings, list)


# ---------------------------------------------------------------------------
# D. Graceful missing-panel handling
# ---------------------------------------------------------------------------


def test_all_parsers_safe_on_empty_string():
    gates, gw = parse_water_gates("")
    rts, rw = parse_rt_impact("")
    area, aw = parse_area_impact("")

    assert gates == []
    assert rts == []
    assert area is None
    assert len(gw) > 0
    assert len(rw) > 0
    assert len(aw) > 0


def test_partial_panels_do_not_raise():
    gates, _ = parse_water_gates(_WATER_GATES_TEXT)
    rts, _ = parse_rt_impact("")       # rt panel absent
    area, _ = parse_area_impact("")    # area panel absent

    assert len(gates) >= 1
    assert rts == []
    assert area is None


# ---------------------------------------------------------------------------
# E. Deterministic normalisation
# ---------------------------------------------------------------------------


def test_water_gates_deterministic():
    r1, _ = parse_water_gates(_WATER_GATES_TEXT)
    r2, _ = parse_water_gates(_WATER_GATES_TEXT)
    assert [(g.gate_name, g.water_level_cm, g.status) for g in r1] == \
           [(g.gate_name, g.water_level_cm, g.status) for g in r2]


def test_rt_impact_deterministic():
    r1, _ = parse_rt_impact(_RT_TEXT)
    r2, _ = parse_rt_impact(_RT_TEXT)
    assert [(r.rt_identifier, r.wilayah) for r in r1] == \
           [(r.rt_identifier, r.wilayah) for r in r2]


def test_area_deterministic():
    a1, _ = parse_area_impact(_AREA_TEXT)
    a2, _ = parse_area_impact(_AREA_TEXT)
    assert a1 == a2


# ---------------------------------------------------------------------------
# F. DB repository wiring with mock connection
# ---------------------------------------------------------------------------


def _mock_conn(snapshot_id: int = 42) -> MagicMock:
    conn = MagicMock()
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = (snapshot_id,)
    conn.cursor.return_value = cur
    return conn


def _make_snapshot(n_gates: int = 2, n_rts: int = 2) -> JakartaSatuSnapshot:
    gates = [
        WaterGateReading(f"GATE_{i}", float(100 + i * 50), "Normal", f"GATE_{i}")
        for i in range(n_gates)
    ]
    rts = [
        AffectedRT(f"{i:03d}/001", f"Kelurahan {i}", "Jakarta Timur", f"{i:03d}/001 K{i}")
        for i in range(n_rts)
    ]
    return JakartaSatuSnapshot(
        scraped_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_url="https://test.example/dashboard",
        scrape_duration_ms=5000,
        panels_found=3,
        water_gates=gates,
        affected_rts=rts,
        flooded_area_km2=2.5,
        raw_water_gates_text="raw gates",
        raw_rt_impact_text="raw rts",
        raw_area_impact_text="raw area",
        warnings=[],
        scrape_success=True,
    )


def test_persist_snapshot_calls_commit():
    from db.repositories.jakarta_satu_repository import persist_snapshot

    conn = _mock_conn()
    persist_snapshot(conn, _make_snapshot())
    conn.commit.assert_called_once()


def test_persist_snapshot_returns_snapshot_id():
    from db.repositories.jakarta_satu_repository import persist_snapshot

    conn = _mock_conn(snapshot_id=99)
    result = persist_snapshot(conn, _make_snapshot())
    assert result == 99


def test_persist_snapshot_executes_master_insert():
    from db.repositories.jakarta_satu_repository import persist_snapshot

    conn = _mock_conn()
    persist_snapshot(conn, _make_snapshot(n_gates=0, n_rts=0))
    cur = conn.cursor.return_value.__enter__.return_value
    assert cur.execute.call_count >= 1


def test_insert_water_gates_empty_skips_db():
    from db.repositories.jakarta_satu_repository import insert_water_gates

    conn = _mock_conn()
    result = insert_water_gates(conn, 1, datetime.now(timezone.utc), [])
    assert result == 0
    conn.cursor.assert_not_called()


def test_insert_rt_impact_empty_skips_db():
    from db.repositories.jakarta_satu_repository import insert_rt_impact

    conn = _mock_conn()
    result = insert_rt_impact(conn, 1, datetime.now(timezone.utc), [])
    assert result == 0
    conn.cursor.assert_not_called()


def test_insert_water_gates_returns_count():
    from db.repositories.jakarta_satu_repository import insert_water_gates

    conn = _mock_conn()
    gates = _make_snapshot(n_gates=4).water_gates
    result = insert_water_gates(conn, 1, datetime.now(timezone.utc), gates)
    assert result == 4


def test_insert_rt_impact_returns_count():
    from db.repositories.jakarta_satu_repository import insert_rt_impact

    conn = _mock_conn()
    rts = _make_snapshot(n_rts=6).affected_rts
    result = insert_rt_impact(conn, 1, datetime.now(timezone.utc), rts)
    assert result == 6


def test_scrape_all_rejects_api_process_execution(monkeypatch):
    fake_log = Mock()

    monkeypatch.setenv("FLOOD_ALLOW_RUNTIME_SCRAPE", "1")
    monkeypatch.setattr("services.jakarta_satu_scraper._is_api_process", lambda: True)
    monkeypatch.setattr("services.jakarta_satu_scraper._log", fake_log)

    with pytest.raises(OutOfBandOnlyError):
        scrape_all()

    fake_log.error.assert_called_once()
