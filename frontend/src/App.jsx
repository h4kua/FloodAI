import { useState, useEffect } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import CommunityReports from "./pages/CommunityReports";
import About from "./pages/About";
import TopBar from "./components/shell/TopBar";
import BottomNav from "./components/shell/BottomNav";
import OnboardingTour from "./components/OnboardingTour";
import { AppContext } from "./lib/appContext";

function AppShell() {
  const [page, setPage] = useState("home");
  const [riskContext, setRiskContext] = useState({ level: "waspada", rainfall: 0 });

  return (
    <div className="shell">
      <TopBar page={page} onNavigate={setPage} />

      <main className="main">
        {page === "home"    && <Home setRiskContext={setRiskContext} riskLevel={riskContext.level} onNavigate={setPage} />}
        {page === "alert"   && <Alert riskLevel={riskContext.level} rainfall={riskContext.rainfall} />}
        {page === "reports" && <CommunityReports riskLevel={riskContext.level} rainfall={riskContext.rainfall} />}
        {page === "about"   && <About riskContext={riskContext} />}
      </main>

      <footer className="footer">
        <span>deFlood.ai — Jakarta Flood Intelligence System · Operator BPBD</span>
        <span>XGBoost · 17 features · AUC-ROC 0.901 · Recall 84% · ECE 0.014 · &lt;1s latency</span>
      </footer>

      <BottomNav page={page} onNavigate={setPage} />
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
