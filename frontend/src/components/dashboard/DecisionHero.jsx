import { useApp } from "../../lib/appContext";
import { use3DTilt } from "../../hooks/use3DTilt";
import { buildStatusDesc } from "../../lib/dashboardHelpers";

/* ── DecisionHero — the first thing a citizen sees ─────────────────────────
   Answers "is my area at risk right now?" in one glance: a giant level word,
   a plain-language one-liner, the trend, and — ONLY when stations are in
   Siaga 1/2 — an inline red alert line (pre-attentive encoding). When the
   status is Aman the card stays calm and minimal: no red, no pulsing
   (deliberate emotional design per the FloodGuard paper).
   Reuses .status-hero.level-* so severity backgrounds + light-theme
   overrides keep working.
*/
export default function DecisionHero({ riskData, siaga1Count = 0, siaga2Count = 0 }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const tiltRef = use3DTilt({ maxTilt: 4 });

  const level = riskData?.level ?? "waspada";
  const riskTrend = riskData?.trendState?.risk_trend;
  const snapshotFetchedAt = riskData?.snapshotFetchedAt;

  const cfgMap = {
    aman:    { label: isId ? "Aman"    : "Safe",    color: "var(--safe)" },
    waspada: { label: isId ? "Waspada" : "Watch",   color: "var(--wsp)"  },
    siaga:   { label: isId ? "Siaga"   : "Alert",   color: "var(--s2)"   },
    bahaya:  { label: isId ? "Bahaya!" : "Danger!", color: "var(--s1)"   },
  };
  const cfg = cfgMap[level] ?? cfgMap.waspada;
  const dynamicDesc = buildStatusDesc(riskData, isId);

  let snapTimeStr = null;
  if (snapshotFetchedAt) {
    const wib = new Date(new Date(snapshotFetchedAt).getTime() + 7 * 3_600_000);
    snapTimeStr = `${String(wib.getUTCHours()).padStart(2, "0")}:${String(wib.getUTCMinutes()).padStart(2, "0")}`;
  }

  const trendCfg = riskTrend === "increasing"
    ? { text: isId ? "↑ Risiko Naik" : "↑ Risk Rising", color: "var(--wsp)", bg: "var(--wsp-soft)", border: "var(--wsp-border)" }
    : riskTrend === "decreasing"
    ? { text: isId ? "↓ Risiko Turun" : "↓ Risk Falling", color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)" }
    : { text: isId ? "→ Stabil" : "→ Stable", color: "var(--muted)", bg: "rgba(255,255,255,0.04)", border: "var(--line)" };

  // AlertRibbon folded in: one red line with real station counts, Siaga only.
  const alertLine = siaga1Count > 0
    ? (isId
        ? `SIAGA 1 AKTIF — ${siaga1Count} stasiun melebihi ambang batas. Hubungi BPBD 117.`
        : `ALERT 1 ACTIVE — ${siaga1Count} stations above threshold. Contact BPBD 117.`)
    : siaga2Count > 0
    ? (isId
        ? `Siaga 2 — ${siaga2Count} stasiun mendekati ambang batas. Pantau perkembangan.`
        : `Alert 2 — ${siaga2Count} stations approaching threshold. Monitor updates.`)
    : null;
  const alertColor = siaga1Count > 0 ? "var(--s1)" : "var(--s2)";

  return (
    <div ref={tiltRef} className={`status-hero card-3d fade-in level-${level}`}>
      <div className="status-hero-main card-3d-content">
        <div className="decision-hero-eyebrow" style={{ color: cfg.color }}>
          {isId ? "STATUS JAKARTA" : "JAKARTA STATUS"}
          {snapTimeStr && (
            <span style={{ opacity: 0.65, marginLeft: "0.5rem" }}>
              · {isId ? "Diperbarui" : "Updated"} {snapTimeStr} WIB
            </span>
          )}
        </div>
        <div className="status-hero-level decision-hero-level" style={{ color: cfg.color }}>
          {cfg.label}
        </div>
        <p className="status-hero-desc decision-hero-desc">{dynamicDesc}</p>

        <div className="decision-hero-meta">
          <span
            className="decision-hero-trend"
            style={{ background: trendCfg.bg, border: `1px solid ${trendCfg.border}`, color: trendCfg.color }}
          >
            {trendCfg.text}
          </span>
        </div>

        {alertLine && (
          <div className="decision-hero-alert" style={{ color: alertColor }}>
            <span className="decision-hero-alert-dot" style={{ background: alertColor }} />
            {alertLine}
          </div>
        )}
      </div>
    </div>
  );
}
