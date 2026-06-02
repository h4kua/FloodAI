from config import CLEAN_DATA_DIR, JAKARTA_LAT, JAKARTA_LON, RAW_DATA_DIR
from processing.cleaner import clean_data
from services.fetcher import (
    fetch_bmkg_alert_detail,
    fetch_bmkg_feed,
    fetch_openweather,
    fetch_poskobanjir_xml,
)
from services.parser import (
    build_realtime_snapshot,
    parse_bmkg_alert,
    parse_bmkg_feed,
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
            # C2 fix: use feed metadata so bmkg_alerts is never empty when feed has items
            alerts.append(_feed_item_to_basic_alert(item))
    return alerts


def run_pipeline():
    print("=" * 50)
    print("POSKOBANJIR REALTIME PIPELINE START")
    print("=" * 50)

    print("\n[STEP 1] Fetch data Posko Banjir...")
    poskobanjir_records = []
    try:
        poskobanjir_xml = fetch_poskobanjir_xml()
        poskobanjir_records = parse_poskobanjir_xml(poskobanjir_xml)
        print(f"Total records Posko Banjir: {len(poskobanjir_records)}")
    except Exception as exc:
        print(f"[WARN] Gagal fetch Posko Banjir: {exc} — melanjutkan tanpa data TMA")

    if poskobanjir_records:
        print("\n[STEP 2] Clean dan simpan data Posko Banjir...")
        df = clean_data(poskobanjir_records)
        save_csv(df, CLEAN_DATA_DIR / "poskobanjir_latest.csv")
    else:
        print("[WARN] Melewati step 2 — tidak ada data TMA.")

    print("\n[STEP 3] Fetch data OpenWeather Jakarta...")
    weather = {}
    try:
        weather = fetch_openweather({"lat": JAKARTA_LAT, "lon": JAKARTA_LON})
        save_json(weather, RAW_DATA_DIR / "openweather_current.json")
        print(f"OpenWeather lokasi: {weather.get('name', 'unknown')}")
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

    if not any([poskobanjir_records, weather, bmkg_feed]):
        print("[ERROR] Semua sumber data gagal. Pipeline berhenti.")
        return

    print("\n[STEP 5] Bangun snapshot realtime gabungan...")
    snapshot = build_realtime_snapshot(
        poskobanjir_records=poskobanjir_records,
        weather=weather,
        bmkg_feed=bmkg_feed,
        bmkg_alerts=bmkg_alerts,
    )
    save_json(snapshot, CLEAN_DATA_DIR / "realtime_snapshot.json")

    print("\nPIPELINE SELESAI!")


if __name__ == "__main__":
    run_pipeline()
