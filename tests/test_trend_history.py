"""
Deterministic replay tests for DB-backed trend history (H2A).

Pure-function tests (no DB required):
  test_compute_from_records_*  — verify _compute_from_records is a pure,
                                  deterministic function given fixed input.

Mocked-DB tests (no live DB required):
  test_compute_trend_reads_from_db  — compute_trend() delegates to DB, not
                                       process-local state.
  test_compute_trend_fail_closed    — DB error → insufficient_data, never
                                       invented trend state.
  test_restart_simulation           — delete + re-read same records →
                                       identical output (restart safety).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from services.trend_analysis import (
    _compute_from_records,
    _insufficient,
    compute_trend,
    record_prediction,
    reset_history,
)

# ---------------------------------------------------------------------------
# Fixture history sets
# ---------------------------------------------------------------------------

_RISING_3 = [
    {
        "timestamp_utc": "2026-01-01T00:00:00+00:00",
        "probability": 0.35,
        "risk_level": "SAFE",
        "water_level_ratio": 0.60,
        "rainfall_mm": 5.0,
    },
    {
        "timestamp_utc": "2026-01-01T00:10:00+00:00",
        "probability": 0.50,
        "risk_level": "WARNING",
        "water_level_ratio": 0.65,
        "rainfall_mm": 8.0,
    },
    {
        "timestamp_utc": "2026-01-01T00:20:00+00:00",
        "probability": 0.65,
        "risk_level": "WARNING",
        "water_level_ratio": 0.70,
        "rainfall_mm": 12.0,
    },
]

_STABLE_4 = [
    {
        "timestamp_utc": f"2026-01-01T00:0{i}:00+00:00",
        "probability": 0.30 + i * 0.005,   # tiny drift — below threshold
        "risk_level": "SAFE",
        "water_level_ratio": 0.50,
        "rainfall_mm": 3.0,
    }
    for i in range(4)
]


# ---------------------------------------------------------------------------
# Pure-function tests — no DB, no mocks
# ---------------------------------------------------------------------------


def test_compute_from_records_deterministic():
    """Same input list → identical output, regardless of call order."""
    r1 = _compute_from_records(_RISING_3)
    r2 = _compute_from_records(_RISING_3)
    assert r1 == r2


def test_compute_from_records_numeric_stability():
    """Key numeric fields round-trip identically across calls."""
    r1 = _compute_from_records(_RISING_3)
    r2 = _compute_from_records(_RISING_3)
    assert r1["risk_delta_1h"] == r2["risk_delta_1h"]
    assert r1["trend_strength"] == r2["trend_strength"]
    assert r1["trend_confidence"] == r2["trend_confidence"]
    assert r1["risk_rate_per_hour"] == r2["risk_rate_per_hour"]


def test_compute_from_records_insufficient_empty():
    r = _compute_from_records([])
    assert r["risk_trend"] == "insufficient_data"
    assert r["data_points"] == 0
    assert r["anomaly_detected"] is False


def test_compute_from_records_insufficient_one_point():
    r = _compute_from_records(_RISING_3[:1])
    assert r["risk_trend"] == "insufficient_data"
    assert r["data_points"] == 1


def test_compute_from_records_rising_trend():
    r = _compute_from_records(_RISING_3)
    assert r["risk_trend"] == "increasing"
    assert r["trend_strength"] > 0.0
    assert r["data_points"] == 3


def test_compute_from_records_stable_trend():
    r = _compute_from_records(_STABLE_4)
    assert r["risk_trend"] == "stable"
    assert r["data_points"] == 4


def test_compute_from_records_all_keys_present():
    """Output contract: all expected keys must be present."""
    r = _compute_from_records(_RISING_3)
    required = {
        "risk_delta_1h",
        "risk_trend",
        "water_level_trend",
        "rainfall_trend",
        "data_points",
        "risk_rate_per_hour",
        "trend_strength",
        "trend_confidence",
        "anomaly_detected",
        "anomaly_type",
    }
    assert required <= r.keys()


def test_insufficient_keys_match_compute_keys():
    """_insufficient() must return the same key set as a full computation."""
    ins = _insufficient(0)
    full = _compute_from_records(_RISING_3)
    assert ins.keys() == full.keys()


# ---------------------------------------------------------------------------
# Mocked-DB tests — verify DB delegation, not just pure computation
# ---------------------------------------------------------------------------


def _mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.close = MagicMock()
    return conn


@contextmanager
def _pooled(conn):
    yield conn


def test_compute_trend_reads_from_db_not_process_state():
    """
    compute_trend() must delegate to get_recent_trend_records, not to any
    process-local deque. Patching the DB read to return _RISING_3 must
    produce exactly _compute_from_records(_RISING_3).
    """
    conn = _mock_conn()
    with patch("services.trend_analysis.pooled_connection", return_value=_pooled(conn)):
        with patch(
            "services.trend_analysis.get_recent_trend_records",
            return_value=_RISING_3,
        ):
            result = compute_trend()

    assert result == _compute_from_records(_RISING_3)


def test_compute_trend_fail_closed_on_connection_error():
    """DB connection failure → insufficient_data, not stale invented state."""
    with patch("services.trend_analysis.pooled_connection", side_effect=Exception("connection refused")):
        result = compute_trend()

    assert result["risk_trend"] == "insufficient_data"
    assert result["data_points"] == 0


def test_compute_trend_fail_closed_on_read_error():
    """DB read failure mid-connection → insufficient_data."""
    conn = _mock_conn()
    with patch("services.trend_analysis.pooled_connection", return_value=_pooled(conn)):
        with patch(
            "services.trend_analysis.get_recent_trend_records",
            side_effect=Exception("timeout"),
        ):
            result = compute_trend()

    assert result["risk_trend"] == "insufficient_data"


def test_restart_simulation():
    """
    Restart simulation: after reset_history (simulating process restart),
    re-reading the same records from DB produces the identical result.

    Core H2A guarantee: trend state lives in the DB, not in the process.
    """
    conn = _mock_conn()

    # Run 1 — before simulated restart
    with patch("services.trend_analysis.pooled_connection", return_value=_pooled(conn)):
        with patch(
            "services.trend_analysis.get_recent_trend_records",
            return_value=_RISING_3,
        ):
            result_before = compute_trend()

    # Simulate restart: reset_history clears DB state; process memory is gone
    with patch("services.trend_analysis.pooled_connection", return_value=_pooled(conn)):
        with patch("services.trend_analysis.delete_trend_records") as mock_delete:
            reset_history()
    assert mock_delete.call_count == 1

    # Run 2 — after restart, same DB records are available again
    with patch("services.trend_analysis.pooled_connection", return_value=_pooled(conn)):
        with patch(
            "services.trend_analysis.get_recent_trend_records",
            return_value=_RISING_3,
        ):
            result_after = compute_trend()

    assert result_before == result_after


def test_record_prediction_logs_warning_on_db_failure(caplog):
    """record_prediction DB failure is logged as WARNING, not raised."""
    with patch("services.trend_analysis.pooled_connection", side_effect=OSError("no route to host")):
        with caplog.at_level(logging.WARNING, logger="services.trend_analysis"):
            record_prediction(0.5, "WARNING", 0.7, 10.0)  # must not raise

    assert any("DB write failed" in m for m in caplog.messages)


def test_reset_history_logs_warning_on_db_failure(caplog):
    """reset_history DB failure is logged as WARNING, not raised."""
    with patch("services.trend_analysis.pooled_connection", side_effect=OSError("no route to host")):
        with caplog.at_level(logging.WARNING, logger="services.trend_analysis"):
            reset_history()  # must not raise

    assert any("DB delete failed" in m for m in caplog.messages)
