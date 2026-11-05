#!/usr/bin/env python
"""
Build frontend/src/data/postRivers.json: for each DSDA water-level post, the stretch of the
river it measures, as map lines that start at the post, so a clicked post can light up its
river in blue.

Inputs:
  data/bundled/awlr_stations.json      post name, coordinates and river(s) ("kali", e.g.
                                       "Kali Cengkareng Drain & Kali Angke")
  data/raw/jakarta_waterways.geojson   OpenStreetMap waterways of Jakarta (lat -6.39 to -6.08)

Per post, the stretch is traced on the waterway network, not looked up by name:
  1. seeds: waterways within SEED_M of the post, those named like the post's river first,
     else the nearest river/canal there (many posts sit on an unnamed OSM piece);
  2. from the seeds, follow connected waterways (sharing a vertex) up- and downstream while
     they stay within RADIUS_KM of the post: a named piece only when its name matches the
     post's river or a seed's, an unnamed river/canal only as an end-to-end continuation, so
     the line never jumps onto a crossing river.
A post with no waterway within SEED_M (the upstream posts in Bogor, Depok and Tangerang lie
outside this map) gets no line; the frontend names its river without drawing one.
Lines are thinned (Douglas-Peucker, about 15 m) and rounded to 5 decimals.

Run:  python scripts/build_post_rivers.py
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict, deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
STATIONS = _ROOT / "data" / "bundled" / "awlr_stations.json"
WATERWAYS = _ROOT / "data" / "raw" / "jakarta_waterways.geojson"
OUT = _ROOT / "frontend" / "src" / "data" / "postRivers.json"
SEED_M = 150.0
RADIUS_KM = 8.0
TOLERANCE_DEG = 0.00015
MAIN_TYPES = {"river", "canal"}
# DSDA and OpenStreetMap spell some rivers differently.
ALIASES = {"banjirkanalbarat": "kanalbanjirbarat", "banjirkanaltimur": "kanalbanjirtimur"}
SKIP = {"laut", "waduk pluit", "anak kali ciliwung"}


def river_key(name: str) -> str:
    text = re.sub(r"\b(kali|sungai|river)\b", "", (name or "").lower())
    key = re.sub(r"[^a-z0-9]", "", text)
    return ALIASES.get(key, key)


def names_match(a: str, b: str) -> bool:
    """'ciliwunggunungsahari' ~ 'ciliwung', 'duriledeng' ~ 'duri', but not 'ciliwunggajahmada'."""
    if not a or not b:
        return False
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 4 and long_.startswith(short) and not (
        len(long_) > len(short) and long_ in _OTHER_BRANCHES and short != long_)


# Named branches that must not stand in for their parent river (Ciliwung Gajah Mada is a
# separate canal west of the Gunung Sahari branch).
_OTHER_BRANCHES = {"ciliwunggajahmada"}


def post_key(name: str) -> str:
    """'P.A. Marina Ancol 1 (Laut)' -> 'marinaancol', 'P.S. Krukut Hulu 2' -> 'krukuthulu'.
    The frontend's postKey (src/lib/floodRoads.js) applies the same rule."""
    text = re.sub(r"\(.*?\)", " ", (name or "").lower())
    text = re.sub(r"^\s*(p\.?\s*[as]\.?|pompa)\s+", " ", text)
    text = re.sub(r"\b(bendung|baru|bubble)\b", " ", text)
    return re.sub(r"[^a-z]", "", text)


def km(a, b) -> float:
    dlat = (a[0] - b[0]) * 111.32
    dlon = (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def seg_km(p, a, b) -> float:
    """Distance from p to segment a-b, all [lat, lon]."""
    k = math.cos(math.radians(p[0]))
    ax, ay, bx, by, px, py = a[1] * k, a[0], b[1] * k, b[0], p[1] * k, p[0]
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1e-12)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy) * 111.32


def thin(points: list, tol: float) -> list:
    """Douglas-Peucker on [lat, lon] points."""
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    norm = math.hypot(dx, dy) or 1e-12
    far, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = abs(dy * (points[i][0] - a[0]) - dx * (points[i][1] - a[1])) / norm
        if d > far:
            far, idx = d, i
    if far <= tol:
        return [a, b]
    return thin(points[: idx + 1], tol)[:-1] + thin(points[idx:], tol)


def clip(line: list, centre: list) -> list[list]:
    """The runs of a line that lie within RADIUS_KM of the post (a long OSM way can run
    far past it)."""
    runs, run = [], []
    for q in line:
        if km(centre, q) <= RADIUS_KM:
            run.append(q)
        elif run:
            runs.append(run + [q])  # one point past the edge, so the run reaches it
            run = []
    if run:
        runs.append(run)
    return [r for r in runs if len(r) >= 2]


