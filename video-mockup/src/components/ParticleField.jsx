import React from "react";
import { T } from "../tokens";

// Deterministic particle positions using golden-ratio seed
const SEEDS = Array.from({ length: 55 }, (_, i) => {
  const g = (i * 137.5085) % 1920;
  return {
    x: g,
    speedFactor: 0.18 + ((i * 73.91) % 0.38),
    size: 1 + ((i * 17.23) % 2.2),
    phase: (i * 2.618) % (Math.PI * 2),
    cyan: i % 3 !== 2,
  };
});

export function ParticleField({ frame, opacity = 0.32 }) {
  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity, overflow: "hidden" }}>
      {SEEDS.map((p, i) => {
        const y = (frame * p.speedFactor * 28 + p.x * 0.55) % 1140;
        const alpha = 0.22 + Math.abs(Math.sin(frame * 0.042 + p.phase)) * 0.38;
        return (
          <div key={i} style={{
            position: "absolute",
            left: p.x,
            top: y % 1080,
            width: p.size,
            height: p.size * 3.5,
            borderRadius: 1,
            background: p.cyan ? T.cyan : "rgba(129,140,248,0.7)",
            opacity: alpha,
          }} />
        );
      })}
    </div>
  );
}
