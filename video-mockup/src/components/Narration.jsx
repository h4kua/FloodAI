import React from "react";
import { AbsoluteFill, interpolate } from "remotion";
import { T, MONO, SANS } from "../tokens";

/**
 * Global narration subtitle bar — synced to 21s frame map:
 *   0  –  89  Intro          (90f)
 *  90  – 164  DeviceShowcase (75f)
 * 165  – 284  Dashboard     (120f)
 * 285  – 374  Chat           (90f)
 * 375  – 449  Evac           (75f)
 * 450  – 629  Outro         (180f)
 */

const LINES = [
  // ── Intro ────────────────────────────────────────────────────────────
  { from: 10,  to: 52,  text: "Masih tau banjir Jakarta pas udah kebanjiran?",               hi: "kebanjiran?"    },
  { from: 58,  to: 84,  text: "AI + 38 sensor + BMKG — update tiap 15 mnt, 100% gratis",    hi: "100% gratis"    },

  // ── Device Showcase ──────────────────────────────────────────────────
  { from: 100, to: 158, text: "Dashboard · AI Chat · Peta Evakuasi — semua dalam 1 app",    hi: "1 app"          },

  // ── Dashboard ────────────────────────────────────────────────────────
  { from: 170, to: 225, text: "Pantau risiko banjir Jakarta real-time kayak punya CCTV sendiri", hi: "CCTV sendiri"},
  { from: 232, to: 278, text: "38+ sensor pantau 24/7 — kamu dapat notifikasi duluan",      hi: "duluan"         },

  // ── Chat ─────────────────────────────────────────────────────────────
  { from: 290, to: 335, text: "Flo — AI chatbot yang ngerti bahasa lo, siap 24/7",          hi: "Flo"            },
  { from: 340, to: 370, text: "Tanya lokasi aman, shelter, evakuasi — jawab di bawah 2 detik", hi: "2 detik"     },

  // ── Evac ─────────────────────────────────────────────────────────────
  { from: 382, to: 442, text: "Masukin alamatmu — rute ke shelter BPBD langsung muncul",    hi: "langsung muncul"},

  // ── Outro ────────────────────────────────────────────────────────────
  { from: 462, to: 530, text: "deFlood.ai — lindungi keluargamu dari banjir Jakarta",        hi: "keluargamu"     },
  { from: 542, to: 620, text: "Coba gratis sekarang di deflood.ai — link ada di bio",        hi: "link ada di bio"},
];

function HighlightedText({ text, hi }) {
  if (!hi || !text.includes(hi)) return <span style={{ color: T.text }}>{text}</span>;
  const idx = text.indexOf(hi);
  return (
    <>
      <span style={{ color: T.muted }}>{text.slice(0, idx)}</span>
      <span style={{ color: T.cyan, fontWeight: 700 }}>{hi}</span>
      <span style={{ color: T.muted }}>{text.slice(idx + hi.length)}</span>
    </>
  );
}

export function NarrationOverlay({ frame }) {
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {LINES.map((line, i) => {
        if (frame < line.from - 5 || frame > line.to + 5) return null;

        const opacity = interpolate(frame, [line.from, line.from + 10, line.to - 10, line.to], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        const slideY  = interpolate(frame, [line.from, line.from + 10], [14, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

        return (
          <div key={i} style={{ position: "absolute", bottom: 36, left: "50%", transform: `translateX(-50%) translateY(${slideY}px)`, opacity, whiteSpace: "nowrap" }}>
            <div style={{
              background: "rgba(4,7,14,0.84)",
              backdropFilter: "blur(16px)",
              border: "1px solid rgba(56,189,248,0.18)",
              borderRadius: 999,
              padding: "10px 28px",
              display: "flex", alignItems: "center", gap: 10,
              boxShadow: "0 8px 32px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,255,255,0.03)",
            }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: T.cyan, display: "block", flexShrink: 0, boxShadow: `0 0 6px ${T.cyan}` }} />
              <span style={{ fontFamily: SANS, fontSize: 18, letterSpacing: "0.01em", lineHeight: 1 }}>
                <HighlightedText text={line.text} hi={line.hi} />
              </span>
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
}
