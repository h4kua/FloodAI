"""
The learned decision layer (models/daily_bundle/decision_layer*.json, trained and tested by
scripts/train_decision_layer.py; report artifacts/reports/decision_layer.md).

It reads what the site sees right now: the daily kecamatan model's city probability, the 14 fixed river
posts now (highest Siaga status, share at Siaga 3+ / 2+, upstream, Manggarai), the same posts
yesterday, and today's rain so far (IMERG Early half-hours that started by now - 5 h, as in training:
mean and max over the model's kecamatan cells, Bogor upstream) with the WIB hour. A small XGBoost
model per rain lag (depth 2, inputs monotone increasing except the hour: a higher post status, chance
or rain can never lower the risk) gives the chance that BPBD records a flood in Jakarta today; three
thresholds learned from 2016-2025 turn it into Waspada / Siaga / Bahaya.

decide_wilayah() gives the same for each of the five kota (models/daily_bundle/wilayah_layer*.json,
scripts/train_wilayah_layer.py): the city inputs plus the kota's highest kecamatan chance and its own
river posts now and yesterday; a post of the kota or upstream at Siaga 1 makes that kota Bahaya. It
does not change the city status. WILAYAH_DECISION_ENABLED=false switches it off.

In the decision engine it replaces the hand-written middle layers; the safety rules in front of it stay
(L0 invalid data, L1 Siaga 1 / rapid rise, L1.7 BMKG severe), and the engine falls back to the full rule
hierarchy when the daily model, the river posts now (fewer than 8) or yesterday, or the layer for the
served lag are missing. It also replaces L2's escalations (heuristic signal conflicts). LEARNED_DECISION_ENABLED=false switches it off.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from realtime_native import daily_features as dfe

BUNDLE_DIR = Path(__file__).resolve().parents[1] / "models" / "daily_bundle"
LAYER_PATH = BUNDLE_DIR / "decision_layer.json"
WILAYAH_PATH = BUNDLE_DIR / "wilayah_layer.json"
LEVEL_ORDER = ("DANGER", "WARNING", "PRE_ALERT")
STATUS_NAMES = {0: "Normal", 1: "Siaga 3", 2: "Siaga 2", 3: "Siaga 1"}


def enabled() -> bool:
    return os.getenv("LEARNED_DECISION_ENABLED", "true").strip().lower() == "true" and LAYER_PATH.exists()


def wilayah_enabled() -> bool:
    return (os.getenv("WILAYAH_DECISION_ENABLED", "true").strip().lower() == "true" and WILAYAH_PATH.exists()
            and LAYER_PATH.exists())


def _load(path: Path) -> dict:
    from xgboost import Booster

    layer = json.loads(path.read_text(encoding="utf-8"))
    for spec in layer["lags"].values():
        booster = Booster()
        booster.load_model(str(BUNDLE_DIR / spec["model_file"]))
        spec["booster"] = booster
    return layer


@lru_cache(maxsize=1)
def load() -> dict:
    return _load(LAYER_PATH)


@lru_cache(maxsize=1)
def load_wilayah() -> dict:
    return _load(WILAYAH_PATH)


def water_now(posts: list[dict] | None) -> dict | None:
    """City water features of the current snapshot, or None with fewer than 8 river posts."""
    records = [(dfe.post_key(p.get("nama_pintu_air")), pd.Timestamp("2000-01-01"), dfe.status_level(p.get("status_siaga")))
               for p in (posts or []) if isinstance(p, dict)]
    if not records:
        return None
    city = dfe.city_water_by_day(pd.DataFrame(records, columns=["post", "date", "status"]))
    if city.empty:
        return None
    return {c: _clean(city.iloc[0][c]) for c in dfe.WATER_DAY}


def _clean(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(value) else value


def score(spec: dict, features: dict, names: list[str]) -> tuple[float, dict]:
    """Flood chance and each input's push on it (log-odds; positive raises the chance)."""
    from xgboost import DMatrix

    row = pd.DataFrame([[float(features.get(n) or 0.0) for n in names]], columns=names, dtype=float)
    matrix = DMatrix(row)
    chance = float(spec["booster"].predict(matrix)[0])
    contribs = spec["booster"].predict(matrix, pred_contribs=True)[0]
    return chance, {n: round(float(c), 4) for n, c in zip(names, contribs[:-1])}


