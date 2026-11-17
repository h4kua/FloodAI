#!/usr/bin/env python
"""
Live validation: what the site said vs the floods reported afterwards (re-run every month of the season).

Decisions: every 15-minute snapshot the server kept (realtime_snapshot_store rows "history:*", read only)
is replayed through the code now served: the daily kecamatan model for that WIB day (IMERG Early from
Giovanni for the whole period, rain lag chosen as live), the learned decision layer and its safety rule
(a river post at Siaga 1 -> Bahaya), falling back to the river-post rules where the layer cannot decide.
For comparison: the rules alone (highest river-post status, or Waspada when the daily model raises it).
BMKG's L1.7 floor is not replayed. This is what the current code says about those moments, not a log of
what the site showed then (the code changed during the period).

Floods: days with a Jakarta flood report in data/processed/news_flood_reports_2026.csv
(scripts/fetch_news_flood_days.py --start 2026-11 --end <month> --out ...), plus any extra CSV of
date,kecamatan rows passed with --labels (for BPBD or PetaBencana records when they arrive). News is a
partial label: a day without a report may still have had a small flood.

Per WIB day: the highest level of the day and whether a flood was reported. Outputs
artifacts/reports/live_validation.{json,md}.
Usage (repo root): python scripts/live_validation.py [--start 2026-11-05] [--end today] [--labels extra.csv]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from realtime_native import daily_features as dfe  # noqa: E402
from realtime_native import daily_model, decision_layer  # noqa: E402
from realtime_native.imerg_client import fetch_rate  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

NEWS = PROCESSED_DATA_DIR / "news_flood_reports_2026.csv"
LEVELS = ["SAFE", "PRE_ALERT", "WARNING", "DANGER"]
NAMES = {"SAFE": "Aman", "PRE_ALERT": "Waspada", "WARNING": "Siaga", "DANGER": "Bahaya"}


def history(start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    from db.supabase_client import get_supabase_client

    client, rows, offset = get_supabase_client(), [], 0
    lo, hi = (start - pd.Timedelta(days=2) - pd.Timedelta(hours=7)), (end + pd.Timedelta(hours=17))
    while True:
        res = (client.table("realtime_snapshot_store").select("fetched_at,poskobanjir:snapshot->poskobanjir")
               .like("id", "history:%").gte("fetched_at", lo.isoformat()).lt("fetched_at", hi.isoformat())
               .order("fetched_at").range(offset, offset + 499).execute())
        batch = res.data or []
        rows += batch
        if len(batch) < 500:
            return rows
        offset += 500


def daily_states(days: list[pd.Timestamp], water_city: pd.DataFrame) -> dict:
    bundle = daily_model.load_bundle()
    cells = sorted({k["cell"] for k in bundle["kecamatan"].values()} | set(bundle["upstream_cells"].values()))
    start_utc = min(days) - pd.Timedelta(days=daily_model.RAIN_DAYS) - pd.Timedelta(hours=7)
    end_utc = pd.Timestamp.now(tz="UTC").tz_localize(None)
    rates = {c: fetch_rate(c, start_utc, end_utc) for c in cells}
    daily = {c: dfe.wib_daily_rain(r) for c, r in rates.items()}
    strict = {c: daily_model._strict_days(r) for c, r in rates.items()}
    states = {}
    for day in days:
        try:
            states[day] = daily_model.predict(daily, strict, water_city, day, bundle)
        except daily_model.DailyModelUnavailable:
            pass
    return states


def flood_days(extra: str | None) -> set:
    frames = []
    if NEWS.exists():
        frames.append(pd.read_csv(NEWS, usecols=["date", "kecamatan"]))
    if extra:
        frames.append(pd.read_csv(extra, usecols=["date", "kecamatan"]))
    if not frames:
        return set()
    return set(pd.to_datetime(pd.concat(frames)["date"]).dt.normalize())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--start", default="2026-11-05")
    parser.add_argument("--end", default="")
    parser.add_argument("--labels", default="")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv

    load_dotenv(_PROJECT_ROOT / ".env")
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else daily_model.wib_date()
    rows = history(start, end)
    water_city = daily_model.city_water_from_rows(rows)
    days = list(pd.date_range(start, end, freq="D"))
    states = daily_states(days, water_city)
    floods = flood_days(args.labels or None)

    per_day, snaps = {}, {"learned": [], "rules": []}
    for r in rows:
        day = daily_model.wib_date(r["fetched_at"])
        st, posts = states.get(day), r.get("poskobanjir")
        now = decision_layer.water_now(posts)
        if st is None or now is None or day < start or day > end:
            continue
        rules = LEVELS[max(int(now["w_max"] or 0), 1 if st["city_level"] != "SAFE" else 0)]
        out = decision_layer.decide(st, posts)
        learned = out["risk_level"] if out else rules
        if (now["w_max"] or 0) >= 3:
            learned = "DANGER"
        d = per_day.setdefault(day, {"learned": "SAFE", "rules": "SAFE", "snapshots": 0, "by_layer": 0,
                                     "chance_max": None, "daily_p": st["city_probability"], "lag": st["lag_days"]})
        d["snapshots"] += 1
        d["by_layer"] += int(out is not None)
        if out is not None:
            d["chance_max"] = max(d["chance_max"] or 0.0, out["score"])
        for who, lvl in (("learned", learned), ("rules", rules)):
            snaps[who].append(lvl)
            if LEVELS.index(lvl) > LEVELS.index(d[who]):
                d[who] = lvl

    report = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "period": [start.date().isoformat(), end.date().isoformat()], "days": len(per_day),
              "flood_days": sorted(d.date().isoformat() for d in floods if start <= d <= end),
              "snapshot_share": {who: {NAMES[l]: round(lv.count(l) / max(len(lv), 1), 3) for l in LEVELS}
                                 for who, lv in snaps.items()},
              "per_day": {}, "by_level": {}}
    for day, d in sorted(per_day.items()):
        report["per_day"][day.date().isoformat()] = {**d, "flood_reported": day in floods,
                                                    "chance_max": None if d["chance_max"] is None else round(d["chance_max"], 3)}
    for who in ("learned", "rules"):
        report["by_level"][who] = {}
        for k, lvl in enumerate(LEVELS[1:], start=1):
            warned = {day for day, d in per_day.items() if LEVELS.index(d[who]) >= k}
            fl = {day for day in per_day if day in floods}
            report["by_level"][who][NAMES[lvl]] = {"warning_days": len(warned), "flood_days": len(fl),
                                                   "warned_flood_days": len(warned & fl),
                                                   "warned_days_without_report": len(warned - fl),
                                                   "missed_flood_days": len(fl - warned)}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "live_validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORTS_DIR / "live_validation.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    return 0


def markdown(r: dict) -> str:
    L = ["# Live validation", "",
         f"Generated {r['generated_utc']} by `scripts/live_validation.py`. Period {r['period'][0]} to {r['period'][1]} "
         f"({r['days']} days with snapshots). Flood days reported: {', '.join(r['flood_days']) or 'none'}.", "",
         "Each 15-minute snapshot replayed through the code now served (daily model + learned layer + Siaga 1 rule); "
         "rules = river-post status or the daily model's Waspada. News is a partial label.", "",
         f"Share of snapshots per level: learned {r['snapshot_share']['learned']}; rules {r['snapshot_share']['rules']}.", "",
         "| Level (day's highest) | Approach | Warning days | Flood days | Warned flood days | Warning days without a report | Missed flood days |",
         "|---|---|---|---|---|---|---|"]
    for who, levels in r["by_level"].items():
        for name, x in levels.items():
            L.append(f"| >= {name} | {who} | {x['warning_days']} | {x['flood_days']} | {x['warned_flood_days']} | "
                     f"{x['warned_days_without_report']} | {x['missed_flood_days']} |")
    L += ["", "| Day | Daily chance (lag) | Layer's highest chance | Learned | Rules | Flood reported |", "|---|---|---|---|---|---|"]
    for day, d in r["per_day"].items():
        L.append(f"| {day} | {d['daily_p']:.3f} ({d['lag']}) | {d['chance_max'] if d['chance_max'] is not None else '-'} | "
                 f"{NAMES[d['learned']]} | {NAMES[d['rules']]} | {'yes' if d['flood_reported'] else 'no'} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
