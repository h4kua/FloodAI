"""DSDA publishes water levels in millimetres; the snapshot carries centimetres."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PARSER = Path(__file__).resolve().parents[1] / "poskobanjir" / "services" / "parser.py"
_spec = importlib.util.spec_from_file_location("poskobanjir_parser", _PARSER)
parser = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parser)


def _dsda_item(**overrides):
    item = {
        "RECORD_STATUS": 1, "NAMA_PINTU_AIR": "Bendung. Katulampa 2",
        "TINGGI_AIR": 2100, "TINGGI_AIR_SEBELUMNYA": 2050,
        "SIAGA1": 2000, "SIAGA2": 1500, "SIAGA3": 800, "SIAGA4": 0,
        "STATUS_SIAGA": "Status : Siaga 1",
    }
    item.update(overrides)
    return item


def test_json_feed_is_converted_to_centimetres():
    (record,) = parser.parse_poskobanjir_json([_dsda_item()])
    # Katulampa's official Siaga 1 is 200 cm; DSDA sends 2000.
    assert record["siaga1"] == "200"
    assert record["tinggi_air"] == "210"
    assert record["tinggi_air_sebelumnya"] == "205"
    assert record["tinggi_air_unit"] == "cm"
    assert record["tma_unaltered"] == "2100"  # raw value kept


def test_conversion_keeps_decimals_and_negative_datums():
    (record,) = parser.parse_poskobanjir_json([_dsda_item(TINGGI_AIR=5174, TINGGI_AIR_SEBELUMNYA=-1748)])
    assert record["tinggi_air"] == "517.4"
    assert record["tinggi_air_sebelumnya"] == "-174.8"


def test_xml_fallback_is_converted_too():
    xml = (
        "<data><row><nama_pintu_air>P.A. Manggarai</nama_pintu_air>"
        "<tinggi_air>5174</tinggi_air><siaga1>9500</siaga1></row></data>"
    )
    (record,) = parser.parse_poskobanjir_xml(xml)
    assert record["tinggi_air"] == "517.4"
    assert record["siaga1"] == "950"


def test_conversion_is_applied_once():
    once = parser.dsda_mm_to_cm({"tinggi_air": "5174"})
    assert parser.dsda_mm_to_cm(once)["tinggi_air"] == "517.4"


def test_missing_and_blank_values_are_left_alone():
    record = parser.dsda_mm_to_cm({"tinggi_air": "", "siaga1": None})
    assert record["tinggi_air"] == ""
    assert record["siaga1"] is None
