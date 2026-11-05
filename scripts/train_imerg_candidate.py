#!/usr/bin/env python
"""
Candidate realtime-native model with GPM IMERG rain (the served bundle is never written).

The served bundle is trained on data/processed/cleaned_flood_data_jakarta.csv, whose
max_rainfall / avg_rainfall columns feed every rain-derived feature (and the water-level,
humidity and BMKG proxies). The candidate swaps those two columns for IMERG rain of the
kecamatan's 0.1-degree cell -- the wettest day of the month and the mean daily rain, in WIB
days -- and rebuilds the dataset with the same builder, so nothing else changes.

Models, all trained by year (train 2020–2022, validate 2023, test 2024) with the served trainer:
  served         dataset rain, the 17 served features
  imerg_all      IMERG rain, the 17 served features
  imerg_no_proxy IMERG rain, without the temperature, humidity and BMKG proxy features
Each is scored on the 2024 rows against the dataset label and the BPBD label, and each
candidate is compared with the served model on the same rows (paired bootstrap, 95 %).
Needs the IMERG cache from scripts/fetch_imerg_history.py.
Outputs artifacts/reports/imerg_candidate.{json,md}.

Usage (repo root):  python scripts/train_imerg_candidate.py [--bootstrap 1000]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (_PROJECT_ROOT, _PROJECT_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import realtime_native.training as training  # noqa: E402
from evaluate_model import YEAR_SPLIT  # noqa: E402
from fetch_imerg_history import build_points  # noqa: E402
from hourly_rain_experiment import _imerg_series, daily_rain_features  # noqa: E402
from precision_experiments import _train, bpbd_labels, operating_points, score  # noqa: E402
from realtime_native.feature_builder import REALTIME_NATIVE_FEATURES, build_bootstrap_training_dataset  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

CLEANED_CSV = PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv"
_SEED = 42


def imerg_monthly() -> pd.DataFrame:
    """(cell, year, month) -> wettest WIB day and mean daily rain, in mm."""
    frames = []
    for cell in sorted(set(build_points().values())):
        daily = daily_rain_features(_imerg_series(cell))["d0"]
        monthly = daily.groupby([daily.index.year, daily.index.month]).agg(["max", "mean"])
        monthly.index.names = ["year", "month"]
        frames.append(monthly.reset_index().assign(cell=cell))
    return pd.concat(frames).rename(columns={"max": "imerg_max", "mean": "imerg_mean"})


def imerg_input(cleaned: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """The cleaned dataset with its two rain columns replaced by IMERG rain."""
    points = build_points()
    rain = imerg_monthly()
    out = cleaned.assign(cell=cleaned["name_3"].map(points))
    out = out.merge(rain, on=["cell", "year", "month"], how="left")
    missing = int(out["imerg_max"].isna().sum())
    if missing:
        raise SystemExit(f"{missing} rows have no IMERG rain; run scripts/fetch_imerg_history.py")
    check = {
        "corr_max_rainfall": round(float(out["max_rainfall"].corr(out["imerg_max"])), 3),
        "corr_avg_rainfall": round(float(out["avg_rainfall"].corr(out["imerg_mean"])), 3),
        "dataset_max_rainfall_median": round(float(out["max_rainfall"].median()), 1),
        "imerg_max_median": round(float(out["imerg_max"].median()), 1),
        "dataset_avg_rainfall_median": round(float(out["avg_rainfall"].median()), 1),
        "imerg_mean_median": round(float(out["imerg_mean"].median()), 1),
    }
    out["max_rainfall"], out["avg_rainfall"] = out["imerg_max"], out["imerg_mean"]
    return out.drop(columns=["cell", "imerg_max", "imerg_mean"]), check


def _paired(y, p_base, p_cand, n_boot, rng) -> dict:
    """95 % interval of candidate minus served, resampling the same test rows."""
    diffs = {"roc_auc": [], "pr_auc": []}
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        diffs["roc_auc"].append(roc_auc_score(y[idx], p_cand[idx]) - roc_auc_score(y[idx], p_base[idx]))
        diffs["pr_auc"].append(average_precision_score(y[idx], p_cand[idx]) - average_precision_score(y[idx], p_base[idx]))
    return {k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for k, v in diffs.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="IMERG candidate vs served model, by year")
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()
    no_proxy = [f for f in REALTIME_NATIVE_FEATURES if f not in training.PROXY_FEATURES]
    variants = {"served": ("dataset", None), "imerg_all": ("imerg", None), "imerg_no_proxy": ("imerg", no_proxy)}

    cleaned = pd.read_csv(CLEANED_CSV)
    results: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "split": "train 2020–2022, validate 2023, test 2024", "runs": {}}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        datasets = {}
        for name, frame in (("dataset", cleaned), ("imerg", None)):
            if frame is None:
                frame, results["rain_check"] = imerg_input(cleaned)
            src = tmp / f"cleaned_{name}.csv"
            frame.to_csv(src, index=False)
            datasets[name] = tmp / f"bootstrap_{name}.csv"
            build_bootstrap_training_dataset(input_path=src, output_path=datasets[name])

        base = pd.read_csv(datasets["dataset"])
        years = pd.to_datetime(base["timestamp"]).dt.year
        # Same sort the trainer applies, so label rows line up with its test predictions.
        ordered = pd.to_datetime(base["timestamp"]).sort_values().index
        ordered = ordered[years.loc[ordered].to_numpy() >= YEAR_SPLIT[1]]
        labels = {"dataset": base["banjir"].loc[ordered].to_numpy(), "bpbd": bpbd_labels(base).loc[ordered].to_numpy()}

        preds = {}
        for name, (rain, features) in variants.items():
            original = training.train_realtime_native_model
            if features is not None:
                training.train_realtime_native_model = lambda *a, _f=features, **k: original(*a, features=_f, **k)
            try:
                run = _train(datasets[rain], YEAR_SPLIT, tmp / name)
            finally:
                training.train_realtime_native_model = original
            assert (run["y_test"] == labels["dataset"]).all(), "row order"
            preds[name] = run["p_test"]
            rules = operating_points(run["y_val"], run["p_val"], run["threshold"])
            results["runs"][name] = {
                "rain": rain, "features": features or list(REALTIME_NATIVE_FEATURES),
                "calibration": run["calibration"], "threshold": round(run["threshold"], 4),
                **{f"on_{lab}_labels": score(y, run["p_test"], rules, args.bootstrap) for lab, y in labels.items()},
            }
            print(f"{name}: dataset-label AUC {results['runs'][name]['on_dataset_labels']['roc_auc']}", flush=True)

        rng = np.random.default_rng(_SEED)
        results["vs_served"] = {
            name: {lab: _paired(y, preds["served"], preds[name], args.bootstrap, rng) for lab, y in labels.items()}
            for name in variants if name != "served"
        }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "imerg_candidate.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (REPORTS_DIR / "imerg_candidate.md").write_text(_markdown(results), encoding="utf-8")
    print(_markdown(results))
    return 0


def _markdown(res: dict) -> str:
    c = res["rain_check"]
    lines = ["# IMERG candidate vs served model", "",
             f"Generated {res['generated_at']} by `scripts/train_imerg_candidate.py`. The served bundle is not touched. "
             f"Split: {res['split']}.", "",
             f"Rain input: dataset `max_rainfall` vs IMERG wettest day, correlation {c['corr_max_rainfall']} "
             f"(medians {c['dataset_max_rainfall_median']} vs {c['imerg_max_median']} mm); `avg_rainfall` vs IMERG "
             f"mean daily rain, correlation {c['corr_avg_rainfall']} (medians {c['dataset_avg_rainfall_median']} vs "
             f"{c['imerg_mean_median']} mm).", "",
             "| Model | Labels | Test rows / floods | ROC-AUC [95 %] | PR-AUC [95 %] | Danger rule: recall / precision / alarms |",
             "|---|---|---|---|---|---|"]
    for name, run in res["runs"].items():
        for lab in ("dataset", "bpbd"):
            s = run[f"on_{lab}_labels"]
            op = s["operating_points"][0]
            lines.append(f"| {name} | {lab} | {s['test_rows']} / {s['test_positives']} | "
                         f"{s['roc_auc'][0]} [{s['roc_auc'][1]}–{s['roc_auc'][2]}] | "
                         f"{s['pr_auc'][0]} [{s['pr_auc'][1]}–{s['pr_auc'][2]}] | "
                         f"{op['recall']} / {op['precision']} / {op['alarms']} |")
    lines += ["", "## Candidate minus served, same 2024 rows (paired bootstrap, 95 %)", "",
              "| Candidate | Labels | ROC-AUC difference | PR-AUC difference |", "|---|---|---|---|"]
    for name, by_label in res["vs_served"].items():
        for lab, ci in by_label.items():
            lines.append(f"| {name} | {lab} | {ci['roc_auc']} | {ci['pr_auc']} |")
    lines += ["", "- The Danger rule is the served one (recall first, precision >= 0.30 on the validation year).",
              "- The BPBD label marks a kecamatan-month as flooded when any RW in it reported a flood that month.",
              "- IMERG Final lags about 3.5 months, so serving this candidate would need IMERG Early rain."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
