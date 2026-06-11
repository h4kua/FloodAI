import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";
import { T, MONO, SANS, BODY } from "../tokens";
import { LaptopDevice, LAPTOP_W, LAPTOP_H, LAPTOP_BEZEL } from "../components/LaptopDevice";
import { ParticleField } from "../components/ParticleField";

// ─── Content rendered inside the laptop screen ────────────────────────────────
const SENSORS = [
  { nama: "Manggarai",    ratio: 0.62, cm: "830", s1: "1350", color: null },
  { nama: "Katulampa",    ratio: 0.44, cm: "88",  s1: "200",  color: null },
  { nama: "Pintu Karet",  ratio: 0.71, cm: "780", s1: "1100", color: null },
  { nama: "Waduk Pluit",  ratio: 0.38, cm: "152", s1: "400",  color: null },
];
function sColor(r) { return r >= 0.75 ? T.s2 : r >= 0.50 ? T.wsp : T.safe; }

const WILAYAH = [
  { name: "Jakarta Utara",   icon: "🌧", temp: "28–31°C", status: "Waspada", sc: T.wsp  },
  { name: "Jakarta Selatan", icon: "🌧", temp: "26–30°C", status: "Siaga 3", sc: T.s2   },
  { name: "Jakarta Pusat",   icon: "☁",  temp: "30–33°C", status: "Normal",  sc: T.safe },
  { name: "Jakarta Barat",   icon: "⛅", temp: "29–34°C", status: "Normal",  sc: T.safe },
];

