/* ── Dashboard primitives ─────────────────────────────────────────────────
   Small, shared leaf components used across the dashboard sections:
   badges, bars, the monochrome weather/phone glyphs, the metric card, and
   the labelled section divider. Extracted from the former Home.jsx.
*/
import { useT } from "../../lib/appContext";
import { use3DTilt } from "../../hooks/use3DTilt";
import { riskClass } from "../../lib/dashboardHelpers";

export function RiskBadge({ level }) {
  const t = useT();
  const cls = riskClass(level);
  return (
    <span className={`risk-badge badge-${cls}`}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor", display: "inline-block" }} />
      {t(`risk.${level}`) || level.replace("_", " ")}
    </span>
  );
}

export function ProbBar({ value }) {
  let color = "#00e5a0";
  if (value >= 0.80) color = "#ff3d5a";
  else if (value >= 0.55) color = "#f97316";
  else if (value >= 0.30) color = "#f5a623";
  return (
    <div className="prob-wrap">
      <div className="prob-track">
        <div className="prob-fill" style={{ width: `${value * 100}%`, background: color }} />
      </div>
      <span className="prob-text">{Math.round(value * 100)}%</span>
    </div>
  );
}

/* ── Weather iconography — inline monochrome SVG (no emoji) ─────────────────
   Renders a clean line-icon in currentColor so it inherits the surrounding
   text/accent color. Pair with weatherCond() from dashboardHelpers.
*/
export function WeatherGlyph({ cond, size = 22, color }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round" };
  const cloud = (dy = 0) => (
    <path d={`M7 ${16 + dy}h8a3 3 0 0 0 .3-5.98A4.4 4.4 0 0 0 6.7 ${10 + dy} 3 3 0 0 0 7 ${16 + dy}Z`} {...p} />
  );
  const rays = [0, 45, 90, 135, 180, 225, 270, 315].map((a) => {
    const r = (a * Math.PI) / 180;
    return <line key={a} x1={12 + 6.5 * Math.cos(r)} y1={12 + 6.5 * Math.sin(r)} x2={12 + 9 * Math.cos(r)} y2={12 + 9 * Math.sin(r)} {...p} />;
  });
  let body;
  switch (cond) {
    case "clear":  body = (<><circle cx="12" cy="12" r="4.2" {...p} />{rays}</>); break;
    case "partly": body = (<><circle cx="9" cy="8.5" r="3" {...p} />{cloud(2)}</>); break;
    case "rain":   body = (<>{cloud(-2)}<line x1="9" y1="17" x2="8" y2="20.5" {...p} /><line x1="13" y1="17" x2="12" y2="20.5" {...p} /></>); break;
    case "storm":  body = (<>{cloud(-2)}<path d="M12.5 16l-2.5 3.2h3l-2.5 3.2" {...p} /></>); break;
    case "snow":   body = (<>{cloud(-2)}<line x1="9" y1="18.2" x2="9" y2="20.5" {...p} /><line x1="13" y1="18.2" x2="13" y2="20.5" {...p} /></>); break;
    case "mist":   body = (<><line x1="4.5" y1="9" x2="19.5" y2="9" {...p} /><line x1="4.5" y1="13" x2="17" y2="13" {...p} /><line x1="6.5" y1="17" x2="19.5" y2="17" {...p} /></>); break;
    default:       body = cloud(0);
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ color, display: "block", flexShrink: 0 }}>
      {body}
    </svg>
  );
}

export function PhoneGlyph({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ display: "block" }}>
      <path d="M6.6 4h2.9l1.4 3.8-2 1.4a10.8 10.8 0 0 0 4.9 4.9l1.4-2 3.8 1.4v2.9a2 2 0 0 1-2.2 2A15.8 15.8 0 0 1 4.6 6.2 2 2 0 0 1 6.6 4Z"
        fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

export function MetricCard({ c, noteStyle }) {
  const tiltRef = use3DTilt({ maxTilt: 10 });
  return (
    <div ref={tiltRef} className={`metric-card card-3d ${c.color}`}>
      <div className="card-3d-content" style={{ display: "flex", flex: 1, flexDirection: "column", justifyContent: "space-between", height: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%" }}>
          <span className="metric-label">{c.label}</span>
          <span className="metric-real-badge" style={noteStyle}>● real</span>
        </div>
        <div>
          <div className={`metric-value ${c.color}`}>{c.value}</div>
          <div className="metric-sub">{c.sub}</div>
        </div>
      </div>
    </div>
  );
}

/* ── SectionDivider — labelled zone separator for the dashboard ────────── */
export function SectionDivider({ label, count }) {
  return (
    <div className="dash-section">
      <span className="dash-section-label">{label}</span>
      {count != null && <span className="dash-section-count">{count}</span>}
      <span className="dash-section-line" />
    </div>
  );
}
