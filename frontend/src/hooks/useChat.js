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

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const result = await sendToFloodAgent(text, history, riskContext, lang);

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: result.reply },
    ]);
    setLoading(false);
  };

  return { messages, loading, sendMessage };
}
