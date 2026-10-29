#!/usr/bin/env python
"""
Flag shelter candidates with two official BPBD DKI lists.

  bpbd_site           the place is on BPBD's list of flood evacuation sites
                      (data-rekapitulasi-lokasi-pengungsi-banjir…xls, 61 sites, 2018;
                      names and kelurahan only, no coordinates)
  flood_prone_school  the place is a school on the list of flood-prone schools
                      (data/bundled/flood_prone_schools.json, 319 schools with coordinates)

Matching:
  * a flood-prone school matches a candidate school within 200 m when their
    names share the school number (or, without numbers, two name words);
  * a BPBD site matches a candidate within 3 km of its kelurahan (located once
    with Nominatim, 1 request a second) whose name holds every word of the site
    name, after spelling fixes such as "SDN" -> "sd negeri".

Output: data/bundled/shelter_flags.json  {shelter_id: {...flags}}, plus the
BPBD sites that matched no candidate, so they can be added by hand later.
Run (repo root):  python scripts/build_shelter_flags.py
"""

from __future__ import annotations

import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
SHELTERS = _ROOT / "data" / "bundled" / "jakarta_shelters.json"
SCHOOLS = _ROOT / "data" / "bundled" / "flood_prone_schools.json"
BPBD_SITES = _ROOT / "data" / "raw" / "data-rekapitulasi-lokasi-pengungsi-banjir-di-provinsi-dki-jakarta-komponen-data.xls"
DST = _ROOT / "data" / "bundled" / "shelter_flags.json"

_SCHOOL_RADIUS_M = 200.0
_SITE_RADIUS_M = 3000.0
_SPELLING = [
    (r"\bsdn\b", "sd negeri"), (r"\bsmpn\b", "smp negeri"), (r"\bsman?\b", "sma negeri"),
    (r"\bsmkn\b", "smk negeri"), (r"\bmi\b", "madrasah ibtidaiyah"), (r"\bpg\b", "pagi"), (r"\bpt\b", "petang"),
    (r"\bkel\b", "kelurahan"), (r"\bkec\b", "kecamatan"), (r"\bmushola|musholla|mushalla|musala\b", "mushala"),
    (r"\bmesjid\b", "masjid"), (r"\bgor\b", "gelanggang olahraga"), (r"\bkantor lurah\b", "kantor kelurahan"),
]
_FILLER = {"jakarta", "dki", "jl", "jalan", "no", "dan", "posko", "aula", "gedung"}
# Words every school name shares; a match needs more than these.
_GENERIC = {"sd", "smp", "sma", "smk", "smu", "tk", "negeri", "swasta", "pagi", "petang", "sekolah"}


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def words(name: str, *, drop_rt_rw: bool = True) -> set[str]:
    text = (name or "").lower().replace(".", " ")
    if drop_rt_rw:  # "SMPN 26 JAKARTA (RW 05)" -> the school, not the RW
        text = re.sub(r"\(?\b(rt|rw)\s*\d+(\s*/\s*\d+)?\)?", " ", text)
    for pattern, repl in _SPELLING:
        text = re.sub(pattern, repl, text)
    tokens = re.findall(r"[a-z]+|\d+", text)
    return {str(int(t)) if t.isdigit() else t for t in tokens if t not in _FILLER}


def numbers(tokens: set[str]) -> set[str]:
    return {t for t in tokens if t.isdigit()}


def school_matches(candidate: set[str], school: set[str]) -> bool:
    cn, sn = numbers(candidate), numbers(school)
    specific = (candidate & school) - _GENERIC - cn
    if cn and sn:
        return bool(cn & sn) and len(specific) >= 1
    if cn or sn:  # "SDN Cempaka Putih Barat 17" is not "Yayasan … Cempaka Putih"
        return False
    return len(specific) >= 2


