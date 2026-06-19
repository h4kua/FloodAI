import React from "react";
import { T, MONO } from "../tokens";

export const PHONE_W      = 360;
export const PHONE_H      = 720;
export const PHONE_STATUS = 48;
export const PHONE_HOME   = 30;

export function PhoneDevice({ children, rotY = 0, floatY = 0, opacity = 1, scale = 1 }) {
  return (
    <div style={{ perspective: 1200, perspectiveOrigin: "50% 50%", display: "inline-flex" }}>
      <div style={{ transform: `scale(${scale}) rotateY(${rotY}deg) rotateX(-4deg) translateY(${floatY}px)`, opacity, position: "relative", willChange: "transform" }}>

        {/* ── Body ── */}
        <div style={{
          width: PHONE_W, height: PHONE_H,
          background: "#05080f",
          borderRadius: 52,
          border: "1.5px solid rgba(56,189,248,0.25)",
          boxShadow: [
            "0 0 65px rgba(56,189,248,0.12)",
            "0 0 130px rgba(56,189,248,0.05)",
            "0 60px 180px rgba(0,0,0,0.96)",
          ].join(", "),
          position: "relative", overflow: "hidden",
        }}>
          {/* Dynamic island */}
          <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", width: 88, height: 28, background: "#040810", borderRadius: 16, zIndex: 10, border: "1px solid rgba(56,189,248,0.07)", display: "flex", alignItems: "center", justifyContent: "flex-end", paddingRight: 10 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#0c1120", border: "1px solid rgba(56,189,248,0.13)" }} />
          </div>

          {/* Status bar */}
          <div style={{ height: PHONE_STATUS, display: "flex", alignItems: "flex-end", justifyContent: "space-between", padding: "0 20px 7px", position: "relative", zIndex: 5 }}>
            <span style={{ fontFamily: MONO, fontSize: 11, color: "rgba(230,237,243,0.58)", letterSpacing: "0.03em" }}>9:41</span>
            <div style={{ display: "flex", gap: 3.5, alignItems: "center" }}>
              {[2,3,4].map(h => <div key={h} style={{ width: 3, height: h*3, background: "rgba(230,237,243,0.58)", borderRadius: 1 }} />)}
              <div style={{ width: 16, height: 8, borderRadius: 2, border: "1px solid rgba(230,237,243,0.46)", marginLeft: 3, padding: 1, display: "flex", alignItems: "center" }}>
                <div style={{ width: "78%", height: "100%", background: T.safe, borderRadius: 1 }} />
              </div>
            </div>
          </div>

          {/* Screen content */}
          <div style={{ position: "absolute", top: PHONE_STATUS, left: 0, right: 0, bottom: PHONE_HOME, overflow: "hidden" }}>
            {children}
          </div>

          {/* Home indicator */}
          <div style={{ position: "absolute", bottom: 9, left: "50%", transform: "translateX(-50%)", width: 86, height: 4, borderRadius: 2, background: "rgba(230,237,243,0.24)" }} />

          {/* Glare */}
          <div style={{ position: "absolute", inset: 0, background: "linear-gradient(132deg, rgba(255,255,255,0.042) 0%, transparent 36%)", borderRadius: 52, pointerEvents: "none" }} />
          {/* Cyan edge */}
          <div style={{ position: "absolute", inset: 0, boxShadow: "0 0 0 1px rgba(56,189,248,0.05) inset", borderRadius: 52, pointerEvents: "none" }} />
        </div>

        {/* Power button */}
        <div style={{ position: "absolute", right: -4, top: 110, width: 4, height: 54, background: "#08101e", borderRadius: "0 3px 3px 0", border: "1px solid rgba(56,189,248,0.09)" }} />
        {/* Volume buttons */}
        {[0,1].map(i => <div key={i} style={{ position: "absolute", left: -4, top: 92+i*62, width: 4, height: 40, background: "#08101e", borderRadius: "3px 0 0 3px", border: "1px solid rgba(56,189,248,0.09)" }} />)}

        {/* Shadow */}
        <div style={{ position: "absolute", bottom: -26, left: "18%", right: "18%", height: 26, background: "radial-gradient(ellipse, rgba(0,0,0,0.6) 0%, transparent 70%)" }} />
      </div>
    </div>
  );
}
