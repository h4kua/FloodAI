/* ── Status / model section ───────────────────────────────────────────────
   The stale-data banner and the AI summary card. (The old StatusHero and
   RecommendationsPanel were retired by the citizen-first rebuild —
   DecisionHero + ActionCard replaced them; the action-derivation logic lives
   on in lib/recommendations.js.)
*/
import { useState } from "react";
import { useApp } from "../../lib/appContext";
import { formatDataTime, dataAgeMinutes, trendDisplay, STALE_STATUS_MIN } from "../../lib/dashboardHelpers";

/* Split the model's interpretation into a one-sentence lead + the remainder.
   Only the FIRST boundary matters; the rest is shown verbatim on demand. */
function splitLead(text) {
  const m = /[.!?]\s+(?=[A-Z0-9])/.exec(text);
  if (!m) return [text, ""];
  const cut = m.index + 1;
  return [text.slice(0, cut), text.slice(cut).trim()];
}

/* ── AI summary card — plain-language summary, deep analysis tucked inside ──
   Shows ONE sentence + two pills (status, trend). The rest of the model's
   explanation and the multi-agent analysis (passed as children) are opt-in.
*/
export function ModelOutputCard({ riskData, children }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const [expanded, setExpanded] = useState(false);

  const interpretation = riskData?.interpretation;
  const riskTrend = riskData?.trendState?.risk_trend;
  const level     = riskData?.level ?? "waspada";
  const snapTimeStr = formatDataTime(riskData?.snapshotFetchedAt, isId);
  const isStale = (dataAgeMinutes(riskData?.snapshotFetchedAt) ?? 0) >= STALE_STATUS_MIN;

  const levelColor = isStale
    ? "var(--muted)"
    : { aman: "var(--safe)", waspada: "var(--wsp)", siaga: "var(--s2)", bahaya: "var(--s1)" }[level] ?? "var(--wsp)";
  const levelLabel = { aman: isId ? "Aman" : "Safe", waspada: isId ? "Waspada" : "Watch",
    siaga: isId ? "Siaga" : "Alert", bahaya: isId ? "Bahaya" : "Danger" }[level] ?? "—";

  const trend = isStale ? null : trendDisplay(riskTrend, level, isId);

  const [lead, rest] = interpretation ? splitLead(interpretation) : ["", ""];

  return (
    <div className="panel panel-body ai-card fade-in">
      <div className="ai-card-head">
        <span className="ai-card-label">✦ {isId ? "Ringkasan AI" : "AI Summary"}</span>
        {snapTimeStr && <span className="ai-card-time">{snapTimeStr}</span>}
      </div>

      {interpretation && (
        <>
          <p className="ai-card-lead">{lead}</p>

          <div className="ai-card-pills">
            <span className="ai-pill" style={{ color: levelColor, borderColor: levelColor }}>{levelLabel}</span>
            {trend && <span className="ai-pill" style={{ color: trend.color }}>{trend.text}</span>}
          </div>

          {rest && (
            <>
              {expanded && <p className="ai-card-rest">{rest}</p>}
              <button className="ai-card-more" onClick={() => setExpanded((v) => !v)}>
                {expanded ? (isId ? "Sembunyikan ▴" : "Hide ▴") : (isId ? "Selengkapnya ▾" : "Read more ▾")}
              </button>
            </>
          )}
        </>
      )}

      {children && <div className="ai-card-deep">{children}</div>}
    </div>
  );
}

/* ── Stale data warning — tampil kalau snapshot > 30 menit ─────────────── */
export function StaleDataBanner({ snapshotFetchedAt }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const ageMin = dataAgeMinutes(snapshotFetchedAt);
  if (ageMin == null || ageMin < 30) return null;

  const ageLabel = ageMin >= 1440
    ? (isId ? `${Math.floor(ageMin / 1440)} hari` : `${Math.floor(ageMin / 1440)} days`)
    : ageMin >= 60
    ? (isId ? `${Math.floor(ageMin / 60)} jam` : `${Math.floor(ageMin / 60)} hours`)
    : (isId ? `${ageMin} menit` : `${ageMin} minutes`);

  return (
    <div className="stale-banner">
      <span aria-hidden="true">!</span>
      <span>
        {isId
          ? `Data terakhir masuk ${ageLabel} lalu, jadi kondisi sebenarnya bisa berbeda.`
          : `The last data came in ${ageLabel} ago, so actual conditions may differ.`}
      </span>
    </div>
  );
}
