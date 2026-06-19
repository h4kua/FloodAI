import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, Easing } from "remotion";
import { T, MONO, SANS, BODY } from "../tokens";
import { ParticleField } from "../components/ParticleField";
import { sceneZoom, countUp, ImpactFlash } from "../components/FX";

function LogoMark({ size = 80 }) {
  const arm = "M 16 5.5 C 24 5.5 27.5 13 23 19 C 21.5 21.5 19 23 16 23";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="dfg_intro" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="55%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#818cf8" />
        </linearGradient>
        <filter id="glow_intro">
          <feGaussianBlur stdDeviation="1.4" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <g stroke="url(#dfg_intro)" strokeLinecap="round" fill="none" strokeWidth="3.5" filter="url(#glow_intro)">
        <path d={arm} />
        <path d={arm} transform="rotate(120 16 16)" />
        <path d={arm} transform="rotate(240 16 16)" />
      </g>
    </svg>
  );
}

const STATS = [
  { end: 38,   suffix: "+", label: "TITIK PANTAU"  },
  { end: 94,   suffix: "%", label: "AKURASI AI"    },
  { fixed: "<1s",           label: "NOTIFIKASI"    },
  { fixed: "Gratis",        label: "SELAMANYA"     },
];

// Per-word staggered reveal: rise + blur→sharp, then synced fade-out
function StaggerLine({ frame, text, start, fadeOut, color }) {
  const words = text.split(" ");
  return (
    <div style={{
      fontFamily: SANS,
      fontWeight: 700,
      fontSize: 148,
      letterSpacing: "-0.05em",
      lineHeight: 1,
      textTransform: "uppercase",
      display: "flex",
      gap: "0.28em",
      opacity: fadeOut,
    }}>
      {words.map((w, i) => {
        const d = start + i * 5;
        const op = interpolate(frame, [d, d + 9], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const y  = interpolate(frame, [d, d + 12], [42, 0], {
          extrapolateLeft: "clamp", extrapolateRight: "clamp",
          easing: Easing.out(Easing.cubic),
        });
        const blur = interpolate(frame, [d, d + 10], [12, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <span key={i} style={{
            color,
            opacity: op,
            transform: `translateY(${y}px)`,
            filter: `blur(${blur}px)`,
            display: "inline-block",
          }}>{w}</span>
        );
      })}
    </div>
  );
}

export function IntroScene() {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // ── Scan line sweeps top → bottom ───────────────────────────────────
  const scanY = interpolate(frame, [4, 32], [0, height], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const scanOp = interpolate(frame, [4, 8, 30, 34], [0, 1, 1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  // ── Big tagline reveal — word-staggered ──────────────────────────────
  const line1FadeOut = interpolate(frame, [42, 52], [1, 0], { extrapolateRight: "clamp" });
  const line2FadeOut = interpolate(frame, [46, 57], [1, 0], { extrapolateRight: "clamp" });

  // ── Brand reveal — starts after tagline is fully gone (frame 57) ─────
  const logoOp    = interpolate(frame, [61, 74], [0, 1], { extrapolateRight: "clamp" });
  const logoScale = spring({ frame: Math.max(0, frame - 61), fps, from: 0.72, to: 1, config: { damping: 12 } });
  const brandOp   = interpolate(frame, [67, 78], [0, 1], { extrapolateRight: "clamp" });
  const brandY    = spring({ frame: Math.max(0, frame - 67), fps, from: 30, to: 0, config: { damping: 10 } });
  const lineW     = interpolate(frame, [65, 80], [0, 100], { extrapolateRight: "clamp" });
  const statsOp   = interpolate(frame, [73, 85], [0, 1], { extrapolateRight: "clamp" });

  // ── Scene fade out ────────────────────────────────────────────────────
  const sceneOp = interpolate(frame, [83, 90], [1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  // ── Glow burst where scanline currently is ───────────────────────────
  const scanGlowOp = scanOp * 0.7;

  return (
    <div style={{
      position: "absolute", inset: 0,
      background: "#030508",
      overflow: "hidden",
      opacity: sceneOp,
      transform: `scale(${sceneZoom(frame, 90, 0.05)})`,
    }}>
      {/* Particle rain */}
      <ParticleField frame={frame} opacity={0.18} />

      {/* Subtle radial glow from center */}
      <div style={{
        position: "absolute", inset: 0,
        background: "radial-gradient(ellipse 90% 60% at 50% 50%, rgba(56,189,248,0.04) 0%, transparent 65%)",
        pointerEvents: "none",
      }} />

      {/* Grid lines */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: "linear-gradient(rgba(56,189,248,0.018) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.018) 1px, transparent 1px)",
        backgroundSize: "90px 90px",
        pointerEvents: "none",
      }} />

      {/* ── SCANLINE ── */}
      <div style={{
        position: "absolute",
        left: 0, right: 0,
        top: scanY,
        height: 2,
        background: `linear-gradient(90deg, transparent 0%, rgba(56,189,248,0.5) 15%, rgba(255,255,255,0.85) 50%, rgba(56,189,248,0.5) 85%, transparent 100%)`,
        boxShadow: "0 0 18px 4px rgba(56,189,248,0.5), 0 0 40px 12px rgba(56,189,248,0.15)",
        opacity: scanGlowOp,
        pointerEvents: "none",
        zIndex: 20,
      }} />

      {/* Scanline wake — faint glow below line */}
      <div style={{
        position: "absolute",
        left: 0, right: 0,
        top: 0, bottom: height - scanY,
        background: "linear-gradient(180deg, transparent 85%, rgba(56,189,248,0.015) 100%)",
        pointerEvents: "none",
        opacity: scanGlowOp,
        zIndex: 10,
      }} />

      {/* ── COLD OPEN TEXT ── */}
      <div style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingLeft: 120,
        paddingTop: 0,
      }}>
        {/* Line 1 — word stagger */}
        <div style={{ marginBottom: 6 }}>
          <StaggerLine frame={frame} text="SEBELUM BANJIR," start={12} fadeOut={line1FadeOut} color={T.text} />
        </div>

        {/* Line 2 — word stagger, amber warning */}
        <StaggerLine frame={frame} text="KAMU SUDAH TAHU." start={24} fadeOut={line2FadeOut} color={T.wsp} />
      </div>

      {/* Impact flash when line 2 lands */}
      <ImpactFlash frame={frame} at={34} peak={0.22} />

      {/* ── BRAND REVEAL (after tagline fades) ── */}
      <div style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
      }}>
        {/* Logo */}
        <div style={{
          opacity: logoOp,
          transform: `scale(${logoScale})`,
          marginBottom: 28,
        }}>
          <div style={{
            width: 120, height: 120, borderRadius: "50%",
            background: "rgba(56,189,248,0.06)",
            border: "1px solid rgba(56,189,248,0.2)",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 0 60px rgba(56,189,248,0.14)",
          }}>
            <LogoMark size={68} />
          </div>
        </div>

        {/* Brand name */}
        <div style={{ opacity: brandOp, transform: `translateY(${brandY}px)`, textAlign: "center", marginBottom: 10 }}>
          <span style={{ fontFamily: SANS, fontWeight: 800, fontSize: 108, letterSpacing: "-0.04em", lineHeight: 0.9 }}>
            <span style={{ color: T.muted }}>de</span>
            <span style={{ color: T.cyan }}>Flood</span>
            <span style={{ color: T.text }}>.ai</span>
          </span>
        </div>

        {/* Underline */}
        <div style={{
          width: `${lineW}%`, maxWidth: 380, height: 3,
          background: `linear-gradient(90deg, transparent, ${T.cyan}, transparent)`,
          marginBottom: 22, opacity: brandOp,
          boxShadow: `0 0 12px ${T.cyan}`,
        }} />

        {/* Subtitle */}
        <div style={{ opacity: brandOp, marginBottom: 52 }}>
          <p style={{ fontFamily: MONO, fontSize: 20, color: T.muted, letterSpacing: "0.18em", textTransform: "uppercase", margin: 0 }}>
            Sistem Peringatan Banjir Jakarta · 100% Gratis
          </p>
        </div>

        {/* Stats row */}
        <div style={{ display: "flex", gap: 16, opacity: statsOp }}>
          {STATS.map((s, i) => (
            <div key={i} style={{
              background: "#161b22",
              border: "1px solid rgba(48,54,61,0.9)",
              borderRadius: 18,
              padding: "16px 30px",
              textAlign: "center",
              minWidth: 140,
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
            }}>
              <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 42, color: T.cyan, lineHeight: 1 }}>
                {s.fixed ?? `${Math.round(countUp(frame, 0, s.end, 73, 16))}${s.suffix}`}
              </div>
              <div style={{ fontFamily: MONO, fontSize: 11, color: T.muted, letterSpacing: "0.1em", marginTop: 6 }}>{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
