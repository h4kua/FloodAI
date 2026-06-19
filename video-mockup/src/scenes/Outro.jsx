import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { T, MONO, SANS, BODY } from "../tokens";
import { LaptopDevice } from "../components/LaptopDevice";
import { PhoneDevice } from "../components/PhoneDevice";
import { ParticleField } from "../components/ParticleField";
import { sceneZoom, LightSweep } from "../components/FX";

function DeFloodLogo({ size = 90 }) {
  const arm = "M 16 5.5 C 24 5.5 27.5 13 23 19 C 21.5 21.5 19 23 16 23";
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="dfg_outro" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#22d3ee" />
          <stop offset="55%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#818cf8" />
        </linearGradient>
        <filter id="glow_outro">
          <feGaussianBlur stdDeviation="1.4" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      <g stroke="url(#dfg_outro)" strokeLinecap="round" fill="none" strokeWidth="3.5" filter="url(#glow_outro)">
        <path d={arm} />
        <path d={arm} transform="rotate(120 16 16)" />
        <path d={arm} transform="rotate(240 16 16)" />
      </g>
    </svg>
  );
}

// Decorative device screen content for bg devices
function BlankDashBg() {
  return (
    <div style={{ width: "100%", height: "100%", background: "#0d1117", padding: 10, overflow: "hidden" }}>
      <div style={{ height: 20, borderRadius: 4, background: "rgba(56,189,248,0.06)", marginBottom: 10 }} />
      <div style={{ height: 50, borderRadius: 8, background: "rgba(251,191,36,0.05)", border: "1px solid rgba(251,191,36,0.12)", marginBottom: 8 }} />
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        {[T.cyan, T.safe, T.wsp].map(c => <div key={c} style={{ flex: 1, height: 40, borderRadius: 6, background: `${c}08`, border: `1px solid ${c}18` }} />)}
      </div>
      {Array.from({ length: 6 }).map((_, i) => <div key={i} style={{ height: 12, borderRadius: 3, background: "rgba(230,237,243,0.03)", marginBottom: 5 }} />)}
    </div>
  );
}

function BlankChatBg() {
  return (
    <div style={{ width: "100%", height: "100%", background: "#0d1117", padding: 8, overflow: "hidden", display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ height: 36, borderRadius: 8, background: "#161b22" }} />
      {[1,0,1,0].map((u,i) => (
        <div key={i} style={{ display: "flex", justifyContent: u ? "flex-end" : "flex-start" }}>
          <div style={{ width: "75%", height: 36 + i * 6, borderRadius: 12, background: u ? "rgba(56,189,248,0.08)" : "#1c2333", border: `1px solid ${u ? "rgba(56,189,248,0.15)" : "rgba(48,54,61,0.6)"}` }} />
        </div>
      ))}
    </div>
  );
}

const FEATURES = [
  { icon: "⬡", label: "XGBoost Model",    sub: "94% accuracy · 14 features"  },
  { icon: "◉", label: "38+ Sensor",        sub: "DSDADKI realtime"            },
  { icon: "🌧", label: "BMKG Weather",     sub: "Per-wilayah forecast"        },
  { icon: "🤖", label: "AI Chatbot Flo",   sub: "Groq · LLaMA-3"             },
  { icon: "🚨", label: "Evacuation Route", sub: "Shelter BPBD otomatis"      },
  { icon: "🗺", label: "Risk Map",         sub: "ML zone estimation"          },
];

