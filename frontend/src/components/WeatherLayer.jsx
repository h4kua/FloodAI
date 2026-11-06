/* ── Weather per wilayah on the home map ──────────────────────────────────
   Each kota is tinted by its weather (nine states, from warm clear to indigo
   thunderstorm) and carries a slow, layered texture: a breathing sun glow or
   stars at night, clouds that drift with the live wind (a faint far layer and
   a nearer one), mist bands, rain in two depths, a soft lightning glow. A
   small glass card names the kota, its temperature and weather in the same
   words as the "Weather now by area" cards (both read the backend's
   OpenWeather data); tapping it opens those cards under the map. Everything
   holds still for people who ask their system for reduced motion, and pauses
   while the map is off screen. The tints and textures take no clicks, so the
   posts stay clickable.
*/
import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { Marker, Pane, Polygon } from "react-leaflet";
import wilayahShapes from "../data/wilayahShapes.json";
import { KINDS, WILAYAH, cloudDrift, describeWeather } from "../lib/wilayahWeather";

// Tint per state: [colour, opacity on the light basemap, opacity on the dark one].
const TINT = {
  clear:   ["#fbbf24", 0.10, 0.04],  // warmth comes mostly from the glow texture; more turned muddy on dark
  night:   ["#6366f1", 0.08, 0.12],
  partly:  ["#94a3b8", 0.16, 0.10],
  cloudy:  ["#64748b", 0.30, 0.20],
  fog:     ["#e2e8f0", 0.38, 0.18],
  drizzle: ["#60a5fa", 0.26, 0.24],
  light:   ["#60a5fa", 0.30, 0.28],
  rain:    ["#3b82f6", 0.36, 0.34],
  heavy:   ["#1d4ed8", 0.46, 0.44],
  storm:   ["#4338ca", 0.50, 0.48],
};
// Light-grey clouds on the dark basemap, where dark grey vanished.
const DARK_SWAP = { partly: "#cbd5e1", cloudy: "#cbd5e1" };

export function tintOf(kind, isDay = true, dark = false) {
  const key = kind === "clear" && !isDay ? "night" : kind;
  const [color, light, darkOpacity] = TINT[key] ?? TINT.cloudy;
  return { color: (dark && DARK_SWAP[key]) || color, opacity: dark ? darkOpacity : light };
}

// Texture layers per state, back to front (each a pattern below, or the flash).
const LAYERS = {
  clear:   ["sun"],
  night:   ["stars"],
  partly:  ["cloud-near-sparse"],
  cloudy:  ["cloud-far", "cloud-near"],
  fog:     ["fog"],
  drizzle: ["cloud-far", "drizzle"],
  light:   ["rain-far", "drizzle"],
  rain:    ["rain-far", "rain"],
  heavy:   ["rain-far", "heavy"],
  storm:   ["rain-far", "heavy", "flash"],
};
// Phones draw only the front texture of each state: every animated layer is a
// repaint of most of the map, every frame.
const compactScreen = () => {
  try { return window.matchMedia("(max-width: 640px)").matches; } catch { return false; }
};
const layersOf = (info, compact) => {
  const list = LAYERS[info.kind === "clear" && !info.isDay ? "night" : info.kind];
  return compact ? list.slice(-1) : list;
};

const reducedMotion = () => {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
};

/* ── Small pictures (inline SVG, gradients from <WeatherPatterns>) ── */
const CLOUD_PATH = "M10 21a6 6 0 0 1-.6-12 8 8 0 0 1 15.2-1.6A6.5 6.5 0 1 1 25 21z";
const cloud = (fill = "url(#wx-g-cloud)") => `<path d="${CLOUD_PATH}" fill="${fill}" stroke="rgba(15,23,42,.22)" stroke-width=".8"/>`;
const drops = (n, x0 = 11, span = 12) => Array.from({ length: n }, (_, i) => {
  const x = x0 + (n > 1 ? (i * span) / (n - 1) : span / 2);
  return `<line class="wx-drop" style="animation-delay:-${(i * 0.23).toFixed(2)}s" x1="${x}" y1="23" x2="${x - 1.4}" y2="27" stroke="#93c5fd" stroke-width="1.8" stroke-linecap="round"/>`;
}).join("");
const rays = (cx, cy, r1, r2) => `<g class="wx-rays" style="transform-origin:${cx}px ${cy}px" stroke="#f59e0b" stroke-width="1.5" stroke-linecap="round">${
  [0, 45, 90, 135, 180, 225, 270, 315].map((a) => {
    const t = (a * Math.PI) / 180;
    return `<line x1="${(cx + Math.cos(t) * r1).toFixed(1)}" y1="${(cy + Math.sin(t) * r1).toFixed(1)}" x2="${(cx + Math.cos(t) * r2).toFixed(1)}" y2="${(cy + Math.sin(t) * r2).toFixed(1)}"/>`;
  }).join("")}</g>`;
