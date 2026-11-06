/* ── Weather per wilayah on the home map ──────────────────────────────────
   A thin cloud haze over each kota, as thick as its cloud cover, and a small
   picture (sun, cloud, cloud with rain) with a label such as "Barat · Berawan".
   Nothing here takes clicks, so the posts under it stay clickable.
*/
import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { Marker, Pane, Polygon } from "react-leaflet";
import wilayahShapes from "../data/wilayahShapes.json";
import { WEATHER_REFRESH_MS, WILAYAH, describeWeather, fetchWilayahWeather } from "../lib/wilayahWeather";

const HAZE = { cloudy: "#94a3b8", rain: "#64748b", heavy: "#475569" };
// Haze opacity at 100 % cloud: thin enough that the basemap and status colours show through.
const HAZE_MAX = { cloudy: 0.16, rain: 0.22, heavy: 0.28 };

const CLOUD = '<path d="M13 22h20a6.5 6.5 0 0 0 .6-13A9 9 0 0 0 16.3 8 7 7 0 0 0 13 22z" fill="#fff" fill-opacity="0.95" stroke="#7b8698" stroke-width="1.4"/>';
const DROPS = (n) => Array.from({ length: n }, (_, i) => {
  const x = 15 + i * (16 / Math.max(1, n - 1));
  return `<line x1="${x}" y1="25" x2="${x - 2}" y2="31" stroke="#2563eb" stroke-width="1.8" stroke-linecap="round"/>`;
}).join("");
const SUN = '<circle cx="23" cy="16" r="6" fill="#f59e0b"/><g stroke="#f59e0b" stroke-width="1.6" stroke-linecap="round">'
  + [0, 45, 90, 135, 180, 225, 270, 315].map((a) => {
    const r = (a * Math.PI) / 180;
    return `<line x1="${23 + Math.cos(r) * 8.5}" y1="${16 + Math.sin(r) * 8.5}" x2="${23 + Math.cos(r) * 11}" y2="${16 + Math.sin(r) * 11}"/>`;
  }).join("") + "</g>";

function picture(kind) {
  const art = kind === "clear" ? SUN : kind === "rain" ? CLOUD + DROPS(3) : kind === "heavy" ? CLOUD + DROPS(5) : CLOUD;
  return `<svg width="46" height="34" viewBox="0 0 46 34" aria-hidden="true">${art}</svg>`;
}

const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

/** Fetches the weather for the five kota every 15 minutes; {} until (or unless) it arrives. */
export function useWilayahWeather() {
  const [weather, setWeather] = useState({});
  useEffect(() => {
    let controller = new AbortController();
    const load = () => {
      controller.abort();
      controller = new AbortController();
      fetchWilayahWeather(controller.signal).then(setWeather).catch(() => { /* layer stays as it was */ });
    };
    load();
    const timer = setInterval(load, WEATHER_REFRESH_MS);
    return () => { clearInterval(timer); controller.abort(); };
  }, []);
  return weather;
}

// Its own pane between the basemap (200) and the flood areas and posts (400),
// so weather that arrives late is still drawn under them.
export default function WeatherLayer({ weather = {}, lang = "id" }) {
  const isEn = lang === "en";
  const items = useMemo(() => WILAYAH.map((w) => ({ ...w, info: describeWeather(weather[w.key], lang) })), [weather, lang]);
  return <Pane name="weather" style={{ zIndex: 350, pointerEvents: "none" }}>{items.flatMap(({ key, id, en, lat, lng, info }) => {
    if (!info) return [];
    const layers = [];
    if (info.kind !== "clear") {
      layers.push(
        <Polygon key={`wx-area-${key}`} positions={wilayahShapes[key] || []} interactive={false}
          pathOptions={{ stroke: false, fillColor: HAZE[info.kind], fillOpacity: 0.04 + HAZE_MAX[info.kind] * info.cloud }} />,
      );
    }
    const label = `${isEn ? en : id} · ${info.text}`;
    const icon = L.divIcon({
      className: "wx-marker",
      html: `<div class="wx-badge wx-${info.kind}">${picture(info.kind)}<span>${escapeHtml(label)}</span></div>`,
      iconSize: [0, 0],
    });
    layers.push(<Marker key={`wx-icon-${key}`} position={[lat, lng]} icon={icon} interactive={false} keyboard={false} />);
    return layers;
  })}</Pane>;
}
