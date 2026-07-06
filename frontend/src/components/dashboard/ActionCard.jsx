import { useT, useApp } from "../../lib/appContext";
import { use3DTilt } from "../../hooks/use3DTilt";
import { deriveActions } from "../../lib/recommendations";
import { PhoneGlyph } from "./primitives";

/* ── ActionCard — "Apa yang harus saya lakukan?" ───────────────────────────
   Cognitive-load reduction per the FloodGuard spec: at most 3 concrete
   actions and ONE primary CTA. Siaga/Bahaya → the CTA is the evacuation
   route; otherwise it points at the live map. BPBD 117 stays one tap away.
*/
export default function ActionCard({ riskData, stations = [], onNavigate }) {
  const t = useT();
  const { lang } = useApp();
  const isId = lang === "id";
  const tiltRef = use3DTilt({ maxTilt: 5 });

  const level = riskData?.level ?? "waspada";
  const { actions, s1, topW } = deriveActions(riskData, stations, isId);
  const topActions = actions.slice(0, 3);

  const isUrgent = level === "siaga" || level === "bahaya" || s1.length > 0;

  const goEvac = () => {
    if (onNavigate) {
      window.scrollTo(0, 0);
      onNavigate("alert");
    }
  };
  const scrollToMap = () => {
    document.getElementById("map-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const callBPBD = () => {
    window.location.href = "tel:117";
  };

  const primaryLabel = isUrgent
    ? (topW
        ? (isId ? `Rute Evakuasi — ${topW.wilayah.replace("Jakarta ", "")}` : `Evacuation Route — ${topW.wilayah.replace("Jakarta ", "")}`)
        : t("home.ctaEvac"))
    : t("home.ctaMonitor");

  return (
    <div ref={tiltRef} className="panel panel-body card-3d action-card">
      <div className="card-3d-content">
        <p className="action-card-title">{t("home.actionTitle")}</p>

        <div className="action-card-list">
          {topActions.map((action, i) => (
            <div key={i} className="action-card-item">
              <span className="action-card-marker">{i + 1}</span>
              <p>{action}</p>
            </div>
          ))}
        </div>

        <div className="action-card-buttons">
          <button
            className={`action-btn${isUrgent ? " primary" : ""}`}
            onClick={isUrgent ? goEvac : scrollToMap}
            title={primaryLabel}
          >
            <span className="action-icon">{isUrgent ? "!" : "◉"}</span>
            {primaryLabel}
          </button>
          {!isUrgent && (
            <button className="action-btn" onClick={goEvac} title={t("home.ctaEvac")}>
              <span className="action-icon">↗</span>
              {t("home.ctaEvac")}
            </button>
          )}
          <button className="action-btn action-btn-call" onClick={callBPBD} title={t("home.callBpbd")}>
            <span className="action-icon"><PhoneGlyph size={14} /></span>
            {t("home.callBpbd")}
          </button>
        </div>

        <p className="action-card-note">
          ● {isId ? "Berdasarkan sensor DSDADKI + BMKG realtime" : "Based on realtime DSDADKI sensors + BMKG data"}
        </p>
      </div>
    </div>
  );
}
