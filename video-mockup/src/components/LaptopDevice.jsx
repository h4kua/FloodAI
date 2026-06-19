import React from "react";
import { T, MONO } from "../tokens";

export const LAPTOP_W    = 860;
export const LAPTOP_H    = 540;
export const LAPTOP_BEZEL = 15;

export function LaptopDevice({ children, rotY = 0, floatY = 0, opacity = 1, scale = 1 }) {
  return (
    <div style={{ perspective: 1100, perspectiveOrigin: "50% 42%", display: "inline-flex", flexDirection: "column", alignItems: "center" }}>
      <div style={{ transform: `scale(${scale}) rotateY(${rotY}deg) rotateX(-6deg) translateY(${floatY}px)`, opacity, position: "relative", willChange: "transform" }}>

        {/* ── Screen lid ── */}
        <div style={{
          width: LAPTOP_W, height: LAPTOP_H,
          background: "#05080f",
          borderRadius: "16px 16px 0 0",
          border: "1px solid rgba(56,189,248,0.26)",
          borderBottom: "2px solid rgba(56,189,248,0.06)",
          boxShadow: [
            "0 0 80px rgba(56,189,248,0.13)",
            "0 0 180px rgba(56,189,248,0.05)",
            "0 50px 140px rgba(0,0,0,0.92)",
          ].join(", "),
          position: "relative",
          overflow: "hidden",
          margin: "0 12px",
        }}>
          {/* Camera */}
          <div style={{ position: "absolute", top: 8, left: "50%", transform: "translateX(-50%)", width: 8, height: 8, borderRadius: "50%", background: "#101825", border: "1px solid rgba(56,189,248,0.14)", zIndex: 5 }} />
          {/* Content area */}
          <div style={{ position: "absolute", top: LAPTOP_BEZEL, left: LAPTOP_BEZEL, right: LAPTOP_BEZEL, bottom: LAPTOP_BEZEL, borderRadius: 8, overflow: "hidden", background: "#0d1117" }}>
            {children}
          </div>
          {/* Top-left glare */}
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(118deg, rgba(255,255,255,0.042) 0%, transparent 38%)", pointerEvents: "none", borderRadius: "16px 16px 0 0" }} />
          {/* Cyan inner ring glow */}
          <div style={{ position: "absolute", inset: 0, boxShadow: "0 0 0 1px rgba(56,189,248,0.07) inset, 0 0 50px rgba(56,189,248,0.04) inset", pointerEvents: "none", borderRadius: "16px 16px 0 0" }} />
        </div>

        {/* ── Hinge ── */}
        <div style={{ width: LAPTOP_W, height: 6, background: "linear-gradient(0deg, #0f1625, #1c2540)", borderLeft: "1px solid rgba(56,189,248,0.09)", borderRight: "1px solid rgba(56,189,248,0.09)", margin: "0 12px" }} />

        {/* ── Base / keyboard ── */}
        <div style={{
          width: LAPTOP_W + 28, height: 44,
          background: "linear-gradient(180deg, #0d1424 0%, #07090f 100%)",
          borderRadius: "0 0 16px 16px",
          border: "1px solid rgba(48,54,61,0.65)",
          borderTop: "none",
          boxShadow: "0 24px 90px rgba(0,0,0,0.95)",
          position: "relative", overflow: "hidden",
        }}>
          {/* Keyboard rows */}
          {[0,1,2].map(i => <div key={i} style={{ position: "absolute", top: 4+i*11, left: 24, right: 90, height: 8, borderRadius: 2, background: "rgba(56,189,248,0.012)", border: "1px solid rgba(56,189,248,0.035)" }} />)}
          {/* Trackpad */}
          <div style={{ position: "absolute", bottom: 6, left: "50%", transform: "translateX(-50%)", width: 100, height: 18, borderRadius: 5, border: "1px solid rgba(56,189,248,0.08)", background: "rgba(56,189,248,0.015)" }} />
          {/* Subtle logo mark center */}
          <div style={{ position: "absolute", right: 20, bottom: 14, width: 14, height: 14, borderRadius: "50%", background: "rgba(56,189,248,0.06)", border: "1px solid rgba(56,189,248,0.1)" }} />
        </div>

        {/* ── Shadow ── */}
        <div style={{ width: LAPTOP_W * 0.62, height: 20, borderRadius: "50%", background: "radial-gradient(ellipse, rgba(0,0,0,0.6) 0%, transparent 70%)", marginTop: 4, marginLeft: "20%" }} />
      </div>
    </div>
  );
}
