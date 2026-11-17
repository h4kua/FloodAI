#!/usr/bin/env python
"""
Experiments on the learned decision layer (exploratory; the served layer is unchanged).

All on the city snapshots of scripts/train_decision_layer.py (06/12/18/23 WIB, DSDA archive 2016-2021 and
the 2025 daily file, rain lag 1 as the site usually serves, snapshots with yesterday's posts), the same
learner (XGBoost depth 2, inputs monotone increasing) and the same test: years 2019, 2020, 2021, 2025,
each scored by a model trained on earlier years, thresholds that raise each level as often as the rules
did on the training snapshots (leave-one-year-out scores), a river post at Siaga 1 -> Bahaya. Intervals
resample days; differences are paired.

1  Today's rain so far. IMERG Early files arrive ~4.5 h after each half-hour, so at hour H the site
   knows the rain of today's half-hours that started by H-5 h. Added: city mean and max over the model's
   kecamatan cells and Bogor upstream, plus the hour (not monotone). The 2025 file has one reading a
   day of unknown time: taken as 06:00.
2  One status per wilayah (the five kota) instead of one for Jakarta. Label per wilayah: a BPBD flood in
   one of its kecamatan that day. The city layer's level for every wilayah vs a layer that adds the
   wilayah's highest kecamatan chance and its own river posts (now / yesterday; the posts upstream of
   Jakarta stay city-wide), thresholds matched to the city layer's alarm volume on the training rows.
3  Ablation (without the daily model, without yesterday, without the upstream posts, daily model alone,
   posts now alone), calibration of the served chance (10 bins, ECE, Brier), and the Waspada threshold
   swept from 10 % to 50 % (alarm share, recall, precision).
5  Lead time, 2020-2021: flood days with a BPBD record and a detik.com report (scripts/fetch_news_flood_days.py;
   first publish time that day from the cached article). Snapshots from 18:00 the day before up to the
   first report: did the layer (and the rules) reach Waspada / Siaga before it, and how many hours before.
   Snapshot spacing is 5-7 h, so leads are coarse; reports follow the flood's start, so they are upper bounds.

Outputs artifacts/reports/decision_layer_experiments.{json,md}.
Usage (repo root): python scripts/decision_layer_experiments.py --rows-cache DIR [--bootstrap 1000] [--cpu]
  (DIR as for scripts/train_decision_layer.py: the snapshot rows are built once and reused.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import types
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from realtime_native import daily_features as dfe  # noqa: E402
from scripts import train_daily_live_model as tdl  # noqa: E402
from scripts import train_decision_layer as dl  # noqa: E402
from scripts.dsda_history import load_year  # noqa: E402
from scripts.thesis_experiments import DateBootstrap  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

LAG = 1
SEED = 42
TEST_YEARS = dl.TEST_YEARS
SERVED = dl.FEATURES
NOW, D1 = dl.NOW, dl.D1
TODAY = ["today_mean", "today_max", "today_bogor"]
WILAYAH = ["jakarta barat", "jakarta pusat", "jakarta selatan", "jakarta timur", "jakarta utara"]
POST_WILAYAH = {"CIDENG": "jakarta pusat", "KARET": "jakarta pusat", "KALIDURI": "jakarta barat",
                "ANGKEHULU": "jakarta barat", "KRUKUTHULU": "jakarta selatan", "MANGGARAI": "jakarta selatan",
                "PESANGGRAHAN": "jakarta selatan", "PULOGADUNG": "jakarta timur", "SUNTERHULU": "jakarta timur",
                "PLUIT": "jakarta utara", "YOSSUDARSO": "jakarta utara"}
UPSTREAM_ALL = {"KATULAMPA", "DEPOK", "CIBALOKGADOG"}
NEWS_2020 = PROCESSED_DATA_DIR / "news_flood_reports_2020_2022.csv"
NEWS_CACHE = _PROJECT_ROOT / "data" / "raw" / "news"


# ---------------------------------------------------------------- learner

def make_model(feats: list[str]) -> XGBClassifier:
    mono = ",".join("0" if (f == "hour" or f.startswith("is_")) else "1" for f in feats)
    return XGBClassifier(n_estimators=300, max_depth=2, learning_rate=0.05, min_child_weight=20, subsample=0.8,
                         colsample_bytree=0.8, eval_metric="logloss", monotone_constraints=f"({mono})",
                         tree_method="hist", random_state=SEED)


def _x(frame: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    return frame[feats].astype(float).fillna(0.0)


def oof(rows: pd.DataFrame, feats: list[str], label: str) -> np.ndarray:
    out = np.full(len(rows), np.nan)
    for year in rows["year"].unique():
        held = (rows["year"] == year).to_numpy()
        model = make_model(feats).fit(_x(rows[~held], feats), rows.loc[~held, label])
        out[held] = model.predict_proba(_x(rows[held], feats))[:, 1]
    return out


def rolling(rows: pd.DataFrame, feats: list[str], label: str, reference: np.ndarray,
            safety: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Out-of-sample score and level on the test years (NaN / -1 elsewhere)."""
    score, level = np.full(len(rows), np.nan), np.full(len(rows), -1)
    for year in TEST_YEARS:
        train, test = (rows["year"] < year).to_numpy(), (rows["year"] == year).to_numpy()
        tr = rows[train].reset_index(drop=True)
        thr = dl.volume_matched(oof(tr, feats, label), reference[train])
        model = make_model(feats).fit(_x(tr, feats), tr[label])
        score[test] = model.predict_proba(_x(rows[test], feats))[:, 1]
        level[test] = dl.learned_levels(score[test], thr, np.where(safety[test], 3, 0))
    return score, level


