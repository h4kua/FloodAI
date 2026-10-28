#!/usr/bin/env python
"""
Feasibility check for daily flood labels (exploratory; nothing here is served).

Target: a city-level flood day = at least N kelurahan with a BPBD flood on that date, taken
from the incident dates in data/raw/rekap_kejadian_2020_2025.csv (one RW-date counted once).
Dates are fully readable for 2020–2022 and only partly for 2023–2025 (40–74 % of rows), so
2023–2025 labels miss some flood days and their precision is a lower bound.

Features: ERA5 daily precipitation from the Open-Meteo archive (no key) for north Jakarta,
south Jakarta and the upper Ciliwung near Bogor — same day, previous two days, 3-day sums —
plus month. Cached in data/raw/openmeteo_daily_2020_2025.json.

Splits: train 2020–2021, test 2022 (complete labels); train 2020–2022, test 2023–2025.
Outputs artifacts/reports/daily_flood_experiment.{json,md}.
Usage (repo root):  python scripts/daily_flood_experiment.py
"""

from __future__ import annotations

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
from utils.paths import REPORTS_DIR  # noqa: E402

REKAP_CSV = _PROJECT_ROOT / "data" / "raw" / "rekap_kejadian_2020_2025.csv"
RAIN_CACHE = _PROJECT_ROOT / "data" / "raw" / "openmeteo_daily_2020_2025.json"
POINTS = {"north": (-6.155, 106.84), "south": (-6.27, 106.85), "bogor": (-6.60, 106.80)}
_MONTHS = ("januari februari maret april mei juni juli agustus september oktober november desember").split()
_SEED = 42


def flood_days() -> pd.Series:
    """{date: number of kelurahan with a BPBD flood that day}."""
    rekap = pd.read_csv(REKAP_CSV).drop_duplicates()
    rows = []
    for kel, year, month, text in zip(rekap["kelurahan"], rekap["tahun"], rekap["bulan"], rekap["tanggal_kejadian"]):
        if not isinstance(text, str):
            continue
        text = re.split(rf"(?i)\b(?:{'|'.join(_MONTHS)})\b", text)[0]
        text = re.sub(r"(?i)tgl\.?|tanggal", "", text)
        for a, b in re.findall(r"(\d{1,2})\s*(?:[-–]|s\.?d\.?)?\s*(\d{1,2})?", text):
            first, last = int(a), int(b) if b else int(a)
            if 1 <= first <= last <= 31 and last - first <= 10:
                for day in range(first, last + 1):
                    try:
                        rows.append((pd.Timestamp(year=int(year), month=int(month), day=day), kel))
                    except ValueError:
                        pass
    events = pd.DataFrame(rows, columns=["date", "kelurahan"]).drop_duplicates()
    return events.groupby("date")["kelurahan"].nunique()


def rainfall() -> pd.DataFrame:
    if not RAIN_CACHE.exists():
        payload = {}
        for name, (lat, lon) in POINTS.items():
            query = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "start_date": "2020-01-01",
                                            "end_date": "2025-12-31", "daily": "precipitation_sum",
                                            "timezone": "Asia/Jakarta"})
            with urllib.request.urlopen(f"https://archive-api.open-meteo.com/v1/archive?{query}", timeout=60) as resp:
                payload[name] = json.load(resp)["daily"]
        RAIN_CACHE.write_text(json.dumps(payload), encoding="utf-8")
    payload = json.loads(RAIN_CACHE.read_text(encoding="utf-8"))
    frame = pd.DataFrame({name: pd.Series(d["precipitation_sum"], index=pd.to_datetime(d["time"]))
                          for name, d in payload.items()}).fillna(0.0)
    feats = pd.DataFrame(index=frame.index)
    for name in POINTS:
        feats[f"{name}_d0"] = frame[name]
        feats[f"{name}_d1"] = frame[name].shift(1)
        feats[f"{name}_d2"] = frame[name].shift(2)
        feats[f"{name}_3day"] = frame[name].rolling(3).sum()
    feats["month_sin"] = np.sin(2 * np.pi * feats.index.month / 12)
    feats["month_cos"] = np.cos(2 * np.pi * feats.index.month / 12)
    return feats.dropna()


def _precision_at_recall(y, p, target):
    prec, rec, _ = precision_recall_curve(y, p)
    ok = rec >= target
    return round(float(prec[ok].max()), 3) if ok.any() else None


def _fit(kind):
    if kind == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    return XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,
                         colsample_bytree=0.8, random_state=_SEED, eval_metric="logloss")


def main() -> int:
    feats = rainfall()
    counts = flood_days().reindex(feats.index, fill_value=0)
    results = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "flood_days_per_year": {int(y): int((g > 0).sum()) for y, g in counts.groupby(counts.index.year)},
               "runs": []}
    splits = {"train 2020–2021, test 2022 (complete dates)": (2022, 2022),
              "train 2020–2022, test 2023–2025 (partial dates)": (2023, 2025)}
    for min_kel in (1, 5):
        y_all = (counts >= min_kel).astype(int)
        for split_name, (first, last) in splits.items():
            years = feats.index.year
            train, test = years < first, (years >= first) & (years <= last)
            y_tr, y_te = y_all[train].to_numpy(), y_all[test].to_numpy()
            for kind in ("logistic", "xgboost"):
                model = _fit(kind).fit(feats[train], y_tr)
                p = model.predict_proba(feats[test])[:, 1]
                rain_only = feats.loc[test, "north_3day"] + feats.loc[test, "south_3day"]
                results["runs"].append({
                    "flood_day": f">= {min_kel} kelurahan", "split": split_name, "model": kind,
                    "test_days": int(test.sum()), "test_flood_days": int(y_te.sum()),
                    "prevalence": round(float(y_te.mean()), 3),
                    "roc_auc": round(float(roc_auc_score(y_te, p)), 3),
                    "pr_auc": round(float(average_precision_score(y_te, p)), 3),
                    "precision_at_recall_80": _precision_at_recall(y_te, p, 0.8),
                    "precision_at_recall_50": _precision_at_recall(y_te, p, 0.5),
                    "rain_3day_sum_alone_roc_auc": round(float(roc_auc_score(y_te, rain_only)), 3),
                })
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "daily_flood_experiment.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = ["# Daily flood-label experiment (exploratory)", "",
             f"Generated {results['generated_at']} by `scripts/daily_flood_experiment.py`. City-level flood day from BPBD "
             "incident dates; ERA5 daily rainfall (Open-Meteo archive) for north/south Jakarta and the upper Ciliwung.", "",
             "Flood days (>= 1 kelurahan) per year: " + ", ".join(f"{y}: {n}" for y, n in results["flood_days_per_year"].items()), "",
             "| Flood day | Split | Model | Test days / flood days | Prevalence | ROC-AUC | PR-AUC | Precision @ recall 0.8 | Precision @ recall 0.5 | 3-day rain alone ROC-AUC |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results["runs"]:
        lines.append(f"| {r['flood_day']} | {r['split']} | {r['model']} | {r['test_days']} / {r['test_flood_days']} | "
                     f"{r['prevalence']} | {r['roc_auc']} | {r['pr_auc']} | {r['precision_at_recall_80']} | "
                     f"{r['precision_at_recall_50']} | {r['rain_3day_sum_alone_roc_auc']} |")
    lines += ["", "- 2023–2025 dates are readable for only 40–74 % of BPBD rows, so some flood days there are labelled dry "
              "and precision is a lower bound.",
              "- ERA5 is a reanalysis (about 25 km grid), not a rain gauge; local downpours are smoothed."]
    (REPORTS_DIR / "daily_flood_experiment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
