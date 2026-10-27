#!/usr/bin/env python
"""
Train a candidate realtime-native bundle and compare it with the current pipeline.

Candidate: the proxy features are dropped (training.CORE_FEATURES) and the model is
Platt-calibrated on the most recent labelled year before the test year
(calibration="latest_year"). Both pipelines are trained forward in time —
train 2020–2022, validate/calibrate 2023, test 2024 — so they are judged on a
year neither has seen.

The served bundle (models/realtime_native_bundle) is never written. The candidate
goes to models/candidates/realtime_native_core_latestcal/ in the same native
format as the served bundle, so promoting it later is a file swap (inference
must then read the bundle's feature_list instead of REALTIME_NATIVE_FEATURES).

Outputs artifacts/reports/candidate_comparison.json and candidate_comparison.md.
Usage (repo root):  python scripts/train_candidate.py [--bootstrap 1000]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (_PROJECT_ROOT, _PROJECT_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import realtime_native.training as training  # noqa: E402
from evaluate_model import YEAR_SPLIT, _redirect_training_outputs, _with_ci  # noqa: E402
from realtime_native.bundle import load_runtime_bundle  # noqa: E402
from retrain_bundle import _re_export_only  # noqa: E402
from utils.paths import MODELS_DIR, REPORTS_DIR  # noqa: E402

CANDIDATE_DIR = MODELS_DIR / "candidates" / "realtime_native_core_latestcal"
_SEED = 42


def _train(out_dir: Path, **kwargs) -> dict:
    _redirect_training_outputs(out_dir)
    return training.train_realtime_native_model(year_split=YEAR_SPLIT, return_test_predictions=True, **kwargs)


def _summary(report: dict, n_boot: int) -> dict:
    preds = report["_test_predictions"]
    threshold = float(report["performance"]["optimal_threshold"])
    return {
        "features": report["feature_count"],
        "calibration": report["calibration"],
        "threshold": round(threshold, 4),
        "validation_recall": round(report["performance"]["validation_recall_at_threshold"], 4),
        "validation_precision": round(report["performance"]["validation_precision_at_threshold"], 4),
        "metrics": _with_ci(np.asarray(preds["y_test"]), np.asarray(preds["test_proba"]), threshold, n_boot),
    }


def _paired_gain(y: np.ndarray, base: np.ndarray, cand: np.ndarray, n_boot: int) -> dict:
    """Candidate minus current on the same resampled 2024 rows (95 % percentile CI)."""
    rng = np.random.default_rng(_SEED)
    gains = {"roc_auc": [], "pr_auc": []}
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        gains["roc_auc"].append(roc_auc_score(y[idx], cand[idx]) - roc_auc_score(y[idx], base[idx]))
        gains["pr_auc"].append(average_precision_score(y[idx], cand[idx]) - average_precision_score(y[idx], base[idx]))
    return {
        name: {"mean": round(float(np.mean(v)), 4), "ci95": [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]}
        for name, v in gains.items()
    }


def _markdown(result: dict) -> str:
    def row(label: str, s: dict) -> str:
        m = s["metrics"]
        ci = lambda k: f"{m[k]['value']:.3f} [{m[k]['ci95'][0]:.3f}–{m[k]['ci95'][1]:.3f}]"
        return (f"| {label} | {s['features']} | {s['calibration']['method']} ({s['calibration']['fit_on']}) "
                f"| {ci('roc_auc')} | {ci('pr_auc')} | {ci('recall')} | {ci('precision')} "
                f"| {ci('brier')} | {m['ece']:.3f} | {s['threshold']:.3f} |")

    g = result["gain"]
    return "\n".join([
        "# Candidate vs current pipeline (by year: train 2020–2022, validate 2023, test 2024)",
        "",
        f"Generated {result['generated_at']} by `scripts/train_candidate.py` "
        f"({result['bootstrap_resamples']} bootstrap resamples, 95 % CIs). Test year 2024: "
        f"{result['current']['metrics']['test_rows']} rows, {result['current']['metrics']['test_positives']} floods.",
        "",
        "| Pipeline | Features | Calibration | ROC-AUC | PR-AUC | Recall | Precision | Brier | ECE | Threshold |",
        "|---|---|---|---|---|---|---|---|---|---|",
        row("Current", result["current"]),
        row("Candidate", result["candidate"]),
        "",
        f"- Paired gain (candidate minus current, same 2024 rows): ROC-AUC {g['roc_auc']['mean']:+.3f} "
        f"[{g['roc_auc']['ci95'][0]:+.3f} to {g['roc_auc']['ci95'][1]:+.3f}], "
        f"PR-AUC {g['pr_auc']['mean']:+.3f} [{g['pr_auc']['ci95'][0]:+.3f} to {g['pr_auc']['ci95'][1]:+.3f}].",
        "- Recall and precision are at each pipeline's own threshold, chosen on 2023 "
        "(11 floods), so they move a lot between runs; ROC-AUC, PR-AUC, Brier and ECE do not depend on it.",
        f"- Candidate bundle: `{result['candidate_bundle']}` (not served). Native-format parity with "
        f"the trained model: max probability difference ={result['candidate_parity_max_abs_diff']:.2e}.",
        "- Data: bootstrap-proxy kecamatan-month rows; no observed field labels.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", type=int, default=1000, help="bootstrap resamples (default 1000)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        current = _train(Path(tmp) / "current")
        candidate = _train(Path(tmp) / "candidate", features=training.CORE_FEATURES, calibration="latest_year")

        if CANDIDATE_DIR.exists():
            shutil.rmtree(CANDIDATE_DIR)
        shutil.copytree(Path(tmp) / "candidate" / "bundle", CANDIDATE_DIR)
    if _re_export_only(CANDIDATE_DIR) != 0:
        raise RuntimeError("native re-export of the candidate failed")

    # The exported bundle must reproduce the trained model on the 2024 rows.
    X_test, _ = _test_rows(training.CORE_FEATURES)
    bundle = load_runtime_bundle(CANDIDATE_DIR / "manifest.json")
    served_like = bundle.model.predict_proba(bundle.scaler.transform(X_test))[:, 1]
    trained = np.asarray(candidate["_test_predictions"]["test_proba"])
    parity = float(np.max(np.abs(served_like - trained)))

    y = np.asarray(current["_test_predictions"]["y_test"])
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bootstrap_resamples": args.bootstrap,
        "split": {"train": "2020–2022", "validation": "2023", "test": "2024"},
        "current": _summary(current, args.bootstrap),
        "candidate": _summary(candidate, args.bootstrap),
        "gain": _paired_gain(y, np.asarray(current["_test_predictions"]["test_proba"]), trained, args.bootstrap),
        "candidate_bundle": str(CANDIDATE_DIR.relative_to(_PROJECT_ROOT)).replace("\\", "/"),
        "candidate_features": list(training.CORE_FEATURES),
        "candidate_parity_max_abs_diff": parity,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "candidate_comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (REPORTS_DIR / "candidate_comparison.md").write_text(_markdown(result), encoding="utf-8")
    print(_markdown(result))
    return 0


def _test_rows(features: list[str]):
    """2024 rows in training order, with the leak-free frequency feature."""
    import pandas as pd

    from realtime_native.feature_builder import REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH, kecamatan_flood_freq_map_before

    df = pd.read_csv(REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    years = df["timestamp"].dt.year
    maps = {int(yr): kecamatan_flood_freq_map_before(int(yr)) for yr in years.unique()}
    df["kecamatan_historical_flood_freq"] = [maps[int(yr)].get(s, 0.0) for yr, s in zip(years, df["name_3"])]
    test = df[years >= YEAR_SPLIT[1]]
    return test[features].apply(pd.to_numeric, errors="coerce").fillna(0.0), test["banjir"].astype(int)


if __name__ == "__main__":
    sys.exit(main())
