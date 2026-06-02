import { useState } from "react";
import { sendToFloodAgent } from "../lib/floodAgent";
import { translate } from "../lib/translations";

export function useChat(riskContext = {}, lang = "id") {
  const welcome = translate(lang, "chat.welcome");
  const [messages, setMessages] = useState([
    { role: "assistant", content: welcome },
  ]);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (text) => {
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const result = await sendToFloodAgent(text, history, riskContext, lang);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.reply },
      ]);
    } catch {
      const fallback = lang === "en"
        ? "An unexpected error occurred. For emergencies: BPBD 117 · Basarnas 115."
        : "Terjadi kesalahan tidak terduga. Darurat: BPBD 117 · Basarnas 115.";
      setMessages((prev) => [...prev, { role: "assistant", content: fallback }]);
    } finally {
      setLoading(false);
    }
  };

  return { messages, loading, sendMessage };
}
