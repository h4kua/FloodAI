import { useApp } from "../lib/appContext";
import ChatBot from "../components/ChatBot";
import CollapsibleSection from "../components/shell/CollapsibleSection";

const isId = (lang) => lang === "id";

const LinkedInSVG = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
  </svg>
);

function Section({ title, children }) {
  return (
    <div className="panel panel-body">
      <p className="about-section-title">{title}</p>
      {children}
    </div>
  );
}

function Row({ tag, title, desc }) {
  return (
    <div className="about-row">
      <span className="about-tag">{tag}</span>
      <div>
        <p className="about-row-title">{title}</p>
        <p className="about-row-desc">{desc}</p>
      </div>
    </div>
  );
}

function TeamCard({ role, roleType, name, linkedin }) {
  return (
    <div className="team-card">
      <div style={{ display: "flex", flex: 1, flexDirection: "column", justifyContent: "space-between", height: "100%", width: "100%" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <span className={`team-role ${roleType}`}>{role}</span>
          <p className="team-name">{name}</p>
        </div>
        <a href={linkedin} target="_blank" rel="noopener noreferrer" className="li-btn">
          <LinkedInSVG />
          LinkedIn
        </a>
      </div>
    </div>
  );
}

// lowerIsBetter: bar shows inverted fill so a LOW score = LONG bar (green = good)
function MetricBar({ label, value, max = 1, color = "var(--cyan)", format, hint, lowerIsBetter = false }) {
  const rawPct = Math.min(value / max, 1) * 100;
  const barPct = lowerIsBetter ? (1 - Math.min(value / max, 1)) * 100 : rawPct;
  const display = format ? format(value) : value;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", minWidth: 0 }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text)" }}>{label}</span>
          {hint && <span style={{ fontSize: "0.78rem", color: "var(--muted-2)" }}>{hint}</span>}
        </div>
        <span style={{ fontSize: "0.85rem", fontWeight: 700, color, flexShrink: 0 }}>{display}</span>
      </div>
      <div style={{ height: "5px", background: "var(--line)", borderRadius: "2px", overflow: "hidden" }}>
        <div style={{ width: `${barPct}%`, height: "100%", background: color, borderRadius: "2px", transition: "width 0.6s ease" }} />
      </div>
    </div>
  );
}

function Step({ num, label, desc }) {
  return (
    <div style={{ display: "flex", gap: "0.875rem", alignItems: "flex-start" }}>
      <span className="step-num">{num}</span>
      <div>
        <p className="step-title">{label}</p>
        <p className="step-desc">{desc}</p>
      </div>
    </div>
  );
}

