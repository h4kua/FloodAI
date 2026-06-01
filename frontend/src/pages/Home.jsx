import { useEffect, useState, useRef } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import { humanizeRiskLevel, humanizeRainfall } from "../lib/humanize";
import { useChat } from "../hooks/useChat";
import { quickReplies } from "../lib/floodAgent";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";

// ── Risk panel (left column) ────────────────────────────
function RiskPanel({ riskData, loading, error, refresh, lastUpdated, level }) {
  const config = humanizeRiskLevel(level);
  const score  = riskData?.riskScore ?? 0;

  const districtRisks = [
    { name: "Jakarta Barat",   score: Math.min(97, score + 12) },
    { name: "Jakarta Utara",   score: Math.min(97, score + 6)  },
    { name: "Jakarta Timur",   score: Math.max(5,  score + 2)  },
    { name: "Jakarta Pusat",   score: Math.max(5,  score - 10) },
    { name: "Jakarta Selatan", score: Math.max(5,  score - 18) },
  ];

  function dotColor(s) {
    if (s >= 80) return "#ff3d5a";
    if (s >= 60) return "#f97316";
    if (s >= 40) return "#f5a623";
    return "#00e5a0";
  }
  function areaLabel(s) {
    if (s >= 80) return "BAHAYA";
    if (s >= 60) return "SIAGA";
    if (s >= 40) return "WASPADA";
    return "AMAN";
  }

  if (loading) return <div className="panel"><LoadingSpinner /></div>;

  if (error) return (
    <div className="panel error-box">
      <p className="error-title">Gagal memuat</p>
      <p className="error-msg">{error}</p>
      <button className="btn btn-ghost" onClick={refresh}>Coba lagi</button>
    </div>
  );

  return (
    <div className="panel fade-up" style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {/* Eyebrow */}
      <p style={{
        fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem",
        letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted-2)",
        marginBottom: "0.375rem",
      }}>// Jakarta · Live</p>

      {/* Big risk number */}
      <div className={`risk-number ${level}`}>{score}</div>

      <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.625rem" }}>
        <span className={`risk-badge ${level}`}>{config.label} · LIVE</span>
      </div>

      <p style={{ fontSize: "0.82rem", color: "var(--muted)", lineHeight: 1.55, marginBottom: "0.875rem" }}>
        {config.desc}
      </p>

      {/* Score bar */}
      <div className="score-bar-wrap" style={{ marginBottom: "0.875rem" }}>
        <div className="score-bar-header">
          <span className="score-bar-label">Skor Risiko</span>
          <span className="score-bar-val" style={{ color: config.color }}>{score}/100</span>
        </div>
        <div className="score-bar-track">
          <div className="score-bar-fill" style={{ width: `${score}%`, background: config.color }} />
        </div>
      </div>

      {/* Stats */}
      <div className="stat-grid" style={{ marginBottom: "0.875rem" }}>
        <div className="stat-card">
          <span className="stat-label">Probabilitas</span>
          <span className={`stat-val ${level}`}>{score}<small>%</small></span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Hujan</span>
          <span className={`stat-val ${level}`}>{riskData?.rainfall ?? 0}<small>mm</small></span>
        </div>
        <div className="stat-card">
          <span className="stat-label">Intensitas</span>
          <span className="stat-val" style={{ fontSize: "0.9rem", paddingTop: "0.2rem" }}>
            {humanizeRainfall(riskData?.rainfall)}
          </span>
        </div>
      </div>

      {/* Nearby districts */}
      <p className="sect-label">Wilayah DKI</p>
      <div className="area-list" style={{ marginBottom: "0.875rem" }}>
        {districtRisks.map((d) => (
          <div className="area-row" key={d.name}>
            <span className="area-dot" style={{ background: dotColor(d.score), boxShadow: `0 0 8px ${dotColor(d.score)}88` }} />
            <div className="area-meta">
              <p className="area-name">{d.name}</p>
              <p className="area-sub">{areaLabel(d.score)} · {d.score}%</p>
            </div>
            <span className="area-arrow">›</span>
          </div>
        ))}
      </div>

      {/* Update row */}
      <div className="update-row">
        <span className="updated-at">
          {lastUpdated
            ? `Updated ${lastUpdated.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })} WIB`
            : "Belum ada data"}
        </span>
        <button className="btn btn-ghost" onClick={refresh}>Refresh</button>
      </div>
    </div>
  );
}

