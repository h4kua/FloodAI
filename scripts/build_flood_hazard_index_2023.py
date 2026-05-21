"""
Build the 2023 flood hazard index dataset (per kelurahan + per-kota aggregate).

Input : data/raw/indeks-bahaya-banjir-tahun-2023-komponen-data.xls (HTML table)
        Confirmed columns: periode_data, wilayah, kecamatan, kelurahan,
        nilai_indeks_bahaya_banjir, kategori_indeks_bahaya_banjir
        Observed: value range ~1.4-2.4; categories RENDAH/SEDANG/TINGGI.
        Only kelurahan with a recorded hazard appear (116 rows).
Output: app/data/flood_hazard_index_2023.json

Run:
    python scripts/build_flood_hazard_index_2023.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "indeks-bahaya-banjir-tahun-2023-komponen-data.xls"
_DST = _PROJECT_ROOT / "data" / "bundled" / "flood_hazard_index_2023.json"

_CANON = ["Jakarta Utara", "Jakarta Selatan", "Jakarta Pusat",
          "Jakarta Timur", "Jakarta Barat", "Kepulauan Seribu"]


def _canon_kota(raw: str) -> str | None:
    text = (raw or "").strip().lower()
    for name in _CANON:
        if name.lower().split()[-1] in text and ("jakarta" in text or "seribu" in text):
            return name
    return None


def _f(v: str) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def build() -> dict:
    soup = BeautifulSoup(_SRC.read_text(encoding="utf-8", errors="replace"), "html.parser")
    rows = soup.find_all("tr")
    hdr = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    idx = {h: i for i, h in enumerate(hdr)}

    kelurahan: dict[str, dict] = {}
    per_kota: dict[str, dict] = defaultdict(lambda: {"values": [], "cats": Counter()})

    for tr in rows[1:]:
        c = [x.get_text(strip=True) for x in tr.find_all(["td", "th"])]
        if len(c) < len(hdr):
            continue
        kota = _canon_kota(c[idx["wilayah"]])
        kel = c[idx["kelurahan"]].strip()
        val = _f(c[idx["nilai_indeks_bahaya_banjir"]])
        cat = c[idx["kategori_indeks_bahaya_banjir"]].strip()
        if not kel or val is None:
            continue
        kelurahan[kel.upper()] = {
            "index": val,
            "category": cat,
            "kota": kota,
            "kecamatan": c[idx["kecamatan"]].strip(),
        }
        if kota:
            per_kota[kota]["values"].append(val)
            per_kota[kota]["cats"][cat] += 1

    kota_out: dict[str, dict] = {}
    for kota, agg in per_kota.items():
        vals = agg["values"]
        kota_out[kota] = {
            "avg_index": round(sum(vals) / len(vals), 4) if vals else None,
            "max_index": round(max(vals), 4) if vals else None,
            "kelurahan_count": len(vals),
            "by_category": dict(agg["cats"]),
            "dominant_category": agg["cats"].most_common(1)[0][0] if agg["cats"] else None,
        }

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/indeks-bahaya-banjir-tahun-2023-komponen-data.xls",
            "kelurahan_count": len(kelurahan),
            "note": "Only flood-hazard-rated kelurahan are listed. Index scale per source (~1-3).",
        },
        "kota": kota_out,
        "kelurahan": kelurahan,
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote 2023 hazard index: {payload['_meta']['kelurahan_count']} kelurahan -> {_DST}")
    for kota, d in payload["kota"].items():
        print(f"  {kota:18} avg={d['avg_index']} max={d['max_index']} dom={d['dominant_category']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
