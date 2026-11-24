#!/usr/bin/env python
"""
Fill the decision log (realtime_snapshot_store rows 'decision:<fetched_at>', read by the Riwayat page)
for the 15-minute history rows that have none, i.e. the days before the server started logging its
own decisions (24 Nov 2026).

Each snapshot is replayed through the code now served, as scripts/live_validation.py does: the daily
model for that WIB day (IMERG Early from Giovanni), the learned decision layer with today's rain up to
that moment, and the Siaga 1 safety rule; where the layer cannot decide, the river-post rules. BMKG's
L1.7 floor is not replayed. Rows are marked "source": "replay"; live rows are never overwritten.

Writes to Supabase. Usage (repo root): python scripts/backfill_decision_log.py [--start 2026-11-05] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from realtime_native import daily_model, decision_layer  # noqa: E402
from scripts import live_validation as lv  # noqa: E402
from services import history_service  # noqa: E402

LEVELS = ["SAFE", "PRE_ALERT", "WARNING", "DANGER"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--start", default="2026-11-05")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
    start, end = pd.Timestamp(args.start), daily_model.wib_date()
    rows = lv.history(start, end)
    existing = history_service._select_since(  # noqa: SLF001 - the same read the Riwayat page uses
        history_service.DECISION_PREFIX, "fetched_at", start.tz_localize("Asia/Jakarta").tz_convert("UTC").to_pydatetime())
    have = {r["fetched_at"] for r in existing}
    water_city = daily_model.city_water_from_rows(rows)
    posts = daily_model.posts_from_rows(rows)
    days = list(pd.date_range(start, end, freq="D"))
    states = lv.daily_states(days, water_city)
    out = []
    for r in rows:
        if r["fetched_at"] in have:
            continue
        day = daily_model.wib_date(r["fetched_at"])
        st, snap_posts = states.get(day), r.get("poskobanjir")
        now = decision_layer.water_now(snap_posts)
        if st is None or now is None:
            continue
        prev = day - pd.Timedelta(days=1)
        river = posts[(posts["date"] == prev) & posts["post"].isin(lv.dfe.RIVER_POSTS)].dropna(subset=["status"])
        st = {**st, "posts_d1": river.groupby("post")["status"].max().to_dict()}
        learned = decision_layer.decide(st, snap_posts, now=r["fetched_at"])
        rules = LEVELS[max(int(now["w_max"] or 0), 1 if st["city_level"] != "SAFE" else 0)]
        level = learned["risk_level"] if learned else rules
        layer = "L3_LEARNED" if learned else "rules"
        if (now["w_max"] or 0) >= 3:
            level, layer = "DANGER", "L1_SIAGA"
        out.append({"t": r["fetched_at"], "level": level, "layer": layer,
                    "chance": learned["score"] if learned and layer == "L3_LEARNED" else None,
                    "daily_p": st["city_probability"], "lag": st["lag_days"], "top": st.get("top_kecamatan"),
                    "source": "replay"})
    counts = pd.Series([o["level"] for o in out]).value_counts().to_dict() if out else {}
    print(f"history rows {len(rows)}, already logged {len(have)}, new decision rows {len(out)}: {counts}")
    if not args.dry_run and out:
        ok = history_service.save_decisions_sync(out)
        print("saved" if ok else "save FAILED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
