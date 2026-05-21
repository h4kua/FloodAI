"""
Unit tests for the API location normaliser.

Guards two related bugs:

  * Bug 1 — DB persistence ValidationError(field="location") when the
    request body sent ``location`` as a ``dict`` instead of a string.
  * Bug 2 — BNPB ``mapped_district: null`` / ``code: NOT_APPLICABLE``
    when the same dict survived through to ``map_to_jakarta_district``,
    stringified as ``"{'city': 'Jakarta'}"`` and failed all alias lookups.

The normaliser runs ONCE at the API boundary and always returns one of the
six canonical kota strings. These tests pin the contract the user spec
defined and prevent silent regressions.
"""

from __future__ import annotations

import pytest

from api.main import (
    _DEFAULT_LOCATION,
    _VALID_KOTA,
    _normalize_location,
)


# ─── Identity / canonical-string inputs ──────────────────────────────────────


@pytest.mark.parametrize("input_value,expected", [
    ("Jakarta Utara",   "Jakarta Utara"),
    ("Jakarta Selatan", "Jakarta Selatan"),
    ("Jakarta Pusat",   "Jakarta Pusat"),
    ("Jakarta Timur",   "Jakarta Timur"),
    ("Jakarta Barat",   "Jakarta Barat"),
    ("Kepulauan Seribu", "Kepulauan Seribu"),
])
def test_canonical_string_passthrough(input_value: str, expected: str) -> None:
    assert _normalize_location(input_value) == expected


# ─── Case / whitespace normalisation ─────────────────────────────────────────


@pytest.mark.parametrize("input_value,expected", [
    ("jakarta selatan",      "Jakarta Selatan"),
    ("JAKARTA UTARA",        "Jakarta Utara"),
    ("  jakarta pusat  ",    "Jakarta Pusat"),
    ("jaKaRta TimUr",        "Jakarta Timur"),
])
def test_case_and_whitespace(input_value: str, expected: str) -> None:
    assert _normalize_location(input_value) == expected


# ─── Dict inputs (Bug 1+2 reproducer) ────────────────────────────────────────


@pytest.mark.parametrize("input_value,expected", [
    ({"city":     "jakarta selatan"}, "Jakarta Selatan"),
    ({"district": "Jakarta Pusat"},   "Jakarta Pusat"),
    ({"kota":     "Jakarta Timur"},   "Jakarta Timur"),
    ({"name":     "Jakarta Barat"},   "Jakarta Barat"),
    ({"kecamatan": "Tanjung Priok"},  "Jakarta Utara"),  # kecamatan → kota via alias
    # ``district`` takes priority over ``city`` per the request schema spec:
    # a payload like ``{"district": "Menteng", "city": "Jakarta"}`` must resolve
    # to the kecamatan-derived kota, not the ambiguous bare-city fallback.
    ({"city": "Jakarta Selatan", "district": "Jakarta Utara"}, "Jakarta Utara"),
    # Empty / whitespace values are skipped to the next key.
    ({"city": "", "district": "Jakarta Barat"}, "Jakarta Barat"),
])
def test_dict_extraction(input_value: dict, expected: str) -> None:
    assert _normalize_location(input_value) == expected


# ─── Ambiguous / missing → default ───────────────────────────────────────────


@pytest.mark.parametrize("input_value", [
    "Jakarta",            # bare kota → ambiguous
    {"city": "Jakarta"},  # bare kota in dict → ambiguous
    None,                 # absent
    {},                   # empty dict
    "",                   # empty string
    "   ",                # whitespace only
    {"city": ""},         # empty value in dict
    {"unrelated_key": "Jakarta Utara"},  # no recognised key → default
    "Bandung",            # outside DKI Jakarta scope
    42,                   # non-string, non-dict
    ["Jakarta Utara"],    # list — not a supported container
])
def test_ambiguous_or_unknown_defaults(input_value) -> None:
    assert _normalize_location(input_value) == _DEFAULT_LOCATION


# ─── Kecamatan / kelurahan / abbreviation aliases ────────────────────────────


@pytest.mark.parametrize("input_value,expected", [
    ("jaksel",          "Jakarta Selatan"),
    ("jak-ut",          "Jakarta Utara"),
    ("south jakarta",   "Jakarta Selatan"),
    ("Menteng",         "Jakarta Pusat"),
    ("Pluit",           "Jakarta Utara"),
    ("Cengkareng",      "Jakarta Barat"),
    ("Jatinegara",      "Jakarta Timur"),
    ("kep. seribu",     "Kepulauan Seribu"),
    ("thousand islands","Kepulauan Seribu"),
])
def test_alias_resolution(input_value: str, expected: str) -> None:
    assert _normalize_location(input_value) == expected


# ─── Contract guards ─────────────────────────────────────────────────────────


def test_result_is_always_in_valid_kota_set() -> None:
    """Whatever the input, the output MUST be one of the six valid kota."""
    for sample in (
        None, "", "   ", "Jakarta", "Bandung", 42, [],
        {"city": "Jakarta"}, {"city": ""},
        "Jakarta Utara", "jaksel", "Pluit",
    ):
        result = _normalize_location(sample)
        assert isinstance(result, str), f"non-str result for {sample!r}: {result!r}"
        assert result in _VALID_KOTA, f"result {result!r} not in canonical set"


def test_default_location_is_in_valid_set() -> None:
    """The advertised default must itself be a valid kota."""
    assert _DEFAULT_LOCATION in _VALID_KOTA
