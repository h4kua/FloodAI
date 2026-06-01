const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT = `
Kamu adalah FloodAI, asisten AI sistem peringatan banjir Indonesia.
Gunakan Bahasa Indonesia yang sederhana dan mudah dipahami masyarakat umum.
Selalu tenang, empatis, dan berikan langkah konkret.
Jika darurat, sarankan hubungi BPBD: 117 atau Basarnas: 115.
`;

export async function sendToFloodAgent(message, history = [], riskContext = {}) {
  const contextPrefix = riskContext.level
    ? `[Konteks: Level risiko ${riskContext.level}, curah hujan ${riskContext.rainfall ?? "tidak diketahui"} mm/jam]\n`
    : "";

  try {
    // Route through backend proxy — never expose API key in browser.
    const url = API_BASE ? `${API_BASE}/api/chat` : null;

    if (!url) {
      return {
        success: false,
        reply: "Layanan chat membutuhkan backend. Untuk darurat hubungi BPBD: 117",
      };
    }

    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: contextPrefix + message,
        history: history.map((m) => ({ role: m.role, content: m.content })),
        system: SYSTEM_PROMPT,
      }),
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return { success: true, reply: data.reply ?? data.content };
  } catch {
    return {
      success: false,
      reply: "Maaf, asisten AI tidak tersedia saat ini. Untuk darurat hubungi BPBD: 117",
    };
  }
}

export const quickReplies = [
  { icon: "🏠", text: "Apakah rumah saya aman dari banjir?" },
  { icon: "🚶", text: "Ke mana saya harus mengungsi?" },
  { icon: "📦", text: "Apa yang harus dibawa saat evakuasi?" },
  { icon: "📞", text: "Siapa yang harus dihubungi saat banjir?" },
  { icon: "⚠️", text: "Apa tanda-tanda banjir akan datang?" },
  { icon: "👨‍👩‍👧", text: "Bagaimana melindungi anak-anak saat banjir?" },
];
