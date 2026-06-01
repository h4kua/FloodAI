import { useState } from "react";
import { sendToFloodAgent } from "../lib/floodAgent";

const WELCOME =
  "Halo, saya deFlood.ai — asisten informasi banjir Jakarta. Silakan tanyakan apa saja seputar kondisi banjir, panduan evakuasi, atau langkah keselamatan.";

export function useChat(riskContext = {}) {
  const [messages, setMessages] = useState([
    { role: "assistant", content: WELCOME },
  ]);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (text) => {
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const result = await sendToFloodAgent(text, history, riskContext);

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: result.reply },
    ]);
    setLoading(false);
  };

  return { messages, loading, sendMessage };
}
