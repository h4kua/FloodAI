"""
Build per-district historical flood statistics from combined.csv.

Input : data/raw/combined.csv  (2013-2020 Jakarta flood events; per-row
        kota_administrasi / kecamatan / kelurahan with month, water height,
        and casualty columns). Confirmed columns:
          kota_administrasi, kecamatan, kelurahan, rw, tahun, bulan,
          lama_genangan, tanggal_kejadian, jumlah_tempat_pengungsian,
          jumlah_luka_ringan, jumlah_luka_berat, ketinggian_air, jumlah_meninggal

NOTE: The data-rekapitulasi-*.csv files are monthly *city-wide aggregates*
(the "kecamatan" column there is a COUNT, not a district name), so they cannot
yield per-district frequency. combined.csv is the only per-district source.

Output: app/data/historical_flood_events.json

Run:
    python scripts/build_historical_flood_events.py
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "combined.csv"
_DST = _PROJECT_ROOT / "data" / "bundled" / "historical_flood_events.json"

# Canonical DKI kota + tolerant matching for source typos ("Jakara Barat", etc.).
_CANONICAL = ["Jakarta Utara", "Jakarta Selatan", "Jakarta Pusat",
              "Jakarta Timur", "Jakarta Barat", "Kepulauan Seribu"]

# Severity normalisation references (cm). 300 cm ~ severe inundation.
_SEVERITY_REF_CM = 300.0
_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _canonical_kota(raw: str) -> str | None:
    text = (raw or "").strip().lower().replace("jakara", "jakarta").replace("urata", "utara")
    for name in _CANONICAL:
        if text == name.lower():
            return name
    # Tolerant: match on the distinctive second token (utara/selatan/...).
    for name in _CANONICAL:
        token = name.lower().split()[-1]
        if token in text and ("jakarta" in text or token == "seribu"):
            return name
    return None


def _height_cm(raw: str) -> float | None:
    """Parse 'ketinggian_air' like '20 - 250' or '95' -> representative cm (max bound)."""
    nums = [float(n.replace(",", ".")) for n in _NUM_RE.findall(str(raw or ""))]
    return max(nums) if nums else None


def _to_float(raw: str) -> float:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return 0.0


def build() -> dict:
    per_kota: dict[str, dict] = defaultdict(
        lambda: {
            "event_count": 0,
            "years": set(),
            "by_month": Counter(),
            "_heights": [],
            "total_meninggal": 0.0,
            "total_luka": 0.0,
        }
    )
    citywide_month = Counter()
    skipped = 0

    with open(_SRC, encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            kota = _canonical_kota(row.get("kota_administrasi", ""))
            if kota is None:
                skipped += 1
                continue
            agg = per_kota[kota]
            agg["event_count"] += 1
            year = (row.get("tahun") or "").strip()
            if year:
                agg["years"].add(year)
            month = (row.get("bulan") or "").strip()
            if month.isdigit():
                agg["by_month"][int(month)] += 1
                citywide_month[int(month)] += 1
            h = _height_cm(row.get("ketinggian_air"))
            if h is not None:
                agg["_heights"].append(h)
            agg["total_meninggal"] += _to_float(row.get("jumlah_meninggal"))
            agg["total_luka"] += _to_float(row.get("jumlah_luka_berat")) + _to_float(
                row.get("jumlah_luka_ringan")
            )

    # Normalise frequency against the busiest district so scores are comparable.
    max_events = max((a["event_count"] for a in per_kota.values()), default=1) or 1

    districts: dict[str, dict] = {}
    for kota, agg in per_kota.items():
        heights = agg["_heights"]
        avg_h = round(sum(heights) / len(heights), 1) if heights else None
        max_h = round(max(heights), 1) if heights else None
        n_years = len(agg["years"]) or 1
        # Severity: blend mean inundation depth with a small fatality weight, clamp [0,1].
        depth_component = min((avg_h or 0.0) / _SEVERITY_REF_CM, 1.0)
        fatality_component = min(agg["total_meninggal"] / 50.0, 1.0)
        severity = round(0.8 * depth_component + 0.2 * fatality_component, 4)
        districts[kota] = {
            "event_count": agg["event_count"],
            "years_covered": sorted(agg["years"]),
            "events_per_year": round(agg["event_count"] / n_years, 2),
            "by_month": {str(m): c for m, c in sorted(agg["by_month"].items())},
            "avg_ketinggian_cm": avg_h,
            "max_ketinggian_cm": max_h,
            "total_meninggal": int(agg["total_meninggal"]),
            "total_luka": int(agg["total_luka"]),
            "historical_flood_frequency": round(agg["event_count"] / max_events, 4),
            "avg_severity_historical": severity,
        }

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/combined.csv (DKI flood events 2013-2020)",
            "rows_skipped_unmapped": skipped,
            "frequency_basis": "event_count normalised to the busiest district (=1.0)",
            "severity_basis": "0.8*min(avg_depth/300cm,1) + 0.2*min(fatalities/50,1)",
        },
        "districts": districts,
        "citywide_by_month": {str(m): c for m, c in sorted(citywide_month.items())},
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload['districts'])} districts -> {_DST}")
    for kota, d in payload["districts"].items():
        print(f"  {kota:18} events={d['event_count']:4}  freq={d['historical_flood_frequency']:.2f}  sev={d['avg_severity_historical']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
