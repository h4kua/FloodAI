import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { T, MONO, SANS, BODY } from "../tokens";
import { LaptopDevice, LAPTOP_W, LAPTOP_BEZEL } from "../components/LaptopDevice";
import { ParticleField } from "../components/ParticleField";
import { sceneZoom, LightSweep } from "../components/FX";

// ─── Evacuation screen content (inside laptop) ───────────────────────────────
const SHELTERS = [
  { name: "GOR Tanjung Priok",   addr: "Jl. Enggano No.1",      dist: "~4 km · ~10 mnt",  rank: 1 },
  { name: "GOR Kalideres",       addr: "Jl. Daan Mogot Km.19",  dist: "~1.5 km · ~5 mnt", rank: 2 },
];

function EvacScreen({ frame, fps }) {
  const address = "Jl. Pluit Raya, Penjaringan, Jakarta Utara";
  const charCount = Math.floor(interpolate(frame, [18, 58], [0, address.length], { extrapolateRight: "clamp" }));
  const typedAddr = address.slice(0, charCount);

  const resultOp = interpolate(frame, [32, 48], [0, 1], { extrapolateRight: "clamp" });
  const routeProg = interpolate(frame, [22, 65], [0, 1], { extrapolateRight: "clamp" });
  const stepsOp  = interpolate(frame, [18, 38], [0, 1], { extrapolateRight: "clamp" });

  return (
    <div style={{ width: "100%", height: "100%", background: "#0d1117", overflow: "hidden", display: "flex", flexDirection: "column" }}>
      {/* Nav */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 18px", height: 40, borderBottom: "1px solid rgba(48,54,61,0.8)", flexShrink: 0 }}>
        <div style={{ width: 18, height: 18, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", opacity: 0.9 }} />
        <span style={{ fontFamily: MONO, fontSize: 11, color: T.cyan, fontWeight: 700, letterSpacing: "0.1em" }}>deFlood.ai</span>
        <div style={{ flex: 1 }} />
        {["Dashboard","Peta","Chat","Evakuasi"].map(t => (
          <span key={t} style={{ fontFamily: MONO, fontSize: 10, color: t === "Evakuasi" ? T.text : T.muted, padding: "3px 9px", background: t === "Evakuasi" ? "rgba(244,63,94,0.1)" : "transparent", border: `1px solid ${t === "Evakuasi" ? "rgba(244,63,94,0.3)" : "transparent"}`, borderRadius: 5 }}>{t}</span>
        ))}
      </div>

      {/* Content: two columns */}
      <div style={{ flex: 1, display: "flex", gap: 0, overflow: "hidden" }}>
        {/* Left: input + steps */}
        <div style={{ width: "42%", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10, borderRight: "1px solid rgba(48,54,61,0.5)", overflow: "hidden" }}>
          {/* Status alert */}
          <div style={{ background: "rgba(251,191,36,0.07)", border: "1px solid rgba(251,191,36,0.28)", borderRadius: 10, padding: "10px 12px", display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 20 }}>⚠</span>
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, color: T.wsp, letterSpacing: "0.07em" }}>STATUS WASPADA</div>
              <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 13, color: T.text, marginTop: 2 }}>Siapkan rencana evakuasi</div>
            </div>
          </div>

          {/* Address input */}
          <div>
            <div style={{ fontFamily: MONO, fontSize: 9, color: T.muted, marginBottom: 6, letterSpacing: "0.07em" }}>MASUKKAN ALAMATMU</div>
            <div style={{ background: "#1c2333", border: `2px solid ${T.cyanBorder}`, borderRadius: 10, padding: "9px 12px", display: "flex", alignItems: "center", gap: 8, boxShadow: "0 0 16px rgba(56,189,248,0.08)" }}>
              <span style={{ fontSize: 14 }}>📍</span>
              <span style={{ fontFamily: BODY, fontSize: 12, color: T.text, flex: 1 }}>
                {typedAddr}
                {frame > 18 && frame < 62 && <span style={{ borderRight: `2px solid ${T.cyan}`, marginLeft: 1 }}>​</span>}
              </span>
              <div style={{ background: T.cyan, color: T.bg, borderRadius: 7, padding: "5px 11px", fontFamily: MONO, fontSize: 11, fontWeight: 700, flexShrink: 0 }}>Cari →</div>
            </div>
          </div>

          {/* Steps */}
          <div style={{ opacity: stepsOp, flex: 1, overflow: "hidden" }}>
            <div style={{ fontFamily: MONO, fontSize: 9, color: T.muted, marginBottom: 7, letterSpacing: "0.07em" }}>5 LANGKAH EVAKUASI</div>
            {[
              { n: "01", text: "Siapkan tas darurat: KTP, obat, air, senter, power bank." },
              { n: "02", text: "Matikan listrik (MCB) dan tutup katup gas sebelum keluar." },
              { n: "03", text: "Beritahu RT/RW dan anggota keluarga titik kumpul." },
              { n: "04", text: "Masukkan alamat → rute shelter terdekat otomatis." },
              { n: "05", text: "Tidak bisa mandiri? Hubungi BPBD: 117." },
            ].map(s => (
              <div key={s.n} style={{ display: "flex", gap: 8, marginBottom: 7, alignItems: "flex-start" }}>
                <span style={{ fontFamily: MONO, fontSize: 9.5, color: T.cyan, fontWeight: 700, background: "rgba(56,189,248,0.08)", border: `1px solid ${T.cyanBorder}`, borderRadius: 5, padding: "2px 6px", flexShrink: 0 }}>{s.n}</span>
                <span style={{ fontFamily: BODY, fontSize: 11, color: T.muted, lineHeight: 1.55 }}>{s.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: map + shelter cards */}
        <div style={{ flex: 1, padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Map */}
          <div style={{ flex: 1, background: "#080e1a", borderRadius: 10, border: "1px solid rgba(48,54,61,0.7)", position: "relative", overflow: "hidden", minHeight: 180 }}>
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={`h${i}`} style={{ position: "absolute", left: 0, right: 0, top: `${(i+1)*12.5}%`, height: 1, background: "rgba(56,189,248,0.06)" }} />
            ))}
            {Array.from({ length: 9 }).map((_, i) => (
              <div key={`v${i}`} style={{ position: "absolute", top: 0, bottom: 0, left: `${(i+1)*10}%`, width: 1, background: "rgba(56,189,248,0.06)" }} />
            ))}
            <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
              <defs>
                <linearGradient id="rg_evac" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor={T.s2} stopOpacity="0.9" />
                  <stop offset="100%" stopColor={T.safe} stopOpacity="0.9" />
                </linearGradient>
                <filter id="rglow_evac">
                  <feGaussianBlur stdDeviation="2.5" result="b"/>
                  <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
                </filter>
              </defs>
              <path d="M 55 210 Q 130 170 200 145 Q 290 118 390 95 Q 480 76 565 58" stroke="url(#rg_evac)" strokeWidth="3.5" fill="none" strokeDasharray={600} strokeDashoffset={600 - routeProg * 600} strokeLinecap="round" filter="url(#rglow_evac)" />
              <circle cx={55} cy={210} r={7} fill={T.s2} opacity={0.9} />
              <circle cx={55} cy={210} r={13} fill={T.s2} opacity={0.18} />
              {routeProg > 0.85 && <>
                <circle cx={565} cy={58} r={8} fill={T.safe} opacity={0.9} />
                <circle cx={565} cy={58} r={16} fill={T.safe} opacity={0.18} />
              </>}
            </svg>
            {[{ cx:"26%",cy:"68%",c:T.wsp }, { cx:"48%",cy:"50%",c:T.safe }, { cx:"67%",cy:"33%",c:T.safe }, { cx:"77%",cy:"58%",c:T.s2 }].map((d,i) => (
              <div key={i} style={{ position:"absolute", left:d.cx, top:d.cy, width:11, height:11, borderRadius:"50%", background:d.c, border:`2px solid #080e1a`, transform:"translate(-50%,-50%)", boxShadow:`0 0 6px ${d.c}` }} />
            ))}
            <div style={{ position:"absolute", top:10, left:10, fontFamily:MONO, fontSize:10, color:T.cyan, background:"rgba(8,14,26,0.85)", border:`1px solid ${T.cyanBorder}`, borderRadius:6, padding:"3px 8px", letterSpacing:"0.07em" }}>● Peta Risiko Jakarta</div>
          </div>

          {/* Shelter cards */}
          <div style={{ opacity: resultOp }}>
            <div style={{ fontFamily:MONO, fontSize:9, color:T.muted, marginBottom:7, letterSpacing:"0.07em" }}>SHELTER TERDEKAT</div>
            {SHELTERS.map((s,i) => {
              const cOp = interpolate(frame, [32+i*10, 48+i*10], [0,1], { extrapolateRight:"clamp" });
              const cY  = spring({ frame: Math.max(0, frame-32-i*10), fps, from:12, to:0, config:{damping:10} });
              return (
                <div key={i} style={{ background:"#161b22", border:`1px solid ${i===0?T.safeBorder:"rgba(48,54,61,0.7)"}`, borderRadius:10, padding:"10px 14px", marginBottom:8, opacity:cOp, transform:`translateY(${cY}px)`, display:"flex", alignItems:"center", gap:12, boxShadow:i===0?"0 0 18px rgba(52,211,153,0.08)":"none" }}>
                  <div style={{ width:34, height:34, borderRadius:"50%", background:i===0?"rgba(52,211,153,0.1)":"#1c2333", border:`2px solid ${i===0?T.safeBorder:"rgba(48,54,61,0.7)"}`, display:"flex", alignItems:"center", justifyContent:"center", fontFamily:MONO, fontSize:14, fontWeight:700, color:i===0?T.safe:T.muted, flexShrink:0 }}>{i+1}</div>
                  <div style={{ flex:1 }}>
                    <div style={{ fontFamily:SANS, fontWeight:700, fontSize:13, color:T.text }}>{s.name}</div>
                    <div style={{ fontFamily:MONO, fontSize:10, color:T.muted }}>{s.addr}</div>
                    <div style={{ fontFamily:MONO, fontSize:11, color:T.cyan, marginTop:2 }}>{s.dist}</div>
                  </div>
                  {i===0 && <div style={{ background:T.safe, color:T.bg, borderRadius:8, padding:"6px 12px", fontFamily:MONO, fontSize:12, fontWeight:700, boxShadow:"0 4px 10px rgba(52,211,153,0.4)" }}>Rute →</div>}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Feature callouts beside laptop ──────────────────────────────────────────
const EVAC_FEATURES = [
  { icon: "📍", label: "Rute Otomatis",       sub: "Shelter BPBD terdekat"     },
  { icon: "🗺", label: "Peta Risiko Live",    sub: "Overlay sensor realtime"   },
  { icon: "⚡", label: "Akurasi Tinggi",      sub: "Jarak + estimasi waktu"    },
  { icon: "📞", label: "Kontak BPBD 117",     sub: "Hotline evakuasi 24/7"     },
];

// ─── Scene ────────────────────────────────────────────────────────────────────
export function EvacScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sceneOp = interpolate(frame, [0, 14, 62, 75], [0, 1, 1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  // Laptop spins in from left
  const laptopRotY = spring({ frame: Math.max(0, frame - 8), fps, from: 48, to: -9, config: { damping: 14, stiffness: 68 } });
  const laptopX    = spring({ frame: Math.max(0, frame - 8), fps, from: -380, to: 0, config: { damping: 14, stiffness: 60 } });
  const laptopOp   = interpolate(frame, [8, 28], [0, 1], { extrapolateRight: "clamp" });
  const laptopFloat = Math.sin(frame * 0.021) * 9;

  // Feature text from right
  const textDelay = 40;
  const textOp = interpolate(frame, [textDelay, textDelay + 28], [0, 1], { extrapolateRight: "clamp" });
  const textX  = spring({ frame: Math.max(0, frame - textDelay), fps, from: 55, to: 0, config: { damping: 12 } });

  const glowPulse = 0.75 + 0.25 * Math.sin(frame * 0.026);

  return (
    <div style={{ position: "absolute", inset: 0, background: "#03060c", overflow: "hidden", opacity: sceneOp, transform: `scale(${sceneZoom(frame, 270, 0.05)})` }}>
      {/* Ambient */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 100% 70% at 30% 50%, rgba(244,63,94,0.05) 0%, transparent 52%), radial-gradient(ellipse 80% 70% at 30% 50%, rgba(56,189,248,0.04) 0%, transparent 60%)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(56,189,248,0.022) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.022) 1px, transparent 1px)", backgroundSize: "90px 90px", pointerEvents: "none" }} />
      <ParticleField frame={frame} opacity={0.15} />

      {/* Screen glow behind laptop (red-tinted for evac) */}
      <div style={{
        position: "absolute",
        left: 0, top: "50%",
        width: 1100, height: 920,
        transform: "translateY(-50%)",
        background: "radial-gradient(ellipse at 40% 50%, rgba(56,189,248,0.15) 0%, rgba(244,63,94,0.06) 28%, rgba(56,189,248,0.01) 56%, transparent 72%)",
        opacity: laptopOp * glowPulse,
        pointerEvents: "none",
        mixBlendMode: "screen",
      }} />

      {/* Layout */}
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", paddingLeft: 50, paddingRight: 65, gap: 52 }}>

        {/* Laptop */}
        <div style={{ transform: `translateX(${laptopX}px)`, opacity: laptopOp, flexShrink: 0, zIndex: 2, position: "relative" }}>
          <LaptopDevice rotY={laptopRotY} floatY={laptopFloat}>
            <EvacScreen frame={frame} fps={fps} />
            <LightSweep frame={frame} start={36} duration={38} />
          </LaptopDevice>
        </div>

        {/* Feature copy */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", transform: `translateX(${textX}px)`, opacity: textOp }}>
          <div style={{ fontFamily: MONO, fontSize: 13, color: T.s1, letterSpacing: "0.18em", marginBottom: 14 }}>● FITUR 03</div>
          <div style={{ fontFamily: SANS, fontWeight: 900, fontSize: 58, letterSpacing: "-0.04em", lineHeight: 1.0, color: T.text, marginBottom: 18 }}>
            JALUR<br />
            <span style={{ color: T.s1 }}>EVAKUASI</span><br />
            <span style={{ fontSize: 42, color: T.muted }}>OTOMATIS</span>
          </div>
          <div style={{ fontFamily: BODY, fontSize: 17, color: T.muted, lineHeight: 1.7, marginBottom: 32, maxWidth: 420 }}>
            Masukkan alamatmu → dapat rute ke shelter BPBD terdekat secara otomatis, lengkap dengan estimasi jarak dan waktu.
          </div>

          {/* Feature cards */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, maxWidth: 420 }}>
            {EVAC_FEATURES.map((f, i) => {
              const delay = 46 + i * 8;
              const op = interpolate(frame, [delay, delay + 20], [0, 1], { extrapolateRight: "clamp" });
              const cy = spring({ frame: Math.max(0, frame - delay), fps, from: 12, to: 0, config: { damping: 10 } });
              return (
                <div key={i} style={{ background: "#161b22", border: "1px solid rgba(48,54,61,0.8)", borderRadius: 12, padding: "11px 14px", opacity: op, transform: `translateY(${cy}px)`, display: "flex", gap: 10, alignItems: "center" }}>
                  <span style={{ fontSize: 20 }}>{f.icon}</span>
                  <div>
                    <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 13, color: T.text }}>{f.label}</div>
                    <div style={{ fontFamily: MONO, fontSize: 10, color: T.muted, marginTop: 2 }}>{f.sub}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* BPBD badge */}
          <div style={{
            marginTop: 28,
            display: "inline-flex", alignItems: "center", gap: 8,
            background: "rgba(244,63,94,0.07)", border: "1px solid rgba(244,63,94,0.3)",
            borderRadius: 999, padding: "9px 20px",
            opacity: interpolate(frame, [56, 72], [0, 1], { extrapolateRight: "clamp" }),
          }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.s1, display: "block", boxShadow: `0 0 6px ${T.s1}` }} />
            <span style={{ fontFamily: MONO, fontSize: 13, color: T.s1, letterSpacing: "0.06em" }}>Darurat: BPBD 117 · PMI 021-7992325</span>
          </div>
        </div>
      </div>

      {/* Vignette */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 88% 80% at 50% 50%, transparent 48%, rgba(0,0,0,0.65) 100%)", pointerEvents: "none" }} />
    </div>
  );
}
