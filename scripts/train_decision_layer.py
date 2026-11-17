#!/usr/bin/env python
"""
Train and test the learned decision layer that replaces the hand-written middle layers of the decision
engine (L1.5, L1.8, L2.3/L3.3, L3, L3.1, L3.7, L4, L1.9), and write it for the site.

What the site sees at any moment, and so what the layer learns from (one row per city snapshot):
  p             the daily kecamatan model's city probability (highest kecamatan; rain through D-L,
                calibrated as served; out of sample: for year Y from a model trained on 2013..Y-1)
  *_now         the river posts right now: highest Siaga status (0 normal .. 3 Siaga 1), share of posts
                at Siaga 3+ / Siaga 2+, upstream (Katulampa, Depok), Manggarai. The 14 fixed river
                posts of realtime_native/daily_features.py (coastal, tidal and gate posts left out).
  *_d1          the same posts yesterday (each post's highest status of the day)
Snapshots: 06:00, 12:00, 18:00 and 23:00 WIB of every day of the DSDA archive (2016-2021: per post the
latest reading of the 3 hours before; date-only readings dropped) and the one daily reading of the 2025
DSDA file. A snapshot counts with at least 8 river posts. Label: BPBD recorded a flood in any of the 42
model kecamatan that day (large: 5 or more kecamatan).

Layer: a depth-3 decision tree (at most 3 questions; leaves of >= 40 snapshots) giving a flood score;
three thresholds turn it into Waspada / Siaga / Bahaya. The thresholds give the layer as many snapshots
at each level as the current design on the training snapshots, so the comparison is at equal alarm
volume. The current design here = the river rules (Siaga 3 -> Waspada, 2 -> Siaga, 1 -> Bahaya, the
core of L1/L1.8) together with the daily model's Waspada; the other engine layers need data the
archive lacks (BMKG, hourly rain, trend), so they are left out of both. Safety rules kept in front of
the layer on the site: invalid data -> Unknown (L0), a post at Siaga 1 or rising fast -> Bahaya (L1),
BMKG severe -> at least Siaga (L1.7). Here: a river post at Siaga 1 -> Bahaya.

Test: test years 2019, 2020, 2021, 2025, each with a tree trained on the earlier snapshots only.
Recall (share of flood-day snapshots at or above the level), precision and alarm share per level,
for any flood and large floods, with paired 95 % intervals that resample days.

Outputs models/daily_bundle/decision_layer.json (one tree per rain lag, trained on every snapshot) and
artifacts/reports/decision_layer.{json,md}.
Usage (repo root): python scripts/train_decision_layer.py [--bootstrap 1000] [--cpu]
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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text
from xgboost import XGBClassifier

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from realtime_native import daily_features as dfe  # noqa: E402
from scripts import train_daily_live_model as tdl  # noqa: E402
from scripts.dsda_history import load_year  # noqa: E402
from scripts.thesis_experiments import DateBootstrap  # noqa: E402
from utils.paths import REPORTS_DIR  # noqa: E402

LAGS = (1, 2, 3)
CHECK_HOURS = (6, 12, 18, 23)
WINDOW_MIN = 180
TEST_YEARS = (2019, 2020, 2021, 2025)
NOW = [f"{c}_now" for c in dfe.WATER_DAY]
D1 = [f"{c}_d1" for c in dfe.WATER_DAY]
FEATURES = ["p"] + NOW + D1
LEVEL_NAMES = {1: "Waspada", 2: "Siaga", 3: "Bahaya"}
LEVEL_KEYS = {1: "PRE_ALERT", 2: "WARNING", 3: "DANGER"}
LARGE = 5
DEPTH, MIN_LEAF, SEED = 3, 40, 42
OUT = tdl.BUNDLE_DIR / "decision_layer.json"


# ---------------------------------------------------------------- data

def archive_snapshots() -> pd.DataFrame:
    """City water features at the check hours of every archive day (2016-2021)."""
    readings = pd.concat([load_year(y)[0] for y in range(2016, 2021)], ignore_index=True).drop_duplicates()
    readings = readings[readings["time"] != readings["time"].dt.floor("D")]  # date-only rows: no hour
    readings = readings.assign(post=readings["post"].map(dfe.post_key)).dropna(subset=["status"])
    readings = readings[readings["post"].isin(dfe.RIVER_POSTS)]
    readings = readings.assign(date=readings["time"].dt.floor("D"),
                               minute=readings["time"].dt.hour * 60 + readings["time"].dt.minute)
    frames = []
    for hour in CHECK_HOURS:
        end = hour * 60
        sub = readings[(readings["minute"] > end - WINDOW_MIN) & (readings["minute"] <= end)]
        latest = sub.sort_values("time").groupby(["date", "post"], as_index=False).last()
        city = dfe.city_water_by_day(latest[["post", "date", "status"]])
        frames.append(city.add_suffix("_now").assign(hour=hour))
    return pd.concat(frames).reset_index()


def snapshots_2025(posts: pd.DataFrame) -> pd.DataFrame:
    """The 2025 DSDA file has one reading a day per post: one snapshot a day."""
    y25 = posts[posts["date"].dt.year == 2025]
    city = dfe.city_water_by_day(y25[["post", "date", "status"]])
    return city.add_suffix("_now").assign(hour=-1).reset_index()


def daily_city_p(lag: int, inputs: dict, device: str) -> tuple[pd.Series, pd.Series]:
    """Out-of-sample calibrated city probability per day, and BPBD flooded-kecamatan count per day."""
    data = tdl.build(lag, inputs["rain"], inputs["points"], inputs["kecamatan"], inputs["floods"],
                     inputs["static"], inputs["city_water"])
    p = tdl.rolling(data, dfe.FEATURES, device)
    iso = inputs["bundle"]["lags"][str(lag)]["isotonic"]
    ok = ~np.isnan(p) & data["rain_lag"].notna().to_numpy()
    frame = data.loc[ok, ["date", "flood"]].assign(p=np.interp(p[ok], iso["x"], iso["y"]))
    g = frame.groupby("date")
    return g["p"].max(), g["flood"].sum()


def assemble(snaps: pd.DataFrame, p: pd.Series, n_flooded: pd.Series, city_water: pd.DataFrame) -> pd.DataFrame:
    rows = snaps.copy()
    rows["p"] = p.reindex(rows["date"]).to_numpy()
    rows["n_flooded"] = n_flooded.reindex(rows["date"]).to_numpy()
    d1 = city_water.reindex(rows["date"] - pd.Timedelta(days=1))
    for c in dfe.WATER_DAY:
        rows[f"{c}_d1"] = d1[c].to_numpy()
    rows = rows.dropna(subset=["p", "n_flooded"]).reset_index(drop=True)
    rows["year"] = rows["date"].dt.year
    rows["flood"] = (rows["n_flooded"] >= 1).astype(int)
    rows["large"] = (rows["n_flooded"] >= LARGE).astype(int)
    return rows


# ---------------------------------------------------------------- levels

def current_levels(rows: pd.DataFrame, waspada: float) -> np.ndarray:
    rules = rows["w_max_now"].fillna(0).to_numpy().astype(int)
    model = (rows["p"].to_numpy() >= waspada).astype(int)
    return np.maximum(rules, model)


def _logistic_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[FEATURES].fillna(0.0)  # a missing post reading counts as normal


def make_scorer(name: str):
    """(fit(frame, y) -> model, score(model, frame) -> flood score in [0, 1])."""
    if name == "tree":
        return (lambda f, y: DecisionTreeClassifier(max_depth=DEPTH, min_samples_leaf=MIN_LEAF,
                                                    random_state=SEED).fit(_logistic_matrix(f), y),
                lambda m, f: m.predict_proba(_logistic_matrix(f))[:, 1])
    if name == "logistic":
        return (lambda f, y: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000)).fit(
                    _logistic_matrix(f), y),
                lambda m, f: m.predict_proba(_logistic_matrix(f))[:, 1])
    if name == "xgb_monotone":
        return (lambda f, y: XGBClassifier(n_estimators=300, max_depth=2, learning_rate=0.05, min_child_weight=20,
                                           subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
                                           monotone_constraints="(" + ",".join("1" for _ in FEATURES) + ")",
                                           tree_method="hist", random_state=SEED).fit(_logistic_matrix(f), y),
                lambda m, f: m.predict_proba(_logistic_matrix(f))[:, 1])
    raise ValueError(name)


def oof_scores(rows: pd.DataFrame, name: str) -> np.ndarray:
    """Leave-one-year-out scores of the given rows (each year scored by a model without it)."""
    fit, score = make_scorer(name)
    out = np.full(len(rows), np.nan)
    for year in rows["year"].unique():
        held = (rows["year"] == year).to_numpy()
        out[held] = score(fit(rows[~held], rows.loc[~held, "flood"]), rows[held])
    return out


def precision_matched(score: np.ndarray, y: np.ndarray, reference: np.ndarray) -> dict[int, float]:
    """Per level, the lowest score threshold whose precision (on these rows) reaches the reference
    level's precision on the same rows: at equal precision, the more floods caught the better.
    inf when no threshold does (the layer then never sets that level)."""
    order = np.argsort(-score)
    s_sorted, y_sorted = score[order], y[order]
    tp = np.cumsum(y_sorted)
    n = np.arange(1, len(y_sorted) + 1)
    out, last = {}, -np.inf
    for k in (1, 2, 3):
        ref = reference >= k
        if ref.sum() == 0:
            out[k] = np.inf
            continue
        target = float(y[ref].mean())
        # Only cut between distinct scores; ask for at least 10 rows above the threshold.
        cut = np.r_[s_sorted[1:] != s_sorted[:-1], True]
        ok = cut & (n >= 10) & (tp / n >= target)
        t = float(s_sorted[np.flatnonzero(ok)[-1]]) if ok.any() else np.inf
        out[k] = max(t, last)
        last = out[k]
    return out


def volume_matched(score: np.ndarray, reference: np.ndarray) -> dict[int, float]:
    """Per level, the score threshold giving as many rows at or above it as the reference level has
    on these rows (training years): the layer raises each level about as often as the rules."""
    out, last = {}, -np.inf
    for k in (1, 2, 3):
        share = float((reference >= k).mean())
        t = float(np.quantile(score, 1 - share)) if share > 0 else np.inf
        out[k] = max(t, last)
        last = out[k]
    return out


def learned_levels(score: np.ndarray, thr: dict[int, float], w_max_now: np.ndarray) -> np.ndarray:
    level = np.zeros(len(score), dtype=int)
    for k in (1, 2, 3):
        level[score >= thr[k]] = k
    level[np.nan_to_num(w_max_now) >= 3] = 3  # safety rule kept in front of the layer (L1)
    return level


def volume_matched_levels(score: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Diagnostic only (uses the test rows): as many rows at each level as the reference."""
    level = np.zeros(len(score), dtype=int)
    for k in (1, 2, 3):
        share = float((reference >= k).mean())
        if share > 0:
            level[score >= np.quantile(score, 1 - share)] = k
    return level


