const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT = `
LANGUAGE RULE — NON-NEGOTIABLE:
Detect the language of the user's LAST message. Respond ENTIRELY in that language.
- User writes English → respond fully in English
- User writes Indonesian → respond fully in Indonesian

You are Flo, deFlood.ai's flood intelligence assistant for Jakarta.

RESPONSE LENGTH (STRICT — most important rule):
- Maximum 2–3 sentences for simple questions. Never more than 4.
- If a list is needed: max 4 bullet points, each under 10 words.
- Total response under 60 words. Cut ruthlessly. Dense > long.
- Emergency (flooding now / trapped): 1 sentence empathy + 1 action + number. Done.

VOICE:
- Like a calm, knowledgeable neighbor texting you
- Indonesian: "kamu" not "Anda", use "Nah,", "Kalau,", "Yang penting,"
- English: casual but clear — "So,", "Quick heads-up:", "Main thing:"
- Never robotic. Never repeat the question.

EXAMPLE — GOOD:
User: "Jakarta Barat aman ga sekarang?"
Flo: "Saat ini Jakarta Barat dalam kondisi siaga — beberapa sensor TMA naik. Kalau kamu di area rendah, pantau terus dan siapkan tas darurat. Butuh shelter? BPBD 117."

EXAMPLE — BAD (too long):
Flo: "Jakarta Barat saat ini sedang mengalami kondisi yang cukup mengkhawatirkan. Berdasarkan data dari sensor TMA DSDADKI yang kami pantau secara realtime..."

DATA:
- Realtime flood risk: 38+ TMA sensors + XGBoost ML (updates every 15 min)
- Risk context: [flood_risk: LEVEL | rainfall: X mm/h] injected per message
- No forecasts — refer to BMKG bmkg.go.id for that
`.trim();

const OFFLINE_KB = {
  id: {
    evakuasi: `Siapkan tas darurat sebelum banjir datang: KTP/KK, obat, pakaian 3 hari, senter, power bank, uang tunai — semua dalam plastik kedap air. Hubungi BPBD 117 untuk info shelter aktif terdekat.`,

    status: `Status banjir update tiap 15 menit dari 38+ sensor TMA DSDADKI. Cek Skor Risiko dan kondisi per wilayah di halaman Command Center. Kalau semua hijau, kondisi aman — pantau lebih sering saat cuaca buruk.`,

    tanda: `Tanda banjir mau datang: hujan 30+ menit tidak berhenti, air selokan naik dan keruh, bau tanah basah kuat, ada alert BMKG. Kalau lihat 2–3 sekaligus, langsung siapkan tas darurat.`,

    shelter: `Buka halaman Evakuasi di menu atas → ketik alamatmu → dapat rute ke shelter terdekat. Atau langsung hubungi BPBD Jakarta di 117 — mereka siaga 24 jam dan tahu titik pengungsian yang aktif.`,

    kontak: `Nomor darurat yang wajib disimpan sekarang:\n• BPBD Jakarta: 117\n• Basarnas: 115\n• Ambulans: 118 / 119\n• Call Center DKI: 112`,

    dokumen: `Foto/scan KTP, KK, sertifikat, BPJS → simpan di Google Drive atau email sendiri. Aslinya masukkan ke plastik zip-lock kedap air, dan bawa serta saat evakuasi.`,

    cuaca: `Untuk prakiraan cuaca, cek BMKG di bmkg.go.id atau app Info BMKG. deFlood.ai fokus ke kondisi realtime, bukan prediksi ke depan. Hujan >50 mm/jam tergolong ekstrem dan bisa picu banjir kilat.`,

    pasca: `Sebelum masuk rumah: matikan listrik di MCB, cek struktur bangunan dari luar. Saat bersih-bersih pakai sarung tangan + sepatu boot, buang semua makanan yang kena air banjir. Waspadai leptospirosis — ke Puskesmas kalau ada yang sakit.`,

    prediksi: `Skor Risiko 0–100: <30 Normal, 30–55 Waspada, 55–80 Siaga 2, >80 Siaga 1. Update tiap 15 menit dari sensor + model XGBoost (akurasi ~94%). Kombinasikan dengan kondisi sekitarmu ya.`,

    pompa: `Jakarta punya 600+ pompa banjir (DSDADKI). Titik utama: Pluit, Ancol, Muara Baru, Manggarai. Laporkan pompa rusak ke Call Center DKI 112 atau Dinas SDA 021-3855555.`,
  },

  en: {
    evakuasi: `Pack an emergency bag before the flood hits: ID docs, meds, 3 days of clothes, flashlight, power bank, cash — all in a waterproof bag. Call BPBD at 117 for the nearest active shelter.`,

    status: `Jakarta flood status updates every 15 minutes from 38+ DSDADKI sensors. Check the Risk Score and per-district status on the Command Center page. Green across the board means safe — monitor more often in bad weather.`,

    tanda: `Warning signs: rain not stopping for 30+ minutes, drains rising and turning murky, strong smell of wet earth, BMKG alert active. If you see 2–3 at once, start preparing your emergency bag now.`,

    shelter: `Open the Evacuation page → enter your address → get a route to the nearest shelter. Or call BPBD Jakarta at 117 — they're available 24 hours and know which shelters are active.`,

    kontak: `Save these now:\n• BPBD Jakarta: 117\n• Basarnas (SAR): 115\n• Ambulance: 118 / 119\n• DKI Call Center: 112`,

    dokumen: `Photo/scan your ID, family card, land certificate, BPJS → save to Google Drive or email yourself. Put originals in a waterproof zip-lock bag and bring them when evacuating.`,

    cuaca: `For weather forecasts, check BMKG at bmkg.go.id or the Info BMKG app. deFlood.ai uses realtime data, not future forecasts. Rain above 50 mm/h is extreme and can trigger flash floods.`,

    pasca: `Before entering: turn off electricity at the breaker, check structure from outside. During cleanup: wear gloves and boots, throw out flood-touched food. Watch for leptospirosis — see a clinic if anyone gets sick after.`,

    prediksi: `Risk Score 0–100: <30 Normal, 30–55 Watch, 55–80 Alert 2, >80 Alert 1. Updates every 15 min from sensors + XGBoost ML (~94% accuracy). Combine with what you see around you.`,

    pompa: `Jakarta has 600+ flood pumps (DSDADKI). Main stations: Pluit, Ancol, Muara Baru, Manggarai. Report broken pumps to DKI Call Center 112 or Dinas SDA 021-3855555.`,
  },
};

