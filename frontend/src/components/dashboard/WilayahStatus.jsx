import { useApp } from "../../lib/appContext";
import {
  JAKARTA_WILAYAH, groupStationsByWilayah, postRiskLevel, riskClass, dataAgeMinutes, STALE_STATUS_MIN, wilayahLabel,
  cleanStationName, formatChance, wilayahModelLevel,
} from "../../lib/dashboardHelpers";
import { RiskBadge } from "./primitives";

/* ── WilayahStatus — "is MY area at risk?" ─────────────────────────────────
   One cell per Jakarta kota. With the per-wilayah decision layer (backend `wilayah_status`) the cell shows
   that kota's own level and today's flood chance; tapping it lists its monitoring posts, the kecamatan
   with today's highest chance, what raised it, and the kecamatan BPBD recorded flooded most often.
   Without it (layer off, data missing) the cell falls back to the worst post of the kota.
*/
export default function WilayahStatus({ riskData }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const stations = riskData?.stations ?? [];
  const model = riskData?.wilayahStatus?.wilayah ?? null;
  if (stations.length === 0 && !model) return null;

  const isStale = (dataAgeMinutes(riskData?.snapshotFetchedAt) ?? 0) >= STALE_STATUS_MIN;
  const groups = groupStationsByWilayah(stations).filter((g) => JAKARTA_WILAYAH.includes(g.key));

  return (
    <div className={`panel panel-body fade-in${isStale ? " is-stale" : ""}`}>
      <p className="station-title">
        {isStale
          ? (isId ? "Status terakhir per wilayah" : "Last known status by area")
          : (isId ? "Status per wilayah" : "Status by area")}
      </p>
      <p className="station-sub" style={{ marginBottom: 0 }}>
        {model
          ? (isId
              ? "Peluang banjir hari ini di tiap kota, dengan ambang yang sama seperti Jakarta. Peluang satu kota lebih kecil, jadi statusnya bisa lebih rendah. Ketuk kota untuk pos pantau dan area yang paling sering banjir."
              : "Today's flood chance in each city, with the same thresholds as Jakarta. One city's chance is lower, so its status can be lower. Tap a city for its posts and the areas that flood most often.")
          : (isId
              ? "Menurut pos pantau air dengan kondisi terparah di tiap wilayah."
              : "Based on the worst water-level post in each area.")}
      </p>
      <ul className="wilayah-status-list">
        {groups.map((g) => {
          const m = model?.[g.key];
          const level = m ? wilayahModelLevel(m.risk_level) : (g.worst ? postRiskLevel(g.worst) : null);
          return (
            <li key={g.key} className={`wilayah-status-cell tone-${level ? riskClass(level) : "none"}`}>
              <details className="wilayah-details">
                <summary>
                  <span className="wilayah-status-name">{wilayahLabel(g.key, isId)}</span>
                  {level && <RiskBadge level={level} />}
                  <small>
                    {m
                      ? (isId ? `Peluang banjir ${formatChance(m.score)}` : `Flood chance ${formatChance(m.score)}`)
                      : g.stations.length
                      ? (isId ? `${g.stations.length} pos pantau` : `${g.stations.length} post${g.stations.length > 1 ? "s" : ""}`)
                      : (isId ? "Belum ada pos pantau" : "No monitoring post")}
                  </small>
                </summary>
                <div className="wilayah-more">
                  {m?.siaga1_rule && (
                    <p>{isId ? "Ada pos di Siaga 1 (di kota ini atau di hulu), jadi status otomatis Bahaya."
                             : "A post at Alert 1 (in this city or upstream) makes the status Danger."}</p>
                  )}
                  {m?.top_kecamatan && (
                    <p>
                      {isId ? "Kecamatan paling berisiko menurut model harian: " : "Riskiest kecamatan by the daily model: "}
                      <strong>{isId ? "Kec. " : ""}{m.top_kecamatan.name}</strong> ({formatChance(m.top_kecamatan.probability)})
                    </p>
                  )}
                  {(isId ? m?.reasons : m?.reasons_en)?.length > 0 && (
                    <p>{isId ? "Paling dinaikkan oleh: " : "Raised most by: "}{(isId ? m.reasons : m.reasons_en).join("; ")}.</p>
                  )}
                  <p className="wilayah-more-title">
                    {isId ? `Pos pantau (${g.stations.length})` : `Monitoring posts (${g.stations.length})`}
                  </p>
                  {g.stations.length ? (
                    <ul className="wilayah-more-list">
                      {g.stations.map((s) => (
                        <li key={s.nama}>
                          <span>{cleanStationName(s.nama)}</span>
                          <RiskBadge level={postRiskLevel(s)} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>{isId ? "Belum ada pos pantau di kota ini." : "No monitoring post in this city."}</p>
                  )}
                  {m?.frequent?.length > 0 && (
                    <>
                      <p className="wilayah-more-title">
                        {isId ? "Paling sering banjir (catatan BPBD 2013–2025)" : "Floods most often (BPBD records 2013–2025)"}
                      </p>
                      <ul className="wilayah-more-list">
                        {m.frequent.map((k) => (
                          <li key={k.kecamatan}>
                            <span>{isId ? "Kec. " : ""}{k.name}</span>
                            <small>{isId ? `${k.flood_days} hari banjir` : `${k.flood_days} flood days`}</small>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              </details>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
