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
export const NEAR_RIVER_M = 1000;

/** True when [lat, lng] lies within radiusM of any of the lines ([[lat, lng], …]). */
export function nearLines(lat, lng, lines = [], radiusM = NEAR_RIVER_M) {
  return lines.some((line) => line.some((a, i) => i > 0 && distanceToSegmentM([lat, lng], line[i - 1], a) <= radiusM));
}

/**
 * Flood-prone points that count right now. With `riverTable`
 * (src/data/postRivers.json), a post at Siaga only activates the points within
 * NEAR_RIVER_M of the river stretch drawn for it, not every point on that river:
 * Semanan, on the Angke far from where Cengkareng Drain measures, stayed red for
 * that post. An upstream post (`upstream`: Katulampa, Depok, outside Jakarta;
 * their water reaches all of the river downstream) or one with no stretch keeps
 * the whole river.
 */
export function activeFloodPoints(points = [], stations = [], rainfallMmH = 0, riverTable = null) {
  const byRiver = postsOnAlert(stations);
  const reaches = (post, p) => {
    const entry = riverTable ? riverForPost(post, riverTable) : null;
    return !entry?.lines?.length || entry.upstream || nearLines(p.lat, p.lon, entry.lines);
  };
  const active = rainfallMmH >= HEAVY_RAIN_MM_H
    ? points.map((p) => ({ ...p, reason: "rain", causes: [] }))
    : points.flatMap((p) => {
        const causes = [...new Map(
          (p.rivers || []).flatMap((r) => byRiver.get(r) || []).filter((s) => reaches(s, p)).map((s) => [s.nama, s]),
        ).values()];
        return causes.length ? [{ ...p, reason: "river", causes }] : [];
      });
  // A post at Siaga whose river has no BPBD point (e.g. Kali Baru Timur) would
  // otherwise mark nothing: the area around the post itself counts instead.
  const covered = new Set(points.flatMap((p) => p.rivers || []));
  const postAreas = stations
    .filter(isSiaga)
    .filter((s) => s.lat != null && s.lon != null)
    .filter((s) => !riversForPost(s.nama).some((r) => covered.has(r)))
    .map((s) => ({ kelurahan: null, lat: s.lat, lon: s.lon, rivers: [], reason: "post", causes: [s] }));
  return [...active, ...postAreas];
}

/**
 * "P.A. Marina Ancol 1 (Laut)" -> "marinaancol", "P.S. Krukut Hulu 2" -> "krukuthulu":
 * the key of the post's river in src/data/postRivers.json (same rule as
 * post_key in scripts/build_post_rivers.py).
 */
export function postKey(name) {
  return (name || "").toLowerCase()
    .replace(/\(.*?\)/g, " ")
    .replace(/^\s*(p\.?\s*[as]\.?|pompa)\s+/, " ")
    .replace(/\b(bendung|baru|bubble)\b/g, " ")
    .replace(/[^a-z]/g, "");
}

export const POST_MATCH_M = 1500;

/**
 * The river entry of a live post ({ nama, lat, lon }): by name first (the longest
 * table key the post's own key starts with; Flusing Ancol and Marina Ancol stand
 * 100 m apart), else the nearest table post within POST_MATCH_M, for names the
 * feed spells differently ("Ancol Flushing" for "Flusing Ancol").
 */
export function riverForPost(station, table = {}) {
  const key = postKey(station?.nama ?? station);
  const hit = Object.keys(table).filter((k) => k && key.startsWith(k)).sort((a, b) => b.length - a.length)[0];
  if (hit) return table[hit];
  if (station?.lat == null || station?.lon == null) return null;
  let best = null;
  let bestM = POST_MATCH_M;
  for (const e of Object.values(table)) {
    if (!e.at) continue;
    const m = segmentLengthM([station.lat, station.lon], e.at);
    if (m <= bestM) { best = e; bestM = m; }
  }
  return best;
}

/** {post name: the active flood-prone points that name it as a cause}. */
export function areasByPost(points = []) {
  const byPost = new Map();
  for (const p of points) {
    for (const s of p.causes || []) byPost.set(s.nama, [...(byPost.get(s.nama) || []), p]);
  }
  return byPost;
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

/** True when [lat, lng] lies within radiusM of any active flood-prone point. */
export function inFloodArea(lat, lng, points = [], radiusM = RISK_RADIUS_M) {
  return points.some((p) => segmentLengthM([lat, lng], [p.lat, p.lon]) <= radiusM);
}

// A place BPBD has used for evacuees goes first when it is this close.
export const BPBD_SITE_FIRST_KM = 1;

/**
 * Shelter order: BPBD evacuation sites within BPBD_SITE_FIRST_KM, then the other
 * safe candidates, then those inside an active flood-prone area or on BPBD's
 * list of flood-prone schools. Each group keeps its nearest-first order; each
 * shelter gets `inFloodArea`.
 */
export function rankSheltersByFlood(shelters = [], points = []) {
  const marked = shelters.map((s) => ({ ...s, inFloodArea: inFloodArea(s.lat, s.lng, points) }));
  const risky = (s) => s.inFloodArea || s.floodProneSchool;
  const preferred = (s) => !risky(s) && s.bpbdSite && s.distanceKm <= BPBD_SITE_FIRST_KM;
  return [
    ...marked.filter(preferred),
    ...marked.filter((s) => !risky(s) && !preferred(s)),
    ...marked.filter(risky),
  ];
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
 * True when every risky run touches the start or the end of the route: the start
 * or the destination itself lies in an active flood-prone area, so no road can
 * avoid those stretches.
 */
export function riskyOnlyAtEnds(runs = []) {
  const risky = runs.map((r, i) => (r.risky ? i : -1)).filter((i) => i >= 0);
  return risky.length > 0 && risky.every((i) => i === 0 || i === runs.length - 1);
}

// Google Maps URLs accept at most 3 waypoints on mobile browsers (9 elsewhere);
// more than that and phones may drop the route.
export const GMAPS_MAX_STOPS = 3;

/**
 * A Google Maps directions link that follows the given route: up to `stops`
 * evenly spaced points along it are passed as waypoints, so Google does not
 * pick its own (possibly flooded) way between the two ends. A GPS start is left
 * out so Google navigates from the phone's live position.
 */
export function googleMapsUrl(origin, dest, coords = [], stops = GMAPS_MAX_STOPS) {
  const ll = ([lat, lng]) => `${lat.toFixed(5)},${lng.toFixed(5)}`;
  const params = new URLSearchParams({ api: "1" });
  if (!origin.isGPS) params.set("origin", ll([origin.lat, origin.lng]));
  params.set("destination", ll([dest.lat, dest.lng]));
  params.set("travelmode", "driving");
  stops = Math.min(stops, GMAPS_MAX_STOPS);
  if (coords.length > 2 && stops > 0) {
    const picks = Array.from({ length: stops }, (_, i) =>
      coords.at(Math.round(((i + 1) * (coords.length - 1)) / (stops + 1))));
    params.set("waypoints", picks.map(ll).join("|"));
  }
  return `https://www.google.com/maps/dir/?${params.toString()}`;
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
