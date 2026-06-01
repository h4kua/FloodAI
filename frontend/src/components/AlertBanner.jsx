import { humanizeRiskLevel } from "../lib/humanize";

export default function AlertBanner({ level = "waspada" }) {
  const config = humanizeRiskLevel(level);
  return (
    <div className={`alert-banner ${level}`}>
      <span className="banner-indicator" />
      <span>
        Status Jakarta: <strong>{config.label}</strong> — {config.desc}
      </span>
    </div>
  );
}
