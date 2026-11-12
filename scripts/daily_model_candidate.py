#!/usr/bin/env python
"""
Calibrate the daily kecamatan flood model and build a candidate bundle with a model card
(exploratory; nothing is served and the served bundle is never written).

1. Out-of-sample probabilities: for every year Y in 2016-2025, XGBoost F4 trained on 2013..Y-1 (as in
   scripts/long_experiments.py).
2. Calibration: an isotonic map fitted on the out-of-sample probabilities of the years before Y is applied
   to year Y (2017 onward), so no year calibrates itself. ECE (10 equal-width bins and 10 equal-count bins)
   and the Brier score, raw vs calibrated, per year and pooled; a reliability table for the pooled years.
3. Levels: Waspada / Siaga / Bahaya thresholds on the calibrated probability chosen by alarm budget
   (4 / 2 / 1 alarm days per kecamatan per month) on the out-of-sample years 2016-2024, scored on 2025.
4. Candidate: XGBoost F4 refitted on 2013 to Sep 2025 and an isotonic map fitted on all out-of-sample
   probabilities, written to models/candidates/daily_f4/ (model.json, isotonic.json, model_card.json).

Outputs artifacts/reports/daily_model_candidate.{json,md}.
Usage (repo root):  python scripts/daily_model_candidate.py [--cpu]
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.long_experiments import long_dataset  # noqa: E402
from scripts.thesis_experiments import F4, make_model  # noqa: E402
from utils.paths import REPORTS_DIR  # noqa: E402

OUT = _PROJECT_ROOT / "models" / "candidates" / "daily_f4"
DAYS_PER_MONTH = 30.44
BUDGETS = {"Waspada": 4, "Siaga": 2, "Bahaya": 1}  # alarm days per kecamatan per month


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10, equal_count: bool = False) -> float:
    if equal_count:
        edges = np.unique(np.quantile(p, np.linspace(0, 1, bins + 1)))
        if len(edges) < 2:  # every probability equal: one bin holding them all
            edges = np.array([edges[0], edges[0]])
    else:
        edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, len(edges) - 2)
    total = 0.0
    for b in range(len(edges) - 1):
        m = idx == b
        if m.any():
            total += m.mean() * abs(p[m].mean() - y[m].mean())
    return round(float(total), 4)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", message=".*mismatched devices.*")
    device = "cpu" if args.cpu else "cuda"

    data = long_dataset()
    oos = []
    for year in range(2016, 2026):
        train, test = data[data["year"] < year], data[data["year"] == year]
        model = make_model("xgboost", train["flood"].to_numpy(), device=device).fit(train[F4], train["flood"])
        oos.append(pd.DataFrame({"year": year, "kecamatan": test["kecamatan"].to_numpy(), "date": test["date"].to_numpy(),
                                 "y": test["flood"].to_numpy(), "raw": model.predict_proba(test[F4])[:, 1]}))
        print("out-of-sample", year, flush=True)
    oos = pd.concat(oos, ignore_index=True)

    oos["cal"] = np.nan
    for year in range(2017, 2026):
        past, now = oos["year"] < year, oos["year"] == year
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(oos.loc[past, "raw"], oos.loc[past, "y"])
        oos.loc[now, "cal"] = iso.predict(oos.loc[now, "raw"])
    scored = oos.dropna(subset=["cal"])

    res: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
                 "features": F4, "per_year": {}}
    for year, g in scored.groupby("year"):
        y = g["y"].to_numpy()
        res["per_year"][int(year)] = {
            "floods": int(y.sum()), "prevalence": round(float(y.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y, g["cal"])), 3),
            "raw": {"ece": ece(y, g["raw"].to_numpy()), "ece_equal_count": ece(y, g["raw"].to_numpy(), equal_count=True),
                    "brier": round(float(brier_score_loss(y, g["raw"])), 4), "mean_p": round(float(g["raw"].mean()), 4)},
            "calibrated": {"ece": ece(y, g["cal"].to_numpy()), "ece_equal_count": ece(y, g["cal"].to_numpy(), equal_count=True),
                           "brier": round(float(brier_score_loss(y, g["cal"])), 4), "mean_p": round(float(g["cal"].mean()), 4)},
        }
    y, raw, cal = scored["y"].to_numpy(), scored["raw"].to_numpy(), scored["cal"].to_numpy()
    res["pooled_2017_2025"] = {
        "raw": {"ece": ece(y, raw), "ece_equal_count": ece(y, raw, equal_count=True), "brier": round(float(brier_score_loss(y, raw)), 4)},
        "calibrated": {"ece": ece(y, cal), "ece_equal_count": ece(y, cal, equal_count=True),
                       "brier": round(float(brier_score_loss(y, cal)), 4)},
        "prevalence": round(float(y.mean()), 4)}
    edges = np.unique(np.quantile(cal, np.linspace(0, 1, 11)))
    bins = np.clip(np.searchsorted(edges, cal, side="right") - 1, 0, len(edges) - 2)
    res["reliability_calibrated"] = [{"p_low": round(float(edges[b]), 4), "p_high": round(float(edges[b + 1]), 4),
                                      "rows": int((bins == b).sum()), "mean_predicted": round(float(cal[bins == b].mean()), 4),
                                      "observed_rate": round(float(y[bins == b].mean()), 4)}
                                     for b in range(len(edges) - 1) if (bins == b).any()]

    # Level thresholds by alarm budget on 2016-2024 out-of-sample (calibrated where available), scored on 2025.
    fit_years = scored[scored["year"] <= 2024]
    thr = {lvl: float(np.quantile(fit_years["cal"], 1 - n / DAYS_PER_MONTH)) for lvl, n in BUDGETS.items()}
    test25 = scored[scored["year"] == 2025]
    n_km = test25["kecamatan"].nunique() * test25["date"].dt.to_period("M").nunique()
    res["levels"] = {"thresholds": {k: round(v, 4) for k, v in thr.items()}, "scored_on_2025": {}}
    for lvl, t in thr.items():
        pred = test25["cal"].to_numpy() >= t
        yy = test25["y"].to_numpy()
        tp, fp = int((pred & (yy == 1)).sum()), int((pred & (yy == 0)).sum())
        res["levels"]["scored_on_2025"][lvl] = {"alarm_days_per_kecamatan_month": round((tp + fp) / n_km, 2),
                                                "recall": round(tp / max(int(yy.sum()), 1), 3),
                                                "precision": round(tp / (tp + fp), 3) if tp + fp else None}

    # Candidate bundle.
    OUT.mkdir(parents=True, exist_ok=True)
    final = make_model("xgboost", data["flood"].to_numpy(), device=device).fit(data[F4], data["flood"])
    final.set_params(device="cpu")
    final.get_booster().save_model(OUT / "model.json")
    iso_all = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(oos["raw"], oos["y"])
    (OUT / "isotonic.json").write_text(json.dumps({"x": iso_all.X_thresholds_.tolist(), "y": iso_all.y_thresholds_.tolist()}),
                                       encoding="utf-8")
    card = {
        "name": "daily kecamatan flood model (candidate, not served)", "created": res["generated_at"],
        "rows": "42 kecamatan x WIB days, 2013-01-01 to 2025-09-30", "label": "BPBD flood recorded in the kecamatan that day",
        "features": F4, "rain": "GPM IMERG Final V07 (serving needs IMERG Early, about a day behind)",
        "model": "XGBoost, scikit-learn API defaults of scripts/thesis_experiments.make_model", "calibration": "isotonic on out-of-sample years 2016-2025",
        "out_of_sample": {"roc_auc_pooled_2016_2022": "0.841 [0.822-0.858]", "roc_auc_pooled_2023_2025": "0.869 [0.852-0.884]",
                          "ece_pooled_2017_2025_calibrated": res["pooled_2017_2025"]["calibrated"]["ece"]},
        "level_thresholds": res["levels"]["thresholds"],
        "limits": ["BPBD dates partly readable after 2022", "no water-level features (they exist only 2016-2021 and 2025)",
                   "kecamatan-level, daily; not a street-level forecast"],
    }
    (OUT / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")

    L = ["# Daily model: calibration, warning levels and a candidate bundle", "",
         f"Generated {res['generated_at']} by `scripts/daily_model_candidate.py` on {device}. Nothing here is served.", "",
         "Out-of-sample XGBoost F4 probabilities (each year from a model trained on earlier years), calibrated with an isotonic "
         "map fitted on the earlier years only.", "",
         "| Year | Floods | ROC-AUC | ECE raw | ECE calibrated | ECE calibrated (equal-count bins) | Brier raw | Brier calibrated | Mean p calibrated | Prevalence |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for yr, s in res["per_year"].items():
        L.append(f"| {yr} | {s['floods']} | {s['roc_auc']} | {s['raw']['ece']} | {s['calibrated']['ece']} | "
                 f"{s['calibrated']['ece_equal_count']} | {s['raw']['brier']} | {s['calibrated']['brier']} | "
                 f"{s['calibrated']['mean_p']} | {s['prevalence']} |")
    p = res["pooled_2017_2025"]
    L += ["", f"Pooled 2017–2025: ECE raw {p['raw']['ece']} → calibrated {p['calibrated']['ece']} "
          f"(equal-count bins {p['raw']['ece_equal_count']} → {p['calibrated']['ece_equal_count']}); "
          f"Brier {p['raw']['brier']} → {p['calibrated']['brier']}; prevalence {p['prevalence']}.", "",
          "Reliability, calibrated, pooled (equal-count bins):", "",
          "| Predicted p range | Rows | Mean predicted | Observed flood rate |", "|---|---|---|---|"]
    for b in res["reliability_calibrated"]:
        L.append(f"| {b['p_low']}–{b['p_high']} | {b['rows']} | {b['mean_predicted']} | {b['observed_rate']} |")
    L += ["", "Warning levels by alarm budget (chosen on 2016–2024, scored on Jan–Sep 2025):", "",
          "| Level | Budget (alarm days per kecamatan-month) | Threshold | 2025 alarm days per kecamatan-month | 2025 recall | 2025 precision |",
          "|---|---|---|---|---|---|"]
    for lvl, s in res["levels"]["scored_on_2025"].items():
        L.append(f"| {lvl} | {BUDGETS[lvl]} | {res['levels']['thresholds'][lvl]} | {s['alarm_days_per_kecamatan_month']} | "
                 f"{s['recall']} | {s['precision']} |")
    L += ["", f"Candidate bundle: `models/candidates/daily_f4/` (model.json, isotonic.json, model_card.json)."]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "daily_model_candidate.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (REPORTS_DIR / "daily_model_candidate.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
