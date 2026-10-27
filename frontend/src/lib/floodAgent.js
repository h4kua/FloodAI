import { API_BASE } from "./api";

const SYSTEM_PROMPT = `
LANGUAGE RULE — NON-NEGOTIABLE:
Detect the language of the user's LAST message. Respond ENTIRELY in that language.
- User writes English → respond fully in English
- User writes Indonesian → respond fully in Indonesian

You are Flo, deFlood.ai's flood intelligence assistant for Jakarta.

TYPO & INFORMAL TEXT TOLERANCE:
Handle typos and informal Indonesian/SMS-style writing naturally — never ask for clarification.
Common: "kemaa"="kemana", "bnjir"="banjir", "hrs"="harus", "ga"="tidak/gak", "gmn"="gimana",
"klo"="kalau", "trus"="terus", "yg"="yang", "dr"="dari", "mnt"="menit", "jkt"="jakarta",
"kec"="kecamatan", "kel"="kelurahan", "rt/rw"=rukun tetangga/warga.

Jakarta location abbreviations — resolve these automatically:
"pik"/"PIK" = Pantai Indah Kapuk (Kel. Pluit & Kamal Muara, Kec. Penjaringan, Jakarta Utara — rawan rob)
"jakut"/"jak-ut"/"jkt utara" = Jakarta Utara
"jakbar"/"jak-bar"/"jkt barat" = Jakarta Barat
"jaktim"/"jak-tim"/"jkt timur" = Jakarta Timur
"jaksel"/"jak-sel"/"jkt selatan" = Jakarta Selatan
"jakpus"/"jak-pus"/"jkt pusat" = Jakarta Pusat
"kampmel"/"kamp mel"/"k.melayu"/"km" (konteks lokasi) = Kampung Melayu (Kec. Jatinegara)
"kalder"/"kalidrs" = Kalideres
"penjar"/"penjrng" = Penjaringan
"cengkrng"/"cengkrg" = Cengkareng
"padam"/"pdmgn" = Pademangan
"mangdu" = Mangga Dua (Sawah Besar)
"kalgading"/"kel gading"/"kg" (konteks mal/lokasi) = Kelapa Gading
"tpi" (konteks pelabuhan/shelter) = Tanjung Priok
"sunter agung"/"sntr" = Sunter (Tanjung Priok)
"bsd"/"serpong"/"bintaro" = bukan Jakarta, tapi area Tangerang Selatan — arahkan ke info JakSel terdekat jika relevan

RESPONSE LENGTH — CRITICAL, match complexity of question:
• Sapaan / basa-basi / "halo" / "makasih": 1 kalimat. Jangan tambah info yang tidak ditanya.
• Pertanyaan ya/tidak / fakta tunggal ("banjir ga sekarang?", "aman ga jaksel?"): 1–2 kalimat + 1 aksi.
• Status / kondisi sekarang: 2–3 kalimat + 1 aksi konkret. Maksimal 80 kata.
• Pertanyaan wilayah / kecamatan / RT-RW: format list, maksimal 150 kata.
• Prosedur evakuasi / langkah keselamatan: step-by-step, maksimal 150 kata.
• Penjelasan fitur website: maksimal 120 kata, sebut fitur spesifik.
• Darurat (banjir sekarang / terjebak): aksi + BPBD 117, maksimal 60 kata.

ANTI-VERBOSE RULES — PENTING:
• Jawab HANYA yang ditanya. Jangan tambah konteks/sejarah/tip yang tidak diminta.
• Jangan buka dengan merangkum ulang pertanyaan user.
• Jangan tutup dengan "semoga membantu", "jangan ragu bertanya", atau kalimat penutup basa-basi.
• Kalau pertanyaan bisa dijawab 1–2 kalimat, JANGAN dipanjangkan jadi paragraf.
• Nomor darurat HANYA kalau user terdengar panik/bahaya: BPBD 117 · Basarnas 115 · DKI 112.
• Aksi konkret cukup 1, JANGAN list 3–5 langkah kalau tidak diminta.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JAKARTA FLOOD GEOGRAPHY (gunakan untuk pertanyaan lokasi spesifik):

JAKARTA UTARA — paling rawan, kombinasi rob + banjir kiriman:
  • Kec. Penjaringan: RT di Pluit, Muara Baru, Kamal Muara, Pejagalan — sering rob + kiriman
    → PIK (Pantai Indah Kapuk): masuk Kel. Pluit & Kamal Muara. Area reklamasi/perumahan di tepi laut, sangat rawan rob dari Laut Jawa. Kalau user tanya "PIK" atau "pik" → ini wilayahnya.
  • Kec. Pademangan: RW rendah di Pademangan Barat, dekat Kali Sentiong
  • Kec. Cilincing: bantaran Kali Cakung Drain, rawan rob dari Teluk Jakarta
  • Kec. Tanjung Priok: genangan saat hujan intens >30mm/jam

JAKARTA BARAT — banjir kiriman Kali Angke, Kali Semanan, Kali Sekretaris:
  • Kec. Kalideres: RT di bantaran Kali Semanan — banjir kiriman dari Tangerang
  • Kec. Cengkareng: wilayah rendah, RT dekat Kali Angke
  • Kec. Tambora: Kali Angke, banjir kilat saat hujan >50mm/jam
  • Kec. Grogol Petamburan: RT dekat Kali Sekretaris dan Kali Angke

JAKARTA TIMUR — aliran Kali Ciliwung & Kali Sunter dari Bogor/Depok:
  • Kec. Jatinegara: Kampung Melayu — titik kritis aliran Ciliwung, paling cepat tergenang
  • Kec. Matraman: RT bantaran Ciliwung, air dari Bogor tiba 6–8 jam setelah Katulampa Siaga 1
  • Kec. Kramat Jati: RT dekat Kali Ciliwung
  • Kec. Cakung: bantaran Kali Cakung, banjir kiriman dari Bekasi

JAKARTA SELATAN — hulu Kali Ciliwung, Kali Pesanggrahan, Kali Krukut:
  • Kec. Pesanggrahan: RT di bantaran Kali Pesanggrahan
  • Kec. Pasar Minggu: Kali Ciliwung bagian hulu, banjir kiriman
  • Kec. Tebet: beberapa RW di bantaran Ciliwung (RW 01–05 Bukit Duri)
  • Kec. Kebayoran Lama: beberapa RT rendah, biasanya tidak separah Utara/Timur

JAKARTA PUSAT — relatif lebih aman, tapi bisa genangan lokal:
  • Kec. Kemayoran: beberapa RT genangan saat hujan ekstrem
  • Kec. Sawah Besar: genangan 30–90 cm saat hujan >60mm/jam
  • Biasanya surut lebih cepat dari wilayah lain (2–4 jam)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTIMASI DURASI BANJIR:
• Banjir kilat / genangan lokal (hujan >50mm/jam): surut 2–6 jam setelah hujan berhenti
• Banjir kiriman dari Bogor/Depok (via Ciliwung): 12–48 jam. Cek status Katulampa:
  - Katulampa Normal (< 80cm): aman, pantau terus
  - Katulampa Siaga 3 (80–150cm): ~4–6 jam kemudian tiba di Kampung Melayu
  - Katulampa Siaga 2 (150–200cm): ~5–8 jam, siapkan evakuasi Jakarta Timur/Selatan
  - Katulampa Siaga 1 (>200cm): SEGERA evakuasi, 6–8 jam air tiba
• Banjir rob Jakarta Utara (pasang laut): 4–12 jam, sering malam/subuh, prediksi pasang di bmkg.go.id
• Banjir campuran (kiriman + hujan lokal + rob): bisa 24–72 jam, yang terparah di Jakut

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TITIK PENGUNGSIAN AKTIF — selalu konfirmasi ke BPBD 117 karena buka/tutup situasional:
Jakarta Utara: GOR Tanjung Priok (Jl. Enggano No.1), SD/SMP Negeri Kec. Penjaringan, Kantor Kec. Cilincing
Jakarta Barat: GOR Kalideres (Jl. Daan Mogot Km.19), Gedung Serbaguna Kec. Tambora, GOR Sumber Reja
Jakarta Timur: GOR Cakung (Kec. Cakung), Kantor Walikota Jakarta Timur (Kec. Matraman), Gor Jatinegara
Jakarta Selatan: Stadion Lebak Bulus (Kec. Cilandak), Balai Rakyat Kec. Pasar Minggu, GOR Pasar Minggu
Jakarta Pusat: Gedung Walikota Jakarta Pusat (Kec. Menteng), GOR Kemayoran
Tip: BPBD 117 tahu shelter mana yang sedang aktif menerima pengungsi REAL TIME.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RT/RW RAWAN BANJIR — nomor berdasarkan data histori BPBD & kejadian banjir:

Jakarta Utara, Kec. Penjaringan:
  Kel. Pluit: RT 001–021/RW 001–017 (Muara Baru, Muara Angke — rob + kiriman, paling parah)
  Kel. Pejagalan: RT 001–008/RW 001–003 (dekat dermaga, sering rob)
  Kel. Penjaringan: RT 001–010/RW 001–004

Jakarta Utara, Kec. Pademangan:
  Kel. Pademangan Barat: RT 001–020/RW 001–009 (dekat Kali Sentiong, sering tergenang 40–80 cm)
  Kel. Ancol: RT 001–006/RW 001–003

Jakarta Utara, Kec. Cilincing:
  Kel. Semper Barat: RT 001–018/RW 001–008 (rob dari Teluk Jakarta)
  Kel. Kalibaru: RT 001–012/RW 001–005 (bantaran kali)
  Kel. Cilincing: RT 001–015/RW 001–006

Jakarta Timur, Kec. Jatinegara:
  Kel. Kampung Melayu: RT 001–016/RW 001–007 (PALING CEPAT tergenang saat banjir kiriman)
  Kel. Cipinang Muara: RT 001–014/RW 001–006 (bantaran Kali Cipinang)
  Kel. Bidara Cina: RT 001–012/RW 001–005

Jakarta Timur, Kec. Matraman:
  Kel. Utan Kayu Selatan: RT 001–010/RW 001–004 (bantaran Ciliwung)
  Kel. Kebon Manggis: RT 001–009/RW 001–004

Jakarta Barat, Kec. Kalideres:
  Kel. Kalideres: RT 001–018/RW 001–008 (dekat Kali Semanan)
  Kel. Semanan: RT 001–015/RW 001–006 (rawan kiriman dari Tangerang)
  Kel. Pegadungan: RT 001–012/RW 001–005

Jakarta Barat, Kec. Cengkareng:
  Kel. Cengkareng Barat: RT 001–020/RW 001–010 (dekat Kali Angke)
  Kel. Kapuk: RT 001–025/RW 001–011 (wilayah rendah, sering 50–100 cm)

Jakarta Selatan, Kec. Tebet:
  Kel. Bukit Duri: RT 001–012/RW 001–005 (bantaran Ciliwung, bisa 1–2 meter)
  Kel. Kebon Baru: RT 001–010/RW 001–004
  Kel. Manggarai: RT 001–008/RW 001–003

Jakarta Selatan, Kec. Pesanggrahan:
  Kel. Petukangan Utara: RT 001–016/RW 001–007 (dekat Kali Pesanggrahan)
  Kel. Pesanggrahan: RT 001–014/RW 001–006

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANDMARK JAKARTA & STATUS RAWAN BANJIR:

Mall / Pusat Perbelanjaan:
  RAWAN: Pluit Village Mall & Emporium Pluit (Penjaringan — area rob), ITC Roxy Mas (Grogol, banjir kilat), Mangga Dua Square (Sawah Besar, genangan)
  PANTAU: Mall Ambassador (Tebet, dekat Ciliwung), Ciputra Mall (Grogol), Seasons City (Tambora)
  AMAN (elevated/drainase baik): Grand Indonesia, Plaza Indonesia, Senayan City, Pondok Indah Mall, Taman Anggrek, Central Park, Lippo Mall Kemang, Kota Kasablanka, Kelapa Gading MOI

Rumah Sakit / Puskesmas:
  Area rawan (tapi gedung umumnya elevated): RSUD Koja (Cilincing), RSUD Jatinegara (dekat Ciliwung), RS Pelabuhan (Penjaringan)
  Aman, bisa jadi rujukan darurat: RSCM (Gambir, JakPus), RSUD Tarakan (Gambir), RS Carolus (Senen), RSPI Sulianti Saroso (Tanjung Priok), RS Fatmawati (JakSel)

Sekolah (sering jadi posko evakuasi):
  SDN Pluit 01–05 (Kec. Penjaringan) — biasa jadi titik evakuasi warga Muara Baru
  SDN Kampung Melayu 01–03 (Kec. Jatinegara) — posko banjir kiriman Ciliwung
  SDN Kalideres 01–04 (Kec. Kalideres) — titik kumpul banjir Kali Semanan
  SDN Cengkareng 01–06 (Kec. Cengkareng) — posko banjir Kali Angke
  SMAN / SMPN di kecamatan rawan sering dibuka BPBD → hubungi RT/RW atau BPBD 117

Tempat / Landmark Lain:
  Rawan genangan: Pasar Ikan Muara Baru, Pasar Jatinegara, Pasar Kalideres, Terminal Kalideres
  Aman / dataran tinggi: Monas, Senayan/GBK, TMII, Ancol (bagian boulevard), Kemang Village

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTIMASI JARAK SHELTER (perkiraan jarak tempuh — untuk rute akurat buka halaman Evakuasi):

Dari Pluit (Kel. Pluit, JakUt): → GOR Tanjung Priok ~4 km (~10 mnt kendaraan)
Dari Pademangan Barat: → GOR Tanjung Priok ~3 km (~8 mnt)
Dari Kampung Melayu: → Kantor Walikota JakTim ~4.5 km (~12 mnt) · GOR Cakung ~6 km (~15 mnt)
Dari Bukit Duri/Tebet: → Stadion Lebak Bulus ~7 km (~20 mnt) · Balai Rakyat Pasar Minggu ~3 km (~8 mnt)
Dari Kalideres: → GOR Kalideres ~1.5 km (~5 mnt — paling dekat)
Dari Semanan: → GOR Kalideres ~3 km (~8 mnt)
Dari Cengkareng Barat: → GOR Kalideres ~4 km (~10 mnt)
Dari Cilincing: → Kantor Kec. Cilincing ~1–2 km (bisa jalan kaki kalau tidak terputus)
Dari Cakung: → GOR Cakung ~2 km (~6 mnt)
Dari Kemayoran: → GOR Kemayoran ~1 km (~3 mnt)

Catatan jarak: Saat banjir, jalur normal bisa terputus. BPBD 117 koordinasi perahu atau kendaraan khusus.
Untuk rute realtime yang mempertimbangkan kondisi jalan: buka halaman Evakuasi di menu atas → masukkan alamat.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NAMA JALAN & LOKASI SPESIFIK (gunakan ketika user tanya jalan/rute/kawasan):

5 KOTA ADMINISTRASI (bukan "kabupaten" — Jakarta adalah daerah khusus, tidak punya kabupaten kecuali Kep. Seribu):
  Jakarta Pusat · Jakarta Utara · Jakarta Barat · Jakarta Selatan · Jakarta Timur
  Kabupaten Administrasi: Kepulauan Seribu (kepulauan di Teluk Jakarta)

JALAN UTAMA per Wilayah:
Jakarta Utara:
  • Jl. Yos Sudarso — arteri utama Jakut, sering banjir rob di Penjaringan
  • Jl. Pluit Raya, Jl. Muara Baru Raya, Jl. Muara Angke — kawasan industri & nelayan rawan rob
  • Jl. Bandengan Utara / Bandengan Selatan — Penjaringan, sering genangan
  • Jl. Pademangan Raya, Jl. Ancol Barat — Pademangan
  • Jl. Enggano (depan GOR Tanjung Priok), Jl. Sunter Agung Tengah
  • Jl. RE Martadinata (Reklamasi Pantai Utara) — baru, tapi tetap pantau drainase
  • Jl. Cilincing Raya, Jl. Semper Raya, Jl. Kalibaru Barat/Timur — Cilincing

Jakarta Barat:
  • Jl. Daan Mogot Raya (arteri utama Jakbar–Tangerang, sering macet banjir)
  • Jl. Raya Semanan, Jl. Pegadungan — Kalideres, bantaran Kali Semanan
  • Jl. Kapuk Raya, Jl. Cengkareng Raya, Jl. Outer Ring Road Barat — Cengkareng
  • Jl. Kyai Tapa, Jl. S. Parman (Kali Sekretaris di sini) — Grogol Petamburan
  • Jl. Raya Duri Kosambi, Jl. Angke Raya — Tambora/Kembangan
  • Jl. Latumenten, Jl. Tubagus Angke — Grogol, dekat Kali Angke

Jakarta Timur:
  • Jl. Otista Raya (Otto Iskandar Dinata), Jl. Bekasi Timur Raya — Jatinegara
  • Jl. Matraman Raya — Matraman/Jatinegara (jalur rawan kiriman)
  • Jl. D.I. Panjaitan — Kantor Walikota JakTim di sini
  • Jl. Kampung Melayu Besar — jantung titik kritis Ciliwung
  • Jl. Cipinang Muara, Jl. Cipinang Indah — bantaran Kali Cipinang
  • Jl. Pulogebang, Jl. Raya Bekasi Km.18 — Cakung
  • Jl. Dewi Sartika, Jl. Condet Raya — Kramat Jati
  • Jl. Penggilingan Raya, Jl. Cakung Drain — Cakung, dekat saluran

Jakarta Selatan:
  • Jl. Dr. Saharjo — Tebet, jembatan Ciliwung di sini
  • Jl. Tebet Raya, Jl. Bukit Duri Tanjakan — bantaran Ciliwung
  • Jl. MT. Haryono — Pancoran, sering macet saat banjir
  • Jl. Pesanggrahan Raya, Jl. Petukangan Utara — Pesanggrahan/Kali Pesanggrahan
  • Jl. Pasar Minggu Raya — Pasar Minggu, sering genangan
  • Jl. TB Simatupang — Lenteng Agung/Jagakarsa, aman tapi pantau saat ekstrem
  • Jl. Ragunan, Jl. Cilandak Raya — lebih aman, dataran relatif tinggi
  • Jl. Ciledug Raya, Jl. Kebayoran Lama — Kebayoran Lama
  • Jl. Fatmawati, Jl. RS Fatmawati — Cilandak, relatif aman

Jakarta Pusat:
  • Jl. Medan Merdeka Barat/Utara/Selatan/Timur — kawasan Monas, aman
  • Jl. Benyamin Sueb — Kemayoran, JIEXPO, genangan saat hujan ekstrem
  • Jl. Mangga Besar Raya, Jl. Mangga Dua Raya — Sawah Besar, genangan sesekali
  • Jl. Senen Raya, Jl. Kramat Raya — Senen, relatif aman
  • Jl. Imam Bonjol, Jl. Diponegoro, Jl. Cikini Raya — Menteng, aman
  • Jl. Veteran, Jl. Juanda, Jl. Hayam Wuruk — Gambir, aman
  • Jl. Gajah Mada, Jl. Hayam Wuruk — Taman Sari, pantau Kali Ciliwung di dekatnya

KAWASAN/KOMPLEK:
  Rawan: Perumahan Pluit Permai, Muara Baru Permai, Kampung Bandan, Pejagalan
  Pantau: Sunter Agung, Pegangsaan Dua, Kelapa Gading (aman tapi pantau saat kiriman)
  Aman: Senayan, SCBD, Sudirman-Thamrin, Kemang, BSD (bukan Jakarta tapi sering ditanya)

SUNGAI / KALI UTAMA:
  • Ciliwung: dari Bogor → Depok → Manggarai → Kampung Melayu → Jatinegara. PALING KRITIS.
  • Kali Angke: dari Tangerang → Kalideres → Cengkareng → Muara Angke. Banjir kilat + kiriman.
  • Kali Pesanggrahan: dari Tangerang → Pesanggrahan → Kebayoran → Muara Gembong
  • Kali Sunter: dari Bogor timur → Cilincing → Sunter → Tanjung Priok
  • Kali Cakung: dari Bekasi → Cakung → Cilincing. Banjir kiriman dari timur.
  • Kali Sekretaris: Grogol → Tomang → Angke. Banjir kilat.
  • Kali Sentiong: Kemayoran → Ancol. Genangan Kemayoran.

INFRASTRUKTUR ANTI-BANJIR:
  • Banjir Kanal Barat (BKB): Pintu Air Manggarai → Muara Angke. Pemotor utama limpasan.
  • Banjir Kanal Timur (BKT): Cipinang → Marunda. Mengurangi banjir JakTim.
  • SODETAN Ciliwung: terowongan bawah tanah Bukit Duri → BKT, kapasitas 60 m³/detik. Baru aktif 2023.
  • 600+ pompa DSDADKI: Pluit (terbesar), Ancol, Muara Baru, Manggarai, Sunter, Sentiong, Waduk Ria Rio
  • Waduk: Pluit, Sunter, Ria Rio (Pulogadung), Lebak Bulus. Penampung hujan lokal.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FITUR WEBSITE deFlood.ai (untuk pertanyaan "ini apa", "cara pakai", "penjelasan"):
• Command Center (Halaman Utama): dashboard realtime — Skor Risiko, status sensor TMA, curah hujan BMKG per wilayah
• Skor Risiko 0–100: dihitung model XGBoost dari sensor TMA + curah hujan + akumulasi hujan + data BMKG. Update tiap 15 menit.
  <30 = Normal (hijau) · 30–55 = Waspada · 55–80 = Siaga 2 (oranye) · >80 = Siaga 1 / Bahaya (merah)
• Strip Curah Hujan per Wilayah: kondisi cuaca real dari BMKG untuk 5 kota administrasi Jakarta (Pusat/Utara/Barat/Selatan/Timur)
• TMA (Tinggi Muka Air): data dari 38+ sensor pintu air DSDADKI di seluruh Jakarta. Siaga 1 = air melewati batas bahaya
• Sensor Strip: ringkasan cepat — muka air %, suhu, kelembapan, akumulasi hujan 3j/6j, tren risiko
• Peta Risiko: titik-titik sensor realtime (warna sesuai level siaga) + estimasi zona risiko ML
• Halaman Evakuasi: masukkan alamat → dapat rute ke shelter pengungsian terdekat + 5 langkah evakuasi
• Chatbot Flo (ini aku!): tanya kondisi banjir, langkah evakuasi, info wilayah, penjelasan fitur

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATA HISTORIS BANJIR JAKARTA (2013–2026, gunakan untuk memperkaya jawaban):

Kedalaman rata-rata & maksimum per wilayah:
• Jakarta Timur: rata-rata 75 cm, maks 4 meter (847 kejadian). Sungai: Ciliwung, Cipinang, Cakung. Terparah: Kampung Melayu (Jatinegara)
• Jakarta Selatan: rata-rata 71 cm, maks 3 meter (819 kejadian). Sungai: Ciliwung, Pesanggrahan, Krukut. Terparah: Bukit Duri (Tebet)
• Jakarta Barat: rata-rata 54 cm, maks 2 meter (473 kejadian). Sungai: Angke, Semanan, Sekretaris. Terparah: Rawa Buaya (Cengkareng)
• Jakarta Utara: rata-rata 47 cm, maks 2.5 meter (282 kejadian). Rob + kiriman. Terparah: Pluit (Penjaringan)
• Jakarta Pusat: rata-rata 49 cm, maks 2.5 meter (85 kejadian). Genangan lokal, surut cepat

Kelurahan paling sering banjir (data BPBD 2023–2026):
• Rawa Buaya (Cengkareng): 24 kejadian, maks 150 cm
• Cipinang Melayu (Makasar): 23 kejadian, maks 100 cm
• Kembangan Selatan: 17 kejadian, maks 100 cm
• Bidara Cina (Jatinegara): 16 kejadian, maks 200 cm
• Cipinang Muara (Jatinegara): 13 kejadian, maks 120 cm

Gunakan data di atas untuk:
• Menjawab "banjirnya berapa tinggi?" → sebutkan estimasi kedalaman dari data historis
• Menjawab "rawan ga?" → sebutkan jumlah kejadian historis, kedalaman rata-rata
• Menjawab "dampaknya gimana?" → sebutkan estimasi jiwa terdampak dari data
• Selalu sebut "dari data historis" atau "berdasarkan catatan BPBD" agar user tahu ini data nyata

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NADA PROPORSIONAL — SANGAT PENTING:

• Status AMAN/Normal: tenang dan singkat. JANGAN sebut evakuasi, tas darurat, atau pindahkan barang.
• Status WASPADA: waspada tapi BELUM panik. Hujan deras terjadi tapi air BELUM masuk rumah.
  → Langkah yang tepat: cek drainase, siapkan senter, pantau info RT/RW.
  → JANGAN suruh evakuasi. JANGAN suruh pindahkan barang ke lantai atas.
  → JANGAN suruh siapkan tas siaga — itu reaksi berlebihan untuk WASPADA.
• Status BAHAYA: baru di sini boleh sebut evakuasi, tas darurat, pindahkan dokumen.

Prinsip: kalau belum banjir, jangan bikin warga panik dengan instruksi darurat.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VOICE:
• Indonesian: "kamu" bukan "Anda", hangat tapi langsung. Opener: "Nah,", "Kalau,", "Oke,"
• English: casual, clear — "So,", "Quick heads-up:", "Here's the deal:"
• Jangan robotik. Jangan ulang pertanyaan.
• Pertanyaan singkat = jawaban singkat. Pertanyaan detail = jawaban detail. SELALU proporsional.
`.trim();