const ART = {
  clear: `<circle cx="17" cy="14" r="6.5" fill="url(#wx-g-sun)"/>${rays(17, 14, 9, 12)}`,
  night: '<path d="M21 5.5a8.5 8.5 0 1 0 6.5 12.6A7 7 0 0 1 21 5.5z" fill="url(#wx-g-moon)"/>',
  partly: `<circle cx="12" cy="10" r="5.5" fill="url(#wx-g-sun)"/>${rays(12, 10, 7.5, 9.8)}<g class="wx-bob">${cloud()}</g>`,
  cloudy: `<g class="wx-bob">${cloud()}</g>`,
  fog: `<g class="wx-bob">${cloud()}</g><g class="wx-mist" stroke="#cbd5e1" stroke-width="1.6" stroke-linecap="round"><line x1="6" y1="24" x2="24" y2="24"/><line x1="10" y1="27" x2="29" y2="27"/></g>`,
  drizzle: `<g class="wx-bob">${cloud("url(#wx-g-raincloud)")}</g>${drops(2, 12, 9)}`,
  light: `<g class="wx-bob">${cloud("url(#wx-g-raincloud)")}</g>${drops(3)}`,
  rain: `<g class="wx-bob">${cloud("url(#wx-g-raincloud)")}</g>${drops(4, 10, 14)}`,
  heavy: `<g class="wx-bob">${cloud("url(#wx-g-stormcloud)")}</g>${drops(5, 9, 16)}`,
  storm: `<g class="wx-bob">${cloud("url(#wx-g-stormcloud)")}</g><path class="wx-bolt" d="M18 18l-4 6h3l-2 5 6-7h-3l2-4z" fill="url(#wx-g-bolt)"/>${drops(2, 10, 14)}`,
};
export const weatherPicture = (kind, isDay = true, size = 34) =>
  `<svg width="${size}" height="${Math.round(size * 0.85)}" viewBox="0 0 34 29" aria-hidden="true">${ART[kind === "clear" && !isDay ? "night" : kind] ?? ART.cloudy}</svg>`;

/**
 * Gradients for the pictures and the moving textures, referenced as
 * url(#wx-…) by the weather layers. Rendered once next to the map; every loop
 * moves by exactly one pattern tile, so it never jumps.
 */
