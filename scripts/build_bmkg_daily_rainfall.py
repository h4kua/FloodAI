"""
Parse laporan_iklim_harian XLSX files from BMKG into a clean daily rainfall CSV.

Output: data/processed/bmkg_daily_rainfall.csv
Columns: date, station_name, wmo_id, lat, lon, rr_mm

Jakarta stations used (by WMO ID):
  96745 — Kemayoran
  96741 — Tanjung Priok
  96747 — Halim Perdana Kusuma

Usage:
    python scripts/build_bmkg_daily_rainfall.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_PATH = ROOT / "data" / "processed" / "bmkg_daily_rainfall.csv"

# Only Jakarta stations — filter by WMO ID
JAKARTA_WMO_IDS = {"96745", "96741", "96747"}

_SENTINEL_INVALID = {8888.0, 9999.0}


def _parse_one_file(path: Path) -> list[dict]:
    df = pd.read_excel(path, header=None)
    rows = df.values.tolist()

    station_name, wmo_id, lat, lon = "", "", None, None
    for row in rows[:8]:
        c1 = str(row[1] if len(row) > 1 else "").strip()
        c2 = str(row[2] if len(row) > 2 else "").strip().lstrip(":").strip()
        if "ID WMO" in c1:
            wmo_id = c2
        elif "NAMA STASIUN" in c1:
            station_name = c2
        elif "LINTANG" in c1:
            try:
                lat = float(c2)
            except ValueError:
                pass
        elif "BUJUR" in c1:
            try:
                lon = float(c2)
            except ValueError:
                pass

    if wmo_id not in JAKARTA_WMO_IDS:
        return []

    # Find header row index
    header_row = None
    for i, row in enumerate(rows):
        if str(row[0] if len(row) > 0 else "").strip() == "TANGGAL":
            header_row = i
            break
    if header_row is None:
        return []

    records = []
    for row in rows[header_row + 1 :]:
        date_val = str(row[0] if len(row) > 0 else "").strip()
        rr_raw = row[1] if len(row) > 1 else None

        if not date_val or date_val == "nan" or "KETERANGAN" in date_val:
            break
        try:
            date = pd.to_datetime(date_val, dayfirst=True).date()
        except (ValueError, TypeError):
            continue

        rr_mm = None
        try:
            rr_float = float(rr_raw)
            if rr_float not in _SENTINEL_INVALID:
                rr_mm = rr_float
        except (TypeError, ValueError):
            pass

        records.append(
            {
                "date": date,
                "station_name": station_name,
                "wmo_id": wmo_id,
                "lat": lat,
                "lon": lon,
                "rr_mm": rr_mm,
            }
        )
    return records


def build_bmkg_daily_rainfall() -> pd.DataFrame:
    all_records: list[dict] = []
    xlsx_files = sorted(
        p for p in RAW_DIR.iterdir() if p.name.startswith("laporan_iklim_harian") and p.suffix == ".xlsx"
    )
    print(f"Found {len(xlsx_files)} laporan_iklim_harian files")

    for path in xlsx_files:
        recs = _parse_one_file(path)
        all_records.extend(recs)
        print(f"  {path.name}: {len(recs)} records")

    if not all_records:
        print("[WARN] No Jakarta rainfall records found")
        return pd.DataFrame(columns=["date", "station_name", "wmo_id", "lat", "lon", "rr_mm"])

    df = pd.DataFrame(all_records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date", "wmo_id"]).sort_values(["date", "wmo_id"])
    return df


def main() -> None:
    df = build_bmkg_daily_rainfall()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved {len(df)} records to {OUTPUT_PATH}")
    print(f"Date range: {df.date.min()} — {df.date.max()}")
    print(f"Stations: {df.station_name.unique().tolist()}")
    print(f"Valid rainfall records: {df.rr_mm.notna().sum()}/{len(df)}")


if __name__ == "__main__":
    main()
