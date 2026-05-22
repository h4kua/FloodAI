JAKARTA_BBOX = {
    "lat_min": -6.4,
    "lat_max": -5.9,
    "lon_min": 106.6,
    "lon_max": 107.1,
}


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


def filter_jakarta_bmkg_alerts(alerts: list) -> list:
    if not alerts:
        return []
    jakarta = []
    for alert in alerts:
        area_desc = (alert.get("area_desc") or "").lower()
        if "jakarta" in area_desc or "dki" in area_desc:
            jakarta.append(alert)
            continue
        polygons = alert.get("polygons") or []
        if any(_polygon_in_jakarta(p) for p in polygons):
            jakarta.append(alert)
    return jakarta
