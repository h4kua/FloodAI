"""
Flood zone intelligence — builds geospatial flood zones from internal AI signals.

IMPORTANT: These zones are derived entirely from the flood prediction pipeline's
signals. They do NOT come from Google Maps or any external routing service.
The routing engine uses these zones purely as spatial constraints to avoid.

Zone schema per entry:
    {"lat": float, "lon": float, "radius_m": int,
     "severity": "high" | "medium", "label": str}
"""

from __future__ import annotations

# ─── Known Jakarta flood-prone zone centroids ────────────────────────────────
# Source: BPBD Jakarta flood history and Ciliwung/Cisadane basin reports.
# Zones are selectively activated based on which signals are currently active.

_ALL_ZONES: list[dict] = [
    # ── River-adjacent / hydrological-stress zones ───────────────────────────
    {
        "id": "ciliwung_manggarai",
        "lat": -6.2149, "lon": 106.8502,
        "label": "Manggarai water gate (Ciliwung)",
        "categories": ["hydro"],
    },
    {
        "id": "ciliwung_bukit_duri",
        "lat": -6.2254, "lon": 106.8440,
        "label": "Bukit Duri (Ciliwung bank)",
        "categories": ["hydro"],
    },
    {
        "id": "ciliwung_kampung_melayu",
        "lat": -6.2416, "lon": 106.8676,
        "label": "Kampung Melayu / Cawang",
        "categories": ["hydro"],
    },
    {
        "id": "penjaringan",
        "lat": -6.1174, "lon": 106.8063,
        "label": "Penjaringan (river delta, North Jakarta)",
        "categories": ["hydro", "coastal"],
    },
    {
        "id": "pluit",
        "lat": -6.1195, "lon": 106.7945,
        "label": "Pluit (coastal, North Jakarta)",
        "categories": ["hydro", "coastal"],
    },
    {
        "id": "grogol",
        "lat": -6.1666, "lon": 106.7970,
        "label": "Grogol Petamburan (West, river branch)",
        "categories": ["rainfall", "hydro"],
    },
    {
        "id": "rawajati",
        "lat": -6.2493, "lon": 106.8419,
        "label": "Rawajati / Kalibata (South Jakarta)",
        "categories": ["rainfall", "hydro"],
    },
    # ── Rainfall-driven / drainage-stress zones ──────────────────────────────
    {
        "id": "kalideres",
        "lat": -6.1444, "lon": 106.7019,
        "label": "Kalideres (West Jakarta, Cengkareng drain)",
        "categories": ["rainfall"],
    },
    {
        "id": "kapuk",
        "lat": -6.1261, "lon": 106.7372,
        "label": "Kapuk (West Jakarta)",
        "categories": ["rainfall"],
    },
    {
        "id": "kebon_jeruk",
        "lat": -6.1949, "lon": 106.7649,
        "label": "Kebon Jeruk (West Jakarta)",
        "categories": ["rainfall"],
    },
    {
        "id": "cilincing",
        "lat": -6.0895, "lon": 106.9175,
        "label": "Cilincing (North Jakarta)",
        "categories": ["rainfall", "coastal"],
    },
]

# ─── Radius constants (metres) ────────────────────────────────────────────────
# Hydro zones: smaller radius = concentrated overflow near river banks.
# Rainfall zones: larger radius = diffuse surface flooding across urban blocks.
# Compound: tightest radius = most precise high-risk area.
_RADIUS_HYDRO_CRITICAL = 500
_RADIUS_HYDRO_STRESS = 700
_RADIUS_RAINFALL_EXTREME = 1200
_RADIUS_RAINFALL_HIGH = 900
_RADIUS_COMPOUND = 400
_RADIUS_BMKG_FALLBACK = 800

_SEVERITY_RANK = {"high": 1, "medium": 0}


def build_flood_zones(features: dict, signals: dict) -> list[dict]:
    """
    Construct the active flood zone list from pipeline signals.

    Activation rules (evaluated in priority order):
      compound_risk           → ALL zones, high severity, tightest radius
      critical_water_level    → hydro zones, high severity, critical radius
      hydro_stress            → hydro zones, high severity, stress radius
      extreme_rainfall        → rainfall zones, medium severity, large radius
      high_rainfall           → rainfall zones, medium severity, standard radius
      bmkg_extreme+confirmed  → all zones (forecast only), medium severity
      no signals              → empty list (no avoidance needed)

    Returns an empty list when no risk signals are active, correctly telling the
    RoutingAgent that no flood-zone avoidance is needed.
    """
    zones: list[dict] = []

    compound = signals.get("compound_risk", False)
    critical_hydro = signals.get("critical_water_level", False)
    hydro_stress = signals.get("hydro_stress", False)
    extreme_rain = signals.get("extreme_rainfall", False)
    high_rain = signals.get("high_rainfall", False)
    bmkg_extreme = signals.get("bmkg_extreme", False)
    bmkg_confirmed = signals.get("bmkg_confirmed", False)

    if compound:
        # Multi-hazard overlap: every historically documented zone is dangerous.
        for z in _ALL_ZONES:
            zones.append(_make_zone(z, "high", _RADIUS_COMPOUND))
        return _deduplicate(zones)

    # Hydrological-stress zones (river overflow, near water gates)
    if critical_hydro:
        for z in _ALL_ZONES:
            if "hydro" in z["categories"]:
                zones.append(_make_zone(z, "high", _RADIUS_HYDRO_CRITICAL))
    elif hydro_stress:
        for z in _ALL_ZONES:
            if "hydro" in z["categories"]:
                zones.append(_make_zone(z, "high", _RADIUS_HYDRO_STRESS))

    # Rainfall-driven zones (surface flooding, drainage failure)
    if extreme_rain:
        for z in _ALL_ZONES:
            if "rainfall" in z["categories"]:
                zones.append(_make_zone(z, "medium", _RADIUS_RAINFALL_EXTREME))
    elif high_rain:
        for z in _ALL_ZONES:
            if "rainfall" in z["categories"]:
                zones.append(_make_zone(z, "medium", _RADIUS_RAINFALL_HIGH))

    # BMKG confirmed alert but no observed hydro/rain yet: activate all as medium
    if bmkg_extreme and bmkg_confirmed and not zones:
        for z in _ALL_ZONES:
            zones.append(_make_zone(z, "medium", _RADIUS_BMKG_FALLBACK))

    return _deduplicate(zones)


def _make_zone(template: dict, severity: str, radius_m: int) -> dict:
    return {
        "lat": template["lat"],
        "lon": template["lon"],
        "radius_m": radius_m,
        "severity": severity,
        "label": template["label"],
    }


def _deduplicate(zones: list[dict]) -> list[dict]:
    """Remove duplicates by (lat, lon), keeping the highest-severity entry."""
    seen: dict[tuple, dict] = {}
    for z in zones:
        key = (z["lat"], z["lon"])
        existing = seen.get(key)
        if existing is None or _SEVERITY_RANK[z["severity"]] > _SEVERITY_RANK[existing["severity"]]:
            seen[key] = z
    return list(seen.values())
