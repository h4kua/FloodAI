import React from "react";
import { T, MONO, SANS } from "../tokens";

/**
 * Browser frame sized for 1920×1080 video.
 * Width is controlled by the parent container.
 */
export function BrowserFrame({ children, url = "deflood.ai", style = {} }) {
  const CHROME_H = 56;
  const FRAME_R  = 20;

  return (
    <div style={{
      borderRadius: FRAME_R,
      overflow: "hidden",
      boxShadow: "0 48px 120px rgba(0,0,0,0.75), 0 0 0 1px rgba(255,255,255,0.08)",
      border: `1px solid rgba(255,255,255,0.10)`,
      ...style,
    }}>
      {/* Browser chrome bar */}
      <div style={{
        background: "#151d2a",
        height: CHROME_H,
        display: "flex",
        alignItems: "center",
        paddingLeft: 20,
        paddingRight: 20,
        gap: 16,
        borderBottom: "1px solid rgba(255,255,255,0.07)",
        flexShrink: 0,
      }}>
        {/* Traffic lights */}
        <div style={{ display: "flex", gap: 8 }}>
          {["#ff5f57","#febc2e","#28c840"].map((c, i) => (
            <div key={i} style={{ width: 16, height: 16, borderRadius: "50%", background: c, opacity: 0.9 }} />
          ))}
        </div>

        {/* URL bar */}
        <div style={{
          flex: 1, maxWidth: 600, margin: "0 auto",
          background: "rgba(13, 17, 23, 0.8)",
          borderRadius: 10,
          height: 34,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          border: "1px solid rgba(255,255,255,0.08)",
          paddingLeft: 12, paddingRight: 12,
        }}>
          {/* Lock icon */}
          <svg width={14} height={14} viewBox="0 0 16 16" fill="#34d399" style={{ opacity: 0.8 }}>
            <path d="M11 7V5a3 3 0 0 0-6 0v2H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1Zm-5-2a2 2 0 1 1 4 0v2H6V5Z"/>
          </svg>
          <span style={{ fontFamily: MONO, fontSize: 14, color: "#8b949e", letterSpacing: "0.02em" }}>
            {url}
          </span>
        </div>

        {/* Right: LIVE chip */}
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          background: "rgba(52,211,153,0.1)",
          border: "1px solid rgba(52,211,153,0.3)",
          borderRadius: 8, padding: "5px 12px",
        }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#34d399", display: "block", boxShadow: "0 0 6px #34d399" }} />
          <span style={{ fontFamily: MONO, fontSize: 12, color: "#34d399", letterSpacing: "0.1em" }}>LIVE</span>
        </div>
      </div>

      {/* App viewport */}
      <div style={{ background: T.bg, overflow: "hidden" }}>
        {children}
      </div>
    </div>
  );
}

/** Top navigation bar (inside the browser frame) — full 1920px scale */
export function AppNav({ activePage = "home" }) {
  const PAGES = [
    { id: "home",  label: "Command Center" },
    { id: "alert", label: "Evakuasi" },
    { id: "about", label: "Tentang" },
  ];

  return (
    <div style={{
      background: "rgba(13,17,23,0.92)",
      backdropFilter: "blur(16px)",
      borderBottom: `1px solid ${T.line}`,
      height: 68,
      display: "flex",
      alignItems: "center",
      paddingLeft: 32,
      paddingRight: 32,
      gap: 12,
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 12 }}>
        <DeFloodLogoMark size={28} />
        <span style={{ fontFamily: SANS, fontWeight: 700, fontSize: 22, letterSpacing: "-0.02em" }}>
          <span style={{ color: T.muted }}>de</span>
          <span style={{ color: T.cyan }}>Flood</span>
          <span style={{ color: T.text }}>.ai</span>
        </span>
      </div>

      {/* Nav buttons */}
      <div style={{ display: "flex", gap: 6, marginLeft: 8 }}>
        {PAGES.map(p => (
          <div key={p.id} style={{
            padding: "8px 18px",
            borderRadius: 10,
            fontFamily: MONO,
            fontSize: 14,
            letterSpacing: "0.02em",
            color:      p.id === activePage ? T.text     : T.muted,
            background: p.id === activePage ? T.panel2   : "transparent",
            border:     p.id === activePage ? `1px solid ${T.line}` : "1px solid transparent",
          }}>
            {p.label}
          </div>
        ))}
      </div>

      {/* Right chips */}
      <div style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center" }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 6,
          background: "rgba(52,211,153,0.08)", border: "1px solid rgba(52,211,153,0.25)",
          borderRadius: 8, padding: "6px 14px",
        }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#34d399", display: "block" }} />
          <span style={{ fontFamily: MONO, fontSize: 12, color: "#34d399", letterSpacing: "0.08em" }}>Online</span>
        </div>
        <div style={{
          background: T.panel2, border: `1px solid ${T.line}`,
          borderRadius: 8, padding: "6px 14px",
          fontFamily: MONO, fontSize: 12, color: T.muted, letterSpacing: "0.04em",
        }}>Jakarta, DKI</div>
      </div>
    </div>
  );
}

function DeFloodLogoMark({ size = 28 }) {
  const arm = "M 16 5.5 C 24 5.5 27.5 13 23 19 C 21.5 21.5 19 23 16 23";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" style={{ display: "block", flexShrink: 0 }}>
      <defs>
        <linearGradient id="dfg_nav" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%"   stopColor="#22d3ee" />
          <stop offset="55%"  stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#818cf8" />
        </linearGradient>
      </defs>
      <g stroke="url(#dfg_nav)" strokeLinecap="round" fill="none" strokeWidth="3.5">
        <path d={arm} />
        <path d={arm} transform="rotate(120 16 16)" />
        <path d={arm} transform="rotate(240 16 16)" />
      </g>
    </svg>
  );
}
