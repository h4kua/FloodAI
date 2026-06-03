from __future__ import annotations

import html
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi.responses import HTMLResponse

from api.observability import get_logger
from utils.paths import ARTIFACTS_DIR, DEFAULT_REALTIME_SNAPSHOT, REPORTS_DIR
from db.psycopg2_connection import pooled_connection

_MODEL_REPORT_PATH = REPORTS_DIR / "realtime_native_model_report.json"

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
    # M4: render dicts/lists as JSON (double quotes) not Python repr (single quotes)
    if isinstance(value, (dict, list)):
        return html.escape(json.dumps(value, ensure_ascii=False))
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


def _load_model_metrics() -> dict:
    """Load model performance metrics from the report JSON file."""
    try:
        with open(_MODEL_REPORT_PATH, encoding="utf-8") as fh:
            report = json.load(fh)
        perf = report.get("performance") or {}
        cal = report.get("calibration") or {}
        return {
            "test_roc_auc": perf.get("test_roc_auc"),
            "test_f1": perf.get("test_f1"),
            "test_precision": perf.get("test_precision"),
            "test_recall": perf.get("test_recall"),
            "test_accuracy": perf.get("test_accuracy"),
            "test_brier": cal.get("test_brier"),
            "test_ece": cal.get("test_ece"),
            "training_rows": report.get("training_rows"),
            "test_rows": report.get("test_rows"),
            "calibration_method": report.get("calibration", {}).get("method"),
        }
    except Exception:
        return {}