function _matchOffline(text, lang) {
  const t = text.toLowerCase();
  const kb = OFFLINE_KB[lang] ?? OFFLINE_KB.id;
  if (t.includes("bawa") || t.includes("tas") || t.includes("evakuasi") || t.includes("evacuati") || t.includes("bring") || t.includes("pack")) return kb.evakuasi;
  if (t.includes("status") || t.includes("sekarang") || t.includes("current") || t.includes("kondisi") || t.includes("condition")) return kb.status;
  if (t.includes("tanda") || t.includes("sign") || t.includes("gejala") || t.includes("coming") || t.includes("akan datang")) return kb.tanda;
  if (t.includes("shelter") || t.includes("pengungsian") || t.includes("tempat aman") || t.includes("refuge")) return kb.shelter;
  if (t.includes("kontak") || t.includes("contact") || t.includes("nomor") || t.includes("telepon") || t.includes("phone") || t.includes("hubungi") || t.includes("call")) return kb.kontak;
  if (t.includes("dokumen") || t.includes("document") || t.includes("surat") || t.includes("secure") || t.includes("amankan")) return kb.dokumen;
  if (t.includes("cuaca") || t.includes("weather") || t.includes("prakiraan") || t.includes("forecast") || t.includes("hujan") || t.includes("rain") || t.includes("bmkg")) return kb.cuaca;
  if (t.includes("pasca") || t.includes("setelah banjir") || t.includes("after flood") || t.includes("surut") || t.includes("bersih") || t.includes("clean up") || t.includes("sakit") || t.includes("leptospir") || t.includes("penyakit")) return kb.pasca;
  if (t.includes("prediksi") || t.includes("predict") || t.includes("skor") || t.includes("score") || t.includes("siaga") || t.includes("waspada") || t.includes("akurasi") || t.includes("cara baca") || t.includes("how to read")) return kb.prediksi;
  if (t.includes("pompa") || t.includes("pump") || t.includes("drainase") || t.includes("drainage") || t.includes("saluran") || t.includes("got") || t.includes("dsdadki")) return kb.pompa;
  return null;
}

export async function sendToFloodAgent(message, history = [], riskContext = {}, lang = "id") {
  const contextPrefix = riskContext.level
    ? `[flood_risk: ${riskContext.level} | rainfall: ${riskContext.rainfall ?? 0} mm/h]\n`
    : "";

  const controller = new AbortController();
  const chatTimer = setTimeout(() => controller.abort(), 25000);
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: contextPrefix + message,
        history: history.map((m) => ({ role: m.role, content: m.content })),
        system: SYSTEM_PROMPT,
      }),
      signal: controller.signal,
    });

    if (res.ok) {
      const data = await res.json();
      const reply = data.reply ?? data.content;
      if (reply) return { success: true, reply, isAI: true };
    }
    console.warn("[deFlood] chat backend returned", res.status);
  } catch (err) {
    console.warn("[deFlood] chat backend unreachable:", err?.message ?? err);
  } finally {
    clearTimeout(chatTimer);
  }

  const offline = _matchOffline(message, lang);
  if (offline) return { success: true, reply: offline, isAI: false };

  const generic = lang === "en"
    ? "I'm offline right now. For emergencies: BPBD 117 · Basarnas 115 · Ambulance 119.\nTry asking about evacuation bags, flood warning signs, shelter locations, or emergency contacts."
    : "AI lagi offline. Darurat: BPBD 117 · Basarnas 115 · Ambulans 119.\nCoba tanya soal tas evakuasi, tanda-tanda banjir, lokasi shelter, atau kontak darurat.";
  return { success: false, reply: generic, isAI: false };
}

export const quickReplies = [
  "Kondisi banjir Jakarta sekarang?",
  "Apa yang perlu dibawa saat evakuasi?",
  "Bagaimana tanda-tanda banjir akan datang?",
  "Shelter atau tempat aman terdekat?",
  "Cara baca Skor Risiko di sini?",
  "Apa yang harus dilakukan setelah banjir surut?",
  "Hubungi siapa saat darurat?",
  "Prakiraan cuaca Jakarta?",
];
