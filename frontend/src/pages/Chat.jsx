import { useState, useRef, useEffect } from "react";
import { useChat } from "../hooks/useChat";
import { quickReplies } from "../lib/floodAgent";
import EmergencyContacts from "../components/EmergencyContacts";

export default function Chat({ riskLevel = "waspada" }) {
  const [input, setInput] = useState("");
  const { messages, loading, sendMessage } = useChat({ level: riskLevel });
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

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}

        {loading && (
          <div className="bubble assistant">
            <div className="typing-dots">
              <span /><span /><span />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="quick-grid">
        {quickReplies.map((text) => (
          <button
            key={text}
            className="quick-btn"
            onClick={() => !loading && sendMessage(text)}
            disabled={loading}
          >
            {text}
          </button>
        ))}
      </div>

      <div className="input-row">
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ketik pertanyaan tentang banjir..."
          disabled={loading}
        />
        <button
          className="btn btn-primary"
          onClick={handleSend}
          disabled={loading || !input.trim()}
          style={{ minWidth: 44, minHeight: 44 }}
        >
          Kirim
        </button>
      </div>

      <EmergencyContacts />
    </>
  );
}