def today_features(daily: dict, now=None) -> dict | None:
    """Today's rain so far as the layer was trained on it, or None without today's half-hours."""
    halfhours = daily.get("today_halfhours")
    if halfhours is None:
        return None
    from realtime_native import daily_model

    bundle = daily_model.load_bundle()
    kec_cells = sorted({k["cell"] for k in bundle["kecamatan"].values()})
    bogor = bundle["upstream_cells"]["bogor"]
    ts = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    ts = (ts.tz_localize("UTC") if ts.tzinfo is None else ts).tz_convert("Asia/Jakarta")
    hour = ts.hour + ts.minute / 60
    cutoff = hour - 5  # half-hours that started by now - 5 h

    def so_far(cell):
        return sum(mm for start, mm in (halfhours.get(cell) or {}).items()
                   if int(start[:2]) + int(start[3:]) / 60 <= cutoff)

    jak = [so_far(c) for c in kec_cells]
    return {"today_mean": float(np.mean(jak)), "today_max": float(max(jak)), "today_bogor": float(so_far(bogor)),
            "hour": float(hour)}


def city_features(daily: dict, posts: list[dict] | None, now=None) -> dict | None:
    """The city layer's inputs for this snapshot, or None when one is missing (the rules then decide)."""
    posts_now = water_now(posts)
    d1 = daily.get("water_d1") or {}
    if posts_now is None or _clean(d1.get("w_max")) is None:
        return None  # fewer than 8 river posts now, or no river-post day for yesterday
    today = today_features(daily, now)
    if today is None:
        return None  # no rain half-hours for today
    # A single missing post reading counts as normal (as in training): a data gap never raises the risk.
    return {"p": float(daily["city_probability"]),
            **{f"{c}_now": posts_now.get(c) or 0.0 for c in dfe.WATER_DAY},
            **{f"{c}_d1": _clean(d1.get(c)) or 0.0 for c in dfe.WATER_DAY},
            **today}


def _level(chance: float, thr: dict) -> str:
    return next((lvl for lvl in LEVEL_ORDER if thr.get(lvl) is not None and chance >= thr[lvl]), "SAFE")


def decide(daily: dict | None, posts: list[dict] | None, now=None) -> dict | None:
    """The layer's level for this snapshot, or None when it cannot decide (the rules then do)."""
    if not enabled() or not daily:
        return None
    layer = load()
    spec = layer["lags"].get(str(daily.get("lag_days")))
    features = city_features(daily, posts, now) if spec is not None else None
    if features is None:
        return None
    chance, push = score(spec, features, layer["features"])
    thr = spec["thresholds"]
    return {"version": layer["version"], "kind": layer["kind"], "lag_days": daily.get("lag_days"),
            "risk_level": _level(chance, thr), "score": round(chance, 4), "thresholds": thr, "features": features,
            "push": push}


def _post_statuses(posts: list[dict] | None) -> dict[str, float]:
    out = {}
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        key, status = dfe.post_key(p.get("nama_pintu_air")), dfe.status_level(p.get("status_siaga"))
        if key in dfe.RIVER_POSTS and not math.isnan(status):
            out[key] = max(out.get(key, 0.0), status)
    return out


def decide_wilayah(daily: dict | None, posts: list[dict] | None, now=None) -> dict | None:
    """Level per kota ("Jakarta Barat", ...), or None when the layer cannot decide."""
    if not wilayah_enabled() or not daily:
        return None
    layer = load_wilayah()
    spec = layer["lags"].get(str(daily.get("lag_days")))
    base = city_features(daily, posts, now) if spec is not None else None
    kec = daily.get("kecamatan") or {}
    if base is None or not kec:
        return None
    statuses, d1 = _post_statuses(posts), daily.get("posts_d1") or {}
    upstream = max((statuses.get(p, 0.0) for p in layer["upstream_posts"]), default=0.0)
    out = {}
    for name in layer["wilayah"]:
        kecs = [k for k, w in layer["kecamatan_wilayah"].items() if w == name and k in kec]
        local = [p for p, w in layer["post_wilayah"].items() if w == name]
        if not kecs:
            continue
        top = max(kecs, key=lambda k: kec[k]["probability"])
        local_now = max((statuses[p] for p in local if p in statuses), default=0.0)
        features = {**base, "p_w": float(kec[top]["probability"]), "local_now": local_now,
                    "local_d1": max((float(d1[p]) for p in local if p in d1), default=0.0),
                    **{f"is_{w.split()[1]}": int(w == name) for w in layer["wilayah"]}}
        chance, push = score(spec, features, layer["features"])
        level = _level(chance, spec["thresholds"])
        siaga1 = local_now >= 3 or upstream >= 3
        out[name.title()] = {
            "risk_level": "DANGER" if siaga1 else level, "score": round(chance, 4), "siaga1_rule": bool(siaga1),
            "top_kecamatan": {"name": kec[top]["name"], "probability": kec[top]["probability"]},
            "reasons": [_feature_text(n, features.get(n), False) for n, c in sorted(push.items(), key=lambda kv: -kv[1])
                        if c > 0.05 and n != "hour" and not n.startswith("is_")][:3],
            "reasons_en": [_feature_text(n, features.get(n), True) for n, c in sorted(push.items(), key=lambda kv: -kv[1])
                           if c > 0.05 and n != "hour" and not n.startswith("is_")][:3],
            "frequent": layer["frequent"].get(name, [])}
    return {"version": layer["version"], "lag_days": daily.get("lag_days"), "thresholds": spec["thresholds"],
            "frequent_period": layer.get("frequent_period"), "wilayah": out}


