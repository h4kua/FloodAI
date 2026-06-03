import { useApp } from "../lib/appContext";
import ChatBot from "../components/ChatBot";

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

function Row({ tag, title, desc, accent = false }) {
  return (
    <div className="about-row">
      <span className="about-tag" style={accent ? { color: "var(--cyan)", borderColor: "var(--cyan-border)" } : {}}>
        {tag}
      </span>
      <div>
        <p className="about-row-title">{title}</p>
        <p className="about-row-desc">{desc}</p>
      </div>
    </div>
  );
}

function Stat({ value, label }) {
  return (
    <div className="stat-item">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function TeamCard({ role, roleType, name, linkedin }) {
  return (
    <div className="team-card">
      <span className={`team-role ${roleType}`}>{role}</span>
      <p className="team-name">{name}</p>
      <a href={linkedin} target="_blank" rel="noopener noreferrer" className="li-btn">
        <LinkedInSVG />
        LinkedIn
      </a>
    </div>
  );
}

export default function About({ riskContext = {} }) {
  const { lang } = useApp();
  const id = isId(lang);

  return (
    <>
      <div className="page-header fade-in">
        <h1 className="page-title">
          {id ? "Tentang deFlood.ai" : "About deFlood.ai"}
        </h1>
      </div>

      <div className="about-grid fade-in">

        {/* Hero banner */}
        <div className="about-hero">
          <div style={{ flex: 1, minWidth: 220 }}>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.03em", color: "var(--cyan)", marginBottom: "0.5rem" }}>
              deFlood<span style={{ color: "var(--s1)" }}>.ai</span>
            </p>
            <p style={{ fontSize: "0.88rem", color: "var(--text)", lineHeight: 1.7, maxWidth: 480 }}>
              {id
                ? "Sistem kecerdasan banjir berbasis AI untuk Jakarta. Menggabungkan data sensor realtime dari 38 stasiun TMA, model machine learning XGBoost, prakiraan BMKG, dan AI generatif untuk membantu operator dan warga memantau serta merespons risiko banjir."
                : "An AI-powered flood intelligence system for Jakarta. Combines realtime sensor data from 38 TMA stations, XGBoost machine learning, BMKG forecasts, and generative AI to help operators and residents monitor and respond to flood risks."}
            </p>
          </div>
          <div className="stat-grid" style={{ minWidth: 200 }}>
            <Stat value="0.863" label="AUC-ROC" />
            <Stat value="16" label={id ? "Fitur ML" : "ML Features"} />
            <Stat value="38" label={id ? "Stasiun TMA" : "TMA Stations"} />
            <Stat value="4" label={id ? "Level Risiko" : "Risk Levels"} />
          </div>
        </div>

        {/* Data Sources */}
        <Section title={id ? "Sumber Data" : "Data Sources"}>
          <Row tag="BMKG" accent title="Badan Meteorologi, Klimatologi & Geofisika"
            desc={id
              ? "Dua feed data BMKG: nowcast alerts (peringatan ekstrem realtime) dan cuaca.json (prakiraan 10 hari untuk DKI Jakarta). Tersedia via poskobanjir.dsdadki.web.id."
              : "Two BMKG data feeds: nowcast alerts (realtime extreme weather warnings) and cuaca.json (10-day forecast for DKI Jakarta). Available via poskobanjir.dsdadki.web.id."} />
          <Row tag="DSDADKI" accent title={id ? "Posko Banjir — DSDADKI" : "Flood Post — DSDADKI"}
            desc={id
              ? "38 stasiun pemantauan tinggi muka air (TMA) sungai Jakarta via datatmalaststatus.json dari Dinas Sumber Daya Air DKI. Data realtime setiap 15 menit dengan threshold Siaga 1–4 per stasiun."
              : "38 Jakarta river water-level monitoring stations via datatmalaststatus.json from Jakarta Water Resources Agency. Realtime data every 15 minutes with Siaga 1–4 thresholds per station."} />
          <Row tag="OWM" title="OpenWeatherMap"
            desc={id
              ? "Data cuaca realtime (suhu, kelembapan, curah hujan 1j/3j) dari stasiun terdekat Jakarta. Digunakan sebagai input utama fitur meteorologi model ML."
              : "Realtime weather data (temperature, humidity, 1h/3h rainfall) from the nearest Jakarta station. Used as primary meteorological feature input for the ML model."} />
          <Row tag="HST" title={id ? "Data Historis Banjir (BPBD)" : "Historical Flood Data (BPBD)"}
            desc={id
              ? "Dataset kejadian banjir Jakarta sejak 2010 dari BPBD untuk pelatihan model. 16 fitur meteorologi dan hidrologi. Bootstrap awal sebelum data TMA realtime tersedia."
              : "Jakarta flood event dataset since 2010 from BPBD for model training. 16 meteorological and hydrological features. Initial bootstrap before realtime TMA data was available."} />
        </Section>

        {/* ML Model */}
        <Section title={id ? "Model Machine Learning" : "Machine Learning Model"}>
          <Row tag="XGB" accent title="XGBoost 3.2.0 Classifier"
            desc={id
              ? "Model gradient boosting yang mengklasifikasikan risiko ke 4 level: AMAN, WASPADA, SIAGA, BAHAYA berdasarkan kondisi cuaca dan hidrologi terkini. Dilatih dengan scikit-learn 1.8.0."
              : "Gradient boosting model classifying risk into 4 levels: SAFE, WATCH, ALERT, DANGER based on current weather and hydrological conditions. Trained with scikit-learn 1.8.0."} />
          <Row tag="16F" title={id ? "16 Fitur Input" : "16 Input Features"}
            desc={id
              ? "Curah hujan (realtime, lag, roll-3), tinggi muka air (ratio & delta), suhu, kelembapan, skor BMKG (severity/certainty/urgency), indeks hidro-meteorologi, dan flag musim."
              : "Rainfall (realtime, lag, roll-3), water level ratio & delta, temperature, humidity, BMKG scores (severity/certainty/urgency), hydro-meteorological index, and monsoon flag."} />
          <Row tag="OOD" title={id ? "IsolationForest — Deteksi Anomali Data" : "IsolationForest — Out-of-Distribution Detection"}
            desc={id
              ? "Model sekunder IsolationForest mendeteksi kondisi di luar distribusi data training. Flag OOD hanya tampil ketika muka air rendah (<75%) karena muka air ≥75% sudah ditangani hydro override secara eksplisit."
              : "Secondary IsolationForest model detects conditions outside the training distribution. OOD flag only appears at low water levels (<75%) since levels ≥75% are handled explicitly by the hydro override."} />
          <Row tag="ECE" title={id ? "Kalibrasi (ECE 0.004)" : "Calibration (ECE 0.004)"}
            desc={id
              ? "Expected Calibration Error 0.004 (n=586 test rows, 1.990 training rows) — dikalibrasi dengan isotonic regression. Brier score 0.066. Model dilatih dengan chronological 80/15/5 split dan scale_pos_weight untuk menangani class imbalance banjir."
              : "ECE 0.004 (n=586 test rows, 1,990 training rows) — calibrated with isotonic regression. Brier score 0.066. Trained with chronological 80/15/5 split and scale_pos_weight to handle flood class imbalance."} />
        </Section>

        {/* AI Chat & Agents */}
        <Section title={id ? "AI Chat & Analisis" : "AI Chat & Analysis"}>
          <Row tag="LLM" accent title="Groq SDK — Llama 3.3 70B Versatile"
            desc={id
              ? "Model bahasa besar dari Meta via Groq API untuk latensi rendah. Merespons pertanyaan seputar banjir, evakuasi, dan keselamatan dalam Bahasa Indonesia maupun Inggris. Fallback offline berbasis knowledge base tersedia."
              : "Meta's large language model via Groq API for low latency. Answers questions about flooding, evacuation, and safety in Indonesian and English. Offline knowledge-base fallback available."} />
          <Row tag="CREW" title="CrewAI 1.14.0 — 3-Agent Crew"
            desc={id
              ? "3 agen AI berjalan sekuensial: AhliCuaca (analisis BMKG & OpenWeather), AhliHidrologi (analisis TMA 37 stasiun), dan KoordinatorRisiko (sintesis keputusan akhir). Tersedia via endpoint /predict/crew-analysis."
              : "3 AI agents run sequentially: WeatherExpert (BMKG & OpenWeather analysis), HydrologyExpert (37-station TMA analysis), and RiskCoordinator (final decision synthesis). Available via /predict/crew-analysis endpoint."} />
          <Row tag="CTX" title={id ? "Konteks Risiko Realtime" : "Realtime Risk Context"}
            desc={id
              ? "Setiap percakapan menyertakan level risiko, muka air, curah hujan, dan prakiraan BMKG terkini sehingga AI memberikan jawaban yang relevan dengan kondisi aktual Jakarta."
              : "Each conversation includes current risk level, water level, rainfall, and BMKG forecast so the AI gives answers relevant to Jakarta's actual conditions."} />
        </Section>

        {/* Tech Stack */}
        <Section title={id ? "Teknologi" : "Tech Stack"}>
          <p style={{ fontSize: "0.8rem", color: "var(--muted)", marginBottom: "0.875rem", lineHeight: 1.6 }}>
            {id
              ? "Dibangun dengan stack modern, di-deploy di Fly.io (backend) dan Vercel (frontend)."
              : "Built with a lightweight modern stack, deployed on Fly.io (backend) and Vercel (frontend)."}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap" }}>
            {[
              "Python 3.12", "FastAPI", "Uvicorn",
              "XGBoost 3.2.0", "scikit-learn 1.8.0",
              "CrewAI 1.14.0", "LiteLLM 1.87.0", "Groq SDK", "Anthropic SDK",
              "React 18", "Vite 5", "React-Leaflet 4",
              "Supabase / PostgreSQL", "psycopg2",
              "Fly.io", "Vercel",
            ].map(tag => (
              <span key={tag} className="tech-tag">{tag}</span>
            ))}
          </div>
        </Section>

        {/* Disclaimer */}
        <Section title={id ? "Peringatan & Batasan" : "Disclaimer & Limitations"}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            {(id ? [
              "Data zona per wilayah adalah estimasi dari skor risiko keseluruhan dengan bias historis — bukan sensor individual per kecamatan.",
              "Model ML dilatih sebelum data TMA realtime tersedia sehingga probabilitas bisa underestimate saat muka air tinggi. Hydro override menangani kondisi ini secara rule-based.",
              "Aplikasi ini adalah alat bantu keputusan, bukan pengganti informasi resmi dari BPBD, BMKG, atau BNPB.",
              "Dalam kondisi darurat, selalu ikuti instruksi petugas BPBD dan Basarnas.",
            ] : [
              "Per-district zone data is estimated from the overall risk score with historical bias — not individual sub-district sensor data.",
              "The ML model was trained before realtime TMA data was available, so it may underestimate probability at high water levels. The hydro override handles this rule-based.",
              "This app is a decision support tool, not a replacement for official information from BPBD, BMKG, or BNPB.",
              "In emergencies, always follow instructions from BPBD and Basarnas officers.",
            ]).map((text, i) => (
              <div key={i} style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start" }}>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--wsp)", fontWeight: 700, flexShrink: 0, marginTop: "0.2rem", letterSpacing: "0.06em" }}>WARN</span>
                <p style={{ fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.55, margin: 0 }}>{text}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* Team */}
        <Section title={id ? "Tim Pengembang" : "Development Team"}>
          <p className="team-intro">
            {id
              ? "deFlood.ai dikembangkan oleh mahasiswa sebagai kontribusi terhadap sistem peringatan dini banjir Jakarta menggunakan kecerdasan buatan."
              : "deFlood.ai was built by students as a contribution to Jakarta's AI-powered early flood warning system."}
          </p>
          <div className="team-grid">
            <TeamCard
              role={id ? "Ketua Project" : "Project Lead"}
              roleType="lead"
              name="Juan Javier SZ"
              linkedin="https://www.linkedin.com/in/juanjaviersz/"
            />
            <TeamCard
              role={id ? "Anggota Tim" : "Team Member"}
              roleType="member"
              name="Jessen Wijaya Agussalim"
              linkedin="https://www.linkedin.com/in/jessen-wijaya-agussalim"
            />
            <TeamCard
              role={id ? "Anggota Tim" : "Team Member"}
              roleType="member"
              name="Chahniyan Regina Kasih"
              linkedin="https://www.linkedin.com/in/chahniyan-regina-kasih-227808280"
            />
            <TeamCard
              role={id ? "Anggota Tim" : "Team Member"}
              roleType="member"
              name="Christopher Patrick"
              linkedin="https://www.linkedin.com/in/christopherpatrick-gunawan"
            />
            <TeamCard
              role={id ? "Mentor" : "Mentor"}
              roleType="mentor"
              name="Haikal Helmy"
              linkedin="https://www.linkedin.com/in/haikal-helmy-875787305"
            />
            <TeamCard
              role={id ? "Mentor" : "Mentor"}
              roleType="mentor"
              name="Oriza Mumtaz"
              linkedin="https://www.linkedin.com/in/oriza-mumtaz-b9290b260"
            />
          </div>
        </Section>

      </div>

      <ChatBot riskContext={riskContext} />
    </>
  );
}
