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

const OFFLINE_KB = {
  id: {
    evakuasi: `Barang wajib saat evakuasi banjir:\n• Dokumen penting (KTP, KK, sertifikat, BPKB)\n• Obat-obatan pribadi & P3K\n• Pakaian untuk 3 hari\n• Air minum & makanan ringan\n• Senter + baterai cadangan, power bank\n• Uang tunai secukupnya\n• Jas hujan atau plastik besar\n\nMasukkan semua ke tas kedap air. Hubungi BPBD 117 untuk info shelter terdekat.`,
    status: `Status banjir Jakarta diperbarui setiap 15 menit dari sensor realtime. Lihat Skor Risiko dan tabel zona di halaman Command Center untuk kondisi saat ini. Jika semua angka 0 dan tidak ada zona siaga, berarti kondisi aman. Pantau terus karena situasi bisa berubah cepat.`,
    tanda: `Tanda-tanda banjir akan datang:\n• Hujan deras > 30 menit tanpa henti\n• Air sungai atau got mulai keruh dan naik\n• Bau tanah basah yang kuat\n• Hewan-hewan (semut, cacing) berpindah ke tempat tinggi\n• Alert BMKG untuk hujan lebat\n• Warna air berubah coklat\n\nJika melihat 3+ tanda, segera siapkan tas darurat dan pantau level sungai terdekat.`,
    shelter: `Untuk menemukan shelter terdekat:\n1. Buka halaman Evakuasi di menu atas\n2. Masukkan alamat Anda\n3. Sistem akan menampilkan rute ke shelter terdekat\n\nAlternatif: Hubungi BPBD Jakarta di 117 atau datangi kantor kelurahan/kecamatan terdekat. Sekolah dan GOR biasanya dijadikan posko pengungsian sementara.`,
    kontak: `Kontak darurat banjir Jakarta:\n• BPBD Jakarta: 117\n• Basarnas: 115\n• PMI Jakarta: (021) 390-6666\n• Ambulans: 118 / 119\n• Damkar: 113\n• Call Center DKI: 112\n\nSimpan nomor-nomor ini di ponsel Anda sebelum dibutuhkan.`,
    dokumen: `Cara mengamankan dokumen penting:\n• Scan/foto semua dokumen → simpan di Google Drive atau email\n• Masukkan aslinya ke plastik zip-lock kedap air\n• Bawa serta saat evakuasi (jangan tinggal di rumah)\n• Prioritaskan: KTP, KK, akta lahir, sertifikat tanah, BPJS\n\nDokumen digital di cloud bisa diakses dari mana saja jika fisik hilang.`,
  },
  en: {
    evakuasi: `Essential items for flood evacuation:\n• Important documents (ID, family card, certificates)\n• Personal medications & first aid kit\n• Clothing for 3 days\n• Drinking water & snacks\n• Flashlight + spare batteries, power bank\n• Sufficient cash\n• Raincoat or large plastic bags\n\nPack everything in a waterproof bag. Call BPBD 117 for nearest shelter info.`,
    status: `Jakarta flood status is updated every 15 minutes from realtime sensors. Check the Risk Score and zone table on the Command Center page for current conditions. If all values show 0 with no alert zones, conditions are safe. Keep monitoring as situations can change rapidly.`,
    tanda: `Signs that flooding is coming:\n• Heavy rain for 30+ minutes without stopping\n• River or drainage water turning murky and rising\n• Strong smell of wet earth\n• Animals (ants, worms) moving to higher ground\n• BMKG alert for heavy rainfall\n• Water turning brown\n\nIf you see 3+ signs, prepare your emergency bag and monitor nearby river levels.`,
    shelter: `To find the nearest shelter:\n1. Open the Evacuation page from the top menu\n2. Enter your address\n3. The system will show the route to the nearest shelter\n\nAlternative: Call BPBD Jakarta at 117 or go to the nearest kelurahan/kecamatan office. Schools and sports halls are typically used as temporary shelters.`,
    kontak: `Emergency contacts for Jakarta flooding:\n• BPBD Jakarta: 117\n• Basarnas (SAR): 115\n• PMI Jakarta: (021) 390-6666\n• Ambulance: 118 / 119\n• Fire Dept: 113\n• DKI Call Center: 112\n\nSave these numbers before you need them.`,
    dokumen: `How to secure important documents:\n• Scan/photo all documents → save to Google Drive or email\n• Put originals in a waterproof zip-lock bag\n• Bring them when evacuating (don't leave at home)\n• Priority: ID card, family card, birth certificate, land certificate, BPJS\n\nDigital documents in the cloud can be accessed from anywhere if the physical copies are lost.`,
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
  if (t.includes("dokumen") || t.includes("document") || t.includes("surat") || t.includes("secure") || t.includes("aman")) return kb.dokumen;
  return null;
}

export async function sendToFloodAgent(message, history = [], riskContext = {}, lang = "id") {
  const contextPrefix = riskContext.level
    ? `[flood_risk: ${riskContext.level} | rainfall: ${riskContext.rainfall ?? 0} mm/h]\n`
    : "";

  // Try backend first
  if (API_BASE) {
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: contextPrefix + message,
          history: history.map((m) => ({ role: m.role, content: m.content })),
          system: SYSTEM_PROMPT,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        return { success: true, reply: data.reply ?? data.content };
      }
    } catch {
      // Fall through to offline KB
    }
  }

  // Offline fallback: keyword matching
  const offline = _matchOffline(message, lang);
  if (offline) return { success: true, reply: offline };

  // Generic offline fallback
  const generic = lang === "en"
    ? "I'm currently offline. For emergencies: BPBD 117 · Basarnas 115 · Ambulance 119.\n\nYou can ask me about: what to pack for evacuation, flood warning signs, nearest shelter, or emergency contacts."
    : "AI sedang offline. Darurat: BPBD 117 · Basarnas 115 · Ambulans 119.\n\nAnda bisa tanya: barang yang dibawa saat evakuasi, tanda-tanda banjir, cara menemukan shelter, atau kontak darurat.";
  return { success: false, reply: generic };
}

export const quickReplies = [
  "Status banjir sekarang?",
  "Apa yang harus dibawa saat evakuasi?",
  "Tanda-tanda banjir akan datang?",
  "Lokasi shelter terdekat?",
  "Bagaimana amankan dokumen penting?",
  "Hubungi siapa saat darurat?",
];