function DashboardScreen({ frame, fps }) {
  const scrollY = interpolate(frame, [100, 280], [0, 155], { extrapolateRight: "clamp" });
  const sparkW  = interpolate(frame, [20, 80], [0, 100], { extrapolateRight: "clamp" });
  const metricOp = interpolate(frame, [22, 46], [0, 1], { extrapolateRight: "clamp" });
  const tableOp  = interpolate(frame, [38, 62], [0, 1], { extrapolateRight: "clamp" });

  const CONTENT_W = LAPTOP_W - LAPTOP_BEZEL * 2;

  return (
    <div style={{ width: "100%", height: "100%", background: "#0d1117", overflow: "hidden", display: "flex", flexDirection: "column", fontSize: 13 }}>
      {/* ── Nav ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 18px", height: 40, borderBottom: "1px solid rgba(48,54,61,0.8)", flexShrink: 0, background: "#0d1117" }}>
        <div style={{ width: 20, height: 20, borderRadius: "50%", background: "linear-gradient(135deg,#22d3ee,#3b82f6)", opacity: 0.9, flexShrink: 0 }} />
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 700, color: T.cyan, letterSpacing: "0.1em" }}>deFlood.ai</span>
        <div style={{ flex: 1 }} />
        {["Dashboard","Peta","Chat","Evakuasi"].map(t => (
          <span key={t} style={{ fontFamily: MONO, fontSize: 10, color: t === "Dashboard" ? T.text : T.muted, padding: "3px 9px", background: t === "Dashboard" ? "rgba(56,189,248,0.1)" : "transparent", border: `1px solid ${t === "Dashboard" ? T.cyanBorder : "transparent"}`, borderRadius: 5 }}>{t}</span>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginLeft: 12 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: T.safe, display: "block", boxShadow: `0 0 5px ${T.safe}` }} />
          <span style={{ fontFamily: MONO, fontSize: 9, color: T.safe }}>LIVE</span>
        </div>
      </div>

      {/* ── Scrollable content ── */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <div style={{ transform: `translateY(-${scrollY}px)`, padding: "14px 18px", display: "flex", flexDirection: "column", gap: 10 }}>

          {/* Status hero */}
          <div style={{ background: "rgba(251,191,36,0.07)", border: "1px solid rgba(251,191,36,0.3)", borderRadius: 12, padding: "12px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: MONO, fontSize: 10, color: T.wsp, letterSpacing: "0.1em", marginBottom: 8 }}>⚠ STATUS WASPADA · UPDATE 3 MENIT LALU</div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div style={{ flex: 1, height: 6, borderRadius: 3, background: "#161b22" }}>
                    <div style={{ width: `${sparkW}%`, maxWidth: "42%", height: "100%", background: `linear-gradient(90deg,${T.safe},${T.wsp})`, borderRadius: 3, boxShadow: `0 0 10px rgba(251,191,36,0.5)` }} />
                  </div>
                  <span style={{ fontFamily: SANS, fontWeight: 800, fontSize: 22, color: T.wsp, lineHeight: 1 }}>42</span>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: T.muted }}>/100</span>
                </div>
                <div style={{ fontFamily: MONO, fontSize: 10, color: T.muted, marginTop: 6 }}>Hujan ringan · 3 sensor siaga · Banjir lokal mungkin terjadi</div>
              </div>
              <div style={{ width: 64, height: 64, borderRadius: "50%", background: "rgba(251,191,36,0.08)", border: `2px solid ${T.wsp}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 26, flexShrink: 0 }}>⚠</div>
            </div>
          </div>

          {/* 4 metric cards */}
          <div style={{ display: "flex", gap: 8, opacity: metricOp }}>
            {[
              { label: "Curah Hujan",   val: "18 mm", sub: "6 jam terakhir",  c: T.cyan },
              { label: "Sensor Aktif",  val: "38",    sub: "DSDADKI online",   c: T.safe },
              { label: "Sta. Siaga",    val: "3",     sub: "dari 38 total",    c: T.wsp  },
              { label: "Pasang Laut",   val: "+14cm",  sub: "rob malam ini",   c: T.s2   },
            ].map(m => (
              <div key={m.label} style={{ flex: 1, background: "#161b22", border: "1px solid rgba(48,54,61,0.9)", borderRadius: 10, padding: "10px 12px" }}>
                <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 20, color: m.c, lineHeight: 1 }}>{m.val}</div>
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: T.muted, marginTop: 5 }}>{m.label}</div>
                <div style={{ fontFamily: MONO, fontSize: 8.5, color: T.muted2, marginTop: 2 }}>{m.sub}</div>
              </div>
            ))}
          </div>

          {/* Wilayah / BMKG strip */}
          <div style={{ opacity: metricOp }}>
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: T.muted, marginBottom: 7, letterSpacing: "0.08em" }}>CURAH HUJAN PER WILAYAH — BMKG</div>
            <div style={{ display: "flex", gap: 7 }}>
              {WILAYAH.map(w => (
                <div key={w.name} style={{ flex: 1, background: "#161b22", border: "1px solid rgba(48,54,61,0.7)", borderRadius: 8, padding: "8px 10px", textAlign: "center" }}>
                  <div style={{ fontSize: 16, marginBottom: 3 }}>{w.icon}</div>
                  <div style={{ fontFamily: MONO, fontSize: 8, color: T.muted, marginBottom: 3 }}>{w.name.replace("Jakarta ", "Jkt ")}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9, padding: "2px 5px", borderRadius: 4, background: `${w.sc}12`, color: w.sc, border: `1px solid ${w.sc}28` }}>{w.status}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Sensor table */}
          <div style={{ opacity: tableOp }}>
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: T.muted, marginBottom: 7, letterSpacing: "0.08em" }}>KETINGGIAN AIR — POS PANTAU</div>
            <div style={{ background: "#0f1420", borderRadius: 10, overflow: "hidden", border: "1px solid rgba(48,54,61,0.7)" }}>
              <div style={{ display: "flex", padding: "7px 12px", borderBottom: "1px solid rgba(48,54,61,0.7)", background: "#0d1117" }}>
                {["Stasiun","Tinggi (cm)","% Siaga 1","Status"].map(h => <span key={h} style={{ flex: 1, fontFamily: MONO, fontSize: 9, color: T.muted, letterSpacing: "0.06em" }}>{h}</span>)}
              </div>
              {SENSORS.map((s, i) => {
                const c = sColor(s.ratio);
                return (
                  <div key={i} style={{ display: "flex", padding: "8px 12px", borderBottom: "1px solid rgba(48,54,61,0.4)", alignItems: "center" }}>
                    <span style={{ flex: 1, fontFamily: BODY, fontSize: 11, color: T.text }}>{s.nama}</span>
                    <span style={{ flex: 1, fontFamily: MONO, fontSize: 11, color: T.muted }}>{s.cm}</span>
                    <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ flex: 1, height: 4, borderRadius: 2, background: "#1c2333" }}>
                        <div style={{ width: `${s.ratio * 100}%`, height: "100%", background: c, borderRadius: 2 }} />
                      </div>
                      <span style={{ fontFamily: MONO, fontSize: 9, color: c, width: 30, textAlign: "right" }}>{Math.round(s.ratio * 100)}%</span>
                    </div>
                    <span style={{ flex: 1, fontFamily: MONO, fontSize: 9, padding: "2px 7px", borderRadius: 5, background: `${c}12`, color: c, border: `1px solid ${c}28`, textAlign: "center" }}>
                      {s.ratio >= 0.75 ? "Siaga 2" : s.ratio >= 0.50 ? "Waspada" : "Aman"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Flood forecast */}
          <div style={{ opacity: tableOp }}>
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: T.muted, marginBottom: 7, letterSpacing: "0.08em" }}>PREDIKSI RISIKO — 24 JAM KE DEPAN</div>
            <div style={{ display: "flex", gap: 6 }}>
              {[
                { time: "Sekarang", label: "Waspada", pct: 42, c: T.wsp  },
                { time: "+6 Jam",   label: "Waspada", pct: 51, c: T.wsp  },
                { time: "+12 Jam",  label: "Siaga 2", pct: 38, c: T.s2   },
                { time: "+24 Jam",  label: "Normal",  pct: 21, c: T.safe },
              ].map(item => (
                <div key={item.time} style={{ flex: 1, background: "#161b22", border: `1px solid ${item.c}28`, borderRadius: 8, padding: "8px 10px", textAlign: "center" }}>
                  <div style={{ fontFamily: MONO, fontSize: 8, color: T.muted2, marginBottom: 4 }}>{item.time}</div>
                  <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 16, color: item.c, lineHeight: 1 }}>{item.pct}%</div>
                  <div style={{ fontFamily: MONO, fontSize: 8, color: item.c, marginTop: 4, padding: "1px 5px", borderRadius: 3, background: `${item.c}14`, display: "inline-block" }}>{item.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Recommended actions */}
          <div style={{ opacity: tableOp }}>
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: T.muted, marginBottom: 6, letterSpacing: "0.08em" }}>REKOMENDASI TINDAKAN</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {[
                { icon: "⚠", text: "Pantau sensor Pintu Karet (71%)",        c: T.wsp  },
                { icon: "📱", text: "Notifikasi siaga — Jkt Selatan aktif",  c: T.s2   },
                { icon: "🗺", text: "Rute evakuasi tersedia — cek peta",     c: T.cyan },
              ].map((a, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, background: "#161b22", borderRadius: 7, padding: "6px 10px", border: `1px solid ${a.c}20` }}>
                  <span style={{ fontSize: 11, flexShrink: 0 }}>{a.icon}</span>
                  <span style={{ fontFamily: MONO, fontSize: 9.5, color: T.muted, flex: 1 }}>{a.text}</span>
                  <span style={{ fontFamily: MONO, fontSize: 9, color: a.c }}>→</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Feature metrics beside laptop ───────────────────────────────────────────
const FEATURES = [
  { val: "38+",  label: "Sensor Aktif",      sub: "Update setiap 15 mnt", c: T.cyan },
  { val: "94%",  label: "Akurasi XGBoost",   sub: "14 fitur cuaca & air", c: T.safe },
  { val: "<1s",  label: "Latency Realtime",  sub: "Streaming DSDADKI",    c: T.wsp  },
];

// ─── Scene ───────────────────────────────────────────────────────────────────
export function DashboardScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sceneOp = interpolate(frame, [0, 14, 304, 330], [0, 1, 1, 0], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });

  // Laptop spins in from left
  const laptopRotY = spring({ frame: Math.max(0, frame - 8), fps, from: 52, to: -10, config: { damping: 14, stiffness: 68 } });
  const laptopX    = spring({ frame: Math.max(0, frame - 8), fps, from: -420, to: 0, config: { damping: 14, stiffness: 60 } });
  const laptopOp   = interpolate(frame, [8, 28], [0, 1], { extrapolateRight: "clamp" });
  const laptopFloat = Math.sin(frame * 0.021) * 10;

  // Feature text slides from right
  const textDelay = 42;
  const textOp = interpolate(frame, [textDelay, textDelay + 28], [0, 1], { extrapolateRight: "clamp" });
  const textX  = spring({ frame: Math.max(0, frame - textDelay), fps, from: 60, to: 0, config: { damping: 12 } });

  const glowPulse = 0.75 + 0.25 * Math.sin(frame * 0.026);

  return (
    <div style={{ position: "absolute", inset: 0, background: "#03060c", overflow: "hidden", opacity: sceneOp }}>
      {/* Ambient */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 100% 70% at 28% 50%, rgba(56,189,248,0.055) 0%, transparent 60%)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", inset: 0, backgroundImage: "linear-gradient(rgba(56,189,248,0.022) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.022) 1px, transparent 1px)", backgroundSize: "90px 90px", pointerEvents: "none" }} />
      <ParticleField frame={frame} opacity={0.16} />

      {/* Screen glow behind laptop */}
      <div style={{
        position: "absolute",
        left: 0, top: "50%",
        width: 1100, height: 920,
        transform: "translateY(-50%)",
        background: "radial-gradient(ellipse at 42% 50%, rgba(56,189,248,0.2) 0%, rgba(56,189,248,0.08) 28%, rgba(56,189,248,0.015) 56%, transparent 72%)",
        opacity: laptopOp * glowPulse,
        pointerEvents: "none",
        mixBlendMode: "screen",
      }} />

      {/* Layout */}
      <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", paddingLeft: 50, paddingRight: 65, gap: 52 }}>

        {/* Laptop */}
        <div style={{ transform: `translateX(${laptopX}px)`, opacity: laptopOp, flexShrink: 0, zIndex: 2, position: "relative" }}>
          <LaptopDevice rotY={laptopRotY} floatY={laptopFloat}>
            <DashboardScreen frame={frame} fps={fps} />
          </LaptopDevice>
        </div>

        {/* Feature copy */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 0, transform: `translateX(${textX}px)`, opacity: textOp }}>
          <div style={{ fontFamily: MONO, fontSize: 13, color: T.cyan, letterSpacing: "0.18em", marginBottom: 14 }}>● FITUR 01</div>
          <div style={{ fontFamily: SANS, fontWeight: 900, fontSize: 58, letterSpacing: "-0.04em", lineHeight: 1.0, color: T.text, marginBottom: 18 }}>
            REALTIME<br />COMMAND<br />
            <span style={{ color: T.cyan }}>CENTER</span>
          </div>
          <div style={{ fontFamily: BODY, fontSize: 17, color: T.muted, lineHeight: 1.7, marginBottom: 36, maxWidth: 460 }}>
            Monitor skor risiko banjir, curah hujan BMKG, dan ketinggian air 38+ sensor DSDADKI — diperbarui setiap 15 menit.
          </div>

          {/* Metric chips */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {FEATURES.map((f, i) => {
              const delay = 62 + i * 18;
              const chipOp = interpolate(frame, [delay, delay + 22], [0, 1], { extrapolateRight: "clamp" });
              const chipY  = spring({ frame: Math.max(0, frame - delay), fps, from: 14, to: 0, config: { damping: 10 } });
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, opacity: chipOp, transform: `translateY(${chipY}px)` }}>
                  <div style={{ fontFamily: SANS, fontWeight: 800, fontSize: 32, color: f.c, lineHeight: 1, width: 70 }}>{f.val}</div>
                  <div>
                    <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 15, color: T.text }}>{f.label}</div>
                    <div style={{ fontFamily: MONO, fontSize: 12, color: T.muted, marginTop: 2 }}>{f.sub}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Live badge */}
          <div style={{
            marginTop: 32,
            display: "inline-flex", alignItems: "center", gap: 8,
            background: "#161b22", border: `1px solid ${T.cyanBorder}`,
            borderRadius: 999, padding: "8px 20px",
            opacity: interpolate(frame, [90, 110], [0, 1], { extrapolateRight: "clamp" }),
          }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.safe, boxShadow: `0 0 6px ${T.safe}`, display: "block" }} />
            <span style={{ fontFamily: MONO, fontSize: 13, color: T.muted, letterSpacing: "0.06em" }}>Live · deflood.ai/dashboard</span>
          </div>
        </div>
      </div>

      {/* Vignette */}
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(ellipse 88% 80% at 50% 50%, transparent 48%, rgba(0,0,0,0.65) 100%)", pointerEvents: "none" }} />
    </div>
  );
}