# ---------------------------------------------------------------- scoring

def level_metrics(y: np.ndarray, level: np.ndarray) -> dict:
    out = {}
    for k, name in LEVEL_NAMES.items():
        warn = level >= k
        tp = int((warn & (y == 1)).sum())
        out[name] = {"alarm_share": round(float(warn.mean()), 3), "recall": round(tp / max(int(y.sum()), 1), 3),
                     "precision": round(tp / max(int(warn.sum()), 1), 3)}
    return out


def paired_diffs(boot: DateBootstrap, y: np.ndarray, a: np.ndarray, b: np.ndarray) -> dict:
    """95 % intervals of (b - a) recall and precision per level over day resamples."""
    out = {}
    for k, name in LEVEL_NAMES.items():
        rec, prec = [], []
        for s in boot.samples:
            ys, wa, wb = y[s], a[s] >= k, b[s] >= k
            if ys.sum() == 0 or wa.sum() == 0 or wb.sum() == 0:
                continue
            rec.append(((wb & (ys == 1)).sum() - (wa & (ys == 1)).sum()) / ys.sum())
            prec.append((wb & (ys == 1)).sum() / wb.sum() - (wa & (ys == 1)).sum() / wa.sum())
        out[name] = {"recall": [round(float(np.percentile(rec, 2.5)), 3), round(float(np.percentile(rec, 97.5)), 3)],
                     "precision": [round(float(np.percentile(prec, 2.5)), 3), round(float(np.percentile(prec, 97.5)), 3)]}
    return out


