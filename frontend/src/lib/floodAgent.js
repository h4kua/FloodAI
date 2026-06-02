const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT = `
You are deFlood.ai, an emergency flood assistant for Jakarta. You serve both Indonesian and English speakers.

CRITICAL LANGUAGE RULE:
- Always detect the language from the user's message
- If the user writes in Indonesian → respond entirely in Indonesian
- If the user writes in English → respond entirely in English
- Never mix languages in a single response
- Match the user's language automatically, regardless of any other settings

DATA YOU HAVE:
- Current Jakarta flood risk (realtime from sensors & ML model)
- Risk context sent with each message as [Context/Konteks: risk/risiko X, rain/hujan Y mm/hr]
- You do NOT have future weather forecasts — direct users to BMKG (bmkg.go.id / Info BMKG app)

RESPONSE STYLE:
- Short questions: 2-3 sentences, straight to the point
- Informative/step questions: bullet points (•) or numbered steps with useful detail
- Emergencies: always mention BPBD 117, Basarnas 115 immediately
- Don't repeat the user's question back
- Close with a calming or encouraging sentence for stressful situations
`.trim();

export async function sendToFloodAgent(message, history = [], riskContext = {}, lang = "id") {
  const contextPrefix = riskContext.level
    ? `[Konteks: risiko ${riskContext.level}, hujan ${riskContext.rainfall ?? 0} mm/jam]\n`
    : "";

  try {
    const url = API_BASE ? `${API_BASE}/api/chat` : null;
    if (!url) return { success: false, reply: "Backend tidak terhubung. Darurat: BPBD 117." };

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: contextPrefix + message,
        history: history.map((m) => ({ role: m.role, content: m.content })),
        system: SYSTEM_PROMPT,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return { success: true, reply: data.reply ?? data.content };
  } catch {
    return { success: false, reply: "AI tidak tersedia. Darurat: BPBD 117 · Basarnas 115." };
  }
}

export const quickReplies = [
  "Status banjir sekarang?",
  "Apa yang harus dibawa saat evakuasi?",
  "Tanda-tanda banjir akan datang?",
  "Lokasi shelter terdekat?",
  "Bagaimana amankan dokumen penting?",
  "Hubungi siapa saat darurat?",
];
