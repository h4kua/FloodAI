"""
Build a national age-structure vulnerability proxy.

DATA REALITY: The provided CSV
  "Jumlah Penduduk Menurut Kelompok Umur dan Jenis Kelamin, 2026.csv"
is the NATIONAL Indonesia population projection by age group (total ~287M, per
the note "Proyeksi Penduduk Indonesia 2020-2050"). It is NOT Jakarta and NOT
per-district, so it cannot provide per-district Jakarta population. We therefore
derive only a NATIONAL age-structure vulnerability proxy (share of elderly and
children, who are higher-vulnerability in floods) and clearly scope it as such.
The per-kota census figures already in bnpb_jakarta_fallback.json remain the
authoritative population source and are NOT overwritten.

Output: app/data/population_age_structure.json

Run:
    python scripts/build_population_age_structure.py
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "Jumlah Penduduk Menurut Kelompok Umur dan Jenis Kelamin, 2026.csv"
_DST = _PROJECT_ROOT / "data" / "bundled" / "population_age_structure.json"

# Excel coerced some age labels into dates: "4/1/00"->0-4, "5/9/01"->5-9,
# "10/14/01"->10-14. Map the lower bound of each age band for classification.
_LOWER_BOUND = {
    "4/1/00": 0, "5/9/01": 5, "10/14/01": 10,
    "15-19": 15, "20-24": 20, "25-29": 25, "30-34": 30, "35-39": 35,
    "40-44": 40, "45-49": 45, "50-54": 50, "55-59": 55, "60-64": 60,
    "65-69": 65, "70-74": 70, "75+": 75,
}


def _to_float(v: str) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", v or "") or 0.0)
    except ValueError:
        return 0.0


def build() -> dict:
    children = elderly = working = total = 0.0
    with open(_SRC, encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.reader(fh):
            if len(row) < 4:
                continue
            label = row[0].strip()
            if label not in _LOWER_BOUND:
                continue
            both = _to_float(row[3])  # Laki + Perempuan (Ribu = thousands)
            total += both
            lb = _LOWER_BOUND[label]
            if lb < 15:
                children += both
            elif lb >= 65:
                elderly += both
            else:
                working += both

    total = total or 1.0
    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": "NATIONAL (Indonesia) — NOT per-district Jakarta",
            "source": "BPS Proyeksi Penduduk Indonesia 2020-2050 (age structure)",
            "caveat": "Use only as a generic age-vulnerability proxy. Authoritative per-kota population lives in bnpb_jakarta_fallback.json and must not be replaced by this national data.",
        },
        "total_thousand": round(total, 1),
        "vulnerability_shares": {
            "children_0_14": round(children / total, 4),
            "elderly_65_plus": round(elderly / total, 4),
            "working_15_64": round(working / total, 4),
            "high_vulnerability_share": round((children + elderly) / total, 4),
        },
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    s = payload["vulnerability_shares"]
    print(f"Wrote national age-structure proxy -> {_DST}")
    print(f"  children_0_14={s['children_0_14']}  elderly_65_plus={s['elderly_65_plus']}  "
          f"high_vuln={s['high_vulnerability_share']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
