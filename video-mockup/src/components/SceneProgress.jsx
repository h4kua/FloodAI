import React from "react";
import { interpolate } from "remotion";
import { T, MONO } from "../tokens";

/**
 * Top-right chapter rail — 6 segments fill as the video advances.
 * Mirrors the frame map in MockupVideo.jsx (21s / 630 frames).
 */
const SCENES = [
  { from: 0,   to: 90,  label: "INTRO"     },
  { from: 90,  to: 165, label: "PLATFORM"  },
  { from: 165, to: 285, label: "DASHBOARD" },
  { from: 285, to: 375, label: "AI CHAT"   },
  { from: 375, to: 450, label: "EVAKUASI"  },
  { from: 450, to: 630, label: "OUTRO"     },
];

export function SceneProgress({ frame }) {
  const railOp = interpolate(frame, [96, 120, 590, 625], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (railOp <= 0) return null;

  const activeIdx = SCENES.findIndex(s => frame >= s.from && frame < s.to);

  return (
    <div style={{
      position: "absolute", top: 30, right: 40,
      display: "flex", alignItems: "center", gap: 7,
      opacity: railOp, zIndex: 90, pointerEvents: "none",
    }}>
      {SCENES.map((s, i) => {
        const isActive = i === activeIdx;
        const fill = interpolate(frame, [s.from, s.to], [0, 100], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
            <div style={{
              width: isActive ? 56 : 26,
              height: 3, borderRadius: 2,
              background: "rgba(139,148,158,0.22)",
              overflow: "hidden",
            }}>
              <div style={{
                width: `${fill}%`, height: "100%",
                background: isActive ? T.cyan : "rgba(56,189,248,0.55)",
                boxShadow: isActive ? `0 0 8px ${T.cyan}` : "none",
                borderRadius: 2,
              }} />
            </div>
            {isActive && (
              <span style={{ fontFamily: MONO, fontSize: 9, color: T.cyan, letterSpacing: "0.16em" }}>
                {String(i + 1).padStart(2, "0")} {s.label}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
