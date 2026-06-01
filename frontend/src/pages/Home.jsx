import { useEffect } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import { humanizeRiskLevel, humanizeRainfall } from "../lib/humanize";
import EmergencyContacts from "../components/EmergencyContacts";
import LoadingSpinner from "../components/LoadingSpinner";

function ScoreBar({ value, color }) {
  return (
    <div className="score-bar-wrap">
      <div className="score-bar-header">
        <span className="score-bar-label">Skor Risiko</span>
        <span className="score-bar-value" style={{ color }}>
          {value}<span style={{ fontSize: "0.75rem", fontWeight: 400, color: "var(--text-2)", marginLeft: 2 }}>/100</span>
        </span>
      </div>
      <div className="score-bar-track">
        <div
          className="score-bar-fill"
          style={{ width: `${value}%`, background: color }}
        />
      </div>
    </div>
  );
}

export default function Home({ setRiskLevel }) {
  const { riskData, loading, lastUpdated, error, refresh } = useFloodRisk();

  useEffect(() => {
    if (riskData?.level) setRiskLevel(riskData.level);
  }, [riskData, setRiskLevel]);

  if (loading) return <LoadingSpinner />;

  if (error) {
    return (
      <>
        <div className="error-box">
          <p className="error-title">Gagal memuat data</p>
          <p className="error-msg">{error}</p>
          <button className="btn btn-ghost" onClick={refresh}>Coba Lagi</button>
        </div>
        <EmergencyContacts />
      </>
    );
  }

  const level  = riskData?.level ?? "waspada";
  const config = humanizeRiskLevel(level);
  const score  = riskData?.riskScore ?? 0;

  return (
    <>
      {/* Risk hero */}
      <div className={`risk-hero ${level}`}>
        <p className="risk-eyebrow">Status Banjir Jakarta</p>
        <p className={`risk-level ${level}`}>{config.label}</p>
        <p className="risk-desc">{config.recommendation}</p>
        <ScoreBar value={score} color={config.color} />
      </div>

      {/* Metrics */}
      <div className="metrics">
        <div className="metric">
          <span className="metric-label">Probabilitas</span>
          <span className="metric-value">
            {score}<span className="metric-unit">%</span>
          </span>
          <span className="metric-sub">kemungkinan banjir</span>
        </div>

        <div className="metric">
          <span className="metric-label">Curah Hujan</span>
          <span className="metric-value">
            {riskData?.rainfall ?? 0}<span className="metric-unit">mm</span>
          </span>
          <span className="metric-sub">{humanizeRainfall(riskData?.rainfall)}</span>
        </div>

        <div className="metric">
          <span className="metric-label">Level</span>
          <span className="metric-value" style={{ fontSize: "1.1rem", color: config.color }}>
            {config.label}
          </span>
          <span className="metric-sub">{level}</span>
        </div>
      </div>

      {/* Interpretation */}
      {riskData?.interpretation && (
        <div className="interpretation">
          {riskData.interpretation}
        </div>
      )}

      {/* Update row */}
      <div className="update-row">
        <span className="updated-at">
          {lastUpdated
            ? `Diperbarui pukul ${lastUpdated.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}`
            : "Belum ada data"}
        </span>
        <button className="btn btn-ghost" onClick={refresh}>
          Perbarui
        </button>
      </div>

      <EmergencyContacts />
    </>
  );
}
