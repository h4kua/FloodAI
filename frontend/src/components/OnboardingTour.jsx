import { useState, useEffect, useCallback, useRef } from "react";
import { useApp } from "../lib/appContext";

const TOUR_KEY = "deflood_tour_v2_done";

/* ── SVG icons ─────────────────────────────────────────── */
const IconMap = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="3 11 22 2 13 21 11 13 3 11"/>
  </svg>
);
const IconAlert = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
  </svg>
);
const IconInfo = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
  </svg>
);
const IconGlobe = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
  </svg>
);
const IconSun = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
  </svg>
);
const IconBot = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/>
  </svg>
);
const IconWave = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 12s3-4 6-4 6 8 9 8 5-4 5-4"/>
    <path d="M2 17s3-2 6-2 6 4 9 4 5-2 5-2" opacity=".5"/>
  </svg>
);
const IconCheck = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
);

/* ── Steps ──────────────────────────────────────────────── */
const STEPS = (id) => [
  {
    key: "welcome",
    selector: null,
    position: "center",
    Icon: IconWave,
    accent: "cyan",
    title: id ? "Selamat datang di deFlood.ai" : "Welcome to deFlood.ai",
    desc: id
      ? "Platform pemantauan banjir Jakarta berbasis AI — menggabungkan 38 sensor TMA, model XGBoost, dan prakiraan BMKG secara realtime. Panduan singkat ini akan menjelaskan fitur-fitur utama."
      : "Jakarta's AI-powered flood monitoring platform — combining 38 live TMA sensors, XGBoost ML, and BMKG forecasts. This short guide walks you through the key features.",
  },
  {
    key: "nav-home",
    selector: ".nav-btn:first-child",
    position: "bottom",
    Icon: IconMap,
    accent: "cyan",
    title: id ? "Command Center" : "Command Center",
    desc: id
      ? "Halaman utama dengan peta banjir realtime, level risiko dari model AI, dan status tiap stasiun TMA (Siaga 1–4) yang diperbarui setiap 15 menit."
      : "Main dashboard with a live flood map, AI risk level, and per-station TMA status (Siaga 1–4) updated every 15 minutes.",
  },
  {
    key: "nav-alert",
    selector: ".nav-btn:nth-child(2)",
    position: "bottom",
    Icon: IconAlert,
    accent: "s1",
    title: id ? "Evakuasi & Rute Aman" : "Evacuation & Safe Routes",
    desc: id
      ? "Cari rute yang menghindari zona banjir aktif. Masukkan titik asal dan tujuan untuk mendapatkan rekomendasi rute ke shelter terdekat."
      : "Find routes that bypass active flood zones. Enter origin and destination to get navigation guidance toward the nearest shelter.",
  },
  {
    key: "nav-about",
    selector: ".nav-btn:nth-child(3)",
    position: "bottom",
    Icon: IconInfo,
    accent: "muted",
    title: id ? "Tentang Sistem" : "About the System",
    desc: id
      ? "Dokumentasi lengkap: sumber data, arsitektur model ML, metrik performa, tim pengembang, dan batasan sistem."
      : "Full documentation: data sources, ML model architecture, performance metrics, development team, and system limitations.",
  },
  {
    key: "lang",
    selector: "button[title='Switch language']",
    position: "below-right",
    Icon: IconGlobe,
    accent: "muted",
    title: id ? "Ganti Bahasa" : "Language Toggle",
    desc: id
      ? "Beralih antara Bahasa Indonesia dan English. Seluruh antarmuka dan respons AI akan menyesuaikan secara otomatis."
      : "Switch between Bahasa Indonesia and English. The full interface and AI responses adapt automatically.",
  },
  {
    key: "theme",
    selector: "button[title='Toggle theme']",
    position: "below-right",
    Icon: IconSun,
    accent: "muted",
    title: id ? "Mode Tampilan" : "Display Mode",
    desc: id
      ? "Pilih mode gelap (navy) atau mode terang (krem hangat) sesuai preferensi dan kondisi pencahayaan."
      : "Choose between dark mode (navy) and light mode (warm cream) based on your preference and ambient lighting.",
  },
  {
    key: "chat",
    selector: ".chatbot-toggle",
    position: "top-left",
    Icon: IconBot,
    accent: "cyan",
    title: id ? "Asisten AI" : "AI Assistant",
    desc: id
      ? "Tanya apa saja seputar banjir Jakarta — evakuasi, shelter, status sungai, atau prakiraan cuaca. Menggunakan Llama 3.3 70B dan menyertakan data kondisi aktual Jakarta."
      : "Ask anything about Jakarta flooding — evacuation, shelters, river status, or weather. Powered by Llama 3.3 70B with live Jakarta conditions injected automatically.",
  },
  {
    key: "done",
    selector: null,
    position: "center",
    Icon: IconCheck,
    accent: "safe",
    title: id ? "Siap digunakan" : "You're all set",
    desc: id
      ? "Semua fitur utama sudah dijelaskan. Panduan ini dapat dibuka kembali kapan saja melalui tombol di pojok kiri bawah."
      : "All key features have been covered. You can reopen this guide anytime via the button in the bottom-left corner.",
  },
];

