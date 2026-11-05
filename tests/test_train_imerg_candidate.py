"""Unit tests for scripts/train_imerg_candidate.py (no IMERG cache, no training)."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts import train_imerg_candidate as tic


def _cleaned():
    return pd.DataFrame({
        "name_3": ["cakung", "tebet"], "year": [2024, 2024], "month": [1, 1],
        "max_rainfall": [70.0, 30.0], "avg_rainfall": [20.0, 10.0], "banjir": [1, 0],
    })


def test_imerg_input_swaps_only_the_two_rain_columns(monkeypatch):
    monkeypatch.setattr(tic, "build_points", lambda: {"cakung": "a", "tebet": "b"})
    monkeypatch.setattr(tic, "imerg_monthly", lambda: pd.DataFrame({
        "cell": ["a", "b"], "year": [2024, 2024], "month": [1, 1],
        "imerg_max": [101.0, 12.0], "imerg_mean": [9.0, 2.0],
    }))
    out, check = tic.imerg_input(_cleaned())
    assert out["max_rainfall"].tolist() == [101.0, 12.0]
    assert out["avg_rainfall"].tolist() == [9.0, 2.0]
    assert out["banjir"].tolist() == [1, 0]
    assert list(out.columns) == list(_cleaned().columns)
    assert check["imerg_max_median"] == pytest.approx(56.5)


def test_imerg_input_refuses_rows_without_imerg_rain(monkeypatch):
    monkeypatch.setattr(tic, "build_points", lambda: {"cakung": "a", "tebet": "b"})
    monkeypatch.setattr(tic, "imerg_monthly", lambda: pd.DataFrame({
        "cell": ["a"], "year": [2024], "month": [1], "imerg_max": [101.0], "imerg_mean": [9.0],
    }))
    with pytest.raises(SystemExit):
        tic.imerg_input(_cleaned())
