import { useApp } from "../../lib/appContext";
import {
  JAKARTA_WILAYAH, groupStationsByWilayah, stationRiskLevel, stationClass, dataAgeMinutes, STALE_STATUS_MIN,
} from "../../lib/dashboardHelpers";
import { RiskBadge } from "./primitives";

/* ── WilayahStatus — "is MY area at risk?" ─────────────────────────────────
   One cell per Jakarta wilayah, status = the worst monitoring post in that
   wilayah (same thresholds as the post list). No model percentages.
*/
export default function WilayahStatus({ riskData }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const stations = riskData?.stations ?? [];
  if (stations.length === 0) return null;

  const isStale = (dataAgeMinutes(riskData?.snapshotFetchedAt) ?? 0) >= STALE_STATUS_MIN;
  const groups = groupStationsByWilayah(stations).filter((g) => JAKARTA_WILAYAH.includes(g.key));

  return (
    <div className={`panel panel-body fade-in${isStale ? " is-stale" : ""}`}>
      <p className="station-title">
        {isStale
          ? (isId ? "Status terakhir per wilayah" : "Last known status by area")
          : (isId ? "Status per wilayah" : "Status by area")}
      </p>
      <ul className="wilayah-status-list">
        {groups.map((g) => (
          <li key={g.key} className={`wilayah-status-cell tone-${g.maxRatio != null ? stationClass(g.maxRatio) : "none"}`}>
            <span className="wilayah-status-name">{g.key.replace("Jakarta ", "")}</span>
            {g.maxRatio != null ? (
              <>
                <RiskBadge level={stationRiskLevel(g.maxRatio)} />
                <small>{isId ? `${g.stations.length} pos pantau` : `${g.stations.length} post${g.stations.length > 1 ? "s" : ""}`}</small>
              </>
            ) : (
              <small>{isId ? "Belum ada pos pantau" : "No monitoring post"}</small>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