export function OutroScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sceneOp   = interpolate(frame, [0, 14], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const logoOp    = interpolate(frame, [0, 26], [0, 1], { extrapolateRight: "clamp" });
  const logoScale = spring({ frame, fps, from: 0.72, to: 1, config: { damping: 12 } });
  const brandOp   = interpolate(frame, [24, 46], [0, 1], { extrapolateRight: "clamp" });
  const brandY    = spring({ frame: Math.max(0, frame - 24), fps, from: 28, to: 0, config: { damping: 10 } });
  const gridOp    = interpolate(frame, [52, 82], [0, 1], { extrapolateRight: "clamp" });
  const ctaOp     = interpolate(frame, [92, 124], [0, 1], { extrapolateRight: "clamp" });
  const lineW     = interpolate(frame, [30, 62], [0, 100], { extrapolateRight: "clamp" });

  const pulseScale = 1 + 0.07 * Math.sin((frame / 30) * Math.PI * 2);
  const pulseOp    = 0.22 + 0.12 * Math.sin((frame / 30) * Math.PI * 2);

  // Background device animations
  const devicesOp = interpolate(frame, [40, 80], [0, 1], { extrapolateRight: "clamp" });
  const laptopRotY = -20 + Math.sin(frame * 0.018) * 6;
  const phoneRotY  =  20 + Math.sin(frame * 0.018 + 1.4) * 6;
  const laptopFloat = Math.sin(frame * 0.022) * 14;
  const phoneFloat  = Math.sin(frame * 0.022 + 0.9) * 14;

  return (
    <div style={{ position: "absolute", inset: 0, background: "#03060c", overflow: "hidden", opacity: sceneOp, transform: `scale(${sceneZoom(frame, 510, 0.04)})` }}>

      {/* Atmospheric gradient */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 110% 75% at 50% 50%, rgba(56,189,248,0.065) 0%, transparent 62%), radial-gradient(ellipse 50% 40% at 15% 85%, rgba(59,130,246,0.04) 0%, transparent 50%), radial-gradient(ellipse 40% 30% at 85% 15%, rgba(129,140,248,0.03) 0%, transparent 50%)", pointerEvents: "none" }} />

      {/* Grid */}
      <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(56,189,248,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.02) 1px, transparent 1px)", backgroundSize: "100px 100px", pointerEvents: "none" }} />

      {/* Particles */}
      <ParticleField frame={frame} opacity={0.18} />

      {/* ── BACKGROUND DEVICES ── */}
      <div style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity: devicesOp * 0.28 }}>
        {/* Laptop — left bg */}
        <div style={{ position: "absolute", left: -60, top: "50%", transform: "translateY(-52%)" }}>
          <LaptopDevice rotY={laptopRotY} floatY={laptopFloat} scale={0.60}>
            <BlankDashBg />
          </LaptopDevice>
        </div>
        {/* Phone — right bg */}
        <div style={{ position: "absolute", right: -20, top: "50%", transform: "translateY(-48%)" }}>
          <PhoneDevice rotY={phoneRotY} floatY={phoneFloat} scale={0.66}>
            <BlankChatBg />
          </PhoneDevice>
        </div>
      </div>

      {/* Feature grid — ghost layer */}
      <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, right: 0, display: "flex", flexWrap: "wrap", padding: "80px 100px", gap: 16, opacity: gridOp * 0.32, alignContent: "flex-start", pointerEvents: "none" }}>
        {FEATURES.map((f, i) => {
          const delay = i * 8;
          const op = interpolate(frame, [52 + delay, 76 + delay], [0, 1], { extrapolateRight: "clamp" });
          return (
            <div key={i} style={{ background: "#161b22", border: "1px solid rgba(48,54,61,0.8)", borderRadius: 16, padding: "14px 20px", display: "flex", gap: 12, alignItems: "center", opacity: op }}>
              <span style={{ fontSize: 22 }}>{f.icon}</span>
              <div>
                <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 15, color: T.text }}>{f.label}</div>
                <div style={{ fontFamily: MONO, fontSize: 11, color: T.muted, marginTop: 2 }}>{f.sub}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── CENTER FOREGROUND ── */}
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", zIndex: 2 }}>

        {/* Logo + pulse ring */}
        <div style={{ position: "relative", marginBottom: 28, opacity: logoOp }}>
          <div style={{ position: "absolute", top: "50%", left: "50%", width: 180, height: 180, borderRadius: "50%", border: `2px solid ${T.cyan}`, transform: `translate(-50%, -50%) scale(${pulseScale})`, opacity: pulseOp }} />
          <div style={{ width: 156, height: 156, borderRadius: "50%", background: "rgba(56,189,248,0.065)", border: "1px solid rgba(56,189,248,0.2)", display: "flex", alignItems: "center", justifyContent: "center", boxShadow: "0 0 80px rgba(56,189,248,0.16)", transform: `scale(${logoScale})` }}>
            <DeFloodLogo size={88} />
          </div>
        </div>

        {/* Brand name */}
        <div style={{ transform: `translateY(${brandY}px)`, opacity: brandOp, textAlign: "center", marginBottom: 14 }}>
          <span style={{ fontFamily: SANS, fontWeight: 800, fontSize: 120, letterSpacing: "-0.04em", lineHeight: 0.9 }}>
            <span style={{ color: T.muted }}>de</span>
            <span style={{ color: T.cyan }}>Flood</span>
            <span style={{ color: T.text }}>.ai</span>
          </span>
        </div>

        {/* Cyan underline */}
        <div style={{ width: `${lineW}%`, maxWidth: 480, height: 3, background: `linear-gradient(90deg, transparent, ${T.cyan}, transparent)`, marginBottom: 22, opacity: brandOp, boxShadow: `0 0 16px ${T.cyan}` }} />

        {/* Tagline */}
        <div style={{ fontFamily: MONO, fontSize: 20, color: T.muted, letterSpacing: "0.16em", textTransform: "uppercase", opacity: brandOp, marginBottom: 32 }}>
          Sistem Peringatan Dini Banjir Jakarta · 100% Gratis
        </div>

        {/* CTA block — social media optimised */}
        <div style={{ opacity: ctaOp, display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>

          {/* Primary CTA button */}
          <div style={{
            background: "linear-gradient(135deg, rgba(56,189,248,0.92) 0%, rgba(59,130,246,0.92) 100%)",
            border: "1px solid rgba(56,189,248,0.55)",
            borderRadius: 18,
            padding: "15px 60px",
            fontFamily: SANS,
            fontWeight: 800,
            fontSize: 27,
            color: "#fff",
            letterSpacing: "-0.01em",
            boxShadow: "0 0 48px rgba(56,189,248,0.38), 0 8px 28px rgba(0,0,0,0.45)",
          }}>
            COBA GRATIS SEKARANG
          </div>

          {/* URL badge with shimmer */}
          <div style={{ position: "relative", overflow: "hidden", background: "#161b22", border: `1px solid rgba(56,189,248,0.28)`, borderRadius: 14, padding: "11px 40px", fontFamily: MONO, fontSize: 24, color: T.cyan, letterSpacing: "0.06em", boxShadow: "0 0 28px rgba(56,189,248,0.1)" }}>
            deflood.ai
            {frame >= 130 && (
              <LightSweep frame={130 + ((frame - 130) % 110)} start={130} duration={42} intensity={0.3} />
            )}
          </div>

          {/* Social handles */}
          <div style={{ display: "flex", gap: 22, alignItems: "center" }}>
            <span style={{ fontFamily: MONO, fontSize: 15, color: T.muted, letterSpacing: "0.05em" }}>Instagram · @defloodai</span>
            <span style={{ color: T.muted2, fontSize: 18 }}>·</span>
            <span style={{ fontFamily: MONO, fontSize: 15, color: T.muted, letterSpacing: "0.05em" }}>TikTok · @defloodai</span>
            <span style={{ color: T.muted2, fontSize: 18 }}>·</span>
            <span style={{ fontFamily: MONO, fontSize: 15, color: T.safe, letterSpacing: "0.05em", fontWeight: 700 }}>100% GRATIS</span>
          </div>

          {/* Trust strip */}
          <div style={{ fontFamily: MONO, fontSize: 12, color: T.muted2, letterSpacing: "0.07em" }}>
            Data BMKG + DSDADKI · Terverifikasi BPBD DKI Jakarta
          </div>
        </div>
      </div>
    </div>
  );
}
