/* ── Station section ──────────────────────────────────────────────────────
   A plain list of the DSDADKI water-level posts: name, area, how full the
   river is relative to its alert threshold, and a status badge. Highest
   first, so the posts that matter are always on top.
*/
import { useState } from "react";
import { useApp } from "../../lib/appContext";
import { stationClass, stationRiskLevel, cleanStationName, stationKecamatan } from "../../lib/dashboardHelpers";
import { RiskBadge } from "./primitives";

const BAR_COLOR = { s1: "var(--s1)", s2: "var(--s2)", wsp: "var(--wsp)", ok: "var(--safe)" };
const PREVIEW = 6;

export function StationPanel({ stations }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const [showAll, setShowAll] = useState(false);

  if (!stations || stations.length === 0) return null;

  const sorted = [...stations].sort((a, b) => b.ratio - a.ratio);
  const displayed = showAll ? sorted : sorted.slice(0, PREVIEW);

  return (
    <div className="panel panel-body fade-in">
      <p className="station-title">{isId ? "Ketinggian air di pos pantau" : "Water level at monitoring posts"}</p>
      <p className="station-sub">
        {isId
          ? "Paling tinggi di atas. 100% berarti air sudah sampai batas siaga."
          : "Highest first. 100% means the water has reached the alert limit."}
      </p>

      <ul className="station-list">
        {displayed.map((s) => {
          const kec   = stationKecamatan(s.nama);
          const color = BAR_COLOR[stationClass(s.ratio)];
          const pct   = Math.round(s.ratio * 100);
          return (
            <li key={s.nama} className="station-row">
              <div className="station-name">
                <span>{cleanStationName(s.nama)}</span>
                {kec && <small>Kec. {kec.kecamatan}</small>}
              </div>
              <div className="station-bar"><i style={{ width: `${Math.min(pct, 100)}%`, background: color }} /></div>
              <span className="station-pct" style={{ color }}>{pct}%</span>
              <RiskBadge level={stationRiskLevel(s.ratio)} />
            </li>
          );
        })}
      </ul>

      {sorted.length > PREVIEW && (
        <button className="ai-card-more" onClick={() => setShowAll((v) => !v)}>
          {showAll
            ? (isId ? "Tampilkan lebih sedikit ▴" : "Show less ▴")
            : (isId ? `Lihat semua ${sorted.length} pos ▾` : `Show all ${sorted.length} posts ▾`)}
        </button>
      )}
    </div>
  );
}
