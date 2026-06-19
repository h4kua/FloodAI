import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { T, MONO, SANS, BODY } from "../tokens";
import { PhoneDevice, PHONE_W, PHONE_H, PHONE_STATUS, PHONE_HOME } from "../components/PhoneDevice";
import { ParticleField } from "../components/ParticleField";
import { sceneZoom, LightSweep } from "../components/FX";

// ─── Chat messages ────────────────────────────────────────────────────────────
const MSGS = [
  { role: "ai",   text: "Halo! Saya Flo 👋\nStatus sekarang: ⚠ Waspada.\nKetinggian air 61% ambang Siaga 1.", at: 0   },
  { role: "user", text: "pik aman ga sekarang?",                                                                at: 28  },
  { role: "ai",   text: "PIK = Pantai Indah Kapuk,\nKec. Penjaringan, Jkt Utara.\n\nSensor Waduk Pluit: 38%\n→ Kondisi AMAN ✓\n\nWaspada rob saat pasang tinggi.",  at: 62  },
  { role: "user", text: "shelter terdekat dari pluit?",                                                        at: 120 },
  { role: "ai",   text: "GOR Tanjung Priok\nJl. Enggano No.1\n~4 km · ~10 mnt\n\n→ Buka Evakuasi untuk rute.", at: 152 },
];

function ChatMessage({ msg, frame, fps }) {
  const local = frame - msg.at;
  if (local < 0) return null;
  const op = interpolate(local, [0, 16], [0, 1], { extrapolateRight: "clamp" });
  const y  = spring({ frame: local, fps, from: 14, to: 0, config: { damping: 10 } });
  const isUser = msg.role === "user";
  return (
    <div style={{ display: "flex", justifyContent: isUser ? "flex-end" : "flex-start", marginBottom: 12, opacity: op, transform: `translateY(${y}px)` }}>
      {!isUser && (
        <div style={{ width: 28, height: 28, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 9, color: "#fff", fontWeight: 700, flexShrink: 0, marginRight: 8, marginTop: 2 }}>AI</div>
      )}
      <div style={{ maxWidth: "80%", background: isUser ? "rgba(56,189,248,0.13)" : "#1c2333", border: `1px solid ${isUser ? T.cyanBorder : "rgba(48,54,61,0.8)"}`, borderRadius: isUser ? "14px 4px 14px 14px" : "4px 14px 14px 14px", padding: "9px 12px" }}>
        <pre style={{ fontFamily: BODY, fontSize: 12, color: T.text, lineHeight: 1.6, margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{msg.text}</pre>
        {!isUser && <div style={{ fontFamily: MONO, fontSize: 9, color: T.muted2, marginTop: 5 }}>● Flo · deFlood.ai</div>}
      </div>
    </div>
  );
}

function TypingDots({ frame }) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
      <div style={{ width: 28, height: 28, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 9, color: "#fff", fontWeight: 700, flexShrink: 0 }}>AI</div>
      <div style={{ background: "#1c2333", border: "1px solid rgba(48,54,61,0.8)", borderRadius: "4px 14px 14px 14px", padding: "10px 14px", display: "flex", alignItems: "center", gap: 5 }}>
        {[0,1,2].map(d => {
          const s = 1 + 0.5 * Math.sin(((frame - d * 7) / 8) * Math.PI);
          return <span key={d} style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: T.muted, transform: `scale(${s})` }} />;
        })}
      </div>
    </div>
  );
}

