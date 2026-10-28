#!/usr/bin/env python
"""
Precision experiments for the realtime-native model (the served bundle is never written).

A. Operating points: precision/recall on the test year for Danger thresholds chosen on the
   validation year by different rules (the current recall-first rule, best F1, best F0.5,
   precision >= 0.5), so a stricter Danger level can be judged on data the rule never saw.
B. Labels: the bootstrap dataset's `banjir` column marks only 276 of the 895 kecamatan-months
   in which BPBD recorded a flood (2020–2024). The pipeline is retrained with labels taken from
   the BPBD per-RW records (data/raw/rekap_kejadian_2020_2025.csv, one RW-date counted once) and
   both models are scored against both label sets on the same test rows.

Each variant is trained by year (train 2020–2022, validate 2023, test 2024) and on the random
split the served bundle uses. Outputs artifacts/reports/precision_experiments.{json,md}.
Usage (repo root):  python scripts/precision_experiments.py [--bootstrap 1000]
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
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (_PROJECT_ROOT, _PROJECT_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import realtime_native.training as training  # noqa: E402
from build_kelurahan_flood_history import _slug  # noqa: E402
from evaluate_model import YEAR_SPLIT, _redirect_training_outputs  # noqa: E402
from realtime_native.feature_builder import REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH  # noqa: E402
from utils.paths import REPORTS_DIR  # noqa: E402

REKAP_CSV = _PROJECT_ROOT / "data" / "raw" / "rekap_kejadian_2020_2025.csv"
_SEED = 42


def bpbd_labels(df: pd.DataFrame) -> pd.Series:
    """1 when BPBD recorded at least one flood in that kecamatan and month."""
    rekap = pd.read_csv(REKAP_CSV).drop_duplicates()  # one RW-date once (RT rows repeat)
    flooded = set(zip(rekap["kecamatan"].map(_slug), rekap["tahun"], rekap["bulan"]))
    ts = pd.to_datetime(df["timestamp"])
    return pd.Series([int((_slug(k), y, m) in flooded) for k, y, m in zip(df["name_3"], ts.dt.year, ts.dt.month)],
                     index=df.index)


def _train(dataset: Path, year_split, out_dir: Path) -> dict:
    """Train in out_dir; return val and test labels/probabilities and the chosen threshold."""
    captured = {}
    original = training._select_threshold

    def capture(y_val, val_proba):
        captured["y_val"], captured["p_val"] = np.asarray(y_val), np.asarray(val_proba)
        return original(y_val, val_proba)

    _redirect_training_outputs(out_dir)
    training._select_threshold = capture
    try:
        report = training.train_realtime_native_model(dataset_path=dataset, year_split=year_split,
                                                      return_test_predictions=True)
    finally:
        training._select_threshold = original
    preds = report.pop("_test_predictions")
    return {
        "split": report["split_strategy"],
        "threshold": float(report["performance"]["optimal_threshold"]),
        "calibration": report["calibration"]["method"],
        "y_val": captured["y_val"], "p_val": captured["p_val"],
        "y_test": np.asarray(preds["y_test"]), "p_test": np.asarray(preds["test_proba"]),
    }


def _fbeta(p, r, beta):
    return (1 + beta**2) * p * r / (beta**2 * p + r + 1e-12)


def operating_points(y_val, p_val, current: float) -> dict[str, float]:
    """Danger thresholds chosen on the validation fold by several rules."""
    prec, rec, thr = precision_recall_curve(y_val, p_val)
    prec, rec = prec[:-1], rec[:-1]  # drop the recall-0 end point
    rules = {"current (recall-first, precision >= 0.30)": current}
    rules["best F1 on validation"] = float(thr[np.argmax(_fbeta(prec, rec, 1))])
    rules["best F0.5 on validation (precision-weighted)"] = float(thr[np.argmax(_fbeta(prec, rec, 0.5))])
    ok = prec >= 0.5
    if ok.any():
        rules["highest recall with precision >= 0.50 on validation"] = float(thr[ok][np.argmax(rec[ok])])
    return rules


def _at(y, p, t):
    pred = p >= t
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    return tp, fp, int((y == 1).sum())


def _ci(stat, y, p, n_boot, rng):
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        vals.append(stat(y[idx], p[idx]))
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return round(float(stat(y, p)), 3), round(float(lo), 3), round(float(hi), 3)


def score(y, p, rules: dict[str, float], n_boot: int) -> dict:
    rng = np.random.default_rng(_SEED)
    out = {
        "test_rows": int(len(y)), "test_positives": int(y.sum()), "prevalence": round(float(y.mean()), 3),
        "roc_auc": _ci(roc_auc_score, y, p, n_boot, rng),
        "pr_auc": _ci(average_precision_score, y, p, n_boot, rng),
        "operating_points": [],
    }
    for name, t in rules.items():
        tp, fp, pos = _at(y, p, t)
        prec = tp / (tp + fp) if tp + fp else 0.0
        out["operating_points"].append({
            "rule": name, "threshold": round(t, 4), "recall": round(tp / pos, 3) if pos else 0.0,
            "precision": round(prec, 3), "f1": round(_fbeta(prec, tp / pos if pos else 0, 1), 3),
            "alarms": tp + fp, "true_alarms": tp, "false_alarms": fp, "missed": pos - tp,
        })
    sweep = []
    for t in (0.05, 0.07, 0.10, 0.126, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60):
        tp, fp, pos = _at(y, p, t)
        sweep.append({"threshold": t, "recall": round(tp / pos, 3) if pos else 0.0,
                      "precision": round(tp / (tp + fp), 3) if tp + fp else None, "alarms": tp + fp})
    out["fixed_threshold_sweep"] = sweep
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()

    base = pd.read_csv(REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH)
    bpbd = base.copy()
    bpbd["banjir"] = bpbd_labels(bpbd)
    years = pd.to_datetime(base["timestamp"]).dt.year
    label_table = pd.DataFrame({"year": years, "dataset_label": base["banjir"], "bpbd_label": bpbd["banjir"]})
    label_summary = {
        int(y): {"dataset": int(g["dataset_label"].sum()), "bpbd": int(g["bpbd_label"].sum()),
                 "both": int((g["dataset_label"] & g["bpbd_label"]).sum()), "rows": int(len(g))}
        for y, g in label_table.groupby("year")
    }

    results: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "label_summary": label_summary, "runs": {}}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bpbd_path = tmp / "bootstrap_bpbd_labels.csv"
        bpbd.to_csv(bpbd_path, index=False)
        label_of = {"dataset": base["banjir"], "bpbd": bpbd["banjir"]}
        for split_name, split in (("by_year", YEAR_SPLIT), ("random", None)):
            for label_name, path in (("dataset", REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH), ("bpbd", bpbd_path)):
                run = _train(path, split, tmp / f"{split_name}_{label_name}")
                rules = operating_points(run["y_val"], run["p_val"], run["threshold"])
                entry = {"split": run["split"], "calibration": run["calibration"],
                         "validation_positives": int(run["y_val"].sum()),
                         "on_own_labels": score(run["y_test"], run["p_test"], rules, args.bootstrap)}
                if split == YEAR_SPLIT:
                    # Same 2024 rows for both datasets, so each model can be scored on the other labels.
                    other = "bpbd" if label_name == "dataset" else "dataset"
                    # Same sort the trainer applies (default kind), so rows line up with y_test.
                    ordered = pd.to_datetime(base["timestamp"]).sort_values().index
                    ordered = ordered[years.loc[ordered].to_numpy() >= YEAR_SPLIT[1]]
                    y_other = label_of[other].loc[ordered].to_numpy()
                    assert (label_of[label_name].loc[ordered].to_numpy() == run["y_test"]).all(), "row order"
                    entry[f"on_{other}_labels"] = score(y_other, run["p_test"], rules, args.bootstrap)
                results["runs"][f"{split_name}/{label_name}"] = entry
                print(f"{split_name}/{label_name}: AUC {entry['on_own_labels']['roc_auc']} "
                      f"PR-AUC {entry['on_own_labels']['pr_auc']}", flush=True)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "precision_experiments.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (REPORTS_DIR / "precision_experiments.md").write_text(_markdown(results), encoding="utf-8")
    print("wrote", REPORTS_DIR / "precision_experiments.md")
    return 0


def _markdown(res: dict) -> str:
    lines = ["# Precision experiments", "",
             f"Generated {res['generated_at']} by `scripts/precision_experiments.py`. The served bundle is not touched.", "",
             "## Labels: dataset vs BPBD records (kecamatan-months flagged as flood)", "",
             "| Year | Rows | Dataset label | BPBD records | Both |", "|---|---|---|---|---|"]
    for y, s in res["label_summary"].items():
        lines.append(f"| {y} | {s['rows']} | {s['dataset']} | {s['bpbd']} | {s['both']} |")
    for key, run in res["runs"].items():
        for label_key in [k for k in run if k.startswith("on_")]:
            s = run[label_key]
            lines += ["", f"## {key} model, scored {label_key.replace('_', ' ')}", "",
                      f"Split: {run['split']}; calibration {run['calibration']}; validation positives "
                      f"{run['validation_positives']}. Test {s['test_rows']} rows, {s['test_positives']} floods "
                      f"(prevalence {s['prevalence']}). ROC-AUC {s['roc_auc'][0]} [{s['roc_auc'][1]}–{s['roc_auc'][2]}], "
                      f"PR-AUC {s['pr_auc'][0]} [{s['pr_auc'][1]}–{s['pr_auc'][2]}].", "",
                      "| Danger threshold rule (chosen on validation) | Threshold | Recall | Precision | F1 | Alarms | False alarms | Missed |",
                      "|---|---|---|---|---|---|---|---|"]
            for op in s["operating_points"]:
                lines.append(f"| {op['rule']} | {op['threshold']} | {op['recall']} | {op['precision']} | {op['f1']} | "
                             f"{op['alarms']} | {op['false_alarms']} | {op['missed']} |")
    lines += ["", "- Recall/precision at a threshold chosen on one validation year move a lot between runs; "
              "ROC-AUC and PR-AUC do not depend on the threshold.",
              "- The BPBD label marks a kecamatan-month as flooded when any RW in it reported a flood that month."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
