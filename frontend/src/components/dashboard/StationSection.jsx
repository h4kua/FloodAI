/* ── Station section ──────────────────────────────────────────────────────
   A plain list of the DSDADKI water-level posts, grouped by wilayah so people
   can find the posts near them: name, kecamatan, how full the river is
   relative to its alert threshold, and a status badge. The most at-risk
   wilayah comes first, and the highest post first within each group.
*/
import { useApp } from "../../lib/appContext";
import {
  postClass, postRiskLevel, cleanStationName, stationKecamatan,
  groupStationsByWilayah, UPSTREAM_GROUP,
} from "../../lib/dashboardHelpers";
import { RiskBadge } from "./primitives";

const BAR_COLOR = { s1: "var(--s1)", s2: "var(--s2)", wsp: "var(--wsp)", ok: "var(--safe)" };

function StationRow({ s }) {
  const kec   = stationKecamatan(s.nama);
  const color = BAR_COLOR[postClass(s)];
  const pct   = Math.round(s.ratio * 100);
  return (
    <li className="station-row">
      <div className="station-name">
        <span>{cleanStationName(s.nama)}</span>
        {kec && <small>Kec. {kec.kecamatan}</small>}
      </div>
      <div className="station-bar"><i style={{ width: `${Math.min(pct, 100)}%`, background: color }} /></div>
      <span className="station-pct" style={{ color }}>{pct}%</span>
      <RiskBadge level={postRiskLevel(s)} />
    </li>
  );
}

export function StationPanel({ stations }) {
  const { lang } = useApp();
  const isId = lang === "id";

  if (!stations || stations.length === 0) return null;

  // Wilayah with posts, most at-risk first; upstream always last.
  const groups = groupStationsByWilayah(stations)
    .filter((g) => g.stations.length > 0)
    .sort((a, b) => (a.key === UPSTREAM_GROUP) - (b.key === UPSTREAM_GROUP) || b.maxRatio - a.maxRatio);

  const groupLabel = (key) => key === UPSTREAM_GROUP
    ? (isId ? "Luar Jakarta (hulu)" : "Outside Jakarta (upstream)")
    : key;

  return (
    <div className="panel panel-body fade-in">
      <p className="station-title">{isId ? "Ketinggian air di pos pantau" : "Water level at monitoring posts"}</p>
      <p className="station-sub">
        {isId
          ? "Dikelompokkan per wilayah. 100% berarti air sudah sampai batas siaga."
          : "Grouped by area. 100% means the water has reached the alert limit."}
      </p>

      {groups.map((g) => (
        <section key={g.key} className="station-group">
          <div className="station-group-head">
            <strong>{groupLabel(g.key)}</strong>
            <small>
              {g.key === UPSTREAM_GROUP
                ? (isId ? "Air dari sini mengalir ke Jakarta" : "Water from here flows into Jakarta")
                : (isId ? `${g.stations.length} pos pantau` : `${g.stations.length} post${g.stations.length > 1 ? "s" : ""}`)}
            </small>
          </div>
          <ul className="station-list">
            {g.stations.map((s) => <StationRow key={s.nama} s={s} />)}
          </ul>
        </section>
      ))}
    </div>
  );
}
