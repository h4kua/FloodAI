import { useT } from "../lib/appContext";

/**
 * Safe Arrival confirmation overlay (FloodGuard FR8). Not a nav-tab
 * destination — triggered automatically by the geofence hook (or the manual
 * "I've Arrived" button) from Alert.jsx's Shelter Finder flow, per the
 * paper's "zero manual input" intent.
 */
export default function SafeArrival({ shelterName, onClose }) {
  const t = useT();

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: "var(--z-modal)",
        background: "rgba(4,10,8,0.72)", backdropFilter: "blur(4px)",
        display: "grid", placeItems: "center", padding: "1.5rem",
      }}
      onClick={onClose}
    >
      <div
        className="panel panel-body fade-in"
        style={{ maxWidth: 380, textAlign: "center", padding: "2.5rem 2rem" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="safe-arrival-check"
          style={{
            width: 88, height: 88, borderRadius: "50%", margin: "0 auto 1.25rem",
            background: "var(--safe-soft)", border: `2px solid var(--safe-border)`,
            display: "grid", placeItems: "center",
          }}
        >
          <svg className="safe-arrival-checkmark" width="40" height="40" viewBox="0 0 24 24" fill="none">
            <path d="M4 12.5 L9.5 18 L20 6" stroke="var(--safe)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.2rem", fontWeight: 800, color: "var(--safe)", marginBottom: "0.5rem" }}>
          {t("safeArrival.title")}
        </p>
        <p style={{ color: "var(--muted)", fontSize: "0.85rem", lineHeight: 1.55, marginBottom: "0.375rem" }}>
          {t("safeArrival.subtitle", { shelter: shelterName })}
        </p>
        <p style={{ color: "var(--muted-2)", fontSize: "0.76rem", marginBottom: "1.5rem" }}>
          {t("safeArrival.notified")}
        </p>
        <button className="btn btn-ghost" onClick={onClose}>{t("safeArrival.close")}</button>
      </div>
    </div>
  );
}
