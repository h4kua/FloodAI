import { humanizeRiskLevel } from "../lib/humanize";

export default function AlertBanner({ level = "waspada" }) {
  const config = humanizeRiskLevel(level);
  return (
    <div className={`alert-banner ${level}`}>
      <span className="banner-dot" />
      <span>
        Status Jakarta: <strong>{config.label}</strong> — {config.desc}
        <span style={{ marginLeft: "1rem", opacity: 0.6, fontWeight: 400 }}>· BPBD 117</span>
      </span>
    </div>
  );
}
