/* ── Weather section ──────────────────────────────────────────────────────
   OpenWeather current conditions: one card per wilayah (5 administrative
   cities), or a single Jakarta card when per-wilayah data is missing.
   Sky, temperature and rain first, then feels-like, humidity, cloud and wind.
   The map's weather cards show the same readings in the same words; tapping
   one opens this tab with that kota's card highlighted (`picked`).
*/
import { useApp } from "../../lib/appContext";
import { weatherCond, weatherLabel, wilayahLabel } from "../../lib/dashboardHelpers";
import { WeatherGlyph } from "./primitives";

const COMPASS = {
  id: ["utara", "timur laut", "timur", "tenggara", "selatan", "barat daya", "barat", "barat laut"],
  en: ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"],
};
const fromDir = (deg, isId) => COMPASS[isId ? "id" : "en"][Math.round((((deg % 360) + 360) % 360) / 45) % 8];

function WeatherWilayahCard({ entry, isId, picked }) {
  const ow = entry.ow;
  const details = [
    ow.feels_like != null && [isId ? "Terasa" : "Feels like", `${Math.round(ow.feels_like)}°C`],
    ow.humidity != null && [isId ? "Kelembapan" : "Humidity", `${ow.humidity}%`],
    ow.clouds != null && [isId ? "Awan" : "Cloud", `${ow.clouds}%`],
    ow.wind_speed != null && [isId ? "Angin" : "Wind",
      `${Math.round(ow.wind_speed * 3.6)} km/${isId ? "jam" : "h"}${ow.wind_deg != null ? ` ${isId ? "dari" : "from"} ${fromDir(ow.wind_deg, isId)}` : ""}`],
  ].filter(Boolean);
  const isRain = ow.rainfall_1h > 0 || ow.weather_main === "Rain" || ow.weather_main === "Drizzle";
  const desc = ow.weather_desc ? weatherLabel(ow.weather_desc, isId) : (isId ? "Berawan" : "Cloudy");

  return (
    <div id={`ow-card-${entry.wilayah.replace(/\s+/g, "-")}`} className={`ow-wilayah-card${isRain ? " rain" : ""}${picked ? " picked" : ""}`}>
      <div className="ow-wilayah-card-header">
        <div className="ow-wilayah-name">{entry.short}</div>
        <div className="ow-wilayah-icon" style={{ color: isRain ? "var(--cyan)" : "var(--muted)" }}>
          <WeatherGlyph cond={weatherCond(ow.weather_main)} size={22} />
        </div>
      </div>
      {ow.temp != null && <div className="ow-wilayah-temp">{Math.round(ow.temp)}°C</div>}
      <div className={`ow-wilayah-desc${isRain ? " rain" : ""}`}>
        {desc}{isRain && ow.rainfall_1h > 0 ? ` · ${ow.rainfall_1h.toLocaleString(isId ? "id-ID" : "en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} ${isId ? "mm/jam" : "mm/h"}` : ""}
      </div>
      {details.length > 0 && (
        <dl className="ow-wilayah-details">
          {details.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      )}
    </div>
  );
}

export function WeatherCurrentCard({ riskData, picked = null }) {
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
    .map(w => ({ wilayah: w, short: wilayahLabel(w, isId), ow: owWilayah[w] }));

  return (
    <div className="panel panel-body fade-in">
      <p className="station-title">{isId ? "Cuaca sekarang per wilayah" : "Weather now by area"}</p>
      <div className="ow-wilayah-grid" style={{ marginTop: "0.75rem" }}>
        {wilayahEntries.map((entry) => (
          <WeatherWilayahCard key={entry.wilayah} entry={entry} isId={isId} picked={picked === entry.wilayah} />
        ))}
      </div>
      <p className="station-sub" style={{ marginTop: "0.75rem", marginBottom: 0 }}>
        {isId
          ? "OpenWeather, satu titik pengukuran per kota. Sama dengan cuaca di peta; tidak mengubah status banjir."
          : "OpenWeather, one point per city. The same readings as the map; weather does not change the flood status."}
      </p>
    </div>
  );
}