// ── Chat panel (right column) ───────────────────────────
function ChatPanel({ riskLevel, riskData }) {
  const riskContext = { level: riskLevel, rainfall: riskData?.rainfall };
  const { messages, loading, sendMessage } = useChat(riskContext);
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    await sendMessage(text);
  };

  return (
    <div className="panel fade-up" style={{ display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div className="chat-header">
        <div className="ai-avatar">AI</div>
        <div>
          <p className="chat-title">deFlood Assistant</p>
          <div className="chat-status">
            <span className="online-dot" />
            <span>online</span>
            <span>·</span>
            <span style={{ background: "var(--cyan-soft)", border: "1px solid var(--cyan-border)", borderRadius: "999px", padding: "2px 6px", fontSize: "0.65rem", letterSpacing: "0.06em" }}>
              Groq · llama-3.3-70b
            </span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            <div className="bubble">
              <pre>{m.content}</pre>
            </div>
          </div>
        ))}
        {loading && (
          <div className="message assistant">
            <div className="bubble">
              <div className="typing-dots"><span /><span /><span /></div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick replies */}
      <div className="quick-grid">
        {quickReplies.slice(0, 4).map((q) => (
          <button key={q} className="quick-chip" onClick={() => !loading && sendMessage(q)} disabled={loading}>
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="input-row">
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Tanya tentang banjir Jakarta..."
          disabled={loading}
        />
        <button className="chat-send" onClick={handleSend} disabled={loading || !input.trim()}>
          ▶
        </button>
      </div>
    </div>
  );
}

// ── Home page ───────────────────────────────────────────
export default function Home({ setRiskLevel, riskLevel }) {
  const { riskData, loading, lastUpdated, error, refresh } = useFloodRisk();

  useEffect(() => {
    if (riskData?.level) setRiskLevel(riskData.level);
  }, [riskData, setRiskLevel]);

  const level = riskData?.level ?? riskLevel ?? "waspada";

  return (
    <>
      <div className="page-bar fade-up">
        <div>
          <p className="page-eyebrow">// Hydra / Operator Dashboard</p>
          <h2 className="page-title">Jakarta Flood Intelligence</h2>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          {["Dashboard", "Map", "Chat"].map((t, i) => (
            <div key={t} style={{
              padding: "0.45rem 0.875rem", borderRadius: "10px",
              border: "1px solid var(--line)",
              background: i === 0 ? "var(--cyan-soft)" : "rgba(255,255,255,0.03)",
              color: i === 0 ? "var(--cyan)" : "var(--muted)",
              fontFamily: "'JetBrains Mono',monospace", fontSize: "0.72rem",
              fontWeight: 600,
            }}>{t}</div>
          ))}
        </div>
      </div>

      <div className="dashboard-grid">
        {/* Left: risk data */}
        <RiskPanel
          riskData={riskData} loading={loading} error={error}
          refresh={refresh} lastUpdated={lastUpdated} level={level}
        />

        {/* Center: Jakarta map */}
        <div className="map-panel fade-up">
          <FloodMap riskScore={riskData?.riskScore ?? 45} level={level} />
        </div>

        {/* Right: AI chat */}
        <ChatPanel riskLevel={level} riskData={riskData} />
      </div>

      {/* Interpretation */}
      {riskData?.interpretation && (
        <div className="interpretation fade-up">
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "var(--cyan)", letterSpacing: "0.1em", textTransform: "uppercase", marginRight: 8 }}>
            Model Output
          </span>
          {riskData.interpretation}
        </div>
      )}
    </>
  );
}
