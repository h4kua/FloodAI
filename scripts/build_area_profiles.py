#!/usr/bin/env python
"""
Build frontend/src/data/areaProfiles.json for the Beranda's "Cek daerahku" card: each of the 42 model
kecamatan with its kota, centre and the number of days BPBD recorded a flood there in 2013-2025, and
its kelurahan with their own flood days (and a centre where the Nominatim cache has one).

Flood days: BPBD dated events 2013-2019 (data/processed/events_clean.csv) and the RW recap 2020-2025
(data/raw/rekap_kejadian_2020_2025.csv), each (place, date) counted once, as in
scripts/hourly_rain_experiment.flood_kecamatan_days. Dates for 2023-2025 are only partly readable, so
recent years count low. Centres: the project dataset's kecamatan coordinates; kelurahan from
data/raw/kelurahan_geocode_cache.json (only the flood-prone ones).
Usage (repo root): python scripts/build_area_profiles.py
"""

from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from scripts.build_kelurahan_flood_history import _CANONICAL_BY_SLUG, _slug  # noqa: E402
from scripts.hourly_rain_experiment import EVENTS_CSV, REKAP_CSV, _dates_in, flood_kecamatan_days  # noqa: E402

OUT = _ROOT / "frontend" / "src" / "data" / "areaProfiles.json"
GEOCODE = _ROOT / "data" / "raw" / "kelurahan_geocode_cache.json"
CLEANED = _ROOT / "data" / "processed" / "cleaned_flood_data_jakarta.csv"


def title(name: str) -> str:
    return " ".join(w.capitalize() for w in re.sub(r"\s+", " ", str(name)).strip().split(" "))


def kelurahan_days() -> pd.DataFrame:
    rows = []
    rekap = pd.read_csv(REKAP_CSV).drop_duplicates()
    for kec, kel, year, month, text in zip(rekap["kecamatan"], rekap["kelurahan"], rekap["tahun"], rekap["bulan"],
                                          rekap["tanggal_kejadian"]):
        rows += [(_slug(str(kec)), str(kel).strip().upper(), d) for d in _dates_in(text, int(year), int(month))]
    events = pd.read_csv(EVENTS_CSV, usecols=["event_date", "kecamatan", "kelurahan"])
    events = events[pd.to_datetime(events["event_date"]).dt.year < 2020]
    rows += [(_slug(str(k)), str(kel).strip().upper(), pd.Timestamp(d).normalize())
             for k, kel, d in zip(events["kecamatan"], events["kelurahan"], events["event_date"])]
    frame = pd.DataFrame(rows, columns=["kecamatan", "kelurahan", "date"])
    frame = frame[frame["kecamatan"].isin(_CANONICAL_BY_SLUG) & (frame["kelurahan"] != "NAN")].copy()
    # One kelurahan, several spellings ("KEL. PULOGEBANG", "PULO GEBANG", "PONDKO LABU"): strip the
    # prefix, then join names within a kecamatan that differ by a space or a typo, under the spelling
    # used most often.
    frame["kelurahan"] = frame["kelurahan"].str.replace(r"^KEL(URAHAN)?\.?\s+", "", regex=True).str.strip()
    canon = {}
    for kec, g in frame.groupby("kecamatan"):
        names = g["kelurahan"].value_counts().index.tolist()  # most used first
        chosen: list[str] = []
        for name in names:
            key = re.sub(r"[^A-Z0-9]", "", name)
            match = next((c for c in chosen if re.sub(r"[^A-Z0-9]", "", c) == key
                          or (abs(len(re.sub(r"[^A-Z0-9]", "", c)) - len(key)) <= 1
                              and difflib.SequenceMatcher(None, re.sub(r"[^A-Z0-9]", "", c), key).ratio() >= 0.8)), None)
            canon[(kec, name)] = match or name
            if match is None:
                chosen.append(name)
    frame["kelurahan"] = [canon[(k, n)] for k, n in zip(frame["kecamatan"], frame["kelurahan"])]
    frame = frame.drop_duplicates()
    # A few BPBD rows file a kelurahan under the wrong kecamatan (Kampung Melayu: Jatinegara 349 days,
    # Duren Sawit 4). Where one kecamatan holds under a fifth of the days the main one has, its rows move
    # to the main one (a date already recorded there is counted once).
    days = frame.groupby(["kecamatan", "kelurahan"]).size().rename("days").reset_index()
    main = days.loc[days.groupby("kelurahan")["days"].idxmax()].set_index("kelurahan")
    stray = days[days["days"] < 0.2 * days["kelurahan"].map(main["days"])]
    move = {(k, n): main.loc[n, "kecamatan"] for k, n in zip(stray["kecamatan"], stray["kelurahan"])}
    frame["kecamatan"] = [move.get((k, n), k) for k, n in zip(frame["kecamatan"], frame["kelurahan"])]
    frame = frame.drop_duplicates()
    return frame.groupby(["kecamatan", "kelurahan"]).size().rename("days").reset_index()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    kec_days = flood_kecamatan_days().groupby("kecamatan").size()
    cleaned = pd.read_csv(CLEANED).drop_duplicates("name_3").set_index("name_3")
    geocode = json.loads(GEOCODE.read_text(encoding="utf-8"))
    kel = kelurahan_days()
    out = []
    for slug in sorted(_CANONICAL_BY_SLUG):
        if slug not in cleaned.index:
            continue
        kels = []
        for _, r in kel[kel["kecamatan"] == slug].sort_values("days", ascending=False).iterrows():
            entry = {"name": title(r["kelurahan"]), "flood_days": int(r["days"])}
            hit = next((v for k, v in geocode.items()
                        if k.split("|")[0] == r["kelurahan"] and _slug(k.split("|")[1]) == slug), None)
            if hit:
                entry["lat"], entry["lon"] = round(hit[0], 5), round(hit[1], 5)
            kels.append(entry)
        out.append({"slug": slug, "name": _CANONICAL_BY_SLUG[slug], "kota": title(cleaned.loc[slug, "name_2"]),
                    "lat": round(float(cleaned.loc[slug, "lat"]), 5), "lon": round(float(cleaned.loc[slug, "long"]), 5),
                    "flood_days": int(kec_days.get(slug, 0)), "kelurahan": kels})
    ranked = sorted(out, key=lambda k: -k["flood_days"])
    for i, k in enumerate(ranked, start=1):
        k["rank"] = i
    OUT.write_text(json.dumps({"period": "2013-2025", "count": len(out), "kecamatan": out}, ensure_ascii=False,
                              separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} kecamatan, {sum(len(k['kelurahan']) for k in out)} kelurahan "
          f"({sum('lat' in x for k in out for x in k['kelurahan'])} with a centre) -> {OUT}")
    print("most flood days:", [(k["name"], k["flood_days"]) for k in ranked[:5]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
