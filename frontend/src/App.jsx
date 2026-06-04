import { useState, useEffect, useContext } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import About from "./pages/About";
import OnboardingTour from "./components/OnboardingTour";
import { AppContext, useT } from "./lib/appContext";

/* ── deFlood.ai logo mark ───────────────────────────────── */
function DeFloodLogo() {
  return (
    <svg
      width="28" height="28" viewBox="0 0 24 24"
      fill="none" aria-hidden="true" style={{ flexShrink: 0 }}
    >
      {/* Water drop */}
      <path
        d="M12 2.8 C9.2 6.4 4.8 11.2 4.8 15.8 C4.8 20.3 8.0 23.2 12 23.2 C16.0 23.2 19.2 20.3 19.2 15.8 C19.2 11.2 14.8 6.4 12 2.8Z"
        fill="var(--cyan-soft)"
        stroke="var(--cyan)"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      {/* AI pulse line inside drop */}
      <path
        d="M8 16 L9.4 13.4 L10.8 18.2 L12.4 10.8 L13.8 16 L15.2 13.4"
        stroke="var(--cyan)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
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
          <DeFloodLogo />
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