def tree_json(tree: DecisionTreeClassifier) -> list[dict]:
    t = tree.tree_
    nodes = []
    for i in range(t.node_count):
        value = t.value[i][0]
        score = float(value[1] / value.sum()) if value.sum() else 0.0
        if t.children_left[i] == -1:
            nodes.append({"id": i, "leaf": True, "score": round(score, 4), "samples": int(t.n_node_samples[i])})
        else:
            nodes.append({"id": i, "leaf": False, "feature": FEATURES[t.feature[i]],
                          "threshold": round(float(t.threshold[i]), 6), "left": int(t.children_left[i]),
                          "right": int(t.children_right[i]), "missing_left": bool(t.missing_go_to_left[i]),
                          "score": round(score, 4), "samples": int(t.n_node_samples[i])})
    return nodes


# ---------------------------------------------------------------- main

SCORERS = ("tree", "logistic", "xgb_monotone")
MODES = {"tree": ("precision",), "logistic": ("precision", "volume"), "xgb_monotone": ("precision", "volume")}


def build_rows(args, device) -> dict[int, pd.DataFrame]:
    # The cache holds only rows this script wrote itself (a local scratch folder); never point it at
    # files from elsewhere, since pickles can run code when loaded.
    cache = Path(args.rows_cache) if args.rows_cache else None
    if cache and all((cache / f"rows_lag{lag}.pkl").exists() for lag in LAGS):
        return {lag: pd.read_pickle(cache / f"rows_lag{lag}.pkl") for lag in LAGS}
    points = tdl.build_points()
    kecamatan = sorted(k for k in points if k in tdl._CANONICAL_BY_SLUG)
    floods = tdl.flood_kecamatan_days()
    floods = floods[(floods["date"] >= tdl.START) & (floods["date"] <= tdl.END)]
    posts = tdl.daily_posts()
    posts = posts.assign(post=posts["post"].map(dfe.post_key))
    city_water = dfe.city_water_by_day(posts)
    inputs = {"points": points, "kecamatan": kecamatan, "floods": floods,
              "static": tdl.static_table(floods, kecamatan, points),
              "rain": tdl.daily_rain_by_cell(sorted(set(points.values()))), "city_water": city_water,
              "bundle": json.loads((tdl.BUNDLE_DIR / "bundle.json").read_text(encoding="utf-8"))}
    snaps = pd.concat([archive_snapshots(), snapshots_2025(posts)], ignore_index=True)
    print(f"snapshots: {len(snaps)} on {snaps['date'].nunique()} days", flush=True)
    out = {}
    for lag in LAGS:
        p, n_flooded = daily_city_p(lag, inputs, device)
        rows = assemble(snaps, p, n_flooded, city_water)
        rows["waspada"] = inputs["bundle"]["lags"][str(lag)]["city_thresholds"]["pre_alert"]
        out[lag] = rows
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
            rows.to_pickle(cache / f"rows_lag{lag}.pkl")
    return out


