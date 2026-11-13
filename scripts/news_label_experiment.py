#!/usr/bin/env python
"""
Do news-derived flood days change the 2023-2025 results? (exploratory; nothing served)

BPBD flood dates are complete to 2022 but only partly readable for 2023-2025, while BPBD's months
are complete. scripts/fetch_news_flood_days.py reads flood reports quoting BPBD (detik.com) and maps
them to kecamatan-days. Labels compared on the test years 2023 to Sep 2025:
  bpbd      the dated BPBD kecamatan-days (as in scripts/long_experiments.py)
  bpbd+news bpbd plus news kecamatan-days whose kecamatan-month BPBD also recorded as flooded
            (news days outside a BPBD flood month are dropped as likely mis-tags)
Checks of the news source: on 2020-2022 (complete BPBD dates, if
data/processed/news_flood_reports_2020_2022.csv exists) the share of filtered news days that BPBD
dated within one day; on 2023-2025 the share of news days inside a BPBD flood month.
Models: XGBoost F4 trained on every earlier year (rolling, as in long_experiments.py), once with the
BPBD labels and once with bpbd+news labels for the 2023-2024 training rows. Scored on both label sets.

Outputs artifacts/reports/news_label_experiment.{json,md}.
Usage (repo root):  python scripts/news_label_experiment.py [--bootstrap 1000] [--cpu]
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
from sklearn.metrics import average_precision_score, roc_auc_score

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.build_kelurahan_flood_history import _slug  # noqa: E402
from scripts.long_experiments import long_dataset  # noqa: E402
from scripts.thesis_experiments import F4, DateBootstrap, fit_predict  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

NEWS = {"2023-2025": PROCESSED_DATA_DIR / "news_flood_reports_2023_2025.csv",
        "2020-2022": PROCESSED_DATA_DIR / "news_flood_reports_2020_2022.csv"}
REKAP = _PROJECT_ROOT / "data" / "raw" / "rekap_kejadian_2020_2025.csv"
TEST_YEARS = (2023, 2024, 2025)
DAYS_PER_MONTH = 30.44


def bpbd_months() -> set[tuple[str, int, int]]:
    rekap = pd.read_csv(REKAP).drop_duplicates()
    return {(_slug(str(k)), int(y), int(m)) for k, y, m in zip(rekap["kecamatan"], rekap["tahun"], rekap["bulan"])}


def news_days(path: Path, months: set) -> pd.DataFrame:
    news = pd.read_csv(path, parse_dates=["date"])[["kecamatan", "date"]].drop_duplicates()
    news["in_bpbd_month"] = [(k, d.year, d.month) in months for k, d in zip(news["kecamatan"], news["date"])]
    return news


def near(pairs, reference: set, days=(-1, 0, 1)) -> int:
    return sum(any((k, d + pd.Timedelta(days=x)) in reference for x in days) for k, d in pairs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", message=".*mismatched devices.*")
    device = "cpu" if args.cpu else "cuda"

    months = bpbd_months()
    data = long_dataset()
    bpbd_set = set(zip(data.loc[data["flood"] == 1, "kecamatan"], data.loc[data["flood"] == 1, "date"]))
    res: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device, "checks": {}}

    if NEWS["2020-2022"].exists():
        old = news_days(NEWS["2020-2022"], months)
        f = old[old["in_bpbd_month"]]
        res["checks"]["2020-2022 (complete BPBD dates)"] = {
            "news_kecamatan_days": int(len(old)), "inside_a_bpbd_flood_month": int(old["in_bpbd_month"].sum()),
            "filtered_confirmed_within_1_day": int(near(zip(f["kecamatan"], f["date"]), bpbd_set)),
            "filtered": int(len(f)),
            "all_confirmed_within_1_day": int(near(zip(old["kecamatan"], old["date"]), bpbd_set))}
    new = news_days(NEWS["2023-2025"], months)
    res["checks"]["2023-2025"] = {"news_kecamatan_days": int(len(new)), "inside_a_bpbd_flood_month": int(new["in_bpbd_month"].sum()),
                                  "near_a_dated_bpbd_day": int(near(zip(new["kecamatan"], new["date"]), bpbd_set))}
    print(res["checks"], flush=True)

    add = new[new["in_bpbd_month"]]
    added = set(zip(add["kecamatan"], add["date"])) - bpbd_set
    data["flood_news"] = [int(f == 1 or (k, d) in added) for f, k, d in zip(data["flood"], data["kecamatan"], data["date"])]
    res["labels"] = {str(y): {"bpbd": int(g["flood"].sum()), "bpbd+news": int(g["flood_news"].sum())}
                     for y, g in data[data["year"] >= 2023].groupby("year")}

    preds = {"trained on bpbd": [], "trained on bpbd+news": []}
    tests = []
    for year in TEST_YEARS:
        train, test = data[data["year"] < year], data[data["year"] == year]
        p_b, = fit_predict("xgboost", train, [test], F4, device=device)
        train_n = train.assign(flood=train["flood_news"])
        p_n, = fit_predict("xgboost", train_n, [test], F4, device=device)
        preds["trained on bpbd"].append(p_b)
        preds["trained on bpbd+news"].append(p_n)
        tests.append(test[["date", "flood", "flood_news", "kecamatan"]])
        print("year", year, flush=True)
    test = pd.concat(tests, ignore_index=True)
    boot = DateBootstrap(test["date"].to_numpy(), args.bootstrap)
    n_km = test["kecamatan"].nunique() * test["date"].dt.to_period("M").nunique()
    res["scores"] = {}
    for model, parts in preds.items():
        p = np.concatenate(parts)
        for lab in ("flood", "flood_news"):
            y = test[lab].to_numpy()
            t = float(np.quantile(p, 1 - 1 / DAYS_PER_MONTH))  # Bahaya budget: one alarm a kecamatan-month
            pred = p >= t
            res["scores"][f"{model} | scored on {'bpbd' if lab == 'flood' else 'bpbd+news'}"] = {
                "floods": int(y.sum()), "prevalence": round(float(y.mean()), 4),
                "roc_auc": boot.ci(roc_auc_score, y, p), "pr_auc": boot.ci(average_precision_score, y, p),
                "at_1_alarm_per_kecamatan_month": {
                    "recall": round(float((pred & (y == 1)).sum() / max(y.sum(), 1)), 3),
                    "precision": round(float((pred & (y == 1)).sum() / max(pred.sum(), 1)), 3),
                    "alarms_per_kecamatan_month": round(float(pred.sum() / n_km), 2)}}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "news_label_experiment.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    L = ["# News-derived flood days for 2023–2025", "",
         f"Generated {res['generated_at']} by `scripts/news_label_experiment.py` on {device}. Nothing here is served.", "",
         "## Checks of the news source", ""]
    for k, c in res["checks"].items():
        L.append(f"- {k}: " + ", ".join(f"{a.replace('_', ' ')} {b}" for a, b in c.items()) + ".")
    L += ["", "## Flood kecamatan-days per test year", "", "| Year | BPBD dated | BPBD + news |", "|---|---|---|"]
    for y, s in res["labels"].items():
        L.append(f"| {y} | {s['bpbd']} | {s['bpbd+news']} |")
    L += ["", "## Test years 2023 to Sep 2025 (rolling models)", "",
          "| Model · labels scored | Floods | ROC-AUC [95 %] | PR-AUC [95 %] | Recall / precision at 1 alarm per kecamatan-month |",
          "|---|---|---|---|---|"]
    for k, s in res["scores"].items():
        a = s["at_1_alarm_per_kecamatan_month"]
        L.append(f"| {k} | {s['floods']} | {s['roc_auc'][0]} [{s['roc_auc'][1]}–{s['roc_auc'][2]}] | "
                 f"{s['pr_auc'][0]} [{s['pr_auc'][1]}–{s['pr_auc'][2]}] | {a['recall']} / {a['precision']} |")
    L += ["", "- News days are kept only inside a kecamatan-month that BPBD recorded as flooded.",
          "- The 1-alarm threshold is the model's own top 3.3 % of kecamatan-days in the test years."]
    (REPORTS_DIR / "news_label_experiment.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
