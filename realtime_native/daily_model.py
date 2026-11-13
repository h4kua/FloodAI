"""
The daily kecamatan flood model on the live site (bundle in models/daily_bundle/, trained and tested
by scripts/train_daily_live_model.py; report artifacts/reports/daily_live_model.md).

For today's WIB date D it gives each of the 42 kecamatan a calibrated probability that BPBD records
a flood there today, from IMERG Early rain through D-L (L = 1, 2 or 3: the most recent WIB day that
Giovanni has complete; it serves Early about a day late), the city's river-post Siaga status on D-1
and D-2 (our own 15-minute history rows in Supabase), the kecamatan's flood history and the season.
The city probability is the highest kecamatan probability; the lag's thresholds (8 / 4 / 2 model
alarm days a month) turn it into a level for the decision engine's L3, where the water-level, BMKG
and data-quality rules still apply.

Heavy work (Giovanni, Supabase) runs only in refresh(), called by the API scheduler, never in a
visitor's request. The result lives in memory for its WIB date; current() returns it or None, and
callers then keep the monthly realtime-native model. Nothing is read from or written to disk, so
tests and replays of past snapshots are unaffected. DAILY_MODEL_ENABLED=false switches it off.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from realtime_native import daily_features as dfe
from realtime_native.imerg_client import ImergUnavailable, fetch_rate

logger = logging.getLogger("flood.daily_model")

BUNDLE_DIR = Path(__file__).resolve().parents[1] / "models" / "daily_bundle"
RAIN_DAYS = 35            # the API's 0.85 daily decay leaves < 1 % after 30 days
RAIN_TTL = timedelta(minutes=55)
WIB = timezone(timedelta(hours=7))
LEVELS = (("danger", "DANGER"), ("warning", "WARNING"), ("pre_alert", "PRE_ALERT"))

_lock = threading.Lock()
_state: dict | None = None
_rain_cache: dict = {}    # {"fetched": datetime, "start": Timestamp, "daily": {...}, "strict": {...}}
_water_cache: dict = {}   # {date: city water features of that WIB day (dict) or None}


class DailyModelUnavailable(RuntimeError):
    pass


def enabled() -> bool:
    return os.getenv("DAILY_MODEL_ENABLED", "true").strip().lower() == "true"


@lru_cache(maxsize=1)
def load_bundle() -> dict:
    from xgboost import Booster

    bundle = json.loads((BUNDLE_DIR / "bundle.json").read_text(encoding="utf-8"))
    for lag, spec in bundle["lags"].items():
        booster = Booster()
        booster.load_model(str(BUNDLE_DIR / spec["model_file"]))
        spec["booster"] = booster
    return bundle


def wib_date(now=None) -> pd.Timestamp:
    """WIB calendar date of ``now`` (datetime or ISO string; naive means UTC)."""
    ts = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return pd.Timestamp(ts.tz_convert("Asia/Jakarta").date())


# ---------------------------------------------------------------- inputs

def _rain(cells: list[str], today: pd.Timestamp, now: datetime) -> tuple[dict, dict]:
    """Daily WIB rain per cell for the last RAIN_DAYS days: (counted when >= 44 half-hours,
    counted only when all 48 are present). Cached for RAIN_TTL."""
    start = today - pd.Timedelta(days=RAIN_DAYS)
    cached = _rain_cache
    if cached and cached["start"] == start and now - cached["fetched"] < RAIN_TTL:
        return cached["daily"], cached["strict"]
    start_utc = start - pd.Timedelta(hours=7)  # WIB midnight
    end_utc = pd.Timestamp(now.astimezone(timezone.utc).replace(tzinfo=None))

    def one(cell):
        return cell, fetch_rate(cell, start_utc, end_utc)

    with ThreadPoolExecutor(max_workers=4) as pool:
        rates = dict(pool.map(one, cells))
    daily = {c: dfe.wib_daily_rain(r) for c, r in rates.items()}
    strict = {c: _strict_days(r) for c, r in rates.items()}
    _rain_cache.clear()
    _rain_cache.update(fetched=now, start=start, daily=daily, strict=strict)
    return daily, strict


def _strict_days(rate: pd.Series) -> pd.Series:
    idx = rate.index
    local = idx.tz_convert(None) + dfe.WIB if idx.tz is not None else idx + dfe.WIB
    present = pd.Series(rate.notna().to_numpy(), index=local).groupby(local.floor("D")).sum()
    return present >= 48


def city_water_from_rows(rows: list[dict]) -> pd.DataFrame:
    """History rows ({fetched_at, poskobanjir}) -> city water features per WIB day."""
    records = []
    for row in rows:
        ts = pd.Timestamp(row.get("fetched_at"))
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        day = pd.Timestamp(ts.tz_convert("Asia/Jakarta").date())
        for post in row.get("poskobanjir") or []:
            if isinstance(post, dict):
                records.append((dfe.post_key(post.get("nama_pintu_air")), day, dfe.status_level(post.get("status_siaga"))))
    posts = pd.DataFrame(records, columns=["post", "date", "status"])
    if posts.empty:
        return pd.DataFrame(columns=dfe.WATER_DAY)
    return dfe.city_water_by_day(posts)


def _history_rows(start_utc: datetime, end_utc: datetime) -> list[dict]:
    from db.supabase_client import get_supabase_client

    client = get_supabase_client()
    rows, offset = [], 0
    while True:
        res = (client.table("realtime_snapshot_store")
               .select("fetched_at,poskobanjir:snapshot->poskobanjir")
               .like("id", "history:%")
               .gte("fetched_at", start_utc.isoformat()).lt("fetched_at", end_utc.isoformat())
               .order("fetched_at").range(offset, offset + 499).execute())
        batch = res.data or []
        rows += batch
        if len(batch) < 500:
            return rows
        offset += 500


def _water(today: pd.Timestamp) -> pd.DataFrame:
    """City water features of D-1 and D-2 from our history rows; completed days are cached."""
    days = [today - pd.Timedelta(days=k) for k in (1, 2)]
    missing = [d for d in days if d not in _water_cache]
    if missing:
        start = (min(missing) - pd.Timedelta(hours=7)).to_pydatetime().replace(tzinfo=timezone.utc)
        end = (max(missing) + pd.Timedelta(hours=17)).to_pydatetime().replace(tzinfo=timezone.utc)
        try:
            city = city_water_from_rows(_history_rows(start, end))
        except Exception as exc:  # noqa: BLE001 - water is optional; the model takes NaN
            logger.warning("daily_model water history unavailable: %s", type(exc).__name__)
            city = None
        for d in missing:
            if city is not None:
                _water_cache[d] = city.loc[d].to_dict() if d in city.index else None
        for old in [d for d in _water_cache if d < today - pd.Timedelta(days=7)]:
            del _water_cache[old]
    known = {d: _water_cache[d] for d in days if _water_cache.get(d)}
    return pd.DataFrame.from_dict(known, orient="index", columns=dfe.WATER_DAY) if known else pd.DataFrame(columns=dfe.WATER_DAY)


# ---------------------------------------------------------------- model

def choose_lag(daily: dict, strict: dict, today: pd.Timestamp) -> int:
    """Smallest lag whose day is complete in every cell (all 48 half-hours) with the six days
    before it counted too (the 7-day sum needs them)."""
    for lag in dfe.LAGS:
        day = today - pd.Timedelta(days=lag)
        window = pd.date_range(day - pd.Timedelta(days=6), day, freq="D")
        if all(bool(strict[c].get(day, False)) and daily[c].reindex(window).notna().all() for c in daily):
            return lag
    raise DailyModelUnavailable("IMERG Early has no complete day in the last three")


def predict(daily: dict, strict: dict, water_city: pd.DataFrame, today: pd.Timestamp, bundle: dict | None = None) -> dict:
    bundle = bundle or load_bundle()
    lag = choose_lag(daily, strict, today)
    spec = bundle["lags"][str(lag)]
    index = pd.date_range(today - pd.Timedelta(days=RAIN_DAYS), today, freq="D")
    up = bundle["upstream_cells"]
    bogor, depok = daily[up["bogor"]].reindex(index), daily[up["depok"]].reindex(index)
    water = dfe.water_features(water_city, [today]).iloc[0]
    season = dfe.season([today]).iloc[0]
    rows, names = [], []
    for slug, k in bundle["kecamatan"].items():
        rain = dfe.rain_features(daily[k["cell"]].reindex(index), bogor, depok, lag).loc[today]
        rows.append({**rain.to_dict(), "hist_rate": k["hist_rate"], **season.to_dict(),
                     "elevation": k["elevation"], "slope": k["slope"], **water.to_dict()})
        names.append(slug)
    from xgboost import DMatrix

    X = pd.DataFrame(rows, columns=bundle["features"])
    raw = spec["booster"].predict(DMatrix(X))
    iso = spec["isotonic"]
    prob = np.clip(np.interp(raw, iso["x"], iso["y"]), 0.0, 1.0)
    thr = spec["city_thresholds"]
    kecamatan = {slug: {"name": bundle["kecamatan"][slug]["name"], "probability": round(float(p), 4),
                        "risk_level": level_for(float(p), thr)} for slug, p in zip(names, prob)}
    top = max(kecamatan, key=lambda s: kecamatan[s]["probability"])
    city_p = kecamatan[top]["probability"]
    rain_day = today - pd.Timedelta(days=lag)
    return {
        "model_version": bundle["version"],
        "date": today.date().isoformat(),
        "lag_days": lag,
        "rain_through": rain_day.date().isoformat(),
        "rain_7d_mm_city_max": round(float(X["rain_7"].max()), 1),
        "upstream_bogor_mm": round(float(bogor.get(rain_day, np.nan)), 1),
        "water_days": [d.date().isoformat() for d in (today - pd.Timedelta(days=1), today - pd.Timedelta(days=2))
                       if d in water_city.index],
        "city_probability": city_p,
        "city_level": level_for(city_p, thr),
        "top_kecamatan": kecamatan[top]["name"],
        "thresholds": {"pre_alert": thr["pre_alert"], "warning": thr["warning"], "danger": thr["danger"]},
        "kecamatan": kecamatan,
    }


def level_for(p: float, thr: dict) -> str:
    for key, level in LEVELS:
        if p >= thr[key]:
            return level
    return "SAFE"


# ---------------------------------------------------------------- state

def refresh(now: datetime | None = None) -> dict | None:
    """Recompute today's predictions (scheduler only). Never raises; keeps the last good state."""
    global _state
    if not enabled():
        return None
    now = now or datetime.now(timezone.utc)
    with _lock:
        try:
            bundle = load_bundle()
            today = wib_date(now)
            cells = sorted({k["cell"] for k in bundle["kecamatan"].values()} | set(bundle["upstream_cells"].values()))
            daily, strict = _rain(cells, today, now)
            state = predict(daily, strict, _water(today), today, bundle)
            state["computed_at_utc"] = now.astimezone(timezone.utc).isoformat(timespec="seconds")
            _state = state
            logger.info("daily_model_refreshed date=%s lag=%s city_p=%.4f level=%s",
                        state["date"], state["lag_days"], state["city_probability"], state["city_level"])
            return state
        except (ImergUnavailable, DailyModelUnavailable) as exc:
            logger.warning("daily_model_unavailable reason=%s", exc)
        except Exception as exc:  # noqa: BLE001 - the site falls back to the monthly model
            logger.error("daily_model_failed error_type=%s error=%s", type(exc).__name__, exc)
        return None


def current(now: datetime | None = None) -> dict | None:
    """Today's predictions, or None (disabled, not computed yet, or computed for another date)."""
    state = _state
    if not enabled() or state is None or state["date"] != wib_date(now).date().isoformat():
        return None
    return state


def _reset_for_tests() -> None:
    global _state
    _state = None
    _rain_cache.clear()
    _water_cache.clear()