def site_words(name: str) -> tuple[set[str], bool]:
    """Words of a BPBD site name and whether they keep RT/RW: "Sekretariat RW 010"
    needs its RW number, "SMPN 26 Jakarta (RW 05)" does not."""
    stripped = words(name)
    if len(stripped - _GENERIC - numbers(stripped)) >= 1 and len(stripped) >= 2:
        return stripped, False
    return words(name, drop_rt_rw=False), True


def is_school(shelter: dict) -> bool:
    return "school" in (shelter.get("amenity") or "") + (shelter.get("building") or "") \
        or "kindergarten" in (shelter.get("amenity") or "")


def read_sites() -> list[dict]:
    text = BPBD_SITES.read_text(encoding="utf-8")
    rows = re.findall(r"<tr>(.*?)</tr>", text, re.S)
    cells = lambda r: [html.unescape(re.sub(r"<.*?>", "", c)).strip() for c in re.findall(r"<t[hd]>(.*?)</t[hd]>", r, re.S)]
    head = cells(rows[0])
    return [dict(zip(head, cells(r))) for r in rows[1:]]


def locate_kelurahan(kelurahan: str, kecamatan: str) -> tuple[float, float] | None:
    q = urllib.parse.urlencode({"q": f"{kelurahan}, {kecamatan}, Jakarta", "format": "json", "limit": 1, "countrycodes": "id"})
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{q}", headers={"User-Agent": "deFlood.ai thesis build script"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    time.sleep(1.1)  # Nominatim usage policy: at most one request a second
    return (float(data[0]["lat"]), float(data[0]["lon"])) if data else None


def main() -> int:
    shelters = json.loads(SHELTERS.read_text(encoding="utf-8"))["shelters"]
    for s in shelters:
        s["_words"] = words(s["name"])
        s["_words_rt_rw"] = words(s["name"], drop_rt_rw=False)
    flags: dict[str, dict] = {}

    schools = json.loads(SCHOOLS.read_text(encoding="utf-8"))["schools"]
    matched_schools = 0
    for school in schools:
        sw = words(school["name"])
        hits = [s for s in shelters
                if is_school(s)
                and haversine_m(school["lat"], school["lon"], s["lat"], s["lon"]) <= _SCHOOL_RADIUS_M
                and school_matches(s["_words"], sw)]
        for s in hits:
            flags.setdefault(s["id"], {})["flood_prone_school"] = school["name"]
        matched_schools += bool(hits)

    sites = read_sites()
    places: dict[tuple[str, str], tuple[float, float] | None] = {}
    unmatched = []
    for site in sites:
        key = (site["kelurahan"], site["kecamatan"])
        if key not in places:
            places[key] = locate_kelurahan(*key)
        centre = places[key]
        sw, keeps_rt_rw = site_words(site["lokasi"])
        key_words = "_words_rt_rw" if keeps_rt_rw else "_words"
        # A name made only of generic words ("SDN 04") could be any school nearby.
        named = bool(sw - _GENERIC - numbers(sw))
        hits = [] if centre is None or not named else [
            s for s in shelters
            if sw <= s[key_words] and haversine_m(centre[0], centre[1], s["lat"], s["lon"]) <= _SITE_RADIUS_M
        ]
        if hits:
            best = min(hits, key=lambda s: haversine_m(centre[0], centre[1], s["lat"], s["lon"]))
            people = site.get("jumlah_jiwa", "")
            flags.setdefault(best["id"], {})["bpbd_site"] = {
                "name": site["lokasi"], "kelurahan": site["kelurahan"],
                "people": int(people) if people.isdigit() else None, "year": site.get("periode_data"),
            }
        else:
            unmatched.append({"name": site["lokasi"], "kelurahan": site["kelurahan"], "kecamatan": site["kecamatan"]})

    payload = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sources": [BPBD_SITES.name, SCHOOLS.name],
            "bpbd_sites": len(sites), "bpbd_sites_matched": len(sites) - len(unmatched),
            "flood_prone_schools": len(schools), "flood_prone_schools_matched": matched_schools,
        },
        "flags": flags,
        "bpbd_sites_unmatched": unmatched,
    }
    DST.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(payload["_meta"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
