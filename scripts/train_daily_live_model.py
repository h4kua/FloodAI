#!/usr/bin/env python
"""
Train and test the daily kecamatan flood model the website can serve, and write its bundle.

Rows: one of the 42 model kecamatan on one WIB day, 2013-01-01 to 2025-12-31. Labels: BPBD flood
dates (scripts/hourly_rain_experiment.flood_kecamatan_days; complete to 2022, partly readable for
2023-2025, so precision there is a lower bound). Features: realtime_native/daily_features.py, which
the server uses too. Rain is IMERG Early (scripts/fetch_imerg_history.py --early), the product a live
service can read; since Giovanni serves it about a day late, one model is trained per rain lag
(L = 1, 2, 3: rain through D-L). Water: DSDA Siaga status of the fixed river posts on D-1 and D-2
(archive 2016-2021, the 2025 DSDA file; NaN elsewhere, which XGBoost learns to handle).

Test: rolling origin. For each year Y in 2016..2025 a model trained on 2013..Y-1 scores Y. Compared:
place and season only; rain at lag 1/2/3 without and with water. 95 % intervals resample test dates.
Paired differences use the same resamples.

Served bundle (models/daily_bundle/): one XGBoost model per lag trained on 2013-2025, an isotonic map
fitted on the pooled out-of-sample predictions (each from a model that never saw that year), and
city thresholds. The city probability is the highest kecamatan probability of the day. Waspada is
set so the model alone would raise it on 8 days a month on average over 2016-2025 (the Watch budget
of scripts/water_level_experiments.py); Siaga and Bahaya only where at least 50 % / 70 % of the
model's alarm days had a flood somewhere in Jakarta. The model raises at most Waspada: Siaga and
Bahaya thresholds are 1.0 (city precision stays near 0.3-0.4 at any threshold).

Outputs models/daily_bundle/{bundle.json, model_lag{1,2,3}.json} and
artifacts/reports/daily_live_model.{json,md}.
Usage (repo root): python scripts/train_daily_live_model.py [--bootstrap 500] [--cpu]
  --bootstrap 0 rebuilds the bundle and the served-model section of the report, keeping the
  intervals of the last full run.
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
from xgboost import XGBClassifier

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from realtime_native import daily_features as dfe  # noqa: E402
from scripts.build_kelurahan_flood_history import _CANONICAL_BY_SLUG, _slug  # noqa: E402
from scripts.daily_model_candidate import ece  # noqa: E402
from scripts.fetch_imerg_history import EARLY_DIR, build_points, parse_timeseries  # noqa: E402
from scripts.hourly_rain_experiment import flood_kecamatan_days  # noqa: E402
from scripts.long_experiments import history_rate  # noqa: E402
from scripts.thesis_experiments import DateBootstrap  # noqa: E402
from scripts.water_level_experiments import daily_posts  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

START, END = "2013-01-01", "2025-12-31"
TEST_YEARS = range(2016, 2026)
COMPLETE = range(2016, 2023)
BUNDLE_DIR = _PROJECT_ROOT / "models" / "daily_bundle"
DAYS_PER_MONTH = 30.44
WASPADA_DAYS = 8  # model alarm days a month at Waspada (pre_alert)
# At city level the model's precision is about 0.3-0.4 at any threshold (base rate 0.22): it says
# "chance is up", not how bad. So it raises at most Waspada; Siaga and Bahaya stay with the water
# and BMKG rules (threshold 1.0 = the model alone never sets them). The report lists the precision
# a higher threshold would have had, for reference.
NOT_BY_MODEL = 1.0
SEED = 42
PLACE = ["hist_rate", "month_sin", "month_cos", "elevation", "slope"]


def features_for(lag: int, water: bool) -> list[str]:
    return dfe.RAIN + dfe.STATIC + (dfe.WATER if water else [])


VARIANTS = {"place and season": PLACE}
for _lag in dfe.LAGS:
    VARIANTS[f"lag {_lag}"] = features_for(_lag, False)
    VARIANTS[f"lag {_lag} + water"] = features_for(_lag, True)
PAIRS = [("place and season", "lag 2"), ("lag 2", "lag 2 + water"), ("lag 3", "lag 3 + water"),
         ("lag 1 + water", "lag 2 + water"), ("lag 2 + water", "lag 3 + water")]


def daily_rain_by_cell(cells: list[str]) -> dict[str, pd.Series]:
    out = {}
    for cell in cells:
        files = sorted(EARLY_DIR.glob(f"{cell}_*.csv"))
        if not files:
            raise SystemExit(f"No IMERG Early data for {cell}; run scripts/fetch_imerg_history.py --early")
        rate = pd.concat(parse_timeseries(f.read_text(encoding="utf-8")) for f in files)
        rate = rate[~rate.index.duplicated(keep="last")].sort_index()
        out[cell] = dfe.wib_daily_rain(rate)
    return out


def static_table(floods: pd.DataFrame, kecamatan: list[str], points: dict) -> pd.DataFrame:
    cleaned = pd.read_csv(PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv")
    geo = cleaned.groupby(cleaned["name_3"].map(_slug))[["elevation", "slope"]].mean()
    table = geo.reindex(kecamatan)
    table["cell"] = [points[k] for k in kecamatan]
    return table


def build(lag: int, rain: dict, points: dict, kecamatan: list[str], floods, static, city_water) -> pd.DataFrame:
    days = pd.date_range(START, END, freq="D")
    up_b = rain[points["upstream_bogor"]].reindex(pd.date_range("2012-12-01", END, freq="D"))
    up_d = rain[points["upstream_depok"]].reindex(up_b.index)
    frames = []
    for kec in kecamatan:
        local = rain[points[kec]].reindex(up_b.index)
        f = dfe.rain_features(local, up_b, up_d, lag).reindex(days)
        f["kecamatan"] = kec
        frames.append(f)
    data = pd.concat(frames).rename_axis("date").reset_index()
    flagged = set(zip(floods["kecamatan"], floods["date"]))
    data["flood"] = [int((k, d) in flagged) for k, d in zip(data["kecamatan"], data["date"])]
    data["year"] = data["date"].dt.year
    data = data.merge(history_rate(floods, kecamatan, range(2013, 2027)), on=["kecamatan", "year"], how="left")
    data = data.join(static[["elevation", "slope"]], on="kecamatan")
    data[["month_sin", "month_cos"]] = dfe.season(data["date"]).to_numpy()
    data[dfe.WATER] = dfe.water_features(city_water, data["date"]).to_numpy()
    return data


def make_model(device: str) -> XGBClassifier:
    return XGBClassifier(n_estimators=400, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                         min_child_weight=5, eval_metric="logloss", tree_method="hist", device=device,
                         random_state=SEED)


def rolling(data: pd.DataFrame, features: list[str], device: str) -> np.ndarray:
    """Out-of-sample prediction for every row of TEST_YEARS (trained on earlier years only)."""
    p = np.full(len(data), np.nan)
    for year in TEST_YEARS:
        train = data[(data["year"] < year)].dropna(subset=["rain_lag"]) if "rain_lag" in features else data[data["year"] < year]
        test = data["year"] == year
        model = make_model(device).fit(train[features], train["flood"])
        p[test.to_numpy()] = model.predict_proba(data.loc[test, features])[:, 1]
    return p


def city_days(data: pd.DataFrame, p: np.ndarray) -> pd.DataFrame:
    frame = pd.DataFrame({"date": data["date"].to_numpy(), "flood": data["flood"].to_numpy(), "p": p})
    return frame.groupby("date").agg(flood=("flood", "max"), p=("p", "max")).reset_index()


def city_thresholds(city: pd.DataFrame) -> dict:
    pre = float(np.quantile(city["p"], 1 - WASPADA_DAYS / DAYS_PER_MONTH))
    return {"pre_alert": pre, "warning": NOT_BY_MODEL, "danger": NOT_BY_MODEL}


def precision_by_budget(city: pd.DataFrame) -> dict:
    """For reference: city recall/precision if the model raised alarms on 8, 4, 2 or 1 days a month."""
    return tier_metrics(city, {f"{n} days a month": float(np.quantile(city["p"], 1 - n / DAYS_PER_MONTH))
                               for n in (8, 4, 2, 1)})


def tier_metrics(city: pd.DataFrame, thr: dict) -> dict:
    out = {}
    for name, t in thr.items():
        warn = city["p"] >= t
        tp = int((warn & (city["flood"] == 1)).sum())
        out[name] = {"threshold": round(float(t), 4), "warning_days_per_month": round(float(warn.mean() * DAYS_PER_MONTH), 2),
                     "recall": round(tp / max(int(city["flood"].sum()), 1), 3),
                     "precision": round(tp / max(int(warn.sum()), 1), 3)}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore", category=UserWarning)
    device = "cpu" if args.cpu else "cuda"

    points = build_points()
    kecamatan = sorted(k for k in points if k in _CANONICAL_BY_SLUG)
    floods = flood_kecamatan_days()
    floods = floods[(floods["date"] >= START) & (floods["date"] <= END)]
    static = static_table(floods, kecamatan, points)
    rain = daily_rain_by_cell(sorted(set(points.values())))
    posts = daily_posts()
    posts = posts.assign(post=posts["post"].map(dfe.post_key))
    city_water = dfe.city_water_by_day(posts)
    print(f"water days: {len(city_water)} ({city_water.index.min():%Y-%m-%d} to {city_water.index.max():%Y-%m-%d})")

    report_path = REPORTS_DIR / "daily_live_model.json"
    if args.bootstrap == 0 and report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["lags"] = {}
        variants = {f"lag {lag} + water": features_for(lag, True) for lag in dfe.LAGS}
    else:
        report = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
                  "rows": None, "variants": {}, "pairs": [], "lags": {}}
        variants = VARIANTS
    datasets = {lag: build(lag, rain, points, kecamatan, floods, static, city_water) for lag in dfe.LAGS}
    base = datasets[1]
    report["rows"] = {"total": int(len(base)), "floods": int(base["flood"].sum()),
                      "water_rows": int(base["w_max_d1"].notna().sum())}
    preds = {}
    for name, feats in variants.items():
        lag = int(name.split()[1]) if name.startswith("lag") else 2
        preds[name] = rolling(datasets[lag], feats, device)
        print(f"  {name}: done", flush=True)

    test = base["year"].isin(TEST_YEARS).to_numpy()
    dates = base["date"].to_numpy()
    blocks = {"2016-2022 (complete labels)": base["year"].isin(COMPLETE).to_numpy(),
              "2023-2025 (partial labels)": base["year"].isin(range(2023, 2026)).to_numpy(),
              "water years 2017-2021, 2025": base["year"].isin([2017, 2018, 2019, 2020, 2021, 2025]).to_numpy()}
    y_all = base["flood"].to_numpy()
    for block, mask in (blocks.items() if args.bootstrap else []):
        boot = DateBootstrap(dates[mask], args.bootstrap)
        y = y_all[mask]
        report["variants"][block] = {
            name: {"roc_auc": boot.ci(roc_auc_score, y, p[mask]), "pr_auc": boot.ci(average_precision_score, y, p[mask])}
            for name, p in preds.items()}
        report["variants"][block]["_floods"] = int(y.sum())
        report["variants"][block]["_prevalence"] = round(float(y.mean()), 4)
        for a, b in PAIRS:
            report["pairs"].append({"block": block, "a": a, "b": b, **boot.diff(y, preds[a][mask], preds[b][mask])})
        print(f"{block}: " + ", ".join(f"{n} {v['roc_auc'][0]}" for n, v in report["variants"][block].items()
                                        if not n.startswith("_")), flush=True)

    # Served bundle: per lag, final model on every year, isotonic on the out-of-sample predictions.
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    bundle = {"version": datetime.now(timezone.utc).strftime("%Y%m%d"), "features": dfe.FEATURES,
              "rain_source": "GPM IMERG Early V07 (Giovanni GPM_3IMERGHHE_07_precipitation)",
              "label_source": "BPBD DKI flood dates per kecamatan", "train_period": [START, END],
              "waspada_days_per_month": WASPADA_DAYS, "model_max_level": "PRE_ALERT", "lags": {}, "kecamatan": {}}
    for lag in dfe.LAGS:
        name = f"lag {lag} + water"
        data, p_oos = datasets[lag], preds[name]
        ok = test & ~np.isnan(p_oos) & data["rain_lag"].notna().to_numpy()
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(p_oos[ok], y_all[ok])
        p_cal = np.full(len(data), np.nan)
        p_cal[ok] = iso.predict(p_oos[ok])
        city = city_days(data[ok], p_cal[ok])
        thr = city_thresholds(city)
        train = data.dropna(subset=["rain_lag"])
        model = make_model(device).fit(train[dfe.FEATURES], train["flood"])
        model.get_booster().set_param({"device": "cpu"})
        model.save_model(BUNDLE_DIR / f"model_lag{lag}.json")
        complete = ok & base["year"].isin(COMPLETE).to_numpy()
        city_c = city_days(data[complete], p_cal[complete])
        bundle["lags"][str(lag)] = {
            "model_file": f"model_lag{lag}.json",
            "isotonic": {"x": [round(float(v), 6) for v in iso.X_thresholds_],
                         "y": [round(float(v), 6) for v in iso.y_thresholds_]},
            "city_thresholds": {k: round(v, 5) for k, v in thr.items()},
        }
        report["lags"][name] = {
            "kecamatan_ece_before": round(ece(y_all[ok], p_oos[ok]), 4), "kecamatan_ece_after": round(ece(y_all[ok], p_cal[ok]), 4),
            "kecamatan_brier_after": round(float(brier_score_loss(y_all[ok], p_cal[ok])), 4),
            "city_roc_auc_2016_2022": round(float(roc_auc_score(city_c["flood"], city_c["p"])), 3),
            "city_flood_day_share_2016_2022": round(float(city_c["flood"].mean()), 3),
            "tiers_2016_2022": tier_metrics(city_c, thr),
            "tiers_2016_2025": tier_metrics(city, thr),
            "reference_budgets_2016_2022": precision_by_budget(city_c),
        }
    last = history_rate(floods, kecamatan, range(2026, 2027)).set_index("kecamatan")["hist_rate"]
    for kec in kecamatan:
        bundle["kecamatan"][kec] = {"name": _CANONICAL_BY_SLUG[kec], "cell": static.loc[kec, "cell"],
                                    "hist_rate": round(float(last[kec]), 6),
                                    "elevation": round(float(static.loc[kec, "elevation"]), 3),
                                    "slope": round(float(static.loc[kec, "slope"]), 4)}
    bundle["upstream_cells"] = {"bogor": points["upstream_bogor"], "depok": points["upstream_depok"]}
    bundle["metrics"] = report["lags"]
    (BUNDLE_DIR / "bundle.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    report["bundle_generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORTS_DIR / "daily_live_model.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["lags"], indent=1))
    return 0


def _ci(v):
    return f"{v[0]} [{v[1]}–{v[2]}]"


def markdown(r: dict) -> str:
    L = ["# Daily kecamatan model for the website (IMERG Early)", "",
         f"Generated {r['generated_utc']} by `scripts/train_daily_live_model.py` on {r['device']}. "
         f"{r['rows']['total']} kecamatan-days 2013-2025, {r['rows']['floods']} with a BPBD flood, "
         f"{r['rows']['water_rows']} with water levels of the previous day.", "",
         "Rain through D-L only (IMERG Early reaches Giovanni about a day late). Rolling origin: each test "
         "year is scored by a model trained on earlier years. 95 % intervals resample test dates.", ""]
    for block, v in r["variants"].items():
        L += [f"## {block}: {v['_floods']} floods, prevalence {v['_prevalence']}", "",
              "| Model | ROC-AUC [95 %] | PR-AUC [95 %] |", "|---|---|---|"]
        L += [f"| {n} | {_ci(s['roc_auc'])} | {_ci(s['pr_auc'])} |" for n, s in v.items() if not n.startswith("_")]
        L.append("")
    L += ["## Paired differences (b minus a, 95 %)", "", "| Block | a | b | ROC-AUC | PR-AUC |", "|---|---|---|---|---|"]
    L += [f"| {p['block']} | {p['a']} | {p['b']} | {p['roc_auc']} | {p['pr_auc']} |" for p in r["pairs"]]
    L += ["", "## Served models: calibration and city tiers", ""]
    for name, m in r["lags"].items():
        L += [f"### {name}", "",
              f"Kecamatan ECE {m['kecamatan_ece_before']} → {m['kecamatan_ece_after']} after isotonic, Brier "
              f"{m['kecamatan_brier_after']}. City (highest kecamatan) ROC-AUC 2016-2022 {m['city_roc_auc_2016_2022']}; "
              f"share of days with a flood somewhere {m['city_flood_day_share_2016_2022']}.", "",
              "| Tier | Threshold | Days a month (2016-2022) | Recall | Precision |", "|---|---|---|---|---|"]
        L += [f"| {k} | {t['threshold']} | {t['warning_days_per_month']} | {t['recall']} | {t['precision']} |"
              for k, t in m["tiers_2016_2022"].items() if t["threshold"] < 1.0]
        L += ["", "Siaga and Bahaya: not raised by the model (threshold 1.0). For reference, other alarm budgets:", "",
              "| Budget | Threshold | Recall | Precision |", "|---|---|---|---|"]
        L += [f"| {k} | {t['threshold']} | {t['recall']} | {t['precision']} |"
              for k, t in m.get("reference_budgets_2016_2022", {}).items()]
        L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
