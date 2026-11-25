#!/usr/bin/env python
"""
Why did the daily model miss the two largest 2026 news flood days (29 Jan: 21 kecamatan, 8 Mar: 22 kecamatan)?
Two candidate causes, both outside the rain over Jakarta itself:

1. Upstream rain ("banjir kiriman"): IMERG over the Bogor and Depok cells in the 1-3 days before, set against the
   same calendar months (Jan-Mar) of 2013-2025 (cached IMERG, data/raw/imerg).
2. Tide: the moon phase (distance to the nearest new or full moon; spring tides follow within about two days).
   Approximate: phase only, no perigee or weather surge. 2026 tide gauges are not in this repository.

Reads IMERG Early for 2026 from Giovanni (needs EARTHDATA_TOKEN, read only). Writes
artifacts/reports/news_2026_miss_causes.md.
Usage (repo root): python scripts/news_2026_miss_causes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from realtime_native import daily_features as dfe  # noqa: E402
from realtime_native.imerg_client import fetch_rate  # noqa: E402
from scripts.hourly_rain_experiment import _imerg_series  # noqa: E402
from utils.paths import REPORTS_DIR  # noqa: E402

CELLS = {"Bogor": "-6.65_106.85", "Depok": "-6.35_106.85", "Jakarta (centre)": "-6.15_106.85"}
DAYS = {"2026-01-29": "29 Jan (21 kecamatan)", "2026-03-08": "8 Mar (22 kecamatan)", "2026-01-22": "22 Jan (28, caught)",
        "2026-01-18": "18 Jan (26, caught)"}
NEW_MOON_REF = pd.Timestamp("2000-01-06 18:14", tz="UTC")  # a known new moon
SYNODIC = 29.530588


def moon_age(day: pd.Timestamp) -> float:
    return float(((day.tz_localize("UTC") + pd.Timedelta(hours=12) - NEW_MOON_REF) / pd.Timedelta(days=1)) % SYNODIC)


def days_to_syzygy(day: pd.Timestamp) -> tuple[float, str]:
    """Signed days to the nearest new (0) or full (half a cycle) moon; negative = before it."""
    age = moon_age(day)
    to_new = age if age < SYNODIC / 2 else age - SYNODIC
    to_full = age - SYNODIC / 2
    return (-to_new, "new moon") if abs(to_new) < abs(to_full) else (-to_full, "full moon")


def history_daily(cell: str) -> pd.Series:
    """Daily WIB rain (mm) from the cached IMERG hourly series 2012-2025."""
    s = _imerg_series(cell)
    return (s.tz_convert("Asia/Jakarta").resample("D").sum()).tz_localize(None)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
    lines = ["# Why the 2026 largest flood days were missed", "",
             "Daily IMERG rain (mm, WIB day) before each flood day, and where it sits among the same months (Jan-Mar) of 2013-2025. "
             "'3-day' = the three days before the flood day (the model's lag-1 window ends the day before). Percentile 90 = wetter "
             "than 90 % of such windows.", ""]
    start = pd.Timestamp("2026-01-01") - pd.Timedelta(hours=7)
    end = pd.Timestamp("2026-03-31 17:00")
    results: dict[str, dict] = {}
    for name, cell in CELLS.items():
        rate = fetch_rate(cell, start, end)
        now_daily = dfe.wib_daily_rain(rate)
        hist = history_daily(cell)
        hist3 = hist.rolling(3).sum().shift(1)  # the three days before each day
        base = hist3[(hist3.index.month <= 3)].dropna()
        base1 = hist.shift(1)[(hist.index.month <= 3)].dropna()
        for iso, label in DAYS.items():
            d = pd.Timestamp(iso)
            before = [float(now_daily.get(d - pd.Timedelta(days=k), np.nan)) for k in (3, 2, 1)]
            s3 = float(np.nansum(before))
            day0 = float(now_daily.get(d, np.nan))
            base0 = hist[(hist.index.month <= 3)].dropna()
            results.setdefault(iso, {})[name] = {
                "d3": before[0], "d2": before[1], "d1": before[2], "sum3": s3, "d0": day0,
                "pct3": float((base < s3).mean() * 100), "pct1": float((base1 < before[2]).mean() * 100),
                "pct0": float((base0 < day0).mean() * 100)}
    lines += ["| Flood day | Cell | Day-3 | Day-2 | Day-1 | 3-day sum | Percentile of 3-day | Percentile of day-1 | Flood day itself (mm) | Percentile of that day |", "|---|---|---|---|---|---|---|---|---|---|"]
    for iso, label in DAYS.items():
        for name in CELLS:
            r = results[iso][name]
            lines.append(f"| {label} | {name} | {r['d3']:.0f} | {r['d2']:.0f} | {r['d1']:.0f} | {r['sum3']:.0f} | {r['pct3']:.0f} | {r['pct1']:.0f} | {r['d0']:.0f} | {r['pct0']:.0f} |")
    lines += ["", "## Tide (moon phase, approximate)", "", "| Flood day | Days to nearest new/full moon | Which |", "|---|---|---|"]
    for iso, label in DAYS.items():
        delta, which = days_to_syzygy(pd.Timestamp(iso))
        lines.append(f"| {label} | {delta:+.1f} | {which} |")
    flood = pd.read_csv(_ROOT / "data" / "processed" / "news_flood_reports_2026_clean.csv", usecols=["date"])
    fdays = sorted(set(pd.to_datetime(flood["date"]).dt.normalize()))
    near = [abs(days_to_syzygy(d)[0]) <= 2.5 for d in fdays]
    allnear = [abs(days_to_syzygy(d)[0]) <= 2.5 for d in pd.date_range("2026-01-01", "2026-05-31")]
    lines += ["", f"Flood days within 2.5 days of a new or full moon: {sum(near)} of {len(near)} ({sum(near) / len(near):.0%}); "
              f"all days Jan-May 2026: {sum(allnear) / len(allnear):.0%}.", ""]
    text = "\n".join(lines) + "\n"
    (REPORTS_DIR / "news_2026_miss_causes.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
