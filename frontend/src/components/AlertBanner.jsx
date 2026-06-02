import { humanizeRiskLevel } from "../lib/humanize";
import { useApp } from "../lib/appContext";

export default function AlertBanner({ level = "waspada" }) {
  const { lang } = useApp();
  const config = humanizeRiskLevel(level, lang);
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
