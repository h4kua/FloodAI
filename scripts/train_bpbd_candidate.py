#!/usr/bin/env python
"""
Train a candidate realtime-native bundle on BPBD flood labels and check how often each level fires.

The bootstrap dataset's `banjir` column marks 282 kecamatan-months as flooded; BPBD records show 895
(2020–2024, see scripts/precision_experiments.py). The candidate uses the same 17 features and
pipeline, with `banjir` replaced by "BPBD recorded a flood in this kecamatan and month". With these
labels the chronological 68/12/20 split has positives, so no random fallback is needed.

Thresholds are set on the validation rows instead of being derived from one number:
  Waspada (pre-alert)  highest threshold that still catches >= 95 % of validation floods
  Siaga   (warning)    the pipeline's recall-first rule (recall >= 0.80, precision >= 0.30)
  Bahaya  (danger)     best F1 on validation, kept above Siaga
The served bundle (models/realtime_native_bundle) is never written; the candidate goes to
models/candidates/realtime_native_bpbd_labels/ in the served native format.

Level check: for the served bundle and the candidate, the model-layer level of every 2023 and 2024
kecamatan-month (the served bundle saw most of these rows in training, so its share is in-sample),
the share of rows at each level where BPBD recorded a flood, and both models on the live snapshot
saved by --snapshot (the `features` block of GET /predict/realtime-native). The rule layers of the
decision engine (water-level floors, BMKG, data quality) are not simulated.

Outputs artifacts/reports/bpbd_candidate.{json,md}.
Usage (repo root):  python scripts/train_bpbd_candidate.py [--snapshot path/to/realtime-native.json]
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
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (_PROJECT_ROOT, _PROJECT_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import realtime_native.training as training  # noqa: E402
from evaluate_model import _redirect_training_outputs  # noqa: E402
from precision_experiments import bpbd_labels  # noqa: E402
from realtime_native.bundle import load_runtime_bundle  # noqa: E402
from realtime_native.feature_builder import (  # noqa: E402
    REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH,
    REALTIME_NATIVE_FEATURES,
    kecamatan_flood_freq_map_before,
)
from retrain_bundle import _re_export_only  # noqa: E402
from utils.paths import MODELS_DIR, REALTIME_NATIVE_BUNDLE_DIR, REPORTS_DIR  # noqa: E402

CANDIDATE_DIR = MODELS_DIR / "candidates" / "realtime_native_bpbd_labels"
LEVELS = ("SAFE", "PRE_ALERT", "WARNING", "DANGER")


def _train(dataset: Path, out_dir: Path) -> dict:
    captured = {}
    original = training._select_threshold

    def capture(y_val, val_proba):
        captured["y_val"], captured["p_val"] = np.asarray(y_val), np.asarray(val_proba)
        return original(y_val, val_proba)

    _redirect_training_outputs(out_dir)
    training._select_threshold = capture
    try:
        report = training.train_realtime_native_model(dataset_path=dataset, return_test_predictions=True)
    finally:
        training._select_threshold = original
    report.update(captured)
    return report


def _thresholds(y_val, p_val, warning: float) -> dict:
    prec, rec, thr = precision_recall_curve(y_val, p_val)
    prec, rec = prec[:-1], rec[:-1]
    pre_alert = float(thr[rec >= 0.95].max())
    f1 = 2 * prec * rec / (prec + rec + 1e-12)
    above = thr > warning
    danger = float(thr[above][np.argmax(f1[above])]) if above.any() else warning
    pre_alert = min(pre_alert, warning)

    def at(t):
        hit = p_val >= t
        tp = int((hit & (y_val == 1)).sum())
        return {"recall": round(tp / int(y_val.sum()), 3), "precision": round(tp / max(int(hit.sum()), 1), 3)}

    return {"pre_alert": round(pre_alert, 4), "warning": round(warning, 4), "danger": round(danger, 4),
            "validation": {"pre_alert": at(pre_alert), "warning": at(warning), "danger": at(danger)}}


def _level(p: np.ndarray, t: dict) -> np.ndarray:
    return np.select([p >= t["danger"], p >= t["warning"], p >= t["pre_alert"]],
                     ["DANGER", "WARNING", "PRE_ALERT"], "SAFE")


def _rows(years_wanted) -> pd.DataFrame:
    df = pd.read_csv(REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH, parse_dates=["timestamp"])
    df["bpbd"] = bpbd_labels(df)
    years = df["timestamp"].dt.year
    maps = {int(y): kecamatan_flood_freq_map_before(int(y)) for y in years.unique()}
    df["kecamatan_historical_flood_freq"] = [maps[int(y)].get(s, 0.0) for y, s in zip(years, df["name_3"])]
    return df[years.isin(years_wanted)]


def _proba(bundle, X: pd.DataFrame) -> np.ndarray:
    return bundle.model.predict_proba(bundle.scaler.transform(X))[:, 1]


def _level_table(levels: np.ndarray, flooded: np.ndarray) -> dict:
    out = {}
    for name in LEVELS:
        mask = levels == name
        out[name] = {"rows": int(mask.sum()), "share": round(float(mask.mean()), 3),
                     "bpbd_flood_rate": round(float(flooded[mask].mean()), 3) if mask.any() else None}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", type=Path, help="saved GET /predict/realtime-native response")
    args = parser.parse_args()

    base = pd.read_csv(REALTIME_NATIVE_BOOTSTRAP_DATASET_PATH)
    labelled = base.assign(banjir=bpbd_labels(base))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dataset = tmp / "bootstrap_bpbd_labels.csv"
        labelled.to_csv(dataset, index=False)
        report = _train(dataset, tmp / "run")
        if CANDIDATE_DIR.exists():
            shutil.rmtree(CANDIDATE_DIR)
        shutil.copytree(tmp / "run" / "bundle", CANDIDATE_DIR)

    thresholds = _thresholds(report["y_val"], report["p_val"], float(report["performance"]["optimal_threshold"]))
    threshold_path = CANDIDATE_DIR / "threshold.json"
    payload = json.loads(threshold_path.read_text(encoding="utf-8"))
    payload.update({
        "threshold": thresholds["danger"], "danger_threshold": thresholds["danger"],
        "warning_threshold": thresholds["warning"], "pre_alert_threshold": thresholds["pre_alert"],
        "label_source": "BPBD records (rekap_kejadian_2020_2025.csv), kecamatan-month",
        "selection_rule": "pre-alert: recall >= 0.95 on validation; warning: recall-first rule; danger: best F1 above warning",
    })
    threshold_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if _re_export_only(CANDIDATE_DIR) != 0:
        raise RuntimeError("native re-export of the candidate failed")

    served = load_runtime_bundle(REALTIME_NATIVE_BUNDLE_DIR / "manifest.json")
    candidate = load_runtime_bundle(CANDIDATE_DIR / "manifest.json")
    preds = report["_test_predictions"]
    y_test, p_trained = np.asarray(preds["y_test"]), np.asarray(preds["test_proba"])

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": report["split_strategy"], "calibration": report["calibration"]["method"],
        "rows_train_val_test": [report["training_rows"], report["validation_rows"], report["test_rows"]],
        "test": {"positives": int(y_test.sum()), "prevalence": round(float(y_test.mean()), 3),
                 "roc_auc": round(float(roc_auc_score(y_test, p_trained)), 3),
                 "pr_auc": round(float(average_precision_score(y_test, p_trained)), 3),
                 "ece": round(float(report["calibration"]["test_ece"]), 3),
                 "brier": round(float(report["calibration"]["test_brier"]), 3)},
        "thresholds": {"candidate": thresholds, "served": {k: served.thresholds[k] for k in ("pre_alert", "warning", "danger")}},
        "levels": {},
    }
    cand_t = thresholds
    for year in (2023, 2024):
        rows = _rows([year])
        X = rows[REALTIME_NATIVE_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        flooded = rows["bpbd"].to_numpy()
        result["levels"][str(year)] = {
            "bpbd_flood_rate": round(float(flooded.mean()), 3),
            "served": _level_table(_level(_proba(served, X), served.thresholds), flooded),
            "candidate": _level_table(_level(_proba(candidate, X), cand_t), flooded),
        }
    rows = _rows([2024])
    parity_X = rows[REALTIME_NATIVE_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    result["candidate_bundle_loads"] = bool(len(_proba(candidate, parity_X)) == len(parity_X))

    if args.snapshot and args.snapshot.exists():
        feats = json.loads(args.snapshot.read_text(encoding="utf-8"))["features"]
        X = pd.DataFrame([{f: float(feats.get(f, 0.0)) for f in REALTIME_NATIVE_FEATURES}])
        ps, pc = float(_proba(served, X)[0]), float(_proba(candidate, X)[0])
        result["live_snapshot"] = {"served": {"probability": round(ps, 4), "level": str(_level(np.array([ps]), served.thresholds)[0])},
                                   "candidate": {"probability": round(pc, 4), "level": str(_level(np.array([pc]), cand_t)[0])}}

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "bpbd_candidate.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (REPORTS_DIR / "bpbd_candidate.md").write_text(_markdown(result), encoding="utf-8")
    print(_markdown(result))
    return 0


def _markdown(r: dict) -> str:
    t, ct, st = r["test"], r["thresholds"]["candidate"], r["thresholds"]["served"]
    lines = ["# BPBD-label candidate (not served)", "",
             f"Generated {r['generated_at']} by `scripts/train_bpbd_candidate.py`. Bundle: "
             f"`models/candidates/realtime_native_bpbd_labels/`.", "",
             f"Split {r['split']} (train/val/test rows {r['rows_train_val_test']}); calibration {r['calibration']}. "
             f"Test: {t['positives']} BPBD floods (prevalence {t['prevalence']}), ROC-AUC {t['roc_auc']}, "
             f"PR-AUC {t['pr_auc']}, Brier {t['brier']}, ECE {t['ece']}.", "",
             "| Level | Served threshold | Candidate threshold | Candidate validation recall / precision |",
             "|---|---|---|---|"]
    for key, name in (("pre_alert", "Waspada"), ("warning", "Siaga"), ("danger", "Bahaya")):
        v = ct["validation"][key]
        lines.append(f"| {name} | {st[key]} | {ct[key]} | {v['recall']} / {v['precision']} |")
    for year, block in r["levels"].items():
        lines += ["", f"## Model-layer level, {year} kecamatan-months (BPBD flood rate {block['bpbd_flood_rate']})", "",
                  "| Level | Served: share of rows | Served: BPBD flood rate | Candidate: share of rows | Candidate: BPBD flood rate |",
                  "|---|---|---|---|---|"]
        for lvl in LEVELS:
            s, c = block["served"][lvl], block["candidate"][lvl]
            lines.append(f"| {lvl} | {s['share']} | {s['bpbd_flood_rate']} | {c['share']} | {c['bpbd_flood_rate']} |")
    if "live_snapshot" in r:
        s, c = r["live_snapshot"]["served"], r["live_snapshot"]["candidate"]
        lines += ["", f"Live snapshot (city features): served p={s['probability']} → {s['level']}; "
                  f"candidate p={c['probability']} → {c['level']}."]
    lines += ["", "- The served bundle was trained on a random split that includes most 2023–2024 rows, so its "
              "level shares there are in-sample; the candidate's 2024 rows are its test set.",
              "- Only the model layer is shown; the decision engine's rule layers can raise or cap the level.",
              "- Monthly training rows differ from 15-minute live snapshots, so live level shares will differ."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
