#!/usr/bin/env python
"""
Train, test and write the per-wilayah decision layer: one status for each of the five kota.

Rows: the city snapshots of scripts/train_decision_layer.py (06/12/18/23 WIB, DSDA archive 2016-2021 and the
2025 daily file, snapshots with yesterday's posts), one per wilayah. Label: a BPBD flood in one of the
wilayah's kecamatan that day. Inputs: everything the city layer reads (the daily model's city chance, the 14
river posts now and yesterday, today's rain so far, the hour), plus the wilayah's highest kecamatan chance
(the daily model, out of sample), its own river posts now and yesterday (highest status; posts upstream of
Jakarta stay in the city inputs) and which wilayah it is. Learner as the city layer: XGBoost depth 2, inputs
monotone increasing except the hour and the wilayah.

Thresholds: the city layer's flood-chance thresholds, so a level means the same chance everywhere (Siaga =
the chance of a recorded flood today in your area, or in Jakarta, reaches the city's Siaga threshold). A kota's
chance is lower than Jakarta's, so kota levels are rarer than the city's. Tested too: thresholds giving each
kota a level as often as the city layer raises it (volume-matched); they fell to a 6 % chance for Waspada and
38 % for Bahaya, which put South Jakarta at Bahaya on calm days of the November 2026 live replay, so they are
not served. Safety rule kept in front: a river post of the wilayah or upstream at Siaga 1 -> Bahaya there.

Test (rain lag 1): years 2019, 2020, 2021, 2025, each trained on earlier years. Compared with the city layer's
level copied to every wilayah; 95 % intervals resample days, paired.

Also written: the kecamatan of each wilayah that BPBD recorded flooded on the most days (2013-2025; the
2023-2025 records are only partly readable, so counts there are low), for the Beranda.

Outputs models/daily_bundle/wilayah_layer.json (+ wilayah_layer_lag{1,2,3}.json) and
artifacts/reports/wilayah_layer.{json,md}.
Usage (repo root): python scripts/train_wilayah_layer.py --rows-cache DIR [--bootstrap 1000] [--cpu]
"""

from __future__ import annotations

import argparse
import json
import sys
import types
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from realtime_native import daily_features as dfe  # noqa: E402
from scripts import decision_layer_experiments as dlx  # noqa: E402
from scripts import train_daily_live_model as tdl  # noqa: E402
from scripts import train_decision_layer as dl  # noqa: E402
from scripts.thesis_experiments import DateBootstrap  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

LAGS = (1, 2, 3)
WILAYAH = dlx.WILAYAH
ONE_HOT = [f"is_{w.split()[1]}" for w in WILAYAH]
W_FEATURES = dl.FEATURES + ["p_w", "local_now", "local_d1"] + ONE_HOT
NOT_MONOTONE = {"hour", *ONE_HOT}
SEED = 42
OUT = tdl.BUNDLE_DIR / "wilayah_layer.json"


def make_model(feats):
    mono = ",".join("0" if f in NOT_MONOTONE else "1" for f in feats)
    return XGBClassifier(n_estimators=300, max_depth=2, learning_rate=0.05, min_child_weight=20, subsample=0.8,
                         colsample_bytree=0.8, eval_metric="logloss", monotone_constraints=f"({mono})",
                         tree_method="hist", random_state=SEED)


def x(frame, feats):
    return frame[feats].astype(float).fillna(0.0)