# ---------------------------------------------------------------- inputs

def today_rain(rows: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    """Rain of today's half-hours that started by H-5 h (WIB), per snapshot."""
    kec_cells = sorted({k["cell"] for k in bundle["kecamatan"].values()})
    bogor = bundle["upstream_cells"]["bogor"]
    hours = rows["hour"].where(rows["hour"] >= 0, 6).to_numpy()
    cutoff = rows["date"].to_numpy() + pd.to_timedelta(hours - 5, unit="h").to_numpy()
    out = {}
    for cell in sorted(set(kec_cells) | {bogor}):
        files = sorted(tdl.EARLY_DIR.glob(f"{cell}_*.csv"))
        rate = pd.concat(tdl.parse_timeseries(f.read_text(encoding="utf-8")) for f in files)
        rate = rate[~rate.index.duplicated(keep="last")].sort_index().fillna(0.0)
        local = pd.Series(rate.to_numpy() * 0.5, index=rate.index.tz_convert(None) + pd.Timedelta(hours=7))
        cum = local.groupby(local.index.floor("D")).cumsum()  # mm since WIB midnight, at each half-hour start
        # value at the last half-hour starting <= cutoff of the same day (0 before the first)
        pos = cum.index.searchsorted(cutoff, side="right") - 1
        vals = np.where(pos >= 0, cum.to_numpy()[np.clip(pos, 0, None)], 0.0)
        same_day = np.where(pos >= 0, cum.index.to_numpy()[np.clip(pos, 0, None)] >= rows["date"].to_numpy(), False)
        out[cell] = np.where(same_day & (hours - 5 >= 0), vals, 0.0)
    jak = np.column_stack([out[c] for c in kec_cells])
    return pd.DataFrame({"today_mean": jak.mean(axis=1), "today_max": jak.max(axis=1), "today_bogor": out[bogor]},
                        index=rows.index)


def post_snapshots() -> pd.DataFrame:
    """Per river post: latest status in the 3 h before each check hour (archive), daily reading (2025)."""
    readings = pd.concat([load_year(y)[0] for y in range(2016, 2021)], ignore_index=True).drop_duplicates()
    readings = readings[readings["time"] != readings["time"].dt.floor("D")]
    readings = readings.assign(post=readings["post"].map(dfe.post_key)).dropna(subset=["status"])
    readings = readings[readings["post"].isin(dfe.RIVER_POSTS)]
    readings = readings.assign(date=readings["time"].dt.floor("D"),
                               minute=readings["time"].dt.hour * 60 + readings["time"].dt.minute)
    frames = []
    for hour in dl.CHECK_HOURS:
        end = hour * 60
        sub = readings[(readings["minute"] > end - dl.WINDOW_MIN) & (readings["minute"] <= end)]
        latest = sub.sort_values("time").groupby(["date", "post"], as_index=False).last()
        frames.append(latest[["date", "post", "status"]].assign(hour=hour))
    posts = tdl.daily_posts()
    posts = posts.assign(post=posts["post"].map(dfe.post_key))
    y25 = posts[(posts["date"].dt.year == 2025) & posts["post"].isin(dfe.RIVER_POSTS)]
    frames.append(y25[["date", "post", "status"]].assign(hour=-1))
    return pd.concat(frames, ignore_index=True)


def wilayah_post_features(snap_posts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(date, hour, wilayah) -> highest local post now; (date, wilayah) -> highest local post that day."""
    local = snap_posts.assign(wilayah=snap_posts["post"].map(POST_WILAYAH)).dropna(subset=["wilayah"])
    now = local.groupby(["date", "hour", "wilayah"])["status"].max().rename("local_now").reset_index()
    posts = tdl.daily_posts()
    posts = posts.assign(post=posts["post"].map(dfe.post_key))
    posts = posts.assign(wilayah=posts["post"].map(POST_WILAYAH)).dropna(subset=["wilayah"])
    day = posts.groupby(["date", "wilayah"])["status"].max().rename("local_day").reset_index()
    return now, day


def report_times() -> pd.DataFrame:
    """First detik.com report time (WIB) per day, 2020-2022."""
    news = pd.read_csv(NEWS_2020)
    out = []
    for url in news["url"].unique():
        path = NEWS_CACHE / f"article_{hashlib.md5(url.encode()).hexdigest()[:16]}.html"
        if not path.exists():
            continue
        m = re.search(r'name="dtk:publishdate" content="(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"',
                      path.read_text(encoding="utf-8", errors="ignore"))
        if m:
            out.append(pd.Timestamp(m.group(1).replace("/", "-")))
    times = pd.Series(sorted(out))
    return times.groupby(times.dt.floor("D")).min().rename("first_report").rename_axis("date").reset_index()


# ---------------------------------------------------------------- scoring helpers

def compare(boot: DateBootstrap, y: np.ndarray, base: tuple, other: tuple) -> dict:
    (s_a, l_a), (s_b, l_b) = base, other
    return {"roc_auc": boot.ci(roc_auc_score, y, s_b), "roc_auc_minus_base": boot.diff(y, s_a, s_b)["roc_auc"],
            "levels": dl.level_metrics(y, l_b), "levels_minus_base": dl.paired_diffs(boot, y, l_a, l_b)}


def calibration(y: np.ndarray, p: np.ndarray) -> dict:
    bins = np.clip((p * 10).astype(int), 0, 9)
    table = []
    ece = 0.0
    for b in range(10):
        m = bins == b
        if m.sum() == 0:
            continue
        pred, obs = float(p[m].mean()), float(y[m].mean())
        ece += m.sum() / len(y) * abs(pred - obs)
        table.append({"bin": f"{b * 10}-{b * 10 + 10} %", "snapshots": int(m.sum()), "mean_chance": round(pred, 3),
                      "flood_share": round(obs, 3)})
    return {"ece": round(ece, 4), "brier": round(float(brier_score_loss(y, p)), 4),
            "brier_no_skill": round(float(brier_score_loss(y, np.full(len(y), y.mean()))), 4), "bins": table}


def cost_curve(y: np.ndarray, p: np.ndarray) -> list[dict]:
    out = []
    for t in np.arange(0.10, 0.5001, 0.025):
        warn = p >= t
        tp = int((warn & (y == 1)).sum())
        out.append({"threshold": round(float(t), 3), "alarm_share": round(float(warn.mean()), 3),
                    "recall": round(tp / max(int(y.sum()), 1), 3), "precision": round(tp / max(int(warn.sum()), 1), 3)})
    return out


# ---------------------------------------------------------------- main

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

    rows = dl.build_rows(types.SimpleNamespace(rows_cache=args.rows_cache), device)[LAG]
    rows = rows.dropna(subset=["w_max_d1"]).reset_index(drop=True)
    rows["hour"] = rows["hour"].where(rows["hour"] >= 0, 6)
    rows[TODAY] = today_rain(rows, bundle)
    current = dl.current_levels(rows, float(rows["waspada"].iloc[0]))
    siaga1 = rows["w_max_now"].fillna(0).to_numpy() >= 3
    test = rows["year"].isin(TEST_YEARS).to_numpy()
    t = rows[test].reset_index(drop=True)
    y = t["flood"].to_numpy()
    boot = DateBootstrap(t["date"].to_numpy(), args.bootstrap)
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
              "bootstrap": args.bootstrap, "lag": LAG, "test_snapshots": int(test.sum()),
              "test_days": int(t["date"].nunique()), "flood_share": round(float(y.mean()), 3)}

    # 1 + 3: variants of the layer
    variants = {
        "served (daily chance + posts now + yesterday)": SERVED,
        "+ today's rain so far (and the hour)": SERVED + TODAY + ["hour"],
        "without the daily model": NOW + D1,
        "without yesterday's posts": ["p"] + NOW,
        "without the upstream posts": [f for f in SERVED if not f.startswith("w_upstream")],
        "daily model alone": ["p"],
        "posts now alone": NOW,
    }
    results = {}
    base = None
    for name, feats in variants.items():
        s, lv = rolling(rows, feats, "flood", current, siaga1)
        results[name] = (s[test], lv[test])
        base = base or results[name]
        print(f"exp1/3 {name}: ROC-AUC {roc_auc_score(y, s[test]):.3f}", flush=True)
    report["rules"] = {"roc_auc": boot.ci(roc_auc_score, y, current[test].astype(float)),
                       "levels": dl.level_metrics(y, current[test])}
    report["variants"] = {name: compare(boot, y, base, res) for name, res in results.items()}
    served_score = results["served (daily chance + posts now + yesterday)"][0]
    report["calibration"] = calibration(y, served_score)
    report["calibration_by_year"] = {str(yr): calibration(y[(t["year"] == yr).to_numpy()],
                                                          served_score[(t["year"] == yr).to_numpy()])["ece"]
                                     for yr in TEST_YEARS}
    report["waspada_curve"] = cost_curve(y, served_score)

    # 2: one status per wilayah
    points = tdl.build_points()
    kecamatan = sorted(k for k in points if k in tdl._CANONICAL_BY_SLUG)
    floods = tdl.flood_kecamatan_days()
    floods = floods[(floods["date"] >= tdl.START) & (floods["date"] <= tdl.END)]
    posts = tdl.daily_posts()
    posts = posts.assign(post=posts["post"].map(dfe.post_key))
    city_water = dfe.city_water_by_day(posts)
    data = tdl.build(LAG, tdl.daily_rain_by_cell(sorted(set(points.values()))), points, kecamatan, floods,
                     tdl.static_table(floods, kecamatan, points), city_water)
    p_kec = tdl.rolling(data, dfe.FEATURES, device)
    iso = bundle["lags"][str(LAG)]["isotonic"]
    ok = ~np.isnan(p_kec) & data["rain_lag"].notna().to_numpy()
    kota = pd.read_csv(PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv").drop_duplicates("name_3")
    kota = dict(zip(kota["name_3"], kota["name_2"]))
    kec = data.loc[ok, ["date", "kecamatan", "flood"]].assign(p=np.interp(p_kec[ok], iso["x"], iso["y"]),
                                                              wilayah=lambda f: f["kecamatan"].map(kota))
    kec = kec.dropna(subset=["wilayah"])
    wd = kec.groupby(["date", "wilayah"]).agg(p_w=("p", "max"), flood_w=("flood", "max")).reset_index()
    snap_posts = post_snapshots()
    now_w, day_w = wilayah_post_features(snap_posts)
    up_now = (snap_posts[snap_posts["post"].isin(UPSTREAM_ALL)].groupby(["date", "hour"])["status"].max()
              .rename("up_now").reset_index())
    base_rows = rows.assign(row_id=np.arange(len(rows)), hour_key=rows["hour"].where(rows["hour"] != 6, 6))
    base_rows["hour_key"] = np.where(base_rows["year"] == 2025, -1, base_rows["hour"])
    w_rows = base_rows.merge(pd.DataFrame({"wilayah": WILAYAH}), how="cross")
    w_rows = w_rows.merge(wd, on=["date", "wilayah"], how="left")
    w_rows = w_rows.merge(now_w.rename(columns={"hour": "hour_key"}), on=["date", "hour_key", "wilayah"], how="left")
    day_w = day_w.assign(date=day_w["date"] + pd.Timedelta(days=1)).rename(columns={"local_day": "local_d1"})
    w_rows = w_rows.merge(day_w, on=["date", "wilayah"], how="left")
    w_rows = w_rows.merge(up_now.rename(columns={"hour": "hour_key"}), on=["date", "hour_key"], how="left")
    w_rows = w_rows.dropna(subset=["p_w", "flood_w"]).reset_index(drop=True)
    for w in WILAYAH:
        w_rows[f"is_{w.split()[1]}"] = (w_rows["wilayah"] == w).astype(int)
    city_score_all = np.full(len(rows), np.nan)
    city_level_all = np.full(len(rows), -1)
    city_score_all[test], city_level_all[test] = results["served (daily chance + posts now + yesterday)"]
    w_rows["city_score"] = city_score_all[w_rows["row_id"]]
    w_rows["city_level"] = city_level_all[w_rows["row_id"]]
    # Reference volume for the wilayah layer: the city layer's levels on the training rows (in-sample rules
    # there, since the city layer has no out-of-sample levels before 2019).
    ref = np.where(w_rows["city_level"] >= 0, w_rows["city_level"], current[w_rows["row_id"]])
    local_siaga1 = (w_rows["local_now"].fillna(0) >= 3) | (w_rows["up_now"].fillna(0) >= 3)
    w_feats = SERVED + ["p_w", "local_now", "local_d1"] + [f"is_{w.split()[1]}" for w in WILAYAH]
    w_rows = w_rows.rename(columns={"flood_w": "flood_wilayah"})
    s_w, l_w = rolling(w_rows, w_feats, "flood_wilayah", ref, local_siaga1.to_numpy())
    wt = (w_rows["year"].isin(TEST_YEARS) & (w_rows["city_level"] >= 0)).to_numpy()
    tw = w_rows[wt].reset_index(drop=True)
    yw = tw["flood_wilayah"].to_numpy()
    wboot = DateBootstrap(tw["date"].to_numpy(), args.bootstrap)
    city_pair = (tw["city_score"].to_numpy(), tw["city_level"].to_numpy())
    report["wilayah"] = {"rows": int(wt.sum()), "flood_share": round(float(yw.mean()), 3),
                         "city level for every wilayah": {"roc_auc": wboot.ci(roc_auc_score, yw, city_pair[0]),
                                                          "levels": dl.level_metrics(yw, city_pair[1])},
                         "own wilayah layer": compare(wboot, yw, city_pair, (s_w[wt], l_w[wt])), "per_wilayah": {}}
    for w in WILAYAH:
        m = (tw["wilayah"] == w).to_numpy()
        report["wilayah"]["per_wilayah"][w] = {
            "flood_share": round(float(yw[m].mean()), 3),
            "city": dl.level_metrics(yw[m], city_pair[1][m]), "own": dl.level_metrics(yw[m], l_w[wt][m])}
    print("exp2 done", flush=True)

    # 5: lead time before the first news report, 2020-2021
    first = report_times()
    flood_days = rows.groupby("date")["flood"].max()
    snaps = rows.assign(time=rows["date"] + pd.to_timedelta(rows["hour"], unit="h"),
                        learned=city_level_all, rules=current)
    snaps = snaps[snaps["year"].isin([2019, 2020, 2021])]
    lead = []
    for _, r in first.iterrows():
        d, tr_ = r["date"], r["first_report"]
        if d.year not in (2020, 2021) or flood_days.get(d, 0) != 1:
            continue
        window = snaps[(snaps["time"] >= d - pd.Timedelta(hours=6)) & (snaps["time"] < tr_)].sort_values("time")
        if window.empty or (window["learned"] < 0).any():
            continue
        rec = {"date": d, "report": tr_}
        for who in ("learned", "rules"):
            for k, name in ((1, "Waspada"), (2, "Siaga")):
                hit = window[window[who] >= k]
                rec[f"{who}_{name}"] = (tr_ - hit["time"].iloc[0]).total_seconds() / 3600 if len(hit) else np.nan
        lead.append(rec)
    lead = pd.DataFrame(lead)
    lt = {"flood_days": int(len(lead))}
    if len(lead):
        lboot = DateBootstrap(lead["date"].to_numpy(), args.bootstrap)
        for name in ("Waspada", "Siaga"):
            a, b = lead[f"rules_{name}"].notna().to_numpy(), lead[f"learned_{name}"].notna().to_numpy()
            diffs = [b[s].mean() - a[s].mean() for s in lboot.samples]
            lt[name] = {"rules_warned_share": round(float(a.mean()), 3), "learned_warned_share": round(float(b.mean()), 3),
                        "learned_minus_rules_95": [round(float(np.percentile(diffs, 2.5)), 3),
                                                   round(float(np.percentile(diffs, 97.5)), 3)],
                        "rules_median_lead_h": round(float(lead[f"rules_{name}"].median()), 1) if a.any() else None,
                        "learned_median_lead_h": round(float(lead[f"learned_{name}"].median()), 1) if b.any() else None,
                        "learned_lead_6h_share": round(float((lead[f"learned_{name}"] >= 6).mean()), 3),
                        "rules_lead_6h_share": round(float((lead[f"rules_{name}"] >= 6).mean()), 3)}
        lt["median_first_report_hour"] = round(float(lead["report"].dt.hour.median()), 1)
    report["lead_time"] = lt
    print("exp5 done", flush=True)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "decision_layer_experiments.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (REPORTS_DIR / "decision_layer_experiments.md").write_text(markdown(report), encoding="utf-8")
    return 0


def _ci(v):
    return f"{v[0]} [{v[1]}–{v[2]}]"


def _levels(x):
    return " · ".join(f"{n} {x[n]['alarm_share']}/{x[n]['recall']}/{x[n]['precision']}" for n in dl.LEVEL_NAMES.values())


def markdown(r: dict) -> str:
    L = ["# Experiments on the learned decision layer", "",
         f"Generated {r['generated_utc']} by `scripts/decision_layer_experiments.py` on {r['device']} "
         f"({r['bootstrap']} day resamples). Rain lag {r['lag']}. Test years 2019, 2020, 2021, 2025: "
         f"{r['test_snapshots']} snapshots on {r['test_days']} days, flood days {r['flood_share']}. Nothing here "
         "changes the site.", "", "Levels read as alarm share / recall / precision.", "",
         "## 1 and 3 · Inputs: today's rain, and what each input adds", "",
         f"Rules (river posts + daily Waspada): ROC-AUC {_ci(r['rules']['roc_auc'])}; {_levels(r['rules']['levels'])}.", "",
         "| Variant | ROC-AUC [95 %] | − served, 95 % | Levels | Recall − served (95 %) per level |", "|---|---|---|---|---|"]
    for name, x in r["variants"].items():
        d = " · ".join(f"{n} {x['levels_minus_base'][n]['recall']}" for n in dl.LEVEL_NAMES.values())
        L.append(f"| {name} | {_ci(x['roc_auc'])} | {x['roc_auc_minus_base']} | {_levels(x['levels'])} | {d} |")
    c = r["calibration"]
    L += ["", f"## 3 · Calibration of the served chance", "",
          f"ECE {c['ece']}, Brier {c['brier']} (no skill {c['brier_no_skill']}). ECE by test year: {r['calibration_by_year']}.", "",
          "| Chance | Snapshots | Mean chance | Flood share |", "|---|---|---|---|"]
    L += [f"| {b['bin']} | {b['snapshots']} | {b['mean_chance']} | {b['flood_share']} |" for b in c["bins"]]
    L += ["", "## 3 · Waspada threshold (served chance, test snapshots)", "",
          "| Threshold | Alarm share | Recall | Precision |", "|---|---|---|---|"]
    L += [f"| {x['threshold']} | {x['alarm_share']} | {x['recall']} | {x['precision']} |" for x in r["waspada_curve"]]
    w = r["wilayah"]
    own = w["own wilayah layer"]
    L += ["", "## 2 · One status per wilayah", "",
          f"{w['rows']} wilayah-snapshots, a flood in the wilayah on {w['flood_share']} of them.", "",
          f"- City level for every wilayah: ROC-AUC {_ci(w['city level for every wilayah']['roc_auc'])}; "
          f"{_levels(w['city level for every wilayah']['levels'])}.",
          f"- Own wilayah layer: ROC-AUC {_ci(own['roc_auc'])} (− city {own['roc_auc_minus_base']}); {_levels(own['levels'])}.",
          "- Own − city per level: " + " · ".join(
              f"{n} recall {own['levels_minus_base'][n]['recall']}, precision {own['levels_minus_base'][n]['precision']}"
              for n in dl.LEVEL_NAMES.values()), "",
          "| Wilayah | Flood share | City: Waspada / Siaga recall, precision | Own: Waspada / Siaga recall, precision |",
          "|---|---|---|---|"]
    for name, x in w["per_wilayah"].items():
        cw, ow = x["city"], x["own"]
        L.append(f"| {name.title()} | {x['flood_share']} | {cw['Waspada']['recall']}, {cw['Waspada']['precision']} / "
                 f"{cw['Siaga']['recall']}, {cw['Siaga']['precision']} | {ow['Waspada']['recall']}, "
                 f"{ow['Waspada']['precision']} / {ow['Siaga']['recall']}, {ow['Siaga']['precision']} |")
    lt = r["lead_time"]
    L += ["", "## 5 · Lead time before the first news report (2020-2021)", "",
          f"{lt['flood_days']} flood days with a BPBD record and a detik.com report"
          + (f"; first report at {lt.get('median_first_report_hour')} h WIB (median)." if lt["flood_days"] else "."), ""]
    for name in ("Waspada", "Siaga"):
        if name in lt:
            x = lt[name]
            L.append(f"- >= {name} before the first report: rules {x['rules_warned_share']} (median lead "
                     f"{x['rules_median_lead_h']} h, >= 6 h on {x['rules_lead_6h_share']}), learned "
                     f"{x['learned_warned_share']} (median {x['learned_median_lead_h']} h, >= 6 h on "
                     f"{x['learned_lead_6h_share']}); learned − rules {x['learned_minus_rules_95']}.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
