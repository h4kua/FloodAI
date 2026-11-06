/* ── Weather per wilayah for the home map ─────────────────────────────────
   Current weather for each of the five mainland kota from Open-Meteo (free,
   no key, 15-minute data): weather code, cloud cover, rain, temperature,
   humidity, wind and day/night. This is a weather model's estimate on a grid
   of a few km, not a radar reading: neighbouring kota can show the same values.
*/

// Where each kota's weather is read and its label drawn: inside the kota,
// away from the clusters of water-level posts.
export const WILAYAH = [
  { key: "Utara",   id: "Utara",   en: "North",   lat: -6.150, lng: 106.925 },
  { key: "Barat",   id: "Barat",   en: "West",    lat: -6.195, lng: 106.765 },
  { key: "Pusat",   id: "Pusat",   en: "Central", lat: -6.163, lng: 106.858 },
  { key: "Selatan", id: "Selatan", en: "South",   lat: -6.290, lng: 106.800 },
  { key: "Timur",   id: "Timur",   en: "East",    lat: -6.250, lng: 106.915 },
];

export const WEATHER_REFRESH_MS = 15 * 60 * 1000;

const FIELDS = [
  "temperature_2m", "apparent_temperature", "relative_humidity_2m", "cloud_cover",
  "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m", "is_day",
];

export function openMeteoUrl(places = WILAYAH) {
  const params = new URLSearchParams({
    latitude: places.map((p) => p.lat).join(","),
    longitude: places.map((p) => p.lng).join(","),
    current: FIELDS.join(","),
    timezone: "Asia/Jakarta",
  });
  return `https://api.open-meteo.com/v1/forecast?${params}`;
}

/** Open-Meteo's answer (one object per place, or one object for one place) → { [key]: weather }. */
export function parseOpenMeteo(data, places = WILAYAH) {
  const list = Array.isArray(data) ? data : [data];
  const out = {};
  places.forEach((p, i) => {
    const c = list[i]?.current;
    if (!c) return;
    out[p.key] = {
      code: c.weather_code ?? 0,
      cloud: c.cloud_cover ?? 0,
      rainMm: c.precipitation ?? 0,
      tempC: c.temperature_2m ?? null,
      feelsC: c.apparent_temperature ?? null,
      humidity: c.relative_humidity_2m ?? null,
      windKmh: c.wind_speed_10m ?? 0,
      windFrom: c.wind_direction_10m ?? 0,
      isDay: c.is_day !== 0,
      time: c.time,
    };
  });
  return out;
}

export async function fetchWilayahWeather(signal) {
  const res = await fetch(openMeteoUrl(), { signal });
  if (!res.ok) throw new Error(`Open-Meteo ${res.status}`);
  return parseOpenMeteo(await res.json());
}

// The eight states the map draws, mildest first; each has its own colour,
// picture and motion. `wet` states count as rain.
export const KINDS = {
  clear:   { id: "Cerah",            en: "Clear",          wet: false },
  partly:  { id: "Berawan sebagian", en: "Partly cloudy",  wet: false },
  cloudy:  { id: "Berawan",          en: "Cloudy",         wet: false },
  fog:     { id: "Berkabut",         en: "Foggy",          wet: false },
  drizzle: { id: "Gerimis",          en: "Drizzle",        wet: true },
  rain:    { id: "Hujan",            en: "Rain",           wet: true },
  heavy:   { id: "Hujan lebat",      en: "Heavy rain",     wet: true },
  storm:   { id: "Hujan petir",      en: "Thunderstorm",   wet: true },
};

/** The state for a WMO weather code, with cloud cover deciding between clear, partly cloudy and cloudy. */
export function weatherKind(w) {
  const code = w?.code ?? 0;
  if (code >= 95) return "storm";
  if ([65, 67, 82].includes(code)) return "heavy";
  if ([61, 63, 66, 80, 81].includes(code)) return "rain";
  if (code >= 51 && code <= 57) return "drizzle";
  if (code === 45 || code === 48) return "fog";
  if (code === 3 || (w.cloud ?? 0) >= 70) return "cloudy";
  if (code === 2 || (w.cloud ?? 0) >= 30) return "partly";
  return "clear";
}

const num = (v, lang, digits = 0) => v.toLocaleString(lang === "en" ? "en-US" : "id-ID", { maximumFractionDigits: digits });

/**
 * What to draw and say for one kota: `kind` (a KINDS key), `cloud` 0..1,
 * a short `text` ("Hujan 1,2 mm"), and `temp` ("29°") when known.
 */
export function describeWeather(w, lang = "id") {
  if (!w) return null;
  const kind = weatherKind(w);
  const name = KINDS[kind][lang === "en" ? "en" : "id"];
  const rain = KINDS[kind].wet && w.rainMm > 0 ? ` ${num(w.rainMm, lang, 1)} mm` : "";
  return {
    kind,
    isDay: w.isDay !== false,
    cloud: Math.min(1, Math.max(0, (w.cloud ?? 0) / 100)),
    text: name + rain,
    temp: w.tempC == null ? null : `${num(w.tempC, lang)}°`,
  };
}

/**
 * Where the clouds should drift: the direction the wind blows TO (Open-Meteo
 * gives where it comes FROM), as a step on the 8-point compass {dx, dy} in
 * screen units (east +x, south +y), and how fast (seconds per pattern tile,
 * slower for light wind). The average over the given kota.
 */
export function cloudDrift(weathers = []) {
  const list = weathers.filter((w) => w && Number.isFinite(w.windFrom));
  if (!list.length) return { dx: 1, dy: 0, seconds: 80 };
  let x = 0;
  let y = 0;
  let speed = 0;
  for (const w of list) {
    const to = ((w.windFrom + 180) * Math.PI) / 180;
    x += Math.sin(to);
    y -= Math.cos(to);
    speed += w.windKmh ?? 0;
  }
  speed /= list.length;
  const step = Math.round(Math.atan2(y, x) / (Math.PI / 4)) * (Math.PI / 4);
  // x and y are already screen directions (y grows southwards).
  const dx = Math.round(Math.cos(step));
  const dy = Math.round(Math.sin(step));
  // 0 km/h → 110 s per tile, 30+ km/h → 35 s: always calm, never racing.
  const seconds = Math.round(110 - Math.min(30, speed) * 2.5);
  return { dx: dx || 0, dy: dy || 0, seconds };
}
