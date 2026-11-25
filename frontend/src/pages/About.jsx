/* ── Tentang — what the site is for, how to read it, how far to trust it ─────
   Laid out like a short document: the section title on the left, the text on the right. The first screen says
   what the site is for and sends the reader to the page they need; the model figures sit under "Detail teknis".
*/
import { useApp } from "../lib/appContext";
import ChatBot from "../components/ChatBot";
import CollapsibleSection from "../components/shell/CollapsibleSection";
import { RiskBadge } from "../components/dashboard/primitives";

const LinkedInSVG = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ flexShrink: 0 }} aria-hidden="true">
    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
  </svg>
);

/** A titled block: title (and a line under it) on the left, content on the right. */
function Doc({ title, note, children, id }) {
  return (
    <section className="doc-sec" aria-labelledby={id}>
      <div className="doc-sec-head">
        <h2 id={id}>{title}</h2>
        {note && <p>{note}</p>}
      </div>
      <div className="doc-sec-body">{children}</div>
    </section>
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
        <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", minWidth: 0, flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text)" }}>{label}</span>
          {hint && <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>{hint}</span>}
        </div>
        <span style={{ fontSize: "0.85rem", fontWeight: 700, color, flexShrink: 0 }}>{display}</span>
      </div>
      <div style={{ height: "5px", background: "var(--line)", borderRadius: "2px", overflow: "hidden" }}>
        <div style={{ width: `${barPct}%`, height: "100%", background: color, borderRadius: "2px" }} />
      </div>
    </div>
  );
}

