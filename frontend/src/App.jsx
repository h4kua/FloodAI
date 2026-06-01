import { useState } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import Chat from "./pages/Chat";
import AlertBanner from "./components/AlertBanner";

const NAV = [
  { id: "home",  label: "Dashboard" },
  { id: "alert", label: "Evakuasi" },
  { id: "chat",  label: "Tanya AI" },
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

        <div className="live-badge">
          <span className="live-dot" />
          Live
        </div>
      </header>

      <main className="main">
        {page === "home"  && <Home setRiskLevel={setRiskLevel} />}
        {page === "alert" && <Alert riskLevel={riskLevel} />}
        {page === "chat"  && <Chat riskLevel={riskLevel} />}
      </main>

      <footer className="footer">
        <span>deFlood.ai — Sistem Peringatan Banjir Jakarta</span>
        <span>Data diperbarui otomatis setiap 15 menit</span>
      </footer>
    </div>
  );
}
