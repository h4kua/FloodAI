#!/usr/bin/env python
"""
Clean the DSDA water-level readings 2016-2020 (scripts/fetch_satudata_tma.py) into one row per post
per WIB day (exploratory; nothing served).

Per reading: the timestamp (dd/mm/yyyy HH:MM, yyyy-mm-dd HH:MM:SS or dd/mm/yyyy; readings without a
date are dropped), the post, the water level (the files give millimetres; stored in cm) and the
official status_siaga ("STATUS : SIAGA 3" and "SIAGA 3" both -> 1; Siaga 2 -> 2; Siaga 1 -> 3;
Normal -> 0). Per post and day: highest status, highest and mean level, number of readings.
Posts on the sea or a tidal outlet (laut, Marina, Pasar Ikan, Tanjungan, Marunda, Ancol) are marked
coastal: they follow the tide, not the rivers.

Writes data/processed/dsda_tma_daily_2016_2020.csv (the 2020 dataset also holds Aug-Dec 2021) and prints a coverage summary per year.
Usage (repo root):  python scripts/dsda_history.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
RAW = _ROOT / "data" / "raw" / "satudata"
OUT = _ROOT / "data" / "processed" / "dsda_tma_daily_2016_2020.csv"
COASTAL_WORDS = ("LAUT", "MARINA", "PASARIKAN", "TANJUNGAN", "MARUNDA", "ANCOL")
STATUS = {"NORMAL": 0, "SIAGA 3": 1, "SIAGA 2": 2, "SIAGA 1": 3}


def post_key(name: str) -> str:
    """'P.A. MANGGARAI' / 'PS. MANGGARAI' -> 'MANGGARAI'; 'PS. KATULAMPA (HULU)' -> 'KATULAMPA'."""
    key = re.sub(r"[^A-Z0-9]", "", (name or "").upper())
    key = re.sub(r"^(PINTUAIR|POSKO|POMPA|PA|PS)", "", key)
    key = re.sub(r"^(BENDUNG|PHB)", "", key)
    key = key.replace("KATULAMPAHULU", "KATULAMPA").replace("ISTIQAL", "ISTIQLAL").replace("LAUTP", "LAUT")
    # One post, several names over the years.
    aliases = {"FLUSHINGANCOL": "ANCOLFLUSHING", "ANCOLFLUSING": "ANCOLFLUSHING", "CIDENGSIANTAR": "CIDENG",
               "PASARIKANLAUT": "PASARIKAN", "TANJUNGANLAUT": "TANJUNGAN", "MARUNDALAUT": "MARUNDA"}
    return aliases.get(key, key)


def status_level(text: str | None) -> float:
    if not text:
        return np.nan
    t = re.sub(r"^STATUS\s*:\s*", "", text.strip().upper())
    return float(STATUS[t]) if t in STATUS else np.nan


def parse_time(text: str | None) -> pd.Timestamp | None:
    if not text or text.startswith("0000"):
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return pd.to_datetime(text, format=fmt)
        except ValueError:
            continue
    return None


def load_year(year: int) -> tuple[pd.DataFrame, dict]:
    rows = []
    for path in sorted((RAW / str(year)).glob("page_*.json")):
        rows += json.loads(path.read_text(encoding="utf-8"))
    frame = pd.DataFrame(rows)
    frame["time"] = [parse_time(t) for t in frame["tanggal"]]
    frame["status"] = [status_level(s) for s in frame["status_siaga"]]
    frame["level_cm"] = pd.to_numeric(frame["tinggi_air"], errors="coerce") / 10.0
    frame["post"] = [post_key(n) for n in frame["nama_pintu_air"]]
    info = {"readings": int(len(frame)), "no_date": int(frame["time"].isna().sum()),
            "unknown_status": int(frame["status"].isna().sum())}
    frame = frame.dropna(subset=["time"])
    # The 2020 dataset also holds Aug-Dec 2021; dates outside 2016-2021 are typos (e.g. 2029).
    frame = frame[frame["time"].dt.year.between(2016, 2021)]
    info["kept"] = int(len(frame))
    return frame[["time", "post", "level_cm", "status"]], info


def daily(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.assign(date=frame["time"].dt.floor("D"))
    out = frame.groupby(["post", "date"]).agg(status_max=("status", "max"), level_max=("level_cm", "max"),
                                              level_mean=("level_cm", "mean"), readings=("status", "size"))
    out = out.reset_index()
    out["coastal"] = out["post"].apply(lambda p: any(w in p for w in COASTAL_WORDS)).astype(int)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    frames = []
    for year in range(2016, 2021):
        frame, info = load_year(year)
        frames.append(frame)
        print(f"{year} file: {info}", flush=True)
    readings = pd.concat(frames, ignore_index=True).drop_duplicates()
    data = daily(readings)
    for year, g in data.groupby(data["date"].dt.year):
        print(f"{year}: {g['date'].nunique()} days, {g['post'].nunique()} posts, "
              f"first {g['date'].min():%Y-%m-%d}, last {g['date'].max():%Y-%m-%d}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(data)} rows)")
    cover = data.groupby("post")["date"].agg(["min", "max", "nunique"]).sort_values("nunique", ascending=False)
    print(cover.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
