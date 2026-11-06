/* ── Weather per wilayah on the home map ──────────────────────────────────
   Each kota is filled with its weather's colour (grey cloud, blue rain, deep
   blue heavy rain; clear stays uncoloured) and gets a small picture (sun,
   cloud, cloud with rain) with a label such as "Barat · Berawan".
   Moving texture on top: rain streaks fall in rainy kota, soft clouds drift
   over cloudy ones (SVG patterns in <WeatherPatterns>, still for people who
   ask their system for reduced motion).
   Nothing here takes clicks, so the posts under it stay clickable.
*/
import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import { Marker, Pane, Polygon } from "react-leaflet";
import wilayahShapes from "../data/wilayahShapes.json";
import { WEATHER_REFRESH_MS, WILAYAH, describeWeather, fetchWilayahWeather } from "../lib/wilayahWeather";

export const WEATHER_FILL = { cloudy: "#64748b", rain: "#3b82f6", heavy: "#1e40af" };
// On the dark basemap a dark grey vanished, so clouds there are a light grey.
const CLOUD_DARK = "#cbd5e1";
// Grey thickens with the cloud cover (30 % → 0.31, 100 % → 0.45); rain is a fixed, stronger blue.
const fillOpacity = (info, dark) => (info.kind === "cloudy"
  ? (dark ? 0.12 + 0.18 * info.cloud : 0.25 + 0.2 * info.cloud)
  : info.kind === "rain" ? 0.42 : 0.52);

const CLOUD = '<path d="M13 22h20a6.5 6.5 0 0 0 .6-13A9 9 0 0 0 16.3 8 7 7 0 0 0 13 22z" fill="#fff" fill-opacity="0.95" stroke="#7b8698" stroke-width="1.4"/>';
const DROPS = (n) => Array.from({ length: n }, (_, i) => {
  const x = 15 + i * (16 / Math.max(1, n - 1));
  return `<line class="wx-d" style="animation-delay:-${(i * 0.27).toFixed(2)}s" x1="${x}" y1="25" x2="${x - 2}" y2="31" stroke="#ffffff" stroke-width="2" stroke-linecap="round"/>`;
}).join("");
const SUN = '<circle cx="23" cy="16" r="6" fill="#f59e0b"/><g class="wx-rays" stroke="#f59e0b" stroke-width="1.6" stroke-linecap="round">'
  + [0, 45, 90, 135, 180, 225, 270, 315].map((a) => {
    const r = (a * Math.PI) / 180;
    return `<line x1="${23 + Math.cos(r) * 8.5}" y1="${16 + Math.sin(r) * 8.5}" x2="${23 + Math.cos(r) * 11}" y2="${16 + Math.sin(r) * 11}"/>`;
  }).join("") + "</g>";

function picture(kind) {
  const art = kind === "clear" ? SUN : kind === "rain" ? CLOUD + DROPS(3) : kind === "heavy" ? CLOUD + DROPS(5) : CLOUD;
  return `<svg width="46" height="34" viewBox="0 0 46 34" aria-hidden="true">${art}</svg>`;
}

const reducedMotion = () => {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
};

/**
 * The moving textures, referenced by the weather polygons as url(#wx-…).
 * Rendered once next to the map; the loops are seamless because each one
 * moves by exactly one pattern tile.
 */
export function WeatherPatterns() {
  const still = useMemo(reducedMotion, []);
  const move = (to, dur) => (still ? null : (
    <animateTransform attributeName="patternTransform" type="translate" from="0 0" to={to} dur={dur} repeatCount="indefinite" />
  ));
  const streak = (x, y, len = 9) => <line key={`${x}-${y}`} x1={x} y1={y} x2={x - len / 3} y2={y + len} />;
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
      <defs>
        <filter id="wx-blur" x="-20%" y="-40%" width="140%" height="180%"><feGaussianBlur stdDeviation="9" /></filter>
        <pattern id="wx-drizzle" width="40" height="40" patternUnits="userSpaceOnUse">
          <g stroke="#ffffff" strokeOpacity="0.45" strokeWidth="1.2" strokeLinecap="round">
            {[streak(10, 4, 5), streak(30, 24, 5)]}
          </g>
          {move("0 40", "1.4s")}
        </pattern>
        <pattern id="wx-rain" width="28" height="28" patternUnits="userSpaceOnUse">
          <g stroke="#ffffff" strokeOpacity="0.55" strokeWidth="1.3" strokeLinecap="round">
            {[streak(8, 1), streak(22, 12), streak(14, 18, 7)]}
          </g>
          {move("0 28", "0.7s")}
        </pattern>
        <pattern id="wx-rain-heavy" width="18" height="18" patternUnits="userSpaceOnUse">
          <g stroke="#ffffff" strokeOpacity="0.7" strokeWidth="1.5" strokeLinecap="round">
            {[streak(5, 0, 8), streak(14, 6, 9), streak(9, 10, 6)]}
          </g>
          {move("0 18", "0.42s")}
        </pattern>
        <pattern id="wx-cloud" width="260" height="170" patternUnits="userSpaceOnUse">
          <g fill="#ffffff" fillOpacity="0.3" filter="url(#wx-blur)">
            <ellipse cx="62" cy="52" rx="38" ry="16" />
            <ellipse cx="82" cy="44" rx="24" ry="14" />
            <ellipse cx="178" cy="118" rx="52" ry="18" />
            <ellipse cx="200" cy="108" rx="28" ry="15" />
          </g>
          {move("260 0", "70s")}
        </pattern>
      </defs>
    </svg>
  );
}

const TEXTURE = { cloudy: "wx-anim-cloud", rain: "wx-anim-rain", heavy: "wx-anim-heavy" };
// Drizzle is drawn sparser and slower than rain, so the strength shows.
const texture = (info) => (info.word === "drizzle" ? "wx-anim-drizzle" : TEXTURE[info.kind]);

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
export default function WeatherLayer({ weather = {}, lang = "id", theme = "light" }) {
  const dark = theme === "dark";
  const isEn = lang === "en";
  const items = useMemo(() => WILAYAH.map((w) => ({ ...w, info: describeWeather(weather[w.key], lang) })), [weather, lang]);
  return <Pane name="weather" style={{ zIndex: 350, pointerEvents: "none" }}>{items.flatMap(({ key, id, en, lat, lng, info }) => {
    if (!info) return [];
    const layers = [];
    if (info.kind !== "clear") {
      layers.push(
        <Polygon key={`wx-area-${key}`} positions={wilayahShapes[key] || []} interactive={false}
          pathOptions={{ color: "#ffffff", weight: 1.5, opacity: 0.7, fillColor: dark && info.kind === "cloudy" ? CLOUD_DARK : WEATHER_FILL[info.kind], fillOpacity: fillOpacity(info, dark) }} />,
        // Same outline again, filled with the moving texture (fill set in CSS). Leaflet
        // sets a class only once, so a change of texture makes a new layer.
        <Polygon key={`wx-move-${key}-${texture(info)}`} positions={wilayahShapes[key] || []} interactive={false}
          pathOptions={{ stroke: false, fillOpacity: 1, className: texture(info) }} />,
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
