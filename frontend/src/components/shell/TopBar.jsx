import { useApp, useT } from "../../lib/appContext";
import { NAV_ITEMS } from "./navConfig";

/* ── deFlood.ai logo mark ───────────────────────────────── */
/* A plain signage tile: water-blue square, two water lines in the chrome colour. */
function DeFloodLogo({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ flexShrink: 0, display: "block" }}>
      <rect width="24" height="24" rx="5" fill="currentColor" />
      <g fill="none" strokeWidth="2.2" strokeLinecap="round" style={{ stroke: "var(--chrome)" }}>
        <path d="M5 10.5c1.75-1.5 3.25-1.5 5 0s3.25 1.5 5 0 3.25-1.5 4 0" />
        <path d="M5 15.5c1.75-1.5 3.25-1.5 5 0s3.25 1.5 5 0 3.25-1.5 4 0" />
      </g>
    </svg>
  );
}

export default function TopBar({ page, onNavigate }) {
  const t = useT();
  const { lang, setLang, theme, setTheme } = useApp();

  return (
    <header className="topbar">
      <span className="logo">
        <DeFloodLogo size={22} />
        <span className="logo-text">
          <span className="logo-de">de</span><span className="logo-flood">Flood</span><span className="logo-ai">.ai</span>
        </span>
      </span>

      <nav className="nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            data-tour={item.tour}
            className={`nav-btn${page === item.id ? " active" : ""}`}
            onClick={() => onNavigate(item.id)}
          >
            {t(item.labelKey)}
          </button>
        ))}
      </nav>

      <div className="topbar-right">
        <button
          className="topbar-toggle"
          data-tour="lang"
          onClick={() => setLang((l) => (l === "id" ? "en" : "id"))}
          title="Switch language"
        >
          {lang === "id" ? "EN" : "ID"}
        </button>
        <button
          className="topbar-toggle"
          data-tour="theme"
          onClick={() => setTheme((th) => (th === "dark" ? "light" : "dark"))}
          title="Toggle theme"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? (
            /* sun — click to go light */
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true" style={{ display: "block" }}>
              <circle cx="12" cy="12" r="4.2" />
              {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => {
                const r = (a * Math.PI) / 180;
                return <line key={a} x1={12 + 6.5 * Math.cos(r)} y1={12 + 6.5 * Math.sin(r)} x2={12 + 9 * Math.cos(r)} y2={12 + 9 * Math.sin(r)} />;
              })}
            </svg>
          ) : (
            /* moon — click to go dark */
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ display: "block" }}>
              <path d="M20 14.5A8 8 0 1 1 9.5 4a6.3 6.3 0 0 0 10.5 10.5Z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  );
}
