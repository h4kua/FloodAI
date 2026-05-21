"""
Build kelurahan-level flood-event history from two component exports.

Inputs (HTML tables despite .xls extension):
  N2 data-kejadian-bencana-banjir-komponen-data.xls            (multi-period)
  N3 data-kejadian-bencana-banjir-tahun-2023-komponen-data.xls (2023)
Shared columns used: periode_data (YYYYMM), wilayah, kecamatan, kelurahan,
  jumlah_rata_rata_ketinggian_air, jumlah_kejadian, jumlah_jiwa_terdampak,
  jumlah_korban_meninggal, jumlah_korban_luka, jumlah_pengungsi

Output: app/data/kelurahan_flood_history.json
  - per-kelurahan aggregates (event count, casualties, years, max depth)
  - per-kota rollup (since VulnerabilityContext keys on kota)

Run:
    python scripts/build_kelurahan_flood_history.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SOURCES = [
    _PROJECT_ROOT / "data" / "raw" / "data-kejadian-bencana-banjir-komponen-data.xls",
    _PROJECT_ROOT / "data" / "raw" / "data-kejadian-bencana-banjir-tahun-2023-komponen-data.xls",
]
_DST = _PROJECT_ROOT / "data" / "bundled" / "kelurahan_flood_history.json"

_CANON = ["Jakarta Utara", "Jakarta Selatan", "Jakarta Pusat",
          "Jakarta Timur", "Jakarta Barat", "Kepulauan Seribu"]
_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _canon_kota(raw: str) -> str | None:
    text = (raw or "").strip().lower()
    for name in _CANON:
        if name.lower().split()[-1] in text and ("jakarta" in text or "seribu" in text):
            return name
    return None


def _max_cm(raw: str) -> float | None:
    nums = [float(n.replace(",", ".")) for n in _NUM_RE.findall(str(raw or ""))]
    return max(nums) if nums else None


def _num(v: str) -> float:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return 0.0


def _agg_factory() -> dict:
    return {
        "event_count": 0.0, "total_jiwa_terdampak": 0.0, "total_meninggal": 0.0,
        "total_luka": 0.0, "total_pengungsi": 0.0, "years": set(),
        "_heights": [], "kota": None, "kecamatan": None,
    }


def build() -> dict:
    per_kel: dict[str, dict] = defaultdict(_agg_factory)

    for src in _SOURCES:
        if not src.exists():
            continue
        soup = BeautifulSoup(src.read_text(encoding="utf-8", errors="replace"), "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            continue
        hdr = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
        idx = {h: i for i, h in enumerate(hdr)}

        def cell(c, key):
            return c[idx[key]] if key in idx and idx[key] < len(c) else ""

        for tr in rows[1:]:
            c = [x.get_text(strip=True) for x in tr.find_all(["td", "th"])]
            if len(c) < len(hdr):
                continue
            kel = cell(c, "kelurahan").strip().upper()
            if not kel:
                continue
            a = per_kel[kel]
            a["event_count"] += _num(cell(c, "jumlah_kejadian")) or 1
            a["total_jiwa_terdampak"] += _num(cell(c, "jumlah_jiwa_terdampak"))
            a["total_meninggal"] += _num(cell(c, "jumlah_korban_meninggal"))
            a["total_luka"] += _num(cell(c, "jumlah_korban_luka"))
            a["total_pengungsi"] += _num(cell(c, "jumlah_pengungsi"))
            periode = cell(c, "periode_data").strip()
            if len(periode) >= 4 and periode[:4].isdigit():
                a["years"].add(periode[:4])
            h = _max_cm(cell(c, "jumlah_rata_rata_ketinggian_air"))
            if h is not None:
                a["_heights"].append(h)
            if a["kota"] is None:
                a["kota"] = _canon_kota(cell(c, "wilayah"))
            if a["kecamatan"] is None:
                a["kecamatan"] = cell(c, "kecamatan").strip() or None

    kelurahan: dict[str, dict] = {}
    by_kota: dict[str, dict] = defaultdict(
        lambda: {"kelurahan_count": 0, "total_events": 0.0, "total_jiwa_terdampak": 0.0,
                 "total_meninggal": 0.0, "_worst": (None, -1.0)}
    )
    for kel, a in per_kel.items():
        ec = int(a["event_count"])
        kelurahan[kel] = {
            "event_count": ec,
            "total_jiwa_terdampak": int(a["total_jiwa_terdampak"]),
            "total_meninggal": int(a["total_meninggal"]),
            "total_luka": int(a["total_luka"]),
            "total_pengungsi": int(a["total_pengungsi"]),
            "years_covered": sorted(a["years"]),
            "max_ketinggian_cm": round(max(a["_heights"]), 1) if a["_heights"] else None,
            "kota": a["kota"],
            "kecamatan": a["kecamatan"],
        }
        if a["kota"]:
            r = by_kota[a["kota"]]
            r["kelurahan_count"] += 1
            r["total_events"] += ec
            r["total_jiwa_terdampak"] += a["total_jiwa_terdampak"]
            r["total_meninggal"] += a["total_meninggal"]
            if ec > r["_worst"][1]:
                r["_worst"] = (kel, ec)

    kota_out = {
        k: {
            "kelurahan_count": v["kelurahan_count"],
            "total_events": int(v["total_events"]),
            "total_jiwa_terdampak": int(v["total_jiwa_terdampak"]),
            "total_meninggal": int(v["total_meninggal"]),
            "worst_kelurahan": v["_worst"][0],
            "worst_kelurahan_events": int(v["_worst"][1]) if v["_worst"][1] >= 0 else 0,
        }
        for k, v in by_kota.items()
    }

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": [s.name for s in _SOURCES],
            "kelurahan_count": len(kelurahan),
        },
        "kelurahan": kelurahan,
        "by_kota": kota_out,
    }


def main() -> int:
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {payload['_meta']['kelurahan_count']} kelurahan -> {_DST}")
    for kota, d in payload["by_kota"].items():
        print(f"  {kota:18} kel={d['kelurahan_count']:3} events={d['total_events']:4} "
              f"worst={d['worst_kelurahan']} ({d['worst_kelurahan_events']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
