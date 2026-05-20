"""
TMA (Tinggi Muka Air) refresh — scheduled-job entry point.

Refreshes the live Jakarta water data the prediction pipeline reads:

  1. AWLR SIAGA thresholds   -> data/raw/awlr_thresholds.json
  2. Live water-gate levels  -> data/raw/pintu_air_latest.json

Both come from public Jakarta Satu ArcGIS FeatureServers (clean JSON, no
browser). This replaced the brittle Selenium dashboard scrape, whose panels
render inside iframes the scraper could not reach. The legacy Selenium ingest
is still available behind ``--selenium`` for diagnostics.

This sets ``FLOOD_ALLOW_RUNTIME_SCRAPE=1`` in-process *before* importing the
optional Selenium scraper, so the runtime-scrape guard only opens inside this
scheduled job and never in the production API (per project constraint).

Usage:
    python scripts/run_tma_scraper.py
    python scripts/run_tma_scraper.py --selenium        # also run legacy DOM scrape + DB write
    python scripts/run_tma_scraper.py --selenium --dry-run

Windows Task Scheduler (hourly):
    Program:   python
    Arguments: scripts\\run_tma_scraper.py
    Start in:  D:\\FloodAI - Copy

Cron (every hour at :05):
    5 * * * * cd /path/to/project && python scripts/run_tma_scraper.py >> logs/tma.log 2>&1

Exit codes:
    0  — at least one live source refreshed successfully
    2  — all configured sources failed (last-known cache is still served downstream)
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the project root is importable when launched as a bare script
# (python scripts/run_tma_scraper.py) — Task Scheduler / cron friendly.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Open the runtime-scrape guard for this scheduled job ONLY, before the optional
# Selenium scraper module is imported anywhere downstream.
os.environ["FLOOD_ALLOW_RUNTIME_SCRAPE"] = "1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("tma_scraper_job")


def _refresh_awlr() -> bool:
    """Refresh AWLR SIAGA thresholds. Returns True on success."""
    try:
        from app.services.awlr_threshold_fetcher import get_awlr_thresholds

        payload = get_awlr_thresholds(force_refresh=True)
        if payload and payload.get("gate_count"):
            logger.info("AWLR thresholds refreshed — %d gates", payload["gate_count"])
            return True
        logger.warning("AWLR thresholds unavailable (no network, no cache).")
    except Exception as exc:  # noqa: BLE001 — scheduled job must never crash
        logger.warning("AWLR threshold refresh failed (non-fatal): %s", exc)
    return False


def _refresh_pintu_air() -> bool:
    """Refresh live water-gate readings. Returns True on success."""
    try:
        from app.services.pintu_air_fetcher import get_pintu_air

        payload = get_pintu_air(force_refresh=True)
        if payload and payload.get("gate_count"):
            logger.info(
                "Pintu Air refreshed — %d gates, max_status=%s, latest=%s",
                payload["gate_count"],
                payload.get("max_status"),
                payload.get("latest_observation_utc"),
            )
            return True
        logger.warning("Pintu Air unavailable (no network, no cache).")
    except Exception as exc:  # noqa: BLE001 — scheduled job must never crash
        logger.warning("Pintu Air refresh failed (non-fatal): %s", exc)
    return False


def _run_legacy_selenium() -> int:
    """Optional legacy Selenium dashboard scrape + DB persist. Never crashes."""
    try:
        from scripts.run_jakarta_satu_ingest import main as ingest_main

        return ingest_main()
    except Exception as exc:  # noqa: BLE001
        logger.error("Legacy Selenium ingest failed: %s", exc)
        return 2


def main() -> int:
    logger.info("TMA refresh starting at %s", datetime.now(timezone.utc).isoformat())

    awlr_ok = _refresh_awlr()
    pintu_ok = _refresh_pintu_air()

    if "--selenium" in sys.argv:
        sys.argv.remove("--selenium")
        logger.info("Running legacy Selenium ingest (diagnostic).")
        _run_legacy_selenium()  # advisory only; does not gate the exit code

    if awlr_ok or pintu_ok:
        logger.info("TMA refresh complete (awlr_ok=%s, pintu_air_ok=%s)", awlr_ok, pintu_ok)
        return 0

    logger.error("TMA refresh failed for all sources — downstream uses last-known cache.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
