"""
Build per-kota BNPB InaRISK flood (Banjir) exposure for DKI Jakarta.

DATA REALITY (verified against the live API):
  * InaRISK does NOT expose per-kecamatan flood IRBI scores. The
    `infografis_table_new/<admin>/0` endpoint returns per-HAZARD-TYPE aggregates
    (Gempabumi, Banjir, ...) at province/kabupaten level only. There is no
    public endpoint yielding "44 kecamatan records with irbi_score".
  * The bundled data/bnpb_jakarta_static.json carries kecamatan LOCATIONS only
    (lat/lon/idkec) — no per-kecamatan IRBI.

What IS real and useful: the "Banjir" row per kabupaten (kota) gives official
flood hazard area (ha) and people exposed (jiwaterpapar). We cache that here and
attach the kecamatan location list for spatial reference. No scores are
fabricated.

Output: app/data/bnpb_jakarta_flood_exposure.json

Run:
    python scripts/build_bnpb_flood_exposure.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STATIC = _PROJECT_ROOT / "data" / "bnpb_jakarta_static.json"
_DST = _PROJECT_ROOT / "data" / "bundled" / "bnpb_jakarta_flood_exposure.json"

# DKI kabupaten/kota ids (InaRISK admin codes).
_KABUPATEN = {
    "3171": "Jakarta Selatan",
    "3172": "Jakarta Timur",
    "3173": "Jakarta Pusat",
    "3174": "Jakarta Barat",
    "3175": "Jakarta Utara",
    "3101": "Kepulauan Seribu",
}
_API = "https://inarisk.bnpb.go.id/api/infografis_table_new/{kab}/0"


def _to_float(v) -> float | None:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def _fetch_banjir(kab_id: str) -> dict:
    resp = requests.get(_API.format(kab=kab_id), timeout=20,
                        headers={"User-Agent": "JakartaFloodSystem/1.0"})
    resp.raise_for_status()
    for row in resp.json():
        if "banjir" in (row.get("bencana") or "").lower():
            return {
                "flood_hazard_area_ha": _to_float(row.get("total_luas_bahaya_ha")),
                "people_exposed": _to_float(row.get("jiwaterpapar")),
            }
    return {"flood_hazard_area_ha": None, "people_exposed": None}


def _load_kecamatan_locations() -> dict:
    try:
        payload = json.loads(_STATIC.read_text(encoding="utf-8"))
        return payload.get("kecamatan", {}) or {}
    except (OSError, ValueError):
        return {}


def build() -> dict:
    kota: dict[str, dict] = {}
    for kab_id, name in _KABUPATEN.items():
        try:
            banjir = _fetch_banjir(kab_id)
        except requests.RequestException as exc:
            banjir = {"flood_hazard_area_ha": None, "people_exposed": None, "error": str(exc)[:120]}
        kota[name] = {"kabupaten_id": kab_id, **banjir}

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "inarisk.bnpb.go.id infografis_table_new (Banjir row, per kabupaten)",
            "limitation": "Per-kecamatan IRBI flood scores are NOT exposed by InaRISK; only kota-level flood exposure is available. Kecamatan entries below are LOCATIONS ONLY.",
        },
        "kota_flood_exposure": kota,
        "kecamatan_locations": _load_kecamatan_locations(),
    }


def main() -> int:
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote flood exposure for {len(payload['kota_flood_exposure'])} kota + "
          f"{len(payload['kecamatan_locations'])} kecamatan locations -> {_DST}")
    for name, d in payload["kota_flood_exposure"].items():
        print(f"  {name:18} exposed={d.get('people_exposed')}  area_ha={d.get('flood_hazard_area_ha')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
