/* ── Small charts without a chart library ────────────────────────────────────
   Lines and bars are SVG stretched to the box (lines keep their width with
   vector-effect), labels are HTML, so text stays readable at any width.
*/
import { LEVEL_COLOR } from "../lib/dashboardHelpers";

const W = 1000;
const H = 100;
const GAP_MS = 2 * 60 * 60 * 1000; // a hole of more than 2 h breaks the line

// Two limit lines close together (Siaga 2 200 cm, Siaga 3 170 cm) put their labels on top of each
// other: the lower line's label goes under its line instead.
function placeLabels(items) {
  const sorted = [...items].sort((a, b) => a.top - b.top);
  return sorted.map((th, i) => ({ ...th, below: i > 0 && th.top - sorted[i - 1].top < 14 }));
}

/**
 * points: [{ t: ms, y: number | null, level?: "SAFE" | ... }], oldest first.
 * thresholds: [{ y, label, color }] drawn as dashed lines with their label.
 * levelStrip: a thin band under the line coloured by each point's level.
 */
export function TimeLine({ points = [], yMin = 0, yMax = 1, thresholds = [], height = 160, ariaLabel, xLabels = [],
                           levelStrip = false, color = "var(--cyan)" }) {
  if (points.length < 2) return null;
  const t0 = points[0].t;
  const span = Math.max(1, points[points.length - 1].t - t0);
  const x = (t) => ((t - t0) / span) * W;
  const y = (v) => H - ((Math.min(Math.max(v, yMin), yMax) - yMin) / Math.max(1e-9, yMax - yMin)) * H;
  const segments = [];
  let current = [];
  points.forEach((p, i) => {
    const broken = p.y == null || (i > 0 && p.t - points[i - 1].t > GAP_MS);
    if (broken && current.length) {
      segments.push(current);
      current = [];
    }
    if (p.y != null) current.push(`${x(p.t).toFixed(1)},${y(p.y).toFixed(1)}`);
  });
  if (current.length) segments.push(current);
  return (
    <div className="chart">
      <div className="chart-plot" style={{ height }} role="img" aria-label={ariaLabel}>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          {thresholds.map((th) => (
            <line key={th.label} x1="0" x2={W} y1={y(th.y)} y2={y(th.y)} stroke={th.color}
                  strokeWidth="1.2" strokeDasharray="5 5" vectorEffect="non-scaling-stroke" />
          ))}
          {segments.map((seg, i) => (
            seg.length === 1
              ? <circle key={i} cx={seg[0].split(",")[0]} cy={seg[0].split(",")[1]} r="1.5" fill={color} />
              : <polyline key={i} points={seg.join(" ")} fill="none" stroke={color} strokeWidth="2"
                          strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        {placeLabels(thresholds.map((th) => ({ ...th, top: (y(th.y) / H) * 100 }))).map((th) => (
          <span key={th.label} className={`chart-th${th.below ? " is-below" : ""}`} style={{ top: `${th.top}%`, color: th.color }}>
            {th.label}
          </span>
        ))}
      </div>
      {levelStrip && (
        <svg className="chart-strip" viewBox={`0 0 ${W} 10`} preserveAspectRatio="none" aria-hidden="true">
          {points.map((p, i) => {
            const next = points[i + 1]?.t ?? p.t;
            const w = next - p.t > GAP_MS ? 0 : x(next) - x(p.t);
            return w > 0 ? <rect key={i} x={x(p.t)} y="0" width={w + 0.5} height="10" fill={LEVEL_COLOR[p.level] ?? "var(--line)"} /> : null;
          })}
        </svg>
      )}
      {xLabels.length > 0 && (
        <div className="chart-x">
          {xLabels.map((l) => <span key={l}>{l}</span>)}
        </div>
      )}
    </div>
  );
}

/** Daily bars: items [{ label, title, values: [n | null, ...] }], series [{ name, color }]. */
export function DayBars({ items = [], series = [], height = 140, unit = "", ariaLabel, maxLabel = "max" }) {
  const max = Math.max(1, ...items.flatMap((d) => d.values.map((v) => v ?? 0)));
  return (
    <div className="chart">
      <div className="bars" style={{ height }} role="img" aria-label={ariaLabel}>
        {items.map((d) => (
          <div key={d.label} className="bars-day" title={d.title}>
            {d.values.map((v, i) => (
              <span key={series[i].name} className="bars-bar"
                    style={{ height: `${v == null ? 0 : Math.max(2, (v / max) * 100)}%`, background: series[i].color,
                             opacity: v == null ? 0.25 : 1 }} />
            ))}
          </div>
        ))}
      </div>
      <div className="chart-x bars-x">
        {items.map((d) => <span key={d.label}>{d.label}</span>)}
      </div>
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>
        ))}
        <span className="chart-max">{`${maxLabel} ${Math.round(max)}${unit}`}</span>
      </div>
    </div>
  );
}
