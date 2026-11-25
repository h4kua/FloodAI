#!/usr/bin/env python
"""
Out-of-time test of the served daily kecamatan model on 2026 (the bundle was trained on years up to 2025).

Every WIB day of 2026 is replayed through `daily_model.predict` (IMERG Early from Giovanni, rain lag chosen as
live, so lag 1 on a complete day) and compared with the Jakarta flood days found in the news
(data/processed/news_flood_reports_2026_clean.csv, scripts/fetch_news_flood_days.py).

What this can and cannot say
- Positives only: a news report names a flood; a day without one may still have had a small flood
  (BPBD publishes nothing for 2026 after 25 May), so the other days are "not reported", not "no flood".
  Ranking (ROC-AUC, recall at an alarm budget) is meaningful; precision is not.
- No DSDA water history before Apr 2026 (none in the database before 5 Nov), so the model runs on rain, place and
  season only; the water inputs are missing (XGBoost default branch). Its own evaluation found the water inputs
  add nothing significant for the kecamatan model.
- The learned decision layer (river posts) is not replayed here.

Outputs artifacts/reports/news_2026_retrospective.{md,json}.
Usage (repo root): python scripts/news_2026_retrospective.py [--start 2026-01-01]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from realtime_native import daily_model  # noqa: E402
from scripts import live_validation as lv  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

NEWS = PROCESSED_DATA_DIR / "news_flood_reports_2026_clean.csv"
LARGE_KEC = 10  # a day with at least this many kecamatan named counts as a large flood day
RNG = np.random.default_rng(7)


def auc(y, s):
    y = np.asarray(y)
    return float(roc_auc_score(y, s)) if 0 < y.sum() < len(y) else float("nan")


def boot_ci(y, s, n=1000, s2=None):
    """95 % CI of AUC (or of the AUC difference s - s2) resampling days."""
    y, s = np.asarray(y), np.asarray(s)
    idx_all, out = np.arange(len(y)), []
    for _ in range(n):
        i = RNG.choice(idx_all, len(y))
        if 0 < y[i].sum() < len(i):
            out.append(auc(y[i], s[i]) - (auc(y[i], np.asarray(s2)[i]) if s2 is not None else 0.0))
    return [round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--start", default="2026-01-01")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")

    news = pd.read_csv(NEWS)
    news["date"] = pd.to_datetime(news["date"]).dt.normalize()
    per_day = news.groupby("date").agg(reports=("url", "nunique"), kecamatan=("kecamatan", "nunique"))
    flood_pairs = set(zip(news["date"], news["kecamatan"]))

    last = daily_model.wib_date() - pd.Timedelta(days=1)
    days = list(pd.date_range(args.start, last, freq="D"))
    print(f"{len(days)} days {days[0].date()}..{days[-1].date()}, {len(per_day)} flood days", flush=True)
    states = lv.daily_states(days, daily_model.city_water_from_rows([]))
    rows = []
    for day in days:
        st = states.get(day)
        if st is None:
            continue
        rows.append({"date": day, "p": st["city_probability"], "level": st["city_level"], "lag": st["lag_days"],
                     "rain7": st["rain_7d_mm_city_max"], "top": st["top_kecamatan"],
                     "flood": int(day in per_day.index),
                     "reports": int(per_day["reports"].get(day, 0)), "kec_named": int(per_day["kecamatan"].get(day, 0)),
                     "kecamatan": st["kecamatan"]})
    df = pd.DataFrame(rows)
    df["large"] = (df["kec_named"] >= LARGE_KEC).astype(int)
    alarm = df["level"] != "SAFE"
    n, nf, nl = len(df), int(df["flood"].sum()), int(df["large"].sum())

    res = {"days_scored": n, "flood_days": nf, "large_flood_days": nl, "lag_counts": df["lag"].value_counts().to_dict()}
    res["auc_model"] = round(auc(df["flood"], df["p"]), 3)
    res["auc_model_ci"] = boot_ci(df["flood"], df["p"])
    res["auc_rain7"] = round(auc(df["flood"], df["rain7"]), 3)
    res["auc_diff_model_minus_rain7_ci"] = boot_ci(df["flood"], df["p"], s2=df["rain7"])
    res["auc_large_model"] = round(auc(df["large"], df["p"]), 3)
    res["auc_large_rain7"] = round(auc(df["large"], df["rain7"]), 3)
    res["alarm_days"] = int(alarm.sum())
    res["alarm_share"] = round(float(alarm.mean()), 3)
    res["recall_flood_at_alarm"] = round(float(alarm[df["flood"] == 1].mean()), 3)
    res["recall_large_at_alarm"] = round(float(alarm[df["large"] == 1].mean()), 3) if nl else None
    # Same number of alarm days for the plain 7-day rain rule.
    k = int(alarm.sum())
    rain_alarm = df["rain7"].rank(ascending=False, method="first") <= k
    res["rain7_recall_flood_same_alarm_days"] = round(float(rain_alarm[df["flood"] == 1].mean()), 3)
    res["rain7_recall_large_same_alarm_days"] = round(float(rain_alarm[df["large"] == 1].mean()), 3) if nl else None
    res["by_month"] = {str(m): {"days": int(g.shape[0]), "alarm_days": int((g["level"] != "SAFE").sum()),
                                "flood_days": int(g["flood"].sum()),
                                "flood_days_with_alarm": int(((g["level"] != "SAFE") & (g["flood"] == 1)).sum())}
                       for m, g in df.groupby(df["date"].dt.to_period("M"))}

    # Kecamatan level: do reported kecamatan rank above the others on the same day?
    pct, y_all, s_all = [], [], []
    for _, r in df.iterrows():
        probs = pd.Series({s: v["probability"] for s, v in r["kecamatan"].items()})
        reported = [k for (d, k) in flood_pairs if d == r["date"] and k in probs.index]
        for slug, p in probs.items():
            y_all.append(int((r["date"], slug) in flood_pairs)); s_all.append(p)
        if reported:
            ranks = probs.rank(pct=True)
            pct += [float(ranks[k]) for k in reported]
    res["kecamatan_auc_all_days"] = round(auc(y_all, s_all), 3)
    res["reported_kecamatan_mean_percentile_on_flood_days"] = round(float(np.mean(pct)), 3) if pct else None

    missed = df[(df["flood"] == 1) & ~alarm].sort_values("kec_named", ascending=False)
    res["missed_flood_days"] = [{"date": str(r["date"].date()), "kecamatan_named": int(r["kec_named"]), "reports": int(r["reports"]),
                                 "p": round(r["p"], 3), "rain7": round(r["rain7"], 1)} for _, r in missed.iterrows()]
    big = df[df["large"] == 1].sort_values("date")
    res["large_days"] = [{"date": str(r["date"].date()), "kecamatan_named": int(r["kec_named"]), "p": round(r["p"], 3),
                          "level": r["level"], "rain7": round(r["rain7"], 1), "top": r["top"]} for _, r in big.iterrows()]

    out = REPORTS_DIR / "news_2026_retrospective"
    out.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    out.with_suffix(".md").write_text(markdown(res), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("by_month", "missed_flood_days", "large_days")},
                     ensure_ascii=False, indent=1), flush=True)
    print(f"-> {out.with_suffix('.md')}")
    return 0


def markdown(r: dict) -> str:
    lines = [
        "# Daily model on 2026 news flood days (out of time)",
        "",
        "Replay of the served daily kecamatan model (rain, place, season; no water inputs) on every day of 2026 against the "
        "Jakarta flood days found in detik.com reports. Positives only: a day without a report is *not reported*, not *no flood*, "
        "so ranking is meaningful and precision is not.",
        "",
        f"- Days scored {r['days_scored']}, news flood days {r['flood_days']}, large flood days (>= {LARGE_KEC} kecamatan named) {r['large_flood_days']}. Rain lag used: {r['lag_counts']}.",
        f"- City ROC-AUC, flood day vs other days: **{r['auc_model']}** (95 % CI {r['auc_model_ci']}); 7-day rain rule alone {r['auc_rain7']}; "
        f"difference model - rain CI {r['auc_diff_model_minus_rain7_ci']}.",
        f"- Large flood days only: model {r['auc_large_model']}, 7-day rain {r['auc_large_rain7']}.",
        f"- At the served Waspada threshold the model raises {r['alarm_days']} days ({r['alarm_share']:.0%}); it catches {r['recall_flood_at_alarm']:.0%} of the flood days"
        f" and {('%.0f%%' % (100 * r['recall_large_at_alarm'])) if r['recall_large_at_alarm'] is not None else 'n/a'} of the large ones. "
        f"The 7-day rain rule with the same number of alarm days catches {r['rain7_recall_flood_same_alarm_days']:.0%} / "
        f"{('%.0f%%' % (100 * r['rain7_recall_large_same_alarm_days'])) if r['rain7_recall_large_same_alarm_days'] is not None else 'n/a'}.",
        f"- Kecamatan level: AUC {r['kecamatan_auc_all_days']} over all kecamatan-days; on flood days the reported kecamatan sit at the "
        f"{r['reported_kecamatan_mean_percentile_on_flood_days']} mean percentile of the 42.",
        "",
        "## By month",
        "",
        "| Month | Days | Alarm days | News flood days | Flood days with alarm |",
        "|---|---|---|---|---|",
    ]
    for m, v in r["by_month"].items():
        lines.append(f"| {m} | {v['days']} | {v['alarm_days']} | {v['flood_days']} | {v['flood_days_with_alarm']} |")
    lines += ["", "## Large flood days", "", "| Date | Kecamatan named | Chance | Level | 7-day rain (mm, city max) | Top kecamatan |", "|---|---|---|---|---|---|"]
    for v in r["large_days"]:
        lines.append(f"| {v['date']} | {v['kecamatan_named']} | {v['p']:.0%} | {v['level']} | {v['rain7']} | {v['top']} |")
    lines += ["", "## Flood days with no alarm (misses)", "", "| Date | Kecamatan named | Reports | Chance | 7-day rain |", "|---|---|---|---|---|"]
    for v in r["missed_flood_days"]:
        lines.append(f"| {v['date']} | {v['kecamatan_named']} | {v['reports']} | {v['p']:.0%} | {v['rain7']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
