/* ── Flood-aware route colouring — pure, UI-agnostic ───────────────────────
   Marks each stretch of a driving route as "rawan" (red) or "relatif aman"
   (green). This is an estimate, not a road-level flood forecast — there is no
   per-road flood data for Jakarta. A stretch is red when it passes within
   RISK_RADIUS_M of a BPBD flood-prone point that is active right now:
     - the point lies on a river whose water-level post is at Siaga (DSDA), or
     - it is raining heavily (≥ HEAVY_RAIN_MM_H), when every point counts —
       local pooling does not wait for a river to rise.
*/

export const RISK_RADIUS_M = 500;
export const HEAVY_RAIN_MM_H = 20;

// DSDA post → BPBD river names it feeds (rivers per post from the public AWLR
// dataset, data/bundled/awlr_stations.json). Upstream Ciliwung posts reach all
// three Ciliwung branches. Posts on rivers BPBD does not list (Kali Baru Timur,
// Kali Duri, sea gauges) map to nothing.
const CILIWUNG_ALL = ["CILIWUNG", "CILIWUNG ARAH ISTANA NEGARA", "CILIWUNG ARAH KANAL BANJIR BARAT"];
const POST_RIVERS = [
  [/katulampa|depok|cibalok|manggarai/i, CILIWUNG_ALL],
  [/karet/i, ["CILIWUNG ARAH KANAL BANJIR BARAT"]],
  [/istiqlal|jembatan merah|flush/i, ["CILIWUNG ARAH ISTANA NEGARA"]],
  [/krukut/i, ["KRUKUT"]],
  [/pesanggrahan/i, ["PESANGGRAHAN", "PESANGGRAHAN & ANGKE"]],
  [/angke|cengkareng drain/i, ["ANGKE", "PESANGGRAHAN & ANGKE"]],
  [/sunter|pulo gadung/i, ["SUNTER"]],
  [/cipinang|kampung rambutan/i, ["CIPINANG"]],
];

export function riversForPost(name) {
  const hit = POST_RIVERS.find(([pattern]) => pattern.test(name || ""));
  return hit ? hit[1] : [];
}

const isSiaga = (station) => /siaga/i.test(station?.status_siaga || "");

/** Posts at Siaga now, grouped by the BPBD river they feed. */
export function postsOnAlert(stations = []) {
  const byRiver = new Map();
  for (const s of stations.filter(isSiaga)) {
    for (const river of riversForPost(s.nama)) byRiver.set(river, [...(byRiver.get(river) || []), s]);
  }
  return byRiver;
}

/** BPBD rivers whose post is at Siaga now. */
export function riversOnAlert(stations = []) {
  return new Set(postsOnAlert(stations).keys());
}

/**
 * Flood-prone points that count right now, each with the reason it is active
 * and, for a river, the posts that caused it (`causes`, each post once).
 */
export function activeFloodPoints(points = [], stations = [], rainfallMmH = 0) {
  if (rainfallMmH >= HEAVY_RAIN_MM_H) return points.map((p) => ({ ...p, reason: "rain", causes: [] }));
  const byRiver = postsOnAlert(stations);
  return points.flatMap((p) => {
    const causes = [...new Map(
      (p.rivers || []).flatMap((r) => byRiver.get(r) || []).map((s) => [s.nama, s]),
    ).values()];
    return causes.length ? [{ ...p, reason: "river", causes }] : [];
  });
}

// Equirectangular metres around Jakarta's latitude — accurate to well under 1 %
// over a few kilometres, which is all a 500 m buffer needs.
const M_PER_DEG_LAT = 111_320;
const M_PER_DEG_LNG = 111_320 * Math.cos((-6.2 * Math.PI) / 180);

function toXY([lat, lng]) {
  return [lng * M_PER_DEG_LNG, lat * M_PER_DEG_LAT];
}

export function segmentLengthM(a, b) {
  const [ax, ay] = toXY(a);
  const [bx, by] = toXY(b);
  return Math.hypot(bx - ax, by - ay);
}

/** Shortest distance in metres from point p to the segment a–b (all [lat, lng]). */
export function distanceToSegmentM(p, a, b) {
  const [px, py] = toXY(p);
  const [ax, ay] = toXY(a);
  const [bx, by] = toXY(b);
  const dx = bx - ax;
  const dy = by - ay;
  const len2 = dx * dx + dy * dy;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/**
 * Split a route ([[lat, lng], …]) into runs of risky / safe stretches.
 * Returns { runs: [{ risky, positions }], riskyM, totalM, pointsHit }.
 */
export function splitRouteByRisk(coords, points, radiusM = RISK_RADIUS_M) {
  const runs = [];
  const hit = new Set();
  let riskyM = 0;
  let totalM = 0;
  for (let i = 0; i < coords.length - 1; i++) {
    const a = coords[i];
    const b = coords[i + 1];
    const near = points.filter((p) => distanceToSegmentM([p.lat, p.lon], a, b) <= radiusM);
    near.forEach((p) => hit.add(p));
    const risky = near.length > 0;
    const len = segmentLengthM(a, b);
    totalM += len;
    if (risky) riskyM += len;
    const last = runs[runs.length - 1];
    if (last && last.risky === risky) last.positions.push(b);
    else runs.push({ risky, positions: [a, b] });
  }
  return { runs, riskyM, totalM, pointsHit: [...hit] };
}

/**
 * Among alternative routes ({ coords, duration, … }), the one with the least
 * risky distance; within 100 m of that, the fastest. Returns its index.
 */
export function safestRouteIndex(scored) {
  if (!scored.length) return -1;
  const leastRisk = Math.min(...scored.map((r) => r.riskyM));
  let best = -1;
  scored.forEach((r, i) => {
    if (r.riskyM > leastRisk + 100) return;
    if (best === -1 || r.duration < scored[best].duration) best = i;
  });
  return best;
}
