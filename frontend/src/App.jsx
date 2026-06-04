import { useState, useEffect, useContext } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import About from "./pages/About";
import OnboardingTour from "./components/OnboardingTour";
import { AppContext, useT } from "./lib/appContext";

/* ── deFlood.ai logo mark ───────────────────────────────── */
/*
 * Design language: abstract geometric like modern AI logos (ChatGPT, Claude,
 * Gemini). A smooth filled circle with three flowing wave arcs inside —
 * each arc subtly references data streams + water. No literal imagery.
 * Gradient from cyan-300 → sky-600. Clean, bold, scalable.
 */
function DeFloodLogo({ size = 22 }) {
  const id = `df${size}`;
  return (
    <svg
      width={size} height={size} viewBox="0 0 32 32"
      fill="none" aria-hidden="true"
      style={{ flexShrink: 0, display: "block" }}
    >
      <defs>
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%"   stopColor="#67e8f9" />
          <stop offset="100%" stopColor="#0369a1" />
        </linearGradient>
        <clipPath id={`${id}c`}>
          <circle cx="16" cy="16" r="13.5" />
        </clipPath>
      </defs>

      {/* Filled circle base — the "AI badge" */}
      <circle cx="16" cy="16" r="13.5" fill={`url(#${id}g)`} />

      {/* Three abstract wave arcs — water + data streams */}
      <g clipPath={`url(#${id}c)`} stroke="white" strokeLinecap="round" strokeLinejoin="round" fill="none">
        {/* Top arc — lightest, suggests distant data */}
        <path d="M5 13 C7.5 10.5 10 14.5 12.5 12 C15 9.5 17.5 13 20 10.5 C21.5 9 23 10 27 9"
          strokeWidth="1.6" opacity="0.45" />
        {/* Middle arc — main wave */}
        <path d="M5 17 C7.5 14.5 10 18.5 12.5 16 C15 13.5 17.5 17 20 14.5 C21.5 13 23 14 27 13"
          strokeWidth="2.2" opacity="0.85" />
        {/* Bottom arc — subtle, suggests depth */}
        <path d="M5 21 C7.5 18.5 10 22.5 12.5 20 C15 17.5 17.5 21 20 18.5 C21.5 17 23 18 27 17"
          strokeWidth="1.6" opacity="0.45" />
      </g>
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
