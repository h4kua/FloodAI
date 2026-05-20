from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import requests

from app.services.data_ingestion import tma_scraper


def test_fetch_tma_data_stops_retrying_when_deadline_expires(monkeypatch):
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    fake_log = Mock()
    request_mock = Mock(side_effect=requests.exceptions.Timeout())
    sleep_mock = Mock()
    now_values = iter([started_at, started_at + timedelta(seconds=3)])

    monkeypatch.setenv("TMA_PROXY_URL", "https://example.test/tma")
    monkeypatch.setenv("TMA_MAX_RETRIES", "3")
    monkeypatch.setenv("TMA_RETRY_DELAY_SECONDS", "2")
    monkeypatch.setenv("TMA_TIMEOUT_SECONDS", "5")
    monkeypatch.setattr(tma_scraper, "_log", fake_log)
    monkeypatch.setattr(tma_scraper.requests, "get", request_mock)
    monkeypatch.setattr(tma_scraper._time, "sleep", sleep_mock)
    monkeypatch.setattr(tma_scraper, "_utcnow", lambda: next(now_values))

    result = tma_scraper.fetch_tma_data(
        now=started_at,
        deadline=started_at + timedelta(seconds=1),
    )

    assert result["status"] == "DEGRADED"
    assert "Retry deadline exceeded" in (result["reason"] or "")
    assert request_mock.call_count == 1
    sleep_mock.assert_not_called()
    fake_log.warning.assert_called_once()
