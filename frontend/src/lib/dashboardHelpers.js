/* ── Dashboard pure helpers ───────────────────────────────────────────────
   Pure, side-effect-free functions and style constants extracted from the
   former 2000-line Home.jsx. No React, no JSX — safe to import anywhere.
*/

/* ── WIB (Jakarta) time formatter ───────────────────────────
   Formats an ISO timestamp as "HH:MM" in Asia/Jakarta (UTC+7, no DST) —
   replaces the manual getTime()+7h/padStart arithmetic that used to be
   duplicated across dashboard components.
*/
/* en-GB (not id-ID) deliberately — id-ID renders "09.05" (period separator),
   the rest of the app's "HH:MM" convention uses a colon. Locale only affects
   punctuation here; the timeZone below still does the actual UTC+7 conversion. */
const _wibFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Jakarta",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

// "1 post is" / "3 posts are" for the English status sentences.
const postsEn = (n) => (n === 1 ? "1 post is" : `${n} posts are`);

export function formatWib(isoString) {
  if (!isoString) return null;
  return _wibFormatter.format(new Date(isoString));
}

/* ── Data freshness ─────────────────────────────────────────
   The scraper runs every 15 min. Past STALE_STATUS_MIN the status is no
   longer "right now": the UI shows the date and greys the status out.
*/
export const STALE_STATUS_MIN = 180;

export function dataAgeMinutes(isoString) {
  if (!isoString) return null;
  return Math.round((Date.now() - new Date(isoString).getTime()) / 60000);
}

/* "23:29 WIB" while fresh, "12 Jul 2026, 23:29 WIB" once stale. */
export function formatDataTime(isoString, isId) {
  if (!isoString) return null;
  const time = `${formatWib(isoString)} WIB`;
  if (dataAgeMinutes(isoString) < STALE_STATUS_MIN) return time;
  const date = new Intl.DateTimeFormat(isId ? "id-ID" : "en-GB", {
    timeZone: "Asia/Jakarta", day: "numeric", month: "short", year: "numeric",
  }).format(new Date(isoString));
  return `${date}, ${time}`;
}

/* ── Risk trend label — its tone follows the status ─────────
   A rising trend under "Aman" is a nudge, not an alarm: neutral wording and
   colour so it never contradicts a calm status.
*/
export const TREND_TONE = {
  warn:    { color: "var(--wsp)",   bg: "var(--wsp-soft)",        border: "var(--wsp-border)"  },
  good:    { color: "var(--safe)",  bg: "var(--safe-soft)",       border: "var(--safe-border)" },
  neutral: { color: "var(--muted)", bg: "var(--panel-2)",           border: "var(--line)"        },
};

export function trendDisplay(riskTrend, level, isId) {
  if (!riskTrend) return null;
  if (riskTrend === "increasing") {
    return level === "aman"
      ? { text: isId ? "↑ Sedikit naik, masih aman" : "↑ Slightly up, still safe", ...TREND_TONE.neutral }
      : { text: isId ? "↑ Risiko naik" : "↑ Risk rising", ...TREND_TONE.warn };
  }
  if (riskTrend === "decreasing") return { text: isId ? "↓ Risiko turun" : "↓ Risk falling", ...TREND_TONE.good };
  return { text: isId ? "→ Stabil" : "→ Stable", ...TREND_TONE.neutral };
}

/* ── Station name cleaner ───────────────────────────────── */
export function cleanStationName(nama) {
  return (nama || "")
    .replace(/^P\.A\.\s*/i, "")
    .replace(/^P\.S\.\s*/i, "")
    .replace(/^Bendung\.\s*/i, "Bendung ")
    .trim();
}

