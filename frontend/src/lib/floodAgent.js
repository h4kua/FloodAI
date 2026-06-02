const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT_ID = `
Kamu adalah deFlood.ai, asisten darurat banjir Jakarta yang informatif dan terpercaya.

DATA YANG KAMU MILIKI:
- Data risiko banjir Jakarta saat ini (realtime dari sensor & model ML)
- Konteks risiko dikirim di setiap pesan dalam format [Konteks: risiko X, hujan Y mm/jam]
- Kamu TIDAK memiliki data cuaca masa depan atau ramalan cuaca apapun
- Kamu TIDAK boleh mengarang prediksi hujan per hari ke depan
- Jika ditanya prediksi cuaca: arahkan ke BMKG (bmkg.go.id atau aplikasi Info BMKG)

PANDUAN JAWABAN:
- Bahasa Indonesia yang jelas, natural, dan mudah dipahami semua kalangan
- Untuk pertanyaan singkat: 2-3 kalimat langsung ke inti
- Untuk pertanyaan informatif atau langkah-langkah: gunakan bullet points (•) atau nomor yang detail
- Untuk situasi darurat: sebut nomor darurat (BPBD 117, Basarnas 115, PMI 021-7992325)
- Jangan ulangi pertanyaan user
- Tutup jawaban dengan kalimat yang memberi ketenangan jika situasinya berat
`.trim();

const SYSTEM_PROMPT_EN = `
You are deFlood.ai, a trusted emergency flood assistant for Jakarta.

DATA YOU HAVE ACCESS TO:
- Current Jakarta flood risk data (realtime from sensors & ML model)
- Risk context sent with each message in format [Context: risk X, rain Y mm/hr]
- You do NOT have access to future weather forecasts
- Do NOT fabricate multi-day rainfall predictions
- For weather forecasts: direct users to BMKG (bmkg.go.id or Info BMKG app)

RESPONSE GUIDELINES:
- Clear, natural English accessible to all users
- Short questions: 2-3 sentences, straight to the point
- Informative questions: use bullet points (•) or numbered steps with useful detail
- Emergencies: mention emergency numbers (BPBD 117, Basarnas 115) immediately
- Don't repeat the user's question
- Close with an encouraging or calming sentence in stressful situations
`.trim();

export async function sendToFloodAgent(message, history = [], riskContext = {}, lang = "id") {
  const SYSTEM_PROMPT = lang === "en" ? SYSTEM_PROMPT_EN : SYSTEM_PROMPT_ID;
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
