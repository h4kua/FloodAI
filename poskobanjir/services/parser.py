from datetime import datetime, timezone
import re
import xml.etree.ElementTree as ET

from services.bmkg_filter import filter_jakarta_bmkg_alerts


CAP_NS = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


def _strip_namespace(tag):
    return tag.split("}", 1)[-1].lower()


def _safe_text(element):
    return (element.text or "").strip() if element is not None else ""


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


def build_realtime_snapshot(poskobanjir_records, weather, bmkg_feed, bmkg_alerts):
    jakarta_alerts = filter_jakarta_bmkg_alerts(bmkg_alerts)
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
        },
        "poskobanjir": poskobanjir_records,
        "openweather": weather,
        "bmkg_feed": bmkg_feed,
        "bmkg_alerts": jakarta_alerts,
    }
