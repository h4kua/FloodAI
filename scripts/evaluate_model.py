#!/usr/bin/env python
"""
Evaluate the realtime-native flood model with 95 % bootstrap confidence intervals.

Three views, all on the bootstrap-proxy dataset (2,928 kecamatan-month rows, 2020–2024):

  deployed   The served bundle (models/realtime_native_bundle, loaded exactly as
             inference loads it) scored on its own random stratified test split.
  random     The training pipeline re-run with the stratified 68/12/20 split.
  by_year    The training pipeline re-run forward in time: train 2020–2022,
             validate 2023, test 2024. This is the honest estimate of how the
             pipeline generalises to a year it has not seen.

Re-runs train inside a temporary directory; production files are never written.

Outputs artifacts/reports/model_evaluation.json and model_evaluation.md.
Usage (repo root):  python scripts/evaluate_model.py [--bootstrap 1000]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import realtime_native.training as training  # noqa: E402
from realtime_native.bundle import load_runtime_bundle  # noqa: E402
from realtime_native.feature_builder import (  # noqa: E402
    REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
    REALTIME_NATIVE_FEATURES,
    kecamatan_flood_freq_map_before,
)
from utils.paths import REALTIME_NATIVE_BUNDLE_DIR, REPORTS_DIR  # noqa: E402

YEAR_SPLIT = (2023, 2024)  # validate 2023, test 2024
_SEED = 42


def _point_metrics(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    pred = p >= threshold
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "precision": float(precision_score(y, pred, zero_division=0)),
    }


def _with_ci(y: np.ndarray, p: np.ndarray, threshold: float, n_boot: int) -> dict:
    """Point estimate + percentile 95 % CI from resampling test rows."""
    point = _point_metrics(y, p, threshold)
    rng = np.random.default_rng(_SEED)
    samples: dict[str, list[float]] = {name: [] for name in point}
    n = len(y)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yb, pb = y[idx], p[idx]
        if yb.min() == yb.max():  # AUCs need both classes
            continue
        for name, value in _point_metrics(yb, pb, threshold).items():
            samples[name].append(value)
    out = {}
    for name, value in point.items():
        lo, hi = np.percentile(samples[name], [2.5, 97.5])
        out[name] = {"value": round(value, 4), "ci95": [round(float(lo), 4), round(float(hi), 4)]}
    out["ece"] = round(training._expected_calibration_error(y, p, n_bins=10), 4)
    out["prevalence"] = round(float(np.mean(y)), 4)
    out["test_rows"] = int(n)
    out["test_positives"] = int(y.sum())
    out["flagged_share"] = round(float(np.mean(p >= threshold)), 4)
    return out


def _leak_free_dataset() -> tuple[pd.DataFrame, pd.Series]:
    """Same features and row order as training (leak-free kecamatan frequency)."""
    df = pd.read_csv(REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    years = df["timestamp"].dt.year
    maps = {int(yr): kecamatan_flood_freq_map_before(int(yr)) for yr in years.unique()}
    df["kecamatan_historical_flood_freq"] = [maps[int(yr)].get(s, 0.0) for yr, s in zip(years, df["name_3"])]
    X = df[REALTIME_NATIVE_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y = pd.to_numeric(df["banjir"], errors="coerce").fillna(0).astype(int)
    return X, y


def evaluate_deployed(n_boot: int) -> dict:
    """Score the served bundle on its random stratified test split."""
    X, y = _leak_free_dataset()
    _, X_test, _, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, shuffle=True, stratify=y,
    )
    bundle = load_runtime_bundle()
    proba = bundle.model.predict_proba(bundle.scaler.transform(X_test))[:, 1]
    threshold = float(bundle.thresholds["danger"])
    return {
        "split": "random_stratified_68_12_20 (as deployed)",
        "threshold": round(threshold, 4),
        "calibration_method": bundle.calibration.get("method"),
        "metrics": _with_ci(np.asarray(y_test), proba, threshold, n_boot),
    }


def _redirect_training_outputs(out_dir: Path) -> None:
    """Point every path the trainer writes to into ``out_dir``."""
    models, reports = out_dir / "models", out_dir / "reports"
    models.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    training.MODELS_DIR, training.REPORTS_DIR = models, reports
    training.REALTIME_NATIVE_BUNDLE_DIR = out_dir / "bundle"
    for name in ("MODEL", "SCALER", "FEATURE_LIST", "MODEL_CARD", "OOD", "THRESHOLD"):
        attr = f"REALTIME_NATIVE_{name}_PATH"
        setattr(training, attr, models / Path(getattr(training, attr)).name)
    training.REALTIME_NATIVE_REPORT_PATH = reports / "realtime_native_model_report.json"
    training.HUMAN_REVIEW_QUEUE_PATH = reports / "pseudo_label_review_queue.json"


def evaluate_retrained(year_split, n_boot: int, out_dir: Path) -> dict:
    _redirect_training_outputs(out_dir)
    report = training.train_realtime_native_model(year_split=year_split, return_test_predictions=True)
    preds = report.pop("_test_predictions")
    threshold = float(report["performance"]["optimal_threshold"])
    return {
        "split": report["split_strategy"],
        "rows_train_val_test": [report["training_rows"], report["validation_rows"], report["test_rows"]],
        "threshold": round(threshold, 4),
        "threshold_selection_tier": json.load(open(training.REALTIME_NATIVE_THRESHOLD_PATH, encoding="utf-8")).get("selection_tier"),
        "calibration_method": report["calibration"]["method"],
        "validation_recall": round(report["performance"]["validation_recall_at_threshold"], 4),
        "validation_precision": round(report["performance"]["validation_precision_at_threshold"], 4),
        "metrics": _with_ci(np.asarray(preds["y_test"]), np.asarray(preds["test_proba"]), threshold, n_boot),
    }


def _markdown(result: dict) -> str:
    rows = []
    for key, label in (("deployed", "Deployed bundle (random split)"),
                       ("random", "Pipeline re-run, random split"),
                       ("by_year", "Pipeline re-run, by year (test 2024)")):
        r = result[key]
        m = r["metrics"]
        fmt = lambda name: f"{m[name]['value']:.3f} [{m[name]['ci95'][0]:.3f}–{m[name]['ci95'][1]:.3f}]"
        rows.append(
            f"| {label} | {m['test_rows']} / {m['test_positives']} | {fmt('roc_auc')} | {fmt('pr_auc')} "
            f"| {m['prevalence']:.3f} | {fmt('recall')} | {fmt('precision')} | {fmt('brier')} | {m['ece']:.3f} "
            f"| {r['threshold']:.3f} |"
        )
    return "\n".join([
        "# Realtime-native model evaluation",
        "",
        f"Generated {result['generated_at']} by `scripts/evaluate_model.py` "
        f"({result['bootstrap_resamples']} bootstrap resamples, 95 % percentile CIs).",
        "",
        "| View | Test rows / positives | ROC-AUC | PR-AUC | PR-AUC no-skill | Recall | Precision | Brier | ECE | Threshold |",
        "|---|---|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "- Data: bootstrap-proxy kecamatan-month rows (2020–2024); several features are proxies "
        "(see context.md, *Model & evaluation*). No observed field labels exist yet.",
        "- The by-year view trains on 2020–2022, picks the threshold on 2023 and tests on 2024 "
        "(few positives, so its intervals are wide).",
        "- PR-AUC no-skill baseline = share of flood rows in the test set.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", type=int, default=1000, help="bootstrap resamples (default 1000)")
    args = parser.parse_args()

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bootstrap_resamples": args.bootstrap,
        "bundle": str(REALTIME_NATIVE_BUNDLE_DIR),
        "deployed": evaluate_deployed(args.bootstrap),
    }
    with tempfile.TemporaryDirectory() as tmp:
        result["random"] = evaluate_retrained(None, args.bootstrap, Path(tmp) / "random")
        result["by_year"] = evaluate_retrained(YEAR_SPLIT, args.bootstrap, Path(tmp) / "by_year")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "model_evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (REPORTS_DIR / "model_evaluation.md").write_text(_markdown(result), encoding="utf-8")
    print(_markdown(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