/* ── Station → Kecamatan/area lookup ───────────────────────
   Used by the water-level list (StationPanel) to show human-readable
   kecamatan names. Entries that contradicted the station coordinates were
   corrected or removed (no label beats a wrong one); the rest are unverified.
*/
const _STATION_KEC = {
  "P.A. Marina Ancol (Laut)":  { kecamatan: "Pademangan",         area: "Pesisir Ancol" },
  "Pompa Pasar Ikan 1":        { kecamatan: "Penjaringan",        area: "Pelabuhan Sunda Kelapa" },
  "P.A. Cengkareng Drain":     { kecamatan: "Cengkareng",         area: "Cengkareng-Kapuk" },
  "P.A. Manggarai 2":          { kecamatan: "Tebet",              area: "Manggarai-Bukit Duri" },
  "P.A. Katulampa":            { kecamatan: "Bogor Timur",        area: "Katulampa, Bogor" },
  "P.A. Depok":                { kecamatan: "Pancoran Mas",       area: "Depok" },
  "P.A. Hek Kramat Jati 1":   { kecamatan: "Kramat Jati",        area: "Kali Baru Timur" },
  "P.A. Ancol Flushing 1":     { kecamatan: "Pademangan",         area: "Saluran Ancol" },
  "P.A. Marina Ancol (Kali)":  { kecamatan: "Pademangan",         area: "Kali Ancol" },
  "P.A. Manggarai":            { kecamatan: "Tebet",              area: "Manggarai" },
  "P.A. Cipinang Melayu":      { kecamatan: "Makasar",            area: "Kali Cipinang" },
  "P.A. Karet":                { kecamatan: "Tanah Abang",        area: "Kali Krukut" },
  "P.A. Pesanggrahan":         { kecamatan: "Pesanggrahan",       area: "Kali Pesanggrahan" },
  "P.A. Krukut Hulu":          { kecamatan: "Mampang Prapatan",   area: "Kali Krukut Hulu" },
  "P.A. Tomang Hulu":          { kecamatan: "Grogol Petamburan",  area: "Kali Angke Hulu" },
  "P.A. Pasar Ikan":           { kecamatan: "Penjaringan",        area: "Muara Baru" },
  "P.A. Waduk Pluit":          { kecamatan: "Penjaringan",        area: "Waduk Pluit" },
  "P.A. Angke Hulu":           { kecamatan: "Cengkareng",         area: "Kali Angke Hulu" },
  "P.A. Sunter Tengah":        { kecamatan: "Tanjung Priok",      area: "Kali Sunter Tengah" },
  "P.A. Mookervart":           { kecamatan: "Kalideres",          area: "Kali Mookervart" },
  "P.A. Pademangan":           { kecamatan: "Pademangan",         area: "Kali Sentiong" },
  "P.A. Cipinang Hulu":        { kecamatan: "Pulogadung",         area: "Kali Cipinang Hulu" },
  "P.A. Kalibaru Timur":       { kecamatan: "Cilincing",          area: "Kali Baru Timur" },
  "P.A. Duri Kosambi":         { kecamatan: "Cengkareng",         area: "Duri Kosambi" },
  "P.A. Jembatan Item":        { kecamatan: "Jatinegara",         area: "Kali Ciliwung" },
};

export function stationKecamatan(nama) {
  return _STATION_KEC[nama?.trim()] ?? null;
}

/* ── Risk helpers ──────────────────────────────────────── */
export function riskClass(rl) {
  if (rl === "SIAGA_1" || rl === "BAHAYA") return "s1";
  if (rl === "SIAGA_2" || rl === "SIAGA") return "s2";
  if (rl === "WASPADA") return "wsp";
  return "ok";
}

/* ── Station helpers ───────────────────────────────────── */
// Classify a station by its ratio (tinggi_air / siaga1).
export function stationRiskLevel(ratio) {
  if (ratio >= 1.0)  return "SIAGA_1";
  if (ratio >= 0.75) return "SIAGA_2";
  if (ratio >= 0.50) return "WASPADA";
  return "NORMAL";
}
export function stationClass(ratio) {
  if (ratio >= 1.0)  return "s1";
  if (ratio >= 0.75) return "s2";
  if (ratio >= 0.50) return "wsp";
  return "ok";
}

/* A post's level from the band DSDA itself reports ("Status : Siaga 2"), the
   same band the decision engine floors on; the ratio to Siaga 1 is only the
   fallback when the feed gives none. With the ratio alone a post at 76% of
   Siaga 1 read "Siaga 2" while DSDA, and the city status, said Siaga 3. */
