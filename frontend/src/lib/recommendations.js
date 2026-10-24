/* ── Action derivation — pure, UI-agnostic ─────────────────────────────────
   Extracted verbatim from the former RecommendationsPanel so the citizen-first
   ActionCard and any future renderer share one source of truth. Returns the
   ranked action strings plus the raw signals (s1/s2 stations, worst wilayah)
   that CTA buttons are built from.
*/

import { dataAgeMinutes, STALE_STATUS_MIN, cleanStationName } from "./dashboardHelpers";

const WORST_RANK = { "Siaga 1": 3, "Siaga 2": 2, "Siaga 3": 1 };

export function deriveActions(riskData, stations = [], isId = true) {
  const rainfall  = riskData?.rainfall ?? 0;
  const riskTrend = riskData?.trendState?.risk_trend;
  const wSummary  = riskData?.wilayahSummary ?? [];
  // Kelurahan-targeted lines come from backend's _kelurahan_targeted_actions
  // (BNPB 2014–2023 history × live wilayah siaga ranks). They're listed first
  // because they answer "where specifically to act", not just "what to do".
  const backendActions = riskData?.recommendedActions ?? [];
  const kelTargeted = backendActions.filter(
    (a) => typeof a === "string" && a.toLowerCase().includes("kelurahan")
  );

  const s1 = [...stations].filter((s) => s.ratio >= 1.0).sort((a, b) => b.ratio - a.ratio);
  const s2 = [...stations].filter((s) => s.ratio >= 0.75 && s.ratio < 1.0).sort((a, b) => b.ratio - a.ratio);

  const dangerW = [...wSummary]
    .filter((w) => ["Siaga 1", "Siaga 2", "Siaga 3"].includes(w.worst_status))
    .sort((a, b) => (WORST_RANK[b.worst_status] ?? 0) - (WORST_RANK[a.worst_status] ?? 0));
  const topW = dangerW[0];

  const actions = [];
  if (s1.length > 0) {
    const st = s1[0];
    actions.push(isId
      ? `Air di ${cleanStationName(st.nama)} sudah ${Math.round(st.ratio * 100)}% dari batas Siaga 1 (${st.tinggi_air} cm). Warga bantaran terdekat: siapkan evakuasi sekarang.`
      : `Water at ${cleanStationName(st.nama)} is ${Math.round(st.ratio * 100)}% of the Alert 1 limit (${st.tinggi_air} cm). Riverbank residents nearby: get ready to evacuate now.`
    );
  }
  if (s2.length > 0) {
    const st = s2[0];
    actions.push(isId
      ? `${cleanStationName(st.nama)} berstatus Siaga 2 (${Math.round(st.ratio * 100)}% dari batas, ${st.tinggi_air} cm). Cek lagi tiap 15 menit dan siapkan tas darurat.`
      : `${cleanStationName(st.nama)} is at Alert 2 (${Math.round(st.ratio * 100)}% of the limit, ${st.tinggi_air} cm). Check again every 15 minutes and pack an emergency bag.`
    );
  }
  // Wilayah line uses the app's own words: DSDA "Siaga 3" is shown as Waspada.
  if (topW) {
    const line = topW.siaga1_count > 0
      ? (isId
          ? `${topW.wilayah}: ${topW.siaga1_count} pos pantau sudah Siaga 1. Kurangi aktivitas di luar ruangan di wilayah ini.`
          : `${topW.wilayah}: ${topW.siaga1_count} post(s) at Alert 1. Limit time outdoors in this area.`)
      : topW.siaga2_count > 0
      ? (isId
          ? `${topW.wilayah}: ${topW.siaga2_count} pos pantau Siaga 2, air mendekati batas. Jauhi bantaran kali.`
          : `${topW.wilayah}: ${topW.siaga2_count} post(s) at Alert 2, water nearing the limit. Stay away from riverbanks.`)
      : (isId
          ? `${topW.wilayah}: air di beberapa pos mulai naik (Waspada). Belum perlu mengungsi, tapi jauhi bantaran kali.`
          : `${topW.wilayah}: water is rising at some posts (Watch). No need to evacuate, but stay away from riverbanks.`);
    actions.push(line);
  }
  if (rainfall > 20) {
    actions.push(isId
      ? `Curah hujan ${Math.round(rainfall)} mm/jam — potensi genangan cepat di titik rendah. Hindari bantaran kali dan underpass.`
      : `Rainfall ${Math.round(rainfall)} mm/h — rapid pooling risk at low points. Avoid riverbanks and underpasses.`
    );
  } else if (rainfall > 5) {
    actions.push(isId
      ? `Hujan ringan ${Math.round(rainfall)} mm/jam — pantau apakah intensitas meningkat dalam 30 menit ke depan.`
      : `Light rain ${Math.round(rainfall)} mm/h — monitor if intensity rises over the next 30 minutes.`
    );
  }
  // The trend advice scales with the status, so a rising trend under "Aman"
  // never tells people to evacuate while the headline says they're safe.
  // A trend from stale data says nothing about now, so it gives no advice.
  const isStale = (dataAgeMinutes(riskData?.snapshotFetchedAt) ?? 0) >= STALE_STATUS_MIN;
  if (riskTrend === "increasing" && !isStale && actions.length < 3) {
    const level = riskData?.level ?? "waspada";
    actions.push(
      level === "aman"
        ? (isId
            ? "Risiko sedikit naik, tapi masih aman. Cek lagi aplikasi ini beberapa jam ke depan."
            : "Risk is slightly up but still safe. Check back in a few hours.")
        : level === "waspada"
        ? (isId
            ? "Risiko sedang naik — siapkan tas darurat dan rencana mengungsi bila diperlukan."
            : "Risk is rising — pack an emergency bag and plan where you'd go if needed.")
        : (isId
            ? "Risiko sedang naik — persiapkan evakuasi mandiri dan koordinasi dengan RT/RW setempat."
            : "Risk is rising — prepare to evacuate and coordinate with your local RT/RW.")
    );
  }
  if (actions.length === 0 && riskData?.level === "unknown") {
    actions.push(isId
      ? "Status belum bisa dinilai karena data belum cukup. Ikuti informasi resmi BPBD DKI Jakarta dan BMKG."
      : "The status can't be judged yet because data is missing. Follow official updates from BPBD DKI Jakarta and BMKG."
    );
  }
  if (actions.length === 0) {
    actions.push(isId
      ? "Kondisi saat ini terpantau normal. Tetap pantau sensor tiap 15 menit selama musim hujan."
      : "Current conditions appear normal. Keep monitoring sensors every 15 min during rain season."
    );
  }
  // Prepend backend kelurahan-targeted lines so location-specific guidance lands first
  if (kelTargeted.length > 0) {
    actions.unshift(...kelTargeted);
  }

  return { actions, s1, s2, topW };
}