// ─── Phone screen content ─────────────────────────────────────────────────────
function ChatScreen({ frame, fps }) {
  const showTyping1 = frame >= 14 && frame < 62;
  const showTyping2 = frame >= 94 && frame < 120;
  const showTyping3 = frame >= 136 && frame < 152;

  return (
    <div style={{ width: "100%", height: "100%", background: "#0d1117", display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div style={{ padding: "9px 14px", background: "#161b22", borderBottom: "1px solid rgba(48,54,61,0.8)", display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
        <div style={{ width: 36, height: 36, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 12, color: "#fff", fontWeight: 700, flexShrink: 0, boxShadow: "0 4px 12px rgba(56,189,248,0.3)" }}>AI</div>
        <div>
          <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 14, color: T.text }}>Flo — deFlood.ai</div>
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.safe, display: "block", boxShadow: `0 0 5px ${T.safe}` }} />
            <span style={{ fontFamily: MONO, fontSize: 10, color: T.safe }}>AI Online · Groq</span>
          </div>
        </div>
        <div style={{ marginLeft: "auto", fontFamily: MONO, fontSize: 9, color: T.muted2 }}>Jakarta 🗺</div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflow: "hidden", padding: "14px 12px 4px" }}>
        {MSGS.map((m, i) => <ChatMessage key={i} msg={m} frame={frame} fps={fps} />)}
        {(showTyping1 || showTyping2 || showTyping3) && <TypingDots frame={frame} />}
      </div>

      {/* Quick reply chips */}
      <div style={{ padding: "6px 12px", display: "flex", gap: 6, flexShrink: 0, overflow: "hidden" }}>
        {["Harus evakuasi?","Sensor Manggarai?","BPBD 117"].map(q => (
          <div key={q} style={{ fontFamily: MONO, fontSize: 10, padding: "4px 10px", borderRadius: 10, background: "rgba(56,189,248,0.07)", border: `1px solid ${T.cyanBorder}`, color: T.cyan, whiteSpace: "nowrap" }}>{q}</div>
        ))}
      </div>

      {/* Input */}
      <div style={{ padding: "8px 12px", borderTop: "1px solid rgba(48,54,61,0.8)", display: "flex", gap: 8, flexShrink: 0, background: "#0d1117" }}>
        <div style={{ flex: 1, background: "#1c2333", border: "1px solid rgba(48,54,61,0.8)", borderRadius: 12, padding: "9px 14px", fontFamily: BODY, fontSize: 13, color: T.muted2 }}>Tanya kondisi banjir…</div>
        <div style={{ width: 38, height: 38, borderRadius: 11, background: T.cyan, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, color: T.bg, fontWeight: 700, flexShrink: 0, boxShadow: "0 4px 12px rgba(56,189,248,0.4)" }}>▶</div>
      </div>
    </div>
  );
}

// ─── Scene ────────────────────────────────────────────────────────────────────
const CALLOUTS = [
  { icon: "🧠", label: "Groq · LLaMA-3",       sub: "Fast inference AI"          },
  { icon: "🗺", label: "Konteks Jakarta",       sub: "Sensor + BPBD + DSDADKI"   },
  { icon: "💬", label: "Bahasa Informal OK",    sub: "Ngerti pik, jakut, mangdu"  },
  { icon: "⚡", label: "Jawaban < 2 detik",     sub: "Respons realtime"           },
];

