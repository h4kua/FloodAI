"""Unit tests for scripts/parse_rekap_kejadian_banjir.py's sheet parser."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.parse_rekap_kejadian_banjir import _parse_sheet

# Column layout used by the fixture, matching the real "No | Name" merged-cell
# pattern: header text lands on the "No" sub-column, the name is one column right.
_KEC_NUM, _KEC_NAME = 2, 3
_KEL_NUM, _KEL_NAME = 4, 5
_RW, _HEIGHT, _TANGGAL = 6, 7, 8
_MENINGGAL, _LUKA_BERAT, _LUKA_RINGAN, _PENGUNGSIAN = 9, 10, 11, 12

_N_COLS = 13


def _blank_row() -> list:
    return [None] * _N_COLS


def _header_frame(extra_rows: list[list]) -> pd.DataFrame:
    header = _blank_row()
    header[_KEC_NUM] = "KECAMATAN"
    header[_KEL_NUM] = "KELURAHAN"
    header[_RW] = "NAMA RW"
    header[_HEIGHT] = "KETINGGIAN AIR"
    header[_TANGGAL] = "TANGGAL KEJADIAN"
    header[_MENINGGAL] = "MENINGGAL"
    header[_LUKA_BERAT] = "LUKA BERAT"
    header[_LUKA_RINGAN] = "LUKA RINGAN"
    header[_PENGUNGSIAN] = "JUMLAH TEMPAT PENGUNGSIAN"

    rows = [_blank_row(), _blank_row(), header, *extra_rows]
    return pd.DataFrame(rows)


def _city_header(kota: str) -> list:
    row = _blank_row()
    row[_KEC_NUM] = kota
    return row


def _incident_row(*, kec_num=None, kec_name=None, kel_num=None, kel_name=None,
                   rw=None, height=None, tanggal=None, meninggal=None,
                   luka_berat=None, luka_ringan=None, pengungsian=None) -> list:
    row = _blank_row()
    row[_KEC_NUM] = kec_num
    row[_KEC_NAME] = kec_name
    row[_KEL_NUM] = kel_num
    row[_KEL_NAME] = kel_name
    row[_RW] = rw
    row[_HEIGHT] = height
    row[_TANGGAL] = tanggal
    row[_MENINGGAL] = meninggal
    row[_LUKA_BERAT] = luka_berat
    row[_LUKA_RINGAN] = luka_ringan
    row[_PENGUNGSIAN] = pengungsian
    return row


def test_parses_city_header_and_incident_row():
    df = _header_frame([
        _city_header("JAKARTA UTARA"),
        _incident_row(kec_num=1, kec_name="PENJARINGAN", kel_num=1, kel_name="KAMAL MUARA",
                      rw="RW 04", height="30 cm", tanggal="tgl. 01 Januari"),
    ])
    rows = _parse_sheet(df, year=2021, month=1)
    assert len(rows) == 1
    r = rows[0]
    assert r["kota_administrasi"] == "JAKARTA UTARA"
    assert r["kecamatan"] == "PENJARINGAN"
    assert r["kelurahan"] == "KAMAL MUARA"
    assert r["rw"] == "RW 04"
    assert r["ketinggian_air"] == "30 cm"
    assert r["tahun"] == 2021
    assert r["bulan"] == 1


def test_continuation_row_inherits_kecamatan_and_kelurahan():
    df = _header_frame([
        _city_header("JAKARTA UTARA"),
        _incident_row(kec_num=1, kec_name="PENJARINGAN", kel_num=1, kel_name="KAMAL MUARA",
                      rw="RW 04", height="30 cm", tanggal="tgl. 01 Januari"),
        # Same kelurahan, new RW/date — merged cells leave kec/kel blank.
        _incident_row(rw="RW 05", height="40 cm", tanggal="tgl. 02 Januari"),
    ])
    rows = _parse_sheet(df, year=2021, month=1)
    assert len(rows) == 2
    assert rows[1]["kecamatan"] == "PENJARINGAN"
    assert rows[1]["kelurahan"] == "KAMAL MUARA"
    assert rows[1]["rw"] == "RW 05"
    assert rows[1]["ketinggian_air"] == "40 cm"


def test_subtotal_row_skipped():
    df = _header_frame([
        _city_header("JAKARTA UTARA"),
        _incident_row(kec_num=1, kec_name="PENJARINGAN", kel_num=1, kel_name="KAMAL MUARA",
                      rw="RW 04", height="30 cm", tanggal="tgl. 01 Januari"),
        _incident_row(kel_name="SUBTOTAL JAKARTA UTARA", pengungsian=999),
    ])
    rows = _parse_sheet(df, year=2021, month=1)
    assert len(rows) == 1


def test_nihil_row_skipped():
    df = _header_frame([
        _city_header("JAKARTA PUSAT"),
        _incident_row(kec_num=1, kec_name="GAMBIR", kel_num=1, kel_name="NIHIL"),
    ])
    rows = _parse_sheet(df, year=2021, month=1)
    assert rows == []


def test_header_echo_footer_row_skipped():
    """Some sheets append a grand-total row whose cells literally repeat the
    header labels ("KECAMATAN"/"KELURAHAN") with monthly aggregate totals —
    must not be mistaken for a real kelurahan record."""
    df = _header_frame([
        _city_header("JAKARTA TIMUR"),
        _incident_row(kec_num=1, kec_name="MATRAMAN", kel_num=1, kel_name="BALE KAMBANG",
                      rw="RW 01", height="20 cm", tanggal="tgl. 01 Januari"),
        _incident_row(kec_name="KECAMATAN", kel_name="KELURAHAN",
                      height="350 cm", tanggal="tgl. 01, 02 Januari", meninggal=13),
    ])
    rows = _parse_sheet(df, year=2020, month=1)
    assert len(rows) == 1
    assert rows[0]["kelurahan"] == "BALE KAMBANG"


def test_two_city_blocks_do_not_leak_context():
    df = _header_frame([
        _city_header("JAKARTA UTARA"),
        _incident_row(kec_num=1, kec_name="PENJARINGAN", kel_num=1, kel_name="KAMAL MUARA",
                      rw="RW 04", height="30 cm", tanggal="tgl. 01 Januari"),
        _city_header("JAKARTA PUSAT"),
        _incident_row(kec_num=1, kec_name="GAMBIR", kel_num=1, kel_name="CIDENG",
                      rw="RW 02", height="25 cm", tanggal="tgl. 02 Januari"),
    ])
    rows = _parse_sheet(df, year=2021, month=1)
    assert len(rows) == 2
    assert rows[0]["kota_administrasi"] == "JAKARTA UTARA"
    assert rows[1]["kota_administrasi"] == "JAKARTA PUSAT"


def test_row_with_no_height_or_date_is_dropped():
    df = _header_frame([
        _city_header("JAKARTA UTARA"),
        _incident_row(kec_num=1, kec_name="PENJARINGAN", kel_num=1, kel_name="KAMAL MUARA"),
    ])
    rows = _parse_sheet(df, year=2021, month=1)
    assert rows == []


def test_missing_header_returns_empty():
    df = pd.DataFrame([_blank_row() for _ in range(5)])
    rows = _parse_sheet(df, year=2021, month=1)
    assert rows == []
