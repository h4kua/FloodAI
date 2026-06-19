// deFlood.ai design tokens — matches frontend/src/styles.css exactly

export const T = {
  // Backgrounds
  bg:      "#0d1117",
  panel:   "#161b22",
  panel2:  "#1c2333",
  panel3:  "#21293b",

  // Borders
  line:    "rgba(48, 54, 61, 1)",
  line2:   "rgba(139, 148, 158, 0.18)",

  // Text
  text:    "#e6edf3",
  muted:   "#8b949e",
  muted2:  "#484f58",

  // Brand cyan
  cyan:        "#38bdf8",
  cyanSoft:    "rgba(56, 189, 248, 0.08)",
  cyanBorder:  "rgba(56, 189, 248, 0.20)",

  // Siaga 1 — rose
  s1:        "#f43f5e",
  s1Soft:    "rgba(244, 63, 94, 0.10)",
  s1Border:  "rgba(244, 63, 94, 0.24)",

  // Siaga 2 — orange
  s2:        "#fb923c",
  s2Soft:    "rgba(251, 146, 60, 0.09)",
  s2Border:  "rgba(251, 146, 60, 0.22)",

  // Waspada — amber
  wsp:        "#fbbf24",
  wspSoft:    "rgba(251, 191, 36, 0.09)",
  wspBorder:  "rgba(251, 191, 36, 0.22)",

  // Aman — emerald
  safe:        "#34d399",
  safeSoft:    "rgba(52, 211, 153, 0.08)",
  safeBorder:  "rgba(52, 211, 153, 0.20)",

  // Border radius
  rSm:  8,
  r:    12,
  rLg:  16,
  rXl:  20,

  // Shadows
  shadow:   "0 8px 32px rgba(0, 0, 0, 0.55)",
  shadowSm: "0 2px 12px rgba(0, 0, 0, 0.32)",
};

// Font shorthand helpers — families are loaded via @remotion/google-fonts
import { FONT_SANS, FONT_BODY, FONT_MONO } from "./fonts";

export const MONO = `'${FONT_MONO}', 'Courier New', monospace`;
export const SANS = `'${FONT_SANS}', '${FONT_BODY}', sans-serif`;
export const BODY = `'${FONT_BODY}', system-ui, sans-serif`;

// Status config lookup
export const STATUS_CFG = {
  aman:    { label: "Aman",    color: T.safe, bg: T.safeSoft, border: T.safeBorder },
  waspada: { label: "Waspada", color: T.wsp,  bg: T.wspSoft,  border: T.wspBorder  },
  siaga:   { label: "Siaga",   color: T.s2,   bg: T.s2Soft,   border: T.s2Border   },
  bahaya:  { label: "Bahaya!", color: T.s1,   bg: T.s1Soft,   border: T.s1Border   },
};
