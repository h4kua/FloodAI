"""
Build the river-overflow flood-zone dataset.

Input : data/raw/data-wilayah-potensi-banjir-akibat-luapan-sungai-komponen-data.xls
        (HTML table; columns: kota, kecamatan, kelurahan, sungai, periode_data)
        NOTE: a second file "...(1).xls" exists but is byte-identical (same md5),
        so only one is parsed — there is a single dataset, not two.
        This data is NAME-based (kelurahan/kecamatan + river); it has no
        coordinates, so lookups are by administrative name, not lat/lon.
Output: app/data/river_flood_zones.json

Run:
    python scripts/build_river_flood_zones.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "data-wilayah-potensi-banjir-akibat-luapan-sungai-komponen-data.xls"
_DST = _PROJECT_ROOT / "app" / "data" / "river_flood_zones.json"


def build() -> dict:
    soup = BeautifulSoup(_SRC.read_text(encoding="utf-8", errors="replace"), "html.parser")
    rows = soup.find_all("tr")
    hdr = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
    idx = {h: i for i, h in enumerate(hdr)}

    zones: list[dict] = []
    by_kec: dict[str, dict] = defaultdict(lambda: {"rivers": set(), "kelurahan": set()})
    by_kel: dict[str, dict] = defaultdict(lambda: {"rivers": set()})

    for tr in rows[1:]:
        c = [x.get_text(strip=True) for x in tr.find_all(["td", "th"])]
        if len(c) < len(hdr):
            continue
        kota = c[idx["kota"]].strip()
        kec = c[idx["kecamatan"]].strip()
        kel = c[idx["kelurahan"]].strip()
        sungai = c[idx["sungai"]].strip()
        if not kel:
            continue
        zones.append({"kota": kota, "kecamatan": kec, "kelurahan": kel, "sungai": sungai})
        if sungai:
            by_kec[kec.upper()]["rivers"].add(sungai)
            by_kel[kel.upper()]["rivers"].add(sungai)
        by_kec[kec.upper()]["kelurahan"].add(kel)

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/data-wilayah-potensi-banjir-akibat-luapan-sungai-komponen-data.xls",
            "zone_count": len(zones),
            "lookup_basis": "administrative name (kecamatan/kelurahan) — no coordinates in source",
        },
        "zones": zones,
        "by_kecamatan": {
            k: {"rivers": sorted(v["rivers"]), "kelurahan": sorted(v["kelurahan"])}
            for k, v in by_kec.items()
        },
        "by_kelurahan": {k: {"rivers": sorted(v["rivers"])} for k, v in by_kel.items()},
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {payload['_meta']['zone_count']} river-overflow zones "
          f"({len(payload['by_kecamatan'])} kecamatan) -> {_DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
