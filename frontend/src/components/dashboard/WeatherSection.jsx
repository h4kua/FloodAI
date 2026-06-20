/* ── Weather section ──────────────────────────────────────────────────────
   OpenWeather current conditions: a single-point card fallback and the
   per-wilayah (5 administrative cities) grid.
*/
import { useApp } from "../../lib/appContext";
import { use3DTilt } from "../../hooks/use3DTilt";
import { weatherCond, windDirection } from "../../lib/dashboardHelpers";
import { WeatherGlyph } from "./primitives";

function WeatherSingleCard({ ow, temp, humidity, rainfall, weatherIcon, desc, chips, isId }) {
  const tiltRef = use3DTilt({ maxTilt: 6 });
  return (
    <div ref={tiltRef} className="weather-current-card card-3d fade-in">
      <div className="card-3d-content">
        <div className="weather-current-header">
          <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
            <span style={{ display: "flex", color: "var(--cyan)" }}>{weatherIcon}</span>
            <div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.56rem", color: "var(--muted-2)", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: "0.1rem" }}>
                {isId ? "Cuaca Jakarta Sekarang" : "Jakarta Current Weather"}
              </div>
              <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.1rem", fontWeight: 700, color: "var(--text)", letterSpacing: "-0.01em" }}>{desc}</div>
              {temp != null && (
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted)", marginTop: "0.1rem" }}>
                  {temp.toFixed(1)}°C
                  {ow?.feels_like != null && <span style={{ marginLeft: "0.4rem", color: "var(--muted-2)" }}>feels {ow.feels_like.toFixed(1)}°</span>}
                </div>
              )}
            </div>
          </div>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em", flexShrink: 0 }}>● OpenWeather</span>
        </div>
        <div className="weather-chips-grid">
          {chips.map((c, i) => (
            <div key={i} className="weather-chip">
              <div>
                <div className="weather-chip-label">{c.label}</div>
                <div className="weather-chip-value" style={c.color ? { color: c.color } : {}}>{c.value}</div>
                {c.sub && <div className="weather-chip-sub">{c.sub}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function WeatherWilayahCard({ entry, isId }) {
  const tiltRef = use3DTilt({ maxTilt: 8 });
  const isRain = entry.ow.rainfall_1h > 0 || entry.ow.weather_main === "Rain" || entry.ow.weather_main === "Drizzle";
  const desc = entry.ow.weather_desc
    ? entry.ow.weather_desc.charAt(0).toUpperCase() + entry.ow.weather_desc.slice(1)
    : (isId ? "Berawan" : "Cloudy");

  return (
    <div ref={tiltRef} className={`ow-wilayah-card card-3d${isRain ? " rain" : ""}`}>
      <div className="ow-wilayah-card-header card-3d-title">
        <div className="ow-wilayah-name">{entry.short}</div>
        <div className="ow-wilayah-icon" style={{ color: isRain ? "var(--cyan)" : "var(--muted)" }}>
          <WeatherGlyph cond={weatherCond(entry.ow.weather_main)} size={22} />
        </div>
      </div>
      <div className="card-3d-content">
        {entry.ow.temp != null && (
          <div className="ow-wilayah-temp">{entry.ow.temp.toFixed(1)}°C</div>
        )}
        <div className={`ow-wilayah-desc${isRain ? " rain" : ""}`}>{desc}</div>
        <div className="ow-wilayah-chips">
          {entry.ow.humidity != null && (
            <span className="ow-mini-chip">RH {Math.round(entry.ow.humidity)}%</span>
          )}
          {entry.ow.wind_speed != null && (
            <span className="ow-mini-chip">{entry.ow.wind_speed.toFixed(1)} m/s</span>
          )}
          {isRain && entry.ow.rainfall_1h > 0 && (
            <span className="ow-mini-chip rain">{entry.ow.rainfall_1h.toFixed(1)} mm/j</span>
          )}
        </div>
        {entry.ow.feels_like != null && (
          <div className="ow-wilayah-feels">feels {entry.ow.feels_like.toFixed(1)}°</div>
        )}
      </div>
    </div>
  );
}

// WeatherCurrentCard — shows per-wilayah OWM data when available,
// falls back to single-point when openweatherWilayah is empty.
export function WeatherCurrentCard({ riskData }) {
  const { lang } = useApp();
  const isId     = lang === "id";
  const owWilayah = riskData?.openweatherWilayah ?? {};
  const owCenter  = riskData?.openweather;
  const hasWilayah = Object.keys(owWilayah).length > 0;

  // ── Fallback: single-point card ───────────────────────────
  if (!hasWilayah) {
    const ow       = owCenter;
    const rainfall = riskData?.rainfall ?? 0;
    const temp     = ow?.temp ?? riskData?.temperature;
    const humidity = ow?.humidity ?? riskData?.humidity;
    if (!temp && !ow) return null;

    const descRaw = ow?.weather_desc ?? (rainfall > 20 ? "hujan lebat" : rainfall > 5 ? "hujan ringan" : "berawan");
    const desc = descRaw.charAt(0).toUpperCase() + descRaw.slice(1);
    const cond = ow?.weather_main ? weatherCond(ow.weather_main) : weatherCond(descRaw);
    const weatherIcon = <WeatherGlyph cond={cond} size={42} />;

    const chips = [
      temp     != null && { label: isId ? "Suhu" : "Temp",     value: `${temp.toFixed(1)}°C`,       sub: ow?.feels_like != null ? `feels ${ow.feels_like.toFixed(1)}°` : null },
      humidity != null && { label: isId ? "Lembap" : "Humidity", value: `${Math.round(humidity)}%` },
      { label: isId ? "Hujan" : "Rainfall", value: rainfall > 0 ? `${Math.round(rainfall)} mm/j` : (isId ? "Tidak hujan" : "No rain"), color: rainfall > 0 ? "var(--cyan)" : "var(--safe)" },
      ow?.wind_speed  != null && { label: isId ? "Angin" : "Wind",    value: `${ow.wind_speed.toFixed(1)} m/s`, sub: windDirection(ow.wind_deg, isId) },
      ow?.pressure    != null && { label: isId ? "Tekanan" : "Pressure", value: `${ow.pressure} hPa` },
      ow?.clouds      != null && { label: isId ? "Tutupan" : "Cloud",  value: `${ow.clouds}%` },
      ow?.visibility  != null && { label: isId ? "Pandang" : "Visibility", value: `${(ow.visibility / 1000).toFixed(0)} km` },
    ].filter(Boolean);

    return (
      <WeatherSingleCard
        ow={ow}
        temp={temp}
        humidity={humidity}
        rainfall={rainfall}
        weatherIcon={weatherIcon}
        desc={desc}
        chips={chips}
        isId={isId}
      />
    );
  }

  // ── Per-wilayah grid (5 kota administrasi) ────────────────
  const WILAYAH_ORDER = ["Jakarta Utara","Jakarta Barat","Jakarta Selatan","Jakarta Timur","Jakarta Pusat"];
  const wilayahEntries = WILAYAH_ORDER
    .filter(w => owWilayah[w])
    .map(w => ({ wilayah: w, short: w.replace("Jakarta ", ""), ow: owWilayah[w] }));

  return (
    <div className="weather-current-card fade-in">
      <div className="weather-current-header" style={{ marginBottom: "0.875rem" }}>
        <div>
          <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.56rem", color: "var(--muted-2)", letterSpacing: "0.12em", textTransform: "uppercase" }}>
            {isId ? "Cuaca Per Wilayah Jakarta" : "Jakarta Weather by District"}
          </div>
          <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "0.88rem", fontWeight: 600, color: "var(--text)", marginTop: "0.15rem" }}>
            {isId ? "Data realtime 5 kota administrasi" : "Realtime data — 5 administrative cities"}
          </div>
        </div>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em", flexShrink: 0 }}>● OpenWeather</span>
      </div>

      <div className="ow-wilayah-grid">
        {wilayahEntries.map((entry) => (
          <WeatherWilayahCard key={entry.wilayah} entry={entry} isId={isId} />
        ))}
      </div>

      <p style={{ marginTop: "0.625rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)", lineHeight: 1.5 }}>
        {isId
          ? "● Titik representatif per kota administrasi · Update tiap 15 menit bersama scraper"
          : "● Representative point per administrative city · Updates every 15 min with scraper"}
      </p>
    </div>
  );
}