const BAND_LEVEL = { 1: "SIAGA_1", 2: "SIAGA_2", 3: "WASPADA", 4: "NORMAL" };
const LEVEL_RANK = { NORMAL: 0, WASPADA: 1, SIAGA_2: 2, SIAGA_1: 3 };
export function postRiskLevel(s) {
  const status = s?.status_siaga || "";
  const band = /siaga\s*([1-4])/i.exec(status);
  if (band) return BAND_LEVEL[band[1]];
  if (/normal/i.test(status)) return "NORMAL";
  return stationRiskLevel(s?.ratio ?? 0);
}
export const postClass = (s) => riskClass(postRiskLevel(s));
// Worst first: by band, then by how close the water is to Siaga 1.
export const byPostSeverity = (a, b) =>
  LEVEL_RANK[postRiskLevel(b)] - LEVEL_RANK[postRiskLevel(a)] || (b.ratio ?? 0) - (a.ratio ?? 0);

/* ── Weather iconography — condition normalizer ─────────────────────────────
   Normalizes any BMKG weather_desc (Indonesian) or OpenWeather weather_main
   (English) to one of seven condition keys consumed by <WeatherGlyph>.
*/
export function weatherCond(text) {
  const s = (text || "").toLowerCase();
  if (s.includes("petir") || s.includes("thunder")) return "storm";
  if (s.includes("hujan") || s.includes("rain") || s.includes("drizzle") || s.includes("gerimis")) return "rain";
  if (s.includes("es") || s.includes("snow") || s.includes("salju")) return "snow";
  if (s.includes("kabur") || s.includes("asap") || s.includes("mist") || s.includes("fog") || s.includes("haze") || s.includes("smoke") || s.includes("dust")) return "mist";
  if (s.includes("cerah berawan") || s.includes("partly") || s.includes("few cloud") || s.includes("scattered")) return "partly";
  if (s.includes("berawan") || s.includes("cloud") || s.includes("mendung") || s.includes("overcast")) return "cloudy";
  if (s.includes("cerah") || s.includes("clear") || s.includes("sun")) return "clear";
  return "cloudy";
}

/* ── Weather description in the UI language ─────────────────
   BMKG and OpenWeather (fetched with lang=id) describe the sky in Indonesian.
   In English mode, map the description to a plain English label by keyword,
   most specific first; unknown text falls back to the original string.
*/
const WEATHER_EN = [
  [["petir", "badai"], "Thunderstorm"],
  [["lebat", "deras", "intensitas tinggi"], "Heavy rain"],
  [["hujan sedang"], "Moderate rain"],
  [["ringan", "rintik", "gerimis"], "Light rain"],
  [["hujan lokal"], "Local showers"],
  [["hujan"], "Rain"],
  [["kabut", "kabur", "asap"], "Haze"],
  [["cerah berawan", "sedikit berawan", "awan tersebar"], "Partly cloudy"],
  [["berawan tebal", "mendung", "awan pecah"], "Overcast"],
  [["berawan", "awan"], "Cloudy"],
  [["cerah"], "Clear"],
];

export function weatherLabel(text, isId) {
  if (!text) return text;
  if (isId) return text.charAt(0).toUpperCase() + text.slice(1);
  const s = text.toLowerCase();
  const hit = WEATHER_EN.find(([keys]) => keys.some((k) => s.includes(k)));
  return hit ? hit[1] : text;
}

