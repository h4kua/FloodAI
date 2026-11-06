/* ── Weather per wilayah for the home map ─────────────────────────────────
   Current cloud cover, rain and weather code for each of the five mainland
   kota from Open-Meteo (free, no key, 15-minute data). This is a weather
   model's estimate on a grid of a few km, not a radar reading: neighbouring
   kota can show the same values.
*/

// Where each kota's weather is read and its label drawn: inside the kota,
// away from the clusters of water-level posts.
export const WILAYAH = [
  { key: "Utara",   id: "Utara",   en: "North",   lat: -6.150, lng: 106.925 },
  { key: "Barat",   id: "Barat",   en: "West",    lat: -6.160, lng: 106.705 },
  { key: "Pusat",   id: "Pusat",   en: "Central", lat: -6.163, lng: 106.858 },
  { key: "Selatan", id: "Selatan", en: "South",   lat: -6.290, lng: 106.800 },
  { key: "Timur",   id: "Timur",   en: "East",    lat: -6.250, lng: 106.915 },
];

export const WEATHER_REFRESH_MS = 15 * 60 * 1000;

export function openMeteoUrl(places = WILAYAH) {
  const params = new URLSearchParams({
    latitude: places.map((p) => p.lat).join(","),
    longitude: places.map((p) => p.lng).join(","),
    current: "cloud_cover,precipitation,weather_code",
    timezone: "Asia/Jakarta",
  });
  return `https://api.open-meteo.com/v1/forecast?${params}`;
}

/** Open-Meteo's answer (one object per place, or one object for one place) → { [key]: {cloud, rainMm, code, time} }. */
export function parseOpenMeteo(data, places = WILAYAH) {
  const list = Array.isArray(data) ? data : [data];
  const out = {};
  places.forEach((p, i) => {
    const c = list[i]?.current;
    if (!c) return;
    out[p.key] = { cloud: c.cloud_cover ?? 0, rainMm: c.precipitation ?? 0, code: c.weather_code ?? 0, time: c.time };
  });
  return out;
}

export async function fetchWilayahWeather(signal) {
  const res = await fetch(openMeteoUrl(), { signal });
  if (!res.ok) throw new Error(`Open-Meteo ${res.status}`);
  return parseOpenMeteo(await res.json());
}

const TEXT = {
  clear:   ["Cerah", "Clear"],
  partly:  ["Berawan sebagian", "Partly cloudy"],
  cloudy:  ["Berawan", "Cloudy"],
  fog:     ["Berkabut", "Foggy"],
  drizzle: ["Gerimis", "Drizzle"],
  rain:    ["Hujan ringan", "Light rain"],
  rain2:   ["Hujan sedang", "Moderate rain"],
  heavy:   ["Hujan lebat", "Heavy rain"],
  storm:   ["Hujan petir", "Thunderstorm"],
};

/**
 * What to draw and say for one kota's weather (WMO weather codes):
 * `kind` is clear | cloudy | rain | heavy, `cloud` 0..1 sets how thick the haze is.
 */
export function describeWeather(w, lang = "id") {
  if (!w) return null;
  const code = w.code ?? 0;
  let word;
  let kind;
  if (code >= 95) { word = "storm"; kind = "heavy"; }
  else if ([65, 67, 82].includes(code)) { word = "heavy"; kind = "heavy"; }
  else if ([63, 81].includes(code)) { word = "rain2"; kind = "rain"; }
  else if ([61, 66, 80].includes(code)) { word = "rain"; kind = "rain"; }
  else if (code >= 51 && code <= 57) { word = "drizzle"; kind = "rain"; }
  else if (code === 45 || code === 48) { word = "fog"; kind = "cloudy"; }
  else if (code === 3 || w.cloud >= 70) { word = "cloudy"; kind = "cloudy"; }
  else if (code === 2 || w.cloud >= 30) { word = "partly"; kind = "cloudy"; }
  else { word = "clear"; kind = "clear"; }
  const text = TEXT[word][lang === "en" ? 1 : 0];
  const rain = w.rainMm > 0 ? ` ${w.rainMm.toLocaleString(lang === "en" ? "en-US" : "id-ID")} mm` : "";
  return { kind, word, cloud: Math.min(1, Math.max(0, (w.cloud ?? 0) / 100)), text: text + rain };
}
