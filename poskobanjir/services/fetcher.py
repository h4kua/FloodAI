import requests

from config import (
    BMKG_CUACA_URL,
    BMKG_NOWCAST_DETAIL_URL,
    BMKG_NOWCAST_FEED_URL,
    BMKG_NOWCAST_FEED_FALLBACK_URL,
    OPENWEATHER_API_KEY,
    OPENWEATHER_URL,
    POSKOBANJIR_JSON_URL,
    POSKOBANJIR_URL,
    TIMEOUT,
)


def fetch_text(url):
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def fetch_json(url):
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_poskobanjir_json() -> list:
    """Fetch TMA data from the JSON endpoint (primary, more reliable than XML)."""
    return fetch_json(POSKOBANJIR_JSON_URL)


def fetch_bmkg_cuaca() -> dict:
    """Fetch BMKG 10-day weather forecast for DKI Jakarta."""
    return fetch_json(BMKG_CUACA_URL)


def fetch_poskobanjir_xml():
    return fetch_text(POSKOBANJIR_URL)


def fetch_bmkg_feed():
    errors = []
    for url in (BMKG_NOWCAST_FEED_URL, BMKG_NOWCAST_FEED_FALLBACK_URL):
        try:
            return fetch_text(url)
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    raise RuntimeError("Gagal mengambil feed BMKG. " + " | ".join(errors))


def fetch_bmkg_alert_detail(kode_detail_cap):
    url = BMKG_NOWCAST_DETAIL_URL.format(kode_detail_cap=kode_detail_cap)
    return fetch_text(url)


def fetch_openweather(params):
    if not OPENWEATHER_API_KEY:
        raise ValueError("OPENWEATHER_API_KEY tidak ditemukan di file .env")

    query = {
        **params,
        "appid": OPENWEATHER_API_KEY,
        "units": "metric",
        "lang": "en",
    }
    response = requests.get(OPENWEATHER_URL, params=query, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_openweather_wilayah(wilayah_coords: dict) -> dict:
    """Fetch OpenWeather current weather untuk setiap kota administrasi Jakarta.

    Args:
        wilayah_coords: dict mapping wilayah name → (lat, lon)

    Returns:
        dict mapping wilayah name → raw OWM response dict.
        Wilayah yang gagal di-fetch tidak dimasukkan ke hasil.
    """
    results: dict = {}
    for wilayah, (lat, lon) in wilayah_coords.items():
        try:
            data = fetch_openweather({"lat": lat, "lon": lon})
            results[wilayah] = data
            print(f"  [OWM] {wilayah}: {data.get('weather', [{}])[0].get('description', '?')} "
                  f"{data.get('main', {}).get('temp', '?')}°C")
        except Exception as exc:
            print(f"  [WARN] OpenWeather gagal untuk {wilayah}: {exc}")
    return results
