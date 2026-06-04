const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const SYSTEM_PROMPT = `
LANGUAGE RULE — NON-NEGOTIABLE:
Detect the language of the user's LAST message. Respond ENTIRELY in that language.
- User writes English → respond fully in English
- User writes Indonesian → respond fully in Indonesian
- NEVER mix languages. NEVER default to Indonesian if user writes English.

You are Flo, deFlood.ai's friendly flood intelligence assistant for Jakarta.

YOUR VOICE & PERSONALITY:
- Warm, calm, and grounding — like a knowledgeable neighbor who genuinely cares
- Speak naturally. Imagine you're texting a friend who just asked about the flood situation
- Lead with empathy when the situation is stressful, then move to information
- Never robotic, never overly formal — conversational but not flippant
- In Indonesian: use "kamu" (not "Anda"), use natural connectors like "Jadi", "Nah", "Kalau", "Yang penting"
- Occasionally open with light affirmations: "Tenang ya,", "Oke,", "Baik,", "Sure,", "Got it —" — but don't overdo it

RESPONSE STYLE — FOLLOW THIS FORMAT:
- 2–4 short paragraphs OR a very short intro + a minimal bullet list
- Start with the current situation or most relevant fact — NOT with "Saya adalah..."
- End with a clear, practical action when relevant
- Emergencies (flooding now, trapped, evacuation urgent): empathize briefly → immediate action → BPBD 117 / Basarnas 115
- Never repeat the user's question back to them
- When it's stressful, close with something calming: "Kamu tidak sendirian ya.", "You've got this."
- Avoid jargon unless the user uses it first

EXAMPLE — GOOD (humanized):
User: "Jakarta Barat kondisinya gimana?"
Flo: "Saat ini Jakarta Barat sedang dalam kondisi siaga — hujan cukup deras dan beberapa sensor TMA menunjukkan level air yang naik.\nKalau kamu ada di area rendah seperti Tambora atau Kembangan, sebaiknya mulai pantau kondisi sekitar dan siapkan tas darurat.\nKalau butuh shelter, BPBD di 117 bisa kasih info titik pengungsian aktif."

EXAMPLE — BAD (robotic):
User: "Jakarta Barat kondisinya gimana?"
Flo: "Jakarta Barat saat ini berada dalam status berikut: [data], [data], [data]."

DATA YOU HAVE:
- Realtime Jakarta flood risk from 38+ TMA sensors + XGBoost ML model (updated every 15 min)
- Risk context injected at start of each session: [flood_risk: LEVEL | rainfall: X mm/h]
- No future weather forecasts — refer users to BMKG (bmkg.go.id / app: Info BMKG) for forecasts
`.trim();

