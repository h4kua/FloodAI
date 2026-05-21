"""
Minimal psycopg2 repository for Jakarta Satu ingestion data (DATA-1).

All functions accept an open connection; the caller owns commit/rollback/close.
Persistence is append-only — no UPDATE or DELETE operations.
"""

from __future__ import annotations

import logging
from datetime import datetime

from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import Json

from services.jakarta_satu_scraper import (
    AffectedRT,
    JakartaSatuSnapshot,
    WaterGateReading,
)

logger = logging.getLogger(__name__)


def insert_snapshot(conn: PgConnection, snapshot: JakartaSatuSnapshot) -> int:
    """
    Insert the master snapshot row and return its generated id.

    The returned id is used as the FK for all child table inserts.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jakarta_satu_snapshots (
                scraped_at, source_url, scrape_duration_ms, panels_found,
                raw_water_gates_text, raw_rt_impact_text, raw_area_impact_text,
                scrape_success, warnings
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                snapshot.scraped_at,
                snapshot.source_url,
                snapshot.scrape_duration_ms,
                snapshot.panels_found,
                snapshot.raw_water_gates_text or None,
                snapshot.raw_rt_impact_text or None,
                snapshot.raw_area_impact_text or None,
                snapshot.scrape_success,
                Json(snapshot.warnings) if snapshot.warnings else None,
            ),
        )
        row = cur.fetchone()
    return int(row[0])


def insert_water_gates(
    conn: PgConnection,
    snapshot_id: int,
    scraped_at: datetime,
    gates: list[WaterGateReading],
) -> int:
    """Insert water gate readings for one snapshot. Returns row count."""
    if not gates:
        return 0
    with conn.cursor() as cur:
        for gate in gates:
            cur.execute(
                """
                INSERT INTO jakarta_satu_water_gates (
                    snapshot_id, scraped_at, gate_name, water_level_cm,
                    status, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot_id,
                    scraped_at,
                    gate.gate_name,
                    gate.water_level_cm,
                    gate.status,
                    Json({
                        "gate_name": gate.gate_name,
                        "water_level_cm": gate.water_level_cm,
                        "status": gate.status,
                        "raw_line": gate.raw_line,
                    }),
                ),
            )
    return len(gates)


def insert_rt_impact(
    conn: PgConnection,
    snapshot_id: int,
    scraped_at: datetime,
    rts: list[AffectedRT],
) -> int:
    """Insert affected RT records for one snapshot. Returns row count."""
    if not rts:
        return 0
    with conn.cursor() as cur:
        for rt in rts:
            cur.execute(
                """
                INSERT INTO jakarta_satu_rt_impact (
                    snapshot_id, scraped_at, rt_identifier,
                    kelurahan, kecamatan, wilayah, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    snapshot_id,
                    scraped_at,
                    rt.rt_identifier,
                    rt.kelurahan,
                    None,      # kecamatan not reliably parseable from dashboard text
                    rt.wilayah,
                    Json({
                        "rt_identifier": rt.rt_identifier,
                        "kelurahan": rt.kelurahan,
                        "wilayah": rt.wilayah,
                        "raw_line": rt.raw_line,
                    }),
                ),
            )
    return len(rts)


def insert_area_impact(
    conn: PgConnection,
    snapshot_id: int,
    scraped_at: datetime,
    flooded_area_km2: float | None,
    raw_text: str,
) -> None:
    """Insert the aggregate flooded-area record for one snapshot."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jakarta_satu_area_impact (
                snapshot_id, scraped_at, flooded_area_km2, raw_payload
            ) VALUES (%s, %s, %s, %s)
            """,
            (
                snapshot_id,
                scraped_at,
                flooded_area_km2,
                Json({"flooded_area_km2": flooded_area_km2, "raw_text": raw_text}),
            ),
        )


def persist_snapshot(conn: PgConnection, snapshot: JakartaSatuSnapshot) -> int:
    """
    Persist a complete JakartaSatuSnapshot in one transaction.

    Inserts master snapshot row + all child records, then commits.
    Returns the snapshot_id assigned by the database.

    Does not catch exceptions — the caller is responsible for rollback
    if this raises.
    """
    snapshot_id = insert_snapshot(conn, snapshot)

    n_gates = insert_water_gates(
        conn, snapshot_id, snapshot.scraped_at, snapshot.water_gates
    )
    n_rts = insert_rt_impact(
        conn, snapshot_id, snapshot.scraped_at, snapshot.affected_rts
    )
    insert_area_impact(
        conn,
        snapshot_id,
        snapshot.scraped_at,
        snapshot.flooded_area_km2,
        snapshot.raw_area_impact_text,
    )

    conn.commit()
    logger.info(
        "Persisted snapshot id=%d: %d gate(s), %d RT(s), area=%s km²",
        snapshot_id,
        n_gates,
        n_rts,
        snapshot.flooded_area_km2,
    )
    return snapshot_id