export function ChatScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sceneOp = interpolate(frame, [0, 14, 82, 90], [0, 1, 1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  // Phone spins in from right
  const phoneRotY  = spring({ frame: Math.max(0, frame - 8), fps, from: -55, to: 10, config: { damping: 14, stiffness: 68 } });
  const phoneX     = spring({ frame: Math.max(0, frame - 8), fps, from: 420, to: 0, config: { damping: 14, stiffness: 60 } });
  const phoneOp    = interpolate(frame, [8, 28], [0, 1], { extrapolateRight: "clamp" });
  const phoneFloat = Math.sin(frame * 0.022) * 11;

  // Feature text slides from left
  const textDelay = 40;
  const textOp = interpolate(frame, [textDelay, textDelay + 28], [0, 1], { extrapolateRight: "clamp" });
  const textX  = spring({ frame: Math.max(0, frame - textDelay), fps, from: -55, to: 0, config: { damping: 12 } });

  const glowPulse = 0.75 + 0.25 * Math.sin(frame * 0.026);

  return (
    <div style={{ position: "absolute", inset: 0, background: "#03060c", overflow: "hidden", opacity: sceneOp, transform: `scale(${sceneZoom(frame, 300, 0.05)})` }}>
      {/* Ambient */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 80% 80% at 74% 50%, rgba(56,189,248,0.06) 0%, transparent 58%), radial-gradient(ellipse 50% 60% at 8% 50%, rgba(129,140,248,0.03) 0%, transparent 50%)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(56,189,248,0.022) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.022) 1px, transparent 1px)", backgroundSize: "90px 90px", pointerEvents: "none" }} />
      <ParticleField frame={frame} opacity={0.16} />

      {/* Screen glow behind phone */}
      <div style={{
        position: "absolute",
        right: 0, top: "50%",
        width: 780, height: 980,
        transform: "translateY(-50%)",
        background: "radial-gradient(ellipse at 58% 50%, rgba(56,189,248,0.2) 0%, rgba(129,140,248,0.1) 22%, rgba(56,189,248,0.025) 52%, transparent 70%)",
        opacity: phoneOp * glowPulse,
        pointerEvents: "none",
        mixBlendMode: "screen",
      }} />

      {/* ── PHONE — right side, large & centered ── */}
      {/* left:860 → CSS layout center at 860+188=1048, visual at scale 1.25 → ±235px → x:813–1283 */}
      <div style={{
        position: "absolute",
        left: 860, top: "50%",
        transform: `translateY(-50%) translateX(${phoneX}px)`,
        opacity: phoneOp,
        zIndex: 2,
      }}>
        <PhoneDevice rotY={phoneRotY} floatY={phoneFloat} scale={1.25}>
          <ChatScreen frame={frame} fps={fps} />
          <LightSweep frame={frame} start={36} duration={36} />
        </PhoneDevice>
      </div>

      {/* ── Feature text — left side ── */}
      <div style={{
        position: "absolute",
        left: 68, top: "50%",
        transform: `translateY(-50%) translateX(${textX}px)`,
        opacity: textOp,
        width: 680,
        zIndex: 3,
      }}>
        <div style={{ fontFamily: MONO, fontSize: 13, color: T.cyan, letterSpacing: "0.18em", marginBottom: 14 }}>● FITUR 02</div>
        <div style={{ fontFamily: SANS, fontWeight: 900, fontSize: 64, letterSpacing: "-0.04em", lineHeight: 1.0, color: T.text, marginBottom: 18 }}>
          <span style={{ color: T.cyan }}>AI</span> CHATBOT<br />
          <span style={{ fontSize: 54, color: T.muted }}>Flo</span>
        </div>
        <div style={{ fontFamily: BODY, fontSize: 17, color: T.muted, lineHeight: 1.7, marginBottom: 28, maxWidth: 500 }}>
          Tanya kondisi banjir apapun — lokasi, evakuasi, sensor, kontak BPBD. Ngerti bahasa santai dan singkatan lokal Jakarta.
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, maxWidth: 460 }}>
          {CALLOUTS.map((c, i) => {
            const delay = 46 + i * 10;
            const op  = interpolate(frame, [delay, delay + 20], [0, 1], { extrapolateRight: "clamp" });
            const cy  = spring({ frame: Math.max(0, frame - delay), fps, from: 12, to: 0, config: { damping: 10 } });
            return (
              <div key={i} style={{ background: "#161b22", border: "1px solid rgba(48,54,61,0.8)", borderRadius: 12, padding: "11px 14px", opacity: op, transform: `translateY(${cy}px)`, display: "flex", gap: 10, alignItems: "center" }}>
                <span style={{ fontSize: 20 }}>{c.icon}</span>
                <div>
                  <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 13, color: T.text }}>{c.label}</div>
                  <div style={{ fontFamily: MONO, fontSize: 10, color: T.muted, marginTop: 2 }}>{c.sub}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Vignette */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 88% 80% at 50% 50%, transparent 48%, rgba(0,0,0,0.65) 100%)", pointerEvents: "none" }} />
    </div>
  );
}
