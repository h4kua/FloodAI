/* ── Action derivation — pure, UI-agnostic ─────────────────────────────────
   Extracted verbatim from the former RecommendationsPanel so the citizen-first
   ActionCard and any future renderer share one source of truth. Returns the
   ranked action strings plus the raw signals (s1/s2 stations, worst wilayah)
   that CTA buttons are built from.
*/

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
      ? `${st.nama} sudah ${Math.round(st.ratio * 100)}% ambang Siaga 1 (TMA ${st.tinggi_air} cm). Warga bantaran terdekat: siapkan evakuasi segera.`
      : `${st.nama} at ${Math.round(st.ratio * 100)}% of Alert-1 threshold (${st.tinggi_air} cm). Nearby residents: prepare immediate evacuation.`
    );
  }
  if (s2.length > 0) {
    const st = s2[0];
    actions.push(isId
      ? `${st.nama} Siaga 2 (${Math.round(st.ratio * 100)}%, TMA ${st.tinggi_air} cm) — pantau setiap 15 mnt, siapkan tas darurat.`
      : `${st.nama} at Alert 2 (${Math.round(st.ratio * 100)}%, ${st.tinggi_air} cm) — monitor every 15 min, prepare emergency bag.`
    );
  }
  if (topW) {
    const sensorsNote = topW.siaga1_count > 0
      ? (isId ? `${topW.siaga1_count} sensor Siaga 1 aktif` : `${topW.siaga1_count} active Alert-1 sensors`)
      : (isId ? `${topW.siaga2_count} sensor Siaga 2` : `${topW.siaga2_count} Alert-2 sensors`);
    actions.push(isId
      ? `${topW.wilayah} — ${topW.worst_status}, ${sensorsNote}. Kurangi aktivitas di luar ruangan di wilayah ini.`
      : `${topW.wilayah} — ${topW.worst_status}, ${sensorsNote}. Reduce outdoor activities in this district.`
    );
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
  if (riskTrend === "increasing" && actions.length < 3) {
    actions.push(isId
      ? `Tren risiko sedang naik — persiapkan evakuasi mandiri dan koordinasi dengan RT/RW setempat.`
      : `Risk trend rising — prepare self-evacuation plan and coordinate with local RT/RW.`
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
