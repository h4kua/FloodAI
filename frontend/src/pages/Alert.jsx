import { humanizeRiskLevel } from "../lib/humanize";
import EmergencyContacts from "../components/EmergencyContacts";

const STEPS = [
  {
    title: "Siapkan Tas Darurat",
    desc: "Kemas dokumen penting, obat-obatan, pakaian untuk 3 hari, air minum, dan senter.",
  },
  {
    title: "Matikan Listrik dan Gas",
    desc: "Cabut semua peralatan listrik dari stop kontak dan matikan kompor gas.",
  },
  {
    title: "Beritahu Anggota Keluarga",
    desc: "Pastikan semua anggota keluarga mengetahui rencana evakuasi dan titik kumpul.",
  },
  {
    title: "Menuju Titik Kumpul",
    desc: "Evakuasi ke lokasi pengungsian resmi terdekat. Hindari area genangan air.",
  },
  {
    title: "Daftar di Pos Pengungsian",
    desc: "Laporkan diri kepada petugas di pos pengungsian untuk pendataan dan bantuan.",
  },
];

export default function Alert({ riskLevel = "waspada" }) {
  const config = humanizeRiskLevel(riskLevel);

  return (
    <>
      {/* Alert hero */}
      <div className={`alert-hero ${riskLevel}`}>
        <div className="alert-level-tag">{config.label}</div>
        <p className={`alert-level-label`}>{config.label}</p>
        <p className="alert-desc">{config.desc}</p>
      </div>

      {/* Evacuation steps */}
      <div className="card">
        <p className="section-label">Langkah Evakuasi</p>
        <div className="steps">
          {STEPS.map((step, i) => (
            <div key={i} className="step">
              <span className="step-num">{i + 1}</span>
              <div>
                <p className="step-title">{step.title}</p>
                <p className="step-desc">{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <EmergencyContacts />
    </>
  );
}
