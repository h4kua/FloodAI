"""Regression tests for the 2026-10-24 evaluation fixes in the realtime-native model."""

from __future__ import annotations

import numpy as np
import pytest
import xgboost as xgb

from realtime_native.bundle import _CalibratedBoosterAdapter
from realtime_native.training import _expected_calibration_error, _select_threshold


def test_select_threshold_falls_back_to_f2_instead_of_flagging_nothing():
    # No threshold reaches precision 0.30: positives score no higher than negatives.
    y = np.array([0] * 90 + [1] * 10)
    p = np.r_[np.linspace(0.05, 0.95, 90), np.linspace(0.05, 0.6, 10)]
    threshold, recall, precision, sweep = _select_threshold(y, p)
    assert sweep.attrs["tier"] == 3
    assert recall > 0
    assert threshold < 1.0


def test_select_threshold_meets_both_floors_when_possible():
    y = np.array([0] * 80 + [1] * 20)
    p = np.r_[np.linspace(0.0, 0.5, 80), np.linspace(0.4, 1.0, 20)]
    threshold, recall, precision, sweep = _select_threshold(y, p)
    assert sweep.attrs["tier"] == 1
    assert recall >= 0.80 and precision >= 0.30


def test_ece_is_zero_when_bins_match_outcomes():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    p = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0])
    assert _expected_calibration_error(y, p) == pytest.approx(0.0)


def test_ece_weights_each_gap_by_its_own_bin():
    # Bin [0.8, 0.9): 4 rows, mean p 0.85, half positive → gap 0.35, weight 1.0
    y = np.array([0, 0, 1, 1])
    p = np.full(4, 0.85)
    assert _expected_calibration_error(y, p) == pytest.approx(0.35)


def _tiny_booster(seed: int):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(60, 3))
    y = (X[:, 0] + rng.normal(scale=0.5, size=60) > 0).astype(int)
    return xgb.train({"objective": "binary:logistic", "max_depth": 2}, xgb.DMatrix(X, label=y), num_boost_round=5)


def test_adapter_pairs_each_calibrator_with_its_own_fold_booster():
    boosters = (_tiny_booster(1), _tiny_booster(2))
    folds = [{"a": -4.0, "b": 2.0}, {"a": -2.0, "b": 1.0}]
    adapter = _CalibratedBoosterAdapter(
        booster=boosters[0],
        calibration_payload={"method": "sigmoid", "folds": folds},
        fold_boosters=boosters,
    )
    X = np.random.default_rng(3).normal(size=(10, 3))
    dmat = xgb.DMatrix(X)
    expected = np.mean([
        1.0 / (1.0 + np.exp(f["a"] * np.clip(b.predict(dmat), 1e-7, 1 - 1e-7) + f["b"]))
        for b, f in zip(boosters, folds)
    ], axis=0)
    np.testing.assert_allclose(adapter.predict_proba(X)[:, 1], expected, rtol=1e-6)


def test_served_bundle_matches_trained_ensemble():
    """The deployed native bundle must reproduce model.pkl (CalibratedClassifierCV)."""
    import joblib

    from realtime_native.bundle import load_runtime_bundle
    from utils.paths import REALTIME_NATIVE_BUNDLE_DIR

    bundle = load_runtime_bundle()
    trained = joblib.load(REALTIME_NATIVE_BUNDLE_DIR / "model.pkl")
    X = bundle.scaler.transform(np.random.default_rng(4).normal(size=(50, len(bundle.feature_list))))
    np.testing.assert_allclose(
        bundle.model.predict_proba(X)[:, 1], trained.predict_proba(X)[:, 1], atol=1e-5,
    )
