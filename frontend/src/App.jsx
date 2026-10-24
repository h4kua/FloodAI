import { useState, useEffect, lazy, Suspense } from "react";
import Home from "./pages/Home";
import LoadingSpinner from "./components/LoadingSpinner";
import TopBar from "./components/shell/TopBar";
import BottomNav from "./components/shell/BottomNav";
import OnboardingTour from "./components/OnboardingTour";
import { AppContext, useT } from "./lib/appContext";

// Beranda is the landing page and ships in the main bundle; the other pages
// load on first visit.
const Alert = lazy(() => import("./pages/Alert"));
const About = lazy(() => import("./pages/About"));

function AppShell() {
  const t = useT();
  const [page, setPage] = useState("home");
  const [riskContext, setRiskContext] = useState({ level: "waspada", rainfall: 0 });

  return (
    <div className="shell">
      <TopBar page={page} onNavigate={setPage} />

      <main className="main">
        {page === "home"  && <Home setRiskContext={setRiskContext} riskLevel={riskContext.level} onNavigate={setPage} />}
        <Suspense fallback={<LoadingSpinner />}>
          {page === "alert" && <Alert riskLevel={riskContext.level} rainfall={riskContext.rainfall} />}
          {page === "about" && <About riskContext={riskContext} />}
        </Suspense>
      </main>

      <footer className="footer">
        <span>deFlood.ai</span>
        <span>{t("footer.disclaimer")}</span>
      </footer>

      <BottomNav page={page} onNavigate={setPage} />
      <OnboardingTour />
    </div>
  );
}

export default function App() {
  const [lang,  setLang]  = useState(() => localStorage.getItem("deflood_lang")  || "id");
  const [theme, setTheme] = useState(() => localStorage.getItem("deflood_theme") || "light");

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
