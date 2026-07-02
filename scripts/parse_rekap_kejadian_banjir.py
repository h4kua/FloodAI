"""
Parse the "01 REKAP KEJADIAN BANJIR PERTAHUN (PER BULAN)" Excel workbooks (2020-2025)
into a per-kelurahan-incident CSV matching the data/raw/combined.csv schema.

Each workbook has one sheet per month (plus a "REKAP PERBULAN" city-wide summary sheet
and, in some years, extra non-month sheets) containing a merged-cell table:
  - A city-header row per kota ("1  JANUARI  JAKARTA UTARA") with the kota name in the
    same column as KECAMATAN, but KELURAHAN blank on that row.
  - Kecamatan/kelurahan header cells only populated on the first row of a district block
    (merged cells) — subsequent RW/RT rows for the same kelurahan leave them blank.
  - SUBTOTAL and NIHIL rows carrying no incident data.

Column positions shift slightly year to year (2020 lacks a NAMA RT column that 2021+
have), so header cells are located dynamically per sheet instead of hardcoding indices.

Output: data/raw/rekap_kejadian_2020_2025.csv
  Columns match combined.csv: kota_administrasi, kecamatan, kelurahan, rw, tahun, bulan,
  lama_genangan, tanggal_kejadian, jumlah_tempat_pengungsian, jumlah_luka_ringan,
  jumlah_luka_berat, ketinggian_air, jumlah_meninggal
  (lama_genangan is left blank — not available at this granularity.)

Run:
    python scripts/parse_rekap_kejadian_banjir.py
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RAW_DIR = _PROJECT_ROOT / "data" / "raw"
_DST = _RAW_DIR / "rekap_kejadian_2020_2025.csv"

_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
_FILE_TEMPLATE = "01 REKAP KEJADIAN BANJIR PERTAHUN (PER BULAN) {year}.xlsx"

_BULAN_ID: dict[str, int] = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}

_SKIP_SHEETS = {"rekap perbulan", "rincian jumlah kejadian"}

_HEADER_KEYS = {
    "kecamatan": "kecamatan",
    "kelurahan": "kelurahan",
    "nama rw": "nama_rw",
    "ketinggian air": "ketinggian_air",
    "tanggal kejadian": "tanggal_kejadian",
    "meninggal": "meninggal",
    "hilang": "hilang",
    "luka berat": "luka_berat",
    "luka ringan": "luka_ringan",
    "jumlah tempat pengungsian": "jumlah_tempat_pengungsian",
}

_OUTPUT_COLUMNS = [
    "kota_administrasi", "kecamatan", "kelurahan", "rw", "tahun", "bulan",
    "lama_genangan", "tanggal_kejadian", "jumlah_tempat_pengungsian",
    "jumlah_luka_ringan", "jumlah_luka_berat", "ketinggian_air", "jumlah_meninggal",
]


def _sheet_month(sheet_name: str) -> int | None:
    name = re.sub(r"\d", "", sheet_name).strip().lower()
    return _BULAN_ID.get(name)


def _locate_headers(df: pd.DataFrame) -> tuple[dict[str, tuple[int, int]], int]:
    """Scan the top rows for header keywords. Returns {field: (row, col)} and the
    last header row index (data starts strictly after it)."""
    found: dict[str, tuple[int, int]] = {}
    max_row = 0
    scan_rows = min(12, len(df))
    for r in range(scan_rows):
        for c in range(df.shape[1]):
            val = df.iat[r, c]
            if not isinstance(val, str):
                continue
            text = val.strip().lower()
            for key, field in _HEADER_KEYS.items():
                if field in found:
                    continue
                if text == key or text.startswith(key):
                    found[field] = (r, c)
                    max_row = max(max_row, r)
    return found, max_row


def _clean(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def _is_city_header(kec_num_val: str, kel_num_val: str) -> bool:
    return bool(kec_num_val) and not kel_num_val and "jakarta" in kec_num_val.lower()


_HEADER_ECHO = {"kecamatan", "kelurahan", "wilayah"}


def _is_noise_row(*vals: str) -> bool:
    for v in vals:
        low = v.lower()
        if not low:
            continue
        if low.startswith("subtotal") or low.startswith("nihil"):
            return True
        # Some sheets repeat a footer/grand-total row whose cells echo the header
        # labels themselves ("KECAMATAN" / "KELURAHAN") instead of real names.
        if low in _HEADER_ECHO:
            return True
    return False


def _num(val) -> float:
    text = _clean(val)
    if not text:
        return 0.0
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return 0.0


def _parse_sheet(df: pd.DataFrame, year: int, month: int) -> list[dict]:
    headers, header_end = _locate_headers(df)
    if "kecamatan" not in headers or "kelurahan" not in headers:
        return []

    # KECAMATAN/KELURAHAN header cells sit atop a merged "No | Name" pair — the
    # header text lands on the number sub-column (also used bare for city-header
    # rows like "1  JANUARI  JAKARTA UTARA"), the actual name is one column right.
    kec_num_col = headers["kecamatan"][1]
    kec_name_col = kec_num_col + 1
    kel_num_col = headers["kelurahan"][1]
    kel_name_col = kel_num_col + 1
    rw_col = headers.get("nama_rw", (None, None))[1]
    height_col = headers.get("ketinggian_air", (None, None))[1]
    tanggal_col = headers.get("tanggal_kejadian", (None, None))[1]
    meninggal_col = headers.get("meninggal", (None, None))[1]
    luka_berat_col = headers.get("luka_berat", (None, None))[1]
    luka_ringan_col = headers.get("luka_ringan", (None, None))[1]
    pengungsian_col = headers.get("jumlah_tempat_pengungsian", (None, None))[1]

    rows: list[dict] = []
    current_kota: str | None = None
    current_kec: str | None = None
    current_kel: str | None = None
    current_rw: str = ""

    for r in range(header_end + 1, len(df)):
        kec_num_val = _clean(df.iat[r, kec_num_col]) if kec_num_col < df.shape[1] else ""
        kel_num_val = _clean(df.iat[r, kel_num_col]) if kel_num_col < df.shape[1] else ""
        kec_name_val = _clean(df.iat[r, kec_name_col]) if kec_name_col < df.shape[1] else ""
        kel_name_val = _clean(df.iat[r, kel_name_col]) if kel_name_col < df.shape[1] else ""

        if _is_city_header(kec_num_val, kel_num_val):
            current_kota = kec_num_val
            current_kec = None
            current_kel = None
            current_rw = ""
            continue

        if _is_noise_row(kec_num_val, kec_name_val, kel_num_val, kel_name_val):
            continue

        if kec_num_val and kec_name_val:
            current_kec = kec_name_val
        if kel_num_val and kel_name_val:
            current_kel = kel_name_val
            current_rw = ""

        rw_val = _clean(df.iat[r, rw_col]) if rw_col is not None and rw_col < df.shape[1] else ""
        if rw_val:
            current_rw = rw_val

        height_val = _clean(df.iat[r, height_col]) if height_col is not None and height_col < df.shape[1] else ""
        tanggal_val = _clean(df.iat[r, tanggal_col]) if tanggal_col is not None and tanggal_col < df.shape[1] else ""

        # A data row must have a kelurahan context and at least one incident signal
        # (height or date) — otherwise it's a blank spacer row.
        if not current_kota or not current_kec or not current_kel:
            continue
        if not height_val and not tanggal_val:
            continue

        rows.append({
            "kota_administrasi": current_kota,
            "kecamatan": current_kec,
            "kelurahan": current_kel,
            "rw": current_rw,
            "tahun": year,
            "bulan": month,
            "lama_genangan": "",
            "tanggal_kejadian": tanggal_val,
            "jumlah_tempat_pengungsian": _num(df.iat[r, pengungsian_col]) if pengungsian_col is not None and pengungsian_col < df.shape[1] else 0.0,
            "jumlah_luka_ringan": _num(df.iat[r, luka_ringan_col]) if luka_ringan_col is not None and luka_ringan_col < df.shape[1] else 0.0,
            "jumlah_luka_berat": _num(df.iat[r, luka_berat_col]) if luka_berat_col is not None and luka_berat_col < df.shape[1] else 0.0,
            "ketinggian_air": height_val,
            "jumlah_meninggal": _num(df.iat[r, meninggal_col]) if meninggal_col is not None and meninggal_col < df.shape[1] else 0.0,
        })

    return rows


def parse_workbook(path: Path) -> list[dict]:
    year_match = re.search(r"(20\d{2})", path.stem)
    if not year_match:
        return []
    year = int(year_match.group(1))

    xls = pd.ExcelFile(path)
    rows: list[dict] = []
    for sheet_name in xls.sheet_names:
        if sheet_name.strip().lower() in _SKIP_SHEETS:
            continue
        month = _sheet_month(sheet_name)
        if month is None:
            continue
        df = pd.read_excel(path, sheet_name=sheet_name, header=None)
        rows.extend(_parse_sheet(df, year, month))
    return rows


def build() -> list[dict]:
    all_rows: list[dict] = []
    for year in _YEARS:
        path = _RAW_DIR / _FILE_TEMPLATE.format(year=year)
        if not path.exists():
            print(f"  skip (not found): {path.name}")
            continue
        rows = parse_workbook(path)
        print(f"  {path.name}: {len(rows)} incident rows")
        all_rows.extend(rows)
    return all_rows


def main() -> int:
    rows = build()
    if not rows:
        print("No rows parsed — aborting write.")
        return 1
    with open(_DST, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {_DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
