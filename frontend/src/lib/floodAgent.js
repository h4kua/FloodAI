const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

// Concise, structured system prompt — max 3-4 sentences or bullet points
const SYSTEM_PROMPT = `
Kamu adalah deFlood.ai, asisten banjir Jakarta.

ATURAN JAWABAN:
- Maksimal 3-4 kalimat ATAU 3-4 bullet points singkat
- Gunakan bullet points jika ada daftar/langkah
- Bahasa Indonesia, langsung ke inti
- Jangan ulangi pertanyaan
- Jika darurat: sebut BPBD 117 atau Basarnas 115
- JANGAN tulis paragraf panjang
`.trim();

export async function sendToFloodAgent(message, history = [], riskContext = {}) {
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
