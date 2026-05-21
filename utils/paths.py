from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"
REALTIME_NATIVE_BUNDLE_DIR = MODELS_DIR / "realtime_native_bundle"
REALTIME_NATIVE_BUNDLE_MANIFEST = REALTIME_NATIVE_BUNDLE_DIR / "manifest.json"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
REPORTS_DIR = ARTIFACTS_DIR / "reports"
CONFIG_DIR = ARTIFACTS_DIR / "configurations"
PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
POSKOBANJIR_DIR = PROJECT_ROOT / "poskobanjir"
POSKOBANJIR_CLEAN_DIR = POSKOBANJIR_DIR / "data" / "clean"
DEFAULT_REALTIME_SNAPSHOT = POSKOBANJIR_CLEAN_DIR / "realtime_snapshot.json"
