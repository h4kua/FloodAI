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
              label={id ? "Menghitung peluang banjir" : "Estimating the flood chance"}
              desc={id ? "Model harian, dilatih dengan catatan banjir BPBD 2013–2025 dan hujan satelit NASA, memperkirakan peluang banjir di tiap kecamatan hari ini dari hujan beberapa hari terakhir. Model keputusan lalu menggabungkannya dengan status pos sungai sekarang dan kemarin serta hujan hari ini menjadi status Jakarta." : "A daily model, trained on BPBD flood records from 2013–2025 and NASA satellite rain, estimates today's flood chance in every kecamatan from the rain of the last few days. A decision model then combines it with the river posts now and yesterday and today's rain into Jakarta's status."} />
            <Step num="3"
              label={id ? "Memberi tahu Anda" : "Telling you"}
              desc={id ? "Hasilnya ditampilkan sebagai status sederhana — Aman, Waspada, Siaga, atau Bahaya — lengkap dengan alasannya. Di peta, setiap area rawan banjir menampilkan peluang banjir hari ini untuk kecamatannya. Pos pantau di Siaga 1 selalu membuat status Bahaya, dan peringatan BMKG yang parah membuat status minimal Siaga." : "The result is shown as a simple status — Safe, Watch, Alert, or Danger — with the reason. On the map, every flood-prone area shows today's flood chance for its kecamatan. A monitoring post at Alert 1 always makes the status Danger, and a severe BMKG warning makes it at least Alert."} />
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
              "Data bisa terlambat jika pos pantau belum mengirim pembaruan. Hujan satelit tiba sekitar 5 jam setelah turun.",
              "Laporan warga belum diverifikasi, tampil 6 jam, dan tidak mengubah status resmi.",
            ] : [
              "This app is an aid, not a replacement for official information from BPBD, BMKG, or BNPB.",
              "In an emergency, always follow instructions from BPBD and Basarnas officers.",
              "Data can be late if monitoring posts haven't sent an update. Satellite rain arrives about 5 hours after it falls.",
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
                ? "Diuji per tahun: untuk tahun 2019, 2020, 2021 dan 2025, model hanya dilatih dengan tahun-tahun sebelumnya, lalu dicek pada tahun itu. Patokannya hari banjir yang dicatat BPBD. Angka di bawah untuk model keputusan Jakarta, dibandingkan dengan aturan lama (status pos sungai + model harian)."
                : "Tested year by year: for 2019, 2020, 2021 and 2025 the model was trained only on earlier years and then checked on that year, against the flood days BPBD recorded. The figures below are for the Jakarta decision model, compared with the old rules (river-post status + daily model)."}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <MetricBar label="AUC-ROC" hint={id ? "(aturan lama 0,694)" : "(old rules 0.694)"}
                value={0.786} color="var(--safe)" format={v => v.toFixed(3)} />
              <MetricBar label={id ? "Presisi Siaga" : "Alert precision"} hint={id ? "(aturan lama 73%)" : "(old rules 73%)"}
                value={0.758} color="var(--s2)" format={v => (v * 100).toFixed(0) + "%"} />
              <MetricBar label={id ? "Banjir tertangkap di Siaga" : "Floods caught at Alert"} hint={id ? "(aturan lama 13%)" : "(old rules 13%)"}
                value={0.22} color="var(--s2)" format={v => (v * 100).toFixed(0) + "%"} />
              <MetricBar label={id ? "Presisi Bahaya" : "Danger precision"} hint={id ? "(aturan lama 76%)" : "(old rules 76%)"}
                value={0.842} color="var(--s1)" format={v => (v * 100).toFixed(0) + "%"} />
              <MetricBar label={id ? "Model harian per kecamatan, AUC-ROC" : "Daily kecamatan model, AUC-ROC"} hint="(2023–2025)"
                value={0.836} color="var(--cyan)" format={v => v.toFixed(3)} />
            </div>
            <ul style={{ margin: "1rem 0 0", paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.4rem", fontSize: "0.85rem", color: "var(--muted)", lineHeight: 1.55 }}>
              <li>
                {id
                  ? "Presisi Siaga 76% berarti sekitar 3 dari 4 saat berstatus Siaga memang ada banjir yang dicatat BPBD di Jakarta hari itu. Banjir kecil sering tidak terdeteksi: status Siaga hanya muncul pada 22% saat banjir."
                  : "76% Alert precision means about 3 in 4 Alert moments had a BPBD-recorded flood in Jakarta that day. Small floods are often missed: Alert shows on only 22% of flood moments."}
              </li>
              <li>
                {id
                  ? "Persentase di area rawan banjir pada peta adalah peluang dari model harian untuk seluruh kecamatan tempat area itu berada, bukan untuk titik itu saja. Model ini hanya menaikkan status sampai Waspada; titik berwarna kuning berada di kecamatan dengan peluang setara Waspada."
                  : "The percentage on a flood-prone area of the map is the daily model's chance for the whole kecamatan it lies in, not for that spot alone. This model raises the status to Watch at most; amber points lie in a kecamatan whose chance is at the Watch level."}
              </li>
              <li>
                {id
                  ? "Model belum diuji langsung di lapangan. Sejak November 2026 setiap keputusan situs dibandingkan dengan laporan banjir setiap bulan. Peluang 10–40% cenderung lebih rendah dari kenyataan, dan catatan BPBD setelah 2022 belum lengkap."
                  : "The model has not been tested in the field yet. Since November 2026 every decision of the site is compared with flood reports each month. Chances of 10–40% tend to run lower than reality, and BPBD records after 2022 are incomplete."}
              </li>
            </ul>
          </Section>

          <Section title={id ? "Sumber data" : "Data sources"}>
            <Row tag="DSDADKI" title={id ? "Pos pantau ketinggian air" : "Water-level monitoring posts"}
              desc={id ? "38 titik dari Dinas Sumber Daya Air DKI (28 pos sungai, pintu air, bendung, dan waduk, serta 10 rumah pompa), diperbarui tiap 15 menit. Arsip 2,2 juta bacaan 2016–2021 dipakai untuk melatih model keputusan." : "38 points from the DKI Water Resources Agency (28 river posts, water gates, weirs and reservoirs, plus 10 pump houses), updated every 15 minutes. An archive of 2.2 million readings from 2016–2021 trained the decision model."} />
            <Row tag="NASA" title={id ? "Hujan satelit GPM IMERG" : "GPM IMERG satellite rain"}
              desc={id ? "Curah hujan setengah-jaman sejak 2013 untuk Jakarta, Bogor dan Depok, tiba sekitar 5 jam setelah hujan." : "Half-hourly rain since 2013 for Jakarta, Bogor and Depok, arriving about 5 hours after it falls."} />
            <Row tag="BMKG" title={id ? "Peringatan & prakiraan cuaca" : "Weather warnings & forecasts"}
              desc={id ? "Peringatan cuaca ekstrem dan prakiraan per wilayah." : "Extreme-weather warnings and per-area forecasts."} />
            <Row tag="OWM" title="OpenWeatherMap"
              desc={id ? "Suhu, kelembapan, dan curah hujan realtime." : "Realtime temperature, humidity, and rainfall."} />
            <Row tag="BPBD" title={id ? "Data historis banjir" : "Historical flood data"}
              desc={id ? "Tanggal banjir per kelurahan 2013–2025 untuk melatih dan menguji model, dan titik rawan banjir untuk peta Beranda dan peta evakuasi." : "Flood dates per kelurahan from 2013–2025 to train and test the models, and flood-prone points for the home and evacuation maps."} />
            <Row tag="OSM" title={id ? "Peta dan rute jalan" : "Maps and road routes"}
              desc={id ? "OpenStreetMap dan OSRM untuk rute evakuasi; navigasi diteruskan ke Google Maps." : "OpenStreetMap and OSRM for evacuation routes; navigation is handed to Google Maps."} />
            <Row tag={id ? "Warga" : "Public"} title={id ? "Laporan warga" : "Community reports"}
              desc={id ? "Kabar dan foto dari warga, disimpan di Supabase. Foto diperkecil dan metadatanya (termasuk lokasi GPS kamera) dihapus." : "Updates and photos from residents, stored in Supabase. Photos are resized and stripped of metadata, including the camera's GPS location."} />
          </Section>

          <Section title={id ? "Model & AI" : "Model & AI"}>
            <Row tag={id ? "Harian" : "Daily"} title={id ? "Model harian per kecamatan (XGBoost)" : "Daily kecamatan model (XGBoost)"}
              desc={id ? "Hujan satelit beberapa hari terakhir, hujan di hulu, musim, riwayat banjir dan ketinggian tanah → peluang banjir tiap kecamatan hari ini. Diperbarui tiap 30 menit." : "Satellite rain of the last few days, upstream rain, season, flood history and elevation → today's flood chance in each kecamatan. Updated every 30 minutes."} />
            <Row tag={id ? "Keputusan" : "Decision"} title={id ? "Model keputusan (XGBoost monoton)" : "Decision model (monotone XGBoost)"}
              desc={id ? "Menggabungkan peluang model harian, status pos sungai sekarang dan kemarin, dan hujan hari ini menjadi peluang banjir Jakarta. Ambang Waspada, Siaga dan Bahaya juga dipelajari dari data. Status pos yang lebih tinggi atau hujan yang lebih deras tidak pernah menurunkan risiko." : "Combines the daily model's chance, the river posts now and yesterday and today's rain into a flood chance for Jakarta. The Watch, Alert and Danger thresholds are learned from data too. A higher post status or heavier rain can never lower the risk."} />
            <Row tag={id ? "Aturan" : "Rules"} title={id ? "Aturan pengaman" : "Safety rules"}
              desc={id ? "Data rusak → Tidak diketahui; pos di Siaga 1 atau air naik cepat → Bahaya; peringatan BMKG parah → minimal Siaga. Jika data model belum lengkap, 10 lapisan aturan lama yang memutuskan." : "Broken data → Unknown; a post at Alert 1 or fast-rising water → Danger; a severe BMKG warning → at least Alert. When the model's data is incomplete, the old 10-layer rules decide."} />
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
