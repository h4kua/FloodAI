import { useApp } from "../lib/appContext";
import ChatBot from "../components/ChatBot";

const id = (lang) => lang === "id";

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

export default function About({ riskContext = {} }) {
  const { lang } = useApp();
  const isId = id(lang);

  return (
    <>
      <div className="page-header fade-in">
        <h1 className="page-title">
          {isId ? "Tentang deFlood.ai" : "About deFlood.ai"}
        </h1>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <a
            href="https://www.linkedin.com/in/juanjaviersz/"
            target="_blank"
            rel="noopener noreferrer"
            className="ig-btn"
            title="LinkedIn"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }}>
              <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
            </svg>
            LinkedIn
          </a>
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
      </div>

      <div className="about-grid fade-in">

        {/* Hero banner */}
        <div className="about-hero">
          <div style={{ flex: 1, minWidth: 220 }}>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.03em", color: "var(--cyan)", marginBottom: "0.5rem" }}>
              deFlood<span style={{ color: "var(--s1)" }}>.ai</span>
            </p>
            <p style={{ fontSize: "0.88rem", color: "var(--text)", lineHeight: 1.7, maxWidth: 480 }}>
              {isId
                ? "Sistem kecerdasan banjir berbasis AI untuk Jakarta. Menggabungkan data sensor realtime, model machine learning, dan AI generatif untuk membantu operator BPBD dan warga Jakarta memantau serta merespons risiko banjir."
                : "An AI-powered flood intelligence system for Jakarta. Combines realtime sensor data, machine learning, and generative AI to help BPBD operators and Jakarta residents monitor and respond to flood risks."}
            </p>
          </div>
          <div className="stat-grid" style={{ minWidth: 200 }}>
            <Stat value="0.945" label="AUC-ROC" />
            <Stat value="16" label={isId ? "Fitur ML" : "ML Features"} />
            <Stat value="< 1s" label="Latency" />
            <Stat value="4" label={isId ? "Level Risiko" : "Risk Levels"} />
          </div>
        </div>

        {/* Data Sources */}
        <Section title={isId ? "Sumber Data" : "Data Sources"}>
          <Row tag="BMKG" accent title="Badan Meteorologi, Klimatologi & Geofisika"
            desc={isId
              ? "Data curah hujan realtime dan prakiraan cuaca dari lembaga meteorologi nasional Indonesia."
              : "Realtime rainfall data and weather forecasts from Indonesia's national meteorology agency."} />
          <Row tag="BNPB" title="Badan Nasional Penanggulangan Bencana"
            desc={isId
              ? "Alert resmi kebencanaan, data historis banjir, dan protokol evakuasi."
              : "Official disaster alerts, historical flood data, and evacuation protocols."} />
          <Row tag="TMA" title={isId ? "Sensor Tinggi Muka Air" : "Water Level Sensors"}
            desc={isId
              ? "Stasiun pemantauan sungai Jakarta. Catatan: TMA scraper saat ini offline — data estimasi digunakan sebagai fallback."
              : "Jakarta river monitoring stations. Note: TMA scraper is currently offline — estimated data is used as fallback."} />
          <Row tag="HST" title={isId ? "Data Historis Banjir" : "Historical Flood Data"}
            desc={isId
              ? "Dataset banjir Jakarta sejak 2010 untuk pelatihan model dengan 16 fitur meteorologi dan hidrologi."
              : "Jakarta flood dataset since 2010 for training the model with 16 meteorological and hydrological features."} />
        </Section>

        {/* ML Model */}
        <Section title={isId ? "Model Machine Learning" : "Machine Learning Model"}>
          <Row tag="XGB" accent title="XGBoost Classifier"
            desc={isId
              ? "Model gradient boosting yang mengklasifikasikan risiko ke 4 level: AMAN, WASPADA, SIAGA, BAHAYA berdasarkan kondisi cuaca dan hidrologi terkini."
              : "Gradient boosting model classifying risk into 4 levels: SAFE, WARNING, ALERT, DANGER based on current weather and hydrological conditions."} />
          <Row tag="16F" title={isId ? "16 Fitur Input" : "16 Input Features"}
            desc={isId
              ? "Curah hujan (jam ini, 6j, 12j, 24j), tinggi muka air sungai, temperatur, kelembapan, dan indikator musiman."
              : "Rainfall (current, 6h, 12h, 24h), river water level, temperature, humidity, and seasonal indicators."} />
          <Row tag="ECE" title={isId ? "Kalibrasi (ECE 0.20)" : "Calibration (ECE 0.20)"}
            desc={isId
              ? "Expected Calibration Error 0.20 (n=1.391) — dikalibrasi ulang menggunakan data kejadian BPBD 2024–2026 sebagai ground truth. Meningkat dari ECE 0.38 (n=7). Model cenderung overconfident; prediksi tetap perlu verifikasi lapangan."
              : "ECE 0.20 (n=1,391) — recalibrated using BPBD flood event data 2024–2026 as ground truth. Improved from ECE 0.38 (n=7). Model tends to be overconfident; predictions still require field verification."} />
          <Row tag="RT" title={isId ? "Update Realtime" : "Realtime Update"}
            desc={isId
              ? "Model berjalan pada setiap permintaan dengan data sensor terkini. Frontend polling setiap 15 menit."
              : "Model runs on each request with the latest sensor data. Frontend polls every 15 minutes."} />
        </Section>

        {/* AI Chat */}
        <Section title={isId ? "AI Chat" : "AI Chat"}>
          <Row tag="LLM" accent title="Groq — Llama 3.3 70B Versatile"
            desc={isId
              ? "Model bahasa besar dari Meta via Groq API untuk latensi rendah. Merespons pertanyaan seputar banjir, evakuasi, dan keselamatan."
              : "Meta's large language model via Groq API for low latency. Answers questions about flooding, evacuation, and safety."} />
          <Row tag="LANG" title={isId ? "Deteksi Bahasa Otomatis" : "Automatic Language Detection"}
            desc={isId
              ? "Chatbot mendeteksi bahasa dari pesan user dan merespons dalam bahasa yang sama — Indonesia atau Inggris."
              : "The chatbot detects the language from the user's message and responds in the same language — Indonesian or English."} />
          <Row tag="CTX" title={isId ? "Konteks Risiko" : "Risk Context"}
            desc={isId
              ? "Setiap percakapan menyertakan level risiko dan curah hujan terkini sehingga AI memberikan jawaban yang relevan dengan kondisi aktual."
              : "Each conversation includes the current risk level and rainfall so the AI gives answers relevant to actual conditions."} />
        </Section>

        {/* Tech Stack */}
        <Section title={isId ? "Teknologi" : "Tech Stack"}>
          <p style={{ fontSize: "0.8rem", color: "var(--muted)", marginBottom: "0.875rem", lineHeight: 1.6 }}>
            {isId
              ? "Dibangun dengan stack modern yang ringan dan dapat di-deploy dengan cepat di Railway dan Vercel."
              : "Built with a lightweight modern stack, deployed quickly on Railway and Vercel."}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap" }}>
            {["FastAPI", "Uvicorn", "Python 3.11", "XGBoost", "scikit-learn 1.5.2", "Groq SDK",
              "React 18", "Vite 5", "React-Leaflet", "OSRM Routing", "Nominatim / OSM",
              "Supabase / PostgreSQL", "Railway", "Vercel"].map(tag => (
              <span key={tag} className="tech-tag">{tag}</span>
            ))}
          </div>
        </Section>

        {/* Disclaimer */}
        <Section title={isId ? "Peringatan & Batasan" : "Disclaimer & Limitations"}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            {(isId ? [
              "Data zona per wilayah adalah estimasi dari skor risiko keseluruhan dengan bias historis — bukan sensor individual per kecamatan.",
              "TMA scraper saat ini offline. Tinggi muka air yang ditampilkan adalah estimasi berbasis probabilitas model.",
              "Aplikasi ini adalah alat bantu keputusan, bukan pengganti informasi resmi dari BPBD, BMKG, atau BNPB.",
              "Dalam kondisi darurat, selalu ikuti instruksi petugas BPBD dan Basarnas.",
            ] : [
              "Per-district zone data is estimated from the overall risk score with historical bias — not individual sub-district sensor data.",
              "The TMA scraper is currently offline. Water level data is probability-based estimation from the model.",
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

        {/* Credit */}
        <div className="credit-card">
          <div style={{ flex: 1 }}>
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.63rem", color: "var(--muted-2)", letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.5rem" }}>
              {isId ? "Dibuat oleh" : "Built by"}
            </p>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.5rem", fontWeight: 800, color: "var(--text)", letterSpacing: "-0.02em", marginBottom: "0.5rem" }}>
              JuanVier
            </p>
            <p style={{ fontSize: "0.82rem", color: "var(--muted)", lineHeight: 1.6, maxWidth: 420 }}>
              {isId
                ? "Proyek ini dibuat sebagai kontribusi terhadap sistem peringatan dini banjir Jakarta menggunakan kecerdasan buatan."
                : "This project was built as a contribution to Jakarta's early flood warning system using artificial intelligence."}
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <a
              href="https://www.linkedin.com/in/juanjaviersz/"
              target="_blank"
              rel="noopener noreferrer"
              className="ig-btn"
              title="LinkedIn"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
              </svg>
              LinkedIn
            </a>
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
