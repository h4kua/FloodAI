/* ── Weather per wilayah for the home map ─────────────────────────────────
   The same OpenWeather readings the backend sends for the five mainland kota
   (`openweather_wilayah` in /predict/realtime-native, one point per kota,
   refreshed with the snapshot) and that the "Weather now by area" cards
   show, so the map and the cards always agree. Until 2026-11-06 the map read
   Open-Meteo instead and the two disagreed (Cloudy on the map, Light rain in
   the card).
*/
import { weatherLabel } from "./dashboardHelpers.js";

// Where each kota's label is drawn: inside the kota, away from the clusters of
// water-level posts. `name` is the backend's key.
export const WILAYAH = [
  { key: "Utara",   name: "Jakarta Utara",   id: "Utara",   en: "North",   lat: -6.150, lng: 106.925 },
  { key: "Barat",   name: "Jakarta Barat",   id: "Barat",   en: "West",    lat: -6.195, lng: 106.765 },
  { key: "Pusat",   name: "Jakarta Pusat",   id: "Pusat",   en: "Central", lat: -6.163, lng: 106.858 },
  { key: "Selatan", name: "Jakarta Selatan", id: "Selatan", en: "South",   lat: -6.290, lng: 106.800 },
  { key: "Timur",   name: "Jakarta Timur",   id: "Timur",   en: "East",    lat: -6.250, lng: 106.915 },
];

// The nine states the map draws, mildest first; each has its own colour,
// picture and motion. `wet` states count as rain.
export const KINDS = {
  clear:   { id: "Cerah",            en: "Clear",          wet: false },
  partly:  { id: "Berawan sebagian", en: "Partly cloudy",  wet: false },
  cloudy:  { id: "Berawan",          en: "Cloudy",         wet: false },
  fog:     { id: "Berkabut",         en: "Hazy or foggy",  wet: false },
  drizzle: { id: "Gerimis",          en: "Drizzle",        wet: true },
  light:   { id: "Hujan ringan",     en: "Light rain",     wet: true },
  rain:    { id: "Hujan sedang",     en: "Moderate rain",  wet: true },
  heavy:   { id: "Hujan lebat",      en: "Heavy rain",     wet: true },
  storm:   { id: "Hujan petir",      en: "Thunderstorm",   wet: true },
};

/**
 * The state of one OpenWeather reading ({weather_main, weather_desc, clouds,
 * rainfall_1h}). Rain strength follows the reading's own words first
 * ("hujan ringan", "heavy intensity rain"), then mm per hour (2.5 / 7.6).
 */
export function weatherKind(ow) {
  if (!ow) return null;
  const main = ow.weather_main || "";
  const desc = (ow.weather_desc || "").toLowerCase();
  const mm = ow.rainfall_1h ?? 0;
  if (main === "Thunderstorm" || /petir|thunder/.test(desc)) return "storm";
  if (main === "Drizzle" || /gerimis|drizzle/.test(desc)) return "drizzle";
  if (main === "Rain" || main === "Squall" || mm > 0) {
    if (/lebat|heavy|extreme|ekstrem|sangat/.test(desc) || mm >= 7.6) return "heavy";
    if (/sedang|moderate/.test(desc) || mm >= 2.5) return "rain";
    return "light";
  }
  if (["Mist", "Haze", "Fog", "Smoke", "Dust", "Sand", "Ash"].includes(main)) return "fog";
  if (main === "Clear") return (ow.clouds ?? 0) >= 30 ? "partly" : "clear";
  return (ow.clouds ?? 100) >= 70 ? "cloudy" : "partly";
}

const num = (v, lang, digits = 0) => v.toLocaleString(lang === "en" ? "en-US" : "id-ID", { maximumFractionDigits: digits, minimumFractionDigits: digits });

/**
 * What to draw and say for one kota, in the same words as the
 * "Weather now by area" card: `kind`, `isDay`, `cloud` 0..1, `text`
 * ("Hujan ringan · 0,1 mm/jam") and `temp` ("35°").
 */
export function describeWeather(ow, lang = "id") {
  const kind = weatherKind(ow);
  if (!kind) return null;
  const isId = lang !== "en";
  const label = ow.weather_desc ? weatherLabel(ow.weather_desc, isId) : KINDS[kind][isId ? "id" : "en"];
  const mm = ow.rainfall_1h ?? 0;
  return {
    kind,
    isDay: !String(ow.weather_icon || "").endsWith("n"),
    cloud: Math.min(1, Math.max(0, (ow.clouds ?? 0) / 100)),
    text: label + (KINDS[kind].wet && mm > 0 ? ` · ${num(mm, lang, 1)} ${isId ? "mm/jam" : "mm/h"}` : ""),
    temp: ow.temp == null ? null : `${Math.round(ow.temp)}°`,
  };
}

/** {"Jakarta Utara": ow, …} from the backend → {Utara: ow, …} keyed like WILAYAH. */
export function byWilayahKey(openweatherWilayah = {}) {
  const out = {};
  for (const w of WILAYAH) if (openweatherWilayah[w.name]) out[w.key] = openweatherWilayah[w.name];
  return out;
}

/**
 * Where the clouds should drift: the direction the wind blows TO (OpenWeather
 * gives `wind_deg`, where it comes FROM), as a step on the 8-point compass
 * {dx, dy} in screen units (east +x, south +y), and how fast (seconds per
 * pattern tile, slower for light wind; `wind_speed` is in m/s). The average
 * over the given readings.
 */
export function cloudDrift(readings = []) {
  const list = readings.filter((w) => w && Number.isFinite(w.wind_deg));
  if (!list.length) return { dx: 1, dy: 0, seconds: 80 };
  let x = 0;
  let y = 0;
  let speed = 0;
  for (const w of list) {
    const to = ((w.wind_deg + 180) * Math.PI) / 180;
    x += Math.sin(to);
    y -= Math.cos(to);
    speed += (w.wind_speed ?? 0) * 3.6;
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
