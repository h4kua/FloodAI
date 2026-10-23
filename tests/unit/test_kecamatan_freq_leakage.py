"""kecamatan_flood_freq_map_before() must only count events from past years,
so training never sees outcomes from its own validation/test period."""

import json

from realtime_native.feature_builder import _KECAMATAN_HISTORY_PATH, kecamatan_flood_freq_map_before


def _counts_before(year):
    payload = json.loads(_KECAMATAN_HISTORY_PATH.read_text(encoding="utf-8"))
    return {
        slug: sum(n for y, n in rec["events_by_year"].items() if y.isdigit() and int(y) < year)
        for slug, rec in payload["by_kecamatan"].items()
    }


def test_frequency_uses_only_years_before_cutoff():
    freq = kecamatan_flood_freq_map_before(2023)
    counts = _counts_before(2023)
    top = max(counts, key=counts.get)
    assert freq[top] == 1.0
    assert all(0.0 <= v <= 1.0 for v in freq.values())
    for slug, n in counts.items():
        assert freq[slug] == round(n / counts[top], 4)


def test_no_history_before_first_year_gives_zero():
    assert set(kecamatan_flood_freq_map_before(2020).values()) == {0.0}


def test_cutoff_changes_the_feature():
    # The leak this guards against: later years (incl. the test period) change the values.
    assert kecamatan_flood_freq_map_before(2023) != kecamatan_flood_freq_map_before(2027)
