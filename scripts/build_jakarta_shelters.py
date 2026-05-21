"""
Build a compact Jakarta shelter dataset from the raw OSM/HOT shelter export.

Input : data/raw/shelter.geojson  (FeatureCollection of ~12.5k Point features,
        OSM-derived; key fields: name, capacity:persons, amenity, addr:full)
Output: app/data/jakarta_shelters.json

Only named features with valid coordinates are kept — an unnamed point is
useless as an evacuation instruction. Field names below were confirmed by
inspecting the source file; nothing is assumed.

Run:
    python scripts/build_jakarta_shelters.py
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PROJECT_ROOT / "data" / "raw" / "shelter.geojson"
_DST = _PROJECT_ROOT / "data" / "bundled" / "jakarta_shelters.json"

_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def _parse_capacity(raw: object) -> tuple[str, int | None]:
    """Parse OSM 'capacity:persons' (e.g. '>500', '100-500', '250') -> (raw, estimate)."""
    text = str(raw or "").strip()
    if not text:
        return "", None
    nums = [float(n.replace(",", ".")) for n in _NUM_RE.findall(text)]
    if not nums:
        return text, None
    # A range -> midpoint; a single bound (">500"/"<100"/"250") -> that number.
    estimate = round(sum(nums[:2]) / 2) if len(nums) >= 2 and "-" in text else round(nums[0])
    return text, estimate


_KEL_RE = re.compile(r"\bkel(?:urahan)?\.?\s+([A-Za-z][A-Za-z .'-]{2,40})", re.IGNORECASE)


def _kelurahan_from_address(address: str) -> str | None:
    """Best-effort kelurahan extraction from a freeform OSM address; None if absent."""
    if not address:
        return None
    m = _KEL_RE.search(address)
    if not m:
        return None
    return m.group(1).strip(" .,'-").title() or None


def _coords(feature: dict) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    lon, lat = coords[0], coords[1]
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def build() -> dict:
    raw = json.loads(_SRC.read_text(encoding="utf-8"))
    shelters: list[dict] = []
    for feature in raw.get("features", []):
        props = feature.get("properties", {}) or {}
        name = (props.get("name") or "").strip()
        if not name:
            continue
        latlon = _coords(feature)
        if latlon is None:
            continue
        lat, lon = latlon
        cap_raw, cap_est = _parse_capacity(props.get("capacity:persons"))
        address = (props.get("addr:full") or "").strip()
        shelters.append(
            {
                # Stable ordinal id so downstream responses can reference a shelter.
                "id": f"SH{len(shelters):05d}",
                "name": name,
                # kelurahan is not a first-class OSM field here; take addr:suburb
                # when present, else a best-effort parse of the full address.
                # Frequently null — never fabricated.
                "kelurahan": (props.get("addr:suburb") or "").strip() or _kelurahan_from_address(address),
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "capacity_raw": cap_raw,
                "capacity_est": cap_est,
                "amenity": (props.get("amenity") or "").strip(),
                "building": (props.get("building") or "").strip(),
                "address": address,
            }
        )

    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "data/raw/shelter.geojson (OSM/HOT InAWARE survey)",
            "shelter_count": len(shelters),
            "note": "Named point candidates for evacuation guidance. capacity_est is a rough numeric estimate parsed from capacity_raw.",
        },
        "shelters": shelters,
    }


def main() -> int:
    if not _SRC.exists():
        print(f"Source not found: {_SRC}")
        return 1
    payload = build()
    _DST.parent.mkdir(parents=True, exist_ok=True)
    _DST.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {payload['_meta']['shelter_count']} shelters -> {_DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
