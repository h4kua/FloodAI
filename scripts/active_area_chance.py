#!/usr/bin/env python
"""
How often a flood-prone area actually floods when the river post that activates it is at Siaga 3, 2 or 1.

The map marks a BPBD/BNPB flood-prone point as active when a post on its river is at Siaga and the point
lies within 1 km of the post's drawn stretch (frontend/src/lib/floodRoads.js activeFloodPoints, with
frontend/src/data/postRivers.json and floodProneZones.json). This script applies the same rule to the
DSDA archive 2016-2021 (each post's highest status of the day, data/processed/dsda_tma_daily_2016_2020.csv)
and counts, per level, the share of (day, kecamatan of an activated point) pairs (gate-operated posts left out: Istiqlal,
Jembatan Merah, Flusing Ancol, Hek sit at Siaga 3+ most days) with a BPBD flood record
that day (scripts/hourly_rain_experiment.flood_kecamatan_days). 95 % intervals resample days.

Writes frontend/src/data/activeAreaChance.json (the map shows these chances on its circles) and
artifacts/reports/active_area_chance.md.
Usage (repo root): python scripts/active_area_chance.py
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from scripts.hourly_rain_experiment import flood_kecamatan_days  # noqa: E402
from utils.paths import PROCESSED_DATA_DIR, REPORTS_DIR  # noqa: E402

DATA = _ROOT / "frontend" / "src" / "data"
OUT = DATA / "activeAreaChance.json"
NEAR_RIVER_M = 1000
CILIWUNG_ALL = ["CILIWUNG", "CILIWUNG ARAH ISTANA NEGARA", "CILIWUNG ARAH KANAL BANJIR BARAT"]
# Same table as POST_RIVERS in frontend/src/lib/floodRoads.js, on the archive's post keys.
POST_RIVERS = [
    (r"katulampa|depok|cibalok|manggarai", CILIWUNG_ALL),
    (r"karet", ["CILIWUNG ARAH KANAL BANJIR BARAT"]),
    (r"istiqlal|jembatanmerah|flush", ["CILIWUNG ARAH ISTANA NEGARA"]),
    (r"krukut", ["KRUKUT"]),
    (r"pesanggrahan", ["PESANGGRAHAN", "PESANGGRAHAN & ANGKE"]),
    (r"angke|cengkarengdrain", ["ANGKE", "PESANGGRAHAN & ANGKE"]),
    (r"sunter|pulogadung", ["SUNTER"]),
    (r"cipinang|kampungrambutan", ["CIPINANG"]),
]
LEVEL_NAMES = {1: "Siaga 3", 2: "Siaga 2", 3: "Siaga 1"}
# Gate-operated posts sit at Siaga 3+ most days in the archive (their status follows the gates, not floods).
GATE_POSTS = {"ISTIQLAL", "JEMBATANMERAH", "FLUSINGANCOL", "ANCOLFLUSHING", "HEK"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def rivers_for(post: str) -> list[str]:
    return next((rivers for pattern, rivers in POST_RIVERS if re.search(pattern, post.lower())), [])


def _dist_m(p, a, b) -> float:
    """Distance from p to segment ab ([lat, lon]), equirectangular metres."""
    lat0 = math.radians(p[0])
    def xy(q):
        return (math.radians(q[1]) * math.cos(lat0) * 6371000, math.radians(q[0]) * 6371000)
    (px, py), (ax, ay), (bx, by) = xy(p), xy(a), xy(b)
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def affected_kecamatan(post: str, points: list[dict], table: dict) -> set[str]:
    rivers = set(rivers_for(post))
    entry = table.get(post.lower()) or table.get(re.sub(r"\d+$", "", post.lower()))
    out = set()
    for p in points:
        if not rivers & set(p.get("rivers") or []):
            continue
        lines = (entry or {}).get("lines") or []
        if entry is None or not lines or entry.get("upstream") or any(
                _dist_m([p["lat"], p["lon"]], line[i - 1], line[i]) <= NEAR_RIVER_M
                for line in lines for i in range(1, len(line))):
            out.add(slug(p["kecamatan"]))
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    points = json.loads((DATA / "floodProneZones.json").read_text(encoding="utf-8"))["points"]
    table = json.loads((DATA / "postRivers.json").read_text(encoding="utf-8"))
    daily = pd.read_csv(PROCESSED_DATA_DIR / "dsda_tma_daily_2016_2020.csv", parse_dates=["date"])
    daily = daily[(daily["coastal"] == 0) & ~daily["post"].isin(GATE_POSTS)].dropna(subset=["status_max"])
    floods = flood_kecamatan_days()
    flooded = set(zip(floods["kecamatan"], floods["date"]))

    rows = []
    for post, g in daily.groupby("post"):
        kecs = affected_kecamatan(post, points, table)
        if not kecs:
            continue
        for date, status in zip(g["date"], g["status_max"]):
            for k in kecs:
                rows.append((post, date, int(status), k, int((k, date) in flooded)))
    pairs = pd.DataFrame(rows, columns=["post", "date", "level", "kecamatan", "flood"])
    rng = np.random.default_rng(42)
    report = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "period": [str(pairs["date"].min().date()), str(pairs["date"].max().date())],
              "posts": sorted(pairs["post"].unique()), "by_level": {}, "by_post": {}}
    for level in (0, 1, 2, 3):
        sub = pairs[pairs["level"] == level]
        days = sub["date"].unique()
        by_day = sub.groupby("date")["flood"].agg(["sum", "count"])
        boots = []
        for _ in range(1000):
            pick = by_day.loc[rng.choice(days, len(days))]
            boots.append(pick["sum"].sum() / pick["count"].sum())
        report["by_level"][str(level)] = {"rate": round(float(sub["flood"].mean()), 3), "pairs": int(len(sub)),
                                          "days": int(len(days)),
                                          "ci95": [round(float(np.percentile(boots, 2.5)), 3),
                                                   round(float(np.percentile(boots, 97.5)), 3)]}
        print(f"level {level}: flood share {sub['flood'].mean():.3f} over {len(sub)} pairs on {len(days)} days", flush=True)
    for post, g in pairs[pairs["level"] >= 1].groupby("post"):
        report["by_post"][post] = {LEVEL_NAMES[lv]: {"rate": round(float(s["flood"].mean()), 3), "pairs": int(len(s))}
                                   for lv, s in g.groupby("level")}
    served = {"source": "DSDA archive 2016-2021 vs BPBD flood records (scripts/active_area_chance.py)",
              # The posts the rates were measured on: the map shows a rate only for a cause post in this list.
              "posts": [p.lower() for p in report["posts"]],
              "by_status": {LEVEL_NAMES[lv]: report["by_level"][str(lv)]["rate"] for lv in (1, 2, 3)},
              "normal": report["by_level"]["0"]["rate"]}
    OUT.write_text(json.dumps(served, indent=2), encoding="utf-8")
    L = ["# How often an activated flood-prone area floods", "",
         f"Generated {report['generated_utc']} by `scripts/active_area_chance.py`. DSDA archive "
         f"{report['period'][0]} to {report['period'][1]}, posts {', '.join(report['posts'])}. A pair = one day and "
         "one kecamatan holding a flood-prone point the post activates (same rule as the map). Rate = share of pairs "
         "with a BPBD flood record in that kecamatan that day; 95 % intervals resample days.", "",
         "| Post's highest status that day | Flood share | 95 % | Pairs | Days |", "|---|---|---|---|---|"]
    for level in (0, 1, 2, 3):
        x = report["by_level"][str(level)]
        L.append(f"| {LEVEL_NAMES.get(level, 'Normal')} | {x['rate']} | {x['ci95']} | {x['pairs']} | {x['days']} |")
    L += ["", "Per post (rate, pairs):", ""]
    for post, levels in report["by_post"].items():
        L.append(f"- {post}: " + "; ".join(f"{n} {v['rate']} ({v['pairs']})" for n, v in levels.items()))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "active_area_chance.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (REPORTS_DIR / "active_area_chance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
