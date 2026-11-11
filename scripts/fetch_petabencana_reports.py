#!/usr/bin/env python
"""
Download PetaBencana.id crowdsourced flood reports for Jakarta (exploratory; nothing served).

Endpoint (docs: github.com/petabencana/petabencana-docs, routes-1/archive-reports.md):
  GET https://api.petabencana.id/archive/reports?start=...&end=...&geoformat=geojson&admin=ID-JK
  header X-Api-Key: <key>, plus a User-Agent. Reports are unverified (residents' posts and partner
  feeds), each with created_at, a point and the local area.
The key is read from .env as PETABENCANA_API_KEY and never printed; ask info@petabencana.id for one.
One week per request, a pause between requests; each week is cached in data/raw/petabencana/ so a
run resumes. A combined CSV (created_at, lon, lat, source, status, local_area_id, text) is written to
data/raw/petabencana/reports.csv.

Usage (repo root):  python scripts/fetch_petabencana_reports.py [--start 2017-01-01] [--end 2025-12-31]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "data" / "raw" / "petabencana"
API = "https://api.petabencana.id/archive/reports"
_UA = "deFlood.ai thesis research script"


def fetch_week(key: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    params = {"start": start.strftime("%Y-%m-%dT%H:%M:%S+0700"), "end": end.strftime("%Y-%m-%dT%H:%M:%S+0700"),
              "geoformat": "geojson", "admin": "ID-JK", "disaster": "flood"}
    for attempt in range(4):
        resp = requests.get(API, params=params, headers={"X-Api-Key": key, "User-Agent": _UA}, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (401, 403):
            raise SystemExit(f"PetaBencana refused the key (HTTP {resp.status_code}).")
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"{start:%Y-%m-%d}: HTTP {resp.status_code}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--start", default="2017-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass
    key = os.getenv("PETABENCANA_API_KEY", "").strip()
    if not key:
        print("PETABENCANA_API_KEY is not set in .env (ask info@petabencana.id for a key).")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    weeks = pd.date_range(args.start, args.end, freq="7D")
    for start in weeks:
        path = OUT / f"week_{start:%Y%m%d}.json"
        if path.exists():
            continue
        end = start + pd.Timedelta(days=7) - pd.Timedelta(seconds=1)
        data = fetch_week(key, start, end)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        n = len(((data.get("result") or {}).get("features")) or [])
        print(f"{start:%Y-%m-%d}: {n} reports", flush=True)
        time.sleep(2)

    rows = []
    for path in sorted(OUT.glob("week_*.json")):
        for f in ((json.loads(path.read_text(encoding="utf-8")).get("result") or {}).get("features") or []):
            p, g = f.get("properties", {}), f.get("geometry") or {}
            lon, lat = (g.get("coordinates") or [None, None])[:2]
            rows.append({"created_at": p.get("created_at"), "lon": lon, "lat": lat, "source": p.get("source"),
                         "status": p.get("status"), "local_area_id": (p.get("tags") or {}).get("local_area_id"),
                         "text": (p.get("text") or "").replace("\n", " ")[:300]})
    with open(OUT / "reports.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["created_at", "lon", "lat", "source", "status", "local_area_id", "text"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} reports -> {OUT / 'reports.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
