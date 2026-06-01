import { useState } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import AlertBanner from "./components/AlertBanner";

const NAV = [
  { id: "home",  label: "Dashboard" },
  { id: "alert", label: "Evakuasi"  },
];

export default function App() {
  const [page, setPage] = useState("home");
  const [riskLevel, setRiskLevel] = useState("waspada");

  return (
    <div className="shell">
      <AlertBanner level={riskLevel} />

      <header className="topbar">
        <span className="logo">
          <span className="logo-de">de</span>
          <span className="logo-flood">Flood</span>
          <span className="logo-ai">.ai</span>
        </span>

        <nav className="nav">
          {NAV.map((item) => (
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
          <div className="status-pill live">
            <span className="live-dot" />
            System Online
          </div>
          <div className="status-pill">
            Jakarta, DKI
          </div>
        </div>
      </header>

      <main className="main">
        {page === "home"  && <Home setRiskLevel={setRiskLevel} riskLevel={riskLevel} />}
        {page === "alert" && <Alert riskLevel={riskLevel} />}
      </main>

      <footer className="footer">
        <span>deFlood.ai — Jakarta Flood Intelligence System</span>
        <span>XGBoost · 16 features · AUC-ROC 0.945 · &lt;1s latency</span>
      </footer>
    </div>
  );
}
