"""
Fresh realtime-snapshot builder.

Reuses the canonical poskobanjir ingestion pipeline (poskobanjir/main.py) to build
a snapshot with the EXACT same shape as the bundled realtime_snapshot.json, then
hands it to the Supabase snapshot repository.

Why a subprocess instead of an in-process import: poskobanjir/ is a self-contained
sub-project whose modules use bare imports (``from config import …``,
``from services.fetcher import …``) that assume poskobanjir/ is the sys.path root.
Those top-level names collide with the FastAPI app's own ``config``/``services``
packages, so it cannot be imported here. Running it as a subprocess (cwd=poskobanjir/)
respects its import root and reuses the builder verbatim — guaranteeing format parity
with zero duplicated fetch/parse logic.

build_fresh_snapshot() never raises: on any failure it returns an empty-but-shaped
snapshot stamped with the current UTC time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

from utils.paths import DEFAULT_REALTIME_SNAPSHOT, PROJECT_ROOT

logger = logging.getLogger("flood.snapshot_refresh")

_POSKOBANJIR_DIR = PROJECT_ROOT / "poskobanjir"
_POSKOBANJIR_ENTRY = "main.py"

# Internal build budget. The /internal/refresh-snapshot endpoint applies its own
# (larger) overall timeout; this caps just the subprocess so a hung upstream fetch
# cannot block indefinitely.
_BUILD_TIMEOUT_S = 40.0

_SNAPSHOT_KEYS = (
    "fetched_at_utc",
    "location",
    "openweather",
    "poskobanjir",
    "bmkg_alerts",
    "bmkg_feed",
    "summary",
    "source_attribution",
)


def _empty_snapshot() -> dict:
    """An empty-but-correctly-shaped snapshot stamped with the current UTC time."""
    return {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "location": "",
        "openweather": {},
        "poskobanjir": [],
        "bmkg_alerts": [],
        "bmkg_feed": [],
        "summary": {},
        "source_attribution": {},
    }


def summarize_sources(snapshot: dict) -> dict:
    """
    Derive per-source success from snapshot content. Returns
    ``{"ok": [...], "failed": [...]}`` over {"openweather","poskobanjir","bmkg"}.
    Logs each failed source at WARNING.
    """
    ow = snapshot.get("openweather")
    pos = snapshot.get("poskobanjir")
    feed = snapshot.get("bmkg_feed")
    alerts = snapshot.get("bmkg_alerts")

    status = {
        "openweather": isinstance(ow, dict) and bool(ow),
        "poskobanjir": isinstance(pos, list) and bool(pos),
        "bmkg": bool(feed) or bool(alerts),
    }
    ok = [name for name, good in status.items() if good]
    failed = [name for name, good in status.items() if not good]
    for name in failed:
        logger.warning("snapshot_source_failed source=%s", name)
    return {"ok": ok, "failed": failed}


def _mtime(path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


async def build_fresh_snapshot() -> dict:
    """
    Build a fresh snapshot by running the poskobanjir pipeline as a subprocess and
    reading the file it writes. Never raises.

    Returns the freshly built snapshot dict, or an empty-but-shaped snapshot (with a
    current ``fetched_at_utc``) when the build fails or does not produce a new file
    (e.g. the upstream poskobanjir source returned nothing, which makes the canonical
    pipeline abort before writing).
    """
    mtime_before = _mtime(DEFAULT_REALTIME_SNAPSHOT)

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            _POSKOBANJIR_ENTRY,
            cwd=str(_POSKOBANJIR_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_BUILD_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("snapshot_build_timeout timeout_s=%s", _BUILD_TIMEOUT_S)
            return _empty_snapshot()

        if proc.returncode != 0:
            tail = (stderr or b"").decode("utf-8", "replace")[-500:]
            logger.warning(
                "snapshot_build_nonzero_exit code=%s stderr_tail=%s", proc.returncode, tail
            )
            # fall through: the file may still be stale; mtime check below decides.
    except Exception as exc:  # noqa: BLE001 — builder must never raise.
        logger.warning("snapshot_build_subprocess_failed error_type=%s error=%s", type(exc).__name__, exc)
        return _empty_snapshot()

    # The canonical pipeline aborts (without writing) when poskobanjir returns no
    # records, so a successful exit does not guarantee a fresh file. Require the
    # file's mtime to have advanced.
    if _mtime(DEFAULT_REALTIME_SNAPSHOT) <= mtime_before:
        logger.warning("snapshot_build_no_fresh_file path=%s", str(DEFAULT_REALTIME_SNAPSHOT))
        return _empty_snapshot()

    try:
        with open(DEFAULT_REALTIME_SNAPSHOT, encoding="utf-8") as fh:
            snapshot = json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("snapshot_build_read_failed error_type=%s error=%s", type(exc).__name__, exc)
        return _empty_snapshot()

    if not isinstance(snapshot, dict) or not snapshot.get("fetched_at_utc"):
        logger.warning("snapshot_build_invalid_shape")
        return _empty_snapshot()

    # Guarantee every expected key is present (shape parity), without overwriting
    # values the canonical builder produced.
    empty = _empty_snapshot()
    for key in _SNAPSHOT_KEYS:
        snapshot.setdefault(key, empty[key])
    return snapshot
