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
      <div style={{ height: "5px", background: "var(--line)", borderRadius: "99px", overflow: "hidden" }}>
        <div style={{ width: `${barPct}%`, height: "100%", background: color, borderRadius: "99px", transition: "width 0.6s ease" }} />
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
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.03em", color: "var(--cyan)", marginBottom: "0.5rem" }}>
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
              desc={id ? "Hasilnya ditampilkan sebagai status sederhana — Aman, Waspada, Siaga, atau Bahaya — beserta langkah yang disarankan." : "The result is shown as a simple status — Safe, Watch, Alert, or Danger — with suggested next steps."} />
          </div>
        </Section>

        <Section title={id ? "Penting diketahui" : "Good to know"}>
          <ul style={{ margin: 0, paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.9rem", color: "var(--muted)", lineHeight: 1.6 }}>
            {(id ? [
              "Aplikasi ini alat bantu, bukan pengganti informasi resmi dari BPBD, BMKG, atau BNPB.",
              "Saat darurat, selalu ikuti arahan petugas BPBD dan Basarnas.",
              "Data bisa terlambat jika pos pantau belum mengirim pembaruan.",
            ] : [
              "This app is an aid, not a replacement for official information from BPBD, BMKG, or BNPB.",
              "In an emergency, always follow instructions from BPBD and Basarnas officers.",
              "Data can be late if monitoring posts haven't sent an update.",
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
              <TeamCard role="Mentor" roleType="mentor" name="Haikal Helmy" linkedin="https://www.linkedin.com/in/haikal-helmy-875787305" />
              <TeamCard role="Mentor" roleType="mentor" name="Oriza Mumtaz" linkedin="https://www.linkedin.com/in/oriza-mumtaz-b9290b260" />
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
                ? "Diukur sekali saat pelatihan, pada data uji 586 baris bulanan (Jan–Des 2024). Data latihnya masih proksi, dan satu fitur (frekuensi banjir per kecamatan) dihitung dari kejadian 2020–2026 — termasuk periode uji. Jadi angka di bawah terlalu optimistis; model ini belum pernah diuji dengan data lapangan."
                : "Measured once at training time on a test set of 586 monthly rows (Jan–Dec 2024). The training data is still a proxy, and one feature (per-kecamatan flood frequency) is computed from 2020–2026 events — including the test period. So the figures below are optimistic; the model has not yet been tested on field data."}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <MetricBar label="AUC-ROC" hint={id ? "(makin tinggi makin baik)" : "(higher is better)"}
                value={0.901} color="var(--safe)" format={v => v.toFixed(3)} />
              <MetricBar label={id ? "Recall @ Siaga" : "Recall @ Alert"} hint={id ? "(makin tinggi makin baik)" : "(higher is better)"}
                value={0.839} color="var(--s2)" format={v => (v * 100).toFixed(1) + "%"} />
              <MetricBar label={id ? "Presisi" : "Precision"} hint={id ? "(makin tinggi makin baik)" : "(higher is better)"}
                value={0.263} color="var(--wsp)" format={v => (v * 100).toFixed(1) + "%"} />
              <MetricBar label="Brier Score" hint={id ? "(makin rendah makin baik)" : "(lower is better)"}
                value={0.072} max={0.25} color="var(--cyan)" lowerIsBetter format={() => "0.072"} />
              <MetricBar label={id ? "ECE (data uji)" : "ECE (test set)"} hint={id ? "(makin rendah makin baik)" : "(lower is better)"}
                value={0.014} max={0.25} color="var(--cyan)" lowerIsBetter format={() => "0.014"} />
            </div>
            <ul style={{ margin: "1rem 0 0", paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.4rem", fontSize: "0.85rem", color: "var(--muted)", lineHeight: 1.55 }}>
              <li>
                {id
                  ? "Presisi 26% berarti sekitar 3 dari 4 peringatan model adalah alarm palsu. Model sengaja dibuat sensitif supaya banjir jarang terlewat (recall 84%)."
                  : "26% precision means about 3 in 4 model warnings are false alarms. The model is deliberately sensitive so floods are rarely missed (84% recall)."}
              </li>
              <li>
                {id
                  ? "Belum ada pengukuran kalibrasi yang sahih untuk model ini di lapangan. Angka kalibrasi lain di proyek ini (ECE 0,196 dan 0,378) berasal dari versi model sebelumnya, dan penyesuaian kalibrasi saat aplikasi berjalan sedang dinonaktifkan."
                  : "There is no valid field calibration measurement for this model yet. Other calibration figures in this project (ECE 0.196 and 0.378) come from earlier model versions, and the live calibration adjustment is switched off."}
              </li>
            </ul>
          </Section>

          <Section title={id ? "Sumber data" : "Data sources"}>
            <Row tag="DSDADKI" title={id ? "Pos pantau ketinggian air" : "Water-level monitoring posts"}
              desc={id ? "38 pos pantau sungai Jakarta dari Dinas Sumber Daya Air DKI, diperbarui tiap 15 menit." : "38 Jakarta river posts from the DKI Water Resources Agency, updated every 15 minutes."} />
            <Row tag="BMKG" title={id ? "Peringatan & prakiraan cuaca" : "Weather warnings & forecasts"}
              desc={id ? "Peringatan cuaca ekstrem dan prakiraan per wilayah." : "Extreme-weather warnings and per-area forecasts."} />
            <Row tag="OWM" title="OpenWeatherMap"
              desc={id ? "Suhu, kelembapan, dan curah hujan realtime." : "Realtime temperature, humidity, and rainfall."} />
            <Row tag="BPBD" title={id ? "Data historis banjir" : "Historical flood data"}
              desc={id ? "Kejadian banjir Jakarta 2020–2024, dipakai untuk melatih model." : "Jakarta flood events from 2020–2024, used to train the model."} />
          </Section>

          <Section title={id ? "Model & AI" : "Model & AI"}>
            <Row tag="XGB" title="XGBoost Classifier"
              desc={id ? "17 fitur cuaca, hidrologi, dan geografis → 4 level risiko. Aturan hidrologi menaikkan level jika air ≥75% ambang siaga." : "17 weather, hydrology, and geographic features → 4 risk levels. A hydrology rule raises the level when water is ≥75% of the alert threshold."} />
            <Row tag="OOD" title="IsolationForest"
              desc={id ? "Menandai kondisi data yang tidak biasa dibanding data latih." : "Flags data conditions that look unusual compared with the training data."} />
            <Row tag="LLM" title="Groq — Llama 3.3 70B"
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