# ---------------------------------------------------------------- plain language

def _feature_text(name: str, value, en: bool) -> str:
    when = ("yesterday" if en else "kemarin") if name.endswith("_d1") else ("now" if en else "sekarang")
    base = name.rsplit("_", 1)[0]
    if name == "p":
        return f"daily model chance {value * 100:.0f}%" if en else f"peluang model harian {value * 100:.0f}%"
    status = ("no data" if en else "tidak ada data") if value is None else STATUS_NAMES.get(int(round(value)), "?")
    if base == "w_max":
        return f"highest river post {when} {status}" if en else f"pos sungai tertinggi {when} {status}"
    if base in ("w_frac1", "w_frac2"):
        band = "Siaga 3" if base == "w_frac1" else "Siaga 2"
        share = "?" if value is None else f"{value * 100:.0f}%"
        return (f"{share} of river posts at {band} or higher {when}" if en
                else f"{share} pos sungai di {band} ke atas {when}")
    if base == "w_upstream":
        return f"upstream posts (Katulampa, Depok) {when} {status}" if en else f"pos hulu (Katulampa, Depok) {when} {status}"
    if base == "w_manggarai":
        return f"Manggarai {when} {status}"
    if name == "today_mean":
        return f"rain so far today {value:.0f} mm on average" if en else f"hujan hari ini sejauh ini rata-rata {value:.0f} mm"
    if name == "today_max":
        return f"rain so far today up to {value:.0f} mm" if en else f"hujan hari ini sejauh ini hingga {value:.0f} mm"
    if name == "today_bogor":
        return f"rain in Bogor so far today {value:.0f} mm" if en else f"hujan di Bogor hari ini {value:.0f} mm"
    if name == "p_w":
        return f"highest kecamatan chance {value * 100:.0f}%" if en else f"peluang kecamatan tertinggi {value * 100:.0f}%"
    if name == "local_now":
        return f"its river posts now {status}" if en else f"pos sungai di wilayah ini sekarang {status}"
    if name == "local_d1":
        return f"its river posts yesterday {status}" if en else f"pos sungai di wilayah ini kemarin {status}"
    return name


def describe(learned: dict, en: bool = False) -> str:
    """The chance, the level thresholds, and the inputs that pushed the chance up the most."""
    thr, push, feats = learned.get("thresholds") or {}, learned.get("push") or {}, learned.get("features") or {}
    up = [n for n, c in sorted(push.items(), key=lambda kv: -kv[1]) if c > 0.05 and n != "hour"][:3]
    pct = lambda v: "-" if v is None else f"{v * 100:.0f}%"  # noqa: E731
    reasons = "; ".join(_feature_text(n, feats.get(n), en) for n in up)
    if en:
        text = (f" Decision model learned from 2016-2025 floods: flood chance today {pct(learned.get('score'))} "
                f"(Watch from {pct(thr.get('PRE_ALERT'))}, Alert {pct(thr.get('WARNING'))}, Danger {pct(thr.get('DANGER'))}).")
        return text + (f" Raised most by: {reasons}." if reasons else "")
    text = (f" Model keputusan yang dipelajari dari banjir 2016-2025: peluang banjir hari ini {pct(learned.get('score'))} "
            f"(Waspada mulai {pct(thr.get('PRE_ALERT'))}, Siaga {pct(thr.get('WARNING'))}, Bahaya {pct(thr.get('DANGER'))}).")
    return text + (f" Paling dinaikkan oleh: {reasons}." if reasons else "")
