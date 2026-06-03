from pathlib import Path
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

TIMEOUT = 15

POSKOBANJIR_URL = "https://poskobanjir.dsdadki.web.id/xmldata.xml"
POSKOBANJIR_JSON_URL = "https://poskobanjir.dsdadki.web.id/datatmalaststatus.json"
BMKG_CUACA_URL = "https://poskobanjir.dsdadki.web.id/cuaca.json"
BMKG_NOWCAST_FEED_URL = "https://www.bmkg.go.id/alerts/nowcast/id"
BMKG_NOWCAST_FEED_FALLBACK_URL = "https://www.bmkg.go.id/alerts/nowcast/id/rss.xml"
BMKG_NOWCAST_DETAIL_URL = (
    "https://www.bmkg.go.id/alerts/nowcast/id/{kode_detail_cap}_alert.xml"
)
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
JAKARTA_LAT = float(os.getenv("JAKARTA_LAT", "-6.2088"))
JAKARTA_LON = float(os.getenv("JAKARTA_LON", "106.8456"))

RAW_DATA_DIR = ROOT_DIR / "data" / "raw"
CLEAN_DATA_DIR = ROOT_DIR / "data" / "clean"
