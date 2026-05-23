from __future__ import annotations

import html
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.responses import HTMLResponse
from imblearn import pipeline

from api.observability import get_logger
from utils.paths import DEFAULT_REALTIME_SNAPSHOT
from db.psycopg2_connection import pooled_connection

_REQUIRED_DB_TABLES = [
    "schema_migrations",
    "pipeline_runs",
    "trend_history",
]
_log = get_logger("flood.api.dashboard")


def _safe_text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return html.escape(str(value))


def _pretty_json(value: Any) -> str:
    return html.escape(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _safe_text(value)


def _load_snapshot(path: Path | str) -> dict:
    """
    Load the realtime snapshot, Supabase-first.

    Order: (1) latest snapshot from Supabase (survives Railway's ephemeral
    filesystem), (2) the bundled JSON file at ``path``, (3) empty dict. Signature
    and return type are unchanged. Runs in the dashboard's worker thread, so the
    synchronous repository core is used directly (no event loop involved).
    """
    try:
        from db.snapshot_repository import _load_latest_snapshot_sync

        remote = _load_latest_snapshot_sync()
    except Exception as exc:  # noqa: BLE001 — never break the dashboard on load.
        remote = None
        _log.warning("dashboard_snapshot_supabase_error", error=str(exc))
    if remote:
        _log.info("snapshot loaded from supabase")
        return remote

    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        _log.info("snapshot loaded from file")
        return data
    except Exception as exc:  # noqa: BLE001 — fall back to empty dict.
        _log.warning("dashboard_snapshot_file_error", error=str(exc))
        return {}


def _extract_location(snapshot: dict) -> str:
    openweather = snapshot.get("openweather", {}) or {}
    coord = openweather.get("coord", {}) or {}
    lat = coord.get("lat")
    lon = coord.get("lon")
    if lat is not None and lon is not None:
        return f"{float(lat):.5f}, {float(lon):.5f}"
    location = snapshot.get("location")
    if isinstance(location, dict):
        lat = location.get("lat") or location.get("latitude")
        lon = location.get("lon") or location.get("longitude")
        if lat is not None and lon is not None:
            return f"{float(lat):.5f}, {float(lon):.5f}"
    return str(location or "Jakarta, Indonesia")


def _query_db_health() -> dict:
    health: dict = {
        "connected": False,
        "error": None,
        "database": None,
        "user": None,
        "tables_present": [],
        "tables_missing": [],
        "schema_migrations_applied": 0,
        "pipeline_runs_total": 0,
        "latest_pipeline_run": None,
    }

    try:
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                database, user = cur.fetchone()
                health["connected"] = True
                health["database"] = database
                health["user"] = user

                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
                tables = {row[0] for row in cur.fetchall()}
                health["tables_present"] = sorted(tables)
                health["tables_missing"] = [
                    table for table in _REQUIRED_DB_TABLES if table not in tables
                ]

                if "schema_migrations" in tables:
                    cur.execute(
                        "SELECT COUNT(*) FROM schema_migrations WHERE success = TRUE"
                    )
                    health["schema_migrations_applied"] = cur.fetchone()[0] or 0

                if "pipeline_runs" in tables:
                    cur.execute("SELECT COUNT(*) FROM pipeline_runs")
                    health["pipeline_runs_total"] = cur.fetchone()[0] or 0
                    cur.execute(
                        "SELECT started_at, system_status, risk_level, origin, destination "
                        "FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
                    )
                    latest = cur.fetchone()
                    if latest is not None:
                        health["latest_pipeline_run"] = {
                            "started_at": latest[0],
                            "system_status": latest[1],
                            "risk_level": latest[2],
                            "origin": latest[3],
                            "destination": latest[4],
                        }
            conn.commit()
    except Exception as exc:
        health["error"] = type(exc).__name__
    return health


def _render_badge(text: str, level: str) -> str:
    css_class = {
        "OK": "badge--ok",
        "SAFE": "badge--ok",
        "PRE_ALERT": "badge--warn",
        "WARNING": "badge--warn",
        "DANGER": "badge--danger",
        "DEGRADED": "badge--warn",
        "FAIL": "badge--danger",
        "PIPELINE_FAILURE": "badge--danger",
    }.get(level, "badge--ok")
    return f"<span class=\"badge {css_class}\">{html.escape(text)}</span>"


def _render_kpi(title: str, value: Any, subtitle: str = "") -> str:
    return (
        f"<div class=\"kpi\">"
        f"<h3>{html.escape(title)}</h3>"
        f"<p class=\"kpi-value\">{_safe_text(value)}</p>"
        f"<p class=\"muted\">{html.escape(subtitle)}</p>"
        f"</div>"
    )


def _render_section(title: str, body: str) -> str:
    return (
        f"<section>"
        f"<h2>{html.escape(title)}</h2>"
        f"{body}"
        f"</section>"
    )


def _render_table(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in rows
    )
    return f"<table class=\"detail-table\">{cells}</table>"


def _render_list(items: list[Any]) -> str:
    if not items:
        return "<p>None</p>"
    rendered = "".join(
        f"<li>{html.escape(str(item))}</li>" for item in items
    )
    return f"<ul>{rendered}</ul>"


def build_demo_page(
    *,
    pipeline,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
) -> HTMLResponse:
    try:
        snapshot_for_pipeline = _load_snapshot(DEFAULT_REALTIME_SNAPSHOT)
        result = pipeline.run(snapshot_for_pipeline, origin=origin, destination=destination)
    except FileNotFoundError as exc:
        return HTMLResponse(
            _render_error_html("Snapshot file not found", "snapshot_unavailable"),
            status_code=404,
        )
    except Exception as exc:
        correlation_id = uuid.uuid4().hex
        _log.error(
            "dashboard_failure",
            correlation_id=correlation_id,
            error=str(exc),
            exc_info=True,
        )
        return HTMLResponse(
            _render_error_html(
                "Pipeline execution failed",
                f"internal_error correlation_id={correlation_id}",
            ),
            status_code=500,
        )

    snapshot_notice: str | None = None
    try:
        snapshot = _load_snapshot(DEFAULT_REALTIME_SNAPSHOT)
    except Exception as exc:
        _log.warning(
            "dashboard_snapshot_unavailable",
            error=str(exc),
            snapshot_path=str(DEFAULT_REALTIME_SNAPSHOT),
        )
        snapshot = {}
        snapshot_notice = (
            "Snapshot metadata unavailable. The dashboard is showing pipeline output "
            "without the latest raw snapshot details."
        )

    db_health = _query_db_health()
    body = _render_dashboard(
        result,
        snapshot,
        db_health,
        origin,
        destination,
        snapshot_notice=snapshot_notice,
    )
    return HTMLResponse(body)


def _render_error_html(title: str, detail: str) -> str:
    return (
        "<html><head><title>Flood AI Demo - Error</title></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(detail)}</p>"
        "</body></html>"
    )


def _render_dashboard(
    result: dict,
    snapshot: dict,
    db_health: dict,
    origin: Optional[str],
    destination: Optional[str],
    snapshot_notice: str | None = None,
) -> str:
    location = _extract_location(snapshot)
    safe_route = result.get("safe_route") or {}
    failure_modes = result.get("failure_modes") or []
    routing_failures = result.get("routing_failures") or []
    recommended_action = result.get("recommended_action") or []
    trend_analysis = result.get("trend_analysis") or {}
    shadow = result.get("shadow_evaluation") or {}

    snapshot_summary = _render_table([
        ("Location", location),
        ("OpenWeather coord", _safe_text(snapshot.get("openweather", {}).get("coord", {}))),
        ("Rain 1h (mm)", str(snapshot.get("openweather", {}).get("rain", {}).get("1h", "—"))),
        ("Rain 3h (mm)", str(snapshot.get("openweather", {}).get("rain", {}).get("3h", "—"))),
        ("Poskobanjir water level", str(snapshot.get("poskobanjir", [{}])[0].get("tinggi_air", "—"))),
        ("Snapshot source", _safe_text(DEFAULT_REALTIME_SNAPSHOT)),
    ])

    db_section = _render_section(
        "PostgreSQL status",
        _render_table([
            ("Connected", "Yes" if db_health.get("connected") else "No"),
            ("Database", _safe_text(db_health.get("database"))),
            ("User", _safe_text(db_health.get("user"))),
            ("Migrations applied", str(db_health.get("schema_migrations_applied", 0))),
            ("Pipeline rows", str(db_health.get("pipeline_runs_total", 0))),
            (
                "Last pipeline run",
                _safe_text(db_health.get("latest_pipeline_run", {}).get("started_at"))
                if db_health.get("latest_pipeline_run")
                else "None",
            ),
        ])
        + (
            f"<p class=\"muted\">Error: {html.escape(db_health['error'])}</p>"
            if db_health.get("error")
            else ""
        )
    )

    pipeline_section = _render_section(
        "Current pipeline output",
        _render_table(
            [
                ("System status", _safe_text(result.get("system_status"))),
                ("Risk level", _safe_text(result.get("risk_level"))),
                ("Confidence", f"{result.get('confidence_score', '—'):.2%}" if isinstance(result.get("confidence_score"), (int, float)) else _safe_text(result.get("confidence_score"))),
                ("Decision reason", _safe_text(result.get("decision_reason"))),
                ("Dominant risk driver", _safe_text(result.get("dominant_risk_driver"))),
                ("Risk interpretation", _safe_text(result.get("risk_interpretation"))),
                ("Data freshness (min)", _safe_text(result.get("data_freshness_minutes"))),
                ("Pipeline version", _safe_text(result.get("pipeline_version"))),
                ("Model name", _safe_text(result.get("model_name"))),
                ("Safe route available", _safe_text(safe_route.get("available"))),
                ("Persistence IDs", _safe_text(result.get("persistence"))),
                ("Persistence error", _safe_text(result.get("persistence_error"))),
            ]
        )
        + "<h3>Safe route</h3>"
        + _render_pre(safe_route)
        + "<h3>Failure modes</h3>"
        + _render_list([f"{fm.get('severity', 'unknown').upper()}: {fm.get('type')} — {fm.get('message')}" for fm in failure_modes])
        + "<h3>Routing failures</h3>"
        + _render_list([f"{fm.get('severity', 'unknown').upper()}: {fm.get('type')} — {fm.get('message')}" for fm in routing_failures])
        + "<h3>Recommended actions</h3>"
        + _render_list(recommended_action)
    )

    metrics_section = _render_section(
        "Trend + shadow analysis",
        _render_table([
            ("Risk delta 1h", _safe_text(trend_analysis.get("risk_delta_1h"))),
            ("Risk trend", _safe_text(trend_analysis.get("risk_trend"))),
            ("Water level trend", _safe_text(trend_analysis.get("water_level_trend"))),
            ("Rainfall trend", _safe_text(trend_analysis.get("rainfall_trend"))),
            ("Trend points", _safe_text(trend_analysis.get("data_points"))),
            ("Shadow profile", _safe_text(shadow.get("shadow_threshold_profile"))),
            ("Shadow error", _safe_text(shadow.get("error"))),
        ])
        + "<h3>Shadow evaluation payload</h3>"
        + _render_pre(shadow)
    )

    snapshot_section = _render_section(
        "Realtime snapshot",
        (
            f"<p>{_render_badge('DEGRADED', 'DEGRADED')} "
            f"{html.escape(snapshot_notice)}</p>"
            if snapshot_notice
            else ""
        )
        + snapshot_summary
        + "<h3>Raw snapshot metadata</h3>"
        + _render_pre(snapshot)
    )

    query_context = _render_section(
        "Dashboard query",
        _render_table(
            [
                ("Origin", _safe_text(origin)),
                ("Destination", _safe_text(destination)),
                ("Snapshot path", _safe_text(DEFAULT_REALTIME_SNAPSHOT)),
            ]
        )
    )

    rendered = (
        "<html><head><title>Jakarta Flood Prediction Demo</title>"
        "<meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />"
        "<style>"
        "body{margin:0;font-family:Segoe UI,Arial,Helvetica,sans-serif;background:#f3f5f7;color:#111;}"
        "main{max-width:1200px;margin:0 auto;padding:24px;}"
        "header{padding:24px 0;}"
        "h1{margin:0;font-size:2.25rem;}"
        "p.lead{margin:.8rem 0 0;font-size:1rem;color:#444;}"
        "section{background:#fff;border-radius:20px;box-shadow:0 18px 50px rgba(12,20,35,.08);padding:24px;margin-bottom:20px;}"
        "h2{margin-top:0;font-size:1.35rem;border-bottom:1px solid #ebeff3;padding-bottom:12px;color:#111;}"
        "h3{margin:20px 0 10px;font-size:1.05rem;color:#1f2937;}"
        ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-top:16px;}"
        ".kpi{background:#f7fafc;border:1px solid #e7edf3;border-radius:16px;padding:18px;}"
        ".kpi h3{margin:0 0 12px;font-size:1rem;color:#0f172a;}"
        ".kpi-value{font-size:1.5rem;font-weight:700;margin:0;color:#111;}"
        ".muted{color:#6b7280;font-size:.95rem;margin:0;}"
        "table.detail-table{width:100%;border-collapse:collapse;margin-top:12px;}"
        "table.detail-table th,table.detail-table td{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid #e5e7eb;}"
        "table.detail-table th{width:220px;color:#334155;font-weight:600;}"
        "pre{background:#0f172a;color:#f8fafc;padding:18px;border-radius:16px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;}"
        "ul{margin:0 0 0 1.2rem;padding:0;}"
        "li{margin-bottom:.55rem;color:#111;}"
        ".badge{display:inline-flex;align-items:center;gap:.35rem;padding:.35rem .8rem;border-radius:999px;font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.02em;}"
        ".badge--ok{background:#ecfdf5;color:#166534;}"
        ".badge--warn{background:#fffbeb;color:#92400e;}"
        ".badge--danger{background:#fef2f2;color:#991b1b;}"
        "</style></head><body><main>"
        "<header>"
        "<h1>Jakarta Flood Prediction Demo</h1>"
        "<p class=\"lead\">Live dashboard for the agentic flood prediction pipeline and PostgreSQL persistence state.</p>"
        "</header>"
        f"{query_context}"
        f"{pipeline_section}"
        f"{metrics_section}"
        f"{snapshot_section}"
        f"{db_section}"
        "</main></body></html>"
    )
    return rendered


def _render_pre(value: Any) -> str:
    if isinstance(value, str):
        return f"<pre>{html.escape(value)}</pre>"
    return f"<pre>{_pretty_json(value)}</pre>"
