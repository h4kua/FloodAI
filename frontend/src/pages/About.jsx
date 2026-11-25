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
    { page: "home", t: id ? "Cek status Jakarta" : "Check Jakarta's status", d: id ? "Aman, Waspada, Siaga atau Bahaya, dan apa yang bisa dilakukan." : "Safe, Watch, Alert or Danger, and what you can do." },
    { page: "alert", t: id ? "Cari rute aman" : "Find a safe route", d: id ? "Jalan yang menghindari area rawan banjir yang sedang aktif." : "A road that avoids the flood-prone areas that are active now." },
    { page: "history", t: id ? "Lihat riwayat" : "See the history", d: id ? "Status dan hujan beberapa hari terakhir, hari demi hari." : "Status and rain over the last days, day by day." },
    { page: "reports", t: id ? "Kirim laporan" : "Send a report", d: id ? "Kabarkan air di sekitar Anda; warga lain ikut melihat." : "Tell others about the water near you." },
  ];

  const levels = [
    { key: "AMAN", d: id ? "Tidak ada tanda banjir. Beraktivitas seperti biasa." : "No sign of flooding. Go about your day." },
    { key: "WASPADA", d: id ? "Ada kemungkinan genangan di beberapa tempat, terutama kalau hujan turun. Tidak perlu panik; pantau info dan hindari parkir di tepi sungai." : "Waterlogging is possible in a few places, mostly if it rains. No need to worry; keep an eye on it and avoid parking by rivers." },
    { key: "SIAGA", d: id ? "Air sungai sudah tinggi atau peluang genangan besar. Mulai bersiap: tas siaga, dokumen di tempat tinggi, cek Rute Aman." : "River levels are high or waterlogging is quite likely. Start getting ready: a go-bag, papers up high, check Safe Route." },
    { key: "BAHAYA", d: id ? "Ada pos di batas tertinggi (Siaga 1) atau risikonya sangat tinggi. Ikuti arahan BPBD dan siap mengungsi bila diminta. Darurat: 112." : "A post is at its highest level (Siaga 1) or the risk is very high. Follow BPBD and be ready to leave if asked. Emergency: 112." },
  ];

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{id ? "Tentang deFlood.ai" : "About deFlood.ai"}</h1>
          <p className="page-sub">
            {id
              ? "Untuk dua hal saja: memperkirakan banjir di Jakarta, dan menunjukkan jalan yang tidak melewati genangan."
              : "For two things only: estimating flooding in Jakarta, and showing roads that avoid waterlogging."}
          </p>
        </div>
      </div>

      <div className="doc fade-in">
        <Doc id="about-start" title={id ? "Mulai dari sini" : "Start here"}
             note={id ? "Pilih yang Anda perlukan sekarang." : "Pick what you need now."}>
          <div className="start-links">
            {start.map((s) => (
              <button key={s.page} type="button" className="start-link" onClick={go(s.page)}>
                <b>{s.t}</b>
                <span>{s.d}</span>
              </button>
            ))}
          </div>
        </Doc>

        <Doc id="about-status" title={id ? "Arti status" : "What the status means"}
             note={id ? "Satu kata untuk seluruh Jakarta, diperbarui tiap 15 menit." : "One word for all of Jakarta, updated every 15 minutes."}>
          <ul className="status-key">
            {levels.map((l) => (
              <li key={l.key}>
                <RiskBadge level={l.key} />
                <p>{l.d}</p>
              </li>
            ))}
          </ul>
        </Doc>

        <Doc id="about-how" title={id ? "Dari data sampai status" : "From data to status"}>
          <ol className="how-steps">
            <li>
              <b>{id ? "Data masuk." : "Data comes in."}</b>{" "}
              {id ? "Tiap 15 menit kami membaca ketinggian air di pos pantau sungai dan pintu air, cuaca, dan peringatan BMKG. Hujan satelit NASA ikut dibaca; datanya tiba sekitar 5 jam setelah hujan."
                  : "Every 15 minutes we read water levels at river and gate posts, the weather and BMKG warnings. NASA satellite rain is read too; it arrives about 5 hours after the rain."}
            </li>
            <li>
              <b>{id ? "Peluang tiap kecamatan." : "A chance for each kecamatan."}</b>{" "}
              {id ? "Model harian, dilatih dengan catatan genangan BPBD 2013–2025, memperkirakan peluang ada genangan di tiap kecamatan hari ini dari hujan beberapa hari terakhir."
                  : "A daily model, trained on BPBD waterlogging records from 2013–2025, estimates today's chance of waterlogging in each kecamatan from the last few days of rain."}
            </li>
            <li>
              <b>{id ? "Peluang untuk Jakarta, lalu status." : "A chance for Jakarta, then the status."}</b>{" "}
              {id ? "Model keputusan menggabungkannya dengan status pos sungai sekarang dan kemarin serta hujan hari ini. Di depannya ada aturan keselamatan: pos di Siaga 1 selalu berarti Bahaya, dan peringatan BMKG yang parah berarti minimal Siaga."
                  : "A decision model combines it with the river posts now and yesterday and today's rain. Safety rules sit in front of it: a post at Siaga 1 always means Danger, and a severe BMKG warning means at least Alert."}
            </li>
            <li>
              <b>{id ? "Pos yang memang selalu tinggi." : "Posts that are always high."}</b>{" "}
              {id ? "P.A. Cengkareng Drain dan dua pos laut (Marina Ancol, Pompa Pasar Ikan) naik turun mengikuti pasang laut dan pintu air. Status resminya tetap tampil, tapi untuk status Jakarta dan lingkaran merah di peta mereka dihitung satu tingkat lebih rendah, supaya tidak membuat status naik terus."
                  : "P.A. Cengkareng Drain and two sea posts (Marina Ancol, Pompa Pasar Ikan) rise and fall with the tide and the gates. Their official status is still shown, but for Jakarta's status and the red circles on the map they count one level lower, so they do not keep the status up."}
            </li>
          </ol>
          <p className="doc-aside">
            {id ? "Lingkaran merah di peta hanya muncul di area rawan banjir yang sungainya sedang di Siaga 2 atau Siaga 1. Itu bukan kepastian banjir: pada catatan 2016–2021, area seperti itu tercatat banjir sekitar 1 dari 4 hari, dibanding 1 dari 60 hari biasa."
                : "Red circles on the map appear only on flood-prone areas whose river is at Alert 2 or Alert 1. That is not a certainty: in the 2016–2021 records such areas had a recorded flood on about 1 day in 4, against 1 in 60 on normal days."}
          </p>
        </Doc>

        <Doc id="about-trust" title={id ? "Seberapa bisa dipercaya" : "How far to trust it"}
             note={id ? "Diuji pada hari yang tidak dipakai untuk melatih." : "Tested on days that were not used for training."}>
          <ul className="doc-list">
            <li>
              {id ? "Pada tahun-tahun yang diuji (2019–2021, 2025), model memberi peluang lebih tinggi pada hari banjir daripada hari biasa sekitar 8 dari 10 kali."
                  : "On the years tested (2019–2021, 2025), the model gave a higher chance to flood days than to ordinary days about 8 times in 10."}
            </li>
            <li>
              {id ? "Uji lagi untuk Januari–Mei 2026 dengan 34 hari banjir dari berita: 6 dari 10 hari banjir, dan 8 dari 10 banjir besar, berstatus Waspada atau lebih. Hasilnya sebanding dengan aturan sederhana “hujan 7 hari terakhir”, bukan lebih baik."
                  : "A further test on January–May 2026 with 34 flood days from the news: 6 in 10 flood days, and 8 in 10 large floods, showed Watch or higher. That is about as good as the simple rule “rain over the last 7 days”, not better."}
            </li>
            <li>
              {id ? "Dua banjir terbesar 2026 (29 Jan dan 8 Mar) tidak tertangkap. Hujan di satelit pada hari-hari itu tidak ekstrem, jadi banjir yang tidak diawali hujan lebat di Jakarta, Bogor atau Depok bisa terlewat."
                  : "The two largest floods of 2026 (29 Jan and 8 Mar) were missed. The satellite rain on those days was not extreme, so floods that do not follow heavy rain over Jakarta, Bogor or Depok can slip through."}
            </li>
            <li>
              {id ? "Angka peluang biasanya kecil (10–40%): artinya peluang ada genangan di salah satu kecamatan hari itu, bukan peluang banjir besar. Genangan kecil sering tidak tercatat, dan catatan BPBD setelah 2022 belum lengkap."
                  : "The chances are usually small (10–40%): they are the chance of waterlogging in at least one kecamatan that day, not of a big flood. Small waterlogging often goes unrecorded, and BPBD records after 2022 are incomplete."}
            </li>
            <li>
              {id ? "Di musim hujan (Januari–Februari) status Waspada muncul hampir setiap hari. Itu peringatan ringan, bukan tanda bahaya."
                  : "In the rainy season (January–February) the Watch status shows on almost every day. That is a light notice, not a sign of danger."}
            </li>
          </ul>
        </Doc>

        <Doc id="about-know" title={id ? "Penting diketahui" : "Good to know"}>
          <ul className="doc-list">
            {(id ? [
              "Situs ini alat bantu, bukan pengganti informasi resmi dari BPBD, BMKG, atau BNPB. Saat darurat, ikuti arahan petugas.",
              "Rute Aman adalah perkiraan dari titik rawan banjir BPBD, bukan kondisi jalan langsung. Cek jalan sendiri sebelum berangkat.",
              "Data bisa terlambat bila pos pantau belum mengirim pembaruan.",
              "Laporan warga belum diverifikasi, tampil 6 jam, dan tidak mengubah status resmi.",
              "Pilihan daerah di Cek daerahku hanya disimpan di perangkat Anda.",
            ] : [
              "This site is an aid, not a replacement for official information from BPBD, BMKG or BNPB. In an emergency, follow the officers.",
              "Safe Route is an estimate from BPBD flood-prone points, not live road conditions. Check the road yourself before you go.",
              "Data can be late if a monitoring post has not sent an update.",
              "Community reports are unverified, shown for 6 hours and never change the official status.",
              "The area you choose in Check my area is kept on your device only.",
            ]).map((text) => <li key={text}>{text}</li>)}
          </ul>
        </Doc>

        <Doc id="about-team" title={id ? "Tim pengembang" : "The team"}
             note={id ? "Dibuat oleh mahasiswa sebagai kontribusi untuk peringatan dini banjir di Jakarta." : "Built by students as a contribution to early flood warning in Jakarta."}>
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
        subtitle={id ? "Performa model, sumber data, dan teknologi" : "Model performance, data sources, and stack"}
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
