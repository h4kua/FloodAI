import { useState } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";

const NAV = [
  { id: "home",  label: "Command Center" },
  { id: "alert", label: "Evakuasi"       },
];

export default function App() {
  const [page, setPage] = useState("home");
  const [riskContext, setRiskContext] = useState({ level: "waspada", rainfall: 0 });

  return (
    <div className="shell">
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
          <div className="chip live">
            <span className="live-dot" />
            System Online
          </div>
          <div className="chip">Jakarta, DKI</div>
        </div>
      </header>

      <main className="main">
        {page === "home"  && <Home setRiskContext={setRiskContext} riskLevel={riskContext.level} />}
        {page === "alert" && <Alert riskLevel={riskContext.level} rainfall={riskContext.rainfall} />}
      </main>

      <footer className="footer">
        <span>deFlood.ai — Jakarta Flood Intelligence System · Operator BPBD</span>
        <span>XGBoost · 16 features · AUC-ROC 0.945 · ECE 0.38 · &lt;1s latency</span>
      </footer>
    </div>
  );
}