def evaluate(rows: pd.DataFrame, name: str, current: np.ndarray, n_boot: int, mode: str = "precision") -> dict:
    fit, score_fn = make_scorer(name)
    learned = np.full(len(rows), -1)
    score = np.full(len(rows), np.nan)
    thresholds = {}
    for year in TEST_YEARS:
        train, test = (rows["year"] < year).to_numpy(), (rows["year"] == year).to_numpy()
        tr = rows[train].reset_index(drop=True)
        oof = oof_scores(tr, name)
        thr = (precision_matched(oof, tr["flood"].to_numpy(), current[train]) if mode == "precision"
               else volume_matched(oof, current[train]))
        model = fit(tr, tr["flood"])
        score[test] = score_fn(model, rows[test])
        learned[test] = learned_levels(score[test], thr, rows.loc[test, "w_max_now"].to_numpy())
        thresholds[str(year)] = {LEVEL_NAMES[k]: (None if np.isinf(v) else round(v, 4)) for k, v in thr.items()}
    test = learned >= 0
    t = rows[test]
    boot = DateBootstrap(t["date"].to_numpy(), n_boot)
    cur = current[test]
    out = {"thresholds_by_test_year": thresholds}
    for label in ("flood", "large"):
        y = t[label].to_numpy()
        vol = volume_matched_levels(score[test], cur)
        out[label] = {
            "roc_auc": {"current (ordinal levels)": boot.ci(roc_auc_score, y, cur.astype(float)),
                        "learned score": boot.ci(roc_auc_score, y, score[test]),
                        "learned minus current": boot.diff(y, cur.astype(float), score[test])["roc_auc"]},
            "current": level_metrics(y, cur), "learned": level_metrics(y, learned[test]),
            "learned_minus_current": paired_diffs(boot, y, cur, learned[test]),
            "equal_volume": {"learned": level_metrics(y, vol), "learned_minus_current": paired_diffs(boot, y, cur, vol)}}
    out["per_year"] = {}
    for year in TEST_YEARS:
        m = (t["year"] == year).to_numpy()
        out["per_year"][str(year)] = {"snapshots": int(m.sum()),
                                      "current": level_metrics(t["flood"].to_numpy()[m], cur[m]),
                                      "learned": level_metrics(t["flood"].to_numpy()[m], learned[test][m])}
    below = learned[test] < cur
    out["below_current_share"] = round(float(below.mean()), 3)
    out["below_current_with_post_siaga2"] = round(float((below & (t["w_max_now"].to_numpy() >= 2)).mean()), 3)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--rows-cache", default="", help="folder to keep the snapshot rows between runs")
    parser.add_argument("--serve", default="", choices=["", *SCORERS], help="write this layer for the site")
    parser.add_argument("--serve-mode", default="volume", choices=["precision", "volume"])
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", category=UserWarning)
    device = "cpu" if args.cpu else "cuda"
    # Snapshots need yesterday's posts (the site falls back to the rules without them); a single
    # missing post reading (upstream, Manggarai) counts as normal, so a data gap never raises the risk.
    rows_by_lag = {lag: r.dropna(subset=["w_max_d1"]).reset_index(drop=True) for lag, r in build_rows(args, device).items()}

    report = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
              "bootstrap": args.bootstrap, "features": FEATURES, "lags": {}}
    for lag, rows in rows_by_lag.items():
        current = current_levels(rows, float(rows["waspada"].iloc[0]))
        test = rows["year"].isin(TEST_YEARS)
        entry = {"snapshots": int(len(rows)), "test_snapshots": int(test.sum()),
                 "test_days": int(rows.loc[test, "date"].nunique()),
                 "flood_share": round(float(rows.loc[test, "flood"].mean()), 3),
                 "large_share": round(float(rows.loc[test, "large"].mean()), 3), "scorers": {}}
        for name, mode in [(n, m) for n in SCORERS for m in MODES[n]]:
            e = entry["scorers"][f"{name} · {mode}-matched"] = evaluate(rows, name, current, args.bootstrap, mode)
            f = e["flood"]
            print(f"lag {lag} {name} {mode}: ROC-AUC {f['roc_auc']['current (ordinal levels)'][0]} -> "
                  f"{f['roc_auc']['learned score'][0]} diff {f['roc_auc']['learned minus current']}; " + "; ".join(
                      f"{n} rec {f['current'][n]['recall']}->{f['learned'][n]['recall']} "
                      f"prec {f['current'][n]['precision']}->{f['learned'][n]['precision']} "
                      f"share {f['current'][n]['alarm_share']}->{f['learned'][n]['alarm_share']}"
                      for n in LEVEL_NAMES.values()), flush=True)
        report["lags"][f"lag {lag}"] = entry

    if args.serve:
        report["served"] = serve(rows_by_lag, args.serve, args.serve_mode)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "decision_layer.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORTS_DIR / "decision_layer.md").write_text(markdown(report), encoding="utf-8")
    return 0