export function WeatherPatterns({ weather = {} }) {
  const svgRef = useRef(null);
  const still = useMemo(reducedMotion, []);
  const drift = useMemo(() => cloudDrift(Object.values(weather)), [weather]);

  // Pause every loop while the map is scrolled out of view.
  useEffect(() => {
    const svg = svgRef.current;
    const box = svg?.parentElement;
    if (!svg || !box || typeof IntersectionObserver === "undefined") return undefined;
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) svg.unpauseAnimations?.(); else svg.pauseAnimations?.();
    });
    io.observe(box);
    return () => io.disconnect();
  }, []);

  const move = (w, h, dx, dy, seconds) => (still ? null : (
    <animateTransform attributeName="patternTransform" type="translate" from="0 0"
      to={`${dx * w} ${dy * h}`} dur={`${seconds}s`} repeatCount="indefinite" />
  ));
  const breathe = (values, seconds) => (still ? null : (
    <animate attributeName="opacity" values={values} dur={`${seconds}s`} repeatCount="indefinite" calcMode="spline"
      keySplines="0.45 0 0.55 1;0.45 0 0.55 1" keyTimes="0;0.5;1" />
  ));
  // Streaks with varied length and strength look like rain, not a grid.
  const streaks = (list, opacity, width) => (
    <g stroke="#ffffff" strokeWidth={width} strokeLinecap="round">
      {list.map(([x, y, len, o], i) => (
        <line key={i} x1={x} y1={y} x2={x - len * 0.28} y2={y + len} strokeOpacity={opacity * o} />
      ))}
    </g>
  );
  const puffs = (list, opacity) => (
    <g fill="#ffffff" fillOpacity={opacity} filter="url(#wx-blur)">
      {list.map(([cx, cy, rx, ry], i) => <ellipse key={i} cx={cx} cy={cy} rx={rx} ry={ry} />)}
    </g>
  );
  const { dx, dy, seconds } = drift;

  return (
    <svg ref={svgRef} width="0" height="0" style={{ position: "absolute" }} aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="wx-g-sun"><stop offset="0" stopColor="#fde68a" /><stop offset="1" stopColor="#f59e0b" /></radialGradient>
        <linearGradient id="wx-g-moon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#eef2ff" /><stop offset="1" stopColor="#a5b4fc" /></linearGradient>
        <linearGradient id="wx-g-cloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffffff" /><stop offset="1" stopColor="#dbe3ee" /></linearGradient>
        <linearGradient id="wx-g-raincloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#e2e8f0" /><stop offset="1" stopColor="#94a3b8" /></linearGradient>
        <linearGradient id="wx-g-stormcloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#94a3b8" /><stop offset="1" stopColor="#475569" /></linearGradient>
        <linearGradient id="wx-g-bolt" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fef08a" /><stop offset="1" stopColor="#f59e0b" /></linearGradient>
        <filter id="wx-blur" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="10" /></filter>
        <radialGradient id="wx-g-glow"><stop offset="0" stopColor="#fff7d6" stopOpacity="0.9" /><stop offset="1" stopColor="#fff7d6" stopOpacity="0" /></radialGradient>

        {/* Clear day: warm light that slowly breathes */}
        <pattern id="wx-p-sun" width="420" height="320" patternUnits="userSpaceOnUse">
          <g opacity="0.35">
            <circle cx="120" cy="90" r="110" fill="url(#wx-g-glow)" />
            <circle cx="330" cy="240" r="80" fill="url(#wx-g-glow)" />
            {breathe("0.25;0.55;0.25", 9)}
          </g>
        </pattern>
        {/* Clear night: a few stars that twinkle out of step */}
        <pattern id="wx-p-stars" width="160" height="140" patternUnits="userSpaceOnUse">
          {[[20, 30, 1.1, 3.1], [90, 18, 0.8, 4.3], [130, 76, 1.2, 5.2], [52, 104, 0.9, 3.7], [110, 128, 0.7, 4.9]].map(([cx, cy, r, s], i) => (
            <circle key={i} cx={cx} cy={cy} r={r} fill="#e0e7ff" opacity="0.6">
              {still ? null : <animate attributeName="opacity" values="0.2;0.85;0.2" dur={`${s}s`} repeatCount="indefinite" />}
            </circle>
          ))}
        </pattern>
        {/* Clouds, drifting where the live wind blows: a faint, slow far layer and a nearer one */}
        <pattern id="wx-p-cloud-far" width="300" height="200" patternUnits="userSpaceOnUse">
          {puffs([[70, 60, 46, 16], [210, 150, 56, 18], [250, 40, 30, 11]], 0.16)}
          {move(300, 200, dx, dy, Math.round(seconds * 1.6))}
        </pattern>
        <pattern id="wx-p-cloud-near" width="380" height="260" patternUnits="userSpaceOnUse">
          {puffs([[90, 70, 62, 22], [120, 60, 36, 18], [270, 190, 72, 24], [300, 178, 40, 18]], 0.3)}
          {move(380, 260, dx, dy, seconds)}
        </pattern>
        <pattern id="wx-p-cloud-near-sparse" width="460" height="320" patternUnits="userSpaceOnUse">
          {puffs([[110, 90, 58, 20], [140, 80, 32, 16], [340, 240, 50, 18]], 0.26)}
          {move(460, 320, dx, dy, seconds)}
        </pattern>
        {/* Fog: long soft bands sliding sideways */}
        <pattern id="wx-p-fog" width="560" height="110" patternUnits="userSpaceOnUse">
          {puffs([[150, 30, 140, 9], [420, 80, 150, 10]], 0.4)}
          {move(560, 110, 1, 0, 120)}
        </pattern>
        {/* Rain in two depths: far streaks are thin and slow, near ones longer */}
        <pattern id="wx-p-rain-far" width="34" height="46" patternUnits="userSpaceOnUse">
          {streaks([[8, 4, 7, 1], [26, 26, 6, 0.8]], 0.32, 1)}
          {move(34, 46, 0, 1, 2.4)}
        </pattern>
        <pattern id="wx-p-drizzle" width="46" height="56" patternUnits="userSpaceOnUse">
          {streaks([[12, 6, 5, 1], [36, 32, 4, 0.8]], 0.45, 1.1)}
          {move(46, 56, 0, 1, 2.2)}
        </pattern>
        <pattern id="wx-p-rain" width="38" height="52" patternUnits="userSpaceOnUse">
          {streaks([[9, 2, 11, 1], [27, 18, 9, 0.75], [19, 36, 10, 0.9]], 0.45, 1.2)}
          {move(38, 52, 0, 1, 1.25)}
        </pattern>
        <pattern id="wx-p-heavy" width="30" height="44" patternUnits="userSpaceOnUse">
          {streaks([[6, 0, 13, 1], [21, 10, 12, 0.85], [14, 24, 13, 0.95], [27, 32, 10, 0.7]], 0.5, 1.3)}
          {move(30, 44, 0, 1, 0.85)}
        </pattern>
      </defs>
    </svg>
  );
}

