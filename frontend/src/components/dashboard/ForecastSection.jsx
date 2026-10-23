/* ── Forecast section ─────────────────────────────────────────────────────
   BMKG per-wilayah 12-hour forecast grid (with a stale-snapshot empty state)
   and the flat BMKG forecast fallback panel.
*/
import { useApp } from "../../lib/appContext";
import { weatherCond } from "../../lib/dashboardHelpers";
import { WeatherGlyph } from "./primitives";

/* ── Wilayah Forecast Grid — compact 12-hour BMKG timeline ──
   Shows WHERE and WHEN rain arrives over the next 1-12 hours.
*/
export function WilayahForecastGrid({ wilayahSummary }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!wilayahSummary || wilayahSummary.length === 0) return null;

  const title = isId ? "Prakiraan cuaca" : "Weather forecast";

  // Stale-snapshot fallback: the backend keeps only FUTURE BMKG slots, so a
  // very old snapshot leaves nothing to show. Say so plainly instead.
  const hasAnyForecast = wilayahSummary.some((w) => (w.forecast?.length ?? 0) > 0);
  if (!hasAnyForecast) {
    return (
      <div className="panel panel-body fade-in">
        <p className="station-title">{title}</p>
        <p className="station-sub" style={{ marginBottom: 0 }}>
          {isId
            ? "Prakiraan belum tersedia karena data belum diperbarui. Coba lagi nanti."
            : "No forecast yet because the data hasn't been updated. Please check back later."}
        </p>
      </div>
    );
  }

  const now = new Date();
  // Hours from now, rounded the same way for the column labels and the title.
  const hoursAhead = (slot) => {
    const diffH = Math.round((new Date(slot.local_datetime) - now) / 3_600_000);
    return diffH <= 4 ? diffH : Math.round(diffH / 3) * 3;
  };
  const getTimeLabel = (slot, i) => {
    if (!slot?.local_datetime) return i === 0 ? (isId ? "Skrg" : "Now") : `+${i * 6}j`;
    const h = hoursAhead(slot);
    if (h <= 1) return isId ? "Skrg" : "Now";
    return isId ? `+${h} jam` : `+${h}h`;
  };

  // Most at-risk wilayah first
  const sorted = [...wilayahSummary].sort((a, b) => (b.worst_rank ?? 0) - (a.worst_rank ?? 0));
  const timeSlots = (sorted[0]?.forecast || []).slice(0, 4);

  // Title follows the slots actually shown — BMKG slots are ~3-6 h apart and
  // can start well after "now", so a fixed "12 jam" would be wrong.
  const lastSlot = timeSlots[timeSlots.length - 1];
  const spanH = lastSlot?.local_datetime ? hoursAhead(lastSlot) : null;
  const spanDays = Math.round(spanH / 24);
  const rangeTitle = !(spanH > 1)
    ? title
    : spanH >= 36
    ? (isId ? `Prakiraan cuaca ${spanDays} hari ke depan` : `Weather for the next ${spanDays} days`)
    : (isId ? `Prakiraan cuaca ${spanH} jam ke depan` : `Weather for the next ${spanH} hours`);

  return (
    <div className="panel panel-body fade-in">
      <p className="station-title">{rangeTitle}</p>
      <p className="station-sub">
        {isId ? "Sumber: BMKG. Ikon biru berarti hujan." : "Source: BMKG. Blue icons mean rain."}
      </p>

      <div className="forecast-table">
        <div className="forecast-table-header">
          <div className="fct-label-cell" />
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="fct-time-header">
              {timeSlots[i] ? getTimeLabel(timeSlots[i], i) : "—"}
            </div>
          ))}
        </div>

        {sorted.map((w) => {
          const slots = (w.forecast || []).slice(0, 4);
          return (
            <div key={w.wilayah} className="forecast-table-row">
              <div className="fct-label-cell">
                <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text)" }}>
                  {w.wilayah.replace("Jakarta ", "")}
                </div>
              </div>

              {[0, 1, 2, 3].map((i) => {
                const slot = slots[i];
                if (!slot) {
                  return <div key={i} className="fct-cell fct-cell-empty"><span>—</span></div>;
                }
                const isRain = slot.weather_desc?.toLowerCase().includes("hujan");
                return (
                  <div key={i} className={`fct-cell${isRain ? " rain" : ""}`}>
                    <span className="fct-icon"><WeatherGlyph cond={weatherCond(slot.weather_desc)} size={22} /></span>
                    <span className={`fct-desc${isRain ? " rain" : ""}`}>{slot.weather_desc ?? "—"}</span>
                    {slot.tmin != null && <span className="fct-temp">{slot.tmin}–{slot.tmax}°</span>}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ForecastPanel({ forecast }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!forecast || forecast.length === 0) return null;

  return (
    <div className="panel panel-body fade-in">
      <p className="station-title">{isId ? "Prakiraan cuaca Jakarta" : "Jakarta weather forecast"}</p>
      <div style={{ display: "flex", gap: "0.625rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
        {forecast.map((slot, i) => {
          const dt = new Date(slot.local_datetime);
          const timeStr = dt.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
          const dateStr = dt.toLocaleDateString("id-ID", { day: "numeric", month: "short" });
          const isRain = slot.weather_desc?.toLowerCase().includes("hujan");
          return (
            <div key={i} style={{
              flex: "1 1 120px",
              background: isRain ? "var(--cyan-soft)" : "var(--panel)",
              border: `1px solid ${isRain ? "var(--cyan-border)" : "var(--line)"}`,
              borderRadius: "var(--r-lg)", padding: "0.625rem 0.75rem",
              display: "flex", flexDirection: "column", gap: "0.25rem", minWidth: 0,
            }}>
              <span style={{ fontSize: "0.76rem", color: "var(--muted-2)" }}>{dateStr} · {timeStr}</span>
              <span style={{ color: isRain ? "var(--cyan)" : "var(--muted)" }}>
                <WeatherGlyph cond={weatherCond(slot.weather_desc)} size={24} />
              </span>
              <span style={{ fontSize: "0.82rem", color: "var(--text)", lineHeight: 1.3, fontWeight: 500 }}>{slot.weather_desc}</span>
              {slot.tmin != null && (
                <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>{slot.tmin}–{slot.tmax}°C</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
