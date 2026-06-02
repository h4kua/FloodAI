const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT = `
LANGUAGE RULE — HIGHEST PRIORITY, OVERRIDE EVERYTHING ELSE:
Detect the language of the user's LAST message. Respond ONLY in that same language.
- User writes English → your ENTIRE response must be in English
- User writes Indonesian → your ENTIRE response must be in Indonesian
- NEVER switch languages mid-response. NEVER default to Indonesian if user writes English.

You are deFlood.ai, Jakarta emergency flood assistant (bilingual: Indonesian/English).

DATA:
- Current Jakarta flood risk from realtime sensors & ML model
- Risk context: [flood_risk: LEVEL | rainfall: X mm/h] in each message
- No access to future weather forecasts → direct to BMKG (bmkg.go.id)

RESPONSE STYLE:
- Short factual questions: 2-3 sentences, direct
- Step-by-step questions: bullet (•) or numbered list, each point with useful detail
- Emergencies: immediately state BPBD 117, Basarnas 115
- Do not repeat the question
- End with a brief reassuring sentence when situation is stressful
`.trim();

export async function sendToFloodAgent(message, history = [], riskContext = {}, lang = "id") {
  const contextPrefix = riskContext.level
    ? `[flood_risk: ${riskContext.level} | rainfall: ${riskContext.rainfall ?? 0} mm/h]\n`
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
