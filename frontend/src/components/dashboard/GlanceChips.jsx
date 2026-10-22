import { useT, useApp } from "../../lib/appContext";

/* ── GlanceChips — the 3–4 numbers that matter, readable in one glance ─────
   Replaces the old MetricsRow + SensorStrip above the fold. Big value, plain
   label, color only as reinforcement (never the sole signal).
*/
export default function GlanceChips({ riskData, siaga1 = 0, siaga2 = 0, totalStations = null, calibratedStations = null }) {
  const t = useT();
  const { lang } = useApp();
  const isId = lang === "id";

  const wlr = riskData?.waterLevelRatio;
  const rainfall = riskData?.rainfall ?? 0;
  const alertCount = siaga1 + siaga2;

  const waterColor = wlr == null ? "var(--muted)" : wlr >= 1 ? "var(--s1)" : wlr >= 0.75 ? "var(--s2)" : wlr >= 0.5 ? "var(--wsp)" : "var(--safe)";
  const alertColor = siaga1 > 0 ? "var(--s1)" : siaga2 > 0 ? "var(--s2)" : "var(--safe)";
  const rainColor = rainfall > 20 ? "var(--s2)" : rainfall > 5 ? "var(--wsp)" : "var(--cyan)";

  const chips = [
    wlr != null && {
      label: t("glance.water"),
      value: `${Math.round(wlr * 100)}%`,
      color: waterColor,
    },
    {
      label: t("glance.rain"),
      value: `${Math.round(rainfall)}`,
      unit: "mm/j",
      sub: rainfall >= 20 ? (isId ? "deras" : "heavy")
         : rainfall >= 5 ? (isId ? "sedang" : "moderate")
         : rainfall > 0  ? (isId ? "ringan" : "light")
         : (isId ? "tidak hujan" : "no rain"),
      color: rainColor,
    },
    {
      label: t("glance.alerts"),
      value: `${alertCount}`,
      color: alertColor,
    },
    totalStations != null && {
      label: t("glance.stations"),
      value: `${calibratedStations ?? totalStations}`,
      color: "var(--cyan)",
    },
  ].filter(Boolean);

  return (
    <div className="glance-grid fade-in">
      {chips.map((chip) => (
        <div key={chip.label} className="glance-chip">
          <span className="glance-chip-value" style={{ color: chip.color }}>
            {chip.value}
            {chip.unit && <span className="glance-chip-unit">{chip.unit}</span>}
          </span>
          <span className="glance-chip-label">{chip.label}{chip.sub && ` · ${chip.sub}`}</span>
        </div>
      ))}
    </div>
  );
}
