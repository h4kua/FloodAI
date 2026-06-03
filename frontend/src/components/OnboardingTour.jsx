import { useState, useEffect, useCallback, useLayoutEffect } from "react";
import { useApp } from "../lib/appContext";

const TOUR_KEY = "deflood_tour_v3_done";
const PAD = 16;
const CARD_W = 340;

/* ── SVG icons ─────────────────────────────────────────── */
const Icons = {
  wave: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12c1.5-2 3-4 5-4s3.5 4 6 4 4-4 6-4"/><path d="M2 18c1.5-1 3-2 5-2s3.5 2 6 2 4-2 6-2" opacity=".45"/>
    </svg>
  ),
  map: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="3 11 22 2 13 21 11 13 3 11"/>
    </svg>
  ),
  shield: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  ),
  info: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
    </svg>
  ),
  globe: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </svg>
  ),
  theme: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>
    </svg>
  ),
  bot: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><circle cx="8.5" cy="16" r="1" fill="currentColor"/><circle cx="15.5" cy="16" r="1" fill="currentColor"/>
    </svg>
  ),
  check: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
};

/* ── Rich text helper ───────────────────────────────────── */
// **bold** → bold white text
// [text]   → highlighted pill (background + accent color)
function RichText({ text, accent = "var(--cyan)" }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\[[^\]]+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return (
            <strong key={i} style={{ color: "var(--text)", fontWeight: 700 }}>
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith("[") && part.endsWith("]")) {
          return (
            <span
              key={i}
              className="tour-hl"
              style={{ "--hl": accent }}
            >
              {part.slice(1, -1)}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}

/* ── Steps ──────────────────────────────────────────────── */
const STEPS = (id) => [
  {
    key: "welcome",
    selector: null,
    icon: Icons.wave,
    accent: "var(--cyan)",
    title: id ? "Selamat datang di deFlood.ai" : "Welcome to deFlood.ai",
    desc: id
      ? "Platform [pemantauan banjir Jakarta] berbasis AI — menggabungkan **38 sensor TMA**, model **XGBoost**, dan prakiraan **BMKG** secara realtime. Panduan ini akan menjelaskan fitur-fitur utama."
      : "Jakarta's [AI-powered flood monitoring] platform — combining **38 TMA sensors**, **XGBoost** ML model, and live **BMKG** forecasts. This guide walks you through the key features.",
  },
  {
    key: "nav-home",
    selector: ".nav-btn:first-child",
    icon: Icons.map,
    accent: "var(--cyan)",
    title: id ? "Command Center" : "Command Center",
    desc: id
      ? "Halaman utama dengan [peta banjir realtime], level risiko dari model AI, dan status tiap stasiun TMA (**Siaga 1–4**) yang diperbarui setiap **15 menit**."
      : "Main dashboard with a [live flood map], AI risk level, and per-station TMA status (**Siaga 1–4**) updated every **15 minutes**.",
  },
  {
    key: "nav-alert",
    selector: ".nav-btn:nth-child(2)",
    icon: Icons.shield,
    accent: "var(--s1)",
    title: id ? "Evakuasi & Rute Aman" : "Evacuation & Safe Routes",
    desc: id
      ? "Cari [rute aman dari banjir]. Masukkan titik asal dan tujuan — sistem akan menghindari zona banjir aktif dan memandu ke **shelter terdekat**."
      : "Find [flood-safe routes]. Enter origin and destination — the system avoids active flood zones and guides to the **nearest shelter**.",
  },
  {
    key: "nav-about",
    selector: ".nav-btn:nth-child(3)",
    icon: Icons.info,
    accent: "var(--muted)",
    title: id ? "Tentang Sistem" : "About the System",
    desc: id
      ? "Dokumentasi lengkap: [sumber data], arsitektur **model ML**, metrik performa, tim pengembang, dan batasan sistem."
      : "Full documentation: [data sources], **ML model** architecture, performance metrics, development team, and system limitations.",
  },
  {
    key: "lang",
    selector: "button[title='Switch language']",
    icon: Icons.globe,
    accent: "var(--muted)",
    title: id ? "Ganti Bahasa" : "Language Toggle",
    desc: id
      ? "Klik untuk beralih antara [Bahasa Indonesia] dan [English]. Seluruh antarmuka dan respons AI akan menyesuaikan secara otomatis."
      : "Click to switch between [Bahasa Indonesia] and [English]. The full interface and AI responses adapt automatically.",
  },
  {
    key: "theme",
    selector: "button[title='Toggle theme']",
    icon: Icons.theme,
    accent: "var(--muted)",
    title: id ? "Mode Tampilan" : "Display Mode",
    desc: id
      ? "Pilih antara [mode gelap] (navy) atau [mode terang] (krem hangat) sesuai kondisi pencahayaan dan preferensi."
      : "Choose between [dark mode] (navy) or [light mode] (warm cream) based on your lighting condition and preference.",
  },
  {
    key: "chat",
    selector: ".chatbot-toggle",
    icon: Icons.bot,
    accent: "var(--cyan)",
    title: id ? "Asisten AI" : "AI Assistant",
    desc: id
      ? "Tanya apa saja seputar banjir Jakarta — [evakuasi], [shelter], status sungai, atau prakiraan cuaca. Menggunakan **Llama 3.3 70B** dengan data kondisi Jakarta terkini."
      : "Ask anything about Jakarta flooding — [evacuation], [shelters], river status, weather. Powered by **Llama 3.3 70B** with live Jakarta conditions.",
  },
  {
    key: "done",
    selector: null,
    icon: Icons.check,
    accent: "var(--safe)",
    title: id ? "Siap digunakan" : "You're all set",
    desc: id
      ? "Semua fitur utama sudah dijelaskan. Panduan ini dapat dibuka kembali kapan saja melalui tombol **?** di pojok kiri bawah."
      : "All key features have been covered. You can reopen this guide anytime using the **?** button in the bottom-left corner.",
  },
];

/* ── Measure target rect ────────────────────────────────── */
function useTargetRect(selector, active, animKey) {
  const [rect, setRect] = useState(null);

  useLayoutEffect(() => {
    if (!active || !selector) { setRect(null); return; }
    const measure = () => {
      const el = document.querySelector(selector);
      if (!el) { setRect(null); return; }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height, right: r.right, bottom: r.bottom });
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, { passive: true });
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure);
    };
  }, [selector, active, animKey]);

  return rect;
}