/* ── Highlight hook ─────────────────────────────────────── */
function useTargetRect(selector, active) {
  const [rect, setRect] = useState(null);
  useEffect(() => {
    if (!active || !selector) { setRect(null); return; }
    const measure = () => {
      const el = document.querySelector(selector);
      if (!el) { setRect(null); return; }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [selector, active]);
  return rect;
}

/* ── Card positioning ───────────────────────────────────── */
function cardStyle(position, rect) {
  const GAP = 14;
  const W = 340;
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  if (position === "center" || !rect) {
    return { position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: W };
  }
  // Below element, horizontally centred on element
  if (position === "bottom") {
    const left = Math.max(GAP, Math.min(rect.left + rect.width / 2 - W / 2, vw - W - GAP));
    return { position: "fixed", top: rect.top + rect.height + GAP, left, width: W };
  }
  // Below element, right-edge of card aligned to right-edge of element
  if (position === "below-right") {
    const right = Math.max(GAP, vw - rect.right);
    return { position: "fixed", top: rect.top + rect.height + GAP, right, width: W };
  }
  // Above element from bottom, right-aligned (chatbot)
  if (position === "top-left") {
    const bottom = vh - rect.top + GAP;
    const right = Math.max(GAP, vw - rect.right - rect.width / 2 + W / 2);
    return { position: "fixed", bottom: Math.max(GAP, bottom), right: Math.max(GAP, vw - rect.right), width: W };
  }
  return { position: "fixed", top: "50%", left: "50%", transform: "translate(-50%, -50%)", width: W };
}

/* ── Tour card ──────────────────────────────────────────── */
function TourCard({ step, idx, total, rect, onNext, onPrev, onSkip }) {
  const { lang } = useApp();
  const id = lang === "id";
  const isFirst = idx === 0;
  const isLast = idx === total - 1;
  const progress = ((idx) / (total - 1)) * 100;
  const { Icon, accent } = step;

  const accentColor = {
    cyan: "var(--cyan)",
    s1: "var(--s1)",
    safe: "var(--safe)",
    muted: "var(--muted)",
  }[accent] || "var(--cyan)";

  return (
    <div className="tour-card" style={cardStyle(step.position, rect)} key={step.key}>
      {/* Progress bar — flush top */}
      <div className="tour-progress-track">
        <div className="tour-progress-fill" style={{ width: `${progress}%`, background: accentColor }} />
      </div>

      <div className="tour-inner">
        {/* Header: icon + pip dots */}
        <div className="tour-header">
          <div className="tour-icon-wrap" style={{ color: accentColor, background: `color-mix(in srgb, ${accentColor} 11%, transparent)` }}>
            <Icon />
          </div>
          <div className="tour-step-pip-row">
            {Array.from({ length: total }).map((_, i) => (
              <span key={i} className={`tour-pip${i === idx ? " active" : ""}`} style={i === idx ? { background: accentColor } : {}} />
            ))}
          </div>
        </div>

        <p className="tour-title">{step.title}</p>
        <p className="tour-desc">{step.desc}</p>

        <div className="tour-actions">
          {!isFirst
            ? <button className="tour-btn-ghost" onClick={onPrev}>{id ? "← Kembali" : "← Back"}</button>
            : <span />
          }
          <div className="tour-actions-right">
            {!isLast && (
              <button className="tour-btn-skip" onClick={onSkip}>{id ? "Lewati" : "Skip"}</button>
            )}
            <button className="tour-btn-primary" style={{ background: accentColor }} onClick={onNext}>
              {isLast ? (id ? "Mulai" : "Get started") : (id ? "Lanjut →" : "Next →")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Main component ─────────────────────────────────────── */
export default function OnboardingTour() {
  const { lang } = useApp();
  const id = lang === "id";
  const [visible, setVisible] = useState(false);
  const [idx, setIdx] = useState(0);
  const [animKey, setAnimKey] = useState(0);

  useEffect(() => {
    if (!localStorage.getItem(TOUR_KEY)) {
      const t = setTimeout(() => setVisible(true), 700);
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
  const rect = useTargetRect(step.selector, visible);

  if (!visible) {
    return (
      <button
        className="tour-reopen-btn"
        onClick={() => { setIdx(0); setVisible(true); }}
        title={id ? "Buka panduan" : "Open guide"}
        aria-label={id ? "Buka panduan onboarding" : "Open onboarding guide"}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </button>
    );
  }

  return (
    <>
      {/* Overlay only for center steps — spotlight's box-shadow handles it otherwise */}
      {!rect && <div className="tour-overlay" />}

      {/* Spotlight creates the dark backdrop via box-shadow + exposes the target */}
      {rect && (
        <div
          className="tour-spotlight"
          style={{
            top: rect.top - 8,
            left: rect.left - 8,
            width: rect.width + 16,
            height: rect.height + 16,
          }}
        />
      )}

      <div key={animKey} style={{ animation: "tour-card-in 0.22s cubic-bezier(0.16,1,0.3,1)" }}>
        <TourCard
          step={step}
          idx={idx}
          total={allSteps.length}
          rect={rect}
          onNext={() => idx < allSteps.length - 1 ? goTo(idx + 1) : finish()}
          onPrev={() => goTo(Math.max(0, idx - 1))}
          onSkip={finish}
        />
      </div>
    </>
  );
}
