"""
Geographic scoping for BMKG CAP alerts — subprocess-side filter.

Aligns with services/bmkg_filter.py in the main FastAPI app so both
layers produce identical pass/drop decisions. This file is the authority:
it runs inside the poskobanjir subprocess and its output is written into
the realtime_snapshot.json that the main app reads.

Two token tiers:
  _JAKARTA_TOKENS  — alerts explicitly naming Jakarta / DKI districts.
  _UPSTREAM_TOKENS — Ciliwung watershed + Banten coastal zones that directly
                     drive Jakarta river levels (Katulampa gauge, tidal backflow).
                     Excluding these caused upstream-surge alerts to vanish from
                     the pipeline despite being the primary flood precursor.

Decision order (first match wins):
  1. area_desc token check (Jakarta + upstream)
  2. Polygon bbox intersection — Jakarta bbox
  3. Headline / description / instruction text fallback
  4. No geographic information at all -> pass (already location-scoped request)
"""

from __future__ import annotations

# Jakarta administrative areas and districts.
_JAKARTA_TOKENS = (
    "dki jakarta",
    "jakarta",
    "jakarta barat",
    "jakarta pusat",
    "jakarta selatan",
    "jakarta timur",
    "jakarta utara",
    "kepulauan seribu",
)

# Direct upstream catchment: Ciliwung headwaters (Bogor-Katulampa),
# Banten coastal (tidal backflow via Teluk Jakarta), and Greater Jakarta corridor.
_UPSTREAM_TOKENS = (
    "banten",
    "jawa barat",
    "jabodetabek",
    "bodetabek",
    "katulampa",
    "ciliwung",
    "bogor",
    "depok",
    "tangerang",
    "bekasi",
)

_ALL_TOKENS = _JAKARTA_TOKENS + _UPSTREAM_TOKENS

JAKARTA_BBOX = {
    "lat_min": -6.4,
    "lat_max": -5.9,
    "lon_min": 106.6,
    "lon_max": 107.1,
}


def _normalize(value: object) -> str:
    return " ".join(str(value or "").lower().replace("/", " ").split())


def _polygon_in_jakarta(polygon_str: str) -> bool:
    if not polygon_str:
        return False
    try:
        for point in polygon_str.strip().split():
            lat, lon = map(float, point.split(","))
            if (
                JAKARTA_BBOX["lat_min"] <= lat <= JAKARTA_BBOX["lat_max"]
                and JAKARTA_BBOX["lon_min"] <= lon <= JAKARTA_BBOX["lon_max"]
            ):
                return True
    except Exception:
        return False
    return False


def is_jakarta_bmkg_alert(alert: dict) -> bool:
    # 1. area_desc token match (Jakarta + upstream catchment)
    area_desc = _normalize(alert.get("area_desc"))
    if area_desc:
        if any(token in area_desc for token in _ALL_TOKENS):
            return True

    # 2. Polygon bbox intersection
    polygons = alert.get("polygons") or []
    if any(_polygon_in_jakarta(p) for p in polygons):
        return True

    # 3. Narrative text fallback: BMKG sometimes encodes region names in
    #    headline/description/instruction rather than area_desc.
    composite = _normalize(
        " ".join([
            str(alert.get("headline") or ""),
            str(alert.get("description") or ""),
            str(alert.get("instruction") or ""),
        ])
    )
    if composite:
        return any(token in composite for token in _ALL_TOKENS)

    # 4. No geographic information at all: treat as local to the
    #    location-scoped BMKG request rather than silently discarding.
    #    Only fires when area_desc, polygons, and narrative are ALL absent —
    #    an unrecognised area_desc (e.g. "Sulawesi Selatan") is geographic
    #    information and must not be treated as a location-less alert.
    has_geographic_info = bool(area_desc or polygons or composite)
    return not has_geographic_info


def filter_jakarta_bmkg_alerts(alerts: list) -> list:
    return [alert for alert in (alerts or []) if is_jakarta_bmkg_alert(alert)]
