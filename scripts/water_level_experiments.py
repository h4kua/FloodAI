#!/usr/bin/env python
"""
Real DSDA water levels in the flood model, and a learned decision layer against the hand-written rules
(exploratory; nothing served).

Water levels: data/processed/dsda_tma_daily_2016_2020.csv (scripts/dsda_history.py; official
status_siaga of every post, Oct 2016 to Dec 2020, gaps in 2016-2017) and the 2025 daily file
(scripts/thesis_experiments.daily_water_levels; one reading a day, status from the live DSDA limits).
City features per day: highest status of the river posts, how many river posts are at Siaga 3 / 2 or
above, Katulampa/Depok (upstream) and Manggarai status, highest coastal status, each also for the day
before. A day counts only when at least 8 river posts reported.

Part A  Does the kecamatan model gain from water levels? XGBoost F4 vs F4 + city water features on the
        kecamatan-days of test years 2019 and 2020 (trained on the earlier water-level days, Oct 2016
        onward), paired bootstrap over dates.
Part B  City-day warnings, test years 2019, 2020 and 2025 (Jan-Sep), each trained on earlier years:
          rules    the highest Siaga status of the river posts (Siaga 3 -> Watch, 2 -> Alert, 1 -> Danger),
                   the core of the engine's L1 / L1.8 rules
          model    the highest kecamatan flood probability of the year's rolling model
                   (scripts/long_experiments.py, trained on 2013..Y-1)
          hybrid   the higher of rules and model (the current design)
          learned  a depth-3 decision tree on the water features + model probability, trained on the earlier
                   water-level days, plus two safety rules: a river post at Siaga 1 -> at least Alert,
                   no water data -> the model alone
        Each scored at its own thresholds (chosen on the training days: Watch on 8, Alert on 4, Danger on
        2 days a month) and at the same number of warning days as the rules. Label: a BPBD flood in any of
        the 42 kecamatan that day; large = 5 or more kecamatan.

Outputs artifacts/reports/water_level_experiments.{json,md}.
Usage (repo root):  python scripts/water_level_experiments.py [--bootstrap 1000] [--cpu]
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
from sklearn.tree import DecisionTreeClassifier, export_text

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.long_experiments import long_dataset  # noqa: E402
from scripts.thesis_experiments import (  # noqa: E402
    F4, SIAGA_JSON, TMA_TO_FEED, DateBootstrap, _boot_days, daily_water_levels, day_metrics, fit_predict, siaga_level,
)
from scripts.dsda_history import COASTAL_WORDS, post_key  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

DAILY_CSV = PROCESSED_DATA_DIR / "dsda_tma_daily_2016_2020.csv"
MIN_RIVER_POSTS = 8
UPSTREAM = {"KATULAMPA", "DEPOK"}
WL = ["river_max", "river_n1", "river_n2", "upstream_max", "manggarai", "coastal_max"]
WL_ALL = WL + [f"{c}_prev" for c in WL]
TEST_YEARS = (2019, 2020, 2021, 2025)
DAYS_PER_MONTH = 30.44
BUDGET = ((1, 8), (2, 4), (3, 2))  # level, warning days a month
APPROACHES = ("rules", "rules (informative posts)", "model", "hybrid", "hybrid (informative posts)", "learned")
DIFFS = [("rules (informative posts)", "learned"), ("hybrid (informative posts)", "learned"),
         ("rules (informative posts)", "hybrid (informative posts)")]


def daily_posts() -> pd.DataFrame:
    """One row per post and day: post key, date, status (0-3), coastal flag, 2016-2020 and 2025."""
    hist = pd.read_csv(DAILY_CSV, parse_dates=["date"])[["post", "date", "status_max", "coastal"]]
    hist = hist.rename(columns={"status_max": "status"})
    feed = {p["name"]: p for p in json.loads(SIAGA_JSON.read_text(encoding="utf-8"))["posts"]}
    y25 = daily_water_levels()
    y25 = y25[y25["nama_objek"].isin(TMA_TO_FEED)]
    y25 = pd.DataFrame({"post": [post_key(n) for n in y25["nama_objek"]], "date": y25["date"],
                        "status": [np.nan if pd.isna(t) else siaga_level(t, feed[TMA_TO_FEED[n]])
                                   for t, n in zip(y25["tma"], y25["nama_objek"])]})
    y25["coastal"] = y25["post"].apply(lambda p: any(w in p for w in COASTAL_WORDS)).astype(int)
    return pd.concat([hist, y25], ignore_index=True).dropna(subset=["status"])


def city_features(posts: pd.DataFrame) -> pd.DataFrame:
    river, coast = posts[posts["coastal"] == 0], posts[posts["coastal"] == 1]
    g = river.groupby("date")
    city = pd.DataFrame({
        "river_posts": g["post"].nunique(),
        "river_max": g["status"].max(),
        "river_n1": g["status"].apply(lambda s: int((s >= 1).sum())),
        "river_n2": g["status"].apply(lambda s: int((s >= 2).sum())),
        "upstream_max": river[river["post"].isin(UPSTREAM)].groupby("date")["status"].max(),
        "manggarai": river[river["post"] == "MANGGARAI"].groupby("date")["status"].max(),
        "coastal_max": coast.groupby("date")["status"].max(),
    })
    city = city[city["river_posts"] >= MIN_RIVER_POSTS].copy()
    full = city.reindex(pd.date_range(city.index.min(), city.index.max(), freq="D"))
    for c in WL:
        city[f"{c}_prev"] = full[c].shift(1).reindex(city.index)
    return city.rename_axis("date")


def thresholds(score: np.ndarray) -> dict[int, float]:
    return {lvl: float(np.quantile(score, 1 - n / DAYS_PER_MONTH)) for lvl, n in BUDGET}


def to_levels(score: pd.Series, t: dict[int, float]) -> pd.Series:
    lv = pd.Series(0, index=score.index)
    for lvl in (1, 2, 3):
        lv[score >= t[lvl]] = lvl
    return lv


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
    data = long_dataset()
    data = data.join(city[WL_ALL], on="date")
    res: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
                 "city_days_with_water_levels": {int(y): int(n) for y, n in city.groupby(city.index.year).size().items()}}
    print("water-level days per year", res["city_days_with_water_levels"], flush=True)

    # ---------------- Part A: water features in the kecamatan model
    has_wl = data["river_max"].notna()
    res["part_a"] = {}
    pa_y, pa_base, pa_wl, pa_dates = [], [], [], []
    for year in (2019, 2020, 2021):
        train = data[has_wl & (data["year"] < year)]
        test = data[has_wl & (data["year"] == year)]
        p_base, = fit_predict("xgboost", train, [test], F4, device=device)
        p_wl, = fit_predict("xgboost", train, [test], F4 + WL_ALL, device=device)
        y = test["flood"].to_numpy()
        res["part_a"][str(year)] = {"train_rows": int(len(train)), "test_rows": int(len(test)), "floods": int(y.sum()),
                                    "F4": {"roc_auc": round(float(roc_auc_score(y, p_base)), 3),
                                           "pr_auc": round(float(average_precision_score(y, p_base)), 3)},
                                    "F4 + water levels": {"roc_auc": round(float(roc_auc_score(y, p_wl)), 3),
                                                          "pr_auc": round(float(average_precision_score(y, p_wl)), 3)}}
        pa_y.append(y), pa_base.append(p_base), pa_wl.append(p_wl), pa_dates.append(test["date"].to_numpy())
        print("part A", year, res["part_a"][str(year)], flush=True)
    y, b, w, d = (np.concatenate(v) for v in (pa_y, pa_base, pa_wl, pa_dates))
    boot = DateBootstrap(d, args.bootstrap)
    res["part_a"]["pooled 2019-2021"] = {"F4": {"roc_auc": boot.ci(roc_auc_score, y, b), "pr_auc": boot.ci(average_precision_score, y, b)},
                                         "F4 + water levels": {"roc_auc": boot.ci(roc_auc_score, y, w),
                                                               "pr_auc": boot.ci(average_precision_score, y, w)},
                                         "difference": boot.diff(y, b, w)}

    # ---------------- Part B: city-day warnings
    flood_kec = data.groupby("date")["flood"].sum()
    res["part_b"] = {"years": {}, "trees": {}, "always_on_posts": {}}
    pooled = {name: [] for name in APPROACHES}
    pooled_score = {name: [] for name in ("rules", "rules (informative posts)", "model", "learned")}
    river_posts = posts[posts["coastal"] == 0]
    pooled_flood, pooled_large = [], []
    for year in TEST_YEARS:
        train_rows = data[data["year"] < year]
        test_rows = data[data["year"] == year]
        p_train_years = []
        # Model probability for every kecamatan-day: test year from the model trained before it; training
        # days from a model trained before *their* year, so the tree never sees in-sample probabilities.
        p_test, = fit_predict("xgboost", train_rows, [test_rows], F4, device=device)
        city_p_test = pd.Series(p_test, index=test_rows.index).groupby(test_rows["date"]).max()
        wl_years = sorted(y for y in city.index.year.unique() if y < year)
        for wy in wl_years:
            tr, te = data[data["year"] < wy], data[data["year"] == wy]
            p, = fit_predict("xgboost", tr, [te], F4, device=device)
            p_train_years.append(pd.Series(p, index=te.index).groupby(te["date"]).max())
        city_p_train = pd.concat(p_train_years)

        def frame(days, city_p):
            f = city.reindex(days)[WL_ALL].copy()
            f["model_p"] = city_p.reindex(days).to_numpy()
            f["flood"] = (flood_kec.reindex(days).fillna(0) >= 1).astype(int).to_numpy()
            f["large"] = (flood_kec.reindex(days).fillna(0) >= 5).astype(int).to_numpy()
            return f

        train_days = city.index[(city.index.year < year)]
        test_days = city.index[city.index.year == year]
        # Rain (IMERG) ends 2025-09-30, so later 2025 days have no model probability and are left out.
        tr = frame(train_days, city_p_train).dropna(subset=["model_p"])
        te = frame(test_days, city_p_test).dropna(subset=["model_p"])
        rule_score = te["river_max"] + 0.01 * te["river_n1"]  # status first, then how many posts
        # Posts at Siaga 3+ on more than half of the training days carry no warning (gate-operated city posts
        # such as Hek, Jembatan Merah, Istiqlal); chosen on the training years only.
        past = river_posts[river_posts["date"].dt.year < year]
        share = past.assign(on=past["status"] >= 1).groupby("post")["on"].mean()
        always_on = sorted(share[share > 0.5].index)
        res["part_b"]["always_on_posts"][str(year)] = {p: round(float(share[p]), 2) for p in always_on}
        inf = river_posts[~river_posts["post"].isin(always_on)].groupby("date")["status"]
        rules_inf = inf.max().reindex(te.index).fillna(0).astype(int)
        rules_inf_score = rules_inf + 0.01 * inf.apply(lambda s: int((s >= 1).sum())).reindex(te.index).fillna(0)
        tree_feats = WL_ALL + ["model_p"]
        tree = DecisionTreeClassifier(max_depth=3, min_samples_leaf=20, class_weight="balanced", random_state=42)
        tree.fit(tr[tree_feats].fillna(-1), tr["flood"])
        learned_score = pd.Series(tree.predict_proba(te[tree_feats].fillna(-1))[:, 1], index=te.index)
        learned_train = pd.Series(tree.predict_proba(tr[tree_feats].fillna(-1))[:, 1], index=tr.index)
        res["part_b"]["trees"][str(year)] = export_text(tree, feature_names=tree_feats)

        levels = {
            "rules": te["river_max"].astype(int),
            "model": to_levels(te["model_p"], thresholds(tr["model_p"].to_numpy())),
        }
        levels["hybrid"] = np.maximum(levels["rules"], levels["model"])
        levels["rules (informative posts)"] = rules_inf
        levels["hybrid (informative posts)"] = np.maximum(rules_inf, levels["model"])
        learned = to_levels(learned_score, thresholds(learned_train.to_numpy()))
        learned[te["river_max"] >= 3] = np.maximum(learned[te["river_max"] >= 3], 2)  # safety: Siaga 1 -> >= Alert
        levels["learned"] = learned
        y_entry = {"days": int(len(te)), "flood_days": int(te["flood"].sum()), "large_days": int(te["large"].sum()),
                   "train_days": int(len(tr)), "auc_any_flood": {}}
        for name, s in (("rules", rule_score), ("rules (informative posts)", rules_inf_score),
                        ("model", te["model_p"]), ("learned", learned_score)):
            y_entry["auc_any_flood"][name] = round(float(roc_auc_score(te["flood"], s)), 3) if te["flood"].nunique() > 1 else None
            pooled_score[name].append(s.to_numpy())
        for name, lv in levels.items():
            pooled[name].append(lv.to_numpy())
        pooled_flood.append(te["flood"].to_numpy())
        pooled_large.append(te["large"].to_numpy())
        res["part_b"]["years"][str(year)] = y_entry
        print("part B", year, y_entry, flush=True)

    flood, large = np.concatenate(pooled_flood), np.concatenate(pooled_large)
    lv = {k: np.concatenate(v) for k, v in pooled.items()}
    res["part_b"]["pooled"] = {}
    for lab, f in (("any flood", flood), ("large flood (>= 5 kecamatan)", large)):
        for lvl, lvl_name in ((1, ">= Watch"), (2, ">= Alert"), (3, "Danger")):
            warn = {k: pd.Series(v >= lvl) for k, v in lv.items()}
            entry = {k: day_metrics(w, pd.Series(f.astype(bool))) for k, w in warn.items()}
            for a, b in DIFFS:
                entry[f"{b} minus {a}"] = _boot_days(warn[a], warn[b], f, args.bootstrap)
            res["part_b"]["pooled"][f"{lab} | {lvl_name}"] = entry
    # Same number of warning days as the informative-post rules, at each level: which score ranks the
    # flood days best when every approach may warn equally often?
    score = {k: np.concatenate(v) for k, v in pooled_score.items()}
    res["part_b"]["equal_warning_days"] = {}
    for lvl, lvl_name in ((1, "Watch"), (2, "Alert"), (3, "Danger")):
        n = int((lv["rules (informative posts)"] >= lvl).sum())
        eq = {"rules (informative posts)": lv["rules (informative posts)"] >= lvl}
        for name in ("model", "learned"):
            order = np.argsort(-score[name], kind="stable")
            pick = np.zeros(len(order), bool)
            pick[order[:n]] = True
            eq[name] = pick
        for lab, f in (("any flood", flood), ("large flood (>= 5 kecamatan)", large)):
            entry = {k: day_metrics(pd.Series(w), pd.Series(f.astype(bool))) for k, w in eq.items()}
            entry["learned minus rules (informative posts)"] = _boot_days(eq["rules (informative posts)"], eq["learned"],
                                                                          f, args.bootstrap)
            res["part_b"]["equal_warning_days"][f"{lab} | {n} days, as many as rules >= {lvl_name}"] = entry
    res["seconds"] = round(time.time() - started, 1)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "water_level_experiments.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    (REPORTS_DIR / "water_level_experiments.md").write_text(markdown(res), encoding="utf-8")
    print(markdown(res))
    return 0


def _ci(v):
    return f"{v[0]} [{v[1]}–{v[2]}]"


def markdown(r: dict) -> str:
    L = ["# Water levels in the model, and a learned decision layer vs the rules", "",
         f"Generated {r['generated_at']} by `scripts/water_level_experiments.py` on {r['device']}. Nothing here is served.", "",
         "City-days with water levels (at least 8 river posts): " +
         ", ".join(f"{y}: {n}" for y, n in r["city_days_with_water_levels"].items()) + ".", "",
         "## Part A · Water levels as model features (kecamatan-days)", "",
         "| Test | Rows | Floods | F4 ROC-AUC | F4 + water ROC-AUC | F4 PR-AUC | F4 + water PR-AUC |", "|---|---|---|---|---|---|---|"]
    for y in ("2019", "2020", "2021"):
        a = r["part_a"][y]
        L.append(f"| {y} | {a['test_rows']} | {a['floods']} | {a['F4']['roc_auc']} | {a['F4 + water levels']['roc_auc']} | "
                 f"{a['F4']['pr_auc']} | {a['F4 + water levels']['pr_auc']} |")
    p = r["part_a"]["pooled 2019-2021"]
    L += ["", f"Pooled 2019–2021: F4 ROC-AUC {_ci(p['F4']['roc_auc'])}, PR-AUC {_ci(p['F4']['pr_auc'])}; "
          f"F4 + water ROC-AUC {_ci(p['F4 + water levels']['roc_auc'])}, PR-AUC {_ci(p['F4 + water levels']['pr_auc'])}. "
          f"Difference (95 %): ROC-AUC {p['difference']['roc_auc']}, PR-AUC {p['difference']['pr_auc']}.", "",
          "## Part B · City-day warnings, test years " + ", ".join(r["part_b"]["years"]), "",
          "| Year | Days | Flood days | Large-flood days | ROC-AUC rules | ROC-AUC rules (informative) | ROC-AUC model | ROC-AUC learned |",
          "|---|---|---|---|---|---|---|---|"]
    for y, e in r["part_b"]["years"].items():
        a = e["auc_any_flood"]
        L.append(f"| {y} | {e['days']} | {e['flood_days']} | {e['large_days']} | {a['rules']} | "
                 f"{a['rules (informative posts)']} | {a['model']} | {a['learned']} |")
    L += ["", "Posts left out of the informative-post rules (share of training days at Siaga 3+): " +
          "; ".join(f"test {y}: " + (", ".join(f"{p} {s}" for p, s in posts.items()) or "none")
                    for y, posts in r["part_b"]["always_on_posts"].items()) + ".", "",
          "Each approach at its own levels (thresholds from the training days):", "",
          "| Label · level | Approach | Warning days | Flood days | Recall | Recall incl. day before | Precision | False alarms |",
          "|---|---|---|---|---|---|---|---|"]
    for key, entry in r["part_b"]["pooled"].items():
        for name in APPROACHES:
            m = entry[name]
            L.append(f"| {key} | {name} | {m['warning_days']} | {m['flood_days']} | {m['recall']} | "
                     f"{m['recall_same_or_day_before']} | {m['precision']} | {m['false_alarm_days']} |")
        for a, b in DIFFS:
            d = entry[f"{b} minus {a}"]
            L.append(f"| {key} | {b} − {a}, 95 % | | | {d['recall_difference']} | | {d['precision_difference']} | |")
    L += ["", "### Same number of warning days as the informative-post rules, per level", "",
          "| Label · days | Approach | Warning days | Recall | Recall incl. day before | Precision |", "|---|---|---|---|---|---|"]
    for lab, entry in r["part_b"]["equal_warning_days"].items():
        for name, m in entry.items():
            if "minus" in name:
                L.append(f"| {lab} | {name}, 95 % | | {m['recall_difference']} | | {m['precision_difference']} |")
            else:
                L.append(f"| {lab} | {name} | {m['warning_days']} | {m['recall']} | {m['recall_same_or_day_before']} | "
                         f"{m['precision']} |")
    L += ["", "### The learned decision trees (one per test year)", ""]
    for y, t in r["part_b"]["trees"].items():
        L += [f"Test {y}:", "", "```text", t.rstrip(), "```", ""]
    L += [f"Run time {r['seconds']} s."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