def connected_to_post(lines: list[list], centre: list) -> list[list]:
    """Only the lines linked (through shared points) to one that touches the post: a river
    that winds out of the radius and back would otherwise leave loose pieces."""
    owners = defaultdict(set)
    for i, line in enumerate(lines):
        for q in line:
            owners[tuple(q)].add(i)
    start = [i for i, line in enumerate(lines)
             if any(seg_km(centre, a, b) * 1000 <= SEED_M for a, b in zip(line, line[1:]))]
    seen, queue = set(start), deque(start)
    while queue:
        cur = queue.popleft()
        for q in lines[cur]:
            for nxt in owners[tuple(q)] - seen:
                seen.add(nxt)
                queue.append(nxt)
    return [lines[i] for i in sorted(seen)]


def load_waterways() -> list[dict]:
    ways = []
    for f in json.loads(WATERWAYS.read_text(encoding="utf-8"))["features"]:
        props = f["properties"]
        coords = [[lat, lon] for lon, lat in f["geometry"]["coordinates"]]
        keys = {river_key(props.get(k)) for k in ("name", "alt_name", "name:en") if props.get(k)}
        ways.append({"coords": coords, "keys": keys - {""}, "type": props.get("waterway"),
                     "ends": {tuple(coords[0]), tuple(coords[-1])}})
    return ways


def trace(ways: list[dict], by_vertex: dict, centre: list, rivers: list[str]) -> list[int]:
    """Indexes of the waterways that form the post's river stretch."""
    wanted = {river_key(r) for r in rivers}
    near = [(min(seg_km(centre, w["coords"][i], w["coords"][i + 1]) for i in range(len(w["coords"]) - 1)), i)
            for i, w in enumerate(ways)]
    near = sorted((d, i) for d, i in near if d * 1000 <= SEED_M)
    named = [i for _, i in near if any(names_match(k, r) for k in ways[i]["keys"] for r in wanted)]
    seeds = named or [i for _, i in near if ways[i]["type"] in MAIN_TYPES][:1]
    if not seeds:
        return []
    allowed = wanted | {k for i in seeds for k in ways[i]["keys"]}

    def within(i):
        return any(km(centre, q) <= RADIUS_KM for q in ways[i]["coords"])

    seen, queue = set(seeds), deque(seeds)
    while queue:
        cur = queue.popleft()
        for vertex in map(tuple, ways[cur]["coords"]):
            for nxt in by_vertex[vertex]:
                if nxt in seen or not within(nxt):
                    continue
                w = ways[nxt]
                if w["keys"]:
                    ok = any(names_match(k, a) for k in w["keys"] for a in allowed)
                else:  # unnamed: only a main channel continuing end to end
                    ok = w["type"] in MAIN_TYPES and vertex in w["ends"] and vertex in ways[cur]["ends"]
                if ok:
                    seen.add(nxt)
                    queue.append(nxt)
    return sorted(seen)


def build() -> dict:
    stations = json.loads(STATIONS.read_text(encoding="utf-8"))["stations"]
    ways = load_waterways()
    by_vertex = defaultdict(set)
    for i, w in enumerate(ways):
        for q in w["coords"]:
            by_vertex[tuple(q)].add(i)

    out = {}
    for s in stations:
        rivers = [r.strip() for r in (s.get("kali") or "").split("&") if r.strip()]
        rivers = [r for r in rivers if r.lower() not in SKIP]
        centre = [s["lat"], s["lon"]]
        # A sea or reservoir gauge (no river in the DSDA list) gets no line.
        picked = trace(ways, by_vertex, centre, rivers) if rivers else []
        lines = connected_to_post([run for i in picked for run in clip(ways[i]["coords"], centre)], centre)
        out[post_key(s["station_name"])] = {
            "post": s["station_name"],
            # The live feed spells some posts differently ("Ancol Flushing" vs "Flusing
            # Ancol"), so the frontend matches a post by place first.
            "at": [round(s["lat"], 5), round(s["lon"], 5)],
            "rivers": rivers,
            "lines": [[[round(lat, 5), round(lon, 5)] for lat, lon in thin(line, TOLERANCE_DEG)] for line in lines],
        }
    return out


def main() -> int:
    out = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} posts -> {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    for v in out.values():
        length = sum(km(a, b) for line in v["lines"] for a, b in zip(line, line[1:]))
        print(f"  {v['post']:30} {' & '.join(v['rivers'])[:44]:44} {len(v['lines']):3} pieces {length:5.1f} km")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
