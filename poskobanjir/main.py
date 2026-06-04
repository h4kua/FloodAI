import sys
from config import CLEAN_DATA_DIR, JAKARTA_LAT, JAKARTA_LON, JAKARTA_WILAYAH_COORDS, RAW_DATA_DIR
from processing.cleaner import clean_data
from services.fetcher import (
    fetch_bmkg_alert_detail,
    fetch_bmkg_cuaca,
    fetch_bmkg_feed,
    fetch_openweather,
    fetch_openweather_wilayah,
    fetch_poskobanjir_json,
    fetch_poskobanjir_xml,
)
from services.parser import (
    build_realtime_snapshot,
    parse_bmkg_alert,
    parse_bmkg_cuaca,
    parse_bmkg_cuaca_per_wilayah,
    parse_bmkg_feed,
    parse_poskobanjir_json,
    parse_poskobanjir_xml,
)
from storage.saver import save_csv, save_json


def _feed_item_to_basic_alert(item: dict) -> dict:
    """Build a minimal alert struct from RSS feed item when CAP detail fetch fails."""
    title = item.get("title", "")
    description = item.get("description", "")
    area_desc = title.split("—")[-1].strip() if "—" in title else description[:120]
    return {
        "identifier": item.get("alert_code", ""),
        "alert_code": item.get("alert_code", ""),
        "event": title.split("—")[0].strip() if "—" in title else title,
        "urgency": "Unknown",
        "severity": "Moderate",
        "certainty": "Possible",
        "effective": item.get("pub_date", ""),
        "expires": "",
        "headline": title,
        "description": description,
        "instruction": "",
        "area_desc": area_desc,
        "polygons": [],
        "parameters": {},
        "_source": "feed_fallback",
    }


def _fetch_bmkg_alerts(feed_items):
    alerts = []
    for item in feed_items:
        alert_code = item.get("alert_code")
        if not alert_code:
            continue

        try:
            detail_xml = fetch_bmkg_alert_detail(alert_code)
            alert = parse_bmkg_alert(detail_xml)
            alert["alert_code"] = alert_code
            alerts.append(alert)
            print(f"[BMKG] Detail berhasil diambil untuk {alert_code}")
        except Exception as exc:
            print(f"[BMKG] Gagal detail {alert_code}: {exc} — pakai feed fallback")
            alerts.append(_feed_item_to_basic_alert(item))
    return alerts


def _fetch_tma_records() -> list:
    """Try JSON endpoint first (reliable), fall back to XML scraper."""
    try:
        raw = fetch_poskobanjir_json()
        records = parse_poskobanjir_json(raw)
        print(f"[TMA] JSON endpoint OK — {len(records)} stasiun aktif")
        return records
    except Exception as exc:
        print(f"[TMA] JSON gagal ({exc}), coba XML fallback...")

    try:
        xml_text = fetch_poskobanjir_xml()
        records = parse_poskobanjir_xml(xml_text)
        print(f"[TMA] XML fallback OK — {len(records)} records")
        return records
    except Exception as exc:
        print(f"[WARN] TMA XML juga gagal: {exc} — melanjutkan tanpa data TMA")
        return []


