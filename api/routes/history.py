"""
History for the Riwayat page: the site's own decisions, satellite rain and river posts over the last
days (services/history_service.py), and one post's water level for its chart on the map.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from services import history_service

router = APIRouter(tags=["history"])


@router.get("/history/summary", summary="Decisions, satellite rain and river posts over the last days.")
async def history_summary(days: int = Query(14, ge=1, le=30)) -> dict:
    return await run_in_threadpool(history_service.summary, days)


@router.get("/history/post", summary="One river post's water level and Siaga band over the last days.")
async def history_post(name: str = Query(..., min_length=2, max_length=80),
                       days: int = Query(2, ge=1, le=7)) -> dict:
    return await run_in_threadpool(history_service.post_series, name, days)
