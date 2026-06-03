from datetime import datetime, timezone, timedelta
import re
import xml.etree.ElementTree as ET

# BMKG cuaca.json uses Jakarta local time (WIB = UTC+7). Store the offset once.
_JAKARTA_TZ = timezone(timedelta(hours=7))

from services.bmkg_filter import filter_jakarta_bmkg_alerts


CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def _strip_namespace(tag):
    return tag.split("}", 1)[-1].lower()


def _safe_text(element):
    return (element.text or "").strip() if element is not None else ""


def parse_poskobanjir_json(json_data: list) -> list:
    """Normalize the JSON TMA endpoint (UPPERCASE keys) to the same lowercase
    schema used by parse_poskobanjir_xml so downstream code is unchanged."""
    records = []
    for item in json_data:
        if item.get("RECORD_STATUS") != 1:
            continue
        records.append({
            "id_pintu_air": str(item.get("ID_PINTU_AIR", "")),
            "kode_stasiun": str(item.get("KODE_STASIUN", "")),
            "nama_pintu_air": item.get("NAMA_PINTU_AIR", ""),
            "lokasi": item.get("LOKASI", ""),
            "sort_number": str(item.get("SORT_NUMBER", "")),
            "siaga1": str(item.get("SIAGA1", "")),
            "siaga2": str(item.get("SIAGA2", "")),
            "siaga3": str(item.get("SIAGA3", "")),
            "siaga4": str(item.get("SIAGA4", "")),
            "latitude": str(item.get("LATITUDE", "")),
            "longitude": str(item.get("LONGITUDE", "")),
            "file_export": item.get("FILE_EXPORT", ""),
            "record_status": str(item.get("RECORD_STATUS", "")),
            "tanggal": item.get("TANGGAL", ""),
            "tinggi_air": str(item.get("TINGGI_AIR", "")),
            "tinggi_air_sebelumnya": str(item.get("TINGGI_AIR_SEBELUMNYA", "")),
            "status_siaga": item.get("STATUS_SIAGA", ""),
            "tma_unaltered": str(item.get("TINGGI_AIR", "")),
            "cctv_url": item.get("CCTV_URL") or "",
        })
    return records


def parse_bmkg_cuaca(json_data: dict) -> list:
    """Extract upcoming forecast entries for DKI Jakarta (adm1=31) from cuaca.json.
    Returns the next 4 forecast periods sorted by local_datetime.

    local_datetime from BMKG is Jakarta local time (WIB = UTC+7). We must convert
    to UTC before comparing with now() to avoid showing past slots as upcoming.
    Without this fix, a slot at 18:00 WIB (past) compares against 14:00 UTC and
    appears future, leaking up to 7 stale hours of forecasts onto the dashboard.
    """
    now_utc = datetime.now(timezone.utc)
    entries = []
    for area in json_data.get("data", []):
        lokasi = area.get("lokasi", {})
        if lokasi.get("adm1") != "31":
            continue
        for item in area.get("cuaca", []):
            dt_str = item.get("local_datetime", "")
            try:
                local_dt = datetime.fromisoformat(dt_str)
                # Attach Jakarta timezone so UTC comparison is correct
                utc_dt = local_dt.replace(tzinfo=_JAKARTA_TZ)
            except (ValueError, AttributeError):
                continue
            if utc_dt >= now_utc:
                entries.append({
                    "local_datetime": dt_str,
                    "weather_desc": item.get("weather_desc", ""),
                    "tmin": item.get("tmin"),
                    "tmax": item.get("tmax"),
                    "humin": item.get("humin"),
                    "humax": item.get("humax"),
                })
    entries.sort(key=lambda x: x["local_datetime"])
    return entries[:4]


def parse_poskobanjir_xml(xml_string):
    data = []

    root = ET.fromstring(xml_string)
    for child in root:
        row = {}
        for item in child:
            row[_strip_namespace(item.tag)] = _safe_text(item)
        if row:
            data.append(row)

    return data


def parse_bmkg_feed(xml_string):
    root = ET.fromstring(xml_string)
    channel = root.find("channel")
    if channel is None:
        return []

    items = []
    for item in channel.findall("item"):
        link = _safe_text(item.find("link"))
        items.append(
            {
                "title": _safe_text(item.find("title")),
                "link": link,
                "description": _safe_text(item.find("description")),
                "author": _safe_text(item.find("author")),
                "pub_date": _safe_text(item.find("pubDate")),
                "alert_code": extract_alert_code(link),
            }
        )
    return items