def run_pipeline():
    print("=" * 50)
    print("POSKOBANJIR REALTIME PIPELINE START")
    print("=" * 50)

    print("\n[STEP 1] Fetch data TMA (JSON primary, XML fallback)...")
    poskobanjir_records = _fetch_tma_records()

    if poskobanjir_records:
        print("\n[STEP 2] Clean dan simpan data TMA...")
        df = clean_data(poskobanjir_records)
        save_csv(df, CLEAN_DATA_DIR / "poskobanjir_latest.csv")
    else:
        print("[WARN] Melewati step 2 — tidak ada data TMA.")

    print("\n[STEP 3] Fetch data OpenWeather — pusat + per wilayah Jakarta...")
    weather = {}
    openweather_wilayah = {}
    try:
        # 1. Titik pusat (tetap dipakai ML feature builder)
        weather = fetch_openweather({"lat": JAKARTA_LAT, "lon": JAKARTA_LON})
        save_json(weather, RAW_DATA_DIR / "openweather_current.json")
        print(f"  [OWM] Pusat Jakarta: {weather.get('name', 'unknown')} "
              f"{weather.get('main', {}).get('temp', '?')}°C")

        # 2. Per kota administrasi (untuk tampilan per wilayah di frontend)
        print("  Fetching per wilayah...")
        openweather_wilayah = fetch_openweather_wilayah(JAKARTA_WILAYAH_COORDS)
        save_json(openweather_wilayah, RAW_DATA_DIR / "openweather_wilayah.json")
        print(f"  Berhasil: {len(openweather_wilayah)}/{len(JAKARTA_WILAYAH_COORDS)} wilayah")
    except Exception as exc:
        print(f"[WARN] Gagal fetch OpenWeather: {exc}")

    print("\n[STEP 4] Fetch RSS dan detail alert BMKG...")
    bmkg_feed = []
    bmkg_alerts = []
    try:
        bmkg_feed_xml = fetch_bmkg_feed()
        bmkg_feed = parse_bmkg_feed(bmkg_feed_xml)
        bmkg_alerts = _fetch_bmkg_alerts(bmkg_feed)
        save_json(bmkg_feed, RAW_DATA_DIR / "bmkg_nowcast_feed.json")
        save_json(bmkg_alerts, RAW_DATA_DIR / "bmkg_nowcast_alerts.json")
        print(f"Total alert BMKG aktif: {len(bmkg_alerts)}")
    except Exception as exc:
        print(f"[WARN] Gagal fetch BMKG: {exc} — tidak ada alert")

    print("\n[STEP 5] Fetch prakiraan cuaca BMKG (cuaca.json)...")
    bmkg_forecast = []
    bmkg_forecast_per_wilayah = {}
    try:
        cuaca_raw = fetch_bmkg_cuaca()
        bmkg_forecast = parse_bmkg_cuaca(cuaca_raw)
        bmkg_forecast_per_wilayah = parse_bmkg_cuaca_per_wilayah(cuaca_raw)
        save_json(cuaca_raw, RAW_DATA_DIR / "bmkg_cuaca.json")
        print(f"Prakiraan cuaca: {len(bmkg_forecast)} slot ke depan")
        print(f"Per wilayah: {list(bmkg_forecast_per_wilayah.keys())}")
        for slot in bmkg_forecast:
            print(f"  {slot['local_datetime']} — {slot['weather_desc']} "
                  f"({slot['tmin']}–{slot['tmax']}°C)")
    except Exception as exc:
        print(f"[WARN] Gagal fetch cuaca BMKG: {exc}")

    failed_sources = sum([
        len(poskobanjir_records) == 0,
        not weather,
        not bmkg_feed,
    ])

    if failed_sources == 3:
        print("[ERROR] Semua sumber data gagal (TMA + cuaca + BMKG). Pipeline berhenti.")
        return False

    if failed_sources > 0:
        print(f"[WARN] {failed_sources}/3 sumber data gagal — melanjutkan dengan data parsial.")

    print("\n[STEP 6] Bangun snapshot realtime gabungan...")
    snapshot = build_realtime_snapshot(
        poskobanjir_records=poskobanjir_records,
        weather=weather,
        bmkg_feed=bmkg_feed,
        bmkg_alerts=bmkg_alerts,
        bmkg_forecast=bmkg_forecast,
        bmkg_forecast_per_wilayah=bmkg_forecast_per_wilayah,
    )
    save_json(snapshot, CLEAN_DATA_DIR / "realtime_snapshot.json")

    print(f"\nPIPELINE SELESAI! ({3 - failed_sources}/3 sumber berhasil)")
    return True


if __name__ == "__main__":
    ok = run_pipeline()
    sys.exit(0 if ok else 1)
