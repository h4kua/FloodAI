import { useApp } from "../lib/appContext";
import ChatBot from "../components/ChatBot";

const ID = "id";

function Section({ title, children }) {
  return (
    <div className="panel panel-body">
      <p className="about-section-title">{title}</p>
      {children}
    </div>
  );
}

function Row({ icon, title, desc }) {
  return (
    <div className="about-row">
      <span className="about-icon">{icon}</span>
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

export default function About({ riskContext = {} }) {
  const { lang } = useApp();
  const id = lang === ID;

  return (
    <>
      <div className="page-header fade-in">
        <h1 className="page-title">
          {id ? "Tentang deFlood.ai" : "About deFlood.ai"}
        </h1>
        <a
          href="https://www.instagram.com/juanvier_/"
          target="_blank"
          rel="noopener noreferrer"
          className="ig-btn"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
            <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
          </svg>
          @juanvier_
        </a>
      </div>

      <div className="about-grid fade-in">

        {/* Hero */}
        <div className="about-hero">
          <div style={{ flex: 1, minWidth: 220 }}>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.03em", color: "var(--cyan)", marginBottom: "0.5rem" }}>
              deFlood<span style={{ color: "var(--s1)" }}>.ai</span>
            </p>
            <p style={{ fontSize: "0.9rem", color: "var(--text)", lineHeight: 1.65, maxWidth: 480 }}>
              {id
                ? "Sistem kecerdasan banjir berbasis AI untuk Jakarta. Menggabungkan data sensor realtime, model machine learning, dan AI generatif untuk membantu operator BPBD dan warga Jakarta dalam memantau dan merespons risiko banjir."
                : "An AI-powered flood intelligence system for Jakarta. Combines realtime sensor data, machine learning models, and generative AI to help BPBD operators and Jakarta residents monitor and respond to flood risks."}
            </p>
          </div>
          <div className="stat-grid" style={{ minWidth: 200 }}>
            <Stat value="0.945" label="AUC-ROC" />
            <Stat value="16" label={id ? "Fitur ML" : "ML Features"} />
            <Stat value="<1s" label="Latency" />
            <Stat value="4" label={id ? "Level Risiko" : "Risk Levels"} />
          </div>
        </div>

        {/* Data Sources */}
        <Section title={id ? "Sumber Data" : "Data Sources"}>
          <Row icon="🌧️"
            title="BMKG"
            desc={id ? "Data curah hujan dan prakiraan cuaca dari Badan Meteorologi, Klimatologi, dan Geofisika Indonesia." : "Rainfall data and weather forecasts from Indonesia's Meteorology, Climatology, and Geophysics Agency."}
          />
          <Row icon="🏛️"
            title="BNPB / BPBD"
            desc={id ? "Alert resmi kebencanaan, data historis banjir, dan protokol evakuasi dari badan nasional penanggulangan bencana." : "Official disaster alerts, historical flood data, and evacuation protocols from the national disaster management agency."}
          />
          <Row icon="📡"
            title={id ? "Sensor TMA" : "TMA Sensors"}
            desc={id ? "Tinggi Muka Air (TMA) dari stasiun pemantauan sungai Jakarta. Catatan: scraper TMA sedang offline, data estimasi digunakan sebagai fallback." : "River water level (TMA) from Jakarta river monitoring stations. Note: TMA scraper is currently offline; estimated data is used as fallback."}
          />
          <Row icon="☁️"
            title={id ? "Data Historis" : "Historical Data"}
            desc={id ? "Dataset banjir Jakarta historis sejak 2010 untuk pelatihan model XGBoost dengan 16 fitur meteorologi dan hidrologi." : "Historical Jakarta flood dataset since 2010 for training the XGBoost model with 16 meteorological and hydrological features."}
          />
        </Section>

        {/* ML Model */}
        <Section title={id ? "Model Machine Learning" : "Machine Learning Model"}>
          <Row icon="🤖"
            title="XGBoost Classifier"
            desc={id ? "Model gradient boosting yang dilatih dengan data historis banjir Jakarta. Mengklasifikasikan risiko ke 4 level: AMAN, WASPADA, SIAGA, BAHAYA." : "Gradient boosting model trained on historical Jakarta flood data. Classifies risk into 4 levels: SAFE, WARNING, ALERT, DANGER."}
          />
          <Row icon="📊"
            title={id ? "16 Fitur Input" : "16 Input Features"}
            desc={id ? "Curah hujan (jam ini, 6j, 12j, 24j), tinggi muka air sungai, temperatur, kelembapan, dan indikator musiman." : "Rainfall (current, 6h, 12h, 24h), river water level, temperature, humidity, and seasonal indicators."}
          />
          <Row icon="⚠️"
            title={id ? "Keterbatasan Kalibrasi" : "Calibration Limitation"}
            desc={id ? "ECE (Expected Calibration Error) sebesar 0.38 menunjukkan model confidence belum sepenuhnya dapat dipercaya. Prediksi perlu diverifikasi dengan data lapangan." : "ECE (Expected Calibration Error) of 0.38 indicates model confidence is not fully reliable. Predictions should be verified with field data."}
          />
          <Row icon="🔄"
            title={id ? "Update Realtime" : "Realtime Update"}
            desc={id ? "Model berjalan setiap permintaan dengan data sensor terkini. Frontend polling setiap 15 menit untuk data terbaru." : "Model runs on each request with the latest sensor data. Frontend polls every 15 minutes for updated data."}
          />
        </Section>

        {/* AI Chat */}
        <Section title={id ? "AI Chat (Groq)" : "AI Chat (Groq)"}>
          <Row icon="💬"
            title="Llama 3.3 70B Versatile"
            desc={id ? "Model bahasa besar dari Meta yang dijalankan via Groq API untuk latensi rendah. Merespons pertanyaan seputar banjir, evakuasi, dan keselamatan." : "Meta's large language model running via Groq API for low latency. Responds to questions about flooding, evacuation, and safety."}
          />
          <Row icon="🌐"
            title={id ? "Bilingual Auto-detect" : "Bilingual Auto-detect"}
            desc={id ? "Chatbot mendeteksi bahasa dari pesan user dan merespons dalam bahasa yang sama (Indonesia atau Inggris)." : "The chatbot detects the language from the user's message and responds in the same language (Indonesian or English)."}
          />
          <Row icon="📍"
            title={id ? "Konteks Risiko" : "Risk Context"}
            desc={id ? "Setiap chat menyertakan konteks risiko saat ini (level dan curah hujan) sehingga AI memberikan jawaban yang relevan dengan kondisi aktual." : "Each chat includes current risk context (level and rainfall) so the AI gives answers relevant to actual conditions."}
          />
          <Row icon="🚫"
            title={id ? "Batas Data" : "Data Boundaries"}
            desc={id ? "AI tidak memiliki akses ke ramalan cuaca masa depan. Untuk prakiraan, diarahkan ke BMKG (bmkg.go.id)." : "The AI has no access to future weather forecasts. For forecasts, users are directed to BMKG (bmkg.go.id)."}
          />
        </Section>

        {/* Tech Stack */}
        <Section title={id ? "Teknologi" : "Tech Stack"}>
          <p style={{ fontSize: "0.8rem", color: "var(--muted)", marginBottom: "0.875rem", lineHeight: 1.6 }}>
            {id ? "deFlood.ai dibangun dengan stack modern yang ringan dan dapat di-deploy dengan cepat:" : "deFlood.ai is built with a modern, lightweight stack that deploys quickly:"}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0" }}>
            {["FastAPI", "Uvicorn", "Python 3.11", "XGBoost", "scikit-learn", "Groq SDK",
              "React 18", "Vite 5", "React-Leaflet", "OSRM Routing", "Nominatim / OSM",
              "Supabase / PostgreSQL", "Railway (Backend)", "Vercel (Frontend)"].map(tag => (
              <span key={tag} className="tech-tag">{tag}</span>
            ))}
          </div>
        </Section>

        {/* Disclaimer */}
        <Section title={id ? "Peringatan & Batasan" : "Disclaimer & Limitations"}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {(id ? [
              "Data zona per wilayah (Penjaringan, Cengkareng, dll.) adalah estimasi yang diturunkan dari skor risiko keseluruhan dengan bias historis — bukan data sensor individual per kecamatan.",
              "TMA scraper saat ini offline. Tinggi muka air yang ditampilkan adalah estimasi berbasis probabilitas.",
              "Aplikasi ini ditujukan sebagai alat bantu keputusan, bukan pengganti informasi resmi dari BPBD, BMKG, atau BNPB.",
              "Dalam kondisi darurat, selalu ikuti instruksi petugas BPBD dan Basarnas.",
            ] : [
              "Per-district zone data (Penjaringan, Cengkareng, etc.) is estimated from the overall risk score with historical bias — not individual sensor data per sub-district.",
              "The TMA scraper is currently offline. Water level data shown is probability-based estimation.",
              "This app is intended as a decision support tool, not a replacement for official information from BPBD, BMKG, or BNPB.",
              "In emergencies, always follow instructions from BPBD and Basarnas officers.",
            ]).map((item, i) => (
              <div key={i} style={{ display: "flex", gap: "0.625rem", fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.55 }}>
                <span style={{ color: "var(--wsp)", flexShrink: 0, fontWeight: 700 }}>⚠</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* Credit card */}
        <div className="credit-card">
          <div style={{ flex: 1 }}>
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted-2)", letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.5rem" }}>
              {id ? "Dibuat oleh" : "Built by"}
            </p>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.5rem", fontWeight: 800, color: "var(--text)", letterSpacing: "-0.02em", marginBottom: "0.5rem" }}>
              JuanVier
            </p>
            <p style={{ fontSize: "0.82rem", color: "var(--muted)", lineHeight: 1.55, maxWidth: 420 }}>
              {id
                ? "Proyek ini dibuat sebagai bentuk kontribusi terhadap sistem peringatan dini banjir Jakarta menggunakan kecerdasan buatan."
                : "This project was created as a contribution towards Jakarta's early flood warning system using artificial intelligence."}
            </p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", alignItems: "flex-start" }}>
            <a
              href="https://www.instagram.com/juanvier_/"
              target="_blank"
              rel="noopener noreferrer"
              className="ig-btn"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
              </svg>
              @juanvier_
            </a>
          </div>
        </div>

      </div>

      <ChatBot riskContext={riskContext} />
    </>
  );
}