/* ── Smart card position ────────────────────────────────── */
function getCardStyle(rect, isMobile) {
  if (isMobile) {
    return { position: "fixed", bottom: 0, left: 0, right: 0, width: "100%", borderRadius: "20px 20px 0 0" };
  }
  if (!rect) {
    return { position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: CARD_W };
  }

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const spaceBelow = vh - rect.bottom;
  const spaceAbove = rect.top;
  const spaceRight = vw - rect.left;
  const spaceLeft = rect.left;

  // Prefer below if enough space
  if (spaceBelow > 200) {
    const left = Math.max(PAD, Math.min(
      rect.left + rect.width / 2 - CARD_W / 2,
      vw - CARD_W - PAD
    ));
    return { position: "fixed", top: rect.bottom + 12, left, width: CARD_W };
  }
  // Try above
  if (spaceAbove > 200) {
    const left = Math.max(PAD, Math.min(
      rect.left + rect.width / 2 - CARD_W / 2,
      vw - CARD_W - PAD
    ));
    return { position: "fixed", bottom: vh - rect.top + 12, left, width: CARD_W };
  }
  // Fallback: right-align below
  const right = Math.max(PAD, vw - rect.right);
  return { position: "fixed", top: rect.bottom + 12, right: Math.min(right, vw - CARD_W - PAD), width: CARD_W };
}

/* ── Pip progress dots ──────────────────────────────────── */
function Pips({ total, current, accent }) {
  return (
    <div className="tour-pips">
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={`tour-pip${i === current ? " on" : ""}`}
          style={i === current ? { background: accent, width: 20 } : {}}
        />
      ))}
    </div>
  );
}

