import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { T, MONO, SANS, BODY } from "../tokens";
import { LaptopDevice } from "../components/LaptopDevice";
import { PhoneDevice } from "../components/PhoneDevice";
import { ParticleField } from "../components/ParticleField";
import { sceneZoom, LightSweep } from "../components/FX";

// ─── Mini Dashboard (laptop screen) ─────────────────────────────────────────
function MiniDashboard() {
  return (
    <div style={{ width: "100%", height: "100%", background: "#0d1117", overflow: "hidden", padding: "10px 12px", display: "flex", flexDirection: "column", gap: 7 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, paddingBottom: 7, borderBottom: "1px solid rgba(48,54,61,0.7)", flexShrink: 0 }}>
        <div style={{ width: 18, height: 18, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)" }} />
        <span style={{ fontFamily: MONO, fontSize: 10, color: T.cyan, letterSpacing: "0.1em", fontWeight: 700 }}>deFlood.ai</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 5 }}>
          {["Dashboard","Peta","Chat","Evakuasi"].map(t => (
            <span key={t} style={{ fontFamily: MONO, fontSize: 8, color: T.muted, padding: "2px 6px", border: `1px solid ${T.line}`, borderRadius: 4 }}>{t}</span>
          ))}
        </div>
      </div>
      <div style={{ background: "rgba(251,191,36,0.07)", border: "1px solid rgba(251,191,36,0.28)", borderRadius: 10, padding: "9px 14px", flexShrink: 0 }}>
        <div style={{ fontFamily: MONO, fontSize: 9, color: T.wsp, marginBottom: 5 }}>⚠ WASPADA · Skor 42 / 100</div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ flex: 1, height: 5, borderRadius: 3, background: "#161b22" }}>
            <div style={{ width: "42%", height: "100%", background: T.wsp, borderRadius: 3, boxShadow: "0 0 8px rgba(251,191,36,0.4)" }} />
          </div>
          <span style={{ fontFamily: SANS, fontWeight: 800, fontSize: 20, color: T.wsp }}>42</span>
        </div>
      </div>
      <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
        {[
          { label: "Curah Hujan", value: "18 mm", color: T.cyan },
          { label: "Sensor Aktif", value: "38",   color: T.safe },
          { label: "Sta. Siaga",   value: "3",    color: T.wsp  },
        ].map(m => (
          <div key={m.label} style={{ flex: 1, background: "#161b22", border: "1px solid rgba(48,54,61,0.9)", borderRadius: 7, padding: "7px 9px" }}>
            <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 17, color: m.color, lineHeight: 1 }}>{m.value}</div>
            <div style={{ fontFamily: MONO, fontSize: 8.5, color: T.muted, marginTop: 3 }}>{m.label}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", flexShrink: 0 }}>
        {[
          { l: "Manggarai", ok: true  }, { l: "Katulampa", ok: true  },
          { l: "Ps. Ikan",  ok: false }, { l: "Angke",     ok: true  },
          { l: "Depok",     ok: true  }, { l: "Cipinang",  ok: false },
        ].map(s => (
          <div key={s.l} style={{ fontFamily: MONO, fontSize: 8, padding: "3px 7px", borderRadius: 10, background: s.ok ? "rgba(52,211,153,0.07)" : "rgba(251,191,36,0.07)", border: `1px solid ${s.ok ? "rgba(52,211,153,0.22)" : "rgba(251,191,36,0.28)"}`, color: s.ok ? T.safe : T.wsp }}>● {s.l}</div>
        ))}
      </div>
      <div style={{ flex: 1, overflow: "hidden" }}>
        {[
          { sta: "BKT Dukuh Atas", cm: "214 cm", status: "Aman",    color: T.safe },
          { sta: "Manggarai",      cm: "620 cm", status: "Waspada", color: T.wsp  },
          { sta: "Katulampa",      cm: "310 cm", status: "Siaga 2", color: T.s2   },
        ].map(r => (
          <div key={r.sta} style={{ display: "flex", alignItems: "center", gap: 6, padding: "4px 0", borderBottom: "1px solid rgba(48,54,61,0.4)" }}>
            <span style={{ fontFamily: BODY, fontSize: 9, color: T.text, flex: 1 }}>{r.sta}</span>
            <span style={{ fontFamily: MONO, fontSize: 9, color: T.muted }}>{r.cm}</span>
            <span style={{ fontFamily: MONO, fontSize: 8, padding: "2px 5px", borderRadius: 5, background: `${r.color}15`, color: r.color, border: `1px solid ${r.color}30` }}>{r.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Mini Chat (phone screen) ────────────────────────────────────────────────
function MiniChat() {
  return (
    <div style={{ width: "100%", height: "100%", background: "#0d1117", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "8px 12px", background: "#161b22", borderBottom: "1px solid rgba(48,54,61,0.8)", display: "flex", alignItems: "center", gap: 9, flexShrink: 0 }}>
        <div style={{ width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 10, color: "#fff", fontWeight: 700, flexShrink: 0 }}>AI</div>
        <div>
          <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 12, color: T.text }}>Flo — deFlood.ai</div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.safe, display: "block" }} />
            <span style={{ fontFamily: MONO, fontSize: 9, color: T.safe }}>AI Online</span>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, padding: "10px 10px 4px", overflow: "hidden", display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", gap: 7 }}>
          <div style={{ width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 8, color: "#fff", fontWeight: 700, flexShrink: 0 }}>AI</div>
          <div style={{ background: "#1c2333", border: "1px solid rgba(48,54,61,0.8)", borderRadius: "4px 12px 12px 12px", padding: "7px 10px" }}>
            <div style={{ fontFamily: BODY, fontSize: 10.5, color: T.text, lineHeight: 1.55 }}>Halo! 👋 Saya Flo.{"\n"}Status: ⚠ Waspada.</div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <div style={{ background: "rgba(56,189,248,0.12)", border: "1px solid rgba(56,189,248,0.22)", borderRadius: "12px 4px 12px 12px", padding: "7px 10px" }}>
            <div style={{ fontFamily: BODY, fontSize: 10.5, color: T.text }}>pik aman ga sekarang?</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 7 }}>
          <div style={{ width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 8, color: "#fff", fontWeight: 700, flexShrink: 0 }}>AI</div>
          <div style={{ background: "#1c2333", border: "1px solid rgba(48,54,61,0.8)", borderRadius: "4px 12px 12px 12px", padding: "7px 10px" }}>
            <div style={{ fontFamily: BODY, fontSize: 10.5, color: T.text, lineHeight: 1.55 }}>PIK (Penjaringan) → Waduk Pluit 38%{"\n"}→ AMAN ✓ · Waspada rob pasang.</div>
          </div>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <div style={{ background: "rgba(56,189,248,0.12)", border: "1px solid rgba(56,189,248,0.22)", borderRadius: "12px 4px 12px 12px", padding: "7px 10px" }}>
            <div style={{ fontFamily: BODY, fontSize: 10.5, color: T.text }}>shelter terdekat?</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 7, alignItems: "center" }}>
          <div style={{ width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 8, color: "#fff", fontWeight: 700, flexShrink: 0 }}>AI</div>
          <div style={{ background: "#1c2333", border: "1px solid rgba(48,54,61,0.8)", borderRadius: "4px 12px 12px 12px", padding: "9px 14px", display: "flex", gap: 4 }}>
            {[0,1,2].map(d => <div key={d} style={{ width: 6, height: 6, borderRadius: "50%", background: T.muted }} />)}
          </div>
        </div>
      </div>
      <div style={{ padding: "7px 10px", borderTop: "1px solid rgba(48,54,61,0.8)", display: "flex", gap: 7, flexShrink: 0 }}>
        <div style={{ flex: 1, background: "#161b22", border: "1px solid rgba(48,54,61,0.8)", borderRadius: 10, padding: "7px 10px", fontFamily: BODY, fontSize: 10, color: T.muted2 }}>Tanya kondisi banjir...</div>
        <div style={{ width: 30, height: 30, borderRadius: 9, background: T.cyan, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, color: T.bg, fontWeight: 700, flexShrink: 0, boxShadow: "0 4px 12px rgba(56,189,248,0.4)" }}>▶</div>
      </div>
    </div>
  );
}