export default function About({ riskContext = {} }) {
  const { lang } = useApp();
  const id = isId(lang);

  return (
    <>
      <div className="page-header fade-in">
        <h1 className="page-title">{id ? "Tentang deFlood.ai" : "About deFlood.ai"}</h1>
      </div>

      <div className="about-grid fade-in">
        {/* What it is — one paragraph, no jargon */}
        <div className="about-hero">
          <div style={{ flex: 1, minWidth: 220 }}>
            <p style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.03em", color: "var(--cyan)", marginBottom: "0.5rem" }}>
              deFlood<span style={{ color: "var(--s1)" }}>.ai</span>
            </p>
            <p style={{ fontSize: "1rem", color: "var(--text)", lineHeight: 1.7, maxWidth: 560 }}>
              {id
                ? "deFlood.ai membantu warga Jakarta tahu apakah daerahnya aman dari banjir, dan apa yang perlu dilakukan kalau tidak. Kami membaca data ketinggian air sungai dan cuaca, lalu menyampaikannya dalam bahasa yang mudah dipahami."
                : "deFlood.ai helps Jakarta residents know whether their area is safe from flooding, and what to do if it isn't. We read river water levels and weather data, then explain them in plain language."}
            </p>
          </div>
        </div>

        <Section title={id ? "Cara kerjanya" : "How it works"}>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <Step num="1"
              label={id ? "Mengumpulkan data" : "Collecting data"}
              desc={id ? "Setiap 15 menit kami mengambil ketinggian air dari pos pantau sungai, kondisi cuaca, dan peringatan BMKG." : "Every 15 minutes we collect water levels from river monitoring posts, weather conditions, and BMKG warnings."} />
            <Step num="2"
              label={id ? "Menghitung risiko" : "Estimating the risk"}
              desc={id ? "Model komputer yang dilatih dengan data banjir Jakarta 2020–2024 memperkirakan seberapa besar kemungkinan banjir." : "A computer model trained on Jakarta flood records from 2020–2024 estimates how likely a flood is."} />
            <Step num="3"
              label={id ? "Memberi tahu Anda" : "Telling you"}
              desc={id ? "Hasilnya ditampilkan sebagai status sederhana — Aman, Waspada, Siaga, atau Bahaya — per kota dan di peta. Status tidak pernah lebih rendah dari batas siaga yang sudah dilewati pos pantau." : "The result is shown as a simple status — Safe, Watch, Alert, or Danger — per city and on the map. The status is never lower than the alert band a monitoring post has already reached."} />
            <Step num="4"
              label={id ? "Membantu Anda bertindak" : "Helping you act"}
              desc={id ? "Halaman Evakuasi mencari rute ke rumah Anda atau ke pengungsian terdekat: jalan hijau aman, jalan merah melewati area rawan banjir, lalu bisa dibuka di Google Maps. Di halaman Laporan, warga saling berbagi kondisi air, boleh dengan foto." : "The Evacuation page finds a route home or to the nearest shelter: green roads are clear, red roads pass flood-prone areas, and the route opens in Google Maps. On the Reports page, residents share what they see, photos included."} />
          </div>
        </Section>

        <Section title={id ? "Penting diketahui" : "Good to know"}>
          <ul style={{ margin: 0, paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.9rem", color: "var(--muted)", lineHeight: 1.6 }}>
            {(id ? [
              "Aplikasi ini alat bantu, bukan pengganti informasi resmi dari BPBD, BMKG, atau BNPB.",
              "Saat darurat, selalu ikuti arahan petugas BPBD dan Basarnas.",
              "Data bisa terlambat jika pos pantau belum mengirim pembaruan.",
              "Laporan warga belum diverifikasi, tampil 6 jam, dan tidak mengubah status resmi.",
            ] : [
              "This app is an aid, not a replacement for official information from BPBD, BMKG, or BNPB.",
              "In an emergency, always follow instructions from BPBD and Basarnas officers.",
              "Data can be late if monitoring posts haven't sent an update.",
              "Community reports are unverified, shown for 6 hours and never change the official status.",
            ]).map((text) => <li key={text}>{text}</li>)}
          </ul>
        </Section>

        <div style={{ gridColumn: "1 / -1" }}>
          <Section title={id ? "Tim pengembang" : "The team"}>
            <p className="team-intro">
              {id
                ? "deFlood.ai dibuat oleh mahasiswa sebagai kontribusi untuk peringatan dini banjir di Jakarta."
                : "deFlood.ai was built by students as a contribution to early flood warning in Jakarta."}
            </p>
            <div className="team-grid">
              <TeamCard role={id ? "Ketua Project" : "Project Lead"} roleType="lead" name="Juan Javier SZ" linkedin="https://www.linkedin.com/in/juanjaviersz/" />
              <TeamCard role={id ? "Anggota Tim" : "Team Member"} roleType="member" name="Jessen Wijaya Agussalim" linkedin="https://www.linkedin.com/in/jessen-wijaya-agussalim" />
              <TeamCard role={id ? "Anggota Tim" : "Team Member"} roleType="member" name="Chahniyan Regina Kasih" linkedin="https://www.linkedin.com/in/chahniyan-regina-kasih-227808280" />
              <TeamCard role={id ? "Anggota Tim" : "Team Member"} roleType="member" name="Christopher Patrick" linkedin="https://www.linkedin.com/in/christopherpatrick-gunawan" />
            </div>
          </Section>
        </div>
      </div>

      {/* Technical depth — for reviewers and developers, closed by default */}
      <CollapsibleSection
        icon="⚙"
        iconBg="var(--cyan-soft)"
        iconColor="var(--cyan)"
        title={id ? "Detail teknis" : "Technical details"}
        subtitle={id ? "Performa model, sumber data, dan teknologi" : "Model performance, data sources, and stack"}
      >
        <div className="about-grid">
          <Section title={id ? "Performa model" : "Model performance"}>
            <p style={{ fontSize: "0.85rem", color: "var(--muted)", marginBottom: "1rem", lineHeight: 1.6 }}>
              {id
                ? "Diukur sekali saat pelatihan, pada 586 baris bulanan yang dipilih acak dari 2020–2024. Data latihnya masih proksi, dan karena dipilih acak, baris uji bertetangga waktu dengan data latih. Jadi angka di bawah terlalu optimistis: saat model serupa dilatih dengan 2020–2022 lalu diuji pada 2024, AUC-nya sekitar 0,83 (rentang 0,75–0,89). Model ini belum pernah diuji dengan data lapangan."
                : "Measured once at training time on 586 monthly rows picked at random from 2020–2024. The training data is still a proxy, and because rows were picked at random, test rows sit next to training rows in time. So the figures below are optimistic: when a similar model is trained on 2020–2022 and tested on 2024, its AUC is about 0.83 (range 0.75–0.89). The model has not yet been tested on field data."}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <MetricBar label="AUC-ROC" hint={id ? "(makin tinggi makin baik)" : "(higher is better)"}
                value={0.899} color="var(--safe)" format={v => v.toFixed(3)} />
              <MetricBar label={id ? "Recall @ Siaga" : "Recall @ Alert"} hint={id ? "(makin tinggi makin baik)" : "(higher is better)"}
                value={0.875} color="var(--s2)" format={v => (v * 100).toFixed(1) + "%"} />
              <MetricBar label={id ? "Presisi" : "Precision"} hint={id ? "(makin tinggi makin baik)" : "(higher is better)"}
                value={0.282} color="var(--wsp)" format={v => (v * 100).toFixed(1) + "%"} />
              <MetricBar label="Brier Score" hint={id ? "(makin rendah makin baik)" : "(lower is better)"}
                value={0.074} max={0.25} color="var(--cyan)" lowerIsBetter format={() => "0.074"} />
              <MetricBar label={id ? "ECE (data uji)" : "ECE (test set)"} hint={id ? "(makin rendah makin baik)" : "(lower is better)"}
                value={0.062} max={0.25} color="var(--cyan)" lowerIsBetter format={() => "0.062"} />
            </div>
            <ul style={{ margin: "1rem 0 0", paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.4rem", fontSize: "0.85rem", color: "var(--muted)", lineHeight: 1.55 }}>
              <li>
                {id
                  ? "Presisi 28% berarti sekitar 7 dari 10 peringatan model adalah alarm palsu. Model sengaja dibuat sensitif supaya banjir jarang terlewat (recall 88%)."
                  : "28% precision means about 7 in 10 model warnings are false alarms. The model is deliberately sensitive so floods are rarely missed (88% recall)."}
              </li>
              <li>
                {id
                  ? "Belum ada pengukuran kalibrasi yang sahih untuk model ini di lapangan. Angka kalibrasi lain di proyek ini (ECE 0,196 dan 0,378) berasal dari versi model sebelumnya, dan penyesuaian kalibrasi saat aplikasi berjalan sedang dinonaktifkan."
                  : "There is no valid field calibration measurement for this model yet. Other calibration figures in this project (ECE 0.196 and 0.378) come from earlier model versions, and the live calibration adjustment is switched off."}
              </li>
              <li>
                {id
                  ? "Kami mencoba ratusan variasi model dan menilainya pada tahun yang belum pernah dilihat model (2024). Membuang fitur proksi dan mengkalibrasi ulang pada tahun terbaru justru menurunkan AUC menjadi 0,73, jadi model yang dipakai tidak diganti. Peningkatan berarti butuh data yang lebih baik: label banjir harian, muka air hulu, dan pasang laut."
                  : "We tried hundreds of model variants and judged them on a year the model had not seen (2024). Dropping the proxy features and recalibrating on the latest year lowered the AUC to 0.73, so the served model was kept. A real gain needs better data: daily flood labels, upstream water levels and tides."}
              </li>
            </ul>
          </Section>

          <Section title={id ? "Sumber data" : "Data sources"}>
            <Row tag="DSDADKI" title={id ? "Pos pantau ketinggian air" : "Water-level monitoring posts"}
              desc={id ? "38 titik dari Dinas Sumber Daya Air DKI (28 pos sungai, pintu air, bendung, dan waduk, serta 10 rumah pompa), diperbarui tiap 15 menit. Status memakai pos yang punya batas siaga resmi; rumah pompa tidak dihitung." : "38 points from the DKI Water Resources Agency (28 river posts, water gates, weirs and reservoirs, plus 10 pump houses), updated every 15 minutes. The status uses posts with official alert levels; pump houses are left out."} />
            <Row tag="BMKG" title={id ? "Peringatan & prakiraan cuaca" : "Weather warnings & forecasts"}
              desc={id ? "Peringatan cuaca ekstrem dan prakiraan per wilayah." : "Extreme-weather warnings and per-area forecasts."} />
            <Row tag="OWM" title="OpenWeatherMap"
              desc={id ? "Suhu, kelembapan, dan curah hujan realtime." : "Realtime temperature, humidity, and rainfall."} />
            <Row tag="BPBD" title={id ? "Data historis banjir" : "Historical flood data"}
              desc={id ? "Kejadian banjir Jakarta 2020–2024 untuk melatih model, dan titik rawan banjir untuk mewarnai jalan di peta evakuasi." : "Jakarta flood events from 2020–2024 to train the model, and flood-prone points to colour roads on the evacuation map."} />
            <Row tag="OSM" title={id ? "Peta dan rute jalan" : "Maps and road routes"}
              desc={id ? "OpenStreetMap dan OSRM untuk rute evakuasi; navigasi diteruskan ke Google Maps." : "OpenStreetMap and OSRM for evacuation routes; navigation is handed to Google Maps."} />
            <Row tag={id ? "Warga" : "Public"} title={id ? "Laporan warga" : "Community reports"}
              desc={id ? "Kabar dan foto dari warga, disimpan di Supabase. Foto diperkecil dan metadatanya (termasuk lokasi GPS kamera) dihapus." : "Updates and photos from residents, stored in Supabase. Photos are resized and stripped of metadata, including the camera's GPS location."} />
          </Section>

          <Section title={id ? "Model & AI" : "Model & AI"}>
            <Row tag="XGB" title="XGBoost Classifier"
              desc={id ? "17 fitur cuaca, hidrologi, dan geografis → peluang banjir. Mesin keputusan berlapis (L0–L4) lalu menetapkan status: data rusak jadi Tidak diketahui, dan status tidak pernah di bawah pita siaga DSDA pos pantau terparah." : "17 weather, hydrology and geographic features → a flood probability. A layered decision engine (L0–L4) then sets the status: broken data becomes Unknown, and the status never sits below the DSDA alert band of the worst post."} />
            <Row tag="OOD" title="IsolationForest"
              desc={id ? "Menandai kondisi data yang tidak biasa dibanding data latih." : "Flags data conditions that look unusual compared with the training data."} />
            <Row tag="LLM" title="Groq — Qwen3 (qwen3.8-27b)"
              desc={id ? "Menulis penjelasan dan menjawab chat. Tidak ikut menentukan status; jika gagal, dipakai template tetap." : "Writes explanations and answers chat. It does not decide the status; a fixed template is used if it fails."} />
          </Section>

          <Section title={id ? "Teknologi" : "Tech stack"}>
            <div style={{ display: "flex", flexWrap: "wrap" }}>
              {[
                "Python 3.12", "FastAPI", "XGBoost 3.2.0", "scikit-learn 1.8.0", "Groq SDK",
                "React 18", "Vite 5", "React-Leaflet 4", "Supabase / PostgreSQL", "Fly.io", "Vercel",
              ].map(tag => <span key={tag} className="tech-tag">{tag}</span>)}
            </div>
          </Section>
        </div>
      </CollapsibleSection>

      <ChatBot riskContext={riskContext} />
    </>
  );
}