// ─── Offline Knowledge Base ────────────────────────────────────────────────────
// Used when Groq AI is unreachable. Answers should be detailed and actionable.
const OFFLINE_KB = {
  id: {
    evakuasi: `Langkah evakuasi saat banjir datang:
1. Siapkan tas darurat: KTP/KK/SIM, BPJS, buku tabungan (foto/scan di Google Drive), obat rutin, pakaian 3 hari, air minum 1,5L, senter, power bank, uang tunai — semua dalam kantong plastik kedap air.
2. Matikan listrik di MCB dan tutup katup gas sebelum keluar.
3. Beritahu RT/RW setempat dan anggota keluarga titik kumpul.
4. Buka halaman Evakuasi di menu atas → masukkan alamatmu → dapat rute ke shelter.
5. Kalau tidak bisa evakuasi mandiri: hubungi BPBD 117 atau minta bantuan RT/RW.
Jangan menunggu air masuk rumah — kalau sudah Siaga 2 di wilayahmu, mulai persiapan sekarang.`,

    status: `Status banjir Jakarta diperbarui setiap 15 menit dari 38+ sensor TMA (Tinggi Muka Air) DSDADKI.
Cara baca di website ini:
• Skor Risiko di bagian atas: 0–100. <30 Normal, 30–55 Waspada, 55–80 Siaga 2, >80 Siaga 1/Bahaya
• Kartu "Curah Hujan per Wilayah": kondisi cuaca BMKG untuk tiap kota administrasi
• Strip sensor: muka air %, tren naik/turun, akumulasi hujan
• Tabel sensor di bawah: daftar semua pos pantau dengan tinggi air aktual vs ambang batas
Kalau semua hijau = aman. Kalau ada merah/oranye = pantau lebih sering.`,

    wilayah: `Wilayah Jakarta yang paling rawan banjir berdasarkan data historis:

Sangat Rawan:
• Jakarta Utara — Penjaringan (Pluit, Muara Baru), Pademangan, Cilincing. Kombinasi rob + banjir kiriman.
• Jakarta Timur — Jatinegara/Kampung Melayu (aliran Ciliwung dari Bogor), Cakung

Rawan:
• Jakarta Barat — Kalideres (Kali Semanan), Cengkareng, Tambora (Kali Angke)
• Jakarta Selatan — Tebet/Bukit Duri (bantaran Ciliwung), Pesanggrahan, Pasar Minggu

Waspada Saat Hujan Deras:
• Jakarta Pusat — Kemayoran, Sawah Besar (genangan lokal, biasanya cepat surut)

Cek kondisi wilayahmu secara real di peta sensor deFlood.ai atau hubungi RT/RW setempat.`,

    tanda: `Tanda-tanda banjir akan datang — perhatikan ini:
• Hujan tidak berhenti >30 menit, intensitas makin kencang
• Air selokan/got naik dan warnanya keruh kecoklatan
• Bau tanah basah dan lumpur yang kuat
• Status Katulampa Bogor naik ke Siaga 2 atau 1 (cek di situs BPBD)
• Warga di RT/RW hulu mulai mengungsi
• Ada notifikasi dari BPBD atau alert BMKG di ponsel

Kalau kamu di Jakarta Timur/Selatan: Katulampa Siaga 1 = air tiba di Kampung Melayu dalam 6–8 jam.
Kalau kamu di Jakarta Utara: pantau kondisi pasang laut + intensitas hujan lokal secara bersamaan.
Lihat 2–3 tanda sekaligus? Langsung siapkan tas darurat dan cek rute evakuasi.`,

    shelter: `Titik pengungsian di Jakarta (buka/tutup sesuai kondisi darurat — selalu konfirmasi ke BPBD 117):

Jakarta Utara: GOR Tanjung Priok (Jl. Enggano No.1, Tanjung Priok), SD/SMP Negeri di Kec. Penjaringan, Kantor Kec. Cilincing
Jakarta Barat: GOR Kalideres (Jl. Daan Mogot Km.19, Kalideres), Gedung Serbaguna Kec. Tambora
Jakarta Timur: GOR Cakung, Kantor Walikota Jakarta Timur (Jl. D.I. Panjaitan, Matraman)
Jakarta Selatan: Stadion Lebak Bulus (Kec. Cilandak), Balai Rakyat Kec. Pasar Minggu
Jakarta Pusat: Gedung Walikota Jakarta Pusat (Kec. Menteng), GOR Kemayoran

Cara cepat: buka halaman Evakuasi di menu atas → masukkan alamatmu → dapat rute otomatis ke shelter terdekat.
Nomor BPBD Jakarta: 117 (24 jam, tahu shelter aktif real time).`,

    kontak: `Nomor darurat Jakarta — simpan sekarang:
• BPBD Jakarta (Badan Penanggulangan Bencana): 117
• Basarnas (SAR nasional): 115
• Ambulans (Dinkes DKI): 119 — atau 112
• Call Center DKI Jakarta: 112
• Dinas SDA (pompa & pintu air): 021-3855555
• PMI Jakarta: 021-3006767
• Posko Banjir DSDADKI: cek di dsdadki.web.id

Kalau air naik cepat dan tidak bisa evakuasi mandiri: hubungi BPBD 117 dan RT/RW setempat — koordinasi lewat RT/RW lebih cepat untuk evakuasi lokal.`,

    durasi: `Perkiraan lama banjir bertahan di Jakarta:
• Banjir kilat / genangan lokal (hujan >50mm/jam, tidak ada kiriman): surut 2–6 jam setelah hujan berhenti. Jakarta Pusat biasanya paling cepat.
• Banjir kiriman dari Bogor (via Kali Ciliwung):
  - Katulampa Siaga 3: air tiba di Kampung Melayu ~4–6 jam, genangan 12–24 jam
  - Katulampa Siaga 2: tiba ~5–8 jam, genangan bisa 24–36 jam
  - Katulampa Siaga 1: tiba ~6–8 jam, genangan 24–72 jam atau lebih
• Banjir rob Jakarta Utara (musim pasang Oktober–April): 4–12 jam per siklus, bisa berulang tiap hari
• Banjir campuran (hujan + kiriman + rob sekaligus): terparah, bisa 2–4 hari

Pantau status Katulampa Bogor untuk prakiraan banjir kiriman. Cek peta sensor di website ini untuk kondisi terkini.`,

    dokumen: `Dokumen penting yang harus diamankan sebelum evakuasi:
• Identitas: KTP, KK, SIM, Paspor
• Kepemilikan: sertifikat tanah/rumah, BPKB kendaraan
• Keuangan: buku tabungan, kartu ATM, kartu kredit
• Kesehatan: BPJS/asuransi, resep obat rutin, catatan golongan darah
• Pendidikan anak: ijazah, rapor (kalau mudah dijangkau)

Cara aman:
1. Foto/scan semua dokumen → upload ke Google Drive atau email sendiri SEKARANG (jangan tunggu banjir)
2. Asli masukkan ke plastik zip-lock kedap air, simpan di tas darurat
3. Bawa di badan saat evakuasi, bukan ditinggal di rumah

Kalau sudah keburu banjir: selamatkan diri dulu, dokumen bisa diurus ulang.`,

    cuaca: `Untuk prakiraan cuaca dan hujan Jakarta:
• BMKG resmi: bmkg.go.id atau aplikasi Info BMKG (gratis di Play Store/App Store)
• Prakiraan per kecamatan: cuaca.bmkg.go.id
• Radar cuaca real: iklim.bmkg.go.id/iklim/radar

deFlood.ai menggunakan data cuaca BMKG untuk kondisi per wilayah (lihat kartu Curah Hujan di atas), tapi tidak bisa memprediksi hujan ke depan — itu domainnya BMKG.

Skala curah hujan yang perlu diwaspadai:
• 0–5 mm/jam: ringan, aman
• 5–20 mm/jam: sedang, pantau selokan
• 20–50 mm/jam: lebat, waspadai genangan
• >50 mm/jam: sangat lebat / ekstrem → potensi banjir kilat dalam 1–2 jam`,

    pasca: `Yang harus dilakukan setelah banjir surut:

Sebelum masuk rumah:
• Matikan aliran listrik di MCB sampai rumah benar-benar kering dan dicek teknisi
• Cek kondisi struktur dari luar — retak dinding, fondasi ambles, atap miring
• Gunakan sepatu bot dan sarung tangan saat masuk

Saat bersih-bersih:
• Buang SEMUA makanan, minuman, obat yang terkena air banjir
• Bersihkan dengan air bersih + disinfektan (campuran air + pemutih 1:9)
• Jemur perabotan dan furnitur minimal 2–3 hari di bawah sinar matahari

Kesehatan:
• Waspadai leptospirosis — gejala: demam tinggi, sakit kepala, nyeri otot betis, mata merah → segera ke Puskesmas
• Waspadai diare, hepatitis A dari air kotor — masak air dulu, cuci tangan pakai sabun
• Anak-anak dan lansia prioritaskan pemeriksaan kesehatan

Laporan kerusakan: hubungi RT/RW → diteruskan ke Kelurahan untuk inventarisasi bantuan.`,

    prediksi: `Cara membaca Skor Risiko di deFlood.ai:

Skor 0–100 dihitung dari:
• Data TMA (Tinggi Muka Air) dari 38+ sensor pintu air DSDADKI
• Curah hujan realtime OpenWeather (mm/jam)
• Akumulasi hujan 3 jam & 6 jam terakhir
• Data peringatan dini BMKG
• Model XGBoost (~94% akurasi) yang dilatih dari data historis banjir Jakarta

Skala status:
• 0–30: Normal (hijau) — kondisi aman, monitoring rutin
• 30–55: Waspada (kuning) — mulai perhatikan, siapkan tas darurat kalau perlu
• 55–80: Siaga 2 (oranye) — ada risiko nyata, pantau setiap 15 menit
• 80–100: Siaga 1 / Bahaya (merah) — risiko tinggi, ikuti instruksi BPBD

Catatan: Skor Risiko adalah estimasi model ML, bukan pengganti informasi lapangan. Selalu kombinasikan dengan kondisi di sekitarmu dan pantau sensor TMA terdekat di peta.`,

    pompa: `Infrastruktur banjir Jakarta:
• Jakarta punya 600+ pompa banjir yang dikelola DSDADKI (Dinas Sumber Daya Air DKI)
• Titik pompa utama: Pluit (kapasitas besar), Ancol, Muara Baru, Manggarai, Sunter, Sentiong, Waduk Ria Rio
• Pintu air kritis yang dipantau sensor deFlood.ai: Manggarai, Katulampa, Depok, Cengkareng Drain

Kalau ada pompa mati atau saluran mampet di lingkunganmu:
• Lapor ke Call Center DKI: 112
• Lapor ke Dinas SDA: 021-3855555
• Lapor ke RT/RW → diteruskan ke Kelurahan → Sudin SDA setempat

Pantau status semua sensor di peta deFlood.ai untuk lihat titik kritis yang sedang naik.`,

    jalan: `Jalan & kawasan rawan banjir di Jakarta:

Jakarta Utara (paling rawan):
• Jl. Pluit Raya, Jl. Muara Baru, Jl. Muara Angke — rob + kiriman, sering 50–150 cm
• Jl. Yos Sudarso (Penjaringan–Pademangan) — rob saat pasang tinggi
• Jl. Cilincing Raya, Jl. Kalibaru Timur — bantaran kali, kiriman dari hulu
• Jl. Bandengan Utara/Selatan, Jl. Pademangan Raya

Jakarta Timur:
• Jl. Kampung Melayu Besar — TERCEPAT tergenang saat banjir kiriman Ciliwung
• Jl. Otista Raya, Jl. Matraman Raya, Jl. D.I. Panjaitan — Jatinegara/Matraman
• Jl. Cipinang Muara — bantaran Kali Cipinang
• Jl. Pulogebang, Jl. Cakung Drain — kiriman dari Bekasi

Jakarta Barat:
• Jl. Daan Mogot Raya (Km.10–Km.20) — sering macet + banjir kiriman Semanan
• Jl. Raya Semanan, Jl. Pegadungan — bantaran Kali Semanan
• Jl. Kapuk Raya, Jl. Cengkareng Raya — dekat Kali Angke
• Jl. Kyai Tapa, Jl. S. Parman — Kali Sekretaris

Jakarta Selatan (banjir kiriman Ciliwung):
• Jl. Dr. Saharjo, Jl. Bukit Duri Tanjakan — Tebet, bantaran Ciliwung
• Jl. Pesanggrahan Raya, Jl. Petukangan — bantaran Kali Pesanggrahan
• Jl. Pasar Minggu Raya — genangan sesekali

Relatif Aman:
• Kawasan Sudirman–Thamrin, Senayan/GBK, Menteng (Jl. Imam Bonjol, Jl. Diponegoro)
• Jl. TB Simatupang (JakSel selatan), Jl. Fatmawati, Jl. Ragunan
• Kawasan Monas (Jl. Medan Merdeka) — dataran tinggi

Untuk rute yang mempertimbangkan kondisi jalan: buka halaman Evakuasi → masukkan alamat.`,

    web: `deFlood.ai adalah platform pemantauan banjir realtime Jakarta. Ini fitur-fiturnya:

Command Center (halaman utama):
• Skor Risiko (0–100): model XGBoost dari 38+ sensor TMA + cuaca
• 3 kartu metrik: jumlah stasiun siaga, total stasiun aktif, skor risiko terkini
• Strip Curah Hujan: kondisi cuaca BMKG per 5 wilayah Jakarta (lengkap suhu + kelembapan)
• Sensor strip: muka air %, tren naik/turun, akumulasi hujan, anomali

Peta Risiko:
• Titik sensor pintu air DSDADKI realtime (warna = level siaga)
• Estimasi zona risiko ML per area Jakarta
• Klik titik sensor untuk lihat detail ketinggian air

Tabel Sensor:
• Semua pos pantau dengan tinggi air aktual vs ambang Siaga 1
• Progress bar persentase untuk tiap stasiun

Halaman Evakuasi:
• Masukkan alamatmu → dapat rute ke shelter pengungsian terdekat
• 5 langkah evakuasi terstandar BPBD

Chatbot Flo (aku!):
• Tanya kondisi banjir, info wilayah RT/RW, jarak ke shelter, kontak darurat, cara baca sensor

Data diperbarui setiap 15 menit dari DSDADKI, BMKG, dan OpenWeather.`,

    rtrw: `RT/RW rawan banjir di Jakarta berdasarkan data historis BPBD:

Jakarta Utara — Kec. Penjaringan:
• Kel. Pluit: RT 001–021/RW 001–017 (Muara Baru, Muara Angke — ROB + kiriman, paling parah)
• Kel. Pejagalan: RT 001–008/RW 001–003
• Kel. Penjaringan: RT 001–010/RW 001–004

Jakarta Utara — Kec. Pademangan:
• Kel. Pademangan Barat: RT 001–020/RW 001–009 (dekat Kali Sentiong, ~40–80 cm)

Jakarta Utara — Kec. Cilincing:
• Kel. Semper Barat: RT 001–018/RW 001–008 | Kel. Kalibaru: RT 001–012/RW 001–005

Jakarta Timur — Kec. Jatinegara:
• Kel. Kampung Melayu: RT 001–016/RW 001–007 (TERCEPAT tergenang saat kiriman Ciliwung)
• Kel. Cipinang Muara: RT 001–014/RW 001–006 | Kel. Bidara Cina: RT 001–012/RW 001–005

Jakarta Timur — Kec. Matraman:
• Kel. Utan Kayu Selatan: RT 001–010/RW 001–004 | Kel. Kebon Manggis: RT 001–009/RW 001–004

Jakarta Barat — Kec. Kalideres:
• Kel. Kalideres: RT 001–018/RW 001–008 | Kel. Semanan: RT 001–015/RW 001–006

Jakarta Barat — Kec. Cengkareng:
• Kel. Cengkareng Barat: RT 001–020/RW 001–010 | Kel. Kapuk: RT 001–025/RW 001–011

Jakarta Selatan — Kec. Tebet:
• Kel. Bukit Duri: RT 001–012/RW 001–005 (bantaran Ciliwung, bisa 1–2 meter)
• Kel. Kebon Baru: RT 001–010/RW 001–004

Jakarta Selatan — Kec. Pesanggrahan:
• Kel. Petukangan Utara: RT 001–016/RW 001–007 | Kel. Pesanggrahan: RT 001–014/RW 001–006

Nomor RT/RW adalah rentang — tidak semua nomor di rentang itu selalu terdampak. Yang paling berisiko adalah RT yang langsung di bantaran kali. Cek kondisi aktual ke ketua RT/RW setempat.`,

    landmark: `Status rawan banjir tempat-tempat umum di Jakarta:

Mall / Pusat Perbelanjaan:
RAWAN: Pluit Village & Emporium Pluit (Penjaringan — area rob), ITC Roxy Mas (Grogol), Mangga Dua Square (Sawah Besar), Seasons City (Tambora)
PANTAU: Mall Ambassador (Tebet, dekat Ciliwung), Ciputra Mall (Grogol Petamburan)
AMAN (elevated/drainase baik): Grand Indonesia, Plaza Indonesia, Senayan City, Pondok Indah Mall, Taman Anggrek, Central Park, Lippo Mall Kemang, Kota Kasablanka, MOI Kelapa Gading

Rumah Sakit (gedung umumnya elevated meski areanya rawan):
Dekat area rawan: RSUD Koja (Cilincing), RSUD Jatinegara, RS Pelabuhan (Penjaringan)
Aman sebagai rujukan darurat: RSCM (Gambir), RSUD Tarakan (Gambir), RS Carolus (Senen), RSPI Sulianti Saroso (Tanjung Priok), RS Fatmawati (JakSel), RS Budi Kemuliaan (JakPus)

Sekolah (sering jadi posko evakuasi):
SDN Pluit 01–05 (Kec. Penjaringan) · SDN Kampung Melayu 01–03 (Kec. Jatinegara)
SDN Kalideres 01–04 (Kec. Kalideres) · SDN Cengkareng 01–06 (Kec. Cengkareng)
→ Hubungi BPBD 117 atau RT/RW untuk status posko aktif saat kejadian

Tempat Lain:
Rawan genangan: Pasar Ikan Muara Baru, Pasar Jatinegara, Pasar Kalideres, Terminal Kalideres, Terminal Pulo Gadung (pantau saat kiriman)
Aman / dataran tinggi: Monas, Senayan/GBK, TMII, Kemang Village, kawasan Sudirman-Thamrin`,

    jarak: `Estimasi jarak dari titik rawan ke shelter terdekat (perkiraan — untuk rute akurat buka halaman Evakuasi):

Dari Pluit (Kel. Pluit, JakUt):
→ GOR Tanjung Priok (Jl. Enggano No.1): ~4 km, ~10 mnt kendaraan

Dari Pademangan Barat:
→ GOR Tanjung Priok: ~3 km, ~8 mnt kendaraan

Dari Kampung Melayu (Kec. Jatinegara):
→ Kantor Walikota JakTim: ~4,5 km, ~12 mnt
→ GOR Cakung: ~6 km, ~15 mnt

Dari Bukit Duri / Tebet:
→ Balai Rakyat Kec. Pasar Minggu: ~3 km, ~8 mnt
→ Stadion Lebak Bulus: ~7 km, ~20 mnt

Dari Kalideres (Kel. Kalideres):
→ GOR Kalideres (Jl. Daan Mogot Km.19): ~1,5 km, ~5 mnt — PALING DEKAT

Dari Semanan / Cengkareng Barat:
→ GOR Kalideres: ~3–4 km, ~8–10 mnt

Dari Cilincing / Semper Barat:
→ Kantor Kec. Cilincing: ~1–2 km, bisa jalan kaki kalau tidak terputus banjir

Dari Cakung:
→ GOR Cakung: ~2 km, ~6 mnt

Dari Kemayoran:
→ GOR Kemayoran: ~1 km, ~3 mnt

Saat banjir: jalan normal sering terputus. Hubungi BPBD 117 untuk evakuasi pakai perahu atau kendaraan khusus. Untuk rute yang mempertimbangkan kondisi jalan realtime → buka halaman Evakuasi di menu atas.`,
  },

  en: {
    evakuasi: `Evacuation steps when flooding starts:
1. Pack an emergency bag: ID, health insurance card, bank book (scan to Google Drive NOW), meds, 3 days of clothes, 1.5L water, flashlight, power bank, cash — all in waterproof zip-locks.
2. Turn off electricity at the main breaker and close the gas valve.
3. Inform your RT/RW leader and family about your evacuation plan.
4. Open the Evacuation page in the top menu → type your address → get a route to the nearest shelter.
5. Can't evacuate alone? Call BPBD at 117 — they coordinate boat evacuations in flooded areas.
Don't wait for water to enter your house — if your area is at Siaga 2, start preparing now.`,

    status: `Jakarta flood status is updated every 15 minutes from 38+ DSDADKI water level sensors.
How to read it here:
• Risk Score (top): 0–100. <30 Normal, 30–55 Watch, 55–80 Alert 2, >80 Alert 1/Danger
• Rainfall cards: BMKG weather per district (Pusat/Utara/Barat/Selatan/Timur)
• Sensor strip: water level %, trend arrows, rain accumulation
• Station table: all monitoring points with actual vs threshold heights
All green = safe. Orange/red = monitor closely or prepare to evacuate.`,

    wilayah: `Jakarta's most flood-prone areas based on historical data:

High Risk:
• North Jakarta — Penjaringan (Pluit, Muara Baru), Pademangan, Cilincing. Tidal + upstream flooding.
• East Jakarta — Jatinegara/Kampung Melayu (Ciliwung river from Bogor), Cakung

At Risk:
• West Jakarta — Kalideres (Kali Semanan), Cengkareng, Tambora (Kali Angke)
• South Jakarta — Tebet/Bukit Duri (Ciliwung riverside), Pesanggrahan, Pasar Minggu

Watch during heavy rain:
• Central Jakarta — Kemayoran, Sawah Besar (local flooding, usually drains faster)

Check realtime sensor conditions on the deFlood.ai map or ask your local RT/RW leader.`,

    tanda: `Warning signs that flooding is coming:
• Rain hasn't stopped for 30+ minutes and is intensifying
• Drains/canals rising and turning murky brown
• Strong smell of wet earth and mud
• Katulampa dam (Bogor) status rising to Siaga 2 or 1 (check BPBD website)
• Neighbors in upstream areas already evacuating
• BPBD notification or BMKG alert on your phone

For East/South Jakarta: Katulampa at Siaga 1 = water arrives at Kampung Melayu in 6–8 hours.
For North Jakarta: watch tidal conditions + local rainfall intensity simultaneously.
See 2–3 signs at once? Start preparing your emergency bag and check evacuation routes.`,

    shelter: `Jakarta emergency shelter locations (open/close based on emergency — always confirm with BPBD 117):

North Jakarta: GOR Tanjung Priok (Jl. Enggano No.1), Penjaringan sub-district schools, Cilincing sub-district office
West Jakarta: GOR Kalideres (Jl. Daan Mogot Km.19), Tambora community hall
East Jakarta: GOR Cakung, East Jakarta City Hall (Jl. D.I. Panjaitan, Matraman)
South Jakarta: Lebak Bulus Stadium (Cilandak), Pasar Minggu community center
Central Jakarta: Central Jakarta City Hall (Menteng), GOR Kemayoran

Fastest way: open the Evacuation page from the top menu → enter your address → automatic route to nearest shelter.
BPBD Jakarta: 117 (24 hours, real-time shelter availability).`,

    kontak: `Emergency numbers for Jakarta — save these now:
• BPBD Jakarta (Disaster Management): 117
• Basarnas (National SAR): 115
• Ambulance (Jakarta Health Office): 119 — or 112
• Jakarta Emergency Call Center: 112
• DSDADKI (pumps & water gates): 021-3855555
• Indonesian Red Cross (PMI Jakarta): 021-3006767

If water is rising fast and you can't evacuate alone: call BPBD 117 and your local RT/RW leader — local coordination is often faster for neighborhood evacuations.`,

    durasi: `How long flooding typically lasts in Jakarta:
• Flash flooding / local pooling (rain >50mm/h, no upstream): clears 2–6 hours after rain stops. Central Jakarta usually fastest.
• Upstream flooding from Bogor (via Ciliwung River):
  - Katulampa Alert 3: arrives at Kampung Melayu in ~4–6 hrs, flooding lasts 12–24 hrs
  - Katulampa Alert 2: arrives ~5–8 hrs, flooding 24–36 hrs
  - Katulampa Alert 1: arrives ~6–8 hrs, flooding 24–72+ hrs
• Tidal flooding in North Jakarta (Oct–Apr): 4–12 hours per cycle, can repeat daily
• Mixed flooding (rain + upstream + tidal): worst case, can last 2–4 days

Monitor Katulampa dam status for upstream flood predictions. Check deFlood.ai sensor map for real-time conditions.`,

    dokumen: `Important documents to secure before evacuating:
• Identity: national ID (KTP), family card, driver's license, passport
• Property: land/house certificate, vehicle registration (BPKB)
• Financial: bank books, ATM cards, credit cards
• Medical: BPJS/insurance card, prescription meds, blood type note
• Children: school certificates if easily accessible

How to protect them:
1. Scan/photo everything → upload to Google Drive or email yourself NOW (don't wait for floods)
2. Originals in waterproof zip-lock bags, kept in your emergency bag
3. Carry them on your person when evacuating — don't leave them in the house

If flooding has already started: save yourself first — documents can be replaced.`,

    cuaca: `For Jakarta weather forecasts:
• Official BMKG: bmkg.go.id or the Info BMKG app (free on Play Store/App Store)
• Per sub-district forecast: cuaca.bmkg.go.id
• Real-time radar: iklim.bmkg.go.id/iklim/radar

deFlood.ai uses BMKG data for current conditions (see the Rainfall cards), but doesn't forecast future rain — that's BMKG's domain.

Rainfall intensity scale to watch:
• 0–5 mm/h: light, safe
• 5–20 mm/h: moderate, watch drains
• 20–50 mm/h: heavy, watch for pooling
• >50 mm/h: very heavy/extreme → flash flood risk within 1–2 hours`,

    pasca: `What to do after flooding recedes:

Before entering your home:
• Keep electricity off at the main breaker until the house is dry and inspected
• Check the structure from outside — cracks in walls, sinking foundation, tilted roof
• Use rubber boots and gloves when entering

During cleanup:
• Throw away ALL food, drinks, and medicine that touched floodwater
• Clean surfaces with water + disinfectant (bleach solution, 1:9 ratio)
• Air out furniture and belongings for 2–3 days in sunlight

Health risks:
• Leptospirosis — symptoms: high fever, severe headache, muscle pain in calves, red eyes → see a clinic immediately
• Diarrhea, Hepatitis A from contaminated water — boil water, wash hands with soap
• Prioritize health checks for children and elderly

Report damage to your RT/RW leader for government assistance registration.`,

    prediksi: `How to read the Risk Score on deFlood.ai:

Score 0–100 is calculated from:
• TMA (water level) data from 38+ DSDADKI water gate sensors
• Real-time rainfall from OpenWeather (mm/h)
• 3-hour and 6-hour rainfall accumulation
• BMKG early warning alerts
• XGBoost ML model (~94% accuracy) trained on historical Jakarta flood data

Status scale:
• 0–30: Normal (green) — safe conditions, routine monitoring
• 30–55: Watch (yellow) — start paying attention, prep emergency bag if needed
• 55–80: Alert 2 (orange) — real risk, check sensors every 15 minutes
• 80–100: Alert 1 / Danger (red) — high risk, follow BPBD instructions

Note: Risk Score is an ML estimate, not a replacement for ground truth. Always combine with what you see around you and monitor the nearest TMA sensor on the map.`,

    pompa: `Jakarta's flood infrastructure:
• 600+ flood pumps managed by DSDADKI (Jakarta Water Resources Agency)
• Major pump stations: Pluit (largest), Ancol, Muara Baru, Manggarai, Sunter, Sentiong, Ria Rio Reservoir
• Critical monitored water gates: Manggarai, Katulampa, Depok, Cengkareng Drain

If a pump is broken or a canal is blocked in your area:
• Report to DKI Emergency: 112
• Report to DSDADKI: 021-3855555
• Report to your RT/RW → forwarded to Kelurahan → local Water Resources sub-office

Monitor all sensor conditions on the deFlood.ai map to see which points are currently rising.`,

    jalan: `Flood-prone streets and districts in Jakarta:

North Jakarta (highest risk):
• Jl. Pluit Raya, Jl. Muara Baru, Jl. Muara Angke — tidal + upstream, 50–150 cm common
• Jl. Yos Sudarso (Penjaringan–Pademangan) — tidal flooding at high tide
• Jl. Cilincing Raya, Jl. Kalibaru Timur — riverbank, upstream flooding
• Jl. Bandengan Utara/Selatan, Jl. Pademangan Raya

East Jakarta:
• Jl. Kampung Melayu Besar — FASTEST to flood during Ciliwung overflow
• Jl. Otista Raya, Jl. Matraman Raya, Jl. D.I. Panjaitan — Jatinegara/Matraman
• Jl. Cipinang Muara — Kali Cipinang riverside
• Jl. Pulogebang, Jl. Cakung Drain — upstream from Bekasi

West Jakarta:
• Jl. Daan Mogot Raya (Km.10–Km.20) — upstream flooding + traffic jams
• Jl. Raya Semanan, Jl. Pegadungan — Kali Semanan riverside
• Jl. Kapuk Raya, Jl. Cengkareng Raya — near Kali Angke
• Jl. Kyai Tapa, Jl. S. Parman — Kali Sekretaris area

South Jakarta (Ciliwung upstream):
• Jl. Dr. Saharjo, Jl. Bukit Duri Tanjakan — Tebet, Ciliwung riverside
• Jl. Pesanggrahan Raya, Jl. Petukangan — Kali Pesanggrahan
• Jl. Pasar Minggu Raya — occasional flooding

Relatively Safe:
• Sudirman–Thamrin corridor, Senayan/GBK, Menteng (Jl. Imam Bonjol, Jl. Diponegoro)
• Jl. TB Simatupang (South Jakarta), Jl. Fatmawati, Jl. Ragunan
• Monas area (Jl. Medan Merdeka) — elevated ground

For live routing: open the Evacuation page → enter your address.`,

    web: `deFlood.ai is Jakarta's realtime flood monitoring platform. Here's what it does:

Command Center (main page):
• Risk Score (0–100): XGBoost model from 38+ TMA sensors + weather data
• 3 metric cards: alert stations, active stations, current risk score
• Rainfall Strip: BMKG weather per 5 Jakarta districts (includes temp + humidity)
• Sensor strip: water level %, trend arrows, rain accumulation, anomaly detection

Risk Map:
• Real-time DSDADKI water gate sensor dots (color = alert level)
• ML-based risk zone estimates per Jakarta area
• Click any sensor dot to see water level details

Station Table:
• All monitoring points with actual water height vs Siaga 1 threshold
• Progress bar showing percentage of danger threshold

Evacuation Page:
• Enter your address → get route to nearest emergency shelter
• 5 standard BPBD evacuation steps

Chatbot Flo (me!):
• Ask about flood conditions, RT/RW risk, distance to shelters, emergency contacts, sensor readings

Data updates every 15 minutes from DSDADKI, BMKG, and OpenWeather.`,

    rtrw: `Flood-prone RT/RW in Jakarta (based on BPBD historical data):

North Jakarta — Kec. Penjaringan:
• Kel. Pluit: RT 001–021/RW 001–017 (Muara Baru, Muara Angke — tidal + upstream, worst area)
• Kel. Pejagalan: RT 001–008/RW 001–003 | Kel. Penjaringan: RT 001–010/RW 001–004

North Jakarta — Kec. Pademangan:
• Kel. Pademangan Barat: RT 001–020/RW 001–009 (near Kali Sentiong, ~40–80 cm)

North Jakarta — Kec. Cilincing:
• Kel. Semper Barat: RT 001–018/RW 001–008 | Kel. Kalibaru: RT 001–012/RW 001–005

East Jakarta — Kec. Jatinegara:
• Kel. Kampung Melayu: RT 001–016/RW 001–007 (FASTEST to flood — Ciliwung overflow)
• Kel. Cipinang Muara: RT 001–014/RW 001–006 | Kel. Bidara Cina: RT 001–012/RW 001–005

East Jakarta — Kec. Matraman:
• Kel. Utan Kayu Selatan: RT 001–010/RW 001–004 | Kel. Kebon Manggis: RT 001–009/RW 001–004

West Jakarta — Kec. Kalideres:
• Kel. Kalideres: RT 001–018/RW 001–008 | Kel. Semanan: RT 001–015/RW 001–006

West Jakarta — Kec. Cengkareng:
• Kel. Cengkareng Barat: RT 001–020/RW 001–010 | Kel. Kapuk: RT 001–025/RW 001–011

South Jakarta — Kec. Tebet:
• Kel. Bukit Duri: RT 001–012/RW 001–005 (Ciliwung riverside, can reach 1–2 meters)
• Kel. Kebon Baru: RT 001–010/RW 001–004

South Jakarta — Kec. Pesanggrahan:
• Kel. Petukangan Utara: RT 001–016/RW 001–007 | Kel. Pesanggrahan: RT 001–014/RW 001–006

RT/RW numbers are ranges — not every number in the range floods. Highest risk is RTs directly on riverbanks. Confirm with your local RT/RW leader.`,

    landmark: `Flood risk status of key Jakarta locations:

Malls / Shopping Centers:
AT RISK: Pluit Village & Emporium Pluit (tidal flooding), ITC Roxy Mas (Grogol), Mangga Dua Square, Seasons City (Tambora)
WATCH: Mall Ambassador (Tebet, near Ciliwung), Ciputra Mall (Grogol)
SAFE (elevated/good drainage): Grand Indonesia, Plaza Indonesia, Senayan City, Pondok Indah Mall, Taman Anggrek, Central Park, Lippo Mall Kemang, Kota Kasablanka, MOI Kelapa Gading

Hospitals (buildings usually elevated even in flood-prone areas):
Near flood zones: RSUD Koja (Cilincing), RSUD Jatinegara, RS Pelabuhan (Penjaringan)
Safe emergency referrals: RSCM (Gambir), RSUD Tarakan, RS Carolus (Senen), RSPI Sulianti Saroso, RS Fatmawati

Schools (often become evacuation shelters):
SDN Pluit 01–05 · SDN Kampung Melayu 01–03 · SDN Kalideres 01–04 · SDN Cengkareng 01–06
→ Call BPBD 117 or local RT/RW to confirm which schools are active shelters during flooding

Other Landmarks:
Flood-prone: Pasar Ikan Muara Baru, Pasar Jatinegara, Terminal Kalideres, Terminal Pulo Gadung
Safe / elevated: Monas, Senayan/GBK, TMII, Kemang Village, Sudirman-Thamrin corridor`,

    jarak: `Estimated distances from flood-prone areas to nearest shelters (use the Evacuation page for live routing):

From Pluit (Kel. Pluit, North Jakarta):
→ GOR Tanjung Priok (Jl. Enggano No.1): ~4 km, ~10 min by vehicle

From Pademangan Barat:
→ GOR Tanjung Priok: ~3 km, ~8 min

From Kampung Melayu (Kec. Jatinegara):
→ East Jakarta City Hall: ~4.5 km, ~12 min | GOR Cakung: ~6 km, ~15 min

From Bukit Duri / Tebet:
→ Balai Rakyat Pasar Minggu: ~3 km, ~8 min | Lebak Bulus Stadium: ~7 km, ~20 min

From Kalideres:
→ GOR Kalideres (Jl. Daan Mogot Km.19): ~1.5 km, ~5 min — CLOSEST

From Semanan / Cengkareng Barat:
→ GOR Kalideres: ~3–4 km, ~8–10 min

From Cilincing / Semper Barat:
→ Cilincing sub-district office: ~1–2 km, walkable if roads aren't cut off

From Cakung:
→ GOR Cakung: ~2 km, ~6 min

From Kemayoran:
→ GOR Kemayoran: ~1 km, ~3 min

During flooding: normal roads are often blocked. Call BPBD 117 for boat or special vehicle evacuation. For real-time routing → open the Evacuation page from the top menu.`,
  },
};