def parse_bmkg_alert(xml_string):
    root = ET.fromstring(xml_string)
    info = root.find("cap:info", CAP_NS)
    area = info.find("cap:area", CAP_NS) if info is not None else None

    parameters = {}
    if info is not None:
        for parameter in info.findall("cap:parameter", CAP_NS):
            name = _safe_text(parameter.find("cap:valueName", CAP_NS))
            value = _safe_text(parameter.find("cap:value", CAP_NS))
            if name:
                parameters[name] = value

    area_description = _safe_text(area.find("cap:areaDesc", CAP_NS)) if area is not None else ""
    polygons = [_safe_text(poly) for poly in area.findall("cap:polygon", CAP_NS)] if area is not None else []

    return {
        "identifier": _safe_text(root.find("cap:identifier", CAP_NS)),
        "sender": _safe_text(root.find("cap:sender", CAP_NS)),
        "sent": _safe_text(root.find("cap:sent", CAP_NS)),
        "status": _safe_text(root.find("cap:status", CAP_NS)),
        "msg_type": _safe_text(root.find("cap:msgType", CAP_NS)),
        "scope": _safe_text(root.find("cap:scope", CAP_NS)),
        "event": _safe_text(info.find("cap:event", CAP_NS)) if info is not None else "",
        "urgency": _safe_text(info.find("cap:urgency", CAP_NS)) if info is not None else "",
        "severity": _safe_text(info.find("cap:severity", CAP_NS)) if info is not None else "",
        "certainty": _safe_text(info.find("cap:certainty", CAP_NS)) if info is not None else "",
        "effective": _safe_text(info.find("cap:effective", CAP_NS)) if info is not None else "",
        "expires": _safe_text(info.find("cap:expires", CAP_NS)) if info is not None else "",
        "headline": _safe_text(info.find("cap:headline", CAP_NS)) if info is not None else "",
        "description": _safe_text(info.find("cap:description", CAP_NS)) if info is not None else "",
        "instruction": _safe_text(info.find("cap:instruction", CAP_NS)) if info is not None else "",
        "web": _safe_text(info.find("cap:web", CAP_NS)) if info is not None else "",
        "area_desc": area_description,
        "polygons": polygons,
        "parameters": parameters,
    }


def extract_alert_code(link):
    match = re.search(r"/([A-Z0-9]+)_alert\.xml$", link or "")
    return match.group(1) if match else ""


def _derive_location(weather: dict) -> str:
    """Derive a location string from OpenWeather response."""
    name = (weather.get("name") or "").strip()
    coord = (weather.get("coord") or {})
    lat = coord.get("lat")
    lon = coord.get("lon")
    if name and lat is not None and lon is not None:
        return f"{name} ({lat:.4f}, {lon:.4f})"
    if lat is not None and lon is not None:
        return f"{lat:.4f}, {lon:.4f}"
    return name or "Jakarta, Indonesia"


def _get_bmkg_daily_rainfall_context() -> dict:
    """Load recent BMKG daily rainfall context. Best-effort — returns empty dict on failure."""
    try:
        import sys
        from pathlib import Path
        _root = Path(__file__).resolve().parents[2]
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        from services.bmkg_rainfall_context import get_recent_daily_rainfall
        return get_recent_daily_rainfall()
    except Exception:
        return {}


def build_realtime_snapshot(
    poskobanjir_records, weather, bmkg_feed, bmkg_alerts, bmkg_forecast=None
):
    jakarta_alerts = filter_jakarta_bmkg_alerts(bmkg_alerts)
    bmkg_daily = _get_bmkg_daily_rainfall_context()

    rain_data = weather.get("rain") or {}
    ow_rain_1h = rain_data.get("1h", 0.0) or 0.0
    ow_rain_3h = rain_data.get("3h", 0.0) or 0.0

    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "location": _derive_location(weather),
        "source_attribution": {
            "poskobanjir": "https://poskobanjir.dsdadki.web.id/",
            "bmkg": "BMKG (Badan Meteorologi, Klimatologi, dan Geofisika)",
            "openweather": "OpenWeather",
        },
        "summary": {
            "total_poskobanjir_records": len(poskobanjir_records),
            "total_bmkg_alerts": len(jakarta_alerts),
            "openweather_location": weather.get("name"),
            "rain_1h_mm": ow_rain_1h,
            "rain_3h_mm": ow_rain_3h,
            "bmkg_daily_yesterday_mm": bmkg_daily.get("yesterday_mm"),
            "bmkg_daily_7d_avg_mm": bmkg_daily.get("last_7d_avg_mm"),
            "bmkg_daily_7d_max_mm": bmkg_daily.get("last_7d_max_mm"),
            "bmkg_rainfall_last_date": bmkg_daily.get("last_available_date"),
        },
        "poskobanjir": poskobanjir_records,
        "openweather": weather,
        "bmkg_feed": bmkg_feed,
        "bmkg_alerts": jakarta_alerts,
        "bmkg_forecast": bmkg_forecast or [],
        "bmkg_daily_rainfall": bmkg_daily,
    }
