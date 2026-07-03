/* ── Status / model section ───────────────────────────────────────────────
   The headline status hero, the stale-data banner, the XGBoost model-output
   card, and the realtime recommendations panel. These translate the raw risk
   data into the plain-language verdict and the call-to-action buttons.
*/
import { useT, useApp } from "../../lib/appContext";
import { use3DTilt } from "../../hooks/use3DTilt";
import { buildStatusDesc } from "../../lib/dashboardHelpers";
import { PhoneGlyph } from "./primitives";

export function RecommendationsPanel({ riskData, stations = [], onNavigate }) {
  const t = useT();
  const tiltRef = use3DTilt({ maxTilt: 6 });
  const { lang } = useApp();
  const isId = lang === "id";

  const rainfall  = riskData?.rainfall ?? 0;
  const riskTrend = riskData?.trendState?.risk_trend;
  const wSummary  = riskData?.wilayahSummary ?? [];
  // Kelurahan-targeted lines come from backend's _kelurahan_targeted_actions
  // (BNPB 2014–2023 history × live wilayah siaga ranks). They're listed first
  // because they answer "where specifically to act", not just "what to do".
  const backendActions = riskData?.recommendedActions ?? [];
  const kelTargeted = backendActions.filter(a => typeof a === "string" && a.toLowerCase().includes("kelurahan"));

  const s1 = [...stations].filter(s => s.ratio >= 1.0).sort((a, b) => b.ratio - a.ratio);
  const s2 = [...stations].filter(s => s.ratio >= 0.75 && s.ratio < 1.0).sort((a, b) => b.ratio - a.ratio);

  const dangerW = [...wSummary]
    .filter(w => ["Siaga 1","Siaga 2","Siaga 3"].includes(w.worst_status))
    .sort((a, b) => ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[b.worst_status] ?? 0) - ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[a.worst_status] ?? 0));
  const topW = dangerW[0];

  const dynActions = [];
  if (s1.length > 0) {
    const st = s1[0];
    dynActions.push(isId
      ? `${st.nama} sudah ${Math.round(st.ratio * 100)}% ambang Siaga 1 (TMA ${st.tinggi_air} cm). Warga bantaran terdekat: siapkan evakuasi segera.`
      : `${st.nama} at ${Math.round(st.ratio * 100)}% of Alert-1 threshold (${st.tinggi_air} cm). Nearby residents: prepare immediate evacuation.`
    );
  }
  if (s2.length > 0) {
    const st = s2[0];
    dynActions.push(isId
      ? `${st.nama} Siaga 2 (${Math.round(st.ratio * 100)}%, TMA ${st.tinggi_air} cm) — pantau setiap 15 mnt, siapkan tas darurat.`
      : `${st.nama} at Alert 2 (${Math.round(st.ratio * 100)}%, ${st.tinggi_air} cm) — monitor every 15 min, prepare emergency bag.`
    );
  }
  if (topW) {
    const sensorsNote = topW.siaga1_count > 0
      ? (isId ? `${topW.siaga1_count} sensor Siaga 1 aktif` : `${topW.siaga1_count} active Alert-1 sensors`)
      : (isId ? `${topW.siaga2_count} sensor Siaga 2` : `${topW.siaga2_count} Alert-2 sensors`);
    dynActions.push(isId
      ? `${topW.wilayah} — ${topW.worst_status}, ${sensorsNote}. Kurangi aktivitas di luar ruangan di wilayah ini.`
      : `${topW.wilayah} — ${topW.worst_status}, ${sensorsNote}. Reduce outdoor activities in this district.`
    );
  }
  if (rainfall > 20) {
    dynActions.push(isId
      ? `Curah hujan ${Math.round(rainfall)} mm/jam — potensi genangan cepat di titik rendah. Hindari bantaran kali dan underpass.`
      : `Rainfall ${Math.round(rainfall)} mm/h — rapid pooling risk at low points. Avoid riverbanks and underpasses.`
    );
  } else if (rainfall > 5) {
    dynActions.push(isId
      ? `Hujan ringan ${Math.round(rainfall)} mm/jam — pantau apakah intensitas meningkat dalam 30 menit ke depan.`
      : `Light rain ${Math.round(rainfall)} mm/h — monitor if intensity rises over the next 30 minutes.`
    );
  }
  if (riskTrend === "increasing" && dynActions.length < 3) {
    dynActions.push(isId
      ? `Tren risiko sedang naik — persiapkan evakuasi mandiri dan koordinasi dengan RT/RW setempat.`
      : `Risk trend rising — prepare self-evacuation plan and coordinate with local RT/RW.`
    );
  }
  if (dynActions.length === 0) {
    dynActions.push(isId
      ? "Kondisi saat ini terpantau normal. Tetap pantau sensor tiap 15 menit selama musim hujan."
      : "Current conditions appear normal. Keep monitoring sensors every 15 min during rain season."
    );
  }
  // Prepend backend kelurahan-targeted lines so location-specific guidance lands first
  if (kelTargeted.length > 0) {
    dynActions.unshift(...kelTargeted);
  }

  // ── Functional buttons ────────────────────────────────────
  const goEvac = () => { if (onNavigate) { window.scrollTo(0, 0); onNavigate("alert"); } };
  const callBPBD = () => { window.location.href = "tel:117"; };
  const scrollSensors = () => {
    document.getElementById("station-panel-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const buttons = [];
  if (s1.length > 0) {
    const nm = s1[0].nama.split(/[\s/]/)[0];
    buttons.push({
      label: isId ? `Evakuasi — area ${nm}` : `Evacuate — ${nm} area`,
      primary: true, icon: "!",
      onClick: goEvac,
      title: isId ? "Buka halaman rute evakuasi" : "Open evacuation route page",
    });
  } else {
    buttons.push({
      label: isId ? "Pantau kondisi sensor" : "Monitor sensor conditions",
      primary: false, icon: "◉",
      onClick: scrollSensors,
      title: isId ? "Scroll ke tabel sensor" : "Scroll to sensor table",
    });
  }
  buttons.push({
    label: topW
      ? (isId ? `Rute evakuasi — ${topW.wilayah.replace("Jakarta ", "")}` : `Evacuation route — ${topW.wilayah.replace("Jakarta ", "")}`)
      : (isId ? "Cek rute evakuasi" : "Check evacuation routes"),
    primary: false, icon: "↗",
    onClick: goEvac,
    title: isId ? "Buka peta rute evakuasi" : "Open evacuation map",
  });
  buttons.push({
    label: isId ? "BPBD Jakarta — 117" : "BPBD Emergency: 117",
    primary: false, icon: <PhoneGlyph size={14} />,
    onClick: callBPBD,
    title: isId ? "Telepon BPBD sekarang" : "Call BPBD now",
    isCall: true,
  });

  return (
    <div ref={tiltRef} className="panel panel-body card-3d">
      <div className="card-3d-content">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
          <p className="panel-title" style={{ marginBottom: 0 }}>{t("rec.title")}</p>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em" }}>● real</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.75rem" }}>
          {dynActions.map((action, i) => (
            <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--cyan)", flexShrink: 0, marginTop: "0.15rem" }}>›</span>
              <p style={{ fontSize: "0.75rem", color: "var(--muted)", lineHeight: 1.55, margin: 0 }}>{action}</p>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {buttons.map((a, i) => (
            <button
              key={i}
              className={`action-btn${a.primary ? " primary" : ""}${a.isCall ? " action-btn-call" : ""}`}
              onClick={a.onClick}
              title={a.title}
            >
              <span className="action-icon">{a.icon}</span>
              {a.label}
            </button>
          ))}
        </div>
        <p style={{ marginTop: "0.625rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)" }}>
          ● {isId ? "Rekomendasi dari sensor DSDADKI + BMKG realtime" : "Based on realtime DSDADKI sensors + BMKG data"}
        </p>
      </div>
    </div>
  );
}

/* ── Model Output Card — realtime ML analysis with signal chips ─────────── */
export function ModelOutputCard({ riskData, score }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!riskData?.interpretation) return null;

  const rainfall   = riskData.rainfall ?? 0;
  const wlr        = riskData.waterLevelRatio ?? 0;
  const riskTrend  = riskData.trendState?.risk_trend;
  const level      = riskData.level ?? "waspada";

  let snapTimeStr = null;
  if (riskData.snapshotFetchedAt) {
    const wib = new Date(new Date(riskData.snapshotFetchedAt).getTime() + 7 * 3_600_000);
    snapTimeStr = `${String(wib.getUTCHours()).padStart(2,"0")}:${String(wib.getUTCMinutes()).padStart(2,"0")}`;
  }

  const trendText = riskTrend === "increasing"
    ? (isId ? "↑ Naik" : "↑ Rising")
    : riskTrend === "decreasing"
    ? (isId ? "↓ Turun" : "↓ Falling")
    : (isId ? "→ Stabil" : "→ Stable");
  const trendColor = riskTrend === "increasing" ? "var(--wsp)" : riskTrend === "decreasing" ? "var(--safe)" : "var(--muted)";

  const scoreColor = score >= 70 ? "var(--s1)" : score >= 45 ? "var(--wsp)" : "var(--safe)";
  const levelColor = { aman: "var(--safe)", waspada: "var(--wsp)", siaga: "var(--s2)", bahaya: "var(--s1)" }[level] ?? "var(--wsp)";
  const levelLabel = { aman: isId ? "Aman" : "Safe", waspada: isId ? "Waspada" : "Watch",
    siaga: isId ? "Siaga" : "Alert", bahaya: isId ? "Bahaya" : "Danger" }[level] ?? "—";

  return (
    <div className="model-output-card fade-in">
      {/* Header row */}
      <div className="model-output-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <div className="model-output-icon">⬡</div>
          <div>
            <div className="model-output-title">
              {isId ? "ANALISIS MODEL" : "MODEL ANALYSIS"}
            </div>
            <div className="model-output-sub">
              XGBoost · {isId ? "17 fitur · update 15 mnt" : "17 features · 15 min update"}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "2px" }}>
          {snapTimeStr && (
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)" }}>
              {snapTimeStr} WIB
            </span>
          )}
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em" }}>● real</span>
        </div>
      </div>

      {/* Interpretation text */}
      <p className="model-output-text">{riskData.interpretation}</p>

      {/* Signal chips — key inputs the model is reading */}
      <div className="model-signal-chips">
        <div className="model-signal-chip">
          <span>{isId ? "Skor" : "Score"}</span>
          <strong style={{ color: scoreColor }}>{score}</strong>
        </div>
        <div className="model-signal-chip">
          <span>{isId ? "Status" : "Status"}</span>
          <strong style={{ color: levelColor }}>{levelLabel}</strong>
        </div>
        {wlr > 0 && (
          <div className="model-signal-chip">
            <span>{isId ? "Muka Air" : "Water Lvl"}</span>
            <strong style={{ color: wlr >= 0.75 ? "var(--wsp)" : "var(--text)" }}>{Math.round(wlr * 100)}%</strong>
          </div>
        )}
        {rainfall > 0 && (
          <div className="model-signal-chip">
            <span>{isId ? "Hujan" : "Rain"}</span>
            <strong style={{ color: "var(--cyan)" }}>{Math.round(rainfall)} mm/j</strong>
          </div>
        )}
        {riskTrend && (
          <div className="model-signal-chip">
            <span>{isId ? "Tren" : "Trend"}</span>
            <strong style={{ color: trendColor }}>{trendText}</strong>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Stale data warning — tampil kalau snapshot > 30 menit ─────────────── */
export function StaleDataBanner({ snapshotFetchedAt, onRefresh, refreshing }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!snapshotFetchedAt) return null;
  const ageMin = Math.round((Date.now() - new Date(snapshotFetchedAt).getTime()) / 60000);
  if (ageMin < 30) return null;

  const ageLabel = ageMin >= 60
    ? (isId ? `${Math.floor(ageMin / 60)} jam ${ageMin % 60} mnt` : `${Math.floor(ageMin / 60)}h ${ageMin % 60}m`)
    : (isId ? `${ageMin} menit` : `${ageMin} min`);

  return (
    <div style={{
      background: "rgba(245,166,35,0.08)", border: "1px solid rgba(245,166,35,0.30)",
      borderRadius: "10px", padding: "0.625rem 1rem",
      display: "flex", alignItems: "center", gap: "0.75rem",
      fontSize: "0.78rem", color: "var(--wsp)",
    }}>
      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.95rem", fontWeight: 800, flexShrink: 0, lineHeight: 1 }}>!</span>
      <span style={{ flex: 1, lineHeight: 1.5 }}>
        {isId
          ? `Sensor DSDADKI belum mengirim data baru sejak ${ageLabel} lalu. Sistem refresh kami tetap berjalan tiap 15 menit — yang stale adalah pengukuran di hulu, bukan koneksi kami.`
          : `DSDADKI sensors haven't pushed new readings for ${ageLabel}. Our refresh job keeps running every 15 min — the upstream measurements are stale, not our connection.`}
      </span>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing}
          style={{
            flexShrink: 0, background: "rgba(245,166,35,0.15)",
            border: "1px solid rgba(245,166,35,0.40)", borderRadius: "8px",
            padding: "0.35rem 0.75rem", color: "var(--wsp)",
            fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem",
            fontWeight: 700, cursor: refreshing ? "wait" : "pointer",
            letterSpacing: "0.04em", opacity: refreshing ? 0.5 : 1,
          }}
        >
          {refreshing ? "…" : (isId ? "↻ Refresh" : "↻ Refresh")}
        </button>
      )}
    </div>
  );
}

