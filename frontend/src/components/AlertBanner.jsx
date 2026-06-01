import { humanizeRiskLevel } from "../lib/humanize";

export default function AlertBanner({ level = "waspada" }) {
  const config = humanizeRiskLevel(level);
  return (
    <div
      style={{
        background: config.color,
        color: "white",
        textAlign: "center",
        padding: "12px 16px",
        fontWeight: "bold",
        fontSize: "18px",
        letterSpacing: "0.01em",
      }}
    >
      {config.emoji} {config.label} — {config.desc}
    </div>
  );
}
