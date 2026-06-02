import { useState, useRef, useEffect } from "react";
import { useChat } from "../hooks/useChat";
import { useT, useApp } from "../lib/appContext";

export default function ChatBot({ riskContext = {} }) {
  const t = useT();
  const { lang } = useApp();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [hasUnread, setHasUnread] = useState(true);
  const { messages, loading, sendMessage, aiOnline } = useChat(riskContext, lang);
  const quickReplies = [
    t("chat.q1"), t("chat.q2"), t("chat.q3"),
    t("chat.q4"), t("chat.q5"), t("chat.q6"),
  ];
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open) {
      setHasUnread(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 60);
    }
  }, [open, messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    await sendMessage(text);
  };

  // Status indicator: null = belum ada percobaan, true = AI, false = offline KB
  const statusDot   = aiOnline === false ? "offline-dot" : "online-dot";
  const statusLabel = aiOnline === false
    ? (lang === "en" ? "Offline (KB)" : "Offline (KB)")
    : (lang === "en" ? "AI Online" : "AI Online");

  return (
    <div className="chatbot-fab">
      {open && (
        <div className="chatbot-panel">
          {/* Header */}
          <div className="chatbot-header">
            <div className="ai-avatar">AI</div>
            <div>
              <p className="chatbot-title">{t("chat.title")}</p>
              <div className="chatbot-status">
                <span className={statusDot} />
                <span>{statusLabel}</span>
              </div>
            </div>
            <button className="chatbot-close" onClick={() => setOpen(false)} aria-label="Tutup chat">
              ✕
            </button>
          </div>

          {/* Messages */}
          <div className="chatbot-messages">
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="msg-bubble">
                  <pre>{m.content}</pre>
                  {/* Show KB badge on offline replies */}
                  {m.role === "assistant" && m.isAI === false && i > 0 && (
                    <span style={{
                      display: "block",
                      marginTop: "0.3rem",
                      fontSize: "0.6rem",
                      opacity: 0.5,
                      fontFamily: "'JetBrains Mono', monospace",
                      letterSpacing: "0.05em",
                    }}>
                      {lang === "en" ? "offline KB" : "offline KB"}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="msg assistant">
                <div className="msg-bubble">
                  <div className="typing-dots"><span /><span /><span /></div>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Quick replies */}
          <div className="chatbot-quickies">
            {quickReplies.map((q) => (
              <button key={q} className="quickie" onClick={() => !loading && sendMessage(q)} disabled={loading}>
                {q}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="chatbot-input-row">
            <input
              className="chatbot-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder={t("chat.placeholder")}
              disabled={loading}
            />
            <button
              className="chatbot-send"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              aria-label="Kirim"
            >
              ▶
            </button>
          </div>
        </div>
      )}

      {/* FAB toggle */}
      <button
        className="chatbot-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Tutup chat" : "Buka chat AI"}
      >
        {open ? "✕" : "AI"}
        {!open && hasUnread && <span className="chatbot-unread">1</span>}
      </button>
    </div>
  );
}
