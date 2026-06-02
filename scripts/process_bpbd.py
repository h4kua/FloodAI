"""
Process BPBD flood event data into:
  1. data/processed/bpbd_flood_calendar.csv  — per-month flood flag (year, month, has_flood, event_count)
  2. data/processed/zone_flood_frequency.csv — per-zone relative flood frequency from kecamatan records

Usage:
    python scripts/process_bpbd.py

Sources:
    data/raw/bpbd_banjir_2024.csv
    data/raw/bpbd_banjir_2025_2026.csv
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

BPBD_FILES = [
    RAW / "bpbd_banjir_2024.csv",
    RAW / "bpbd_banjir_2025_2026.csv",
]

# Map our 5 app zones to kecamatan keywords in BPBD data
ZONE_KECAMATAN_MAP = {
    "Penjaringan":  ["penjaringan", "pluit", "pademangan", "tanjung priok", "kapuk muara"],
    "Cengkareng":   ["cengkareng", "rawa buaya", "kalideres", "kali deres", "tegal alur", "pegadungan"],
    "Jatinegara":   ["jatinegara", "kampung melayu", "bidara cina", "kramat jati", "cawang", "cililitan"],
    "Kalideres":    ["kalideres", "kembangan", "kebon jeruk", "kedoya", "joglo", "sukabumi"],
    "Kebayoran":    ["kebayoran", "pesanggrahan", "cilandak", "pasar minggu", "pejaten", "jagakarsa"],
}


def _load_all_rows() -> list[dict]:
    rows = []
    for path in BPBD_FILES:
        if not path.exists():
            print(f"[WARN] Not found: {path}")
            continue
        with open(path, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    return rows


def _parse_period(periode: str) -> tuple[int, int]:
    """YYYYMM → (year, quarter_month). Quarter month = first month of the triwulan."""
    year = int(periode[:4])
    quarter = int(periode[4:6])
    # 03 → Q1 (months 1-3), 06 → Q2 (months 4-6), 09 → Q3 (months 7-9), 12 → Q4 (months 10-12)
    quarter_start = {3: 1, 6: 4, 9: 7, 12: 10}.get(quarter, 1)
    return year, quarter_start


def build_flood_calendar(rows: list[dict]) -> list[dict]:
    """
    Aggregate per YYYYMM (quarter period). Output has a row per quarter-period
    with the months covered, total event count, and has_flood flag.
    """
    by_period: dict[str, dict] = defaultdict(lambda: {"event_count": 0, "kelurahan_count": 0})
    for row in rows:
        p = row.get("periode_data", "").strip()
        if not p or len(p) != 6:
            continue
        try:
            events = int(row.get("jumlah_kejadian", 0) or 0)
        except (ValueError, TypeError):
            events = 0
        by_period[p]["event_count"] += events
        by_period[p]["kelurahan_count"] += 1

    calendar = []
    for periode, stats in sorted(by_period.items()):
        year, quarter_start = _parse_period(periode)
        quarter = int(periode[4:6])
        months = list(range(quarter_start, quarter_start + 3))
        calendar.append({
            "periode_data": periode,
            "year": year,
            "quarter": quarter,
            "months_covered": ",".join(str(m) for m in months),
            "event_count": stats["event_count"],
            "kelurahan_count": stats["kelurahan_count"],
            "has_flood": 1 if stats["event_count"] > 0 else 0,
        })
    return calendar


def build_zone_frequency(rows: list[dict]) -> list[dict]:
    """
    Count flood events per zone using kecamatan-keyword matching.
    Normalises to a relative score 0–100 for use as per-zone bias.
    """
    zone_events: dict[str, int] = defaultdict(int)
    zone_kelurahan: dict[str, int] = defaultdict(int)

    for row in rows:
        kec = (row.get("kecamatan") or "").lower().strip()
        try:
            events = int(row.get("jumlah_kejadian", 0) or 0)
        except (ValueError, TypeError):
            events = 0

        for zone, keywords in ZONE_KECAMATAN_MAP.items():
            if any(kw in kec for kw in keywords):
                zone_events[zone] += events
                zone_kelurahan[zone] += 1
                break  # each record goes to the first matching zone

    if not zone_events:
        return []

    max_events = max(zone_events.values()) or 1
    results = []
    for zone in ZONE_KECAMATAN_MAP:
        events = zone_events.get(zone, 0)
        # bias: -20 to +20 range, centred at 0, proportional to event count
        normalised = events / max_events  # 0.0 – 1.0
        bias = round((normalised - 0.5) * 40)  # maps to -20..+20
        results.append({
            "zone": zone,
            "total_events": events,
            "kelurahan_records": zone_kelurahan.get(zone, 0),
            "normalised_score": round(normalised, 4),
            "suggested_bias": bias,
        })

    # Sort highest flood frequency first
    results.sort(key=lambda r: r["total_events"], reverse=True)
    return results


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)

    rows = _load_all_rows()
    print(f"Loaded {len(rows)} BPBD records from {len(BPBD_FILES)} files")

    # 1. Flood calendar
    calendar = build_flood_calendar(rows)
    cal_path = PROCESSED / "bpbd_flood_calendar.csv"
    with open(cal_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=calendar[0].keys())
        writer.writeheader()
        writer.writerows(calendar)
    print(f"Flood calendar written: {cal_path} ({len(calendar)} rows)")
    for row in calendar:
        print(f"  {row['periode_data']}  events={row['event_count']:3d}  kelurahan={row['kelurahan_count']:3d}  has_flood={row['has_flood']}")

    # 2. Zone frequency
    zones = build_zone_frequency(rows)
    zone_path = PROCESSED / "zone_flood_frequency.csv"
    with open(zone_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=zones[0].keys())
        writer.writeheader()
        writer.writerows(zones)
    print(f"\nZone frequency written: {zone_path}")
    print(f"{'Zone':<15} {'Events':>7} {'Kelurahan':>10} {'Score':>7} {'Bias':>6}")
    for z in zones:
        print(f"  {z['zone']:<13} {z['total_events']:>7} {z['kelurahan_records']:>10} {z['normalised_score']:>7.3f} {z['suggested_bias']:>+6}")


if __name__ == "__main__":
    main()
