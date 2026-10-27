import { useState, useRef, useEffect } from "react";
import { useChat } from "../hooks/useChat";
import { useT, useApp } from "../lib/appContext";

/* AI answers arrive as light markdown: **bold**, "* " or "- " bullets,
   "1. " steps, "### " headings. They are rendered as text elements, so no
   asterisks show and no HTML from the model is ever injected. */
function inline(text, keyBase) {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, i) =>
    part.length > 4 && part.startsWith("**") && part.endsWith("**")
      ? <strong key={`${keyBase}-${i}`}>{part.slice(2, -2)}</strong>
      : part.replace(/\*(\S[^*]*?)\*/g, "$1"));
}

function MessageText({ text }) {
  const blocks = [];
  let list = null;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = line.match(/^[*\-•]\s+(.*)$/);
    const step = line.match(/^\d+[.)]\s+(.*)$/);
    if (bullet || step) {
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) { list = { type, items: [] }; blocks.push(list); }
      list.items.push((bullet || step)[1]);
      continue;
    }
    list = null;
    if (!line || /^[-*_]{3,}$/.test(line)) continue;   // blank lines and rules
    const heading = line.match(/^#{1,6}\s+(.*)$/);
    blocks.push({ type: heading ? "heading" : "p", text: heading ? heading[1] : line });
  }
  return (
    <div className="msg-text">
      {blocks.map((b, i) => {
        if (b.type === "ul" || b.type === "ol") {
          const List = b.type;
          return <List key={i}>{b.items.map((item, j) => <li key={j}>{inline(item, `${i}-${j}`)}</li>)}</List>;
        }
        return <p key={i} className={b.type === "heading" ? "msg-heading" : undefined}>{inline(b.text, i)}</p>;
      })}
    </div>
  );
}

export default function ChatBot({ riskContext = {} }) {
  const t = useT();
  const { lang } = useApp();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [hasUnread, setHasUnread] = useState(true);
  const { messages, loading, sendMessage, aiOnline } = useChat(riskContext, lang);
  const quickReplies = [
    t("chat.q1"), t("chat.q2"), t("chat.q3"), t("chat.q4"),
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

  // null = probe in-flight, true = AI ready, false = offline KB
  const statusDot   = aiOnline === true ? "online-dot" : "offline-dot";
  const statusLabel = aiOnline === null
    ? (lang === "en" ? "Connecting..." : "Menghubungkan...")
    : aiOnline === false
    ? "Offline (KB)"
    : "AI Online";

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
                  {m.role === "assistant" ? <MessageText text={m.content} /> : <pre>{m.content}</pre>}
                  {/* Show KB badge on offline replies */}
                  {m.role === "assistant" && m.isAI === false && i > 0 && (
                    <span style={{
                      display: "block",
                      marginTop: "0.3rem",
                      fontSize: "0.76rem",
                      opacity: 0.5,
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
        {open ? "✕" : (lang === "en" ? "Ask AI" : "Tanya AI")}
        {!open && hasUnread && <span className="chatbot-unread">1</span>}
      </button>
    </div>
  );
}
