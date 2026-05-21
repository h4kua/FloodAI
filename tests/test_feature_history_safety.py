"""
Concurrency and write-safety tests for realtime_feature_history.csv (H2B).

All tests use a temporary directory so the production CSV is never touched.

test_serial_append_*    — baseline correctness (no concurrency)
test_concurrent_appends — 10 threads × 5 rows, assert all 50 rows present
test_lock_file_created  — FileLock creates a .lock sentinel beside the CSV
test_atomic_write_*     — tmp file is cleaned up; original survives a simulated
                          crash (tmp left behind is harmless on next run)
test_lock_timeout_*     — timeout logs a warning and does not raise
"""

from __future__ import annotations

import logging
import threading
import unittest.mock as mock
from pathlib import Path

import pandas as pd
import pytest
from filelock import FileLock
from filelock import Timeout as FileLockTimeout

from realtime_native.feature_builder import _append_history, _load_history


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(ts: str, mm: float = 5.0, wl: float = 0.5) -> dict:
    return {"timestamp": ts, "rainfall_mm": mm, "water_level_ratio": wl}


def _ts(i: int) -> str:
    """Unique ISO-8601 timestamp per index."""
    h, m = divmod(i, 60)
    return f"2026-01-01T{h:02d}:{m:02d}:00+00:00"


# ---------------------------------------------------------------------------
# Serial correctness
# ---------------------------------------------------------------------------


def test_serial_append_creates_file(tmp_path):
    csv = tmp_path / "hist.csv"
    _append_history(_row(_ts(0)), path=csv)
    assert csv.exists()


def test_serial_append_row_count(tmp_path):
    csv = tmp_path / "hist.csv"
    for i in range(5):
        _append_history(_row(_ts(i), mm=float(i)), path=csv)
    df = _load_history(csv)
    assert len(df) == 5


def test_serial_append_values_preserved(tmp_path):
    csv = tmp_path / "hist.csv"
    _append_history(_row(_ts(0), mm=42.0, wl=0.75), path=csv)
    df = _load_history(csv)
    assert df.iloc[0]["rainfall_mm"] == pytest.approx(42.0)
    assert df.iloc[0]["water_level_ratio"] == pytest.approx(0.75)


def test_serial_tail_cap_at_2000(tmp_path):
    csv = tmp_path / "hist.csv"
    for i in range(2005):
        _append_history(_row(_ts(i)), path=csv)
    df = _load_history(csv)
    assert len(df) == 2000


# ---------------------------------------------------------------------------
# Concurrency: 10 threads × 5 rows = 50 total
# ---------------------------------------------------------------------------


def test_concurrent_appends_no_lost_writes(tmp_path):
    """
    Serialized writes must produce exactly n_threads * rows_per_thread rows.
    Without FileLock, concurrent read-modify-write loses writes (last writer wins).
    """
    csv = tmp_path / "hist.csv"
    n_threads = 10
    rows_per_thread = 5
    errors: list[Exception] = []

    def worker(tid: int) -> None:
        for i in range(rows_per_thread):
            ts = f"2026-01-01T{tid:02d}:{i:02d}:00+00:00"
            try:
                _append_history(_row(ts, mm=float(tid * 10 + i)), path=csv)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    df = _load_history(csv)
    assert len(df) == n_threads * rows_per_thread, (
        f"Expected {n_threads * rows_per_thread} rows, got {len(df)}. "
        "Likely a lost write from concurrent append without serialization."
    )


def test_concurrent_appends_valid_csv_schema(tmp_path):
    """All rows written concurrently must have the expected columns."""
    csv = tmp_path / "hist.csv"
    errors: list[Exception] = []

    def worker(tid: int) -> None:
        for i in range(3):
            ts = f"2026-01-01T{tid:02d}:{i:02d}:00+00:00"
            try:
                _append_history(_row(ts), path=csv)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    df = _load_history(csv)
    assert {"timestamp", "rainfall_mm", "water_level_ratio"} <= set(df.columns)
    assert df["rainfall_mm"].notna().all()
    assert df["water_level_ratio"].notna().all()


# ---------------------------------------------------------------------------
# Lock released after write
# ---------------------------------------------------------------------------


def test_lock_released_after_successful_write(tmp_path):
    """
    After _append_history returns, the OS-level lock must be released so the
    next writer can acquire it immediately (no deadlock).
    """
    csv = tmp_path / "hist.csv"
    _append_history(_row(_ts(0)), path=csv)
    # If the lock were still held, FileLock(timeout=0) would raise Timeout.
    lock_path = csv.with_suffix(".lock")
    with FileLock(lock_path, timeout=0):
        pass  # acquired immediately — lock was released


# ---------------------------------------------------------------------------
# Atomic write: .tmp is cleaned up on success
# ---------------------------------------------------------------------------


def test_tmp_file_absent_after_successful_write(tmp_path):
    """os.replace moves .tmp → .csv; no .tmp file should linger after success."""
    csv = tmp_path / "hist.csv"
    _append_history(_row(_ts(0)), path=csv)
    assert not (tmp_path / "hist.tmp").exists()


# ---------------------------------------------------------------------------
# Lock timeout: warning logged, no exception raised
# ---------------------------------------------------------------------------


def test_lock_timeout_logs_warning_and_does_not_raise(tmp_path, caplog):
    """
    When FileLock raises Timeout (lock held by another process),
    _append_history must log a WARNING and return without raising.
    """
    csv = tmp_path / "hist.csv"

    with mock.patch(
        "realtime_native.feature_builder.FileLock",
        side_effect=FileLockTimeout(str(csv.with_suffix(".lock"))),
    ):
        with caplog.at_level(logging.WARNING, logger="realtime_native.feature_builder"):
            _append_history(_row(_ts(0)), path=csv)  # must not raise

    assert any("lock timeout" in m for m in caplog.messages)
    assert not csv.exists()  # write was skipped