const FEATURE_CHIPS = [
  { label: "XGBoost · 94%",    color: T.cyan, icon: "◈" },
  { label: "38+ Sensor",        color: T.safe, icon: "◉" },
  { label: "AI Chatbot Flo",    color: T.cyan, icon: "◎" },
  { label: "Evakuasi Otomatis", color: T.wsp,  icon: "◇" },
  { label: "Peta Risiko",       color: T.s2,   icon: "◈" },
  { label: "BMKG + DSDADKI",    color: T.muted,icon: "◆" },
];

// ─── Main scene ──────────────────────────────────────────────────────────────
export function DeviceShowcaseScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sceneOp   = interpolate(frame, [0, 14, 62, 75], [0, 1, 1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
  const glowPulse = 0.72 + 0.28 * Math.sin(frame * 0.026);

  // Laptop: slides in from left
  const laptopDelay = 8;
  const laptopRotY  = spring({ frame: Math.max(0, frame - laptopDelay), fps, from: 62, to: -8, config: { damping: 13, stiffness: 64 } });
  const laptopX     = spring({ frame: Math.max(0, frame - laptopDelay), fps, from: -420, to: 0, config: { damping: 14, stiffness: 58 } });
  const laptopOp    = interpolate(frame, [laptopDelay, laptopDelay + 18], [0, 1], { extrapolateRight: "clamp" });
  const laptopFloat = Math.sin(frame * 0.022) * 10;

  // Phone: slides in from right, slightly lower
  const phoneDelay  = 20;
  const phoneRotY   = spring({ frame: Math.max(0, frame - phoneDelay), fps, from: -58, to: 9, config: { damping: 13, stiffness: 64 } });
  const phoneX      = spring({ frame: Math.max(0, frame - phoneDelay), fps, from: 420, to: 0, config: { damping: 14, stiffness: 58 } });
  const phoneOp     = interpolate(frame, [phoneDelay, phoneDelay + 18], [0, 1], { extrapolateRight: "clamp" });
  const phoneFloat  = Math.sin(frame * 0.022 + 1.5) * 10;

  // Brand header
  const brandOp = interpolate(frame, [36, 54], [0, 1], { extrapolateRight: "clamp" });
  const brandY  = spring({ frame: Math.max(0, frame - 36), fps, from: 22, to: 0, config: { damping: 10 } });

  return (
    <div style={{ position: "absolute", inset: 0, background: "#03060c", overflow: "hidden", opacity: sceneOp, transform: `scale(${sceneZoom(frame, 300, 0.05)})` }}>

      {/* Grid */}
      <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(56,189,248,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.025) 1px, transparent 1px)", backgroundSize: "90px 90px", pointerEvents: "none" }} />

      {/* Particles */}
      <ParticleField frame={frame} opacity={0.2} />

      {/* Background watermark */}
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        <span style={{ fontFamily: SANS, fontWeight: 900, fontSize: 360, letterSpacing: "-0.07em", color: T.cyan, lineHeight: 1, opacity: 0.026, userSelect: "none" }}>dF.ai</span>
      </div>

      {/* ── Glow behind laptop (left-center) ── */}
      <div style={{
        position: "absolute",
        left: "22%", top: "54%",
        width: 820, height: 700,
        transform: "translate(-50%, -50%)",
        background: "radial-gradient(ellipse at 50% 50%, rgba(56,189,248,0.2) 0%, rgba(56,189,248,0.08) 30%, rgba(56,189,248,0.015) 58%, transparent 74%)",
        opacity: laptopOp * glowPulse,
        pointerEvents: "none",
        mixBlendMode: "screen",
      }} />

      {/* ── Glow behind phone (right-center) ── */}
      <div style={{
        position: "absolute",
        right: "20%", top: "56%",
        width: 520, height: 680,
        transform: "translate(50%, -50%)",
        background: "radial-gradient(ellipse at 50% 50%, rgba(129,140,248,0.18) 0%, rgba(56,189,248,0.08) 34%, transparent 64%)",
        opacity: phoneOp * glowPulse,
        pointerEvents: "none",
        mixBlendMode: "screen",
      }} />

      {/* ── BOTH DEVICES: flex centered in a constrained zone ── */}
      {/* paddingTop keeps devices below the brand header; paddingBottom keeps
          them above the feature chips. Scale is reduced to fit comfortably. */}
      <div style={{
        position: "absolute",
        left: 0, right: 0,
        top: 0, bottom: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 56,
        padding: "190px 56px 110px",
        zIndex: 2,
      }}>

        {/* Laptop — slightly up for stagger */}
        <div style={{ transform: `translateX(${laptopX}px) translateY(-18px)`, opacity: laptopOp, flexShrink: 0 }}>
          <LaptopDevice rotY={laptopRotY} floatY={laptopFloat} scale={0.86}>
            <MiniDashboard />
            <LightSweep frame={frame} start={44} duration={36} />
          </LaptopDevice>
        </div>

        {/* Phone — slightly down for stagger */}
        <div style={{ transform: `translateX(${phoneX}px) translateY(18px)`, opacity: phoneOp, flexShrink: 0 }}>
          <PhoneDevice rotY={phoneRotY} floatY={phoneFloat} scale={0.78}>
            <MiniChat />
            <LightSweep frame={frame} start={44} duration={36} />
          </PhoneDevice>
        </div>
      </div>

      {/* ── Brand header — top center ── */}
      <div style={{
        position: "absolute",
        top: 44, left: "50%",
        transform: `translateX(-50%) translateY(${brandY}px)`,
        opacity: brandOp,
        textAlign: "center",
        zIndex: 4,
        whiteSpace: "nowrap",
      }}>
        <div style={{ fontFamily: MONO, fontSize: 11, color: T.cyan, letterSpacing: "0.24em", marginBottom: 8 }}>● INTRODUCING</div>
        <div style={{ fontFamily: SANS, fontWeight: 900, fontSize: 52, letterSpacing: "-0.04em", lineHeight: 1, color: T.text }}>
          <span style={{ color: T.muted }}>de</span>
          <span style={{ color: T.cyan }}>Flood</span>
          <span>.ai</span>
        </div>
        <div style={{ fontFamily: MONO, fontSize: 13, color: T.muted, marginTop: 9, letterSpacing: "0.12em" }}>
          Jakarta Flood Intelligence System
        </div>
        <div style={{ width: 220, height: 2, background: `linear-gradient(90deg, transparent, ${T.cyan}, transparent)`, margin: "10px auto 0", boxShadow: `0 0 12px ${T.cyan}60` }} />
      </div>

      {/* ── Feature chips — bottom center ── */}
      <div style={{
        position: "absolute",
        bottom: 46, left: "50%",
        transform: "translateX(-50%)",
        display: "flex",
        gap: 9,
        flexWrap: "nowrap",
        zIndex: 4,
      }}>
        {FEATURE_CHIPS.map((f, i) => {
          const delay = 44 + i * 9;
          const chipOp = interpolate(frame, [delay, delay + 20], [0, 1], { extrapolateRight: "clamp" });
          const chipY  = spring({ frame: Math.max(0, frame - delay), fps, from: 14, to: 0, config: { damping: 10 } });
          return (
            <div key={i} style={{
              opacity: chipOp,
              transform: `translateY(${chipY}px)`,
              background: "rgba(5,8,16,0.9)",
              border: `1px solid ${f.color}35`,
              borderBottom: `2px solid ${f.color}`,
              borderRadius: 8,
              padding: "6px 13px",
              display: "flex", alignItems: "center", gap: 7,
            }}>
              <span style={{ fontFamily: MONO, fontSize: 11, color: f.color }}>{f.icon}</span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: f.color, letterSpacing: "0.03em" }}>{f.label}</span>
            </div>
          );
        })}
      </div>

      {/* Vignette */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 86% 80% at 50% 50%, transparent 42%, rgba(0,0,0,0.72) 100%)", pointerEvents: "none", zIndex: 3 }} />
    </div>
  );
}
