"""ECE of scripts/daily_model_candidate.py: equal-width and equal-count bins."""

import numpy as np

from scripts.daily_model_candidate import ece


def test_perfectly_calibrated_probabilities_have_zero_ece():
    p = np.array([0.0] * 10 + [1.0] * 10)
    y = np.array([0] * 10 + [1] * 10)
    assert ece(y, p) == 0.0
    assert ece(y, p, equal_count=True) == 0.0


def test_overconfident_probabilities_are_penalised_by_the_gap():
    y = np.array([0, 0, 0, 1] * 25)          # 25 % floods
    p = np.full(100, 0.75)                    # always says 75 %
    assert ece(y, p) == 0.5
    assert ece(y, p, equal_count=True) == 0.5
