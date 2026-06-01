import { humanizeRiskLevel } from "../lib/humanize";
import EmergencyContacts from "../components/EmergencyContacts";

const evacuationSteps = [
  { icon: "📦", title: "Siapkan Tas Darurat",   desc: "Dokumen penting, obat-obatan, pakaian 3 hari, air minum" },
  { icon: "🔌", title: "Matikan Listrik & Gas",  desc: "Cabut semua peralatan listrik dan matikan kompor gas" },
  { icon: "📞", title: "Hubungi Keluarga",        desc: "Beritahu anggota keluarga tentang rencana evakuasi" },
  { icon: "🚶", title: "Pergi ke Titik Kumpul",  desc: "Menuju lokasi pengungsian terdekat yang aman" },
  { icon: "📋", title: "Daftar di Posko",         desc: "Laporkan diri ke petugas di tempat pengungsian" },
];

export default function Alert({ riskLevel = "waspada" }) {
  const config = humanizeRiskLevel(riskLevel);
  const s = {
    container: { maxWidth: "600px", margin: "0 auto", padding: "16px", display: "flex", flexDirection: "column", gap: "16px" },
    card: { background: "#1e293b", borderRadius: "12px", padding: "20px" },
    step: { display: "flex", alignItems: "flex-start", gap: "14px", background: "#0f172a", borderRadius: "10px", padding: "14px" },
  };

  return (
    <div style={s.container}>
      <div style={{ ...s.card, borderLeft: `4px solid ${config.color}`, textAlign: "center" }}>
        <p style={{ fontSize: "48px", margin: "0 0 8px" }}>{config.emoji}</p>
        <h2 style={{ margin: "0 0 6px", fontSize: "24px", color: config.color }}>{config.label}</h2>
        <p style={{ margin: 0, color: "#cbd5e1" }}>{config.desc}</p>
      </div>

      <div style={s.card}>
        <h3 style={{ margin: "0 0 14px", fontSize: "18px" }}>🚨 Langkah Evakuasi</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {evacuationSteps.map((step, i) => (
            <div key={i} style={s.step}>
              <span style={{ fontSize: "28px", flexShrink: 0 }}>{step.icon}</span>
              <div>
                <p style={{ margin: "0 0 4px", fontWeight: "bold" }}>{i + 1}. {step.title}</p>
                <p style={{ margin: 0, color: "#94a3b8", fontSize: "14px" }}>{step.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <EmergencyContacts />
    </div>
  );
}
