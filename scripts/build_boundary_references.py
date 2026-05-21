"""
Cache administrative-boundary reference data for spatial-lookup fallback.

Downloads three public references and stores them under app/data/:
  * BPS province registry  -> bps_wilayah_provinsi.json   (name normalisation)
  * BIG Jakarta admin item -> big_jakarta_admin_boundary.json
  * Indonesia admin geojson -> indonesia_admin.geojson     (fallback boundaries)

These are REFERENCE caches. The runtime spatial lookup currently uses kecamatan
centroids (bnpb_jakarta_mapper.get_kecamatan_by_coords), which works without
polygon geometry. Polygon-in-shape lookup would need a geometry library
(shapely) and is intentionally NOT wired here; these files are cached so that
enhancement can be done later offline.

Each download is independent and best-effort: a failure on one does not stop
the others.

Run:
    python scripts/build_boundary_references.py
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DATA = _PROJECT_ROOT / "data" / "bundled"

_SOURCES = {
    "bps_wilayah_provinsi.json": (
        "https://sig.bps.go.id/rest-bridging-dagri/getwilayah?level=provinsi&parent=0"
    ),
    "big_jakarta_admin_boundary.json": (
        "https://geoservices.big.go.id/portal/sharing/rest/content/items/"
        "49bda2cefd3f4b92aa726300bcdb40f7/data?f=json"
    ),
    "indonesia_admin.geojson": (
        "https://raw.githubusercontent.com/superpikar/indonesia-geojson/master/indonesia.geojson"
    ),
}


def _fetch_and_save(filename: str, url: str) -> bool:
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "JakartaFloodSystem/1.0"})
        resp.raise_for_status()
        data = resp.json()  # requests transparently gunzips
        dst = _DATA / filename
        dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        size_kb = round(dst.stat().st_size / 1024, 1)
        print(f"  OK  {filename}  ({size_kb} KB)")
        return True
    except (requests.RequestException, ValueError, OSError) as exc:
        print(f"  FAIL {filename}: {str(exc)[:120]}")
        return False


def main() -> int:
    _DATA.mkdir(parents=True, exist_ok=True)
    print("Caching boundary references -> app/data/")
    ok = sum(_fetch_and_save(name, url) for name, url in _SOURCES.items())
    print(f"{ok}/{len(_SOURCES)} reference files cached.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
