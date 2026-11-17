#!/usr/bin/env python
"""
Can the live daily model warn of LARGE flood days well enough to raise Siaga? (exploratory; nothing served)

The served daily model (scripts/train_daily_live_model.py) may raise Jakarta to Waspada only: as a city
score, the highest kecamatan probability finds "a flood anywhere" with precision ~0.31-0.36 at any
threshold. Most of those days are one or two flooded RT. This script asks the question Siaga needs:
does the model find the days on which BPBD records floods in many kecamatan at once?

Rows: WIB days 2016-2025 (rain from IMERG Early as served, lag 1 and lag 2: rain through D-1 / D-2,
plus the D-1/D-2 river-post status). Labels per day: number of the 42 kecamatan with a BPBD flood;
large = 5 or more (as scripts/water_level_experiments.py), very large = 10 or more.

City scores, each out of sample (for test year Y trained on 2013..Y-1 only):
  max    highest kecamatan probability (what the site serves now)
  sum    sum of the kecamatan probabilities (expected number of flooded kecamatan)
  city   XGBoost trained directly on city days with the large label, on city rain (mean and max over the
         model's kecamatan), upstream rain, season and water status
Scored by year block (2016-2022 complete labels; 2023-2025 partly readable labels, precision a lower
bound): ROC-AUC and PR-AUC with 95 % intervals that resample days, paired differences, and recall and
precision when the score raises an alarm on 8 / 4 / 2 / 1 days a month (threshold = that quantile of
the block's own scores, so slightly optimistic).

Outputs artifacts/reports/large_flood_experiment.{json,md}.
Usage (repo root): python scripts/large_flood_experiment.py [--bootstrap 1000] [--cpu]
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
from xgboost import XGBClassifier

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from realtime_native import daily_features as dfe  # noqa: E402
from scripts import train_daily_live_model as tdl  # noqa: E402
from scripts.thesis_experiments import DateBootstrap  # noqa: E402
from utils.paths import REPORTS_DIR  # noqa: E402

LAGS = (1, 2)
TEST_YEARS = range(2016, 2026)
BLOCKS = {"2016-2022 (complete labels)": range(2016, 2023), "2023-2025 (partial labels)": range(2023, 2026)}
LABELS = {"any flood": 1, "large (>= 5 kecamatan)": 5, "very large (>= 10 kecamatan)": 10}
BUDGETS = (8, 4, 2, 1)
SCORES = ("max", "sum", "city")
CITY_RAIN = ["rain_lag", "rain_3", "rain_7", "api"]
CITY_SHARED = ["up_bogor_lag", "up_bogor_3", "up_depok_lag", "month_sin", "month_cos"] + dfe.WATER
SEED = 42


def city_table(data: pd.DataFrame, p_kec: np.ndarray) -> pd.DataFrame:
    frame = data.assign(p=p_kec)
    g = frame.groupby("date")
    city = pd.DataFrame({"n_flooded": g["flood"].sum(), "max": g["p"].max(), "sum": g["p"].sum()})
    for col in CITY_RAIN:
        city[f"{col}_mean"] = g[col].mean()
        city[f"{col}_max"] = g[col].max()
    city[CITY_SHARED] = g[CITY_SHARED].first()
    city["year"] = city.index.year
    return city


def city_features() -> list[str]:
    return [f"{c}_{a}" for c in CITY_RAIN for a in ("mean", "max")] + CITY_SHARED


def rolling_city(city: pd.DataFrame, device: str) -> np.ndarray:
    feats, p = city_features(), np.full(len(city), np.nan)
    y = (city["n_flooded"] >= LABELS["large (>= 5 kecamatan)"]).astype(int)
    for year in TEST_YEARS:
        train = (city["year"] < year) & city["rain_lag_mean"].notna()
        test = (city["year"] == year).to_numpy()
        model = XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                              min_child_weight=3, eval_metric="logloss", tree_method="hist", device=device,
                              random_state=SEED)
        model.fit(city.loc[train, feats], y[train])
        p[test] = model.predict_proba(city.loc[test, feats])[:, 1]
    return p


def at_budget(y_label: np.ndarray, y_any: np.ndarray, score: np.ndarray, per_month: int) -> dict:
    thr = float(np.quantile(score, 1 - per_month / tdl.DAYS_PER_MONTH))
    warn = score >= thr
    tp = int((warn & (y_label == 1)).sum())
    return {"alarm_days": int(warn.sum()), "recall": round(tp / max(int(y_label.sum()), 1), 3),
            "precision": round(tp / max(int(warn.sum()), 1), 3),
            "precision_any_flood": round(int((warn & (y_any == 1)).sum()) / max(int(warn.sum()), 1), 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", category=UserWarning)
    device = "cpu" if args.cpu else "cuda"

    points = tdl.build_points()
    kecamatan = sorted(k for k in points if k in tdl._CANONICAL_BY_SLUG)
    floods = tdl.flood_kecamatan_days()
    floods = floods[(floods["date"] >= tdl.START) & (floods["date"] <= tdl.END)]
    static = tdl.static_table(floods, kecamatan, points)
    rain = tdl.daily_rain_by_cell(sorted(set(points.values())))
    posts = tdl.daily_posts()
    posts = posts.assign(post=posts["post"].map(dfe.post_key))
    city_water = dfe.city_water_by_day(posts)

    report = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
              "bootstrap": args.bootstrap, "lags": {}}
    for lag in LAGS:
        data = tdl.build(lag, rain, points, kecamatan, floods, static, city_water)
        data = data[data["year"] >= 2013].reset_index(drop=True)
        p_kec = tdl.rolling(data, dfe.FEATURES, device)
        ok = data["year"].isin(TEST_YEARS).to_numpy() & ~np.isnan(p_kec) & data["rain_lag"].notna().to_numpy()
        city = city_table(data[ok], p_kec[ok])
        city["city"] = rolling_city(city, device)
        city = city.dropna(subset=["city"])
        lag_out = {}
        for block, years in BLOCKS.items():
            c = city[city["year"].isin(years)]
            boot = DateBootstrap(c.index.to_numpy(), args.bootstrap)
            y_any = (c["n_flooded"] >= 1).astype(int).to_numpy()
            entry = {"days": int(len(c))}
            for label, k in LABELS.items():
                y = (c["n_flooded"] >= k).astype(int).to_numpy()
                e = {"flood_days": int(y.sum()), "share": round(float(y.mean()), 3)}
                for s in SCORES:
                    e[s] = {"roc_auc": boot.ci(roc_auc_score, y, c[s].to_numpy()),
                            "pr_auc": boot.ci(average_precision_score, y, c[s].to_numpy()),
                            "budgets": {f"{n} a month": at_budget(y, y_any, c[s].to_numpy(), n) for n in BUDGETS}}
                e["diffs"] = {f"{b} - {a}": boot.diff(y, c[a].to_numpy(), c[b].to_numpy())
                              for a, b in (("max", "sum"), ("max", "city"), ("sum", "city"))}
                entry[label] = e
            lag_out[block] = entry
            print(f"lag {lag} {block}: " + "; ".join(
                f"{label} " + ", ".join(f"{s} {entry[label][s]['roc_auc'][0]}" for s in SCORES) for label in LABELS),
                flush=True)
        report["lags"][f"lag {lag}"] = lag_out

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "large_flood_experiment.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORTS_DIR / "large_flood_experiment.md").write_text(markdown(report), encoding="utf-8")
    return 0


def _ci(v):
    return f"{v[0]} [{v[1]}–{v[2]}]"


def markdown(r: dict) -> str:
    L = ["# Large flood days: can the live daily model justify Siaga?", "",
         f"Generated {r['generated_utc']} by `scripts/large_flood_experiment.py` on {r['device']} "
         f"({r['bootstrap']} day resamples). Nothing here is served.", "",
         "City scores, out of sample: **max** = highest kecamatan probability (served now), **sum** = expected "
         "number of flooded kecamatan, **city** = XGBoost on city days trained on the large label. Alarm "
         "thresholds are the block's own quantiles (slightly optimistic).", ""]
    for lag, blocks in r["lags"].items():
        for block, e in blocks.items():
            L += [f"## {lag} (rain through D-{lag[-1]}) · {block} · {e['days']} days", "",
                  "| Label | Days (share) | Score | ROC-AUC [95 %] | PR-AUC [95 %] |", "|---|---|---|---|---|"]
            for label in LABELS:
                x = e[label]
                for s in SCORES:
                    L.append(f"| {label} | {x['flood_days']} ({x['share']}) | {s} | {_ci(x[s]['roc_auc'])} | {_ci(x[s]['pr_auc'])} |")
            L += ["", "Paired differences (95 %):", ""]
            for label in LABELS:
                L.append(f"- {label}: " + "; ".join(f"{k} ROC-AUC {v['roc_auc']}, PR-AUC {v['pr_auc']}"
                                                    for k, v in e[label]["diffs"].items()))
            L += ["", "| Label | Score | Alarms a month | Alarm days | Recall | Precision | Precision for any flood |",
                  "|---|---|---|---|---|---|---|"]
            for label in LABELS:
                if label == "any flood":
                    continue
                for s in SCORES:
                    for n, b in e[label][s]["budgets"].items():
                        L.append(f"| {label} | {s} | {n} | {b['alarm_days']} | {b['recall']} | {b['precision']} | "
                                 f"{b['precision_any_flood']} |")
            L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
