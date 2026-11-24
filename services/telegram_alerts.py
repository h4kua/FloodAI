"""
Telegram alerts: the site posts to one Telegram channel when Jakarta's status rises to Siaga or
Bahaya, and again when it falls back below Siaga. People join the channel; nothing about them is
stored here.

Configured on the server: TELEGRAM_BOT_TOKEN (from @BotFather, never logged) and TELEGRAM_CHAT_ID
(the channel, e.g. "@defloodjakarta", with the bot as an admin). TELEGRAM_MIN_LEVEL (default
WARNING) sets the lowest level that is announced. Without the token and chat id nothing is sent.
The last announced level lives in realtime_snapshot_store (id 'notify:telegram'), so a restart
does not send the same alert twice.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

logger = logging.getLogger("flood.telegram")

STATE_ID = "notify:telegram"
SITE_URL = "https://deflood.vercel.app"
LEVEL_RANK = {"UNKNOWN": -1, "SAFE": 0, "PRE_ALERT": 1, "WARNING": 2, "DANGER": 3}
LEVEL_ID = {"SAFE": "Aman", "PRE_ALERT": "Waspada", "WARNING": "Siaga", "DANGER": "Bahaya", "UNKNOWN": "Tidak diketahui"}


def configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip())


def _min_level() -> str:
    level = os.getenv("TELEGRAM_MIN_LEVEL", "WARNING").strip().upper()
    return level if level in ("PRE_ALERT", "WARNING", "DANGER") else "WARNING"


def decide_message(level: str, last_level: str | None, interpretation: str, min_level: str) -> str | None:
    """The message to post for a change from ``last_level`` to ``level``, or None."""
    rank, last, floor = LEVEL_RANK.get(level, -1), LEVEL_RANK.get(last_level or "SAFE", 0), LEVEL_RANK[min_level]
    if level == "UNKNOWN":
        return None  # missing data is not news for residents; the site says so itself
    if rank >= floor and rank > last:
        icon = "🔴" if level == "DANGER" else "🟠"
        return (f"{icon} deFlood.ai · Status banjir Jakarta naik ke {LEVEL_ID[level].upper()}\n\n"
                f"{interpretation}\n\nCek daerahmu dan rute aman: {SITE_URL}")
    if last >= floor and rank < floor:
        return (f"🟢 deFlood.ai · Status banjir Jakarta turun ke {LEVEL_ID.get(level, level)}\n\n"
                f"{interpretation}\n\n{SITE_URL}")
    return None


def _load_last() -> str | None:
    from db.supabase_client import get_supabase_client

    res = get_supabase_client().table("realtime_snapshot_store").select("snapshot").eq("id", STATE_ID).limit(1).execute()
    rows = res.data or []
    return (rows[0].get("snapshot") or {}).get("level") if rows else None


def _save_last(level: str) -> None:
    from db.supabase_client import get_supabase_client

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    get_supabase_client().table("realtime_snapshot_store").upsert(
        {"id": STATE_ID, "snapshot": {"level": level, "at": now}, "fetched_at": now}).execute()


def send(text: str) -> bool:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    try:
        resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                             json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=10)
    except requests.RequestException as exc:
        logger.warning("telegram_send_failed error_type=%s", type(exc).__name__)
        return False
    if resp.status_code != 200:
        logger.warning("telegram_send_failed status=%s", resp.status_code)
        return False
    return True


def maybe_notify(result: dict) -> str | None:
    """Post an alert when the level crosses TELEGRAM_MIN_LEVEL; returns the text sent, else None."""
    if not configured():
        return None
    level = result.get("risk_level") or "UNKNOWN"
    if level == "UNKNOWN":
        return None
    last = _load_last()
    text = decide_message(level, last, result.get("risk_interpretation") or "", _min_level())
    if text and not send(text):
        return None  # keep the old level: the next refresh tries again
    if level != last:
        _save_last(level)
    if text:
        logger.info("telegram_alert_sent level=%s previous=%s", level, last)
    return text
