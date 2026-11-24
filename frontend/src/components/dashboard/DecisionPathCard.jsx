/* ── How today's status was decided ─────────────────────────────────────────
   Follows the backend order (services/decision_engine.py): the safety rules
   L0 (no data), L1 (a post at Siaga 1 or a rapid rise) and L1.7 (BMKG severe
   warning) first; if none fires, the learned decision layer
   (realtime_native/decision_layer.py) turns its flood chance into a level;
   without its inputs the hand-written rule layers decide instead.
*/
import { useApp } from "../../lib/appContext";
import { formatChance, layerTopReasons } from "../../lib/dashboardHelpers";
import { RiskBadge } from "./primitives";

const SAFETY = [
  { key: "L0_PHYSICAL", id: "Data sungai tidak tersedia", en: "No river data" },
  { key: "L1_SIAGA", id: "Pos di Siaga 1 atau air naik cepat", en: "A post at Siaga 1 or water rising fast" },
  { key: "L1_7_BMKG_SAFETY_FLOOR", id: "Peringatan cuaca ekstrem BMKG", en: "BMKG severe weather warning" },
];
const NAMES = {
  id: { PRE_ALERT: "Waspada", WARNING: "Siaga", DANGER: "Bahaya" },
  en: { PRE_ALERT: "Watch", WARNING: "Alert", DANGER: "Danger" },
};

export default function DecisionPathCard({ riskData }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const decision = riskData?.decision;
  const layer = riskData?.decisionLayer;
  const badge = (riskData?.level ?? "unknown").toUpperCase();
  if (!decision?.layer) return null;

  const decidedBy = decision.layer;
  const safetyHit = SAFETY.find((s) => s.key === decidedBy);
  const learned = decidedBy === "L3_LEARNED" && layer?.decided;
  const posts = riskData?.stations?.length ?? 0;
  const daily = riskData?.dailyModel;
  const reasons = learned ? layerTopReasons(layer, isId) : [];
  const thr = layer?.thresholds ?? {};
  const names = NAMES[isId ? "id" : "en"];

  return (
    <div className="panel panel-body ai-card fade-in">
      <div className="ai-card-head">
        <span className="ai-card-label">{isId ? "Bagaimana keputusan dibuat" : "How the status was decided"}</span>
      </div>
      <ol className="decision-steps">
        <li className="decision-step">
          <h4>{isId ? "Data masuk" : "Data in"}</h4>
          <p>
            {isId
              ? `${posts} pos pantau air DSDA (tiap 15 menit)${daily?.city_probability != null ? `, model harian per kecamatan (peluang tertinggi ${formatChance(daily.city_probability)})` : ""}, hujan satelit NASA hari ini dan peringatan BMKG.`
              : `${posts} DSDA water-level posts (every 15 minutes)${daily?.city_probability != null ? `, the daily kecamatan model (highest chance ${formatChance(daily.city_probability)})` : ""}, today's NASA satellite rain and BMKG warnings.`}
          </p>
        </li>
        <li className="decision-step">
          <h4>{isId ? "Aturan keselamatan diperiksa dulu" : "Safety rules checked first"}</h4>
          <ul className="rule-list">
            {SAFETY.map((s) => {
              const hit = s.key === decidedBy;
              return (
                <li key={s.key} className={hit ? "rule-hit" : undefined}>
                  <span className="rule-mark" aria-hidden="true">{hit ? "!" : "✓"}</span>
                  <span>{isId ? s.id : s.en}: {hit ? (isId ? "terpicu, status langsung ditetapkan" : "triggered, it sets the status") : (isId ? "tidak terpicu" : "not triggered")}</span>
                </li>
              );
            })}
          </ul>
        </li>
        {!safetyHit && (
          <li className="decision-step">
            {learned ? (
              <>
                <h4>{isId ? `Lapisan keputusan terlatih: peluang ${formatChance(layer.score)}` : `Learned decision layer: ${formatChance(layer.score)} chance`}</h4>
                <p>
                  {isId
                    ? "Model XGBoost yang dilatih pada data DSDA dan banjir BPBD 2016–2025 menggabungkan semua data di atas menjadi satu peluang banjir hari ini."
                    : "An XGBoost model trained on DSDA and BPBD flood data 2016–2025 combines all of the above into one flood chance for today."}
                </p>
                <div className="chance-bar" role="img"
                     aria-label={isId ? `Peluang ${formatChance(layer.score)}` : `Chance ${formatChance(layer.score)}`}>
                  <span className="chance-bar-fill" style={{ left: `${Math.min(100, layer.score * 100)}%` }} />
                  {["PRE_ALERT", "WARNING", "DANGER"].filter((k) => thr[k] != null).map((k) => (
                    <span key={k} className="chance-bar-tick" style={{ left: `${thr[k] * 100}%` }}>
                      {names[k]} {Math.round(thr[k] * 100)}%
                    </span>
                  ))}
                </div>
                {reasons.length > 0 && (
                  <>
                    <p>{isId ? "Yang paling menaikkan peluang:" : "What raised the chance most:"}</p>
                    <ul>{reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                  </>
                )}
              </>
            ) : (
              <>
                <h4>{isId ? "Aturan pos sungai" : "River-post rules"}</h4>
                <p>
                  {isId
                    ? "Lapisan terlatih belum punya semua masukannya (misalnya hujan satelit hari ini), jadi status mengikuti aturan berdasarkan status Siaga tiap pos dan model harian."
                    : "The learned layer does not have all its inputs yet (today's satellite rain, for example), so the status follows rules on each post's Siaga status and the daily model."}
                </p>
              </>
            )}
          </li>
        )}
        <li className="decision-step is-final">
          <h4>{isId ? "Hasil" : "Result"}</h4>
          <p style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <RiskBadge level={badge} />
            <span>
              {safetyHit
                ? (isId ? "ditetapkan oleh aturan keselamatan." : "set by a safety rule.")
                : learned
                  ? (isId ? "dari peluang lapisan terlatih dan ambangnya." : "from the learned layer's chance and its thresholds.")
                  : (isId ? "dari aturan pos sungai." : "from the river-post rules.")}
            </span>
          </p>
        </li>
      </ol>
    </div>
  );
}