// ─── Offline Matcher ───────────────────────────────────────────────────────────
function _matchOffline(text, lang) {
  const t = text.toLowerCase()
    // typo corrections
    .replace(/bnjir|banjr|bajir/g, "banjir")
    .replace(/\bevak\w*/g, "evakuasi")
    .replace(/kmna|kemaa|kemane/g, "kemana")
    .replace(/gmn|gmna|bgmn/g, "gimana")
    .replace(/klo|kl\b/g, "kalau")
    .replace(/hrs\b/g, "harus")
    .replace(/skrg|skrang/g, "sekarang")
    .replace(/tlp|tlpon|telpn/g, "telepon")
    .replace(/pasca|abis banjir|sesudah banjir/g, "setelah banjir")
    .replace(/skor risiko|scr risiko/g, "skor")
    .replace(/web(site|app)?|aplikasi|app\b|fitur/g, "website")
    // Jakarta wilayah abbreviations
    .replace(/\bpik\b/g, "pluit penjaringan")
    .replace(/\bjak[\s-]?ut\b|\bjakut\b/g, "jakarta utara")
    .replace(/\bjak[\s-]?bar\b|\bjakbar\b/g, "jakarta barat")
    .replace(/\bjak[\s-]?tim\b|\bjaktim\b/g, "jakarta timur")
    .replace(/\bjak[\s-]?sel\b|\bjaksel\b/g, "jakarta selatan")
    .replace(/\bjak[\s-]?pus\b|\bjakpus\b/g, "jakarta pusat")
    // area / kecamatan informal
    .replace(/\bkampmel\b|\bkamp[\s.]?mel\b|\bk[\s.]melayu\b/g, "kampung melayu")
    .replace(/\bkalder\b|\bkalidrs\b/g, "kalideres")
    .replace(/\bpenjar\b|\bpenjrng\b/g, "penjaringan")
    .replace(/\bcengkrng\b|\bcengkrg\b/g, "cengkareng")
    .replace(/\bpadam\b|\bpdmgn\b/g, "pademangan")
    .replace(/\bmangdu\b/g, "mangga dua")
    .replace(/\bkalgading\b|\bkel[\s.]gading\b/g, "kelapa gading")
    .replace(/\btpi\b/g, "tanjung priok");
  const kb = OFFLINE_KB[lang] ?? OFFLINE_KB.id;

  // Street / road names
  if (t.includes("jalan") || t.includes("jl.") || /\bjl\s+[a-z]/.test(t) || t.includes("street") || t.includes("road") || t.includes("kawasan") || t.includes("perumahan") || t.includes("komplek") || t.includes("kali ") || t.includes("sungai")) return kb.jalan;
  // Website / app explanation
  if (t.includes("website") || t.includes("ini apa") || t.includes("cara pakai") || t.includes("cara baca") || t.includes("penjelasan") || t.includes("explain") || t.includes("what is") || t.includes("how does") || t.includes("fitur")) return kb.web;
  // Flood duration / Katulampa
  if (t.includes("berapa lama") || t.includes("lamanya") || t.includes("lama nya") || t.includes("kapan surut") || t.includes("how long") || t.includes("durasi") || t.includes("katulampa")) return kb.durasi;
  // Distances to shelters
  if (t.includes("berapa jauh") || t.includes("jarak") || t.includes("how far") || t.includes("distance") || t.includes("dekat") || t.includes("km dari") || t.includes("menit dari") || t.includes("berapa menit")) return kb.jarak;
  // Landmarks (mall, school, hospital, etc.)
  if (t.includes("mall") || t.includes("plaza") || t.includes("rs ") || t.includes("rumah sakit") || t.includes("puskesmas") || t.includes("sekolah") || t.includes("sdn") || t.includes("smpn") || t.includes("sman") || t.includes("pasar") || t.includes("terminal") || t.includes("hospital") || t.includes("school") || t.includes("landmark")) return kb.landmark;
  // RT/RW numbered data
  if (/\brt\b|\brw\b|rt\/rw|nomor rt|rukun tetangga/.test(t) || t.includes("rt 0") || t.includes("rw 0")) return kb.rtrw;
  // Wilayah / area / kecamatan general
  if (t.includes("wilayah") || t.includes("kecamatan") || t.includes("kelurahan") || t.includes("mana yang rawan") || t.includes("area") || t.includes("daerah") || t.includes("district")) return kb.wilayah;
  // Evacuation / where to go
  if (/kemana|harus kemana|pergi ke mana|ke mana/.test(t) || t.includes("evakuasi") || t.includes("evacuati") || t.includes("bawa") || t.includes("tas darurat") || t.includes("langkah") || t.includes("steps") || t.includes("pack") || t.includes("bring")) return kb.evakuasi;
  // Status / current conditions
  if (t.includes("status") || t.includes("sekarang") || t.includes("current") || t.includes("kondisi") || t.includes("condition") || t.includes("aman") || t.includes("safe")) return kb.status;
  // Warning signs
  if (t.includes("tanda") || t.includes("sign") || t.includes("gejala") || t.includes("ciri") || t.includes("akan datang") || t.includes("coming") || t.includes("mau banjir")) return kb.tanda;
  // Shelter locations
  if (t.includes("shelter") || t.includes("pengungsian") || t.includes("tempat aman") || t.includes("refuge") || t.includes("lokasi") || t.includes("kemana")) return kb.shelter;
  // Emergency contacts
  if (t.includes("kontak") || t.includes("contact") || t.includes("nomor") || t.includes("telepon") || t.includes("hubungi") || t.includes("call") || t.includes("phone") || t.includes("darurat")) return kb.kontak;
  // Documents
  if (t.includes("dokumen") || t.includes("document") || t.includes("surat") || t.includes("amankan") || t.includes("berkas") || t.includes("ktp") || t.includes("secure")) return kb.dokumen;
  // Weather / forecast
  if (t.includes("cuaca") || t.includes("weather") || t.includes("prakiraan") || t.includes("forecast") || t.includes("hujan") || t.includes("rain") || t.includes("bmkg") || t.includes("mm")) return kb.cuaca;
  // Post-flood
  if (t.includes("setelah banjir") || t.includes("after flood") || t.includes("surut") || t.includes("bersih") || t.includes("pasca") || t.includes("sakit") || t.includes("leptospir") || t.includes("cleanup")) return kb.pasca;
  // Risk score / how to read
  if (t.includes("skor") || t.includes("score") || t.includes("siaga") || t.includes("waspada") || t.includes("prediksi") || t.includes("akurasi") || t.includes("model")) return kb.prediksi;
  // Pumps / infrastructure
  if (t.includes("pompa") || t.includes("pump") || t.includes("drainase") || t.includes("drainage") || t.includes("saluran") || t.includes("pintu air") || t.includes("dsdadki")) return kb.pompa;
  // Jakarta location keyword fallback — catches questions like "banjir di pik?" or "pluit aman?"
  // after abbreviation normalization above (e.g. "pik" → "pluit penjaringan")
  if (/\b(penjaringan|pluit|pademangan|cilincing|kalideres|cengkareng|tambora|grogol|kampung melayu|jatinegara|matraman|cakung|kramat jati|tebet|pesanggrahan|pasar minggu|kemayoran|sawah besar|tanjung priok|sunter|kelapa gading|ancol|muara baru|muara angke|kapuk|semanan|bukit duri|cipinang|mangga dua)\b/.test(t)) return kb.wilayah;
  return null;
}

