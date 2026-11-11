#!/usr/bin/env python
"""
The daily flood model on 13 years (2013 to Sep 2025), tested year by year (exploratory; nothing served).

Rows: one kecamatan (the 42 model kecamatan) on one WIB day, 2013-01-01 to 2025-09-30, with GPM IMERG
rain (scripts/fetch_imerg_history.py --history adds Dec 2012 to Nov 2019). Labels: BPBD flood dates,
2013-2019 from data/processed/events_clean.csv and 2020 onward from the RW rekap (both read by
scripts/hourly_rain_experiment.flood_kecamatan_days). Dates are complete to 2022 and only partly
readable for 2023-2025, so precision there is a lower bound.

Rolling origin: for each test year Y from 2016 to 2025, models are trained on every year before Y
(2013..Y-1) and scored on Y alone, so no test day ever informs its own model. The kecamatan flood
history feature uses years before the row's year only (none for 2013).

Models (fixed settings, no tuning on the test years):
  rain that day (baseline), logistic F4, XGBoost F4, XGBoost F5 (+ hourly intensity),
  XGBoost F6 (+ soil moisture, MJO, ENSO, northerly wind, spring tide),
  day ahead without / with drivers (no rain of the day itself).
Pooled scores over 2016-2022 (complete labels) and 2023-2025 (partial), with 95 % intervals from a
bootstrap over test dates, and paired differences.

Outputs artifacts/reports/long_experiments.{json,md}.
Usage (repo root):  python scripts/long_experiments.py [--bootstrap 1000] [--cpu]
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
from scripts.build_kelurahan_flood_history import _CANONICAL_BY_SLUG, _slug  # noqa: E402
from scripts.fetch_imerg_history import build_points  # noqa: E402
from scripts.hourly_rain_experiment import _imerg_series, daily_rain_features, flood_kecamatan_days  # noqa: E402
from scripts.thesis_experiments import F4, F5, F6, DateBootstrap, add_drivers, fit_predict  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

START, END = "2013-01-01", "2025-09-30"
FIRST_TEST, LAST_TEST = 2016, 2025
COMPLETE_LABELS = range(2016, 2023)  # BPBD dates fully readable
AHEAD = ["d1", "d3prev", "d7prev", "api14", "up_bogor_d1", "hist_rate", "month_sin", "month_cos", "elevation", "slope"]
AHEAD_DRIVERS = ["soil07_prev", "soil728_prev", "mjo_x", "mjo_y", "mjo_amp", "oni", "north_wind_d1",
                 "spring_tide", "coastal", "coastal_spring_tide"]
MODELS = {  # name: (kind, features)
    "baseline: rain that day": (None, ["d0"]),
    "logistic F4": ("logistic", F4),
    "XGBoost F4": ("xgboost", F4),
    "XGBoost F5 (+ hourly intensity)": ("xgboost", F5),
    "XGBoost F6 (+ drivers)": ("xgboost", F6),
    "day ahead, no drivers": ("xgboost", AHEAD),
    "day ahead, + drivers": ("xgboost", AHEAD + AHEAD_DRIVERS),
}
PAIRS = [("baseline: rain that day", "XGBoost F4"), ("logistic F4", "XGBoost F4"),
         ("XGBoost F4", "XGBoost F5 (+ hourly intensity)"), ("XGBoost F5 (+ hourly intensity)", "XGBoost F6 (+ drivers)"),
         ("day ahead, no drivers", "day ahead, + drivers")]


def history_rate(floods: pd.DataFrame, kecamatan: list[str], years: range) -> pd.DataFrame:
    """Share of days with a flood in each kecamatan over 2013..year-1; none for 2013 (leak-free)."""
    per_year = floods.assign(year=floods["date"].dt.year).groupby(["kecamatan", "year"]).size()
    rows = []
    for year in years:
        n_days = (pd.Timestamp(year=year, month=1, day=1) - pd.Timestamp(START)).days
        for kec in kecamatan:
            past = per_year.loc[kec] if kec in per_year.index.get_level_values(0) else pd.Series(dtype=float)
            rows.append((kec, year, float(past[(past.index < year) & (past.index >= 2013)].sum()) / n_days
                         if n_days else np.nan))
    return pd.DataFrame(rows, columns=["kecamatan", "year", "hist_rate"])


def long_dataset() -> pd.DataFrame:
    points = build_points()
    by_cell = {}
    for cell in sorted(set(points.values())):
        hourly = _imerg_series(cell)
        assert hourly.index.is_unique, f"overlapping IMERG files for {cell}"
        by_cell[cell] = daily_rain_features(hourly)
    up_b, up_d = by_cell[points["upstream_bogor"]], by_cell[points["upstream_depok"]]
    upstream = pd.DataFrame({"up_bogor_d0": up_b["d0"], "up_bogor_d1": up_b["d1"], "up_bogor_max3h": up_b["max3h"],
                             "up_depok_d0": up_d["d0"], "up_depok_max3h": up_d["max3h"]})
    kecamatan = sorted(k for k in points if k in _CANONICAL_BY_SLUG)
    frames = []
    for kec in kecamatan:
        f = by_cell[points[kec]].join(upstream).loc[START:END].copy()
        f["kecamatan"] = kec
        frames.append(f)
    data = pd.concat(frames).rename_axis("date").reset_index()
    floods = flood_kecamatan_days()
    flagged = set(zip(floods["kecamatan"], floods["date"]))
    data["flood"] = [int((k, d) in flagged) for k, d in zip(data["kecamatan"], data["date"])]
    data["year"] = data["date"].dt.year
    data = data.merge(history_rate(floods, kecamatan, range(2013, 2026)), on=["kecamatan", "year"], how="left")
    data["month_sin"] = np.sin(2 * np.pi * data["date"].dt.month / 12)
    data["month_cos"] = np.cos(2 * np.pi * data["date"].dt.month / 12)
    data = data.sort_values(["kecamatan", "date"]).reset_index(drop=True)
    by_kec = data.groupby("kecamatan")["d0"]
    data["d7prev"] = by_kec.transform(lambda s: s.shift(1).rolling(7, min_periods=1).sum())
    data["api14"] = by_kec.transform(lambda s: s.shift(1).fillna(0.0).ewm(alpha=0.15, adjust=False).mean() / 0.15)
    cleaned = pd.read_csv(PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv")
    data = data.join(cleaned.groupby(cleaned["name_3"].map(_slug))[["elevation", "slope"]].mean(), on="kecamatan")
    return add_drivers(data)


def score_block(name, y, p, dates, n_boot):
    boot = DateBootstrap(dates, n_boot)
    return {"rows": int(len(y)), "floods": int(y.sum()), "prevalence": round(float(y.mean()), 4),
            "roc_auc": boot.ci(roc_auc_score, y, p), "pr_auc": boot.ci(average_precision_score, y, p)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", message=".*mismatched devices.*")
    device = "cpu" if args.cpu else "cuda"
    started = time.time()

    data = long_dataset()
    res: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
                 "rows": int(len(data)), "floods_by_year": {int(y): int(g["flood"].sum()) for y, g in data.groupby("year")},
                 "missing": {c: round(float(data[c].isna().mean()), 4) for c in sorted(set(F6 + AHEAD + AHEAD_DRIVERS))
                             if data[c].isna().any()}}
    print("rows", res["rows"], "floods by year", res["floods_by_year"], flush=True)

    preds = {name: [] for name in MODELS}
    tests = []
    per_year = {}
    for year in range(FIRST_TEST, LAST_TEST + 1):
        train, test = data[data["year"] < year], data[data["year"] == year]
        y_te = test["flood"].to_numpy()
        tests.append(test[["date", "flood", "year"]])
        per_year[year] = {"floods": int(y_te.sum()), "prevalence": round(float(y_te.mean()), 4), "models": {}}
        for name, (kind, feats) in MODELS.items():
            p = test["d0"].to_numpy() if kind is None else fit_predict(kind, train, [test], feats, device=device)[0]
            preds[name].append(p)
            per_year[year]["models"][name] = {"roc_auc": round(float(roc_auc_score(y_te, p)), 3),
                                              "pr_auc": round(float(average_precision_score(y_te, p)), 3)}
        print(year, {k: v["roc_auc"] for k, v in per_year[year]["models"].items()}, flush=True)
    res["per_year"] = per_year

    test_all = pd.concat(tests).reset_index(drop=True)
    p_all = {name: np.concatenate(v) for name, v in preds.items()}
    res["pooled"] = {}
    for block, years in (("2016–2022 (complete labels)", COMPLETE_LABELS), ("2023–Sep 2025 (partial labels)", range(2023, 2026))):
        mask = test_all["year"].isin(list(years)).to_numpy()
        y, dates = test_all["flood"].to_numpy()[mask], test_all["date"].to_numpy()[mask]
        boot = DateBootstrap(dates, args.bootstrap)
        res["pooled"][block] = {
            "models": {name: {"roc_auc": boot.ci(roc_auc_score, y, p[mask]), "pr_auc": boot.ci(average_precision_score, y, p[mask])}
                       for name, p in p_all.items()},
            "paired": {f"{b} minus {a}": boot.diff(y, p_all[a][mask], p_all[b][mask]) for a, b in PAIRS},
            "rows": int(mask.sum()), "floods": int(y.sum()), "prevalence": round(float(y.mean()), 4),
        }
    res["seconds"] = round(time.time() - started, 1)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "long_experiments.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (REPORTS_DIR / "long_experiments.md").write_text(markdown(res), encoding="utf-8")
    print(markdown(res))
    return 0


def _ci(v):
    return f"{v[0]} [{v[1]}–{v[2]}]"


def markdown(r: dict) -> str:
    L = ["# Daily flood model, 2013 to Sep 2025, tested year by year", "",
         f"Generated {r['generated_at']} by `scripts/long_experiments.py` on {r['device']}. Nothing here is served.", "",
         f"{r['rows']} kecamatan-days. Each test year is scored by models trained on every earlier year only. "
         "BPBD flood dates are complete to 2022 and partly readable for 2023–2025.", "",
         "Flood kecamatan-days by year: " + ", ".join(f"{y}: {n}" for y, n in r["floods_by_year"].items()) + ".", ""]
    for block, b in r["pooled"].items():
        L += [f"## Pooled test years {block}", "",
              f"{b['rows']} rows, {b['floods']} flood rows (prevalence {b['prevalence']}, the no-skill PR-AUC).", "",
              "| Model | ROC-AUC [95 %] | PR-AUC [95 %] |", "|---|---|---|"]
        for name, s in b["models"].items():
            L.append(f"| {name} | {_ci(s['roc_auc'])} | {_ci(s['pr_auc'])} |")
        L += ["", "| Paired difference (95 %) | ROC-AUC | PR-AUC |", "|---|---|---|"]
        for name, d in b["paired"].items():
            L.append(f"| {name} | {d['roc_auc']} | {d['pr_auc']} |")
        L.append("")
    names = list(next(iter(r["per_year"].values()))["models"])
    L += ["## ROC-AUC by test year", "", "| Year | Floods | " + " | ".join(names) + " |",
          "|---|---|" + "---|" * len(names)]
    for y, s in r["per_year"].items():
        L.append(f"| {y} | {s['floods']} | " + " | ".join(str(s["models"][n]["roc_auc"]) for n in names) + " |")
    L += ["", "## PR-AUC by test year", "", "| Year | Prevalence | " + " | ".join(names) + " |",
          "|---|---|" + "---|" * len(names)]
    for y, s in r["per_year"].items():
        L.append(f"| {y} | {s['prevalence']} | " + " | ".join(str(s["models"][n]["pr_auc"]) for n in names) + " |")
    if r["missing"]:
        L += ["", "Missing values (share of rows): " + ", ".join(f"{k} {v}" for k, v in r["missing"].items()) + "."]
    L += ["", f"Run time {r['seconds']} s."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
