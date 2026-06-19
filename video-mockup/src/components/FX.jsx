import React from "react";
import { interpolate } from "remotion";

/**
 * Cinematic FX toolkit shared by all scenes.
 *  - sceneZoom()  → slow push-in so every cut has motion
 *  - <LightSweep> → diagonal glare passing over a device screen
 *  - <FilmGrain>  → animated noise + scanlines over the whole video
 *  - countUp()    → eased number counter for stats
 */

// Slow Ken Burns push-in: scale 1 → ~1.045 across the scene
export function sceneZoom(frame, durationInFrames, amount = 0.045) {
  return 1 + interpolate(frame, [0, durationInFrames], [0, amount], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

// Eased count-up for hero numbers ("0 → 94")
export function countUp(frame, from, to, start, duration) {
  const t = interpolate(frame, [start, start + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
  return from + (to - from) * eased;
}

// Diagonal light sweep across a screen — place inside an overflow:hidden parent
export function LightSweep({ frame, start, duration = 34, intensity = 0.16 }) {
  const x = interpolate(frame, [start, start + duration], [-65, 165], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const op = interpolate(
    frame,
    [start, start + 6, start + duration - 6, start + duration],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  if (op <= 0) return null;
  return (
    <div style={{
      position: "absolute", inset: 0,
      pointerEvents: "none", zIndex: 50,
      background: `linear-gradient(105deg, transparent ${x - 18}%, rgba(255,255,255,${intensity}) ${x}%, rgba(56,189,248,${intensity * 0.5}) ${x + 7}%, transparent ${x + 18}%)`,
      opacity: op,
      mixBlendMode: "screen",
    }} />
  );
}

// Inline SVG noise tile — generated once, shifted per frame for living grain
const NOISE_SVG = encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="180" height="180" filter="url(#n)" opacity="0.55"/></svg>`,
);

export function FilmGrain({ frame, opacity = 0.05 }) {
  // jump the tile around each frame so the grain "boils"
  const ox = (frame * 47) % 180;
  const oy = (frame * 91) % 180;
  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", zIndex: 200 }}>
      {/* grain */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `url("data:image/svg+xml,${NOISE_SVG}")`,
        backgroundPosition: `${ox}px ${oy}px`,
        opacity,
        mixBlendMode: "overlay",
      }} />
      {/* faint scanlines */}
      <div style={{
        position: "absolute", inset: 0,
        background: "repeating-linear-gradient(0deg, rgba(255,255,255,0.014) 0px, rgba(255,255,255,0.014) 1px, transparent 1px, transparent 4px)",
        opacity: 0.5,
      }} />
      {/* chromatic edge tint */}
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse 120% 100% at 50% 50%, transparent 70%, rgba(56,189,248,0.035) 100%)",
      }} />
    </div>
  );
}

// Quick white flash for impact moments (tagline hits, etc.)
export function ImpactFlash({ frame, at, color = "rgba(190,235,255,1)", peak = 0.5 }) {
  const op = interpolate(frame, [at, at + 2, at + 14], [0, peak, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (op <= 0) return null;
  return (
    <div style={{
      position: "absolute", inset: 0,
      background: `radial-gradient(ellipse 80% 60% at 50% 50%, ${color} 0%, transparent 70%)`,
      opacity: op,
      pointerEvents: "none",
      mixBlendMode: "screen",
      zIndex: 60,
    }} />
  );
}
