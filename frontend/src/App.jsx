import { useState, useEffect, useContext } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import About from "./pages/About";
import OnboardingTour from "./components/OnboardingTour";
import { AppContext, useT } from "./lib/appContext";

/* ── deFlood.ai logo mark ───────────────────────────────── */
/*
 * Abstract triskelion vortex — three identical curved arms at 120° intervals.
 * Squircle badge (rounded-rect) with cyan→blue gradient.
 * Reads as: rotating flow (water) + dynamic intelligence (AI).
 * No literal imagery — same design language as Claude, DeepSeek, ChatGPT.
 */
function DeFloodLogo({ size = 22 }) {
  const id = `df${size}`;
  /* Each arm: starts near outer edge, sweeps elegantly toward center */
  const arm = "M 16 5.5 C 24 5.5 27.5 13 23 19 C 21.5 21.5 19 23 16 23";
  return (
    <svg
      width={size} height={size} viewBox="0 0 32 32"
      fill="none" aria-hidden="true"
      style={{ flexShrink: 0, display: "block" }}
    >
      <defs>
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%"   stopColor="#22d3ee" />
          <stop offset="55%"  stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#0c4a6e" />
        </linearGradient>
        <clipPath id={`${id}c`}>
          <rect x="1" y="1" width="30" height="30" rx="7.5" />
        </clipPath>
      </defs>

      {/* Squircle badge background */}
      <rect x="1" y="1" width="30" height="30" rx="7.5" fill={`url(#${id}g)`} />

      {/* Three-arm vortex mark */}
      <g clipPath={`url(#${id}c)`} stroke="white" strokeLinecap="round" fill="none" strokeWidth="2.8">
        <path d={arm} />
        <path d={arm} transform="rotate(120 16 16)" />
        <path d={arm} transform="rotate(240 16 16)" />
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
