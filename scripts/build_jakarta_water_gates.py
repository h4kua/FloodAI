"""
Build the Jakarta water-gate (pintu air) registry from the SDA component export.

Input : data/raw/data-pintu-air-komponen-data.xls  (HTML table)
        Confirmed columns: periode_data, wilayah, nama_pintu_air, sistem_aliran,
        inlet, outlet, lintang, bujur, jumlah_unit
Output: app/data/jakarta_water_gates.json

NOTE on scope: this registry describes operational gates (flow system, inlet/
outlet, unit count) and their coordinates. It contains NO SIAGA threshold
columns, so there is nothing new to merge into hydrology_analyzer's per-station
thresholds — it is kept as its own dataset rather than force-merged into the
AWLR recorder registry (awlr_stations.json), which is a distinct entity.

Run:
    python scripts/build_jakarta_water_gates.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "data-pintu-air-komponen-data.xls"
_DST = _PROJECT_ROOT / "data" / "bundled" / "jakarta_water_gates.json"

_LAT_RANGE = (-7.0, -5.5)
_LON_RANGE = (106.0, 107.5)


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

    gates: list[dict] = []
    for tr in rows[1:]:
        c = [x.get_text(strip=True) for x in tr.find_all(["td", "th"])]
        if len(c) < len(hdr):
            continue
        lat = _f(c[idx["lintang"]]) if "lintang" in idx else None
        lon = _f(c[idx["bujur"]]) if "bujur" in idx else None
        if lat is not None and not (_LAT_RANGE[0] <= lat <= _LAT_RANGE[1]):
            lat = None
        if lon is not None and not (_LON_RANGE[0] <= lon <= _LON_RANGE[1]):
            lon = None
        gates.append(
            {
                "name": c[idx["nama_pintu_air"]] if "nama_pintu_air" in idx else "",
                "wilayah": c[idx["wilayah"]] if "wilayah" in idx else "",
                "sistem_aliran": c[idx["sistem_aliran"]] if "sistem_aliran" in idx else "",
                "inlet": c[idx["inlet"]] if "inlet" in idx else "",
                "outlet": c[idx["outlet"]] if "outlet" in idx else "",
                "jumlah_unit": c[idx["jumlah_unit"]] if "jumlah_unit" in idx else "",
                "lat": round(lat, 6) if lat is not None else None,
                "lon": round(lon, 6) if lon is not None else None,
            }
        )

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/data-pintu-air-komponen-data.xls",
            "gate_count": len(gates),
            "note": "Operational pintu-air registry. No SIAGA threshold columns present, so hydrology thresholds are unchanged.",
        },
        "gates": gates,
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {payload['_meta']['gate_count']} water gates -> {_DST}")
    for g in payload["gates"][:3]:
        print(f"  {g['name'][:30]:30} aliran={g['sistem_aliran']} ({g['lat']},{g['lon']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
