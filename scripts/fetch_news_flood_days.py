#!/usr/bin/env python
"""
Flood days in Jakarta 2023-2025 from news reports that quote BPBD (exploratory; nothing served).

BPBD's own dates are only partly readable after 2022 (scripts/hourly_rain_experiment.py). Jakarta
newsrooms report the BPBD flood list on the day ("14 RT di Jakarta masih tergenang ..."), so the
detik.com search (date filter, newest first) is read month by month for a few queries, reports of a
flood that happened are kept (titles about a forecast, a warning or another city are dropped), and each
article is read for the kelurahan and kecamatan it names, mapped to the 42 model kecamatan with the
BPBD place lists (events_clean.csv, rekap_kejadian_2020_2025.csv). The publication date (WIB) is taken
as the flood date.

Cached in data/raw/news/ (search pages and articles, so a rerun resumes); writes
data/processed/news_flood_reports_2023_2025.csv (date, url, title, kecamatan, kelurahan).
Polite: one request every 1.5 s, a plain User-Agent.

Usage (repo root):  python scripts/fetch_news_flood_days.py [--start 2023-01] [--end 2025-12]
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from scripts.build_kelurahan_flood_history import _CANONICAL_BY_SLUG, _slug  # noqa: E402

CACHE = _ROOT / "data" / "raw" / "news"
OUT = _ROOT / "data" / "processed" / "news_flood_reports_2023_2025.csv"
SEARCH = "https://www.detik.com/search/searchall"
QUERIES = ["RT tergenang", "RT terendam banjir", "banjir Jakarta kelurahan", "genangan Jakarta BPBD"]
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) deFlood.ai thesis research"}
WIB = timezone(timedelta(hours=7))
FLOOD = re.compile(r"(?i)tergenang|terendam|kebanjiran|\bbanjir\b|genangan")
NOT_EVENT = re.compile(r"(?i)potensi|waspada|prakiraan|peringatan|antisipasi|siaga bencana|imbau|cegah|rencana|anggaran"
                       r"|bekasi|tangerang|depok|bogor|semarang|bandung|surabaya|banten|jawa")
JAKARTA = re.compile(r"(?i)jakarta|\bdki\b|jakut|jaksel|jaktim|jakbar|jakpus")
INFRA = re.compile(r"(?i)\b(?:pos|pintu air|p\.\s?a\.|p\.\s?s\.|bendung(?:an)?|kali|sungai|waduk|pompa|rumah pompa|"
                   r"banjir kanal(?: barat| timur)?)\s+\w+(?:\s+\w+)?")


def _get(url: str, params: dict | None = None) -> str:
    for attempt in range(4):
        try:
            resp = requests.get(url, params=params, headers=_UA, timeout=60)
            if resp.status_code == 200:
                return resp.text
        except requests.RequestException:
            pass
        time.sleep(10 * (attempt + 1))
    return ""


def _cached(name: str, fetch) -> str:
    path = CACHE / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    text = fetch()
    path.write_text(text, encoding="utf-8")
    time.sleep(1.5)
    return text


def search_month(query: str, month: pd.Period) -> list[dict]:
    rows, page = [], 1
    start, end = month.start_time, month.end_time
    while page <= 10:
        params = {"query": query, "sortby": "time", "page": page,
                  "fromdatex": start.strftime("%d/%m/%Y"), "todatex": end.strftime("%d/%m/%Y")}
        key = hashlib.md5(repr(sorted(params.items())).encode()).hexdigest()[:16]
        text = _cached(f"search_{month}_{key}.html", lambda: _get(SEARCH, params))
        arts = re.findall(r'<article class="list-content__item">(.*?)</article>', text, re.S)
        if not arts:
            break
        for a in arts:
            link = re.search(r'href="(https://[^"]+)"', a)
            title = re.search(r'dtr-ttl="([^"]*)"', a)
            ts = re.search(r'd-time="(\d+)"', a)
            if link and title and ts:
                rows.append({"url": link.group(1), "title": html.unescape(title.group(1)),
                             "date": datetime.fromtimestamp(int(ts.group(1)), WIB).date()})
        page += 1
    return rows


def place_index() -> dict[str, str]:
    """Kelurahan or kecamatan name (lower case) -> model kecamatan slug."""
    events = pd.read_csv(_ROOT / "data" / "processed" / "events_clean.csv", usecols=["kecamatan", "kelurahan"])
    rekap = pd.read_csv(_ROOT / "data" / "raw" / "rekap_kejadian_2020_2025.csv", usecols=["kecamatan", "kelurahan"])
    rows = pd.concat([events, rekap]).dropna()
    rows = rows.assign(kel=rows["kelurahan"].str.strip().str.lower(), slug=rows["kecamatan"].map(lambda k: _slug(str(k))))
    # A few BPBD rows file a kelurahan under the wrong kecamatan (Kampung Melayu under Duren Sawit):
    # each kelurahan takes the kecamatan it is filed under most often.
    kel = rows.groupby(["kel", "slug"]).size().reset_index(name="n").sort_values("n", ascending=False)
    names = dict(zip(kel.drop_duplicates("kel")["kel"], kel.drop_duplicates("kel")["slug"]))
    names.update({str(k).strip().lower(): _slug(str(k)) for k in rows["kecamatan"].unique()})
    return {k: v for k, v in names.items() if len(k) >= 5 and v in _CANONICAL_BY_SLUG}


def article_text(url: str) -> str:
    key = hashlib.md5(url.encode()).hexdigest()[:16]
    raw = _cached(f"article_{key}.html", lambda: _get(url))
    body = re.search(r'<div class="detail__body-text[^"]*">(.*?)<div class="detail__body-tag', raw, re.S)
    text = body.group(1) if body else raw
    # "Baca juga" boxes link other stories (another kelurahan, another day): drop them, scripts and ads too.
    text = re.sub(r'<table class="linksisip".*?</table>|<script.*?</script>|<style.*?</style>', " ", text, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    # Water posts and rivers share names with kelurahan (Pintu Air Manggarai, Pos Pesanggrahan): not flooded places.
    return INFRA.sub(" ", text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--start", default="2023-01")
    parser.add_argument("--end", default="2025-12")
    parser.add_argument("--out", default=str(OUT), help="output CSV")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    CACHE.mkdir(parents=True, exist_ok=True)

    found = {}
    for month in pd.period_range(args.start, args.end, freq="M"):
        n = 0
        for q in QUERIES:
            for r in search_month(q, month):
                if FLOOD.search(r["title"]) and not NOT_EVENT.search(r["title"]) and r["url"] not in found:
                    found[r["url"]] = r
                    n += 1
        print(f"{month}: {n} candidate reports", flush=True)

    index = place_index()
    pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, index), key=len, reverse=True)) + r")\b", re.I)
    rows = []
    for r in found.values():
        text = article_text(r["url"])
        if not JAKARTA.search(r["title"] + " " + text[:600]):
            continue
        places = {m.lower() for m in pattern.findall(text)}
        for kec in sorted({index[p] for p in places}):
            rows.append({**r, "kecamatan": kec, "kelurahan": ", ".join(sorted(p for p in places if index[p] == kec))})
    out = pd.DataFrame(rows, columns=["date", "url", "title", "kecamatan", "kelurahan"])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"{len(found)} reports, {out['url'].nunique()} with a model kecamatan, "
          f"{out[['date', 'kecamatan']].drop_duplicates().shape[0]} kecamatan-days -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
