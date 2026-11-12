#!/usr/bin/env python
"""
City-wide or per-post water levels in the daily kecamatan model? (exploratory; nothing served)

Same rows as Part A of scripts/water_level_experiments.py: kecamatan-days with DSDA water levels, test
years 2019, 2020 and 2021, each model trained on the earlier water-level days (Oct 2016 onward).
  V0  F4 (rain, antecedent rain, upstream rain, place and season)
  V1  V0 + city water features (highest river status, posts at Siaga, upstream, Manggarai, coast; + day before)
  V2  V1 + the status of each main post (today and the day before) + the kecamatan's latitude and longitude,
      so the model can learn which post matters where (Manggarai for Jatinegara, Angke for Kebon Jeruk, ...)
  V3  V0 + per-post statuses + location, without the city summaries
  A0  day ahead: no rain or water of the day itself (yesterday's rain, history, place, season)
  A1  A0 + yesterday's water levels (city and per post) + location
Pooled 2019-2021 scores with 95 % intervals and paired differences (bootstrap over dates).

Outputs artifacts/reports/local_water_experiment.{json,md}.
Usage (repo root):  python scripts/local_water_experiment.py [--bootstrap 1000] [--cpu]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
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
from scripts.long_experiments import AHEAD, long_dataset  # noqa: E402
from scripts.thesis_experiments import F4, DateBootstrap, fit_predict  # noqa: E402
from scripts.water_level_experiments import WL, WL_ALL, city_features, daily_posts  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

# Posts with readings in most of 2016-2021 and 2025 (river posts first, then two coastal ones).
MAIN_POSTS = ["KATULAMPA", "DEPOK", "MANGGARAI", "KARET", "KRUKUTHULU", "PESANGGRAHAN", "ANGKEHULU",
              "SUNTERHULU", "CIPINANGHULU", "PULOGADUNG", "MARINAANCOL", "PASARIKAN"]
TEST_YEARS = (2019, 2020, 2021)


def per_post(posts: pd.DataFrame) -> pd.DataFrame:
    wide = posts[posts["post"].isin(MAIN_POSTS)].pivot_table(index="date", columns="post", values="status", aggfunc="max")
    wide = wide.reindex(columns=MAIN_POSTS)
    wide.columns = [f"st_{c.lower()}" for c in wide.columns]
    full = wide.reindex(pd.date_range(wide.index.min(), wide.index.max(), freq="D"))
    prev = full.shift(1).reindex(wide.index)
    prev.columns = [f"{c}_prev" for c in wide.columns]
    return wide.join(prev)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", message=".*mismatched devices.*")
    device = "cpu" if args.cpu else "cuda"
    started = time.time()

    posts = daily_posts()
    city = city_features(posts)
    pp = per_post(posts)
    data = long_dataset().join(city[WL_ALL], on="date").join(pp, on="date")
    cleaned = pd.read_csv(PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv")
    loc = cleaned.groupby(cleaned["name_3"].map(_slug))[["lat", "long"]].first()
    data = data.join(loc, on="kecamatan")
    post_now = [c for c in pp.columns if not c.endswith("_prev")]
    post_prev = [c for c in pp.columns if c.endswith("_prev")]
    variants = {
        "V0 F4": F4,
        "V1 + city water": F4 + WL_ALL,
        "V2 + city water + per post + location": F4 + WL_ALL + post_now + post_prev + ["lat", "long"],
        "V3 + per post + location": F4 + post_now + post_prev + ["lat", "long"],
        "A0 day ahead": AHEAD,
        "A1 day ahead + yesterday's water + location": AHEAD + [f"{c}_prev" for c in WL] + post_prev + ["lat", "long"],
    }
    pairs = [("V0 F4", "V1 + city water"), ("V1 + city water", "V2 + city water + per post + location"),
             ("V1 + city water", "V3 + per post + location"), ("A0 day ahead", "A1 day ahead + yesterday's water + location")]

    rows = data[data["river_max"].notna()]
    preds = {k: [] for k in variants}
    ys, dates, per_year = [], [], {}
    for year in TEST_YEARS:
        train, test = rows[rows["year"] < year], rows[rows["year"] == year]
        y = test["flood"].to_numpy()
        per_year[year] = {"train_rows": int(len(train)), "test_rows": int(len(test)), "floods": int(y.sum())}
        for name, feats in variants.items():
            p, = fit_predict("xgboost", train, [test], feats, device=device)
            preds[name].append(p)
            per_year[year][name] = round(float(roc_auc_score(y, p)), 3)
        ys.append(y), dates.append(test["date"].to_numpy())
        print(year, per_year[year], flush=True)
    y, d = np.concatenate(ys), np.concatenate(dates)
    p = {k: np.concatenate(v) for k, v in preds.items()}
    boot = DateBootstrap(d, args.bootstrap)
    res = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
           "posts": MAIN_POSTS, "per_year_roc_auc": per_year,
           "pooled": {k: {"roc_auc": boot.ci(roc_auc_score, y, v), "pr_auc": boot.ci(average_precision_score, y, v)}
                      for k, v in p.items()},
           "paired": {f"{b} minus {a}": boot.diff(y, p[a], p[b]) for a, b in pairs},
           "rows": int(len(y)), "floods": int(y.sum()), "prevalence": round(float(y.mean()), 4)}
    res["seconds"] = round(time.time() - started, 1)

    L = ["# City-wide or per-post water levels in the daily model", "",
         f"Generated {res['generated_at']} by `scripts/local_water_experiment.py` on {device}. Nothing here is served.", "",
         f"Kecamatan-days with water levels, test years 2019–2021 pooled: {res['rows']} rows, {res['floods']} floods "
         f"(prevalence {res['prevalence']}). Per-post features: " + ", ".join(MAIN_POSTS) + ".", "",
         "| Variant | ROC-AUC [95 %] | PR-AUC [95 %] |", "|---|---|---|"]
    for k, s in res["pooled"].items():
        L.append(f"| {k} | {s['roc_auc'][0]} [{s['roc_auc'][1]}–{s['roc_auc'][2]}] | "
                 f"{s['pr_auc'][0]} [{s['pr_auc'][1]}–{s['pr_auc'][2]}] |")
    L += ["", "| Paired difference (95 %) | ROC-AUC | PR-AUC |", "|---|---|---|"]
    for k, dd in res["paired"].items():
        L.append(f"| {k} | {dd['roc_auc']} | {dd['pr_auc']} |")
    L += ["", "ROC-AUC by test year:", "", "| Year | Floods | " + " | ".join(variants) + " |", "|---|---|" + "---|" * len(variants)]
    for yr, s in per_year.items():
        L.append(f"| {yr} | {s['floods']} | " + " | ".join(str(s[k]) for k in variants) + " |")
    L += ["", f"Run time {res['seconds']} s."]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "local_water_experiment.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (REPORTS_DIR / "local_water_experiment.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
