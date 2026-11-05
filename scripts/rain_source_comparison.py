#!/usr/bin/env python
"""
IMERG vs ERA5 rain on the same kecamatan-days (exploratory; nothing here is served).

Builds both datasets of scripts/hourly_rain_experiment.py, fits the same model on each with the
daily feature set, and reports the IMERG-minus-ERA5 ROC-AUC / PR-AUC difference with a 95 %
interval from a paired bootstrap over test dates. Needs the IMERG cache from
scripts/fetch_imerg_history.py. Outputs artifacts/reports/rain_source_comparison.{json,md}.

Usage (repo root):  python scripts/rain_source_comparison.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402

from scripts.hourly_rain_experiment import (  # noqa: E402
    DAILY_FEATURES, _model, _paired_bootstrap, build_dataset,
)
from utils.paths import REPORTS_DIR  # noqa: E402

SPLITS = {"train 2020–2021, test 2022 (complete dates)": (2022, 2022),
          "train 2020–2022, test 2023–Sep 2025 (partial dates)": (2023, 2025)}


def main() -> int:
    keys = ["kecamatan", "date"]
    era5 = build_dataset("openmeteo").set_index(keys)
    imerg = build_dataset("imerg").set_index(keys)
    common = era5.index.intersection(imerg.index)
    era5, imerg = era5.loc[common].reset_index(), imerg.loc[common].reset_index()
    runs = []
    for split, (first, last) in SPLITS.items():
        for kind in ("logistic", "xgboost"):
            probs, y_te, dates = {}, None, None
            for name, data in (("era5", era5), ("imerg", imerg)):
                train = data[data["year"] < first]
                test = data[(data["year"] >= first) & (data["year"] <= last)]
                y_tr, y_te = train["flood"].to_numpy(), test["flood"].to_numpy()
                dates = test["date"].to_numpy()
                model = _model(kind, y_tr).fit(train[DAILY_FEATURES].fillna(0.0), y_tr)
                probs[name] = model.predict_proba(test[DAILY_FEATURES].fillna(0.0))[:, 1]
            runs.append({
                "split": split, "model": kind,
                "era5_roc_auc": round(float(roc_auc_score(y_te, probs["era5"])), 3),
                "imerg_roc_auc": round(float(roc_auc_score(y_te, probs["imerg"])), 3),
                "era5_pr_auc": round(float(average_precision_score(y_te, probs["era5"])), 3),
                "imerg_pr_auc": round(float(average_precision_score(y_te, probs["imerg"])), 3),
                "imerg_minus_era5_95ci": _paired_bootstrap(dates, y_te, probs["era5"], probs["imerg"]),
            })
    results = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "rows": int(len(common)), "features": DAILY_FEATURES, "runs": runs}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "rain_source_comparison.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = ["# IMERG vs ERA5 rain, flood days per kecamatan", "",
             f"Generated {results['generated_at']} by `scripts/rain_source_comparison.py`. Same {results['rows']:,} "
             "kecamatan-days, same labels and model, daily feature set; only the rain source differs.", "",
             "| Split | Model | ROC-AUC ERA5 → IMERG | PR-AUC ERA5 → IMERG | IMERG − ERA5, 95 % CI |",
             "|---|---|---|---|---|"]
    for r in runs:
        ci = r["imerg_minus_era5_95ci"]
        lines.append(f"| {r['split']} | {r['model']} | {r['era5_roc_auc']} → {r['imerg_roc_auc']} | "
                     f"{r['era5_pr_auc']} → {r['imerg_pr_auc']} | ROC {ci['roc_auc']}, PR {ci['pr_auc']} |")
    (REPORTS_DIR / "rain_source_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
