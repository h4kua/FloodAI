#!/usr/bin/env python
"""
Does hourly rain intensity predict flood days better than daily rain totals?
(exploratory; nothing here is served)

Rows: one kecamatan (the 42 model kecamatan) on one day, 2020-01-01 to 2025-09-30 (WIB).
Label: BPBD recorded a flood in that kecamatan on that date (data/raw/rekap_kejadian_2020_2025.csv,
dates read as in scripts/daily_flood_experiment.py). Dates are complete for 2020-2022 and only partly
readable for 2023-2025, so later labels miss some floods and their precision is a lower bound.

Rain, per kecamatan from its 0.1-degree cell (see scripts/fetch_imerg_history.py):
  --source imerg      GPM IMERG Final half-hourly (satellite + gauges), cached by fetch_imerg_history.py
  --source openmeteo  ERA5 hourly reanalysis from the Open-Meteo archive (no key; about 25 km, it
                      smooths local downpours), cached in data/raw/openmeteo_hourly/
Feature sets:
  daily   = rain that day, the day before, the 3 days before; upstream (Bogor, Depok) daily rain;
            month; the kecamatan's flood-day rate in earlier years (2013 onward, leak-free)
  hourly  = daily + wettest 1 h / 3 h / 6 h, hours with >= 10 mm, upstream wettest 3 h
Splits: train 2020-2021, test 2022 (complete dates); train 2020-2022, test 2023 to Sep 2025.
The hourly-minus-daily difference has a 95 % interval from a bootstrap over test dates.
Outputs artifacts/reports/hourly_rain_experiment_<source>.{json,md}.

Usage (repo root):  python scripts/hourly_rain_experiment.py --source openmeteo|imerg
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from scripts.build_kelurahan_flood_history import _CANONICAL_BY_SLUG, _slug  # noqa: E402
from scripts.fetch_imerg_history import OUT_DIR as IMERG_DIR, build_points, parse_timeseries  # noqa: E402
from utils.paths import REPORTS_DIR  # noqa: E402

REKAP_CSV = _PROJECT_ROOT / "data" / "raw" / "rekap_kejadian_2020_2025.csv"
EVENTS_CSV = _PROJECT_ROOT / "data" / "processed" / "events_clean.csv"
OPENMETEO_DIR = _PROJECT_ROOT / "data" / "raw" / "openmeteo_hourly"
START, END = "2020-01-01", "2025-09-30"
FETCH_START = "2019-12-01"  # a month before START, so 1 Jan 2020 has its previous days
WIB = pd.Timedelta(hours=7)
_MONTHS = "januari februari maret april mei juni juli agustus september oktober november desember".split()
_SEED = 42
_BOOT = 300

DAILY_FEATURES = ["d0", "d1", "d3prev", "up_bogor_d0", "up_bogor_d1", "up_depok_d0",
                  "month_sin", "month_cos", "hist_rate"]
HOURLY_FEATURES = DAILY_FEATURES + ["max1h", "max3h", "max6h", "hours10", "up_bogor_max3h", "up_depok_max3h"]


# ---------------------------------------------------------------- labels

def _dates_in(text: str, year: int, month: int) -> list[pd.Timestamp]:
    """Day numbers written before the month name, e.g. "17, 29, 30 Oktober" or "4-6 Desember"."""
    if not isinstance(text, str):
        return []
    text = re.split(rf"(?i)\b(?:{'|'.join(_MONTHS)})\b", text)[0]
    text = re.sub(r"(?i)tgl\.?|tanggal", "", text)
    days = []
    for a, b in re.findall(r"(\d{1,2})\s*(?:[-–]|s\.?d\.?)?\s*(\d{1,2})?", text):
        first, last = int(a), int(b) if b else int(a)
        if 1 <= first <= last <= 31 and last - first <= 10:
            for day in range(first, last + 1):
                try:
                    days.append(pd.Timestamp(year=year, month=month, day=day))
                except ValueError:
                    pass
    return days


def flood_kecamatan_days() -> pd.DataFrame:
    """(kecamatan, date) pairs with a BPBD flood, 2013 onward, for the 42 model kecamatan."""
    rows = []
    rekap = pd.read_csv(REKAP_CSV).drop_duplicates()
    for kec, year, month, text in zip(rekap["kecamatan"], rekap["tahun"], rekap["bulan"], rekap["tanggal_kejadian"]):
        slug = _slug(str(kec))
        if slug in _CANONICAL_BY_SLUG:
            rows += [(slug, d) for d in _dates_in(text, int(year), int(month))]
    events = pd.read_csv(EVENTS_CSV, usecols=["event_date", "kecamatan"])
    events = events[pd.to_datetime(events["event_date"]).dt.year < 2020]  # rekap covers 2020 onward
    for kec, date in zip(events["kecamatan"], pd.to_datetime(events["event_date"])):
        slug = _slug(str(kec))
        if slug in _CANONICAL_BY_SLUG:
            rows.append((slug, date.normalize()))
    return pd.DataFrame(rows, columns=["kecamatan", "date"]).drop_duplicates()


def history_rate(floods: pd.DataFrame, kecamatan: list[str], years: range) -> pd.DataFrame:
    """Share of days with a flood in each kecamatan over 2013..year-1 (leak-free)."""
    per_year = floods.assign(year=floods["date"].dt.year).groupby(["kecamatan", "year"]).size()
    out = []
    for year in years:
        n_days = (pd.Timestamp(year=year, month=1, day=1) - pd.Timestamp("2013-01-01")).days
        for kec in kecamatan:
            past = per_year.loc[kec] if kec in per_year.index.get_level_values(0) else pd.Series(dtype=float)
            out.append((kec, year, float(past[past.index < year].sum()) / n_days))
    return pd.DataFrame(out, columns=["kecamatan", "year", "hist_rate"])


# ---------------------------------------------------------------- rain

def _openmeteo_series(cell: str) -> pd.Series:
    OPENMETEO_DIR.mkdir(parents=True, exist_ok=True)
    cache = OPENMETEO_DIR / f"{cell}_{FETCH_START}.json"
    if not cache.exists():
        lat, lon = cell.split("_")
        query = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": FETCH_START, "end_date": END,
                                        "hourly": "precipitation", "models": "era5", "timezone": "GMT"})
        with urllib.request.urlopen(f"https://archive-api.open-meteo.com/v1/archive?{query}", timeout=120) as resp:
            cache.write_text(json.dumps(json.load(resp)["hourly"]), encoding="utf-8")
    hourly = json.loads(cache.read_text(encoding="utf-8"))
    return pd.Series(hourly["precipitation"], index=pd.to_datetime(hourly["time"], utc=True), dtype=float)


def _imerg_series(cell: str) -> pd.Series:
    files = sorted(IMERG_DIR.glob(f"{cell}_*.csv"))
    if not files:
        raise SystemExit(f"No IMERG data for {cell}; run scripts/fetch_imerg_history.py first.")
    rate = pd.concat(parse_timeseries(f.read_text(encoding="utf-8")) for f in files)
    depth = rate * 0.5  # mm/h over a half hour -> mm
    return depth.resample("1h").sum(min_count=1)


def daily_rain_features(hourly_mm: pd.Series) -> pd.DataFrame:
    """Hourly rain depth (UTC) -> one row per WIB day."""
    local = hourly_mm.copy()
    local.index = local.index.tz_convert(None) + WIB  # naive WIB
    local = local.fillna(0.0)
    day = local.index.floor("D")
    frame = pd.DataFrame({
        "d0": local.groupby(day).sum(),
        "max1h": local.groupby(day).max(),
        "max3h": local.rolling(3, min_periods=1).sum().groupby(day).max(),
        "max6h": local.rolling(6, min_periods=1).sum().groupby(day).max(),
        "hours10": (local >= 10).groupby(day).sum().astype(float),
    })
    frame["d1"] = frame["d0"].shift(1)
    frame["d3prev"] = frame["d0"].shift(1).rolling(3, min_periods=1).sum()
    return frame


def build_dataset(source: str) -> pd.DataFrame:
    points = build_points()
    get = _imerg_series if source == "imerg" else _openmeteo_series
    by_cell = {cell: daily_rain_features(get(cell)) for cell in sorted(set(points.values()))}
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
    data = data.merge(history_rate(floods, kecamatan, range(2020, 2026)), on=["kecamatan", "year"], how="left")
    data["month_sin"] = np.sin(2 * np.pi * data["date"].dt.month / 12)
    data["month_cos"] = np.cos(2 * np.pi * data["date"].dt.month / 12)
    return data.dropna(subset=["d1", "up_bogor_d1"])


# ---------------------------------------------------------------- models

def _model(kind: str, y: np.ndarray):
    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
    ratio = float((y == 0).sum()) / max(int(y.sum()), 1)
    return XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                         scale_pos_weight=ratio, random_state=_SEED, eval_metric="logloss")


def _precision_at_recall(y, p, target):
    prec, rec, _ = precision_recall_curve(y, p)
    ok = rec >= target
    return round(float(prec[ok].max()), 3) if ok.any() else None


def _paired_bootstrap(dates, y, p_a, p_b):
    """95 % interval of (b - a) for ROC-AUC and PR-AUC, resampling whole test dates."""
    rng = np.random.default_rng(_SEED)
    unique = np.unique(dates)
    index = {d: np.flatnonzero(dates == d) for d in unique}
    diffs = {"roc_auc": [], "pr_auc": []}
    for _ in range(_BOOT):
        rows = np.concatenate([index[d] for d in rng.choice(unique, len(unique))])
        if y[rows].min() == y[rows].max():
            continue
        diffs["roc_auc"].append(roc_auc_score(y[rows], p_b[rows]) - roc_auc_score(y[rows], p_a[rows]))
        diffs["pr_auc"].append(average_precision_score(y[rows], p_b[rows]) - average_precision_score(y[rows], p_a[rows]))
    return {k: [round(float(np.percentile(v, 2.5)), 3), round(float(np.percentile(v, 97.5)), 3)] for k, v in diffs.items()}


def run(data: pd.DataFrame) -> list[dict]:
    splits = {"train 2020–2021, test 2022 (complete dates)": (2022, 2022),
              "train 2020–2022, test 2023–Sep 2025 (partial dates)": (2023, 2025)}
    runs = []
    for split, (first, last) in splits.items():
        train = data[data["year"] < first]
        test = data[(data["year"] >= first) & (data["year"] <= last)]
        y_tr, y_te = train["flood"].to_numpy(), test["flood"].to_numpy()
        dates = test["date"].to_numpy()
        for kind in ("logistic", "xgboost"):
            probs = {}
            for name, cols in (("daily", DAILY_FEATURES), ("hourly", HOURLY_FEATURES)):
                model = _model(kind, y_tr).fit(train[cols].fillna(0.0), y_tr)
                p = model.predict_proba(test[cols].fillna(0.0))[:, 1]
                probs[name] = p
                runs.append({"split": split, "model": kind, "features": name,
                             "test_rows": int(len(test)), "test_floods": int(y_te.sum()),
                             "prevalence": round(float(y_te.mean()), 4),
                             "roc_auc": round(float(roc_auc_score(y_te, p)), 3),
                             "pr_auc": round(float(average_precision_score(y_te, p)), 3),
                             "precision_at_recall_50": _precision_at_recall(y_te, p, 0.5)})
            runs[-1]["hourly_minus_daily_95ci"] = _paired_bootstrap(dates, y_te, probs["daily"], probs["hourly"])
        runs.append({"split": split, "model": "rain alone", "features": "d0 vs max3h",
                     "roc_auc_d0": round(float(roc_auc_score(y_te, test["d0"].fillna(0))), 3),
                     "roc_auc_max3h": round(float(roc_auc_score(y_te, test["max3h"].fillna(0))), 3)})
    return runs


def _rain_check(data: pd.DataFrame) -> dict:
    """Wettest kecamatan-day on the record storm (BMKG Halim measured 377 mm on 1 Jan 2020)."""
    day = data[data["date"] == pd.Timestamp("2020-01-01")]
    return {"max_d0_mm": round(float(day["d0"].max()), 1), "max_1h_mm": round(float(day["max1h"].max()), 1)}


def main() -> int:
    parser = argparse.ArgumentParser(description="hourly vs daily rain flood-day experiment")
    parser.add_argument("--source", choices=("imerg", "openmeteo"), required=True)
    args = parser.parse_args()
    data = build_dataset(args.source)
    results = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": args.source,
               "rows": int(len(data)), "flood_rows": int(data["flood"].sum()),
               "floods_per_year": {int(y): int(g.sum()) for y, g in data.groupby("year")["flood"]},
               "record_storm_check": _rain_check(data), "runs": run(data)}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"hourly_rain_experiment_{args.source}"
    (REPORTS_DIR / f"{stem}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    label = {"imerg": "GPM IMERG Final half-hourly (satellite + gauges, 0.1°)",
             "openmeteo": "ERA5 hourly reanalysis via Open-Meteo (about 25 km)"}[args.source]
    check = results["record_storm_check"]
    lines = [f"# Hourly vs daily rain, flood days per kecamatan ({args.source})", "",
             f"Generated {results['generated_at']} by `scripts/hourly_rain_experiment.py --source {args.source}`. "
             f"Rain: {label}. Rows: {results['rows']:,} kecamatan-days, {results['flood_rows']:,} with a BPBD flood.", "",
             "Flood kecamatan-days per year: " + ", ".join(f"{y}: {n}" for y, n in results["floods_per_year"].items()), "",
             f"Record storm check, 1 Jan 2020: wettest kecamatan {check['max_d0_mm']} mm that day "
             f"(wettest hour {check['max_1h_mm']} mm); BMKG Halim measured 377 mm.", "",
             "| Split | Model | Features | Test rows / floods | ROC-AUC | PR-AUC | Precision @ recall 0.5 | Hourly − daily, 95 % CI |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results["runs"]:
        if r["model"] == "rain alone":
            lines.append(f"| {r['split']} | rain alone | day total vs wettest 3 h | | "
                         f"{r['roc_auc_d0']} vs {r['roc_auc_max3h']} | | | |")
            continue
        ci = r.get("hourly_minus_daily_95ci")
        ci_text = f"ROC {ci['roc_auc']}, PR {ci['pr_auc']}" if ci else ""
        lines.append(f"| {r['split']} | {r['model']} | {r['features']} | {r['test_rows']:,} / {r['test_floods']:,} | "
                     f"{r['roc_auc']} | {r['pr_auc']} | {r['precision_at_recall_50']} | {ci_text} |")
    lines += ["", "- 2023–2025 BPBD dates are only partly readable, so those labels miss floods; precision there is a lower bound.",
              "- Each kecamatan takes the rain of the cell that holds its centroid; upstream = Katulampa (Bogor) and Depok cells."]
    (REPORTS_DIR / f"{stem}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
