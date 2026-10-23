"""Canonical Jakarta wilayah for DSDADKI posts — the single source of truth.

DSDADKI sends a post's wilayah as `file_export`, e.g. "KOTA JAKARTA UTARA";
upstream posts come as Depok / Bogor. Both the backend `wilayah_summary` and
the per-station `wilayah_jakarta` field the frontend groups by are derived
here, so a correction only ever needs to be made in this file.
"""

from __future__ import annotations

JAKARTA_WILAYAH = ["Jakarta Pusat", "Jakarta Utara", "Jakarta Barat", "Jakarta Selatan", "Jakarta Timur"]

# DSDADKI files these posts under KOTA JAKARTA UTARA, but their coordinates put
# them in Kramat Jati (Timur) and the Kali Duri area (Barat).
WILAYAH_OVERRIDE = {
    "P.A. Hek Kramat Jati 1": "Jakarta Timur",
    "P.A. Kaliduri 1":        "Jakarta Barat",
}


def record_wilayah(name: object, file_export: object) -> str | None:
    """Canonical Jakarta wilayah of a post, or None when it lies outside Jakarta.

    `file_export` is matched case-insensitively against the canonical names, so
    both "KOTA JAKARTA UTARA" and "Jakarta Utara" resolve to "Jakarta Utara".
    """
    override = WILAYAH_OVERRIDE.get(str(name or ""))
    if override:
        return override
    raw = str(file_export or "").upper()
    for wilayah in JAKARTA_WILAYAH:
        if wilayah.upper() in raw:
            return wilayah
    return None
