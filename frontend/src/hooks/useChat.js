import { useState, useEffect, useRef } from "react";
import { sendToFloodAgent } from "../lib/floodAgent";
import { translate } from "../lib/translations";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function probeGroqHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/chat/health`);
    if (!res.ok) return false;
    const data = await res.json();
    return data.groq_configured === true;
  } catch {
    return false;
  }
}

export function useChat(riskContext = {}, lang = "id") {
  const welcome = translate(lang, "chat.welcome");
  const [messages, setMessages] = useState([
    { role: "assistant", content: welcome, isAI: true },
  ]);
  const [loading, setLoading] = useState(false);
  // null = probe in-flight, true = AI ready, false = offline KB
  const [aiOnline, setAiOnline] = useState(null);
  const probed = useRef(false);
  const messagesRef = useRef(messages);

  useEffect(() => {
    if (probed.current) return;
    probed.current = true;
    probeGroqHealth().then((ok) => setAiOnline(ok));
  }, []);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const sendMessage = async (text) => {
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    try {
      const history = messagesRef.current.map((m) => ({ role: m.role, content: m.content }));
      const result = await sendToFloodAgent(text, history, riskContext, lang);
      setAiOnline(result.isAI === true);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.reply, isAI: result.isAI === true },
      ]);
    } catch {
      setAiOnline(false);
      const fallback = lang === "en"
        ? "An unexpected error occurred. For emergencies: BPBD 117 · Basarnas 115."
        : "Terjadi kesalahan tidak terduga. Darurat: BPBD 117 · Basarnas 115.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: fallback, isAI: false },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return { messages, loading, sendMessage, aiOnline };
}