/* ── Dynamic status description ─────────────────────────────
   Generates a plain-language summary from actual realtime sensor data.
   Replaces the four static hand-written strings that lived in cfgMap.
*/
export function buildStatusDesc(riskData, isId) {
  const level      = riskData?.level ?? "waspada";
  const wlr        = riskData?.waterLevelRatio ?? 0;
  const rainfall   = riskData?.rainfall ?? 0;
  const riskTrend  = riskData?.trendState?.risk_trend;
  const stations   = riskData?.stations ?? [];
  const wSummary   = riskData?.wilayahSummary ?? [];

  const s1 = stations.filter(s => postRiskLevel(s) === "SIAGA_1").sort(byPostSeverity);
  const s2 = stations.filter(s => postRiskLevel(s) === "SIAGA_2").sort(byPostSeverity);
  const dangerW = [...wSummary]
    .filter(w => ["Siaga 1","Siaga 2","Siaga 3"].includes(w.worst_status))
    .sort((a, b) => ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[b.worst_status] ?? 0) - ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[a.worst_status] ?? 0));
  const topW = dangerW[0];
  // When the learned decision layer set the level, lead with its flood chance for today.
  const learned = riskData?.decisionLayer?.decided ? riskData.decisionLayer : null;
  const lNote = learned
    ? (isId ? ` Peluang banjir hari ini ${formatChance(learned.score)} menurut model keputusan.`
            : ` Today's flood chance is ${formatChance(learned.score)} according to the decision model.`)
    : "";

  if (level === "unknown") {
    return isId
      ? "Data pos pantau dan cuaca belum cukup untuk menilai risiko banjir saat ini. Ikuti informasi resmi BPBD DKI Jakarta dan BMKG sampai data pulih."
      : "There isn't enough water-level and weather data to judge the flood risk right now. Follow official updates from BPBD DKI Jakarta and BMKG until the data is back.";
  }

  if (level === "bahaya") {
    const stNote = s1.length > 0
      ? (isId ? ` ${s1.length} pos pantau sudah melewati batas siaga, terparah di ${cleanStationName(s1[0].nama)}.` : ` ${postsEn(s1.length)} past the alert limit, worst at ${cleanStationName(s1[0].nama)}.`)
      : "";
    return isId
      ? `Kondisi berbahaya.${lNote}${stNote} Ikuti arahan BPBD dan bersiap mengungsi. Telepon 117 jika butuh bantuan.`
      : `Dangerous conditions.${lNote}${stNote} Follow BPBD instructions and get ready to evacuate. Call 117 if you need help.`;
  }

  if (level === "siaga") {
    const wlrPct = Math.round(wlr * 100);
    const sNote  = s1.length + s2.length > 0
      ? (isId ? ` ${s1.length + s2.length} pos pantau mendekati atau melewati batas siaga.` : ` ${postsEn(s1.length + s2.length)} near or past the alert limit.`)
      : "";
    const wNote  = topW
      ? (isId ? ` Paling perlu diwaspadai: ${topW.wilayah}.` : ` Watch ${topW.wilayah} most closely.`)
      : "";
    const lead = learned
      ? (isId ? `Peluang banjir hari ini ${formatChance(learned.score)}.` : `Today's flood chance is ${formatChance(learned.score)}.`)
      : (isId ? `Air sudah ${wlrPct}% dari batas siaga.` : `Water is at ${wlrPct}% of the alert limit.`);
    return isId
      ? `${lead}${sNote}${wNote} Siapkan tas darurat dan pantau terus.`
      : `${lead}${sNote}${wNote} Pack an emergency bag and keep watching.`;
  }

  if (level === "waspada") {
    const tNote = riskTrend === "increasing"
      ? (isId ? " Risikonya sedang naik." : " The risk is rising.")
      : riskTrend === "decreasing"
      ? (isId ? " Kondisinya mulai membaik." : " Things are improving.")
      : "";
    const alertCount = s1.length + s2.length;
    const sNote = alertCount > 0
      ? (isId ? ` ${alertCount} pos pantau berstatus siaga.` : ` ${postsEn(alertCount)} on alert.`)
      : "";
    const rfNote = rainfall > 5
      ? (isId ? ` Sedang hujan ${Math.round(rainfall)} mm/jam.` : ` It's raining ${Math.round(rainfall)} mm/h.`)
      : "";
    // The daily kecamatan model raises Waspada after wet days even when every post is normal: say so.
    const daily = riskData?.dailyModel;
    // With the learned layer deciding, mention recent rain only when the daily chance pushed the risk up.
    const rainPushed = !learned || (learned.push?.p ?? 0) > 0;
    const top = daily && daily.city_level !== "SAFE" && rainPushed ? dailyTopKecamatan(daily, 1)[0] : null;
    const dNote = top
      ? (isId
          ? ` Hujan beberapa hari terakhir menaikkan peluang banjir hari ini, tertinggi ${formatChance(top.probability)} di Kec. ${top.name}.`
          : ` Rain over the last few days raises today's flood chance, highest ${formatChance(top.probability)} in ${top.name}.`)
      : "";
    return isId
      ? `Ada tanda awal yang perlu diperhatikan.${lNote}${dNote}${sNote}${tNote}${rfNote} Pantau terus kondisinya.`
      : `There are early warning signs.${lNote}${dNote}${sNote}${tNote}${rfNote} Keep an eye on conditions.`;
  }

  // aman — only claim "all normal" when every post really is below Waspada,
  // so the sentence agrees with the per-wilayah badges right below it.
  const totalSt   = stations.length;
  const alertSt   = s1.length + s2.length;
  // Posts the backend marks `chronic` sit at Siaga 3 most of the time (Cengkareng Drain, two sea posts),
  // so their Siaga 3 does not raise the city status; say so instead of listing them as a warning.
  const waspadaPosts = stations.filter(s => postRiskLevel(s) === "WASPADA");
  const usualPosts = waspadaPosts.filter(s => s.chronic);
  const waspadaSt = waspadaPosts.length - usualPosts.length;
  const usualNames = usualPosts.map(s => cleanStationName(s.nama)).join(", ");
  const usualNote = usualPosts.length === 0
    ? ""
    : (isId
        ? ` ${usualNames} memang sering di Siaga 3, jadi tidak menaikkan status Jakarta.`
        : ` ${usualNames} ${usualPosts.length > 1 ? "are" : "is"} often at Siaga 3, so ${usualPosts.length > 1 ? "they do" : "it does"} not raise Jakarta's status.`);
  const sNote = totalSt === 0
    ? ""
    : alertSt > 0
    ? (isId ? ` Tapi ${alertSt} pos pantau sudah mendekati batas siaga — pantau terus.` : ` But ${postsEn(alertSt)} close to the alert limit — keep watching.`)
    : waspadaSt > 0
    ? (isId ? ` Air di ${waspadaSt} dari ${totalSt} pos pantau mulai tinggi (Waspada), tapi belum mendekati batas siaga.` : ` Water is getting high at ${waspadaSt} of ${totalSt} posts (Watch), but not near the alert limit.`) + usualNote
    : usualPosts.length > 0
    ? usualNote
    : (isId ? ` Semua ${totalSt} pos pantau dalam batas normal.` : ` All ${totalSt} monitoring posts are normal.`);
  // When the model input is statistically unusual (isOutlier && WLR < 0.75),
  // don't claim "nothing concerning" — frame it as honest uncertainty.
  const oodActive = riskData?.isOutlier && wlr < 0.75;
  const closing = oodActive
    ? (isId ? " Ada data yang sedikit tidak biasa, jadi tetap pantau sesekali." : " Some data looks a little unusual, so check back now and then.")
    : "";
  return isId
    ? `Jakarta saat ini aman dari banjir.${sNote}${closing}`
    : `Jakarta is currently safe from flooding.${sNote}${closing}`;
}