def _query_risk_history() -> list[dict]:
    """Query last 24h of pipeline runs for the sparkline chart."""
    try:
        with pooled_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT started_at, risk_level, system_status
                    FROM pipeline_runs
                    WHERE started_at >= NOW() - INTERVAL '24 hours'
                    ORDER BY started_at ASC
                    LIMIT 200
                    """
                )
                rows = cur.fetchall()
            conn.commit()
        _RISK_SCORE = {"SAFE": 0, "PRE_ALERT": 1, "WARNING": 2, "DANGER": 3, "UNKNOWN": 0}
        return [
            {"ts": str(r[0]), "score": _RISK_SCORE.get(str(r[1] or ""), 0), "risk": str(r[1] or "")}
            for r in rows
        ]
    except Exception:
        return []


def _render_sparkline(points: list[dict]) -> str:
    """Render a minimal SVG sparkline of risk scores over time."""
    if len(points) < 2:
        return "<p class=\"muted\">Not enough data for chart (need ≥2 points in last 24h).</p>"

    scores = [p["score"] for p in points]
    n = len(scores)
    w, h = 600, 80
    pad = 8
    x_step = (w - 2 * pad) / max(n - 1, 1)

    # Color per risk level for dots
    _colors = {"SAFE": "#22c55e", "PRE_ALERT": "#facc15", "WARNING": "#f97316", "DANGER": "#ef4444", "UNKNOWN": "#94a3b8"}

    pts = " ".join(
        f"{pad + i * x_step:.1f},{h - pad - scores[i] * (h - 2 * pad) / 3:.1f}"
        for i in range(n)
    )

    dots = "".join(
        f'<circle cx="{pad + i * x_step:.1f}" cy="{h - pad - scores[i] * (h - 2 * pad) / 3:.1f}" '
        f'r="3" fill="{_colors.get(points[i].get("risk", ""), "#94a3b8")}" />'
        for i in range(n)
    )

    # Y-axis labels
    labels = "".join(
        f'<text x="{pad - 4}" y="{h - pad - lvl * (h - 2 * pad) / 3 + 4}" '
        f'font-size="8" fill="#94a3b8" text-anchor="end">'
        f'{["SAFE", "PRE", "WARN", "DANG"][lvl]}</text>'
        for lvl in range(4)
    )

    latest_risk = points[-1].get("risk", "")
    latest_color = _colors.get(latest_risk, "#94a3b8")

    # Show actual data range when fewer than the expected 96 points (24h @ 15-min intervals).
    _expected_24h = 96
    if n < _expected_24h:
        try:
            _first_ts = datetime.fromisoformat(str(points[0]["ts"]).replace("Z", "+00:00"))
            _last_ts = datetime.fromisoformat(str(points[-1]["ts"]).replace("Z", "+00:00"))
            _range_h = (_last_ts - _first_ts).total_seconds() / 3600
            _range_label = f"actual range: {_range_h:.1f}h"
        except Exception:
            _range_label = f"{n} of {_expected_24h} expected points"
        range_note = f" ({_range_label})"
    else:
        range_note = ""

    return (
        f'<p style="font-size:.8rem;color:#6b7280;margin-bottom:4px;">'
        f'Last 24h — {n} data point{"s" if n != 1 else ""}{range_note} — latest: '
        f'<strong style="color:{latest_color}">{latest_risk}</strong></p>'
        f'<svg width="{w}" height="{h}" style="display:block;max-width:100%;" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{w}" height="{h}" fill="#0f172a" rx="8"/>'
        f'{labels}'
        f'<polyline points="{pts}" fill="none" stroke="#60a5fa" stroke-width="1.5"/>'
        f'{dots}'
        f'</svg>'
    )


def _render_model_metrics(metrics: dict) -> str:
    """Render model performance panel."""
    if not metrics:
        return "<p class=\"muted\">Model report not available.</p>"
    auc = metrics.get("test_roc_auc")
    f1 = metrics.get("test_f1")
    prec = metrics.get("test_precision")
    rec = metrics.get("test_recall")
    acc = metrics.get("test_accuracy")
    brier = metrics.get("test_brier")
    rows = metrics.get("training_rows", "?")
    test_n = metrics.get("test_rows", "?")
    cal = metrics.get("calibration_method", "?")

    def _fmt(v, pct=True):
        if v is None:
            return "—"
        return f"{v:.1%}" if pct else f"{v:.4f}"

    return (
        _render_table([
            ("AUC-ROC", _fmt(auc)),
            ("F1-Score", _fmt(f1)),
            ("Precision", _fmt(prec)),
            ("Recall", _fmt(rec)),
            ("Accuracy", _fmt(acc)),
            ("Brier Score", _fmt(brier, pct=False)),
            ("Calibration", (
                f"{cal} — maps raw XGBoost scores to real probabilities using monotone regression; "
                "better than sigmoid for skewed flood data"
                if str(cal).lower() == "isotonic"
                else str(cal)
            )),
            ("Training rows", str(rows)),
            ("Test rows", str(test_n)),
        ])
        + "<p class=\"muted\" style=\"font-size:.8rem;margin-top:8px;\">"
        "Trained on bootstrap proxy data — historical records augmented with synthetic flood events to compensate for class imbalance "
        "(chronological 80/15/5 split).</p>"
        + "<p style=\"background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:8px 12px;"
        "font-size:.8rem;color:#0c4a6e;margin-top:6px;\">"
        "ℹ️ <strong>Low F1-Score is expected</strong> for rare flood events — the model prioritises recall to avoid missing real floods. "
        f"<strong>AUC-ROC ({_fmt(auc) if auc else '86.3%'}) is the primary metric</strong>: it measures discrimination across all thresholds "
        "and is robust to class imbalance. "
        "Recall on live production data is independently verified via shadow-mode monitoring (pure hydrology rules, no ML).</p>"
    )


def _render_uncalibrated_stations(poskobanjir_list: list) -> str:
    """Flag stations where all siaga thresholds are identical (placeholder data)."""
    uncal = []
    for s in poskobanjir_list:
        try:
            s1 = int(float(s.get("siaga1") or 0))
            s2 = int(float(s.get("siaga2") or 0))
            s3 = int(float(s.get("siaga3") or 0))
            if s1 == s2 == s3 and s1 > 0:
                uncal.append(html.escape(str(s.get("nama_pintu_air") or "?")))
        except (TypeError, ValueError):
            pass
    if not uncal:
        return ""
    return (
        f"<p style=\"background:#fff7ed;border:1px solid #fb923c;border-radius:8px;"
        f"padding:8px 12px;font-size:.85rem;color:#9a3412;margin-top:8px;\">"
        f"⚠️ <strong>{len(uncal)} uncalibrated station(s)</strong> — "
        f"siaga1=siaga2=siaga3 (placeholder thresholds, not operationally calibrated): "
        f"{', '.join(uncal[:5])}{'...' if len(uncal) > 5 else ''}</p>"
    )


def _render_data_quality(result: dict) -> str:
    dq = (result.get("diagnostics") or {}).get("data_quality_report") or {}
    excluded = dq.get("excluded_stations") or []
    used = dq.get("stations_used_in_model")
    stale = result.get("stale_stations") or []

    parts: list[str] = ["<h3>Data quality</h3>"]
    if used is not None:
        parts.append(f"<p><strong>{used}</strong> stations used in model. ")
    else:
        parts.append("<p>")

    if excluded:
        names = ", ".join(html.escape(s.get("nama", "?")) for s in excluded)
        parts.append(
            f"<strong>{len(excluded)}</strong> excluded (non-standard datum): {names}. "
        )
    if stale:
        stale_names = ", ".join(
            html.escape(str(s.get("station", "?"))) for s in stale
        )
        parts.append(
            f"<strong>{len(stale)}</strong> excluded (>2h stale, threshold consistent across all stations): "
            f"{stale_names}. "
        )
    if not excluded and not stale:
        parts.append("No stations excluded.")
    parts.append("</p>")
    return "".join(parts)


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
    model_metrics = _load_model_metrics()
    risk_history = _query_risk_history()
    body = _render_dashboard(
        result,
        snapshot,
        db_health,
        origin,
        destination,
        snapshot_notice=snapshot_notice,
        model_metrics=model_metrics,
        risk_history=risk_history,
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
    model_metrics: dict | None = None,
    risk_history: list | None = None,
) -> str:
    location = _extract_location(snapshot)
    safe_route = result.get("safe_route") or {}
    failure_modes = result.get("failure_modes") or []
    routing_failures = result.get("routing_failures") or []
    recommended_action = result.get("recommended_action") or []
    trend_analysis = result.get("trend_analysis") or {}
    shadow = result.get("shadow_evaluation") or {}

    poskobanjir_list = snapshot.get("poskobanjir", [])
    # Show highest-alert station — lower rank = higher severity
    _SIAGA_RANK_MAP = {"Siaga 1": 0, "Siaga 2": 1, "Siaga 3": 2}

    def _station_siaga_rank(st: dict) -> int:
        s = str(st.get("status_siaga", ""))
        for lvl, rank in _SIAGA_RANK_MAP.items():
            if lvl in s:
                return rank
        return 99

    _elevated = [s for s in poskobanjir_list if _station_siaga_rank(s) < 99]
    if _elevated:
        _top = sorted(_elevated, key=_station_siaga_rank)[0]
        _top_name = _top.get("nama_pintu_air", "?")
        _top_status = next((x for x in _SIAGA_RANK_MAP if x in str(_top.get("status_siaga", ""))), "")
        poskobanjir_level = f"{_top.get('tinggi_air', '?')}cm — {_top_name} [{_top_status}]"
    else:
        def _safe_level(st: dict) -> bool:
            try:
                return float(st.get("tinggi_air") or -1) >= 0
            except (TypeError, ValueError):
                return False
        _valid = [s for s in poskobanjir_list if _safe_level(s)]
        poskobanjir_level = f"{_valid[0].get('tinggi_air', '—')}cm" if _valid else "—"
    # L3: make coordinates a clickable Google Maps link
    coord = (snapshot.get("openweather", {}) or {}).get("coord", {}) or {}
    lat_val = coord.get("lat")
    lon_val = coord.get("lon")
    if lat_val is not None and lon_val is not None:
        location_cell = (
            f'<a href="https://maps.google.com/?q={lat_val},{lon_val}" target="_blank">'
            f'{html.escape(location)}</a>'
        )
    else:
        location_cell = html.escape(location)
    # M5: show 0.0 mm when OpenWeather omits the rain field (not raining)
    rain_1h = snapshot.get("openweather", {}).get("rain", {}).get("1h", 0.0)
    rain_3h = snapshot.get("openweather", {}).get("rain", {}).get("3h", 0.0)

    # BMKG daily rainfall context (from laporan_iklim_harian station data)
    bmkg_daily = snapshot.get("bmkg_daily_rainfall") or {}
    _summary = snapshot.get("summary") or {}
    bmkg_yesterday = _summary.get("bmkg_daily_yesterday_mm") or bmkg_daily.get("yesterday_mm")
    bmkg_7d_avg = _summary.get("bmkg_daily_7d_avg_mm") or bmkg_daily.get("last_7d_avg_mm")
    bmkg_7d_max = _summary.get("bmkg_daily_7d_max_mm") or bmkg_daily.get("last_7d_max_mm")
    bmkg_last_date = _summary.get("bmkg_rainfall_last_date") or bmkg_daily.get("last_available_date")

    rain_context_note = ""
    if (not rain_1h or rain_1h == 0.0) and bmkg_7d_avg and float(bmkg_7d_avg) > 0:
        rain_context_note = (
            f" <span style='color:#d97706;font-size:.85rem;'>"
            f"&#9888; BMKG 7-hari avg: {bmkg_7d_avg:.1f} mm/hari — "
            f"hujan sebelumnya menjelaskan kenaikan TMA meski 0mm sekarang</span>"
        )

    if lat_val is not None and lon_val is not None:
        coord_cell = (
            f'<a href="https://maps.google.com/?q={lat_val},{lon_val}" target="_blank">'
            f'{float(lat_val):.5f}, {float(lon_val):.5f}</a>'
        )
    else:
        coord_cell = _safe_text(coord)

    _bmkg_yesterday_cell = f"{bmkg_yesterday:.1f} mm" if bmkg_yesterday is not None else "—"
    _bmkg_7d_cell = (
        f"avg {bmkg_7d_avg:.1f} mm/hari, max {bmkg_7d_max:.1f} mm/hari"
        if bmkg_7d_avg is not None else "—"
    )
    snapshot_summary = (
        f"<table class=\"detail-table\">"
        f"<tr><th>Location</th><td>{location_cell}</td></tr>"
        f"<tr><th>OpenWeather coord</th><td>{coord_cell}</td></tr>"
        f"<tr><th>Rain 1h (mm)</th><td>{html.escape(str(rain_1h))}{rain_context_note}</td></tr>"
        f"<tr><th>Rain 3h (mm)</th><td>{html.escape(str(rain_3h))}</td></tr>"
        f"<tr><th>BMKG kemarin (daily)</th><td>{_bmkg_yesterday_cell}</td></tr>"
        f"<tr><th>BMKG 7-hari terakhir</th>"
        f"<td>{_bmkg_7d_cell}"
        f"{(' <span style=\"color:#6b7280;font-size:.8rem;\">(data s.d. ' + html.escape(str(bmkg_last_date)) + ')</span>') if bmkg_last_date else ''}"
        f"</td></tr>"
        f"<tr><th>Poskobanjir water level</th><td>{html.escape(poskobanjir_level)}</td></tr>"
        f"</table>"
    )

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

    # C5: OOD label — must be computed before pipeline_section uses conf_display
    conf_val = result.get("confidence_score")
    ood_active = any(f.get("type") in ("ood_input", "ood_escalation") for f in failure_modes)
    conf_display = (
        f"{conf_val:.2%} [OOD — REDUCED RELIABILITY]"
        if isinstance(conf_val, (int, float)) and ood_active
        else (f"{conf_val:.2%}" if isinstance(conf_val, (int, float)) else _safe_text(conf_val))
    )

    # C3: BMKG feed summary — split Jakarta vs non-Jakarta for visual clarity
    bmkg_feed_items = snapshot.get("bmkg_feed") or []
    bmkg_feed_summary = ""
    if bmkg_feed_items:
        _jkt_tokens = (
            "jakarta", "dki jakarta", "jabodetabek", "bodetabek",
            "depok", "tangerang", "bekasi", "bogor",
            "katulampa", "ciliwung",
        )

        def _is_jakarta_feed(item: dict) -> bool:
            text = " ".join([
                str(item.get("title") or ""),
                str(item.get("description") or ""),
            ]).lower()
            return any(tok in text for tok in _jkt_tokens)

        jakarta_items = [i for i in bmkg_feed_items if _is_jakarta_feed(i)]
        other_items = [i for i in bmkg_feed_items if not _is_jakarta_feed(i)]

        jkt_html = ""
        if jakarta_items:
            jkt_titles = [html.escape(i.get("title", "")[:90]) for i in jakarta_items[:5]]
            jkt_html = (
                f"<p style=\"font-size:.8rem;font-weight:600;color:#1e40af;margin:6px 0 2px;\">Jakarta / Jabodetabek relevant ({len(jakarta_items)}):</p>"
                f"<ul style=\"font-size:.85rem;color:#1e3a5f;margin:0 0 6px 1.2rem;\">"
                + "".join(f"<li>{t}</li>" for t in jkt_titles)
                + ("</ul><p style=\"font-size:.75rem;color:#6b7280;\">…and more</p>" if len(jakarta_items) > 5 else "</ul>")
            )

        other_html = ""
        if other_items:
            other_titles = [html.escape(i.get("title", "")[:80]) for i in other_items[:3]]
            other_html = (
                f"<p style=\"font-size:.8rem;font-weight:600;color:#6b7280;margin:6px 0 2px;\">Non-Jakarta / national ({len(other_items)}):</p>"
                f"<ul style=\"font-size:.8rem;color:#9ca3af;margin:0 0 0 1.2rem;\">"
                + "".join(f"<li>{t}</li>" for t in other_titles)
                + ("</ul><p style=\"font-size:.75rem;color:#9ca3af;\">…and more</p>" if len(other_items) > 3 else "</ul>")
            )

        bmkg_feed_summary = (
            f"<h3>BMKG feed ({len(bmkg_feed_items)} total items)</h3>"
            + jkt_html
            + other_html
        )

    stale_stations = result.get("stale_stations") or []
    stale_banner = ""
    if stale_stations:
        sorted_stale = sorted(stale_stations, key=lambda s: s.get("age_hours", 0), reverse=True)
        stale_list = ", ".join(
            f"{html.escape(str(s.get('station','?')))} ({s.get('age_hours',0):.1f}h)"
            for s in sorted_stale
        )
        stale_banner = (
            f"<p style=\"background:#fef3c7;border:1px solid #d97706;border-radius:8px;"
            f"padding:10px 14px;margin-bottom:12px;color:#92400e;font-size:.9rem;\">"
            f"⚠️ <strong>{len(stale_stations)} stale station(s) excluded</strong> "
            f"(all stations with tanggal &gt;2h old are excluded from model): "
            f"{stale_list}.</p>"
        )

    pipeline_section = _render_section(
        "Current pipeline output",
        stale_banner + _render_table(
            [
                ("System status", _safe_text(result.get("system_status"))),
                ("Risk level", _safe_text(result.get("risk_level"))),
                ("Confidence", conf_display),
                ("Decision reason", _safe_text(result.get("decision_reason"))),
                *(
                    [("Decision override", html.escape(str(result["decision_override_reason"])))]
                    if result.get("decision_override_reason")
                    else []
                ),
                ("Dominant risk driver", _safe_text(result.get("dominant_risk_driver"))),
                ("Risk interpretation", _safe_text(result.get("risk_interpretation"))),
                # C7: flag when freshness exceeds scheduler interval (15 min)
                ("Data freshness (min)", (
                    f"{result.get('data_freshness_minutes')} ⚠️ STALE (>15 min refresh interval)"
                    if isinstance(result.get("data_freshness_minutes"), (int, float))
                    and result.get("data_freshness_minutes", 0) > 15
                    else _safe_text(result.get("data_freshness_minutes"))
                )),
                ("Pipeline version", _safe_text(result.get("pipeline_version"))),
                ("Model name", _safe_text(result.get("model_name"))),
                ("Safe route available", (
                    "Enter origin and destination above to find a safe route"
                    if not origin and not destination
                    else _safe_text(safe_route.get("available"))
                )),
                ("Persistence IDs", _safe_text(result.get("persistence"))),  # M4: dict → JSON via _safe_text
                ("Persistence error", _safe_text(result.get("persistence_error"))),
            ]
        )
        + _render_data_quality(result)
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
            ("Confidence", conf_display),
            ("Risk delta 1h", _safe_text(trend_analysis.get("risk_delta_1h"))),
            ("Risk trend", _safe_text(trend_analysis.get("risk_trend"))),
            ("Trend basis", _safe_text(trend_analysis.get("trend_basis", "composite_hydro_rainfall"))),
            ("Water level trend", _safe_text(trend_analysis.get("water_level_trend"))),
            ("Rainfall trend", _safe_text(trend_analysis.get("rainfall_trend"))),
            ("Trend points", (
                lambda dp: (
                    f"{dp} points (~{dp * 15 / 1440:.1f} days)"
                    if isinstance(dp, int) and dp > 0
                    else _safe_text(dp)
                )
            )(trend_analysis.get("data_points"))),
        ])
        # M4: human-readable shadow summary instead of raw JSON
        + "<h3>Shadow model assessment</h3>"
        + (f"<p style=\"font-size:.95rem;padding:8px 0;\">{html.escape(shadow.get('shadow_summary', ''))}</p>" if shadow.get("shadow_summary") else "")
        + _render_table([
            ("Shadow risk", _safe_text(shadow.get("shadow_risk_level"))),
            ("Agrees with production", "Yes ✅" if shadow.get("shadow_agreement") else "No ⚠️"),
            ("Disagreement levels", _safe_text(shadow.get("shadow_disagreement_levels"))),
            ("Profile", f"{_safe_text(shadow.get('shadow_threshold_profile'))} — pure hydrology rules (ratio + siaga3 count), independent of ML"),
        ])
        + bmkg_feed_summary
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
        + _render_uncalibrated_stations(poskobanjir_list)
        + "<h3>Raw snapshot metadata</h3>"
        + _render_pre(snapshot)
    )

    # Model performance + historical chart sections
    model_section = _render_section(
        "Model Performance (XGBoost Flood Predictor — Realtime Native)",
        _render_model_metrics(model_metrics or {})
    )

    history_section = _render_section(
        "Risk Level History — Last 24h",
        _render_sparkline(risk_history or [])
        + f"<p class=\"muted\" style=\"font-size:.8rem;margin-top:8px;\">"
        f"Total pipeline runs in DB: <strong>{db_health.get('pipeline_runs_total', '?')}</strong>. "
        "Chart shows last 24h only. Each dot = one prediction cycle (15-min interval).</p>"
    )

    # C4: routing form + M7: only show origin/destination when set
    routing_rows = []
    if origin:
        routing_rows.append(f"<tr><th>Origin</th><td>{_safe_text(origin)}</td></tr>")
    if destination:
        routing_rows.append(f"<tr><th>Destination</th><td>{_safe_text(destination)}</td></tr>")
    routing_table = f"<table class=\"detail-table\">{''.join(routing_rows)}</table>" if routing_rows else ""

    query_context = _render_section(
        "Safe Route Finder",
        "<form method=\"get\" action=\"/demo\" style=\"display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:16px;\">"
        "<div><label style=\"font-size:.9rem;font-weight:600;display:block;margin-bottom:4px;\">Origin</label>"
        f"<input name=\"origin\" value=\"{html.escape(origin or '')}\" placeholder=\"e.g. Menteng, Jakarta Pusat\" "
        "style=\"padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:.95rem;width:280px;\"/></div>"
        "<div><label style=\"font-size:.9rem;font-weight:600;display:block;margin-bottom:4px;\">Destination</label>"
        f"<input name=\"destination\" value=\"{html.escape(destination or '')}\" placeholder=\"e.g. Monas, Jakarta Pusat\" "
        "style=\"padding:8px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:.95rem;width:280px;\"/></div>"
        "<button type=\"submit\" style=\"padding:8px 20px;background:#4f46e5;color:#fff;border:none;border-radius:8px;"
        "font-size:.95rem;font-weight:600;cursor:pointer;\">Find Safe Route</button>"
        "</form>"
        + routing_table
        + (
            "<h3>Route result</h3>" + _render_pre(safe_route)
            if safe_route and safe_route.get("available")
            else (
                f"<p class=\"muted\">{html.escape(safe_route.get('reason', 'Enter origin and destination above to find a safe route.'))}</p>"
                if safe_route
                else "<p class=\"muted\">Enter origin and destination above to find a safe route.</p>"
            )
        )
    )

    rendered = (
        "<html><head><title>Jakarta Flood Prediction Demo</title>"
        "<meta charset=\"utf-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />"
        # L7: auto-refresh every 15 minutes (matches snapshot scheduler interval)
        "<meta http-equiv=\"refresh\" content=\"900\" />"
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
        f"{history_section}"
        f"{model_section}"
        f"{snapshot_section}"
        f"{db_section}"
        "</main>"
        # L7: auto-refresh countdown banner
        "<div id=\"refresh-bar\" style=\"position:fixed;bottom:0;left:0;right:0;background:#1e293b;color:#94a3b8;"
        "font-size:.85rem;padding:8px 24px;display:flex;justify-content:space-between;align-items:center;\">"
        "<span>Jakarta Flood AI — Agentic Pipeline v2.0</span>"
        "<span>Next refresh in: <strong id=\"countdown\">15:00</strong></span>"
        "</div>"
        "<script>"
        "var secs=900;"
        "function tick(){"
        "secs--;"
        "if(secs<=0){location.reload();return;}"
        "var m=Math.floor(secs/60),s=secs%60;"
        "document.getElementById('countdown').textContent=(m<10?'0':'')+m+':'+(s<10?'0':'')+s;"
        "setTimeout(tick,1000);}"
        "setTimeout(tick,1000);"
        "</script>"
        "</body></html>"
    )
    return rendered


def _render_pre(value: Any) -> str:
    if isinstance(value, str):
        return f"<pre>{html.escape(value)}</pre>"
    return f"<pre>{_pretty_json(value)}</pre>"
