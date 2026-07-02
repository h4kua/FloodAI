"""
Build kelurahan-level flood-event history from three component exports.

Inputs:
  N2 data-kejadian-bencana-banjir-komponen-data.xls            (HTML table, multi-period)
  N3 data-kejadian-bencana-banjir-tahun-2023-komponen-data.xls (HTML table, 2023)
  N4 rekap_kejadian_2020_2025.csv (row-per-incident, built by
     scripts/parse_rekap_kejadian_banjir.py from the "01 REKAP KEJADIAN BANJIR
     PERTAHUN" workbooks) — covers 2020-2025 at finer granularity than N2/N3,
     so N2/N3 rows for those years are skipped in favour of N4 (dedup by year).

Shared columns used from N2/N3: periode_data (YYYYMM), wilayah, kecamatan,
  kelurahan, jumlah_rata_rata_ketinggian_air, jumlah_kejadian,
  jumlah_jiwa_terdampak, jumlah_korban_meninggal, jumlah_korban_luka,
  jumlah_pengungsi
Columns used from N4: kota_administrasi, kecamatan, kelurahan, tahun,
  ketinggian_air, jumlah_meninggal, jumlah_luka_ringan, jumlah_luka_berat,
  jumlah_tempat_pengungsian

Output: data/bundled/kelurahan_flood_history.json
  - per-kelurahan aggregates (event count, casualties, years, max depth)
  - per-kota rollup (since VulnerabilityContext keys on kota)
  - per-kecamatan rollup with a normalized historical_flood_frequency (0-1),
    keyed by a slug matching realtime_native's name_3 format (see
    realtime_native/feature_builder.py) so it can be joined into ML training.

Run:
    python scripts/build_kelurahan_flood_history.py
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_HTML_SOURCES = [
    _PROJECT_ROOT / "data" / "raw" / "data-kejadian-bencana-banjir-komponen-data.xls",
    _PROJECT_ROOT / "data" / "raw" / "data-kejadian-bencana-banjir-tahun-2023-komponen-data.xls",
]
_REKAP_CSV = _PROJECT_ROOT / "data" / "raw" / "rekap_kejadian_2020_2025.csv"
# Years the CSV covers at finer granularity — HTML-source rows for these years
# are skipped so the two sources don't double-count the same incidents.
_REKAP_COVERED_YEARS = {"2020", "2021", "2022", "2023", "2024", "2025"}
_DST = _PROJECT_ROOT / "data" / "bundled" / "kelurahan_flood_history.json"

_CANON = ["Jakarta Utara", "Jakarta Selatan", "Jakarta Pusat",
          "Jakarta Timur", "Jakarta Barat", "Kepulauan Seribu"]
_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")

# The 42 kecamatan realtime_native's training data (name_3) is keyed on —
# Kepulauan Seribu has no water-level stations and isn't in that set.
_CANONICAL_KECAMATAN = [
    "Gambir", "Sawah Besar", "Kemayoran", "Senen", "Cempaka Putih", "Menteng",
    "Tanah Abang", "Johar Baru",
    "Penjaringan", "Pademangan", "Tanjung Priok", "Koja", "Kelapa Gading", "Cilincing",
    "Cengkareng", "Kalideres", "Kebon Jeruk", "Kembangan", "Grogol Petamburan",
    "Taman Sari", "Tambora", "Palmerah",
    "Matraman", "Pulo Gadung", "Jatinegara", "Duren Sawit", "Kramat Jati", "Cakung",
    "Pasar Rebo", "Ciracas", "Cipayung", "Makasar",
    "Tebet", "Setiabudi", "Mampang Prapatan", "Pasar Minggu", "Cilandak",
    "Kebayoran Baru", "Kebayoran Lama", "Pesanggrahan", "Jagakarsa", "Pancoran",
]
# Known source typos/abbreviations that don't slug-match the canonical list directly.
_KECAMATAN_SLUG_ALIASES = {
    "ciliincing": "cilincing",
    "mampang": "mampangprapatan",
}


def _slug(text: str) -> str:
    """Lowercase, strip a leading kec./kecamatan prefix, drop all non-alphanumerics.
    Matches realtime_native's name_3 format (e.g. "Tanah Abang" -> "tanahabang")."""
    cleaned = re.sub(r"^(kec\.?|kecamatan)\s+", "", (text or "").strip().lower())
    slug = re.sub(r"[^a-z0-9]", "", cleaned)
    return _KECAMATAN_SLUG_ALIASES.get(slug, slug)


_CANONICAL_BY_SLUG = {_slug(name): name for name in _CANONICAL_KECAMATAN}


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