export default function About({ riskContext = {}, onNavigate }) {
  const { lang } = useApp();
  const id = lang === "id";
  const go = (page) => () => onNavigate?.(page);

  const start = [
    { page: "home", t: id ? "Cek status Jakarta" : "Check Jakarta's status", d: id ? "Aman sampai Bahaya, dan langkahnya." : "Safe to Danger, and what to do." },
    { page: "alert", t: id ? "Cari rute aman" : "Find a safe route", d: id ? "Jalan yang menghindari area banjir." : "Roads that avoid flooded areas." },
    { page: "history", t: id ? "Lihat riwayat" : "See the history", d: id ? "Status dan hujan hari-hari lalu." : "Status and rain on past days." },
    { page: "reports", t: id ? "Kirim laporan" : "Send a report", d: id ? "Kabarkan air di sekitar Anda." : "Tell others about the water near you." },
  ];

  const levels = [
    { key: "AMAN", d: id ? "Tidak ada tanda banjir. Beraktivitas seperti biasa." : "No sign of flooding. Go about your day." },
    { key: "WASPADA", d: id ? "Mungkin ada genangan kalau hujan. Tidak perlu panik; pantau saja." : "Some waterlogging is possible if it rains. No need to worry; just keep an eye on it." },
    { key: "SIAGA", d: id ? "Air sungai tinggi atau genangan cukup mungkin. Mulai bersiap." : "Rivers are high or waterlogging is likely. Start getting ready." },
    { key: "BAHAYA", d: id ? "Risiko tinggi. Ikuti arahan BPBD. Darurat: 112." : "High risk. Follow BPBD. Emergency: 112." },
  ];

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{id ? "Tentang deFlood.ai" : "About deFlood.ai"}</h1>
          <p className="page-sub">
            {id
              ? "Memperkirakan banjir di Jakarta dan menunjukkan jalan yang menghindari genangan."
              : "Estimating flooding in Jakarta and showing roads that avoid waterlogging."}
          </p>
        </div>
      </div>

      <div className="doc fade-in">
        <Doc id="about-start" title={id ? "Mulai dari sini" : "Start here"}>
          <div className="start-links">
            {start.map((s) => (
              <button key={s.page} type="button" className="start-link" onClick={go(s.page)}>
                <b>{s.t}</b>
                <span>{s.d}</span>
              </button>
            ))}
          </div>
        </Doc>

        <Doc id="about-status" title={id ? "Arti status" : "What the status means"}>
          <ul className="status-key">
            {levels.map((l) => (
              <li key={l.key}>
                <RiskBadge level={l.key} />
                <p>{l.d}</p>
              </li>
            ))}
          </ul>
        </Doc>

        <Doc id="about-how" title={id ? "Cara kerjanya" : "How it works"}>
          <ol className="how-steps">
            <li>
              {id ? "Tiap 15 menit kami membaca tinggi air di pos sungai, cuaca, dan peringatan BMKG."
                  : "Every 15 minutes we read river-post water levels, weather and BMKG warnings."}
            </li>
            <li>
              {id ? "Model menghitung peluang genangan tiap kecamatan dari hujan satelit beberapa hari terakhir, dilatih dengan catatan BPBD 2013–2025."
                  : "A model estimates each kecamatan's waterlogging chance from recent satellite rain, trained on BPBD records from 2013–2025."}
            </li>
            <li>
              {id ? "Hasilnya digabung dengan status pos sungai menjadi satu status untuk Jakarta. Pos di Siaga 1 selalu berarti Bahaya."
                  : "That is combined with the river posts into one status for Jakarta. A post at Siaga 1 always means Danger."}
            </li>
          </ol>
          <p className="doc-aside">
            {id ? "Lingkaran merah di peta bukan kepastian banjir: area seperti itu tercatat banjir sekitar 1 dari 4 hari, dibanding 1 dari 60 hari biasa."
                : "A red circle on the map is not a certain flood: such areas flooded about 1 day in 4, against 1 in 60 on normal days."}
          </p>
        </Doc>

        <Doc id="about-trust" title={id ? "Seberapa bisa dipercaya" : "How far to trust it"}>
          <ul className="doc-list">
            {(id ? [
              "Pada hari-hari uji, model memberi peluang lebih tinggi pada hari banjir sekitar 8 dari 10 kali.",
              "Uji Januari–Mei 2026: 6 dari 10 hari banjir tertangkap, sama baiknya dengan aturan sederhana “hujan 7 hari terakhir”. Dua banjir terbesar (29 Jan, 8 Mar) terlewat.",
              "Peluang biasanya kecil (10–40%). Itu peluang genangan di satu kecamatan, bukan banjir besar.",
              "Di musim hujan, Waspada muncul hampir tiap hari. Itu peringatan ringan.",
            ] : [
              "On test days, the model gave flood days a higher chance about 8 times in 10.",
              "Jan–May 2026 test: 6 in 10 flood days caught, as good as the simple rule “rain over the last 7 days”. The two largest floods (29 Jan, 8 Mar) were missed.",
              "Chances are usually small (10–40%). That is the chance of waterlogging in one kecamatan, not a big flood.",
              "In the rainy season, Watch shows almost daily. It is a light notice.",
            ]).map((text) => <li key={text}>{text}</li>)}
          </ul>
        </Doc>

        <Doc id="about-know" title={id ? "Penting diketahui" : "Good to know"}>
          <ul className="doc-list">
            {(id ? [
              "Alat bantu, bukan pengganti info resmi BPBD, BMKG, atau BNPB.",
              "Rute Aman adalah perkiraan dari titik rawan BPBD, bukan kondisi jalan langsung. Cek sendiri sebelum berangkat.",
              "Laporan warga belum diverifikasi dan tidak mengubah status resmi.",
            ] : [
              "An aid, not a replacement for official BPBD, BMKG or BNPB information.",
              "Safe Route is an estimate from BPBD flood-prone points, not live road conditions. Check it yourself before you go.",
              "Community reports are unverified and never change the official status.",
            ]).map((text) => <li key={text}>{text}</li>)}
          </ul>
        </Doc>

        <Doc id="about-team" title={id ? "Tim pengembang" : "The team"}>
          <div className="team-grid">
            <TeamCard role={id ? "Ketua Project" : "Project Lead"} roleType="lead" name="Juan Javier SZ" linkedin="https://www.linkedin.com/in/juanjaviersz/" />
            <TeamCard role={id ? "Anggota Tim" : "Team Member"} roleType="member" name="Jessen Wijaya Agussalim" linkedin="https://www.linkedin.com/in/jessen-wijaya-agussalim" />
            <TeamCard role={id ? "Anggota Tim" : "Team Member"} roleType="member" name="Chahniyan Regina Kasih" linkedin="https://www.linkedin.com/in/chahniyan-regina-kasih-227808280" />
            <TeamCard role={id ? "Anggota Tim" : "Team Member"} roleType="member" name="Christopher Patrick" linkedin="https://www.linkedin.com/in/christopherpatrick-gunawan" />
          </div>
        </Doc>
      </div>

      {/* Technical depth — for reviewers and developers, closed by default */}
      <CollapsibleSection
        icon="⚙"
        iconBg="var(--cyan-soft)"
        iconColor="var(--cyan)"
        title={id ? "Detail teknis" : "Technical details"}
        subtitle={id ? "Performa model, data, teknologi" : "Model performance, data, stack"}
      >
        <div className="doc">
          <Doc id="tech-perf" title={id ? "Performa model" : "Model performance"}
               note={id ? "Ukuran: AUC-ROC (0,5 = menebak, 1 = sempurna)." : "Measure: AUC-ROC (0.5 = guessing, 1 = perfect)."}>
            <p className="doc-aside" style={{ marginTop: 0 }}>
              {id
                ? "Uji per tahun: untuk 2019, 2020, 2021 dan 2025, model hanya dilatih dengan tahun-tahun sebelumnya, lalu dicek pada tahun itu terhadap hari banjir yang dicatat BPBD. Angka untuk model keputusan Jakarta, dibandingkan dengan aturan lama (status pos sungai + model harian)."
                : "Year-by-year test: for 2019, 2020, 2021 and 2025 the model was trained only on earlier years and then checked on that year against the flood days BPBD recorded. Figures are for the Jakarta decision model, compared with the old rules (river-post status + daily model)."}
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <MetricBar label="AUC-ROC" hint={id ? "(aturan lama 0,694)" : "(old rules 0.694)"} value={0.786} color="var(--safe)" format={(v) => v.toFixed(3)} />
              <MetricBar label={id ? "Presisi Siaga" : "Alert precision"} hint={id ? "(aturan lama 73%)" : "(old rules 73%)"} value={0.758} color="var(--s2)" format={(v) => `${(v * 100).toFixed(0)}%`} />
              <MetricBar label={id ? "Banjir tertangkap di Siaga" : "Floods caught at Alert"} hint={id ? "(aturan lama 13%)" : "(old rules 13%)"} value={0.22} color="var(--s2)" format={(v) => `${(v * 100).toFixed(0)}%`} />
              <MetricBar label={id ? "Presisi Bahaya" : "Danger precision"} hint={id ? "(aturan lama 76%)" : "(old rules 76%)"} value={0.842} color="var(--s1)" format={(v) => `${(v * 100).toFixed(0)}%`} />
              <MetricBar label={id ? "Model harian per kecamatan" : "Daily kecamatan model"} hint="(2023–2025)" value={0.836} color="var(--cyan)" format={(v) => v.toFixed(3)} />
              <MetricBar label={id ? "Model harian, uji 2026 (berita)" : "Daily model, 2026 test (news)"} hint={id ? "(hujan 7 hari saja 0,821)" : "(7-day rain alone 0.821)"} value={0.844} color="var(--cyan)" format={(v) => v.toFixed(3)} />
            </div>
            <ul className="doc-list" style={{ marginTop: "1rem" }}>
              <li>
                {id ? "Presisi Siaga 76% berarti sekitar 3 dari 4 saat berstatus Siaga memang ada genangan yang dicatat BPBD di Jakarta hari itu. Banjir kecil sering terlewat: Siaga hanya muncul pada 22% saat banjir."
                    : "76% Alert precision means about 3 in 4 Alert moments had a BPBD-recorded flood in Jakarta that day. Small floods are often missed: Alert shows on only 22% of flood moments."}
              </li>
              <li>
                {id ? "Uji 2026 hanya memakai hari banjir dari berita (tanpa hari yang pasti tidak banjir) dan tanpa data tinggi air pos sebelum April, jadi hanya urutan risiko yang bisa diukur, bukan ketepatan alarm."
                    : "The 2026 test uses news flood days only (no days known to be dry) and has no water-level data before April, so only the ranking can be measured, not alarm precision."}
              </li>
              <li>
                {id ? "Sejak November 2026 setiap keputusan situs dicatat dan dibandingkan dengan laporan banjir tiap bulan (halaman Riwayat)."
                    : "Since November 2026 every decision of the site is logged and compared with flood reports each month (the History page)."}
              </li>
            </ul>
          </Doc>

          <Doc id="tech-data" title={id ? "Sumber data" : "Data sources"}>
            <Row tag="DSDADKI" title={id ? "Pos pantau ketinggian air" : "Water-level monitoring posts"}
              desc={id ? "38 titik dari Dinas Sumber Daya Air DKI, diperbarui tiap 15 menit. Sekitar 20 pos sungai dan pintu air dinilai; rumah pompa tidak punya batas banjir. Arsip 2,2 juta bacaan 2016–2021 melatih model keputusan."
                       : "38 points from the DKI Water Resources Agency, updated every 15 minutes. About 20 river and gate posts are scored; pump houses have no flood limits. An archive of 2.2 million readings from 2016–2021 trained the decision model."} />
            <Row tag="NASA" title={id ? "Hujan satelit GPM IMERG" : "GPM IMERG satellite rain"}
              desc={id ? "Curah hujan setengah-jaman sejak 2013 untuk Jakarta, Bogor dan Depok, tiba sekitar 5 jam setelah hujan." : "Half-hourly rain since 2013 for Jakarta, Bogor and Depok, arriving about 5 hours after it falls."} />
            <Row tag="BMKG" title={id ? "Peringatan & prakiraan cuaca" : "Weather warnings & forecasts"}
              desc={id ? "Peringatan cuaca ekstrem dan prakiraan per wilayah." : "Extreme-weather warnings and per-area forecasts."} />
            <Row tag="OWM" title="OpenWeatherMap"
              desc={id ? "Suhu, kelembapan, dan curah hujan saat ini." : "Current temperature, humidity and rainfall."} />
            <Row tag="BPBD" title={id ? "Data historis banjir" : "Historical flood data"}
              desc={id ? "Tanggal genangan per kelurahan 2013–2025 untuk melatih dan menguji model, dan titik rawan banjir untuk peta dan Cek daerahku. Berita detik.com yang mengutip BPBD dipakai untuk menguji 2026."
                       : "Waterlogging dates per kelurahan 2013–2025 to train and test the models, and flood-prone points for the maps and Check my area. detik.com news quoting BPBD tests 2026."} />
            <Row tag="OSM" title={id ? "Peta, rute, dan tempat aman" : "Maps, routes and safe places"}
              desc={id ? "OpenStreetMap dan OSRM untuk rute; calon tempat aman dari survei OSM/InAWARE, bukan daftar resmi. Navigasi diteruskan ke Google Maps."
                       : "OpenStreetMap and OSRM for routes; candidate safe places from the OSM/InAWARE survey, not an official list. Navigation is handed to Google Maps."} />
            <Row tag={id ? "Warga" : "Public"} title={id ? "Laporan warga" : "Community reports"}
              desc={id ? "Kabar dan foto dari warga, disimpan di Supabase. Foto diperkecil dan metadatanya (termasuk lokasi GPS kamera) dihapus."
                       : "Updates and photos from residents, stored in Supabase. Photos are resized and stripped of metadata, including the camera's GPS location."} />
          </Doc>

          <Doc id="tech-model" title={id ? "Model & AI" : "Model & AI"}>
            <Row tag={id ? "Harian" : "Daily"} title={id ? "Model harian per kecamatan (XGBoost)" : "Daily kecamatan model (XGBoost)"}
              desc={id ? "Hujan satelit beberapa hari terakhir, hujan di hulu, musim, riwayat banjir dan ketinggian tanah → peluang genangan tiap kecamatan hari ini. Diperbarui tiap 30 menit."
                       : "Satellite rain of the last few days, upstream rain, season, flood history and elevation → today's chance of waterlogging in each kecamatan. Updated every 30 minutes."} />
            <Row tag={id ? "Keputusan" : "Decision"} title={id ? "Model keputusan (XGBoost monoton)" : "Decision model (monotone XGBoost)"}
              desc={id ? "Menggabungkan peluang model harian, status pos sungai sekarang dan kemarin, dan hujan hari ini menjadi peluang untuk Jakarta. Ambang Waspada (20%), Siaga (65%) dan Bahaya (80%) dipelajari dari data. Status pos yang lebih tinggi atau hujan yang lebih deras tidak pernah menurunkan risiko."
                       : "Combines the daily model's chance, the river posts now and yesterday and today's rain into a chance for Jakarta. The Watch (20%), Alert (65%) and Danger (80%) thresholds are learned from data. A higher post status or heavier rain can never lower the risk."} />
            <Row tag={id ? "Aturan" : "Rules"} title={id ? "Aturan pengaman" : "Safety rules"}
              desc={id ? "Data rusak → Tidak diketahui; pos di Siaga 1 → Bahaya; pos yang sudah di Siaga 3 atau lebih dan naik lebih dari 10% batas Siaga 1 di antara dua bacaan → Bahaya; peringatan BMKG parah → minimal Siaga. Kenaikan di pos yang masih rendah tidak dihitung (kesalahan 24–25 Nov 2026 diperbaiki). Jika data model belum lengkap, 10 lapisan aturan lama yang memutuskan."
                       : "Broken data → Unknown; a post at Siaga 1 → Danger; a post already at Siaga 3 or higher that rises by more than 10% of its Siaga 1 limit between two readings → Danger; a severe BMKG warning → at least Alert. A rise at a post that is still low does not count (the 24–25 Nov 2026 error was fixed). When the model's data is incomplete, the old 10-layer rules decide."} />
            <Row tag="LLM" title="Groq — Qwen3 (qwen3.8-27b)"
              desc={id ? "Menulis penjelasan dan menjawab chat. Tidak ikut menentukan status; jika gagal, dipakai template tetap." : "Writes explanations and answers chat. It does not decide the status; a fixed template is used if it fails."} />
          </Doc>

          <Doc id="tech-stack" title={id ? "Teknologi" : "Tech stack"}>
            <div style={{ display: "flex", flexWrap: "wrap" }}>
              {["Python 3.12", "FastAPI", "XGBoost 3.2.0", "scikit-learn 1.8.0", "Groq SDK", "React 18", "Vite 5", "React-Leaflet 4", "Supabase / PostgreSQL", "Fly.io", "Vercel"]
                .map((tag) => <span key={tag} className="tech-tag">{tag}</span>)}
            </div>
          </Doc>
        </div>
      </CollapsibleSection>

      <ChatBot riskContext={riskContext} />
    </>
  );
}
