const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT = `
Kamu adalah deFlood.ai, asisten AI sistem peringatan banjir Indonesia.
Gunakan Bahasa Indonesia yang jelas, ringkas, dan mudah dipahami masyarakat umum.
Selalu tenang, empatis, dan berikan langkah konkret yang bisa langsung dilakukan.
Hindari jargon teknis. Jika kondisi darurat, sarankan hubungi BPBD: 117 atau Basarnas: 115.
`.trim();

export async function sendToFloodAgent(message, history = [], riskContext = {}) {
  const contextPrefix = riskContext.level
    ? `[Konteks sistem: Level risiko saat ini ${riskContext.level}, curah hujan ${riskContext.rainfall ?? "tidak diketahui"} mm/jam]\n\n`
    : "";

  try {
    const url = API_BASE ? `${API_BASE}/api/chat` : null;

    if (!url) {
      return {
        success: false,
        reply:
          "Layanan chat membutuhkan koneksi ke server. Untuk kondisi darurat, hubungi BPBD: 117.",
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
      reply:
        "Asisten AI tidak dapat dijangkau saat ini. Untuk kondisi darurat, hubungi BPBD: 117.",
    };
  }
}

export const quickReplies = [
  "Apa tanda-tanda banjir akan datang?",
  "Ke mana saya harus mengungsi?",
  "Apa yang harus dibawa saat evakuasi?",
  "Bagaimana mengamankan rumah dari banjir?",
  "Siapa yang harus dihubungi saat darurat?",
  "Bagaimana melindungi anak-anak saat banjir?",
];
