#!/usr/bin/env python
"""
Which flood drivers from the literature add skill? (exploratory; nothing here is served)

Each driver group is added on its own to feature set F4 of scripts/thesis_experiments.py
(rain, antecedent rain, upstream rain, place and season), the same XGBoost is fitted on
2020-2021, and the test years (2023 to Sep 2025) are scored against F4 with a paired bootstrap
over test dates (95 %). Validation PR-AUC (2022) is reported too: a group that helps on the test
years but not on 2022 is not a robust gain.

Usage (repo root):  python scripts/driver_ablation.py [--bootstrap 1000]
Outputs artifacts/reports/driver_ablation.{json,md}.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

from sklearn.metrics import average_precision_score, roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.thesis_experiments import F4, F5, DateBootstrap, fit_predict, kecamatan_days, split  # noqa: E402
from utils.paths import REPORTS_DIR  # noqa: E402

GROUPS = {
    "hourly rain intensity": [f for f in F5 if f not in F4],
    "soil moisture (ERA5-Land, day before)": ["soil07_prev", "soil728_prev"],
    "MJO (OMI index)": ["mjo_x", "mjo_y", "mjo_amp"],
    "ENSO (ONI)": ["oni"],
    "northerly surge (wind from the north, Java Sea)": ["north_wind", "north_wind_d1"],
    "spring tide (moon phase) on the coast": ["spring_tide", "coastal", "coastal_spring_tide"],
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", message=".*mismatched devices.*")
    device = "cpu" if args.cpu else "cuda"

    train, val, test = split(kecamatan_days())
    y_val, y_te = val["flood"].to_numpy(), test["flood"].to_numpy()
    boot = DateBootstrap(test["date"].to_numpy(), args.bootstrap)
    base_val, base_te = fit_predict("xgboost", train, [val, test], F4, device=device)
    res = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "base": {"features": "F4", "validation_pr_auc": round(float(average_precision_score(y_val, base_val)), 3),
                    "test_roc_auc": round(float(roc_auc_score(y_te, base_te)), 3),
                    "test_pr_auc": round(float(average_precision_score(y_te, base_te)), 3)},
           "groups": {}}
    for name, extra in GROUPS.items():
        p_val, p_te = fit_predict("xgboost", train, [val, test], F4 + extra, device=device)
        res["groups"][name] = {
            "features": extra,
            "validation_pr_auc": round(float(average_precision_score(y_val, p_val)), 3),
            "test_roc_auc": round(float(roc_auc_score(y_te, p_te)), 3),
            "test_pr_auc": round(float(average_precision_score(y_te, p_te)), 3),
            "minus_F4": boot.diff(y_te, base_te, p_te),
        }
        print(name, res["groups"][name], flush=True)

    # Day ahead: only what is known the evening before (no rain of the day itself). The drivers
    # that cause rain (MJO, northerly surge) should matter here if anywhere.
    ahead = ["d1", "d3prev", "d7prev", "api14", "up_bogor_d1", "hist_rate", "month_sin", "month_cos",
             "elevation", "slope"]
    ahead_drivers = ["soil07_prev", "soil728_prev", "mjo_x", "mjo_y", "mjo_amp", "oni", "north_wind_d1",
                     "spring_tide", "coastal", "coastal_spring_tide"]
    a_val, a_te = fit_predict("xgboost", train, [val, test], ahead, device=device)
    d_val, d_te = fit_predict("xgboost", train, [val, test], ahead + ahead_drivers, device=device)
    res["day_ahead"] = {
        "features": ahead, "drivers": ahead_drivers,
        "without_drivers": {"validation_pr_auc": round(float(average_precision_score(y_val, a_val)), 3),
                            "test_roc_auc": round(float(roc_auc_score(y_te, a_te)), 3),
                            "test_pr_auc": round(float(average_precision_score(y_te, a_te)), 3)},
        "with_drivers": {"validation_pr_auc": round(float(average_precision_score(y_val, d_val)), 3),
                         "test_roc_auc": round(float(roc_auc_score(y_te, d_te)), 3),
                         "test_pr_auc": round(float(average_precision_score(y_te, d_te)), 3)},
        "with_minus_without": boot.diff(y_te, a_te, d_te),
    }
    print("day ahead", res["day_ahead"], flush=True)

    lines = ["# Driver ablation", "", f"Generated {res['generated_at']} by `scripts/driver_ablation.py`. "
             "Each group is added on its own to F4; XGBoost (default settings) trained 2020–2021, validated 2022, "
             "tested 2023 to Sep 2025.", "",
             f"F4 alone: PR-AUC on 2022 {res['base']['validation_pr_auc']}, test ROC-AUC {res['base']['test_roc_auc']}, "
             f"test PR-AUC {res['base']['test_pr_auc']}.", "",
             "| Added to F4 | PR-AUC on 2022 | Test ROC-AUC | Test PR-AUC | ROC-AUC vs F4 (95 %) | PR-AUC vs F4 (95 %) |",
             "|---|---|---|---|---|---|"]
    for name, g in res["groups"].items():
        lines.append(f"| {name} | {g['validation_pr_auc']} | {g['test_roc_auc']} | {g['test_pr_auc']} | "
                     f"{g['minus_F4']['roc_auc']} | {g['minus_F4']['pr_auc']} |")
    a = res["day_ahead"]
    lines += ["", "- An interval that excludes 0 on the test years and a higher PR-AUC on 2022 = a robust gain.", "",
              "## Day ahead (no rain of the day itself)", "",
              f"Features: {', '.join(a['features'])}; drivers: {', '.join(a['drivers'])}.", "",
              "| Model | PR-AUC on 2022 | Test ROC-AUC | Test PR-AUC |", "|---|---|---|---|",
              f"| without drivers | {a['without_drivers']['validation_pr_auc']} | {a['without_drivers']['test_roc_auc']} | "
              f"{a['without_drivers']['test_pr_auc']} |",
              f"| with drivers | {a['with_drivers']['validation_pr_auc']} | {a['with_drivers']['test_roc_auc']} | "
              f"{a['with_drivers']['test_pr_auc']} |", "",
              f"With minus without (95 %): ROC-AUC {a['with_minus_without']['roc_auc']}, "
              f"PR-AUC {a['with_minus_without']['pr_auc']}."]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "driver_ablation.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (REPORTS_DIR / "driver_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
