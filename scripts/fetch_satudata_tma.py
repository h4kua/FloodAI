#!/usr/bin/env python
"""
Download DSDA water-level readings 2016-2020 from Satu Data Jakarta (exploratory; nothing served).

Datasets "Data Tinggi Muka Air di DKI Jakarta Tahun 2016 ... 2020" (Dinas Sumber Daya Air): every
reading of every pintu air / pos, with the official status_siaga, several times an hour. The
portal's table API (POST /backend/api/v2/satudata/get-table-data, 5,000 rows a page) is read page
by page with a pause between requests; each page is cached in data/raw/satudata/<year>/ so an
interrupted run resumes. Columns kept: tanggal, nama_pintu_air, lokasi, tinggi_air, status_siaga.

Usage (repo root):  python scripts/fetch_satudata_tma.py [--years 2016 2017 2018 2019 2020]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "data" / "raw" / "satudata"
API = "https://satudata.jakarta.go.id/backend/api/v2/satudata/get-table-data"
PAGE_URLS = {
    2016: "data-tinggi-muka-air-di-dki-jakarta-tahun-2016",
    2017: "data-tinggi-muka-air-di-dki-jakarta-tahun-2017",
    2018: "data-tinggi-muka-air-di-dki-jakarta-tahun-2018",
    2019: "data-tinggi-muka-air-dki-jakarta-tahun-2019",
    2020: "data-tinggi-muka-air-di-provinsi-dki-jakarta-tahun-2020",
}
KEEP = ("tanggal", "nama_pintu_air", "lokasi", "tinggi_air", "status_siaga")
PER_PAGE = 5000
_HEADERS = {"User-Agent": "deFlood.ai thesis research script", "Content-Type": "application/json"}


def fetch_page(page_url: str, page: int) -> dict:
    body = {"page_url": page_url, "kategori": "dataset", "page": page, "per_page": PER_PAGE}
    for attempt in range(5):
        try:
            resp = requests.post(API, data=json.dumps(body), headers=_HEADERS, timeout=180)
            if resp.status_code == 200:
                return json.loads(resp.content.decode("utf-8-sig"))
        except (requests.RequestException, ValueError):
            pass
        time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"{page_url} page {page} failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--years", type=int, nargs="+", default=sorted(PAGE_URLS))
    args = parser.parse_args()
    for year in args.years:
        folder = OUT / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        first = fetch_page(PAGE_URLS[year], 1)
        pages = int(first["total_pages"])
        print(f"{year}: {first['total']} rows, {pages} pages", flush=True)
        for page in range(1, pages + 1):
            path = folder / f"page_{page:05d}.json"
            if path.exists():
                continue
            data = first if page == 1 else fetch_page(PAGE_URLS[year], page)
            rows = [{k: r.get(k) for k in KEEP} for r in data.get("data", [])]
            path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            if page % 20 == 0:
                print(f"  {year} page {page}/{pages}", flush=True)
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
