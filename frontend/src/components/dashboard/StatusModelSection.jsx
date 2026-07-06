/* ── Status / model section ───────────────────────────────────────────────
   The stale-data banner and the XGBoost model-output card. (The old
   StatusHero and RecommendationsPanel were retired by the citizen-first
   rebuild — DecisionHero + ActionCard replaced them; the action-derivation
   logic lives on in lib/recommendations.js.)
*/
import { useApp } from "../../lib/appContext";

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