def serve(rows_by_lag: dict, name: str, mode: str) -> dict:
    """Train the chosen layer on every snapshot (thresholds from leave-one-year-out scores) and write it."""
    fit, _ = make_scorer(name)
    layer = {"version": datetime.now(timezone.utc).strftime("%Y%m%d"), "kind": name, "threshold_mode": mode,
             "features": FEATURES,
             "label": "BPBD flood in any of the 42 model kecamatan that day", "levels": LEVEL_KEYS,
             "safety_rule": "a river post at Siaga 1 -> DANGER (engine L1)", "lags": {}}
    summary = {}
    for lag, rows in rows_by_lag.items():
        current = current_levels(rows, float(rows["waspada"].iloc[0]))
        oof = oof_scores(rows, name)
        thr = (precision_matched(oof, rows["flood"].to_numpy(), current) if mode == "precision"
               else volume_matched(oof, current))
        model = fit(rows, rows["flood"])
        spec = {"thresholds": {LEVEL_KEYS[k]: (None if np.isinf(v) else round(float(v), 5)) for k, v in thr.items()},
                "train_snapshots": int(len(rows)), "train_years": sorted(int(y) for y in rows["year"].unique())}
        if name == "tree":
            spec["nodes"] = tree_json(model)
        elif name == "logistic":
            scaler, logit = model.named_steps["standardscaler"], model.named_steps["logisticregression"]
            spec["mean"] = [round(float(v), 6) for v in scaler.mean_]
            spec["scale"] = [round(float(v), 6) for v in scaler.scale_]
            spec["coef"] = [round(float(v), 6) for v in logit.coef_[0]]
            spec["intercept"] = round(float(logit.intercept_[0]), 6)
        else:
            spec["model_file"] = f"decision_layer_lag{lag}.json"
            model.save_model(tdl.BUNDLE_DIR / spec["model_file"])
        layer["lags"][str(lag)] = spec
        summary[f"lag {lag}"] = spec["thresholds"]
    OUT.write_text(json.dumps(layer, indent=2), encoding="utf-8")
    return {"kind": name, "mode": mode, "thresholds": summary}


