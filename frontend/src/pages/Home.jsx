import { useEffect } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import { humanizeRiskLevel, humanizeRainfall } from "../lib/humanize";
import EmergencyContacts from "../components/EmergencyContacts";
import LoadingSpinner from "../components/LoadingSpinner";

export default function Home({ setRiskLevel }) {
  const { riskData, loading, lastUpdated, error, refresh } = useFloodRisk();

  useEffect(() => {
    if (riskData?.level) setRiskLevel(riskData.level);
  }, [riskData, setRiskLevel]);

  const s = {
    container: { maxWidth: "600px", margin: "0 auto", padding: "16px", display: "flex", flexDirection: "column", gap: "16px" },
    card:      { background: "#1e293b", borderRadius: "12px", padding: "20px" },
    heading:   { margin: "0 0 12px", fontSize: "20px", fontWeight: "bold" },
    stat:      { display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: "1px solid #334155" },
    label:     { color: "#94a3b8", fontSize: "15px" },
    value:     { fontWeight: "600", fontSize: "15px" },
    btn:       { background: "#3b82f6", color: "white", border: "none", borderRadius: "8px", padding: "12px 20px", fontSize: "16px", cursor: "pointer", minHeight: "44px", width: "100%" },
    errBox:    { background: "#450a0a", border: "1px solid #dc2626", borderRadius: "8px", padding: "12px", color: "#fca5a5" },
  };

  if (loading) return <LoadingSpinner />;

  if (error) {
    return (
      <div style={s.container}>
        <div style={s.errBox}>
          <p style={{ margin: 0 }}>❌ {error}</p>
          <button onClick={refresh} style={{ ...s.btn, marginTop: "12px" }}>Coba Lagi</button>
        </div>
        <EmergencyContacts />
      </div>
    );
  }

  const config = humanizeRiskLevel(riskData?.level ?? "waspada");

  return (
    <div style={s.container}>
      <div style={{ ...s.card, borderLeft: `4px solid ${config.color}` }}>
        <h2 style={s.heading}>📊 Status Banjir Jakarta</h2>
        <div style={s.stat}>
          <span style={s.label}>🎯 Level Risiko</span>
          <span style={{ ...s.value, color: config.color }}>{config.emoji} {config.label}</span>
        </div>
        <div style={s.stat}>
          <span style={s.label}>🌧️ Curah Hujan</span>
          <span style={s.value}>{humanizeRainfall(riskData?.rainfall)}</span>
        </div>
        <div style={{ ...s.stat, borderBottom: "none" }}>
          <span style={s.label}>📈 Skor Risiko</span>
          <span style={s.value}>{riskData?.riskScore ?? "—"} / 100</span>
        </div>
        {riskData?.interpretation && (
          <p style={{ margin: "12px 0 0", color: "#cbd5e1", fontSize: "14px" }}>
            {riskData.interpretation}
          </p>
        )}
        <p style={{ margin: "8px 0 0", color: "#475569", fontSize: "12px" }}>
          Diperbarui: {lastUpdated?.toLocaleTimeString("id-ID") ?? "—"} · otomatis setiap 15 menit
        </p>
      </div>

      <button onClick={refresh} style={s.btn}>🔄 Perbarui Data</button>

      <EmergencyContacts />
    </div>
  );
}
