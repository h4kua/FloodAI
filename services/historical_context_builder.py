"""
Historical flood context builder — shared by crew, LLM orchestrator, and chat.

Loads bundled JSON files once (cached) and produces a compact Bahasa Indonesia
briefing string for a given district. Used to inject location-specific depth
estimates, flood frequency, affected rivers, and proportional framing into
AI-generated explanations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_BUNDLED = Path(__file__).resolve().parent.parent / "data" / "bundled"

_DISTRICT_ALIASES: dict[str, str] = {
    "Jakarta Timur": "Jakarta Timur",
    "Jakarta Selatan": "Jakarta Selatan",
    "Jakarta Utara": "Jakarta Utara",
    "Jakarta Barat": "Jakarta Barat",
    "Jakarta Pusat": "Jakarta Pusat",
    "KOTA ADM. JAKARTA TIMUR": "Jakarta Timur",
    "KOTA ADM. JAKARTA SELATAN": "Jakarta Selatan",
    "KOTA ADM. JAKARTA UTARA": "Jakarta Utara",
    "KOTA ADM. JAKARTA BARAT": "Jakarta Barat",
    "KOTA ADM. JAKARTA PUSAT": "Jakarta Pusat",
}


def _resolve_district(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    if cleaned in _DISTRICT_ALIASES:
        return _DISTRICT_ALIASES[cleaned]
    for alias, canonical in _DISTRICT_ALIASES.items():
        if alias.lower() in cleaned.lower() or cleaned.lower() in alias.lower():
            return canonical
    return cleaned


def _load_json(filename: str) -> dict:
    path = _BUNDLED / filename
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        _log.debug("historical_context_load_failed file=%s", filename)
        return {}


@lru_cache(maxsize=1)
def _historical_events() -> dict:
    return _load_json("historical_flood_events.json")


@lru_cache(maxsize=1)
def _kelurahan_history() -> dict:
    return _load_json("kelurahan_flood_history.json")


@lru_cache(maxsize=1)
def _river_zones() -> dict:
    return _load_json("river_flood_zones.json")


@lru_cache(maxsize=1)
def _hazard_index() -> dict:
    return _load_json("flood_hazard_index_2023.json")


def _top_kelurahan(district: str, limit: int = 5) -> list[dict[str, Any]]:
    kel_data = (_kelurahan_history().get("kelurahan") or {})
    matches = []
    for name, info in kel_data.items():
        if not isinstance(info, dict):
            continue
        kota = info.get("kota", "")
        if _resolve_district(kota) == district:
            matches.append({"kelurahan": name, **info})
    matches.sort(key=lambda x: x.get("event_count", 0), reverse=True)
    return matches[:limit]


def _rivers_for_district(district: str) -> list[str]:
    zones = (_river_zones().get("zones") or [])
    rivers: set[str] = set()
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        kota = zone.get("kota", "")
        if district.upper().replace("JAKARTA ", "") in kota.upper():
            sungai = zone.get("sungai")
            if sungai:
                rivers.add(sungai)
    return sorted(rivers)


def _current_month_flood_risk(district: str) -> str:
    events = (_historical_events().get("districts") or {}).get(district)
    if not events or not isinstance(events, dict):
        return ""
    by_month = events.get("by_month", {})
    month = str(datetime.now().month)
    month_events = by_month.get(month, 0)
    total_events = events.get("event_count", 1)
    pct = round(month_events / total_events * 100) if total_events > 0 else 0
    month_names_id = {
        "1": "Januari", "2": "Februari", "3": "Maret", "4": "April",
        "5": "Mei", "6": "Juni", "7": "Juli", "8": "Agustus",
        "9": "September", "10": "Oktober", "11": "November", "12": "Desember",
    }
    month_name = month_names_id.get(month, month)
    if pct >= 15:
        return f"Bulan {month_name} termasuk periode rawan banjir ({pct}% kejadian historis)."
    return f"Bulan {month_name} bukan puncak musim banjir ({pct}% kejadian historis)."


def build_historical_briefing(district_raw: str) -> str:
    """
    Build a compact Bahasa Indonesia historical flood briefing for the given
    district. Returns empty string if no data is available.

    Used by:
      - flood_crew.py coordinator task
      - llm_orchestrator.py user message
      - chat.py retrieved context
    """
    district = _resolve_district(district_raw)
    events = (_historical_events().get("districts") or {}).get(district)
    if not events or not isinstance(events, dict):
        return ""

    avg_depth_cm = events.get("avg_ketinggian_cm", 0)
    max_depth_cm = events.get("max_ketinggian_cm", 0)
    event_count = events.get("event_count", 0)
    years = events.get("years_covered", [])
    total_luka = events.get("total_luka", 0)
    total_meninggal = events.get("total_meninggal", 0)

    rivers = _rivers_for_district(district)
    top_kel = _top_kelurahan(district)
    month_risk = _current_month_flood_risk(district)
    hazard = (_hazard_index().get("kota") or {}).get(district, {})

    lines: list[str] = []
    lines.append(f"DATA HISTORIS BANJIR {district.upper()}:")

    period = f"{years[0]}–{years[-1]}" if len(years) >= 2 else (years[0] if years else "?")
    lines.append(f"  {event_count} kejadian banjir tercatat ({period})")

    lines.append(
        f"  Rata-rata kedalaman: {avg_depth_cm:.0f} cm ({avg_depth_cm/100:.1f} m) · "
        f"Maksimum: {max_depth_cm:.0f} cm ({max_depth_cm/100:.1f} m)"
    )

    if total_luka > 0 or total_meninggal > 0:
        impact_parts = []
        if total_luka > 0:
            impact_parts.append(f"{total_luka:,} jiwa terdampak".replace(",", "."))
        if total_meninggal > 0:
            impact_parts.append(f"{total_meninggal} korban jiwa")
        lines.append(f"  Dampak kumulatif: {' · '.join(impact_parts)}")

    if rivers:
        lines.append(f"  Sungai/kali terkait: {', '.join(rivers)}")

    if top_kel:
        kel_parts = []
        for k in top_kel[:4]:
            name = k["kelurahan"]
            kec = k.get("kecamatan", "")
            count = k.get("event_count", 0)
            max_cm = k.get("max_ketinggian_cm", 0)
            depth_str = f", maks {max_cm:.0f} cm" if max_cm > 0 else ""
            kec_str = f" ({kec})" if kec else ""
            kel_parts.append(f"{name}{kec_str}: {count}x{depth_str}")
        lines.append(f"  Kelurahan tersering: {' · '.join(kel_parts)}")

    if hazard:
        dom_cat = hazard.get("dominant_category", "")
        avg_idx = hazard.get("avg_index", 0)
        if dom_cat:
            lines.append(f"  Indeks bahaya 2023: kategori dominan {dom_cat} (rata-rata {avg_idx:.1f}/3)")

    if month_risk:
        lines.append(f"  {month_risk}")

    return "\n".join(lines)


def build_chat_historical_context(district_raw: str) -> dict[str, Any]:
    """
    Build a structured dict for chat endpoint context injection.
    Lighter than the full briefing — just the key numbers.
    """
    district = _resolve_district(district_raw)
    events = (_historical_events().get("districts") or {}).get(district)
    if not events:
        return {}

    top_kel = _top_kelurahan(district, limit=3)
    rivers = _rivers_for_district(district)

    return {
        "district": district,
        "total_events": events.get("event_count", 0),
        "avg_depth_cm": events.get("avg_ketinggian_cm", 0),
        "max_depth_cm": events.get("max_ketinggian_cm", 0),
        "total_affected": events.get("total_luka", 0),
        "rivers": rivers[:5],
        "top_kelurahan": [
            {
                "name": k["kelurahan"],
                "kecamatan": k.get("kecamatan", ""),
                "events": k.get("event_count", 0),
                "max_depth_cm": k.get("max_ketinggian_cm", 0),
            }
            for k in top_kel
        ],
        "month_note": _current_month_flood_risk(district),
    }
