#!/usr/bin/env python
"""
Thesis experiments: a daily flood model of our own, warning thresholds, rules vs model vs hybrid.
(exploratory; the served bundle is never written)

Rows: one kecamatan (the 42 model kecamatan) on one WIB day, 2020-01-01 to 2025-09-30 (IMERG
Final ends there). Label: BPBD recorded a flood in that kecamatan on that date
(data/raw/rekap_kejadian_2020_2025.csv, dates read by scripts/hourly_rain_experiment.py; complete
for 2020-2022, only partly readable for 2023-2025, so later precision is a lower bound).
Split: train 2020-2021, validate 2022 (complete dates), test 2023 to Sep 2025.

Exp 1  Model: feature sets F1-F5 (rain only -> + antecedent rain -> + upstream -> + place and
       season -> + hourly intensity) and model families (logistic regression, random forest, MLP,
       XGBoost, XGBoost tuned by random search on the GPU), against two baselines (rain that day,
       climatology). ROC-AUC / PR-AUC on the test years with 95 % intervals from a bootstrap over
       test dates, and paired differences.
Exp 2  Thresholds: warning thresholds chosen on 2022 by an alarm budget (alarms per kecamatan per
       month), by best F1 and by precision >= 0.30, then scored on the test years; the BMKG
       heavy-rain rule (>= 50 / 100 mm a day) for comparison.
Exp 3  Rules vs model vs hybrid, Jakarta-days 1 Jan to 30 Sep 2025: rules = DSDA Siaga limits (live pintu-air feed) of the
       15 of the 19 posts in the daily water-level file (data/raw/tinggi-muka-air-(tma)-pada-sungai-...xls;
       one reading a day, time not stated), model = the Exp 1 model's highest kecamatan
       probability, hybrid = the higher level of the two (as the engine's water floors do).
       Scored against BPBD flood days (any record) and large flood days (>= 10 RW records).

Outputs artifacts/reports/thesis_experiments.{json,md}. Needs the IMERG cache from
scripts/fetch_imerg_history.py and an NVIDIA GPU for the tuned XGBoost (falls back to CPU).

Usage (repo root):  python scripts/thesis_experiments.py [--trials 200] [--bootstrap 1000]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_curve, roc_auc_score
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.build_kelurahan_flood_history import _slug  # noqa: E402
from scripts.hourly_rain_experiment import _dates_in, build_dataset  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

SEED = 42
TRAIN_END, VAL_YEAR = 2021, 2022
REKAP_CSV = _PROJECT_ROOT / "data" / "raw" / "rekap_kejadian_2020_2025.csv"
TMA_XLS = _PROJECT_ROOT / "data" / "raw" / "tinggi-muka-air-(tma)-pada-sungai-komponen-data.xls"
# Siaga limits from the live DSDA pintu-air feed (same water-level scale as the 2025 file). The AWLR
# FeatureServer copy in data/bundled/awlr_stations.json is on another scale for several posts
# (Manggarai Siaga 1 = 250 cm there, 950 cm here) and is not used.
SIAGA_JSON = _PROJECT_ROOT / "data" / "bundled" / "dsda_siaga_limits_2026-11-10.json"
TMA_TO_FEED = {
    "BENDUNG KATULAMPA": "Bendung. Katulampa 2", "ISTIQLAL": "P.A. Istiqlal 1",
    "JEMBATAN MERAH": "P.A. Jembatan Merah 1", "PA. FLUSHING ANCOL": "P.A. Ancol Flushing 1",
    "PA. KARET": "P.A. Karet 1", "PA. MANGGARAI": "P.A. Manggarai 2",
    "PA. MARINA (KALI)": "P.A. Marina Ancol 1 (Kali)", "PA. MARINA (LAUT)": "P.A. Marina Ancol 1 (Laut)",
    "PA. PULOGADUNG": "P.A. Pulo Gadung 2", "PA.HEK": "P.A. Hek Kramat Jati 1",
    "PS. ANGKE HULU": "P.S. Angke Hulu 1", "PS. DEPOK": "P.S. Depok 2", "PS. KRUKUT HULU": "P.S. Krukut Hulu 2",
    "PS. PESANGGRAHAN": "P.S. Pesanggrahan 1", "PS. SUNTER HULU": "P.S. Sunter Hulu",
}  # Pasar Ikan (Laut), Cipinang Hulu, Tangki and Waduk Pluit have no limits in the feed.
EXP3_START, EXP3_END = "2025-01-01", "2025-09-30"
DAYS_PER_MONTH = 30.44

F1 = ["d0", "d1", "d3prev"]
F2 = F1 + ["d7prev", "api14"]
F3 = F2 + ["up_bogor_d0", "up_bogor_d1", "up_depok_d0"]
F4 = F3 + ["hist_rate", "month_sin", "month_cos", "elevation", "slope"]
F5 = F4 + ["max1h", "max3h", "max6h", "hours10", "up_bogor_max3h", "up_depok_max3h"]
DRIVERS = ["soil07_prev", "soil728_prev", "mjo_x", "mjo_y", "mjo_amp", "oni", "north_wind", "north_wind_d1",
           "spring_tide", "coastal", "coastal_spring_tide"]
F6 = F5 + DRIVERS
FEATURE_SETS = {"F1 rain (today, yesterday, 3 days)": F1, "F2 + antecedent rain (7 days, API)": F2,
                "F3 + upstream rain (Bogor, Depok)": F3, "F4 + place and season": F4,
                "F5 + hourly intensity": F5,
                "F6 + drivers (soil moisture, MJO, ENSO, northerly surge, spring tide)": F6}
DRIVERS_DIR = _PROJECT_ROOT / "data" / "raw" / "drivers"
# Kecamatan on the Jakarta Bay shore, where BPBD warns of rob (tidal floods).
COASTAL = {"penjaringan", "pademangan", "tanjungpriok", "koja", "cilincing"}
_WIB = pd.Timedelta(hours=7)


# ---------------------------------------------------------------- data

def kecamatan_days() -> pd.DataFrame:
    data = build_dataset("imerg").sort_values(["kecamatan", "date"]).reset_index(drop=True)
    by_kec = data.groupby("kecamatan")["d0"]
    data["d7prev"] = by_kec.transform(lambda s: s.shift(1).rolling(7, min_periods=1).sum())
    # Antecedent precipitation index, decay 0.85 a day: sum over earlier days of 0.85^(i-1) * rain.
    data["api14"] = by_kec.transform(lambda s: s.shift(1).fillna(0.0).ewm(alpha=0.15, adjust=False).mean() / 0.15)
    cleaned = pd.read_csv(PROCESSED_DATA_DIR / "cleaned_flood_data_jakarta.csv")
    static = cleaned.groupby(cleaned["name_3"].map(_slug))[["elevation", "slope"]].mean()
    data = data.join(static, on="kecamatan")
    return add_drivers(data)


def _hourly_json(path: Path, key: str) -> pd.Series:
    raw = json.loads(path.read_text(encoding="utf-8"))
    s = pd.Series(raw[key], index=pd.to_datetime(raw["time"]) + _WIB, dtype=float)  # GMT -> naive WIB
    return s


def add_drivers(data: pd.DataFrame) -> pd.DataFrame:
    """Drivers named in the literature (see scripts/fetch_flood_drivers.py for sources)."""
    from scripts.fetch_imerg_history import build_points

    points = build_points()
    # Soil moisture of the previous WIB day (the day's own value already contains its rain).
    soil = {}
    for cell in sorted(set(points.values())):
        path = DRIVERS_DIR / f"soil_{cell}.json"
        daily = pd.DataFrame({k: _hourly_json(path, f"soil_moisture_{k}").resample("1D").mean()
                              for k in ("0_to_7cm", "7_to_28cm")}).shift(1)
        soil[cell] = daily
    soil_rows = pd.concat([soil[points[k]].assign(kecamatan=k) for k in data["kecamatan"].unique()])
    soil_rows = soil_rows.rename(columns={"0_to_7cm": "soil07_prev", "7_to_28cm": "soil728_prev"})
    soil_rows = soil_rows.rename_axis("date").reset_index()
    data = data.merge(soil_rows, on=["kecamatan", "date"], how="left")

    # MJO (OMI): the phase plane is (PC2, -PC1), the counterpart of RMM1/RMM2.
    omi = pd.read_csv(DRIVERS_DIR / "omi.1x.txt", sep=r"\s+", header=None, names=["y", "m", "d", "pc1", "pc2", "amp"])
    omi["date"] = pd.to_datetime(dict(year=omi["y"], month=omi["m"], day=omi["d"]))
    omi = omi.assign(mjo_x=omi["pc2"], mjo_y=-omi["pc1"], mjo_amp=omi["amp"])[["date", "mjo_x", "mjo_y", "mjo_amp"]]
    data = data.merge(omi, on="date", how="left")

    # ENSO: ONI anomaly of the 3-month season centred on the month (DJF -> January).
    oni = pd.read_csv(DRIVERS_DIR / "oni.ascii.txt", sep=r"\s+")
    seasons = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
    oni["month"] = oni["SEAS"].map({s: i + 1 for i, s in enumerate(seasons)})
    oni_map = {(int(y), int(m)): float(a) for y, m, a in zip(oni["YR"], oni["month"], oni["ANOM"])}
    data["oni"] = [oni_map.get((d.year, d.month), np.nan) for d in data["date"]]

    # Northerly surge proxy: mean wind component from the north at two sea points, per WIB day.
    north = []
    for name in ("karimata", "javasea"):
        path = DRIVERS_DIR / f"wind_{name}.json"
        speed, direction = _hourly_json(path, "wind_speed_10m"), _hourly_json(path, "wind_direction_10m")
        north.append((speed * np.cos(np.deg2rad(direction))).resample("1D").mean())  # + = wind from the north
    north = pd.concat(north, axis=1).mean(axis=1)
    data["north_wind"] = data["date"].map(north)
    data["north_wind_d1"] = data["date"].map(north.shift(1))

    # Spring tides come near new and full moon: 1 at syzygy, -1 at quarter moon (synodic month 29.53 d,
    # new moon 2000-01-06 18:14 UTC). A proxy for the tidal range; perigee is not modelled.
    age = ((data["date"] + pd.Timedelta(hours=12) - _WIB) - pd.Timestamp("2000-01-06 18:14")).dt.total_seconds() / 86400
    data["spring_tide"] = np.cos(4 * np.pi * (age % 29.530588) / 29.530588)
    data["coastal"] = data["kecamatan"].isin(COASTAL).astype(float)
    data["coastal_spring_tide"] = data["coastal"] * data["spring_tide"]
    return data


def split(data: pd.DataFrame):
    return (data[data["year"] <= TRAIN_END], data[data["year"] == VAL_YEAR], data[data["year"] > VAL_YEAR])


# ---------------------------------------------------------------- models

def _ratio(y) -> float:
    return float((y == 0).sum()) / max(int(y.sum()), 1)


def make_model(kind: str, y: np.ndarray, params: dict | None = None, device: str = "cuda"):
    if kind == "logistic":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             LogisticRegression(max_iter=3000, class_weight="balanced"))
    if kind == "random_forest":
        return make_pipeline(SimpleImputer(strategy="median"),
                             RandomForestClassifier(n_estimators=500, min_samples_leaf=20, n_jobs=-1,
                                                    class_weight="balanced_subsample", random_state=SEED))
    if kind == "mlp":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             MLPClassifier(hidden_layer_sizes=(64, 32), alpha=1e-3, early_stopping=True,
                                           max_iter=400, random_state=SEED))
    base = dict(n_estimators=400, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                scale_pos_weight=_ratio(y), eval_metric="aucpr", tree_method="hist", device=device,
                random_state=SEED)
    base.update(params or {})
    return XGBClassifier(**base)


def fit_predict(kind, train, others, features, params=None, device="cuda"):
    y = train["flood"].to_numpy()
    model = make_model(kind, y, params, device).fit(train[features], y)
    return [model.predict_proba(o[features])[:, 1] for o in others]


def tune_xgboost(train, val, features, trials: int, device: str) -> tuple[dict, list]:
    rng = np.random.default_rng(SEED)
    ratio = _ratio(train["flood"].to_numpy())
    y_val = val["flood"].to_numpy()
    history = []
    for i in range(trials):
        params = {
            "max_depth": int(rng.integers(2, 9)),
            "learning_rate": float(10 ** rng.uniform(-2, -0.7)),
            "n_estimators": int(rng.integers(200, 1501)),
            "min_child_weight": float(rng.uniform(1, 20)),
            "subsample": float(rng.uniform(0.5, 1.0)),
            "colsample_bytree": float(rng.uniform(0.4, 1.0)),
            "gamma": float(rng.uniform(0, 5)),
            "reg_lambda": float(10 ** rng.uniform(-1, 1)),
            "scale_pos_weight": float(ratio * rng.choice([0.25, 0.5, 1.0])),
        }
        (p,) = fit_predict("xgboost", train, [val], features, params, device)
        history.append({"trial": i, "val_pr_auc": round(float(average_precision_score(y_val, p)), 4), **params})
    best = max(history, key=lambda h: h["val_pr_auc"])
    return {k: v for k, v in best.items() if k not in ("trial", "val_pr_auc")}, history


# ---------------------------------------------------------------- metrics

class DateBootstrap:
    """Resample whole test dates (rows of one day move together)."""

    def __init__(self, dates: np.ndarray, n: int):
        rng = np.random.default_rng(SEED)
        unique, inverse = np.unique(dates, return_inverse=True)
        self.index = [np.flatnonzero(inverse == i) for i in range(len(unique))]
        self.choices = [rng.integers(0, len(unique), len(unique)) for _ in range(n)]

    @property
    def samples(self):
        for choice in self.choices:  # rows built per resample, so memory stays small
            yield np.concatenate([self.index[i] for i in choice])

    def ci(self, stat, y, p):
        vals = [stat(y[s], p[s]) for s in self.samples if y[s].min() != y[s].max()]
        lo, hi = np.percentile(vals, [2.5, 97.5])
        return [round(float(stat(y, p)), 3), round(float(lo), 3), round(float(hi), 3)]

    def diff(self, y, p_a, p_b):
        out = {}
        for name, stat in (("roc_auc", roc_auc_score), ("pr_auc", average_precision_score)):
            vals = [stat(y[s], p_b[s]) - stat(y[s], p_a[s]) for s in self.samples if y[s].min() != y[s].max()]
            out[name] = [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]
        return out


def scores(y, p, boot: DateBootstrap) -> dict:
    return {"roc_auc": boot.ci(roc_auc_score, y, p), "pr_auc": boot.ci(average_precision_score, y, p)}


def at_threshold(y, p, t, n_kec_months) -> dict:
    pred = p >= t
    tp, fp, pos = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((y == 1).sum())
    return {"threshold": round(float(t), 4), "recall": round(tp / pos, 3) if pos else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "alarms": tp + fp, "missed": pos - tp,
            "alarms_per_kecamatan_month": round((tp + fp) / n_kec_months, 2)}


def thresholds_on_validation(y_val, p_val) -> dict[str, float]:
    rules = {}
    for budget in (0.5, 1, 2, 4):
        rules[f"budget {budget} alarm(s) per kecamatan per month"] = float(np.quantile(p_val, 1 - budget / DAYS_PER_MONTH))
    prec, rec, thr = precision_recall_curve(y_val, p_val)
    prec, rec = prec[:-1], rec[:-1]
    f1 = 2 * prec * rec / (prec + rec + 1e-12)
    rules["best F1 on 2022"] = float(thr[np.argmax(f1)])
    ok = prec >= 0.30
    if ok.any():
        rules["highest recall with precision >= 0.30 on 2022"] = float(thr[ok][np.argmax(rec[ok])])
    return rules


# ---------------------------------------------------------------- Exp 3 data

def daily_water_levels() -> pd.DataFrame:
    text = TMA_XLS.read_text(encoding="utf-8", errors="replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)
    cells = lambda r: [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()  # noqa: E731
                       for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)]
    frame = pd.DataFrame([cells(r) for r in rows[1:]], columns=cells(rows[0]))
    frame["date"] = pd.to_datetime(dict(year=frame["periode_data"].astype(int), month=frame["bulan"].astype(int),
                                        day=frame["tanggal"].astype(int)))
    frame["tma"] = pd.to_numeric(frame["tma"], errors="coerce")
    # A reading of exactly 0 cm is a missing value at every post but Katulampa (a weir that can run dry).
    frame.loc[(frame["tma"] == 0) & (frame["nama_objek"] != "BENDUNG KATULAMPA"), "tma"] = np.nan
    return frame


def siaga_level(tma: float, st: dict) -> int:
    if pd.isna(tma):
        return 0
    if tma >= st["siaga1"]:
        return 3
    if tma >= st["siaga2"]:
        return 2
    if tma >= st["siaga3"]:
        return 1
    return 0


def rules_by_day(tma: pd.DataFrame) -> tuple[pd.Series, dict]:
    feed = {p["name"]: p for p in json.loads(SIAGA_JSON.read_text(encoding="utf-8"))["posts"]}
    matched = {p: feed[TMA_TO_FEED[p]] for p in tma["nama_objek"].unique() if TMA_TO_FEED.get(p) in feed}
    rows = tma[tma["nama_objek"].isin(matched)].copy()
    rows["level"] = [siaga_level(t, matched[p]) for t, p in zip(rows["tma"], rows["nama_objek"])]
    info = {"posts_in_file": int(tma["nama_objek"].nunique()), "posts_with_siaga_bands": sorted(matched),
            "posts_without_bands": sorted(set(tma["nama_objek"]) - set(matched)),
            "missing_readings": int(rows["tma"].isna().sum())}
    return rows[["date", "nama_objek", "level"]], info


def jakarta_flood_days(start: str, end: str) -> pd.Series:
    """RW records per date anywhere in Jakarta (all kecamatan), from the BPBD rekap."""
    rekap = pd.read_csv(REKAP_CSV).drop_duplicates()
    counts: dict[pd.Timestamp, int] = {}
    for y, m, text in zip(rekap["tahun"], rekap["bulan"], rekap["tanggal_kejadian"]):
        for d in _dates_in(text, int(y), int(m)):
            counts[d] = counts.get(d, 0) + 1
    days = pd.date_range(start, end, freq="D")
    return pd.Series([counts.get(d, 0) for d in days], index=days)


def day_metrics(warn: pd.Series, flood: pd.Series) -> dict:
    w, f = warn.to_numpy(bool), flood.to_numpy(bool)
    w_prev = np.r_[False, w[:-1]]  # warned the day before
    tp, fp = int((w & f).sum()), int((w & ~f).sum())
    return {"warning_days": int(w.sum()), "flood_days": int(f.sum()), "caught_same_day": tp,
            "recall": round(tp / f.sum(), 3) if f.sum() else None,
            "recall_same_or_day_before": round(float(((w | w_prev) & f).sum() / f.sum()), 3) if f.sum() else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None, "false_alarm_days": fp}


def _boot_days(warn_a, warn_b, flood, n):
    """95 % interval of (b - a) recall and precision, resampling days."""
    rng = np.random.default_rng(SEED)
    a, b, f = (np.asarray(x, bool) for x in (warn_a, warn_b, flood))
    rec, prec = [], []
    for _ in range(n):
        s = rng.integers(0, len(f), len(f))
        if f[s].sum() == 0:
            continue
        rec.append((b[s] & f[s]).sum() / f[s].sum() - (a[s] & f[s]).sum() / f[s].sum())
        if b[s].sum() and a[s].sum():
            prec.append((b[s] & f[s]).sum() / b[s].sum() - (a[s] & f[s]).sum() / a[s].sum())
    q = lambda v: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)]  # noqa: E731
    return {"recall_difference": q(rec), "precision_difference": q(prec)}


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=200, help="XGBoost random-search trials (GPU)")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    device = "cpu" if args.cpu else "cuda"
    started = time.time()
    sys.stdout.reconfigure(encoding="utf-8")
    # The GPU booster predicting on CPU pandas data warns once per call; the result is the same.
    import warnings
    warnings.filterwarnings("ignore", message=".*mismatched devices.*")

    data = kecamatan_days()
    train, val, test = split(data)
    y_tr, y_val, y_te = (d["flood"].to_numpy() for d in (train, val, test))
    test_dates = test["date"].to_numpy()
    boot = DateBootstrap(test_dates, args.bootstrap)
    n_kec_months = test["kecamatan"].nunique() * len(test["date"].dt.to_period("M").unique())
    res: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "device": device,
        "rows": {"train": len(train), "validate": len(val), "test": len(test)},
        "floods": {"train": int(y_tr.sum()), "validate": int(y_val.sum()), "test": int(y_te.sum())},
        "prevalence_test": round(float(y_te.mean()), 4),
        "missing_static": int(data["elevation"].isna().sum()),
    }
    print(f"rows {res['rows']} floods {res['floods']}", flush=True)

    # ---------------- Exp 1a: feature sets with XGBoost (default settings)
    res["exp1_feature_sets"] = {}
    for name, feats in FEATURE_SETS.items():
        p_val, p_te = fit_predict("xgboost", train, [val, test], feats, device=device)
        res["exp1_feature_sets"][name] = {"validation_pr_auc": round(float(average_precision_score(y_val, p_val)), 3),
                                          **scores(y_te, p_te, boot)}
        print(name, res["exp1_feature_sets"][name], flush=True)
    best_set = max(res["exp1_feature_sets"], key=lambda k: res["exp1_feature_sets"][k]["validation_pr_auc"])
    feats = FEATURE_SETS[best_set]
    res["best_feature_set"] = best_set

    # ---------------- Exp 1b: model families on the best feature set
    preds_val, preds_te = {}, {}
    preds_te["baseline: rain that day (d0)"] = test["d0"].to_numpy()
    preds_val["baseline: rain that day (d0)"] = val["d0"].to_numpy()
    preds_val["baseline: climatology"], preds_te["baseline: climatology"] = fit_predict(
        "logistic", train, [val, test], ["hist_rate", "month_sin", "month_cos"])
    for kind in ("logistic", "random_forest", "mlp", "xgboost"):
        preds_val[kind], preds_te[kind] = fit_predict(kind, train, [val, test], feats, device=device)
        print(kind, "done", flush=True)
    t0 = time.time()
    best_params, history = tune_xgboost(train, val, feats, args.trials, device)
    tune_seconds = round(time.time() - t0, 1)
    preds_val["xgboost_tuned"], preds_te["xgboost_tuned"] = fit_predict(
        "xgboost", train, [val, test], feats, best_params, device)
    res["exp1_tuning"] = {"trials": args.trials, "seconds": tune_seconds, "best_params": best_params,
                          "best_val_pr_auc": max(h["val_pr_auc"] for h in history)}
    res["exp1_models"] = {}
    for name in preds_te:
        res["exp1_models"][name] = {"validation_pr_auc": round(float(average_precision_score(y_val, preds_val[name])), 3),
                                    **scores(y_te, preds_te[name], boot)}
    chosen = max(("logistic", "random_forest", "mlp", "xgboost", "xgboost_tuned"),
                 key=lambda k: res["exp1_models"][k]["validation_pr_auc"])
    res["chosen_model"] = chosen
    res["exp1_paired"] = {
        f"{chosen} minus {other}": boot.diff(y_te, preds_te[other], preds_te[chosen])
        for other in preds_te if other != chosen
    }
    print("chosen", chosen, flush=True)

    # ---------------- Exp 2: thresholds chosen on 2022, scored on the test years
    rules = thresholds_on_validation(y_val, preds_val[chosen])
    res["exp2_model_thresholds"] = {name: at_threshold(y_te, preds_te[chosen], t, n_kec_months) for name, t in rules.items()}
    res["exp2_rain_rules"] = {f"rain that day >= {mm} mm (BMKG {'heavy' if mm == 50 else 'very heavy'})":
                              at_threshold(y_te, test["d0"].to_numpy(), mm, n_kec_months) for mm in (50, 100)}
    # Equal alarm volume: the rain threshold that raises as many alarms as the model's 1-per-month budget.
    budget_key = "budget 1 alarm(s) per kecamatan per month"
    n_alarms = res["exp2_model_thresholds"][budget_key]["alarms"]
    rain_t = float(np.sort(test["d0"].to_numpy())[::-1][max(n_alarms - 1, 0)])
    res["exp2_rain_equal_volume"] = at_threshold(y_te, test["d0"].to_numpy(), rain_t, n_kec_months)

    # ---------------- Exp 3: rules vs model vs hybrid, Jakarta-days Jan-Sep 2025
    tma = daily_water_levels()
    post_levels, tma_info = rules_by_day(tma)
    days = pd.date_range(EXP3_START, EXP3_END, freq="D")
    post_levels = post_levels[(post_levels["date"] >= EXP3_START) & (post_levels["date"] <= EXP3_END)]
    # A post at Siaga 3 or above on more than half of the days carries no warning information
    # (the coastal posts follow the tide); the main rule variant leaves those posts out.
    on_share = post_levels.assign(on=post_levels["level"] >= 1).groupby("nama_objek")["on"].mean()
    always_on = sorted(on_share[on_share > 0.5].index)
    tma_info["always_on_posts"] = {p: round(float(on_share[p]), 2) for p in always_on}
    city_level = lambda rows: rows.groupby("date")["level"].max().reindex(days).fillna(0).astype(int)  # noqa: E731
    rule_all = city_level(post_levels)
    rule_level = city_level(post_levels[~post_levels["nama_objek"].isin(always_on)])
    window = test[(test["date"] >= EXP3_START) & (test["date"] <= EXP3_END)]
    city_p = pd.Series(preds_te[chosen], index=test.index).loc[window.index].groupby(window["date"]).max().reindex(days)
    val_city = pd.Series(preds_val[chosen], index=val.index).groupby(val["date"]).max()
    # City thresholds chosen on 2022 days: Watch on 8, Alert on 4, Danger on 2 days a month.
    city_t = {lvl: float(np.quantile(val_city, 1 - n / DAYS_PER_MONTH)) for lvl, n in ((1, 8), (2, 4), (3, 2))}
    model_level = pd.Series(0, index=days)
    for lvl in (1, 2, 3):
        model_level[city_p >= city_t[lvl]] = lvl
    hybrid_level = np.maximum(rule_level, model_level)
    records = jakarta_flood_days(EXP3_START, EXP3_END)
    labels = {"any BPBD flood record": records >= 1, "large flood (>= 10 RW records)": records >= 10}
    res["exp3"] = {"period": f"{EXP3_START} to {EXP3_END}", "water_level_file": tma_info,
                   "city_model_thresholds": {str(k): round(v, 4) for k, v in city_t.items()},
                   "results": {}}
    approaches = (("rules, all 15 posts", rule_all), ("rules", rule_level), ("model", model_level), ("hybrid", hybrid_level))
    res["exp3"]["level_days"] = {name: {str(l): int((lv == l).sum()) for l in range(4)} for name, lv in approaches}
    for lab_name, flood in labels.items():
        for lvl, lvl_name in ((1, ">= Watch"), (2, ">= Alert"), (3, "Danger")):
            warn = {name: lv >= lvl for name, lv in approaches}
            entry = {name: day_metrics(w, flood) for name, w in warn.items()}
            entry["hybrid minus rules"] = _boot_days(warn["rules"], warn["hybrid"], flood, args.bootstrap)
            res["exp3"]["results"][f"{lab_name} | {lvl_name}"] = entry
    # Same number of warning days as the rules (>= Watch), for a like-for-like comparison.
    n_rule = int((rule_level >= 1).sum())
    if n_rule:
        t_eq = float(np.sort(city_p.to_numpy())[::-1][n_rule - 1])
        for lab_name, flood in labels.items():
            res["exp3"]["results"][f"{lab_name} | model with as many warning days as the rules"] = {
                "model": day_metrics(city_p >= t_eq, flood), "rules": day_metrics(rule_level >= 1, flood)}

    res["seconds"] = round(time.time() - started, 1)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "thesis_experiments.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    (REPORTS_DIR / "thesis_experiments.md").write_text(markdown(res), encoding="utf-8")
    print(markdown(res))
    return 0


def _ci(v):
    return f"{v[0]} [{v[1]}–{v[2]}]"


def markdown(r: dict) -> str:
    L = ["# Thesis experiments", "",
         f"Generated {r['generated_at']} by `scripts/thesis_experiments.py` on {r['device']}. Nothing here is served.", "",
         "Rows: kecamatan-days of the 42 model kecamatan, IMERG rain, BPBD flood dates. Train 2020–2021, "
         "validate 2022, test 2023 to Sep 2025 (BPBD dates are only partly readable after 2022, so test precision "
         "is a lower bound).", "",
         f"Rows train / validate / test: {r['rows']['train']} / {r['rows']['validate']} / {r['rows']['test']}; "
         f"flood rows {r['floods']['train']} / {r['floods']['validate']} / {r['floods']['test']} "
         f"(test prevalence {r['prevalence_test']}, the no-skill PR-AUC).", "",
         "## Exp 1a · Feature sets (XGBoost, default settings)", "",
         "| Features | PR-AUC on 2022 | Test ROC-AUC [95 %] | Test PR-AUC [95 %] |", "|---|---|---|---|"]
    for name, s in r["exp1_feature_sets"].items():
        L.append(f"| {name} | {s['validation_pr_auc']} | {_ci(s['roc_auc'])} | {_ci(s['pr_auc'])} |")
    L += ["", f"Best on 2022: **{r['best_feature_set']}**.", "",
          "## Exp 1b · Models on that feature set", "",
          "| Model | PR-AUC on 2022 | Test ROC-AUC [95 %] | Test PR-AUC [95 %] |", "|---|---|---|---|"]
    for name, s in r["exp1_models"].items():
        L.append(f"| {name} | {s['validation_pr_auc']} | {_ci(s['roc_auc'])} | {_ci(s['pr_auc'])} |")
    t = r["exp1_tuning"]
    L += ["", f"Tuned XGBoost: {t['trials']} random-search trials in {t['seconds']} s, best PR-AUC on 2022 "
          f"{t['best_val_pr_auc']}. Chosen model (best PR-AUC on 2022): **{r['chosen_model']}**.", "",
          "Paired differences on the test years (95 %, bootstrap over dates):", "",
          "| Comparison | ROC-AUC difference | PR-AUC difference |", "|---|---|---|"]
    for name, d in r["exp1_paired"].items():
        L.append(f"| {name} | {d['roc_auc']} | {d['pr_auc']} |")
    L += ["", "## Exp 2 · Warning thresholds (chosen on 2022, scored on the test years)", "",
          "| Rule | Threshold | Recall | Precision | Alarms | Alarms per kecamatan-month | Missed floods |",
          "|---|---|---|---|---|---|---|"]
    rows = {**{f"model: {k}": v for k, v in r["exp2_model_thresholds"].items()},
            **{f"rain: {k}": v for k, v in r["exp2_rain_rules"].items()},
            "rain: same number of alarms as the model's 1-per-month budget": r["exp2_rain_equal_volume"]}
    for name, s in rows.items():
        L.append(f"| {name} | {s['threshold']} | {s['recall']} | {s['precision']} | {s['alarms']} | "
                 f"{s['alarms_per_kecamatan_month']} | {s['missed']} |")
    e = r["exp3"]
    w = e["water_level_file"]
    L += ["", f"## Exp 3 · Rules vs model vs hybrid, Jakarta-days {e['period']}", "",
          f"Water levels: {len(w['posts_with_siaga_bands'])} of {w['posts_in_file']} posts have DSDA Siaga bands "
          f"(without: {', '.join(w['posts_without_bands']) or 'none'}); {w['missing_readings']} missing readings. "
          "One reading a day; the file does not say at what time.", "",
          "Posts at Siaga 3 or above on more than half of the days (left out of \"rules\", kept in \"rules, all 15 "
          "posts\"): " + ", ".join(f"{p} ({int(s * 100)} %)" for p, s in w["always_on_posts"].items()) + ". "
          "\"rules\" = the highest Siaga level of the other posts; \"hybrid\" = the higher of \"rules\" and the model.", "",
          "Days at each level (0 Safe, 1 Watch, 2 Alert, 3 Danger): " +
          "; ".join(f"{k} {v}" for k, v in e["level_days"].items()), "",
          "| Label · warning level | Approach | Warning days | Flood days | Recall | Recall incl. day before | Precision | False-alarm days |",
          "|---|---|---|---|---|---|---|---|"]
    for key, entry in e["results"].items():
        for name in ("rules, all 15 posts", "rules", "model", "hybrid"):
            if name in entry:
                m = entry[name]
                L.append(f"| {key} | {name} | {m['warning_days']} | {m['flood_days']} | {m['recall']} | "
                         f"{m['recall_same_or_day_before']} | {m['precision']} | {m['false_alarm_days']} |")
        if "hybrid minus rules" in entry:
            d = entry["hybrid minus rules"]
            L.append(f"| {key} | hybrid − rules, 95 % | | | {d['recall_difference']} | | {d['precision_difference']} | |")
    L += ["", f"Run time {r['seconds']} s."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
