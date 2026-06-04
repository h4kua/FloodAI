import { useState, useEffect, useContext } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import About from "./pages/About";
import OnboardingTour from "./components/OnboardingTour";
import { AppContext, useT } from "./lib/appContext";

/* ── deFlood.ai logo mark ───────────────────────────────── */
/*
 * Icon concept: TMA gauge (tongkat pengukur Tinggi Muka Air) — the exact
 * instrument Jakarta flood monitoring uses at pintu air stations.
 * Left: gauge post with 3 siaga-level tick marks.
 * Right: rising water fill with wave, level at middle tick (Siaga 3 zone).
 * Specific to Jakarta flood infrastructure. Readable at 20–32px.
 */
function DeFloodLogo({ size = 22 }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24"
      fill="none" aria-hidden="true"
      style={{ flexShrink: 0, display: "block" }}
    >
      {/* Water fill — rising level */}
      <path
        d="M8 13 C9.5 11.5 11 14 12.5 12.5 C14 11 15.5 13.5 17 12 C18 11.2 19 11.5 20 11.5 L20 20 L8 20 Z"
        fill="var(--cyan-soft)"
      />
      {/* Wave at water surface */}
      <path
        d="M8 13 C9.5 11.5 11 14 12.5 12.5 C14 11 15.5 13.5 17 12 C18 11.2 19 11.5 20 11.5"
        stroke="var(--cyan)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
      />
      {/* Gauge post — TMA stick */}
      <line x1="6" y1="4" x2="6" y2="20" stroke="var(--cyan)" strokeWidth="2.5" strokeLinecap="round"/>
      {/* Siaga tick marks on gauge */}
      <line x1="6" y1="8"  x2="9.5" y2="8"  stroke="var(--cyan)" strokeWidth="1.4" strokeLinecap="round" opacity="0.45"/>
      <line x1="6" y1="12" x2="10"  y2="12" stroke="var(--cyan)" strokeWidth="1.6" strokeLinecap="round"/>
      <line x1="6" y1="16" x2="9.5" y2="16" stroke="var(--cyan)" strokeWidth="1.4" strokeLinecap="round" opacity="0.45"/>
      {/* Active level indicator dot on gauge */}
      <circle cx="6" cy="12" r="2.2" fill="var(--cyan)"/>
    </svg>
  );
}

function AppShell() {
  const t = useT();
  const { lang, setLang, theme, setTheme } = useContext(AppContext);
  const [page, setPage] = useState("home");
  const [riskContext, setRiskContext] = useState({ level: "waspada", rainfall: 0 });

  return (
    <div className="shell">
      <header className="topbar">
        <span className="logo">
          <DeFloodLogo size={22} />
          <span className="logo-text">
            <span className="logo-de">de</span><span className="logo-flood">Flood</span><span className="logo-ai">.ai</span>
          </span>
        </span>

        <nav className="nav">
          {[
            { id: "home",  label: t("nav.home") },
            { id: "alert", label: t("nav.evac") },
            { id: "about", label: t("nav.about") },
          ].map((item) => (
            <button
              key={item.id}
              className={`nav-btn${page === item.id ? " active" : ""}`}
              onClick={() => setPage(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="topbar-right">
          <button className="topbar-toggle" onClick={() => setLang(l => l === "id" ? "en" : "id")} title="Switch language">
            {lang === "id" ? "EN" : "ID"}
          </button>
          <button className="topbar-toggle" onClick={() => setTheme(th => th === "dark" ? "light" : "dark")} title="Toggle theme">
            {theme === "dark" ? "☀" : "🌙"}
          </button>
          <div className="chip live">
            <span className="live-dot" />
            {t("topbar.online")}
          </div>
          <div className="chip">Jakarta, DKI</div>
        </div>
      </header>

      <main className="main">
        {page === "home"  && <Home setRiskContext={setRiskContext} riskLevel={riskContext.level} />}
        {page === "alert" && <Alert riskLevel={riskContext.level} rainfall={riskContext.rainfall} />}
        {page === "about" && <About riskContext={riskContext} />}
      </main>

      <footer className="footer">
        <span>deFlood.ai — Jakarta Flood Intelligence System · Operator BPBD</span>
        <span>XGBoost · 16 features · AUC-ROC 0.863 · ECE 0.004 · &lt;1s latency</span>
      </footer>

      <OnboardingTour />
    </div>
  );
}

export default function App() {
  const [lang,  setLang]  = useState(() => localStorage.getItem("deflood_lang")  || "id");
  const [theme, setTheme] = useState(() => localStorage.getItem("deflood_theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("deflood_theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("deflood_lang", lang);
  }, [lang]);

  return (
    <AppContext.Provider value={{ lang, setLang, theme, setTheme }}>
      <AppShell />
    </AppContext.Provider>
  );
}