/* ── Wilayah status styling ────────────────────────────── */
export const WILAYAH_STATUS_STYLE = {
  "Siaga 1": { color: "var(--s1)", bg: "var(--s1-soft)", border: "var(--s1-border)" },
  "Siaga 2": { color: "var(--s2)", bg: "var(--s2-soft)", border: "var(--s2-border)" },
  "Siaga 3": { color: "var(--wsp)", bg: "var(--wsp-soft)", border: "var(--wsp-border)" },
  "Normal":  { color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)" },
};

/* ── Flood probability helpers ─────────────────────────────────── */
export function probColor(pct) {
  if (pct >= 75) return "var(--s1)";
  if (pct >= 55) return "var(--wsp)";
  if (pct >= 30) return "var(--s2)";
  return "var(--safe)";
}

// Derives per-wilayah flood probability from realtime TMA ratios +
// XGBoost global probability + siaga station counts.
// No historical DB needed — derived entirely from live sensor data.
export function computeWilayahFloodProb(w, stationsForWilayah, globalProb) {
  const maxRatio = stationsForWilayah.reduce((m, s) => Math.max(m, s.ratio || 0), 0);

  // TMA ratio → base probability (sigmoid-like curve)
  let tmaProb;
  if (maxRatio >= 1.0)       tmaProb = Math.min(0.97, 0.75 + maxRatio * 0.15);
  else if (maxRatio >= 0.75) tmaProb = 0.45 + (maxRatio - 0.75) * 1.20;
  else if (maxRatio >= 0.50) tmaProb = 0.20 + (maxRatio - 0.50) * 1.00;
  else                       tmaProb = maxRatio * 0.40;

  // Global ML probability scales the result (0.55–1.00)
  const mlScale = 0.55 + (globalProb ?? 0.5) * 0.45;

  // Bonus for multiple siaga sensors in the same wilayah (max +12%)
  const alertBonus = Math.min(
    (w?.siaga1_count ?? 0) * 0.06 + (w?.siaga2_count ?? 0) * 0.03 + (w?.siaga3_count ?? 0) * 0.015,
    0.12
  );

  let prob = (tmaProb * 0.80 + alertBonus) * mlScale;

  // Status-based floor: prevent obvious under-estimates
  const floors = { 4: 0.78, 3: 0.52, 2: 0.30, 1: 0.15, 0: 0.04 };
  prob = Math.max(prob, floors[w?.worst_rank ?? 0] ?? 0.04);

  return Math.round(Math.min(prob, 0.99) * 100);
}

