"""
Jakarta Satu hourly ingestion entry point (DATA-1).

Single-execution mode — safe to call from cron or Windows Task Scheduler hourly.

Exit codes:
  0  — success (warnings are non-fatal)
  1  — fatal scrape failure (ScraperError)
  2  — database connection or persistence failure

Usage:
    python scripts/run_jakarta_satu_ingest.py
    python scripts/run_jakarta_satu_ingest.py --dry-run   # scrape only, no DB write
    python scripts/run_jakarta_satu_ingest.py --wait 20   # override JS wait seconds

Cron example (every hour at :05):
    5 * * * * cd /path/to/project && python scripts/run_jakarta_satu_ingest.py >> logs/ingest.log 2>&1

Windows Task Scheduler:
    Program:  python
    Arguments: scripts\\run_jakarta_satu_ingest.py
    Start in: D:\\FloodAI
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("ingest")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Jakarta Satu dashboard and persist to PostgreSQL."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and parse but do not write to the database.",
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=15,
        metavar="SECONDS",
        help="Seconds to wait for JS rendering after page load (default: 15).",
    )
    return parser.parse_args()


def _print_summary(snapshot) -> None:
    logger.info(
        "SUMMARY scraped_at=%s panels=%d gates=%d rts=%d area_km2=%s warnings=%d",
        snapshot.scraped_at.isoformat(),
        snapshot.panels_found,
        len(snapshot.water_gates),
        len(snapshot.affected_rts),
        snapshot.flooded_area_km2,
        len(snapshot.warnings),
    )


def main() -> int:
    args = _parse_args()
    os.environ.setdefault("FLOOD_ALLOW_RUNTIME_SCRAPE", "1")
    logger.info(
        "Jakarta Satu ingest starting at %s",
        datetime.now(timezone.utc).isoformat(),
    )

    # ── Step 1: scrape ────────────────────────────────────────────────────────
    from services.jakarta_satu_scraper import ScraperError, scrape_all

    try:
        snapshot = scrape_all(wait_s=args.wait)
    except ScraperError as exc:
        logger.error("FATAL scrape failure: %s", exc)
        return 1

    logger.info(
        "Scrape complete — panels_found=%d, gates=%d, rts=%d, area=%s km², warnings=%d",
        snapshot.panels_found,
        len(snapshot.water_gates),
        len(snapshot.affected_rts),
        snapshot.flooded_area_km2,
        len(snapshot.warnings),
    )
    for w in snapshot.warnings:
        logger.warning("  [scrape warning] %s", w)

    # ── Step 2: persist (skipped in dry-run) ──────────────────────────────────
    if args.dry_run:
        logger.info("--dry-run: skipping database write.")
        _print_summary(snapshot)
        return 0

    from db.psycopg2_connection import pooled_connection
    from db.repositories.jakarta_satu_repository import persist_snapshot

    try:
        conn_ctx = pooled_connection()
        conn = conn_ctx.__enter__()
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)
        return 2

    try:
        snapshot_id = persist_snapshot(conn, snapshot)
        logger.info("Persisted as snapshot_id=%d", snapshot_id)
    except Exception as exc:
        logger.error("Database persistence failed: %s", exc)
        try:
            conn.rollback()
        except Exception:
            pass
        return 2
    finally:
        conn_ctx.__exit__(None, None, None)

    _print_summary(snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
