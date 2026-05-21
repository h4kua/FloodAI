"""
PostgreSQL runtime healthcheck for the Jakarta Flood Prediction System.

Checks:
  1. Connection + latency
  2. Basic queries (SELECT 1, server info, transaction cycle)
  3. Schema validation (required tables + critical columns)
  4. Migration state (schema_migrations table)
  5. Write round-trip (insert/read/rollback via trend_history)
  6. pipeline_writer smoke test (full 6-stage commit)

Exit codes:
  0  — all checks pass
  1  — one or more CRITICAL checks failed

Usage:
    python scripts/check_postgres_runtime.py
"""

from __future__ import annotations

import os
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_REQUIRED_TABLES = [
    "schema_migrations",
    "snapshots",
    "snapshot_sources",
    "pipeline_runs",
    "perception_results",
    "reasoning_results",
    "evaluation_results",
    "decisions",
    "trust_breakdowns",
    "failure_logs",
    "calibration_metrics",
    "ground_truth_outcomes",
    "replay_scenarios",
    "scenario_runs",
    "trend_history",
    "jakarta_satu_snapshots",
    "jakarta_satu_water_gates",
    "jakarta_satu_rt_impact",
    "jakarta_satu_area_impact",
]

_SNAPSHOT_REQUIRED_COLS = [
    "id", "snapshot_hash", "fetched_at_utc", "first_seen_at",
    "observation_id", "location", "openweather", "poskobanjir", "bmkg_alerts",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt(ok: bool, label: str, detail: str = "", critical: bool = False) -> str:
    status = "OK  " if ok else ("FAIL" if critical else "WARN")
    crit = " [CRITICAL]" if critical and not ok else ""
    suffix = f": {detail}" if detail else ""
    return f"  [{status}]{crit}  {label}{suffix}"


def _connect():
    import psycopg2
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    name = os.getenv("DB_NAME", "flood_ai")
    user = os.getenv("DB_USER", "postgres")
    pw   = os.getenv("DB_PASSWORD", "")
    if not pw:
        raise RuntimeError("DB_PASSWORD not set in environment")
    t0 = time.perf_counter()
    conn = psycopg2.connect(
        host=host, port=port, dbname=name, user=user, password=pw,
        connect_timeout=10, application_name="flood-ai-healthcheck",
    )
    conn.autocommit = False
    ms = round((time.perf_counter() - t0) * 1000, 1)
    return conn, ms, f"{host}:{port}/{name} user={user}"


# ── Individual checks ─────────────────────────────────────────────────────────

def check_basic_queries(conn) -> list[tuple[bool, str, str]]:
    results = []
    cur = conn.cursor()

    cur.execute("SELECT 1")
    results.append((cur.fetchone()[0] == 1, "SELECT 1", ""))

    cur.execute("SELECT current_database(), current_user, version()")
    db, usr, ver = cur.fetchone()
    results.append((True, "server info", f"db={db} user={usr} pg={ver[:35]}.."))

    cur.execute("SELECT txid_current()")
    txid = cur.fetchone()[0]
    conn.commit()
    results.append((txid is not None, "transaction cycle", f"txid={txid} commit=OK"))

    cur.close()
    return results


def check_schema(conn) -> tuple[list[str], list[str]]:
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )
    existing = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.commit()
    missing = [t for t in _REQUIRED_TABLES if t not in existing]
    present = [t for t in _REQUIRED_TABLES if t in existing]
    return present, missing


def check_snapshot_columns(conn) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='snapshots'"
    )
    existing = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.commit()
    return [c for c in _SNAPSHOT_REQUIRED_COLS if c not in existing]


def check_migrations(conn) -> tuple[int, int, list[str]]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT filename, success FROM schema_migrations ORDER BY applied_at ASC"
        )
        rows = cur.fetchall()
        conn.commit()
        applied = sum(1 for r in rows if r[1])
        failed  = [r[0] for r in rows if not r[1]]
        return applied, len(failed), failed
    except Exception as exc:
        conn.rollback()
        return 0, 1, [f"schema_migrations unreadable: {exc}"]
    finally:
        cur.close()


