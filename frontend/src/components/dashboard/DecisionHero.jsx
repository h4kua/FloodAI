import { useApp } from "../../lib/appContext";
import {
  buildStatusDesc, formatDataTime, dataAgeMinutes, trendDisplay, STALE_STATUS_MIN,
} from "../../lib/dashboardHelpers";

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

  const level = riskData?.level ?? "waspada";
  const riskTrend = riskData?.trendState?.risk_trend;
  const snapshotFetchedAt = riskData?.snapshotFetchedAt;

  const cfgMap = {
    aman:    { label: isId ? "Aman"    : "Safe",    color: "var(--safe)" },
    waspada: { label: isId ? "Waspada" : "Watch",   color: "var(--wsp)"  },
    siaga:   { label: isId ? "Siaga"   : "Alert",   color: "var(--s2)"   },
    bahaya:  { label: isId ? "Bahaya!" : "Danger!", color: "var(--s1)"   },
  };
  const dynamicDesc = buildStatusDesc(riskData, isId);

  // Old data must not look like "right now": grey the status, show the date.
  const isStale = (dataAgeMinutes(snapshotFetchedAt) ?? 0) >= STALE_STATUS_MIN;
  const cfg = isStale
    ? { ...(cfgMap[level] ?? cfgMap.waspada), color: "var(--muted)" }
    : (cfgMap[level] ?? cfgMap.waspada);
  const snapTimeStr = formatDataTime(snapshotFetchedAt, isId);

  const trendCfg = trendDisplay(riskTrend, level, isId);

  // AlertRibbon folded in: one red line with real station counts, Siaga only.
  const alertLine = siaga1Count > 0
    ? (isId
        ? `Siaga 1 — ${siaga1Count} pos pantau melewati batas aman. Hubungi BPBD 117.`
        : `Alert 1 — ${siaga1Count} posts above the safe limit. Contact BPBD 117.`)
    : siaga2Count > 0
    ? (isId
        ? `Siaga 2 — ${siaga2Count} pos pantau mendekati batas aman. Pantau terus.`
        : `Alert 2 — ${siaga2Count} posts nearing the safe limit. Keep watching.`)
    : null;
  const alertColor = siaga1Count > 0 ? "var(--s1)" : "var(--s2)";

  return (
    <div className={`status-hero fade-in level-${level}${isStale ? " is-stale" : ""}`}>
      <div className="status-hero-main">
        <div className="decision-hero-eyebrow" style={{ color: cfg.color }}>
          {isStale
            ? (isId ? "Status terakhir yang diketahui" : "Last known status")
            : (isId ? "Status Jakarta saat ini" : "Jakarta right now")}
          {snapTimeStr && (
            <span style={{ color: "var(--muted)", marginLeft: "0.5rem", fontWeight: 500 }}>
              · {isId ? "data" : "data from"} {snapTimeStr}
            </span>
          )}
        </div>
        <div className="status-hero-level decision-hero-level" style={{ color: cfg.color }}>
          {cfg.label}
        </div>
        <p className="status-hero-desc decision-hero-desc">{dynamicDesc}</p>

        {/* A trend from old data says nothing about now — hide it when stale */}
        {trendCfg && !isStale && (
          <div className="decision-hero-meta">
            <span
              className="decision-hero-trend"
              style={{ background: trendCfg.bg, border: `1px solid ${trendCfg.border}`, color: trendCfg.color }}
            >
              {trendCfg.text}
            </span>
          </div>
        )}

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