// Infer Jakarta wilayah from lat/lon when backend wilayah field is absent.
export function inferWilayah(lat, lon) {
  if (!lat || !lon) return "";
  if (lat > -6.16 && lon > 106.75) return "Jakarta Utara";
  if (lon > 106.875)                return "Jakarta Timur";
  if (lat < -6.25)                  return "Jakarta Selatan";
  if (lon < 106.825)                return "Jakarta Barat";
  return "Jakarta Pusat";
}

/* ── Stations grouped by wilayah ────────────────────────────
   The backend sends each post's canonical wilayah as `wilayah_jakarta`
   (null = upstream), including corrections for posts DSDADKI misfiles — see
   realtime_native/wilayah.py, the single source of truth. The name match below
   is only a fallback for a backend that predates that field.
*/
export const JAKARTA_WILAYAH = ["Jakarta Utara", "Jakarta Barat", "Jakarta Pusat", "Jakarta Selatan", "Jakarta Timur"];
export const UPSTREAM_GROUP = "upstream";

const WILAYAH_EN = { Utara: "North", Barat: "West", Pusat: "Central", Selatan: "South", Timur: "East" };

/** "Jakarta Utara" -> "Utara" / "North" (short) or "Jakarta Utara" / "North Jakarta". */
export function wilayahLabel(name, isId, { short = true } = {}) {
  const part = (name || "").replace(/^Jakarta\s+/, "");
  if (isId) return short ? part : name;
  const en = WILAYAH_EN[part];
  if (!en) return name;
  return short ? en : `${en} Jakarta`;
}

export function stationWilayah(s) {
  if ("wilayah_jakarta" in s) return s.wilayah_jakarta ?? UPSTREAM_GROUP;
  const raw = (s.wilayah || "").toUpperCase();
  const named = JAKARTA_WILAYAH.find((w) => raw.includes(w.toUpperCase()));
  if (named) return named;
  if (raw) return UPSTREAM_GROUP;   // a named place outside Jakarta (Depok, Bogor…)
  return inferWilayah(s.lat, s.lon) || UPSTREAM_GROUP;
}

/* All 5 Jakarta wilayah (even with no posts) plus the upstream group when it
   has posts. Each group: { key, stations (worst first), worst, maxRatio }. */
export function groupStationsByWilayah(stations = []) {
  const byKey = {};
  for (const s of stations) (byKey[stationWilayah(s)] ??= []).push(s);
  const keys = [...JAKARTA_WILAYAH, ...(byKey[UPSTREAM_GROUP] ? [UPSTREAM_GROUP] : [])];
  return keys.map((key) => {
    const list = [...(byKey[key] ?? [])].sort(byPostSeverity);
    return { key, stations: list, worst: list[0] ?? null, maxRatio: list.length ? Math.max(...list.map((s) => s.ratio ?? 0)) : null };
  });
}

/* ── Wind direction (8-point compass, localized) ───────── */
export function windDirection(deg, isId) {
  if (deg == null) return "—";
  const id = ["U","TL","T","TG","S","BD","B","BL"];
  const en = ["N","NE","E","SE","S","SW","W","NW"];
  const idx = Math.round(deg / 45) % 8;
  return isId ? id[idx] : en[idx];
}

/* ── Daily kecamatan model (backend `daily_model`) ─────── */
const DAILY_LEVEL = { DANGER: "bahaya", WARNING: "siaga", PRE_ALERT: "waspada", SAFE: "aman" };

// The n kecamatan with the highest chance today, highest first: { slug, name, probability, level }.
export function dailyTopKecamatan(dailyModel, n = 5) {
  const rows = Object.entries(dailyModel?.kecamatan ?? {}).map(([slug, k]) => ({
    slug, name: k.name, probability: k.probability ?? 0, level: DAILY_LEVEL[k.risk_level] ?? "aman",
  }));
  return rows.sort((a, b) => b.probability - a.probability || a.name.localeCompare(b.name)).slice(0, n);
}

