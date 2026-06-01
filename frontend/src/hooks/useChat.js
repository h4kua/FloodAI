import { useState } from "react";
import { sendToFloodAgent } from "../lib/floodAgent";

export function useChat(riskContext = {}) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content:
        "Halo! Saya FloodAI 🌊 Siap membantu informasi dan panduan banjir. Ada yang bisa saya bantu?",
    },
  ]);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (text) => {
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const result = await sendToFloodAgent(text, history, riskContext);
    setMessages((prev) => [...prev, { role: "assistant", content: result.reply }]);
    setLoading(false);
  };

  return { messages, loading, sendMessage };
}
