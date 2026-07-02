"""Water-level station -> kecamatan/area mapping, shared by inference.py
(station labels) and feature_builder.py (per-kecamatan feature construction).

Kept in its own module so neither of those two — which already import from
each other's package — need to import one another to reach this table.
"""

from __future__ import annotations

STATION_KECAMATAN: dict[str, dict[str, str]] = {
    "P.A. Marina Ancol (Laut)":  {"kecamatan": "Penjaringan", "area": "pesisir Ancol"},
    "P.A. Marina Ancol (Kali)":  {"kecamatan": "Penjaringan", "area": "Ancol"},
    "Pompa Pasar Ikan 1":        {"kecamatan": "Penjaringan", "area": "Pelabuhan Sunda Kelapa"},
    "P.A. Karet 1":              {"kecamatan": "Tanah Abang", "area": "Karet-Kuningan"},
    "Pompa Yos Sudarso 1":       {"kecamatan": "Tanjung Priok", "area": "Sunter Agung"},
    "P.A. Hek":                  {"kecamatan": "Matraman", "area": "Cipinang Melayu"},
    "P.A. Cengkareng Drain":     {"kecamatan": "Cengkareng", "area": "Cengkareng-Kapuk"},
    "P.A. Manggarai 2":          {"kecamatan": "Tebet", "area": "Manggarai-Bukit Duri"},
    "P.A. Pulo Gadung 2":        {"kecamatan": "Pulo Gadung", "area": "Sunter-Pulo Gadung"},
    "Rumah Pompa Pluit 1":       {"kecamatan": "Penjaringan", "area": "Pluit"},
    "P.A. Kaliduri 1":           {"kecamatan": "Tambora", "area": "Kali Duri-Tambora"},
    "P.A. Ancol Flushing 1":     {"kecamatan": "Pademangan", "area": "Ancol-Pademangan"},
    "P.A. Jembatan Merah 1":     {"kecamatan": "Menteng", "area": "Menteng-Cikini"},
    "P.A. Istiqlal 1":           {"kecamatan": "Sawah Besar", "area": "Istiqlal-Sawah Besar"},
    "Pompa Cideng 1":            {"kecamatan": "Gambir", "area": "Cideng-Gambir"},
    "P.S. Krukut Hulu 2":        {"kecamatan": "Kebayoran Baru", "area": "Krukut-Kebayoran"},
    "P.S. Sunter Hulu":          {"kecamatan": "Cakung", "area": "Sunter Hulu"},
    "Waduk Kampung Rambutan 1":   {"kecamatan": "Ciracas", "area": "Kampung Rambutan"},
    "Rumah Pompa Kemang 2":       {"kecamatan": "Mampang Prapatan", "area": "Kemang"},
    "Rumah Pompa Atma Jaya":      {"kecamatan": "Mampang Prapatan", "area": "Kuningan"},
    "Posko SDA Palmerah":         {"kecamatan": "Palmerah", "area": "Palmerah-Grogol"},
    "Jembatan MT. Haryono":       {"kecamatan": "Jatinegara", "area": "MT Haryono-Cawang"},
    "Rumah Pompa Tipala":         {"kecamatan": "Makasar", "area": "Cipinang-Makasar"},
    "Bendung. Katulampa 2":       {"kecamatan": "Bogor Selatan", "area": "Katulampa (hulu Ciliwung)"},
    "Pompa Kamal Muara (Bubble)": {"kecamatan": "Penjaringan", "area": "Kamal Muara"},
    "Pompa Lagoa (Bubble)":       {"kecamatan": "Koja", "area": "Lagoa-Koja"},
    "Pompa Cilincing (Bubble)":   {"kecamatan": "Cilincing", "area": "Cilincing"},
}
