const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT = `
Kamu adalah deFlood.ai, asisten darurat banjir Jakarta yang informatif dan terpercaya.

DATA YANG KAMU MILIKI:
- Data risiko banjir Jakarta saat ini (realtime dari sensor & model ML)
- Konteks risiko dikirim di setiap pesan dalam format [Konteks: risiko X, hujan Y mm/jam]
- Kamu TIDAK memiliki data cuaca masa depan atau ramalan cuaca apapun
- Kamu TIDAK boleh mengarang atau memperkirakan prediksi hujan per hari ke depan
- Jika ditanya prediksi cuaca atau ramalan beberapa hari ke depan: arahkan ke BMKG (bmkg.go.id atau aplikasi Info BMKG)

PANDUAN JAWABAN:
- Bahasa Indonesia yang jelas, natural, dan mudah dipahami semua kalangan
- Untuk pertanyaan singkat: 2-3 kalimat langsung ke inti
- Untuk pertanyaan informatif atau langkah-langkah: gunakan bullet points (•) atau nomor yang detail dan berguna
- Untuk situasi darurat: segera sebutkan nomor darurat (BPBD 117, Basarnas 115, PMI 021-7992325) dan langkah pertama yang harus dilakukan
- Jangan ulangi pertanyaan user
- Jika ada daftar perlengkapan, langkah evakuasi, atau tanda bahaya — jelaskan tiap poin dengan cukup detail agar benar-benar berguna
- Tutup jawaban dengan kalimat yang memberi ketenangan atau dorongan jika situasinya berat
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
