"""
Build the flood-prone schools dataset.

Input : data/raw/data-sekolah-rawan-banjir-di-provinsi-dki-jakarta-komponen-data.xls
        (HTML table; columns: nama_sekolah, alamat, kelurahan, kecamatan,
         jumlah_siswa, jumlah_guru, telepon, kondisi_lingkungan, latitude,
         longitude, periode_data)
Output: app/data/flood_prone_schools.json

Coordinate quirk: lat/lon use inconsistent dot placement (thousands vs decimal),
e.g. "-6.172.409" = -6.172409, "-615.357" = -6.15357, "10.679.081" = 106.79081.
We strip non-digits and rescale each value until it lands inside the Jakarta
bounding box; rows that cannot be made valid are dropped (never guessed).

Run:
    python scripts/build_flood_prone_schools.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "data-sekolah-rawan-banjir-di-provinsi-dki-jakarta-komponen-data.xls"
_DST = _PROJECT_ROOT / "data" / "bundled" / "flood_prone_schools.json"

_LAT_RANGE = (5.5, 7.0)     # magnitude (Jakarta lat is negative)
_LON_RANGE = (106.0, 107.5)


def _parse_coord(raw: str, lo: float, hi: float, *, negative: bool) -> float | None:
    """Strip to digits and rescale by powers of 10 until within [lo, hi]."""
    digits = re.sub(r"[^\d]", "", raw or "")
    if not digits:
        return None
    base = int(digits)
    for k in range(0, len(digits) + 1):
        v = base / (10 ** k)
        if lo <= v <= hi:
            return round(-v if negative else v, 6)
    return None


def build() -> dict:
    soup = BeautifulSoup(_SRC.read_text(encoding="utf-8", errors="replace"), "html.parser")
    rows = soup.find_all("tr")
    hdr = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    idx = {h: i for i, h in enumerate(hdr)}

    schools: list[dict] = []
    dropped = 0
    for tr in rows[1:]:
        c = [x.get_text(strip=True) for x in tr.find_all(["td", "th"])]
        if len(c) < len(hdr):
            continue
        lat = _parse_coord(c[idx["latitude"]], *_LAT_RANGE, negative=True)
        lon = _parse_coord(c[idx["longitude"]], *_LON_RANGE, negative=False)
        if lat is None or lon is None:
            dropped += 1
            continue
        try:
            siswa = int(float(c[idx["jumlah_siswa"]])) if "jumlah_siswa" in idx else None
        except (TypeError, ValueError):
            siswa = None
        schools.append(
            {
                "name": c[idx["nama_sekolah"]] if "nama_sekolah" in idx else "",
                "kelurahan": c[idx["kelurahan"]] if "kelurahan" in idx else "",
                "kecamatan": c[idx["kecamatan"]] if "kecamatan" in idx else "",
                "alamat": c[idx["alamat"]] if "alamat" in idx else "",
                "jumlah_siswa": siswa,
                "kondisi": c[idx["kondisi_lingkungan"]] if "kondisi_lingkungan" in idx else "",
                "lat": lat,
                "lon": lon,
            }
        )

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/data-sekolah-rawan-banjir-di-provinsi-dki-jakarta-komponen-data.xls",
            "school_count": len(schools),
            "rows_dropped_bad_coords": dropped,
        },
        "schools": schools,
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {payload['_meta']['school_count']} schools "
          f"(dropped {payload['_meta']['rows_dropped_bad_coords']}) -> {_DST}")
    for s in payload["schools"][:3]:
        print(f"  {s['name'][:30]:30} siswa={s['jumlah_siswa']} ({s['lat']},{s['lon']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
