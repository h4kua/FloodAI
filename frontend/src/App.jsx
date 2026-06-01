import { useState } from "react";
import Home from "./pages/Home";
import Alert from "./pages/Alert";
import Chat from "./pages/Chat";
import AlertBanner from "./components/AlertBanner";

const navItems = [
  { id: "home",  label: "🏠 Beranda" },
  { id: "alert", label: "⚠️ Peringatan" },
  { id: "chat",  label: "💬 Tanya AI" },
];

export default function App() {
  const [page, setPage] = useState("home");
  const [riskLevel, setRiskLevel] = useState("waspada");

  return (
    <div style={{ minHeight: "100vh", background: "#0f172a", color: "#f1f5f9", fontFamily: "system-ui, sans-serif" }}>
      <AlertBanner level={riskLevel} />

      <nav style={{ display: "flex", gap: "4px", padding: "8px 16px", background: "#1e293b", borderBottom: "1px solid #334155" }}>
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setPage(item.id)}
            style={{
              background: page === item.id ? "#3b82f6" : "transparent",
              color: page === item.id ? "white" : "#94a3b8",
              border: "none",
              borderRadius: "8px",
              padding: "10px 16px",
              fontSize: "15px",
              cursor: "pointer",
              fontWeight: page === item.id ? "600" : "400",
              minHeight: "44px",
            }}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <main>
        {page === "home"  && <Home setRiskLevel={setRiskLevel} />}
        {page === "alert" && <Alert riskLevel={riskLevel} />}
        {page === "chat"  && <Chat riskLevel={riskLevel} />}
      </main>

      <footer style={{ textAlign: "center", padding: "24px 16px", color: "#475569", fontSize: "13px", borderTop: "1px solid #1e293b" }}>
        © {new Date().getFullYear()} FloodAI — Sistem Peringatan Banjir Jakarta
      </footer>
    </div>
  );
}