// 0.004 -> "<1%", 0.137 -> "14%".
export function formatChance(p) {
  if (p == null || Number.isNaN(p)) return "—";
  const pct = p * 100;
  return pct > 0 && pct < 1 ? "<1%" : `${Math.round(pct)}%`;
}

/* ── Decision layers' levels (backend SAFE / PRE_ALERT / WARNING / DANGER) ── */
const MODEL_LEVEL = { SAFE: "AMAN", PRE_ALERT: "WASPADA", WARNING: "SIAGA", DANGER: "BAHAYA", UNKNOWN: "UNKNOWN" };
export function modelLevelKey(level) {
  return MODEL_LEVEL[level] ?? "UNKNOWN";
}
export const LEVEL_COLOR = { SAFE: "var(--safe)", PRE_ALERT: "var(--wsp)", WARNING: "var(--s2)", DANGER: "var(--s1)", UNKNOWN: "var(--muted-2)" };

/** A timestamp as WIB date and/or time ("24 Nov, 14.30"). */
export function formatWibAt(ts, isId, { date = true, time = true } = {}) {
  if (!ts) return "";
  const d = typeof ts === "number" ? new Date(ts) : new Date(ts);
  const opts = { timeZone: "Asia/Jakarta" };
  if (date) Object.assign(opts, { day: "numeric", month: "short" });
  if (time) Object.assign(opts, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString(isId ? "id-ID" : "en-GB", opts);
}

/* ── What raised the learned layer's chance, in words (same as backend decision_layer.describe) ── */
const STATUS_NAME = ["Normal", "Siaga 3", "Siaga 2", "Siaga 1"];
export function layerReasonText(name, value, isId) {
  const when = name.endsWith("_d1") ? (isId ? "kemarin" : "yesterday") : (isId ? "sekarang" : "now");
  const base = name.replace(/_(now|d1)$/, "");
  const status = value == null ? (isId ? "tidak ada data" : "no data") : (STATUS_NAME[Math.round(value)] ?? "?");
  const pct = (v) => (v == null ? "?" : `${Math.round(v * 100)}%`);
  const mm = (v) => `${Math.round(v ?? 0)} mm`;
  switch (base) {
    case "p": return isId ? `peluang model harian ${pct(value)}` : `daily model chance ${pct(value)}`;
    case "w_max": return isId ? `pos sungai tertinggi ${when} ${status}` : `highest river post ${when} ${status}`;
    case "w_frac1": return isId ? `${pct(value)} pos sungai di Siaga 3 ke atas ${when}` : `${pct(value)} of river posts at Siaga 3 or higher ${when}`;
    case "w_frac2": return isId ? `${pct(value)} pos sungai di Siaga 2 ke atas ${when}` : `${pct(value)} of river posts at Siaga 2 or higher ${when}`;
    case "w_upstream": return isId ? `pos hulu (Katulampa, Depok) ${when} ${status}` : `upstream posts (Katulampa, Depok) ${when} ${status}`;
    case "w_manggarai": return `Manggarai ${when} ${status}`;
    case "today_mean": return isId ? `hujan hari ini rata-rata ${mm(value)}` : `rain so far today ${mm(value)} on average`;
    case "today_max": return isId ? `hujan hari ini hingga ${mm(value)}` : `rain so far today up to ${mm(value)}`;
    case "today_bogor": return isId ? `hujan di Bogor hari ini ${mm(value)}` : `rain in Bogor today ${mm(value)}`;
    default: return name;
  }
}

/** The learned layer's inputs that raised the chance most (push > 0.05 log-odds), as text. */
export function layerTopReasons(layer, isId, n = 3) {
  const push = layer?.push ?? {};
  return Object.entries(push)
    .filter(([name, v]) => v > 0.05 && name !== "hour")
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([name]) => layerReasonText(name, layer?.features?.[name], isId));
}

/** Distance in km between two [lat, lon] points (haversine). */
export function distanceKm(lat1, lon1, lat2, lon2) {
  const r = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * r) / 2) ** 2
    + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lon2 - lon1) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(a));
}
