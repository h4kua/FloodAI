import { useApp, useT } from "../../lib/appContext";
import {
  buildStatusDesc, formatDataTime, dataAgeMinutes, trendDisplay, STALE_STATUS_MIN,
  postClass, byPostSeverity, cleanStationName,
} from "../../lib/dashboardHelpers";

const GAUGE_LEVELS = [["s1", "SIAGA_1"], ["s2", "SIAGA_2"], ["wsp", "WASPADA"], ["ok", "NORMAL"]];

/* ── Post gauge — every monitoring post as one coloured segment ───────────
   Worst first, so the eye lands on trouble; the legend gives exact counts.
   Each post's own DSDA band, as in the post list and the map (postClass).
*/
function PostGauge({ stations, isId }) {
  const t = useT();
  if (!stations.length) return null;
  const sorted = [...stations].sort(byPostSeverity);
  const counts = { s1: 0, s2: 0, wsp: 0, ok: 0 };
  sorted.forEach((s) => { counts[postClass(s)] += 1; });
  return (
    <aside className="hero-gauge" aria-label={isId ? "Ringkasan pos pantau air" : "Water-level post summary"}>
      <div className="hero-gauge-head">
        <span>{isId ? "Pos pantau air" : "Water-level posts"}</span>
        <strong>{stations.length}</strong>
      </div>
      <div className="hero-gauge-bar" aria-hidden="true">
        {sorted.map((s, i) => (
          <i key={i} className={`seg-${postClass(s)}`} title={cleanStationName(s.nama)} />
        ))}
      </div>
      <ul className="hero-gauge-legend">
        {GAUGE_LEVELS.map(([cls, key]) => (
          <li key={cls} className={counts[cls] ? "" : "is-zero"}>
            <i className={`seg-${cls}`} />
            <span>{t(`risk.${key}`)}</span>
            <b>{counts[cls]}</b>
          </li>
        ))}
      </ul>
    </aside>
  );
}

/* What a resident should do at each level, in plain words (BPBD DKI preparedness advice). */
const TODO = {
  aman: {
    id: ["Beraktivitas seperti biasa.", "Buka lagi situs ini saat hujan deras turun.", "Kenali tempat aman terdekat di halaman Rute Aman."],
    en: ["Go about your day as usual.", "Check again when heavy rain starts.", "Know your nearest safe place on the Safe Route page."],
  },
  waspada: {
    id: ["Cek situs ini atau info BPBD tiap beberapa jam.", "Kalau sempat, simpan dokumen penting di tempat yang tinggi.", "Hindari memarkir kendaraan dekat sungai atau saluran air."],
    en: ["Check this site or BPBD news every few hours.", "If you have a moment, put important papers somewhere high.", "Avoid parking near rivers or drains."],
  },
  siaga: {
    id: ["Siapkan tas siaga: dokumen, obat, senter, power bank, air minum.", "Pindahkan barang berharga dan kendaraan ke tempat yang lebih tinggi.", "Cek jalan yang menghindari banjir di halaman Rute Aman."],
    en: ["Pack a go-bag: papers, medicine, torch, power bank, water.", "Move valuables and vehicles to higher ground.", "Check a route around flood areas on the Safe Route page."],
  },
  bahaya: {
    id: ["Segera mengungsi bila air mulai masuk atau petugas meminta.", "Matikan listrik dari meteran sebelum air masuk rumah.", "Jangan menyeberangi arus banjir, juga dengan kendaraan. Darurat: 112."],
    en: ["Leave right away if water comes in or officials ask you to.", "Switch off the power at the meter before water gets in.", "Never cross flowing floodwater, on foot or by vehicle. Emergency: 112."],
  },
};