const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

/**
 * One kota's card. Tapping it (or Tab, then Enter: Leaflet makes it focusable)
 * calls onPick; the details sit under the map, not in a popup over it. Leaflet
 * sets the title only once, so later titles are written here.
 */
function WeatherCard({ position, icon, title, onPick }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    ref.current.options.title = title;  // used again when a new icon is set
    ref.current.getElement()?.setAttribute("title", title);
  }, [title]);
  return <Marker ref={ref} position={position} icon={icon} title={title} eventHandlers={{ click: onPick }} />;
}

/**
 * The tints and textures sit in a pane between the basemap (200) and the flood
 * areas and posts (400); the cards in one above (450), so they can be tapped.
 */
export default function WeatherLayer({ weather = {}, lang = "id", theme = "light", onPick, picked = null }) {
  const dark = theme === "dark";
  const en = lang === "en";
  const items = useMemo(() => WILAYAH.map((w) => ({ ...w, info: describeWeather(weather[w.key], lang) })), [weather, lang]);
  const compact = useMemo(compactScreen, []);

  const areas = items.flatMap(({ key, info }) => {
    if (!info) return [];
    const positions = wilayahShapes[key] || [];
    const tint = tintOf(info.kind, info.isDay, dark);
    return [
      <Polygon key={`wx-area-${key}`} positions={positions} interactive={false}
        pathOptions={{ color: "#ffffff", weight: 1.2, opacity: dark ? 0.35 : 0.75, fillColor: tint.color, fillOpacity: tint.opacity }} />,
      // Leaflet sets a class only once, so the texture is part of the key: a
      // change of weather at the 15-minute refresh makes new layers.
      // The pattern goes in the fill attribute, which resolves in the page. In the
      // production stylesheet (an external file) fill: url(#…) was looked up in
      // that file, found nothing, and Leaflet's default solid blue showed.
      ...layersOf(info, compact).map((layer) => (
        <Polygon key={`wx-${layer}-${key}`} positions={positions} interactive={false}
          pathOptions={layer === "flash"
            ? { stroke: false, fillColor: "#e0e7ff", fillOpacity: 0, className: "wx-t wx-t-flash" }
            : { stroke: false, fillColor: `url(#wx-p-${layer})`, fillOpacity: 1, className: "wx-t" }} />
      )),
    ];
  });

  const cards = items.flatMap(({ key, name: wilayah, id, en: enName, lat, lng, info }) => {
    if (!info) return [];
    const name = en ? enName : id;
    const icon = L.divIcon({
      className: "wx-marker",
      html: `<div class="wx-card wx-k-${info.kind}${picked === wilayah ? " is-picked" : ""}">`
        + `<span class="wx-ico">${weatherPicture(info.kind, info.isDay)}</span>`
        + `<span class="wx-txt"><b>${escapeHtml(name)}</b><small>${info.temp ? `${escapeHtml(info.temp)} · ` : ""}${escapeHtml(info.text)}</small></span></div>`,
      iconSize: [0, 0],
    });
    const fullName = en ? `${enName} Jakarta` : `Jakarta ${id}`;
    return [
      <WeatherCard key={`wx-card-${key}`} position={[lat, lng]} icon={icon} onPick={() => onPick?.(wilayah)}
        title={`${fullName}: ${info.temp ? `${info.temp}, ` : ""}${info.text}${en ? " (details below the map)" : " (detail di bawah peta)"}`} />,
    ];
  });

  return (
    <>
      <Pane name="weather" style={{ zIndex: 350, pointerEvents: "none" }}>{areas}</Pane>
      <Pane name="weather-cards" style={{ zIndex: 450 }}>{cards}</Pane>
    </>
  );
}

/** The states on the map right now, for the legend: [{ id, name, color }]. */
export function weatherKey(weather = {}, lang = "id", dark = false) {
  const seen = new Map();
  for (const w of WILAYAH) {
    const info = describeWeather(weather[w.key], lang);
    if (!info) continue;
    const id = info.kind === "clear" && !info.isDay ? "night" : info.kind;
    if (!seen.has(id)) {
      const name = id === "night" ? (lang === "en" ? "Clear night" : "Cerah (malam)") : KINDS[info.kind][lang === "en" ? "en" : "id"];
      seen.set(id, { id, name, color: tintOf(info.kind, info.isDay, dark).color });
    }
  }
  return [...seen.values()];
}
