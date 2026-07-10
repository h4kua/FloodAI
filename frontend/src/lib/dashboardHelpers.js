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

export function formatWib(isoString) {
  if (!isoString) return null;
  return _wibFormatter.format(new Date(isoString));
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
   Used by KecamatanZones to show human-readable location
   names instead of technical station identifiers.
*/
const _STATION_KEC = {
  "P.A. Marina Ancol (Laut)":  { kecamatan: "Penjaringan",        area: "Pesisir Ancol" },
  "Pompa Pasar Ikan 1":        { kecamatan: "Penjaringan",        area: "Pelabuhan Sunda Kelapa" },
  "P.A. Cengkareng Drain":     { kecamatan: "Cengkareng",         area: "Cengkareng-Kapuk" },
  "P.A. Manggarai 2":          { kecamatan: "Tebet",              area: "Manggarai-Bukit Duri" },
  "P.A. Katulampa":            { kecamatan: "Bogor Timur",        area: "Katulampa, Bogor" },
  "P.A. Depok":                { kecamatan: "Pancoran Mas",       area: "Depok" },
  "P.A. Hek Kramat Jati 1":   { kecamatan: "Kramat Jati",        area: "Kali Baru Timur" },
  "P.A. Kaliduri 1":           { kecamatan: "Kalideres",          area: "Kali Biru" },
  "P.A. Ancol Flushing 1":     { kecamatan: "Cilincing",          area: "Saluran Ancol" },
  "P.A. Marina Ancol (Kali)":  { kecamatan: "Penjaringan",        area: "Kali Ancol" },
  "P.A. Manggarai":            { kecamatan: "Tebet",              area: "Manggarai" },
  "P.A. Cipinang Melayu":      { kecamatan: "Makasar",            area: "Kali Cipinang" },
  "P.A. Sunter Hulu":          { kecamatan: "Cilincing",          area: "Kali Sunter Hulu" },
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
  if (rl === "SIAGA_1") return "s1";
  if (rl === "SIAGA_2") return "s2";
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

  const s1 = [...stations].filter(s => s.ratio >= 1.0).sort((a, b) => b.ratio - a.ratio);
  const s2 = [...stations].filter(s => s.ratio >= 0.75 && s.ratio < 1.0).sort((a, b) => b.ratio - a.ratio);
  const dangerW = [...wSummary]
    .filter(w => ["Siaga 1","Siaga 2","Siaga 3"].includes(w.worst_status))
    .sort((a, b) => ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[b.worst_status] ?? 0) - ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[a.worst_status] ?? 0));
  const topW = dangerW[0];

  if (level === "bahaya") {
    const stNote = s1.length > 0
      ? (isId ? `${s1.length} sensor melewati ambang Siaga 1 — terparah: ${s1[0].nama}` : `${s1.length} sensor(s) past Alert-1 threshold — worst: ${s1[0].nama}`)
      : "";
    const rfNote = rainfall > 0 ? (isId ? `, hujan ${Math.round(rainfall)} mm/jam` : `, rain ${Math.round(rainfall)} mm/h`) : "";
    return isId
      ? `KONDISI KRITIS! ${stNote}${rfNote}. Ikuti instruksi BPBD segera — hubungi 117. Bersiap evakuasi sekarang.`
      : `CRITICAL! ${stNote}${rfNote}. Follow BPBD instructions immediately — call 117. Prepare to evacuate now.`;
  }

  if (level === "siaga") {
    const wlrPct = Math.round(wlr * 100);
    const sNote  = s2.length > 0
      ? (isId ? ` ${s2.length} sensor Siaga 2${s1.length > 0 ? `, ${s1.length} Siaga 1` : ""}.` : ` ${s2.length} Alert-2 sensor(s)${s1.length > 0 ? `, ${s1.length} Alert-1` : ""}.`)
      : "";
    const wNote  = topW
      ? (isId ? ` ${topW.wilayah} status ${topW.worst_status}.` : ` ${topW.wilayah} at ${topW.worst_status}.`)
      : "";
    return isId
      ? `Ketinggian air ${wlrPct}% dari ambang siaga.${sNote}${wNote} Siapkan tas darurat dan pantau setiap 15 menit.`
      : `Water level at ${wlrPct}% of alert threshold.${sNote}${wNote} Prepare emergency bag and monitor every 15 min.`;
  }

  if (level === "waspada") {
    const tNote = riskTrend === "increasing"
      ? (isId ? " Tren risiko sedang naik." : " Risk trend is rising.")
      : riskTrend === "decreasing"
      ? (isId ? " Situasi mulai membaik." : " Situation improving.")
      : "";
    const alertCount = s1.length + s2.length;
    const sNote = alertCount > 0
      ? (isId ? ` ${alertCount} sensor dalam kondisi siaga.` : ` ${alertCount} sensor(s) in alert state.`)
      : "";
    const rfNote = rainfall > 5
      ? (isId ? ` Curah hujan ${Math.round(rainfall)} mm/jam.` : ` Rainfall ${Math.round(rainfall)} mm/h.`)
      : "";
    return isId
      ? `Ada tanda awal yang perlu dipantau.${sNote}${tNote}${rfNote} Cek ketinggian air berkala.`
      : `Early warning signs detected.${sNote}${tNote}${rfNote} Check water levels regularly.`;
  }

  // aman
  const totalSt = stations.length;
  const sNote = totalSt > 0
    ? (isId ? ` Semua ${totalSt} stasiun terkalibrasi dalam batas normal.` : ` All ${totalSt} calibrated stations within normal range.`)
    : "";
  // Mirror the OOD badge gate (isOutlier && WLR < 0.75): when the input is
  // statistically unusual, don't claim "nothing concerning" — that contradicts
  // the visible Anomali chip. Frame it as honest uncertainty instead.
  const oodActive = riskData?.isOutlier && wlr < 0.75;
  const closing = oodActive
    ? (isId
      ? " Data sensor sedikit tidak biasa — verdict aman ini perlu dipantau berkala."
      : " Sensor input is slightly unusual — keep monitoring this 'safe' verdict.")
    : (isId ? " Tidak ada tanda-tanda mengkhawatirkan." : " No concerning signs detected.");
  return isId
    ? `Jakarta saat ini aman dari risiko banjir.${sNote}${closing}`
    : `Jakarta is currently safe from flood risk.${sNote}${closing}`;
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
  if (pct >= 30) return "#f5a623";
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

/* ── Wind direction (8-point compass, localized) ───────── */
export function windDirection(deg, isId) {
  if (deg == null) return "—";
  const id = ["U","TL","T","TG","S","BD","B","BL"];
  const en = ["N","NE","E","SE","S","SW","W","NW"];
  const idx = Math.round(deg / 45) % 8;
  return isId ? id[idx] : en[idx];
}