const OFFLINE_KB = {
  id: {
    evakuasi: `Kalau situasinya sudah mengharuskan evakuasi, hal yang paling menyelamatkan waktu adalah tas darurat yang sudah disiapkan sebelum banjir datang — bukan baru dikemas saat air sudah masuk.

Yang wajib ada di dalam tas:
• Dokumen penting asli (KTP, KK, sertifikat tanah) + foto/scan-nya di cloud
• Obat-obatan rutin dan P3K
• Pakaian untuk 2–3 hari + jas hujan
• Air minum dan makanan kering yang tidak mudah basi
• Senter, power bank, baterai cadangan
• Uang tunai secukupnya

Masukkan semua ke tas yang bisa ditutup rapat, atau pakai kresek besar supaya tidak basah. Untuk info shelter terdekat yang aktif saat ini, hubungi BPBD di 117 — mereka siaga 24 jam.`,

    status: `Status banjir Jakarta diperbarui setiap 15 menit langsung dari 38+ sensor TMA DSDADKI. Kamu bisa lihat Skor Risiko dan kondisi tiap wilayah di halaman Command Center.

Kalau angkanya kecil dan tidak ada zona siaga, kondisi masih aman. Tapi situasi bisa berubah cukup cepat — terutama saat hujan deras di hulu — jadi kalau cuaca lagi buruk, pantau lebih sering ya.`,

    tanda: `Banjir biasanya tidak datang tiba-tiba. Ada tanda-tandanya kalau kamu tahu yang harus diperhatikan.

Yang paling sering muncul sebelum banjir:
• Hujan tidak berhenti lebih dari 30–40 menit tanpa jeda
• Air di selokan atau kali mulai naik dan berubah keruh kecokelatan
• Bau tanah basah yang kuat dan tidak biasa
• Semut atau cacing berpindah ke tempat yang lebih tinggi
• Ada peringatan BMKG untuk hujan lebat di sekitar wilayah kamu

Kalau kamu lihat 2–3 dari tanda itu bersamaan, jangan tunggu sampai air masuk rumah. Mulai siapkan tas darurat dan pantau kondisi terkini lewat aplikasi ini atau BMKG.`,

    shelter: `Untuk menemukan shelter atau titik evakuasi terdekat, buka halaman Evakuasi di menu atas dan ketik alamatmu — sistem langsung tampilkan rute ke shelter terdekat.

Alternatif yang lebih cepat: hubungi BPBD Jakarta di 117. Mereka tahu persis titik pengungsian mana yang aktif dan bisa bantu koordinasi evakuasi. Biasanya sekolah dan GOR jadi pilihan pertama BPBD saat kondisi darurat.`,

    kontak: `Simpan nomor-nomor ini sekarang, sebelum kamu benar-benar butuh — lebih baik sudah ada di kontak daripada panik cari-cari saat darurat.

Nomor darurat penting:
• BPBD Jakarta: 117 (koordinasi bencana & evakuasi)
• Basarnas: 115 (pencarian & penyelamatan)
• Ambulans: 118 / 119
• PMI Jakarta: (021) 390-6666
• Pemadam Kebakaran: 113
• Call Center DKI Jakarta: 112

Semuanya gratis, aktif 24 jam.`,

    dokumen: `Dokumen penting itu yang paling susah diganti kalau sudah basah atau hilang kena banjir. Jadi paling aman memang disiapkan jauh sebelum banjir datang.

Yang bisa dilakukan sekarang:
• Foto atau scan semua dokumen — simpan di Google Drive atau kirim ke email sendiri
• Masukkan aslinya ke plastik zip-lock yang kedap air
• Saat evakuasi, bawa fisiknya — jangan ditinggal di rumah

Prioritaskan: KTP, KK, akta lahir, sertifikat tanah, dan kartu BPJS. Kalau fisiknya hilang, versi digital di cloud biasanya masih bisa dipakai untuk pengurusan administrasi awal.`,

    cuaca: `Untuk prakiraan cuaca yang detail, sumber paling terpercaya tetap BMKG — bisa diakses di bmkg.go.id atau aplikasi Info BMKG yang ada di Play Store dan App Store.

deFlood.ai sendiri fokus ke data cuaca realtime dan sensor ketinggian air sekarang — bukan prediksi ke depan. Hujan di atas 50 mm/jam sudah tergolong ekstrem dan bisa memicu banjir kilat, terutama di area yang drainasenya kurang lancar.

Musim hujan Jakarta biasanya November–Maret, puncaknya di Januari–Februari.`,

    pasca: `Setelah banjir surut, godaannya memang langsung masuk dan bersih-bersih. Tapi ada beberapa hal yang perlu dicek dulu supaya aman.

Langkah yang disarankan sebelum dan saat bersih-bersih:
• Lihat kondisi bangunan dari luar dulu — pastikan tidak ada yang retak atau miring
• Matikan listrik dari panel (MCB) sebelum masuk, terutama kalau lantai masih basah
• Pakai sarung tangan karet dan sepatu boot saat bersih-bersih
• Buang semua makanan yang sudah kena air banjir — jangan dikonsumsi
• Buka jendela dan ventilasi selebar mungkin supaya udara bisa berputar

Yang perlu diwaspadai setelah banjir: leptospirosis, diare, dan infeksi kulit — terutama kalau banyak kontak dengan air banjir. Kalau ada yang sakit, segera ke Puskesmas terdekat ya.`,

    prediksi: `Skor Risiko di deFlood.ai itu angka antara 0–100 yang menunjukkan seberapa besar kemungkinan banjir di Jakarta saat ini — dihitung dari kombinasi data cuaca, ketinggian muka air, dan model XGBoost yang dilatih dari data historis.

Cara bacanya:
• Di bawah 30 → Normal, kondisi aman
• 30–55 → Waspada, pantau lebih ketat
• 55–80 → Siaga 2, siapkan tas darurat
• Di atas 80 → Siaga 1, pertimbangkan evakuasi kalau kamu di zona rendah

Data diperbarui tiap 15 menit, akurasi modelnya sekitar 94%. Tapi tetap kombinasikan dengan informasi BMKG dan kondisi sekitar kamu ya — angka model itu alat bantu, bukan pengganti penilaian lapangan.`,

    pompa: `Jakarta punya lebih dari 600 unit pompa banjir — stasioner dan mobile — yang dikelola DSDADKI (Dinas Sumber Daya Air DKI). Saat banjir, pompa-pompa inilah yang bekerja membuang genangan ke kanal dan laut.

Titik pompa utama ada di Pluit, Ancol, Muara Baru, dan Manggarai. Kapasitasnya ada batasnya, terutama kalau hujan sangat deras dalam waktu singkat.

Kalau ada pompa yang kelihatannya rusak atau tidak berfungsi, bisa lapor ke Dinas SDA di 021-3855555 atau Call Center DKI 112.`,
  },

  en: {
    evakuasi: `If things have escalated to the point of evacuation, the most time-saving thing you can do is have an emergency bag ready before the water rises — not packed in a panic when it's already at the door.

What to pack:
• Original documents (ID, family card, land certificates) + digital copies in the cloud
• Daily medications & basic first aid
• 2–3 days of clothes + a raincoat
• Drinking water and dry food that keeps well
• Flashlight, power bank, spare batteries
• Some cash

Pack it all in a waterproof bag or a tied garbage bag to keep things dry. For the nearest active shelter, call BPBD at 117 — they're available 24 hours.`,

    status: `Jakarta flood status updates every 15 minutes directly from 38+ DSDADKI water level sensors. You can check the Risk Score and each district's status on the Command Center page.

If the numbers are low and there are no alert zones, conditions are currently safe. That said, the situation can shift quickly — especially when there's heavy rain upstream — so keep an eye on it if the weather looks rough.`,

    tanda: `Floods rarely come out of nowhere. There are usually signs beforehand if you know what to look for.

Common warning signs:
• Heavy rain that doesn't stop for 30–40 minutes
• Water in drains or canals rising and turning murky brown
• A strong, unusual smell of wet earth
• Ants or earthworms moving to higher ground
• A BMKG heavy rain alert for your area

If you spot 2–3 of these at the same time, don't wait for water to enter your home. Start preparing your emergency bag and monitor the latest updates.`,

    shelter: `To find the nearest evacuation shelter, open the Evacuation page from the top menu and enter your address — the system will show you the route to the nearest shelter.

The faster option: call BPBD Jakarta at 117. They know exactly which shelters are active right now and can help coordinate. Schools and sports halls (GOR) are usually the first places BPBD uses during emergencies.`,

    kontak: `Save these numbers now, before you actually need them — much better to have them in your contacts than to search in a panic during a crisis.

Key emergency contacts:
• BPBD Jakarta: 117 (disaster response & evacuation)
• Basarnas (SAR): 115
• Ambulance: 118 / 119
• PMI Jakarta (Red Cross): (021) 390-6666
• Fire Department: 113
• DKI Jakarta Call Center: 112

All free, all available 24 hours.`,

    dokumen: `Important documents are often the hardest things to replace after flood damage. The safest approach is to protect them before the flood ever comes.

What you can do right now:
• Photo or scan all documents → save to Google Drive or email them to yourself
• Put the originals in a waterproof zip-lock bag
• Bring the physical copies when you evacuate — don't leave them behind

Priority documents: ID card, family card, birth certificate, land title, and BPJS card. If the originals are lost, digital versions in the cloud can usually get you through the initial administrative steps.`,

    cuaca: `For detailed weather forecasts, the most reliable source is BMKG — accessible at bmkg.go.id or through the Info BMKG app on Play Store and App Store.

deFlood.ai focuses on realtime weather data and water level sensors right now — not future forecasts. Rain above 50 mm/h is considered extreme and can trigger flash flooding, especially in areas with poor drainage.

Jakarta's rainy season runs November–March, with the peak typically in January–February.`,

    pasca: `After the flood recedes, the urge to go straight in and clean up is understandable. But a few checks first will keep you safe.

Steps before and during cleanup:
• Inspect the building structure from outside first — look for cracks or any leaning
• Turn off electricity at the breaker panel before entering, especially if floors are still wet
• Wear rubber gloves and rubber boots while cleaning
• Throw out any food that came into contact with floodwater — don't eat it
• Open windows and ventilation as wide as possible for airflow

Watch out for leptospirosis, diarrhea, and skin infections — especially if you had a lot of contact with floodwater. If anyone feels unwell afterward, get to the nearest health clinic (Puskesmas). You've got this.`,

    prediksi: `The Risk Score in deFlood.ai is a number from 0 to 100 showing the current probability of flooding in Jakarta — calculated from a combination of weather data, water levels, and an XGBoost ML model trained on years of historical data.

How to read it:
• Below 30 → Normal, conditions are safe
• 30–55 → Watch (Waspada) — monitor more closely
• 55–80 → Alert Level 2 (Siaga 2) — prepare your emergency bag
• Above 80 → Alert Level 1 (Siaga 1) — consider evacuating if you're in a low-lying area

Data refreshes every 15 minutes, with around 94% model accuracy. That said, always combine it with BMKG information and what you observe around you — the score is a decision support tool, not a replacement for ground-level awareness.`,

    pompa: `Jakarta has over 600 stationary and mobile flood pumps managed by DSDADKI (the DKI Water Resources Agency). During floods, these are what actively drain standing water back into canals and out to sea.

The main pump stations are at Pluit, Ancol, Muara Baru, and Manggarai. Their capacity has limits, especially when rainfall is very intense over a short period.

If you see a pump that looks broken or isn't working, you can report it to the Water Agency at 021-3855555 or the DKI Call Center at 112.`,
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

  // Offline fallback: keyword matching
  const offline = _matchOffline(message, lang);
  if (offline) return { success: true, reply: offline, isAI: false };

  // Generic offline fallback — humanized
  const generic = lang === "en"
    ? "I'm currently offline and can't reach the AI backend.\n\nFor emergencies: BPBD 117 · Basarnas 115 · Ambulance 119.\n\nYou can also ask me about: what to pack for evacuation, flood warning signs, finding a nearby shelter, or emergency contacts — I have those answers stored locally."
    : "AI lagi tidak bisa dihubungi saat ini.\n\nKalau darurat: BPBD 117 · Basarnas 115 · Ambulans 119.\n\nKamu juga bisa tanya ke saya seputar: barang yang perlu dibawa saat evakuasi, tanda-tanda banjir akan datang, cara menemukan shelter, atau kontak darurat — jawaban untuk itu ada di sini meski sedang offline.";
  return { success: false, reply: generic, isAI: false };
}

export const quickReplies = [
  "Status banjir sekarang?",
  "Apa yang harus dibawa saat evakuasi?",
  "Tanda-tanda banjir akan datang?",
  "Lokasi shelter terdekat?",
  "Cara membaca prediksi risiko?",
  "Langkah aman setelah banjir surut?",
  "Hubungi siapa saat darurat?",
  "Prakiraan cuaca Jakarta?",
];
