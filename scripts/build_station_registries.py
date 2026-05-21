"""
Build AWLR + ARR station registries from the public Jakarta Satu FeatureServers.

Outputs:
  app/data/awlr_stations.json  — water-level stations: name, lat, lon, SIAGA thresholds
  app/data/arr_stations.json   — rainfall stations: name, lat, lon, river basin (DAS)

IMPORTANT (confirmed by inspecting the live services):
  * The AWLR layer carries the SIAGA threshold bands and coordinates (reused here
    via app.services.awlr_threshold_fetcher).
  * The ARR layer is a STATION REGISTRY only — fields NAMAOBJ/LAT/LONG_/DAS/WADMKK/
    ALAMAT. It does NOT expose a live rainfall value, so there is no
    rainfall_mm_per_hour to extract; we cache station locations for spatial
    nearest-gauge lookup and record that readings are unavailable from this feed.

Run:
    python scripts/build_station_registries.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Make `app` importable when launched as a bare script (python scripts/...).
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_AWLR_DST = _PROJECT_ROOT / "app" / "data" / "awlr_stations.json"
_ARR_DST = _PROJECT_ROOT / "app" / "data" / "arr_stations.json"

_ARR_URL = (
    "https://jakartasatu.jakarta.go.id/server/rest/services/"
    "Automatic_Rainfall_Recorder_ARR/FeatureServer/0/query"
    "?where=1%3D1&outFields=*&f=json"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_awlr_stations() -> dict:
    """Reshape the AWLR threshold dataset into a station registry with coords."""
    from app.services.awlr_threshold_fetcher import get_awlr_thresholds

    payload = get_awlr_thresholds(force_refresh=True) or {}
    stations = []
    for gate in payload.get("gates", []):
        lat, lon = gate.get("lat"), gate.get("lon")
        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            continue
        stations.append(
            {
                "station_name": gate.get("name"),
                "lat": lat,
                "lon": lon,
                "kali": gate.get("kali"),
                "wadmkk": gate.get("wadmkk"),
                "siaga1_cm": gate.get("siaga1_cm"),
                "siaga_1": gate.get("siaga_1"),
                "siaga_2": gate.get("siaga_2"),
                "siaga_3": gate.get("siaga_3"),
                "siaga_4": gate.get("siaga_4"),
            }
        )
    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": _now(),
            "source": "jakartasatu AWLR FeatureServer (via awlr_threshold_fetcher)",
            "station_count": len(stations),
        },
        "stations": stations,
    }


def build_arr_stations() -> dict:
    """Fetch the ARR rainfall-recorder station registry (locations only)."""
    resp = requests.get(_ARR_URL, timeout=20, headers={"User-Agent": "JakartaFloodSystem/1.0"})
    resp.raise_for_status()
    features = resp.json().get("features", [])
    stations = []
    for feat in features:
        a = feat.get("attributes", {}) or {}
        name = (a.get("NAMAOBJ") or "").strip()
        lat, lon = a.get("LAT"), a.get("LONG_")
        if not name or not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            continue
        stations.append(
            {
                "station_name": name,
                "lat": lat,
                "lon": lon,
                "das": (a.get("DAS") or "").strip(),
                "wadmkk": (a.get("WADMKK") or "").strip(),
                "alamat": (a.get("ALAMAT") or "").strip(),
            }
        )
    return {
        "_meta": {
            "schema_version": "1",
            "generated_at": _now(),
            "source": "jakartasatu ARR (Automatic Rainfall Recorder) FeatureServer",
            "station_count": len(stations),
            "note": "Registry of rainfall-gauge locations. This feed does NOT expose live rainfall_mm_per_hour values.",
        },
        "stations": stations,
    }


def main() -> int:
    _AWLR_DST.parent.mkdir(parents=True, exist_ok=True)

    awlr = build_awlr_stations()
    _AWLR_DST.write_text(json.dumps(awlr, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {awlr['_meta']['station_count']} AWLR stations -> {_AWLR_DST}")

    try:
        arr = build_arr_stations()
        _ARR_DST.write_text(json.dumps(arr, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {arr['_meta']['station_count']} ARR stations -> {_ARR_DST}")
    except requests.RequestException as exc:
        print(f"ARR fetch failed (skipped): {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