def _load_html_sources(per_kel: dict[str, dict]) -> None:
    for src in _HTML_SOURCES:
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
            periode = cell(c, "periode_data").strip()
            year = periode[:4] if len(periode) >= 4 and periode[:4].isdigit() else None
            if year in _REKAP_COVERED_YEARS:
                continue  # superseded by the finer-grained REKAP CSV for this year
            a = per_kel[kel]
            a["event_count"] += _num(cell(c, "jumlah_kejadian")) or 1
            a["total_jiwa_terdampak"] += _num(cell(c, "jumlah_jiwa_terdampak"))
            a["total_meninggal"] += _num(cell(c, "jumlah_korban_meninggal"))
            a["total_luka"] += _num(cell(c, "jumlah_korban_luka"))
            a["total_pengungsi"] += _num(cell(c, "jumlah_pengungsi"))
            if year:
                a["years"].add(year)
            h = _max_cm(cell(c, "jumlah_rata_rata_ketinggian_air"))
            if h is not None:
                a["_heights"].append(h)
            if a["kota"] is None:
                a["kota"] = _canon_kota(cell(c, "wilayah"))
            if a["kecamatan"] is None:
                a["kecamatan"] = cell(c, "kecamatan").strip() or None


_KEL_PREFIX_RE = re.compile(r"^(kel\.?|kelurahan)\s+", re.IGNORECASE)


def _load_rekap_csv(per_kel: dict[str, dict]) -> None:
    if not _REKAP_CSV.exists():
        return
    with open(_REKAP_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            kel = _KEL_PREFIX_RE.sub("", (row.get("kelurahan") or "").strip()).strip().upper()
            if not kel:
                continue
            a = per_kel[kel]
            a["event_count"] += 1
            a["total_meninggal"] += _num(row.get("jumlah_meninggal"))
            a["total_luka"] += _num(row.get("jumlah_luka_ringan")) + _num(row.get("jumlah_luka_berat"))
            a["total_pengungsi"] += _num(row.get("jumlah_tempat_pengungsian"))
            tahun = (row.get("tahun") or "").strip()
            if tahun:
                a["years"].add(tahun)
            h = _max_cm(row.get("ketinggian_air"))
            if h is not None:
                a["_heights"].append(h)
            if a["kota"] is None:
                a["kota"] = _canon_kota(row.get("kota_administrasi"))
            if a["kecamatan"] is None:
                a["kecamatan"] = (row.get("kecamatan") or "").strip() or None


def build() -> dict:
    per_kel: dict[str, dict] = defaultdict(_agg_factory)
    _load_html_sources(per_kel)
    _load_rekap_csv(per_kel)

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

    by_kecamatan = _build_kecamatan_rollup(kelurahan)

    return {
        "_meta": {
            "schema_version": "2",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": [s.name for s in _HTML_SOURCES] + [_REKAP_CSV.name],
            "kelurahan_count": len(kelurahan),
            "kecamatan_count": len(by_kecamatan),
        },
        "kelurahan": kelurahan,
        "by_kota": kota_out,
        "by_kecamatan": by_kecamatan,
    }


def _build_kecamatan_rollup(kelurahan: dict[str, dict]) -> dict[str, dict]:
    """Aggregate per-kelurahan records up to kecamatan level, keyed by a slug
    matching realtime_native's name_3 format. Unmapped kecamatan (typos we
    don't recognise, or Kepulauan Seribu which has no name_3 counterpart) are
    kept under their raw slug so nothing is silently dropped, but only slugs
    matching _CANONICAL_KECAMATAN will actually join into ML training."""
    agg: dict[str, dict] = defaultdict(
        lambda: {"event_count": 0, "kelurahan_count": 0, "years": set(), "_heights": [],
                  "display_name": None, "kota": None}
    )
    for kel, rec in kelurahan.items():
        raw_kec = rec.get("kecamatan")
        if not raw_kec:
            continue
        slug = _slug(raw_kec)
        a = agg[slug]
        a["event_count"] += rec["event_count"]
        a["kelurahan_count"] += 1
        a["years"].update(rec["years_covered"])
        if rec["max_ketinggian_cm"] is not None:
            a["_heights"].append(rec["max_ketinggian_cm"])
        if a["display_name"] is None:
            a["display_name"] = _CANONICAL_BY_SLUG.get(slug, raw_kec)
        if a["kota"] is None:
            a["kota"] = rec.get("kota")

    max_events = max((a["event_count"] for a in agg.values()), default=1) or 1
    return {
        slug: {
            "kecamatan": a["display_name"],
            "kota": a["kota"],
            "kelurahan_count": a["kelurahan_count"],
            "event_count": a["event_count"],
            "years_covered": sorted(a["years"]),
            "max_ketinggian_cm": round(max(a["_heights"]), 1) if a["_heights"] else None,
            "historical_flood_frequency": round(a["event_count"] / max_events, 4),
        }
        for slug, a in agg.items()
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