def kota_of() -> dict[str, str]:
    c = pd.read_csv(PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv").drop_duplicates("name_3")
    return dict(zip(c["name_3"], c["name_2"]))


def wilayah_rows(lag: int, rows: pd.DataFrame, ctx: dict, device: str) -> pd.DataFrame:
    """rows (city snapshots of this lag) x wilayah, with the wilayah inputs and label."""
    data = tdl.build(lag, ctx["rain"], ctx["points"], ctx["kecamatan"], ctx["floods"], ctx["static"], ctx["city_water"])
    p = tdl.rolling(data, dfe.FEATURES, device)
    iso = ctx["bundle"]["lags"][str(lag)]["isotonic"]
    ok = ~np.isnan(p) & data["rain_lag"].notna().to_numpy()
    kec = data.loc[ok, ["date", "kecamatan", "flood"]].assign(p=np.interp(p[ok], iso["x"], iso["y"]))
    kec["wilayah"] = kec["kecamatan"].map(ctx["kota"])
    wd = kec.groupby(["date", "wilayah"]).agg(p_w=("p", "max"), flood_wilayah=("flood", "max")).reset_index()
    base = rows.assign(row_id=np.arange(len(rows)), hour_key=np.where(rows["year"] == 2025, -1, rows["hour"]))
    w = base.merge(pd.DataFrame({"wilayah": WILAYAH}), how="cross").merge(wd, on=["date", "wilayah"], how="left")
    w = w.merge(ctx["now_w"].rename(columns={"hour": "hour_key"}), on=["date", "hour_key", "wilayah"], how="left")
    w = w.merge(ctx["d1_w"], on=["date", "wilayah"], how="left")
    w = w.merge(ctx["up_now"].rename(columns={"hour": "hour_key"}), on=["date", "hour_key"], how="left")
    w = w.dropna(subset=["p_w", "flood_wilayah"]).reset_index(drop=True)
    for name, col in zip(WILAYAH, ONE_HOT):
        w[col] = (w["wilayah"] == name).astype(int)
    w["safety"] = (w["local_now"].fillna(0) >= 3) | (w["up_now"].fillna(0) >= 3)
    return w


def evaluate(w: pd.DataFrame, rows: pd.DataFrame, current: np.ndarray, n_boot: int) -> dict:
    """Test years: the city layer copied to each wilayah vs the wilayah layer (both out of sample)."""
    city_s, city_l = np.full(len(rows), np.nan), np.full(len(rows), -1)
    siaga1 = rows["w_max_now"].fillna(0).to_numpy() >= 3
    feats = dl.FEATURES
    city_thr = {}
    for year in dl.TEST_YEARS:
        train, test = (rows["year"] < year).to_numpy(), (rows["year"] == year).to_numpy()
        tr = rows[train].reset_index(drop=True)
        thr = city_thr[year] = dl.volume_matched(dlx.oof(tr, feats, "flood"), current[train])
        model = dlx.make_model(feats).fit(dlx._x(tr, feats), tr["flood"])
        city_s[test] = model.predict_proba(dlx._x(rows[test], feats))[:, 1]
        city_l[test] = dl.learned_levels(city_s[test], thr, np.where(siaga1[test], 3, 0))
    w = w.assign(city_score=city_s[w["row_id"]], city_level=city_l[w["row_id"]])
    ref = np.where(w["city_level"] >= 0, w["city_level"], current[w["row_id"]])
    s_w, l_w = dlx.rolling(w, W_FEATURES, "flood_wilayah", ref, w["safety"].to_numpy())
    # Served: the city layer's chance thresholds of that test year applied to the kota's own chance.
    l_c = np.full(len(w), -1)
    for year, thr in city_thr.items():
        m = (w["year"] == year).to_numpy()
        l_c[m] = dl.learned_levels(s_w[m], thr, np.where(w["safety"].to_numpy()[m], 3, 0))
    wt = (w["year"].isin(dl.TEST_YEARS) & (w["city_level"] >= 0)).to_numpy()
    t = w[wt].reset_index(drop=True)
    y = t["flood_wilayah"].to_numpy()
    boot = DateBootstrap(t["date"].to_numpy(), n_boot)
    city = (t["city_score"].to_numpy(), t["city_level"].to_numpy())
    out = {"rows": int(wt.sum()), "flood_share": round(float(y.mean()), 3),
           "city": {"roc_auc": boot.ci(roc_auc_score, y, city[0]), "levels": dl.level_metrics(y, city[1])},
           "wilayah": dlx.compare(boot, y, city, (s_w[wt], l_c[wt])),
           "wilayah_volume_matched": dlx.compare(boot, y, city, (s_w[wt], l_w[wt])), "per_wilayah": {}}
    for name in WILAYAH:
        m = (t["wilayah"] == name).to_numpy()
        out["per_wilayah"][name] = {"flood_share": round(float(y[m].mean()), 3),
                                    "city": dl.level_metrics(y[m], city[1][m]),
                                    "wilayah": dl.level_metrics(y[m], l_c[wt][m]),
                                    "wilayah_volume_matched": dl.level_metrics(y[m], l_w[wt][m])}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--rows-cache", required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", category=UserWarning)
    device = "cpu" if args.cpu else "cuda"

    bundle = json.loads((tdl.BUNDLE_DIR / "bundle.json").read_text(encoding="utf-8"))
    city_layer = json.loads((tdl.BUNDLE_DIR / "decision_layer.json").read_text(encoding="utf-8"))
    rows_by_lag = {lag: r.dropna(subset=["w_max_d1"]).reset_index(drop=True)
                   for lag, r in dl.build_rows(types.SimpleNamespace(rows_cache=args.rows_cache), device).items()}
    for rows in rows_by_lag.values():
        rows["hour"] = rows["hour"].where(rows["hour"] >= 0, 6)
        rows[dl.TODAY] = dl.today_rain(rows, bundle)

    points = tdl.build_points()
    kecamatan = sorted(k for k in points if k in tdl._CANONICAL_BY_SLUG)
    floods = tdl.flood_kecamatan_days()
    floods = floods[(floods["date"] >= tdl.START) & (floods["date"] <= tdl.END)]
    posts = tdl.daily_posts()
    posts = posts.assign(post=posts["post"].map(dfe.post_key))
    snap_posts = dlx.post_snapshots()
    now_w, day_w = dlx.wilayah_post_features(snap_posts)
    kota = kota_of()
    ctx = {"points": points, "kecamatan": kecamatan, "floods": floods, "bundle": bundle, "kota": kota,
           "static": tdl.static_table(floods, kecamatan, points), "city_water": dfe.city_water_by_day(posts),
           "rain": tdl.daily_rain_by_cell(sorted(set(points.values()))), "now_w": now_w,
           "d1_w": day_w.assign(date=day_w["date"] + pd.Timedelta(days=1)).rename(columns={"local_day": "local_d1"}),
           "up_now": snap_posts[snap_posts["post"].isin(dlx.UPSTREAM_ALL)].groupby(["date", "hour"])["status"].max()
           .rename("up_now").reset_index()}

    counts = floods.groupby("kecamatan").size()
    frequent = {}
    for name in WILAYAH:
        ks = sorted((k for k in bundle["kecamatan"] if kota.get(k) == name), key=lambda k: -int(counts.get(k, 0)))
        frequent[name] = [{"kecamatan": k, "name": bundle["kecamatan"][k]["name"], "flood_days": int(counts.get(k, 0))}
                          for k in ks[:3]]

    layer = {"version": datetime.now(timezone.utc).strftime("%Y%m%d"), "kind": "xgb_monotone", "features": W_FEATURES,
             "wilayah": WILAYAH, "kecamatan_wilayah": {k: kota[k] for k in bundle["kecamatan"]},
             "post_wilayah": dlx.POST_WILAYAH, "upstream_posts": sorted(dlx.UPSTREAM_ALL),
             "frequent": frequent, "frequent_period": "BPBD flood days 2013-2025 (2023-2025 partly readable)",
             "label": "BPBD flood in one of the wilayah's kecamatan that day", "lags": {}}
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
              "bootstrap": args.bootstrap, "features": W_FEATURES, "frequent": frequent}
    for lag in LAGS:
        rows = rows_by_lag[lag]
        w = wilayah_rows(lag, rows, ctx, device)
        if lag == 1:
            current = dl.current_levels(rows, float(rows["waspada"].iloc[0]))
            report["test_lag1"] = evaluate(w, rows, current, args.bootstrap)
            e = report["test_lag1"]
            print(f"lag 1 test: city ROC-AUC {e['city']['roc_auc'][0]} -> wilayah {e['wilayah']['roc_auc'][0]} "
                  f"diff {e['wilayah']['roc_auc_minus_base']}", flush=True)
        city_thr = city_layer["lags"][str(lag)]["thresholds"]
        thr = {1: city_thr["PRE_ALERT"], 2: city_thr["WARNING"], 3: city_thr["DANGER"]}
        model = make_model(W_FEATURES).fit(x(w, W_FEATURES), w["flood_wilayah"])
        model.save_model(tdl.BUNDLE_DIR / f"wilayah_layer_lag{lag}.json")
        layer["lags"][str(lag)] = {"model_file": f"wilayah_layer_lag{lag}.json", "train_rows": int(len(w)),
                                   "thresholds": {dl.LEVEL_KEYS[k]: (None if np.isinf(v) else round(float(v), 5))
                                                  for k, v in thr.items()}}
        print(f"lag {lag}: thresholds {layer['lags'][str(lag)]['thresholds']}", flush=True)
    report["thresholds"] = {lag: spec["thresholds"] for lag, spec in layer["lags"].items()}
    OUT.write_text(json.dumps(layer, indent=2), encoding="utf-8")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "wilayah_layer.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORTS_DIR / "wilayah_layer.md").write_text(markdown(report), encoding="utf-8")
    return 0