def _ci(v):
    return f"{v[0]} [{v[1]}–{v[2]}]"


def markdown(r: dict) -> str:
    L = ["# Learned decision layer vs the current rules", "",
         f"Generated {r['generated_utc']} by `scripts/train_decision_layer.py` on {r['device']} "
         f"({r['bootstrap']} day resamples).", "",
         f"Features: {', '.join(r['features'])}. Current = river rules (Siaga 3/2/1 -> Waspada/Siaga/Bahaya) + "
         "the daily model's Waspada. Learned: a flood score from one of three learners (depth-3 tree; logistic "
         "regression; XGBoost depth 2 with every feature monotone increasing), thresholds per level set on the "
         "training years (leave-one-year-out scores) at the precision the current level has there, so at equal "
         "precision the one catching more floods is better. A river post at Siaga 1 stays Bahaya. Test years "
         "2019, 2020, 2021, 2025, each trained on earlier snapshots only. 'Equal volume' re-cuts the learned "
         "score on the test rows to the current alarm shares (a ranking check, not deployable).", ""]
    if "served" in r:
        L += [f"Served: **{r['served']['kind']}** ({r['served']['mode']}-matched thresholds), "
              f"thresholds {r['served']['thresholds']}.", ""]
    for lag, e in r["lags"].items():
        L += [f"## {lag} · {e['test_snapshots']} test snapshots on {e['test_days']} days "
              f"(flood days {e['flood_share']}, large {e['large_share']})", ""]
        for name, x in e["scorers"].items():
            L += [f"### {name}", "", f"Thresholds by test year: {x['thresholds_by_test_year']}", ""]
            for label, title in (("flood", "any flood"), ("large", "large flood (>= 5 kecamatan)")):
                z = x[label]
                L += [f"**{title}**: ROC-AUC current {_ci(z['roc_auc']['current (ordinal levels)'])}, learned "
                      f"{_ci(z['roc_auc']['learned score'])}, difference {z['roc_auc']['learned minus current']}.", "",
                      "| Level | Current share / recall / precision | Learned share / recall / precision | "
                      "Learned − current recall, precision (95 %) | Equal volume: learned recall / precision | "
                      "Equal volume − current recall, precision (95 %) |", "|---|---|---|---|---|---|"]
                for n in LEVEL_NAMES.values():
                    c, lv, d = z["current"][n], z["learned"][n], z["learned_minus_current"][n]
                    v, vd = z["equal_volume"]["learned"][n], z["equal_volume"]["learned_minus_current"][n]
                    L.append(f"| >= {n} | {c['alarm_share']} / {c['recall']} / {c['precision']} | "
                             f"{lv['alarm_share']} / {lv['recall']} / {lv['precision']} | {d['recall']}, {d['precision']} | "
                             f"{v['recall']} / {v['precision']} | {vd['recall']}, {vd['precision']} |")
                L.append("")
            L += [f"Snapshots below the current level: {x['below_current_share']} (with a river post at Siaga 2+: "
                  f"{x['below_current_with_post_siaga2']}).", ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
