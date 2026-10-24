/* ── Weather section ──────────────────────────────────────────────────────
   OpenWeather current conditions: one card per wilayah (5 administrative
   cities), or a single Jakarta card when per-wilayah data is missing.
   Only what a resident cares about: sky, temperature, and rain.
*/
import { useApp } from "../../lib/appContext";
import { weatherCond, weatherLabel } from "../../lib/dashboardHelpers";
import { WeatherGlyph } from "./primitives";

function WeatherWilayahCard({ entry, isId }) {
  const ow = entry.ow;
  const isRain = ow.rainfall_1h > 0 || ow.weather_main === "Rain" || ow.weather_main === "Drizzle";
  const desc = ow.weather_desc ? weatherLabel(ow.weather_desc, isId) : (isId ? "Berawan" : "Cloudy");

  return (
    <div className={`ow-wilayah-card${isRain ? " rain" : ""}`}>
      <div className="ow-wilayah-card-header">
        <div className="ow-wilayah-name">{entry.short}</div>
        <div className="ow-wilayah-icon" style={{ color: isRain ? "var(--cyan)" : "var(--muted)" }}>
          <WeatherGlyph cond={weatherCond(ow.weather_main)} size={22} />
        </div>
      </div>
      {ow.temp != null && <div className="ow-wilayah-temp">{Math.round(ow.temp)}°C</div>}
      <div className={`ow-wilayah-desc${isRain ? " rain" : ""}`}>
        {desc}{isRain && ow.rainfall_1h > 0 ? ` · ${ow.rainfall_1h.toFixed(1)} ${isId ? "mm/j" : "mm/h"}` : ""}
      </div>
    </div>
  );
}

export function WeatherCurrentCard({ riskData }) {
  const { lang } = useApp();
  const isId     = lang === "id";
  const owWilayah = riskData?.openweatherWilayah ?? {};
  const hasWilayah = Object.keys(owWilayah).length > 0;

  // ── Fallback: one Jakarta-wide card ───────────────────────
  if (!hasWilayah) {
    const ow       = riskData?.openweather;
    const rainfall = riskData?.rainfall ?? 0;
    const temp     = ow?.temp ?? riskData?.temperature;
    if (!temp && !ow) return null;

    const descRaw = ow?.weather_desc ?? (rainfall > 20 ? "hujan lebat" : rainfall > 5 ? "hujan ringan" : "berawan");
    const cond = ow?.weather_main ? weatherCond(ow.weather_main) : weatherCond(descRaw);

    return (
      <div className="panel panel-body fade-in" style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <span style={{ color: "var(--cyan)" }}><WeatherGlyph cond={cond} size={42} /></span>
        <div>
          <p className="station-sub" style={{ margin: 0 }}>{isId ? "Cuaca Jakarta sekarang" : "Jakarta weather now"}</p>
          <p className="station-title" style={{ margin: "0.1rem 0" }}>
            {weatherLabel(descRaw, isId)}{temp != null ? ` · ${Math.round(temp)}°C` : ""}
          </p>
          <p className="station-sub" style={{ margin: 0 }}>
            {rainfall > 0
              ? (isId ? `Hujan ${Math.round(rainfall)} mm/jam` : `Rain ${Math.round(rainfall)} mm/h`)
              : (isId ? "Tidak hujan" : "No rain")}
          </p>
        </div>
      </div>
    );
  }

  // ── Per-wilayah grid (5 kota administrasi) ────────────────
  const WILAYAH_ORDER = ["Jakarta Utara","Jakarta Barat","Jakarta Selatan","Jakarta Timur","Jakarta Pusat"];
  const wilayahEntries = WILAYAH_ORDER
    .filter(w => owWilayah[w])
    .map(w => ({ wilayah: w, short: w.replace("Jakarta ", ""), ow: owWilayah[w] }));

  return (
    <div className="panel panel-body fade-in">
      <p className="station-title">{isId ? "Cuaca sekarang per wilayah" : "Weather now by area"}</p>
      <div className="ow-wilayah-grid" style={{ marginTop: "0.75rem" }}>
        {wilayahEntries.map((entry) => (
          <WeatherWilayahCard key={entry.wilayah} entry={entry} isId={isId} />
        ))}
      </div>
    </div>
  );
}