def markdown(r: dict) -> str:
    e = r["test_lag1"]
    lv = dlx._levels
    L = ["# Per-wilayah decision layer", "",
         f"Generated {r['generated_utc']} by `scripts/train_wilayah_layer.py` on {r['device']} ({r['bootstrap']} day "
         "resamples). Test (rain lag 1): years 2019, 2020, 2021, 2025, each trained on earlier years; levels read as "
         "alarm share / recall / precision; label = a BPBD flood in the wilayah that day.", "",
         f"{e['rows']} wilayah-snapshots, flood in the wilayah on {e['flood_share']}.", "",
         f"- City layer copied to every wilayah: ROC-AUC {dlx._ci(e['city']['roc_auc'])}; {lv(e['city']['levels'])}.",
         f"- Wilayah layer, served (the city's chance thresholds): ROC-AUC {dlx._ci(e['wilayah']['roc_auc'])} "
         f"(− city {e['wilayah']['roc_auc_minus_base']}); {lv(e['wilayah']['levels'])}.",
         f"- Wilayah layer, volume-matched thresholds (not served): {lv(e['wilayah_volume_matched']['levels'])}; − city "
         + " · ".join(f"{n} recall {e['wilayah_volume_matched']['levels_minus_base'][n]['recall']}, precision "
                      f"{e['wilayah_volume_matched']['levels_minus_base'][n]['precision']}" for n in dl.LEVEL_NAMES.values())
         + ".",
         "- Served wilayah − city per level: " + " · ".join(
             f"{n} recall {e['wilayah']['levels_minus_base'][n]['recall']}, precision "
             f"{e['wilayah']['levels_minus_base'][n]['precision']}" for n in dl.LEVEL_NAMES.values()), "",
         "| Wilayah | Flood share | City: Waspada / Siaga / Bahaya (recall, precision) | Wilayah layer (served) |", "|---|---|---|---|"]
    for name, x_ in e["per_wilayah"].items():
        def fmt(m):
            return " / ".join(f"{m[n]['recall']}, {m[n]['precision']}" for n in dl.LEVEL_NAMES.values())
        L.append(f"| {name.title()} | {x_['flood_share']} | {fmt(x_['city'])} | {fmt(x_['wilayah'])} |")
    L += ["", f"Served thresholds (flood chance per level): {r['thresholds']}", "",
          "Kecamatan flooded on the most days (BPBD 2013-2025):", ""]
    for name, ks in r["frequent"].items():
        L.append(f"- {name.title()}: " + ", ".join(f"{k['name']} ({k['flood_days']})" for k in ks))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
