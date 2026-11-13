"""
Features of the daily kecamatan flood model, shared by training (scripts/train_daily_live_model.py)
and serving (realtime_native/daily_model.py) so both compute them the same way.

Rain is GPM IMERG Early, the satellite product a live service can read. Giovanni serves it about a
day behind real time (28 h on 2026-11-13), so the model never sees the rain of the day it predicts:
a lag-L model uses rain through WIB day D-L, and the server picks the smallest L whose day is
complete. Water levels are the official DSDA Siaga status of a fixed set of river posts that report
both in the 2016-2021 archive and in today's feed, summarised over the city for D-1 and D-2 (our own
15-minute snapshots cover those days completely). Coastal and gate-operated posts are left out: their
status follows the tide or the gates, and its base rate differs between the archive and the live feed.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

WIB = pd.Timedelta(hours=7)
LAGS = (1, 2, 3)
MIN_HALF_HOURS = 44  # of 48: a WIB day with fewer IMERG half-hours counts as missing
STATUS = {"NORMAL": 0, "SIAGA 3": 1, "SIAGA 2": 2, "SIAGA 1": 3}
# River posts in both the 2016-2021 archive and the live feed, with comparable status base rates.
RIVER_POSTS = frozenset({
    "MANGGARAI", "KARET", "KATULAMPA", "DEPOK", "KRUKUTHULU", "PESANGGRAHAN", "CIDENG", "SUNTERHULU",
    "PULOGADUNG", "ANGKEHULU", "YOSSUDARSO", "CIBALOKGADOG", "KALIDURI", "PLUIT",
})
UPSTREAM_POSTS = frozenset({"KATULAMPA", "DEPOK"})
MIN_RIVER_POSTS = 8

WATER_DAY = ["w_max", "w_frac1", "w_frac2", "w_upstream", "w_manggarai"]
WATER = [f"{c}_d1" for c in WATER_DAY] + [f"{c}_d2" for c in WATER_DAY]
RAIN = ["rain_lag", "rain_3", "rain_7", "api", "up_bogor_lag", "up_bogor_3", "up_depok_lag"]
STATIC = ["hist_rate", "month_sin", "month_cos", "elevation", "slope"]
FEATURES = RAIN + STATIC + WATER


def post_key(name: str | None) -> str:
    """'P.A. Manggarai 2' / 'PS. MANGGARAI' -> 'MANGGARAI'; 'Rumah Pompa Pluit 1' -> 'PLUIT'."""
    key = re.sub(r"[^A-Z0-9]", "", (name or "").upper())
    key = re.sub(r"^(PINTUAIR|POSKO|POMPA|PA|PS)", "", key)
    key = re.sub(r"^(BENDUNG|PHB)", "", key)
    key = key.replace("KATULAMPAHULU", "KATULAMPA").replace("ISTIQAL", "ISTIQLAL")
    key = re.sub(r"\d+$", "", key)  # sensor number: "Manggarai 2", "Yos Sudarso 1"
    aliases = {"KALIDURIKALIJODO": "KALIDURI", "RUMAHPOMPAPLUIT": "PLUIT", "FLUSHINGANCOL": "ANCOLFLUSHING",
               "FLUSINGANCOL": "ANCOLFLUSHING", "HEKKRAMATJATI": "HEK"}
    return aliases.get(key, key)


def status_level(text: str | None) -> float:
    """Official status_siaga text -> 0 normal, 1 Siaga 3, 2 Siaga 2, 3 Siaga 1; NaN when unreadable."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return np.nan
    t = re.sub(r"^STATUS\s*:\s*", "", str(text).strip().upper())
    return float(STATUS[t]) if t in STATUS else np.nan


def city_water_by_day(posts: pd.DataFrame) -> pd.DataFrame:
    """posts: one row per post and WIB day (post key, date, status = the day's highest status)
    -> city water features per day; days with fewer than MIN_RIVER_POSTS river posts are dropped."""
    river = posts[posts["post"].isin(RIVER_POSTS)].dropna(subset=["status"])
    river = river.groupby(["date", "post"], as_index=False)["status"].max()
    g = river.groupby("date")["status"]
    city = pd.DataFrame({
        "posts": g.size(),
        "w_max": g.max(),
        "w_frac1": g.apply(lambda s: float((s >= 1).mean())),
        "w_frac2": g.apply(lambda s: float((s >= 2).mean())),
        "w_upstream": river[river["post"].isin(UPSTREAM_POSTS)].groupby("date")["status"].max(),
        "w_manggarai": river[river["post"] == "MANGGARAI"].groupby("date")["status"].max(),
    })
    return city[city["posts"] >= MIN_RIVER_POSTS].drop(columns="posts").rename_axis("date")


def water_features(city: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    """City water features of D-1 and D-2 for each date D (NaN where that day is missing)."""
    dates = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    out = {}
    for lag in (1, 2):
        shifted = city.reindex(dates - pd.Timedelta(days=lag))
        for c in WATER_DAY:
            out[f"{c}_d{lag}"] = shifted[c].to_numpy() if c in shifted else np.full(len(dates), np.nan)
    return pd.DataFrame(out)


def wib_daily_rain(rate_mm_per_h: pd.Series) -> pd.Series:
    """Half-hourly IMERG rate (mm/h, UTC index) -> rain per WIB day in mm, NaN for days with fewer
    than MIN_HALF_HOURS half-hours (missing half-hours inside a counted day add nothing)."""
    idx = rate_mm_per_h.index
    local = idx.tz_convert(None) + WIB if idx.tz is not None else idx + WIB
    s = pd.Series(rate_mm_per_h.to_numpy(dtype=float), index=local)
    day = s.index.floor("D")
    depth = (s * 0.5).groupby(day).sum(min_count=1)
    present = s.notna().groupby(day).sum()
    return depth.where(present >= MIN_HALF_HOURS)


def rain_features(local: pd.Series, bogor: pd.Series, depok: pd.Series, lag: int) -> pd.DataFrame:
    """Daily rain (WIB days, one index for all three series) -> features for day D from rain
    through D-lag. Rolling sums need every day present; the API treats a missing day as dry."""
    s, b, d = local.shift(lag), bogor.shift(lag), depok.shift(lag)
    return pd.DataFrame({
        "rain_lag": s,
        "rain_3": s.rolling(3).sum(),
        "rain_7": s.rolling(7).sum(),
        "api": s.fillna(0.0).ewm(alpha=0.15, adjust=False).mean() / 0.15,  # decay 0.85 a day
        "up_bogor_lag": b,
        "up_bogor_3": b.rolling(3).sum(),
        "up_depok_lag": d,
    }, index=local.index)


def season(dates) -> pd.DataFrame:
    m = pd.to_datetime(pd.Series(dates)).dt.month.to_numpy()
    return pd.DataFrame({"month_sin": np.sin(2 * np.pi * m / 12), "month_cos": np.cos(2 * np.pi * m / 12)})