def check_write_roundtrip(conn) -> tuple[bool, str]:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO trend_history
                (station_id, observed_at, probability, risk_level,
                 water_level_ratio, rainfall_mm)
            VALUES ('_healthcheck_probe', NOW(), 0.01, 'SAFE', 0.1, 0.0)
            RETURNING id
            """,
        )
        row_id = cur.fetchone()[0]

        cur.execute(
            "SELECT station_id, probability, risk_level FROM trend_history WHERE id = %s",
            (row_id,),
        )
        r = cur.fetchone()
        assert r and r[0] == "_healthcheck_probe"

        conn.rollback()

        cur.execute("SELECT COUNT(*) FROM trend_history WHERE id = %s", (row_id,))
        assert cur.fetchone()[0] == 0, "rollback did not remove the row"

        return True, f"insert+read+rollback OK id={row_id}"
    except Exception as exc:
        conn.rollback()
        return False, str(exc)[:120]
    finally:
        cur.close()


def check_pipeline_writer() -> tuple[bool, str]:
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from db.pipeline_writer import (
            DecisionPayload,
            EvaluationPayload,
            PerceptionPayload,
            PipelineRunConfig,
            ReasoningPayload,
            execute_pipeline,
        )

        result = execute_pipeline(
            snapshot_input={"openweather": {"_healthcheck": True}},
            location="_healthcheck",
            perception=PerceptionPayload(
                data_freshness_minutes=1.0,
                snapshot_completeness=1.0,
                signal_presence={"healthcheck": True},
            ),
            reasoning=ReasoningPayload(
                probability=0.01,
                confidence_score=0.99,
                model_variant="healthcheck",
            ),
            evaluation=EvaluationPayload(
                system_status="OK",
                risk_level="SAFE",
                probability=0.01,
                confidence_score=0.99,
                requires_manual_review=False,
            ),
            decision=DecisionPayload(
                system_status="OK",
                requires_manual_review=False,
                decision_reason="RISK",
                data_validity="VALID",
                ml_execution_mode="FULL",
                risk_level="SAFE",
                probability=0.01,
                confidence_score=0.99,
                is_safe_for_automation=True,
            ),
            pipeline_run=PipelineRunConfig(
                execution_mode="healthcheck",
                api_version="healthcheck/v1",
                pipeline_version="healthcheck-1.0",
            ),
        )
        ids = result.as_dict()
        return True, f"6-stage commit OK snap={ids['snapshot_id'][:8]}.."
    except Exception as exc:
        return False, str(exc)[:120]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="PostgreSQL runtime healthcheck.")
    parser.add_argument(
        "--skip-write",
        action="store_true",
        help="Skip write validation (checks 5 and 6). Read/connectivity checks still run.",
    )
    args = parser.parse_args()

    print("=" * 64)
    print("  Flood AI -- PostgreSQL Runtime Healthcheck")
    if args.skip_write:
        print("  (read-only mode: --skip-write)")
    print("=" * 64)

    failures: list[str] = []

    # 1. Connection
    print("\n[1] Connection")
    ok, ms, detail = check_connection_probe()
    print(_fmt(ok, "connect", f"{detail}  latency={ms}ms", critical=True))
    if not ok:
        failures.append("connection")
        print("\nFAILED -- cannot connect, skipping remaining checks.")
        return 1

    conn, _, _ = _connect()
    try:
        # 2. Basic queries
        print("\n[2] Basic Queries")
        for ok, label, detail in check_basic_queries(conn):
            print(_fmt(ok, label, detail, critical=True))
            if not ok:
                failures.append(label)

        # 3. Schema
        print("\n[3] Schema Validation")
        present, missing = check_schema(conn)
        ok = len(missing) == 0
        print(_fmt(ok, "required tables",
                   f"{len(present)}/{len(_REQUIRED_TABLES)} present", critical=True))
        for t in missing:
            print(f"       MISSING: {t}")
            failures.append(f"table:{t}")

        missing_cols = check_snapshot_columns(conn)
        ok = len(missing_cols) == 0
        print(_fmt(ok, "snapshots columns",
                   f"missing={missing_cols or 'none'}", critical=True))
        if missing_cols:
            failures.append("snapshots_columns")

        # 4. Migration state
        print("\n[4] Migration State")
        applied, n_failed, failed_names = check_migrations(conn)
        ok = n_failed == 0
        print(_fmt(ok, "schema_migrations",
                   f"{applied} applied, {n_failed} failed", critical=True))
        for f in failed_names:
            print(f"       FAILED migration: {f}")
            failures.append(f"migration:{f}")

        # 5. Write round-trip (skipped with --skip-write)
        if args.skip_write:
            print("\n[5] Write Round-Trip (trend_history, rolled back)")
            print("  [SKIP]  insert+read+rollback: skipped (--skip-write)")
        else:
            print("\n[5] Write Round-Trip (trend_history, rolled back)")
            ok, detail = check_write_roundtrip(conn)
            print(_fmt(ok, "insert+read+rollback", detail, critical=True))
            if not ok:
                failures.append("write_roundtrip")

    finally:
        conn.close()

    # 6. pipeline_writer (skipped with --skip-write)
    print("\n[6] pipeline_writer 6-Stage Smoke Test")
    if args.skip_write:
        print("  [SKIP]  execute_pipeline: skipped (--skip-write)")
    else:
        ok, detail = check_pipeline_writer()
        print(_fmt(ok, "execute_pipeline", detail, critical=True))
        if not ok:
            failures.append("pipeline_writer")

    # Runtime integration summary
    print("\n" + "-" * 64)
    print(f"  {'Component':<30} {'Reads':<7} {'Writes':<7} Notes")
    print("  " + "-" * 62)
    _rows = [
        ("db.psycopg2_connection",      "YES", "NO ",  "env config; caller owns transaction"),
        ("db.migration_runner",          "YES", "YES",  "schema_migrations tracking"),
        ("db.pipeline_writer",           "YES", "YES",  "atomic 6-stage; retry on transient"),
        ("db.trend_repository",          "YES", "YES",  "ring-buffer; auto-commit per write"),
        ("db.repositories.jakarta_satu", "NO ", "YES",  "append-only; caller owns transaction"),
        ("services.trend_analysis",  "YES", "YES",  "fail-open writes; fail-closed reads"),
        ("pipeline.flood_pipeline",  "NO ", "YES",  "best-effort via pipeline_writer"),
        ("api.main (FastAPI)",        "NO ", "NO ",  "delegates entirely to services"),
    ]
    for comp, reads, writes, notes in _rows:
        print(f"  {comp:<30} {reads:<7} {writes:<7} {notes}")

    print()
    if failures:
        print(f"FAILED -- {len(failures)} critical check(s): {', '.join(failures)}")
        return 1
    print("All checks passed.")
    return 0


def check_connection_probe() -> tuple[bool, float, str]:
    try:
        conn, ms, detail = _connect()
        conn.close()
        return True, ms, detail
    except Exception as exc:
        return False, 0.0, str(exc)[:120]


if __name__ == "__main__":
    sys.exit(main())