/* ── DecisionHero — the first thing a citizen sees ─────────────────────────
   Answers "is my area at risk right now?" in one glance: a giant level word,
   a plain-language one-liner, the trend, and — ONLY when stations are in
   Siaga 1/2 — an inline red alert line (pre-attentive encoding). When the
   status is Aman the card stays calm and minimal: no red, no pulsing
   (deliberate emotional design per the FloodGuard paper).
   The card itself is a solid signage block coloured by .status-hero.level-*;
   text inherits the block's ink colour.
*/
export default function DecisionHero({ riskData, siaga1Count = 0, siaga2Count = 0 }) {
  const { lang } = useApp();
  const isId = lang === "id";

  const level = riskData?.level ?? "waspada";
  const riskTrend = riskData?.trendState?.risk_trend;
  const snapshotFetchedAt = riskData?.snapshotFetchedAt;

  const cfgMap = {
    aman:    { label: isId ? "Aman"    : "Safe" },
    waspada: { label: isId ? "Waspada" : "Watch" },
    siaga:   { label: isId ? "Siaga"   : "Alert" },
    bahaya:  { label: isId ? "Bahaya!" : "Danger!" },
    unknown: { label: isId ? "Belum diketahui" : "Unknown" },
  };
  const dynamicDesc = buildStatusDesc(riskData, isId);

  // Old data must not look like "right now": grey the status, show the date.
  const isStale = (dataAgeMinutes(snapshotFetchedAt) ?? 0) >= STALE_STATUS_MIN;
  const cfg = cfgMap[level] ?? cfgMap.waspada;
  const snapTimeStr = formatDataTime(snapshotFetchedAt, isId);

  const trendCfg = trendDisplay(riskTrend, level, isId);

  // Rainfall (OpenWeather, mm/h) — the one number from the old glance chips
  // that the hero didn't already show.
  const rain = riskData?.rainfall;
  const rainText = rain == null ? null
    : rain >= 20 ? (isId ? `Hujan deras · ${Math.round(rain)} mm/jam` : `Heavy rain · ${Math.round(rain)} mm/h`)
    : rain >= 5  ? (isId ? `Hujan sedang · ${Math.round(rain)} mm/jam` : `Moderate rain · ${Math.round(rain)} mm/h`)
    : rain > 0   ? (isId ? `Hujan ringan · ${rain.toFixed(1).replace(".", ",")} mm/jam` : `Light rain · ${rain.toFixed(1)} mm/h`)
    : (isId ? "Tidak hujan" : "No rain");

  // AlertRibbon folded in: one red line with real station counts, Siaga only.
  const alertLine = siaga1Count > 0
    ? (isId
        ? `${siaga1Count} pos pantau air sudah di Siaga 1, batas tertinggi. Ikuti info BPBD; butuh bantuan: BPBD 117.`
        : `${siaga1Count === 1 ? "1 water-level post is" : `${siaga1Count} water-level posts are`} at Alert 1, the highest level. Follow BPBD updates; need help: BPBD 117.`)
    : siaga2Count > 0
    ? (isId
        ? `${siaga2Count} pos pantau air sedang di Siaga 2: air agak tinggi, belum di batas tertinggi.`
        : `${siaga2Count === 1 ? "1 water-level post is" : `${siaga2Count} water-level posts are`} at Alert 2: water is fairly high, not yet at the highest level.`)
    : null;

  return (
    <div className={`status-hero fade-in level-${level}${isStale ? " is-stale" : ""}`}>
      <div className="status-hero-main">
        <div className="decision-hero-eyebrow">
          {isStale
            ? (isId ? "Status terakhir yang diketahui" : "Last known status")
            : (isId ? "Status Jakarta saat ini" : "Jakarta right now")}
          {snapTimeStr && (
            <span className="decision-hero-time">
              {isId ? `data pukul ${snapTimeStr}` : `data from ${snapTimeStr}`}
            </span>
          )}
        </div>
        <div className="status-hero-level decision-hero-level">
          {cfg.label}
        </div>
        <p className="status-hero-desc decision-hero-desc">{dynamicDesc}</p>

        {/* Trend + rain from old data say nothing about now — hide them when stale */}
        {!isStale && (trendCfg || rainText) && (
          <p className="decision-hero-meta">
            {[trendCfg && (isId ? `Tren ${trendCfg.text.replace(/^[^A-Za-z]+/, "").toLowerCase()}.` : `Trend: ${trendCfg.text.replace(/^[^A-Za-z]+/, "").toLowerCase()}.`),
              rainText && (isId ? `${rainText.replace(/ · (.*)$/, " ($1)")} di pusat kota.` : `${rainText.replace(/ · (.*)$/, " ($1)")} in central Jakarta.`)]
              .filter(Boolean).join(" ")}
          </p>
        )}

        {!isStale && TODO[level] && (
          <div className="decision-hero-todo">
            <p className="decision-hero-todo-title">{isId ? "Yang bisa Anda lakukan" : "What you can do"}</p>
            <ul>{TODO[level][isId ? "id" : "en"].map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        )}

        {alertLine && (
          <div className="decision-hero-alert">
            <span className="decision-hero-alert-dot" />
            {alertLine}
          </div>
        )}
      </div>
      <PostGauge stations={riskData?.stations ?? []} isId={isId} />
    </div>
  );
}
