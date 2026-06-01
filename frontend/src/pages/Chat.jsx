import { useState } from "react";
import { useChat } from "../hooks/useChat";
import { quickReplies } from "../lib/floodAgent";
import EmergencyContacts from "../components/EmergencyContacts";

export default function Chat({ riskLevel = "waspada" }) {
  const [input, setInput] = useState("");
  const { messages, loading, sendMessage } = useChat({ level: riskLevel });

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    await sendMessage(text);
  };

  const s = {
    container: { maxWidth: "600px", margin: "0 auto", padding: "16px", display: "flex", flexDirection: "column", gap: "16px" },
    messages:  { background: "#1e293b", borderRadius: "12px", padding: "16px", minHeight: "300px", maxHeight: "420px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "12px" },
    bubble: (role) => ({
      background: role === "user" ? "#1d4ed8" : "#0f172a",
      color: "white",
      padding: "10px 14px",
      borderRadius: role === "user" ? "12px 12px 4px 12px" : "12px 12px 12px 4px",
      alignSelf: role === "user" ? "flex-end" : "flex-start",
      maxWidth: "85%",
      fontSize: "15px",
      lineHeight: "1.5",
    }),
    inputRow:  { display: "flex", gap: "8px" },
    input:     { flex: 1, background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", padding: "12px", color: "white", fontSize: "16px", outline: "none" },
    btn:       { background: "#3b82f6", color: "white", border: "none", borderRadius: "8px", padding: "12px 16px", fontSize: "16px", cursor: "pointer", minHeight: "44px", minWidth: "44px" },
    quickGrid: { display: "flex", flexWrap: "wrap", gap: "8px" },
    quickBtn:  { background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", padding: "8px 12px", color: "#e2e8f0", fontSize: "14px", cursor: "pointer", minHeight: "44px" },
  };

  return (
    <div style={s.container}>
      <div style={s.messages}>
        {messages.map((m, i) => (
          <div key={i} style={s.bubble(m.role)}>
            {m.role === "assistant" && <span style={{ marginRight: "6px" }}>🌊</span>}
            {m.content}
          </div>
        ))}
        {loading && (
          <div style={s.bubble("assistant")}>
            🌊 <em style={{ color: "#94a3b8" }}>Sedang mengetik...</em>
          </div>
        )}
      </div>

      <div style={s.quickGrid}>
        {quickReplies.slice(0, 4).map((q) => (
          <button key={q.text} style={s.quickBtn} onClick={() => sendMessage(q.text)}>
            {q.icon} {q.text}
          </button>
        ))}
      </div>

      <div style={s.inputRow}>
        <input
          style={s.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Ketik pertanyaan Anda..."
          disabled={loading}
        />
        <button style={s.btn} onClick={handleSend} disabled={loading}>
          ➤
        </button>
      </div>

      <EmergencyContacts />
    </div>
  );
}