/* ── Card component ─────────────────────────────────────── */
function TourCard({ step, idx, total, rect, isMobile, onNext, onPrev, onSkip }) {
  const { lang } = useApp();
  const id = lang === "id";
  const isFirst = idx === 0;
  const isLast = idx === total - 1;

  return (
    <div className={`tour-card${isMobile ? " tour-card--mobile" : ""}`} style={getCardStyle(rect, isMobile)}>
      <div className="tour-card-body">
        {/* Top row: icon + pips */}
        <div className="tour-top-row">
          <div className="tour-icon-box" style={{ color: step.accent, background: `color-mix(in srgb, ${step.accent} 10%, transparent)` }}>
            {step.icon}
          </div>
          <Pips total={total} current={idx} accent={step.accent} />
        </div>

        {/* Title */}
        <h2 className="tour-title">{step.title}</h2>

        {/* Description with rich text */}
        <p className="tour-desc">
          <RichText text={step.desc} accent={step.accent} />
        </p>

        {/* Actions */}
        <div className="tour-footer">
          <div className="tour-footer-left">
            {!isFirst && (
              <button className="tour-btn-back" onClick={onPrev}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
                {id ? "Kembali" : "Back"}
              </button>
            )}
          </div>
          <div className="tour-footer-right">
            {!isLast && (
              <button className="tour-btn-skip" onClick={onSkip}>
                {id ? "Lewati" : "Skip"}
              </button>
            )}
            <button className="tour-btn-next" style={{ background: step.accent }} onClick={onNext}>
              {isLast
                ? (id ? "Mulai" : "Start")
                : (id ? "Lanjut" : "Next")}
              {!isLast && (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Main ───────────────────────────────────────────────── */
export default function OnboardingTour() {
  const { lang } = useApp();
  const id = lang === "id";
  const [visible, setVisible] = useState(false);
  const [idx, setIdx] = useState(0);
  const [animKey, setAnimKey] = useState(0);
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 640);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 640);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (!localStorage.getItem(TOUR_KEY)) {
      const t = setTimeout(() => setVisible(true), 500);
      return () => clearTimeout(t);
    }
  }, []);

  const finish = useCallback(() => {
    localStorage.setItem(TOUR_KEY, "1");
    setVisible(false);
  }, []);

  const goTo = useCallback((next) => {
    setAnimKey(k => k + 1);
    setIdx(next);
  }, []);

  const allSteps = STEPS(id);
  const step = allSteps[idx];
  const hasTarget = Boolean(step.selector);
  const rect = useTargetRect(step.selector, visible, animKey);

  if (!visible) {
    return (
      <button className="tour-reopen-btn" onClick={() => { setIdx(0); setVisible(true); }}
        title={id ? "Buka panduan" : "Open guide"}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </button>
    );
  }

  return (
    <>
      {/* Overlay: shown for center steps; spotlight handles bg for targeted steps */}
      {!hasTarget && <div className="tour-overlay" />}

      {/* Spotlight cutout — box-shadow darkens everything outside, target element visible */}
      {hasTarget && rect && (() => {
        const pad = isMobile ? 10 : 8;
        return (
          <div
            className="tour-spotlight"
            style={{
              top:    rect.top    - pad,
              left:   rect.left   - pad,
              width:  rect.width  + pad * 2,
              height: rect.height + pad * 2,
            }}
          />
        );
      })()}

      {/* Fallback dark bg when selector not found yet */}
      {hasTarget && !rect && <div className="tour-overlay" />}

      {/* Card */}
      <div
        key={animKey}
        className="tour-card-anim"
        style={{ zIndex: 9003, position: "fixed", inset: 0, pointerEvents: "none" }}
      >
        <TourCard
          step={step}
          idx={idx}
          total={allSteps.length}
          rect={rect}
          isMobile={isMobile}
          onNext={() => idx < allSteps.length - 1 ? goTo(idx + 1) : finish()}
          onPrev={() => goTo(Math.max(0, idx - 1))}
          onSkip={finish}
        />
      </div>
    </>
  );
}
