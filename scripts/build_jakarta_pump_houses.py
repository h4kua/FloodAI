"""
Build the Jakarta pump-house dataset from the BPBD/SDA component export.

Input : data/raw/data-lokasi-rumah-pompa-komponen-data.xls  (HTML table)
        Confirmed columns: periode_data, wilayah, kecamatan, kelurahan, lokasi,
        alamat, kewenangan, jumlah_pompa, total_kapasitas, lintang, bujur
Output: app/data/jakarta_pump_houses.json

`total_kapasitas` is the source figure as published (small values ~0.07-2.0);
the unit is not stated in the export, so it is stored verbatim as
``total_capacity`` without asserting m3/s vs m3/h.

Run:
    python scripts/build_jakarta_pump_houses.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "data-lokasi-rumah-pompa-komponen-data.xls"
_DST = _PROJECT_ROOT / "data" / "bundled" / "jakarta_pump_houses.json"

_LAT_RANGE = (-7.0, -5.5)
_LON_RANGE = (106.0, 107.5)


def _f(v: str) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _i(v: str) -> int | None:
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def build() -> dict:
    soup = BeautifulSoup(_SRC.read_text(encoding="utf-8", errors="replace"), "html.parser")
    rows = soup.find_all("tr")
    header = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    idx = {h: i for i, h in enumerate(header)}

    pumps: list[dict] = []
    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < len(header):
            continue
        lat = _f(cells[idx["lintang"]]) if "lintang" in idx else None
        lon = _f(cells[idx["bujur"]]) if "bujur" in idx else None
        if lat is None or lon is None:
            continue
        if not (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1] and _LON_RANGE[0] <= lon <= _LON_RANGE[1]):
            continue
        pumps.append(
            {
                "name": cells[idx["lokasi"]] if "lokasi" in idx else "",
                "kecamatan": cells[idx["kecamatan"]] if "kecamatan" in idx else "",
                "kelurahan": cells[idx["kelurahan"]] if "kelurahan" in idx else "",
                "alamat": cells[idx["alamat"]] if "alamat" in idx else "",
                "kewenangan": cells[idx["kewenangan"]] if "kewenangan" in idx else "",
                "jumlah_pompa": _i(cells[idx["jumlah_pompa"]]) if "jumlah_pompa" in idx else None,
                "total_capacity": _f(cells[idx["total_kapasitas"]]) if "total_kapasitas" in idx else None,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
            }
        )

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/data-lokasi-rumah-pompa-komponen-data.xls",
            "pump_count": len(pumps),
            "capacity_note": "total_capacity is the published figure; source does not state the unit.",
        },
        "pumps": pumps,
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {payload['_meta']['pump_count']} pump houses -> {_DST}")
    for p in payload["pumps"][:3]:
        print(f"  {p['name']:24} pompa={p['jumlah_pompa']} cap={p['total_capacity']} ({p['lat']},{p['lon']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