/* ── Status Hero — the FIRST thing user sees: "apakah ada risiko banjir?" ── */
export function StatusHero({ riskData }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const tiltRef = use3DTilt({ maxTilt: 5 });

  const level    = riskData?.level ?? "waspada";
  const score    = riskData?.riskScore ?? 0;
  const wlr      = riskData?.waterLevelRatio;
  const rainfall = riskData?.rainfall ?? 0;
  const riskTrend = riskData?.trendState?.risk_trend;
  const snapshotFetchedAt = riskData?.snapshotFetchedAt;

  const cfgMap = {
    aman:    { label: isId ? "Aman"     : "Safe",    color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)" },
    waspada: { label: isId ? "Waspada"  : "Watch",   color: "var(--wsp)",  bg: "var(--wsp-soft)",  border: "var(--wsp-border)"  },
    siaga:   { label: isId ? "Siaga"    : "Alert",   color: "var(--s2)",   bg: "var(--s2-soft)",   border: "var(--s2-border)"   },
    bahaya:  { label: isId ? "Bahaya!"  : "Danger!", color: "var(--s1)",   bg: "var(--s1-soft)",   border: "var(--s1-border)"   },
  };
  const cfg = cfgMap[level] ?? cfgMap.waspada;
  // Dynamic description built from realtime sensor data — not hand-written strings
  const dynamicDesc = buildStatusDesc(riskData, isId);

  let snapTimeStr = null;
  if (snapshotFetchedAt) {
    const wib = new Date(new Date(snapshotFetchedAt).getTime() + 7 * 60 * 60 * 1000);
    snapTimeStr = `${String(wib.getUTCHours()).padStart(2,"0")}:${String(wib.getUTCMinutes()).padStart(2,"0")}`;
  }

  // Trend badge — displayed as a pill so users immediately understand direction
  const trendCfg = riskTrend === "increasing"
    ? { text: isId ? "↑ Risiko Naik" : "↑ Risk Rising", color: "var(--wsp)", bg: "var(--wsp-soft)", border: "var(--wsp-border)",
        hint: isId ? "Sensor menunjukkan kondisi memburuk" : "Sensors show deteriorating conditions" }
    : riskTrend === "decreasing"
    ? { text: isId ? "↓ Risiko Turun" : "↓ Risk Falling", color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)",
        hint: isId ? "Kondisi mulai membaik" : "Conditions improving" }
    : { text: isId ? "→ Stabil" : "→ Stable", color: "var(--muted)", bg: "rgba(255,255,255,0.04)", border: "var(--line)",
        hint: isId ? "Tidak ada perubahan signifikan" : "No significant change" };

  // Mini sparkline from recent_probabilities — shows risk score over last ~45 min
  const probs = riskData?.trendState?.recent_probabilities ?? [];
  const sparkW = Math.max(probs.length, 2) * 22;
  const sparkH = 32;
  const sparkY = (p) => sparkH - 4 - Math.round(Math.min(p, 1) * (sparkH - 8));

  return (
    <div ref={tiltRef} className={`status-hero card-3d fade-in level-${level}`}>
      <div className="status-hero-main card-3d-content">
        <div style={{
          fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem",
          color: cfg.color, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.25rem",
        }}>
          {isId ? "STATUS JAKARTA" : "JAKARTA STATUS"}
          {snapTimeStr && <span style={{ opacity: 0.65, marginLeft: "0.5rem" }}>· {snapTimeStr} WIB</span>}
        </div>
        <div className="status-hero-level" style={{ color: cfg.color }}>{cfg.label}</div>
        <p className="status-hero-desc">{dynamicDesc}</p>
      </div>
      <div className="status-hero-stats card-3d-content">
        {wlr != null && (
          <div className="hero-stat">
            <div className="hero-stat-value" style={{ color: cfg.color }}>{Math.round(wlr * 100)}%</div>
            <div className="hero-stat-label">{isId ? "Ketinggian Air" : "Water Level"}</div>
          </div>
        )}
        <div className="hero-stat">
          <div className="hero-stat-value" style={{ color: cfg.color }}>{score}</div>
          <div className="hero-stat-label">{isId ? "Skor Risiko" : "Risk Score"}</div>
        </div>
        {/* Trend pill badge — more user-friendly than raw arrow text */}
        <div className="hero-stat">
          <div style={{
            display: "inline-flex", alignItems: "center",
            background: trendCfg.bg, border: `1px solid ${trendCfg.border}`,
            borderRadius: "999px", padding: "0.3rem 0.75rem",
            fontFamily: "'JetBrains Mono',monospace",
            fontSize: "0.72rem", fontWeight: 700, color: trendCfg.color,
            letterSpacing: "0.03em", whiteSpace: "nowrap",
          }}>
            {trendCfg.text}
          </div>
          <div className="hero-stat-label" style={{ marginTop: "0.3rem" }}>{trendCfg.hint}</div>
        </div>
        {rainfall > 0 && (
          <div className="hero-stat">
            <div className="hero-stat-value" style={{ color: "var(--wsp)" }}>{Math.round(rainfall)} mm/j</div>
            <div className="hero-stat-label">{isId ? "Curah Hujan" : "Rainfall"}</div>
          </div>
        )}
        {probs.length >= 2 && (
          <div className="hero-stat secondary">
            <svg width={sparkW} height={sparkH} style={{ display: "block" }}>
              {probs.map((p, i, arr) => i === 0 ? null : (
                <line key={i}
                  x1={(i - 1) * 22 + 11} y1={sparkY(arr[i - 1])}
                  x2={i * 22 + 11}       y2={sparkY(p)}
                  stroke={cfg.color} strokeWidth="1.5" strokeLinecap="round"
                />
              ))}
              {probs.map((p, i) => (
                <circle key={i}
                  cx={i * 22 + 11} cy={sparkY(p)}
                  r={i === probs.length - 1 ? 3 : 2}
                  fill={cfg.color}
                />
              ))}
            </svg>
            <div className="hero-stat-label">{isId ? "Skor ~45 mnt" : "Score ~45 min"}</div>
          </div>
        )}
      </div>
    </div>
  );
}