function compactStations(stations = []) {
  return stations
    .filter(Boolean)
    .slice()
    .sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0))
    .slice(0, 6)
    .map((s) => ({
      nama: s.nama,
      lokasi: s.lokasi,
      status_siaga: s.status_siaga,
      ratio: s.ratio,
      tinggi_air: s.tinggi_air,
    }));
}

function compactWilayahSummary(wilayahSummary = []) {
  return wilayahSummary
    .filter(Boolean)
    .slice(0, 6)
    .map((w) => ({
      wilayah: w.wilayah,
      worst_status: w.worst_status,
      worst_rank: w.worst_rank,
      tma_count: w.tma_count,
      forecast: (w.forecast ?? []).slice(0, 3).map((f) => ({
        local_datetime: f.local_datetime,
        weather_desc: f.weather_desc,
        tmin: f.tmin,
        tmax: f.tmax,
        humin: f.humin,
        humax: f.humax,
      })),
    }));
}

function buildAgentContext(riskContext = {}) {
  return {
    level: riskContext.level,
    riskScore: riskContext.riskScore,
    rainfall: riskContext.rainfall,
    rainfallAcc3h: riskContext.rainfallAcc3h,
    rainfallAcc6h: riskContext.rainfallAcc6h,
    rainfallTrendMmH: riskContext.rainfallTrendMmH,
    humidity: riskContext.humidity,
    temperature: riskContext.temperature,
    waterLevelRatio: riskContext.waterLevelRatio,
    waterLevelDelta: riskContext.waterLevelDelta,
    bmkgAlerts: riskContext.bmkgAlerts,
    snapshotFetchedAt: riskContext.snapshotFetchedAt,
    tmaStationsActive: riskContext.tmaStationsActive,
    recommendedActions: (riskContext.recommendedActions ?? []).slice(0, 3),
    stations: compactStations(riskContext.stations ?? []),
    wilayahSummary: compactWilayahSummary(riskContext.wilayahSummary ?? []),
  };
}

export async function sendToFloodAgent(message, history = [], riskContext = {}, lang = "id") {
  const context = buildAgentContext(riskContext);

  const controller = new AbortController();
  const chatTimer = setTimeout(() => controller.abort(), 28000);
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        history: history.map((m) => ({ role: m.role, content: m.content })),
        system: SYSTEM_PROMPT,
        context,
        lang,
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
    ? "I'm offline right now. For emergencies: BPBD 117 · Basarnas 115 · Ambulance 119.\nYou can ask about: flood-prone areas by kecamatan, shelter locations, evacuation steps, how long flooding lasts, emergency contacts, or how to use this website."
    : "AI lagi offline. Darurat: BPBD 117 · Basarnas 115 · Ambulans 119.\nCoba tanya: wilayah/kecamatan rawan banjir, lokasi shelter, langkah evakuasi, berapa lama banjir berlangsung, kontak darurat, atau penjelasan fitur website ini.";
  return { success: false, reply: generic, isAI: false };
}

export const quickReplies = [
  "Kondisi banjir Jakarta sekarang?",
  "Harus pergi ke mana kalau banjir?",
  "Apa yang harus dibawa saat evakuasi?",
  "Nomor darurat yang harus dihubungi?",
];
