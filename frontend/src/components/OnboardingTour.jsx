import { useState, useEffect, useCallback, useLayoutEffect } from "react";
import { useApp } from "../lib/appContext";

const TOUR_KEY = "deflood_tour_v7_done";

/* ── SVG icons ──────────────────────────────────────────── */
const Icons = {
  wave:   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12c1.5-2 3-4 5-4s3.5 4 6 4 4-4 6-4"/><path d="M2 18c1.5-1 3-2 5-2s3.5 2 6 2 4-2 6-2" opacity=".4"/></svg>,
  shield: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  bot:   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><circle cx="8.5" cy="16" r="1" fill="currentColor"/><circle cx="15.5" cy="16" r="1" fill="currentColor"/></svg>,
  check:  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>,
};

/* ── Steps (plain text, no markup) ─────────────────────── */
const STEPS = (id) => [
  {
    key: "welcome", selector: null, icon: Icons.wave, accent: "var(--cyan)",
    title: id ? "Selamat datang di deFlood.ai" : "Welcome to deFlood.ai",
    desc: id
      ? "Di sini Anda bisa melihat apakah Jakarta aman dari banjir dan apa yang perlu dilakukan."
      : "See whether Jakarta is safe from flooding and what you should do.",
  },
  {
    key: "nav-evac", selector: "[data-tour='nav-evac']", icon: Icons.shield, accent: "var(--s1)",
    title: id ? "Evakuasi" : "Evacuation",
    desc: id
      ? "Temukan tempat pengungsian terdekat dan rute aman ke sana."
      : "Find the nearest shelter and a safe route to get there.",
  },
  {
    key: "chat", selector: ".chatbot-toggle", icon: Icons.bot, accent: "var(--cyan)",
    title: id ? "Tanya AI" : "Ask the AI",
    desc: id
      ? "Ada pertanyaan soal banjir? Ketuk tombol ini dan tanyakan saja."
      : "Questions about flooding? Tap this button and just ask.",
  },
  {
    key: "done", selector: ".tour-reopen-btn", icon: Icons.check, accent: "var(--safe)",
    title: id ? "Selesai" : "All set",
    desc: id
      ? "Ketuk tombol ini kapan saja untuk melihat panduan lagi."
      : "Tap this button anytime to see this guide again.",
  },
];

/* ── Measure target element ─────────────────────────────── */
function useTargetRect(selector, active, dep) {
  const [rect, setRect] = useState(null);
  useLayoutEffect(() => {
    if (!active || !selector) { setRect(null); return; }
    const run = () => {
      // TopBar and BottomNav both carry the same data-tour attribute — pick
      // whichever is actually visible at this viewport (non-zero box).
      const el = [...document.querySelectorAll(selector)]
        .find((candidate) => {
          const r = candidate.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        });
      if (!el) { setRect(null); return; }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, right: r.right, bottom: r.bottom, width: r.width, height: r.height });
    };
    run();
    window.addEventListener("resize", run);
    return () => window.removeEventListener("resize", run);
  }, [selector, active, dep]);
  return rect;
}

/* ── Card position logic ────────────────────────────────── */
function getCardPos(rect, isMobile) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const W = isMobile ? Math.min(312, vw - 32) : 340;
  const GAP = 12;

  // No target — centered
  if (!rect) {
    return { style: { position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: W }, fromTop: false };
  }

  if (isMobile) {
    // Target in bottom 45% → float card near top (below topbar)
    const fromTop = rect.top > vh * 0.45;
    const x = Math.max(16, Math.min(vw / 2 - W / 2, vw - W - 16));
    if (fromTop) {
      return { style: { position: "fixed", top: 64, left: x, width: W }, fromTop: true };
    }
    // 148 clears the fixed bottom nav (64px) + lifted chatbot FAB (54px) + gap
    return { style: { position: "fixed", bottom: 148, left: x, width: W }, fromTop: false };
  }

  // Desktop: prefer below
  const below = vh - rect.bottom > 190;
  const above = rect.top > 190;
  const cx = Math.max(GAP, Math.min(rect.left + rect.width / 2 - W / 2, vw - W - GAP));
  if (below) return { style: { position: "fixed", top: rect.bottom + GAP, left: cx, width: W }, fromTop: true };
  if (above) return { style: { position: "fixed", bottom: vh - rect.top + GAP, left: cx, width: W }, fromTop: false };
  // Fallback right-anchored
  const right = Math.max(GAP, vw - rect.right);
  return { style: { position: "fixed", top: rect.bottom + GAP, right, width: W }, fromTop: true };
}

/* ── Pip dots ───────────────────────────────────────────── */
function Pips({ total, current, accent }) {
  return (
    <div className="tour-pips">
      {Array.from({ length: total }).map((_, i) => (
        <span key={i} className={`tour-pip${i === current ? " on" : ""}`}
          style={i === current ? { background: accent, width: 18 } : {}} />
      ))}
    </div>
  );
}

/* ── Card ───────────────────────────────────────────────── */
function TourCard({ step, idx, total, rect, isMobile, onNext, onPrev, onSkip }) {
  const { lang } = useApp();
  const id = lang === "id";
  const isFirst = idx === 0;
  const isLast = idx === total - 1;
  const { style, fromTop } = getCardPos(rect, isMobile);

  const radiusClass = isMobile
    ? (fromTop ? "tour-card--radius-top" : "tour-card--radius-bottom")
    : "";

  return (
    <div className={`tour-card ${radiusClass}`} style={style}>
      <div className="tour-card-inner">
        {/* Header */}
        <div className="tour-card-head">
          <div className="tour-icon-pill" style={{ color: step.accent, background: `color-mix(in srgb,${step.accent} 12%,transparent)` }}>
            {step.icon}
          </div>
          <Pips total={total} current={idx} accent={step.accent} />
        </div>

        <h2 className="tour-title">{step.title}</h2>
        <p className="tour-desc">{step.desc}</p>

        {/* Footer */}
        <div className="tour-footer">
          <div>
            {!isFirst && (
              <button className="tour-btn-back" onClick={onPrev}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
                {id ? "Kembali" : "Back"}
              </button>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {!isLast && (
              <button className="tour-btn-skip" onClick={onSkip}>{id ? "Lewati" : "Skip"}</button>
            )}
            <button className="tour-btn-next" style={{ background: step.accent }} onClick={onNext}>
              {isLast ? (id ? "Mulai" : "Start") : (id ? "Lanjut" : "Next")}
              {!isLast && <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="9 18 15 12 9 6"/></svg>}
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
  const [isMobile, setIsMobile] = useState(typeof window !== "undefined" && window.innerWidth <= 640);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 640);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    if (!localStorage.getItem(TOUR_KEY)) {
      const t = setTimeout(() => setVisible(true), 600);
      return () => clearTimeout(t);
    }
  }, []);

  const finish = useCallback(() => {
    localStorage.setItem(TOUR_KEY, "1");
    setVisible(false);
  }, []);

  const goTo = useCallback((n) => { setAnimKey(k => k + 1); setIdx(n); }, []);

  const allSteps = STEPS(id);
  const step = allSteps[idx];
  const hasTarget = Boolean(step.selector);
  const rect = useTargetRect(step.selector, visible, animKey);

  const isLastStep = idx === allSteps.length - 1;
  const spotPad = isMobile ? 10 : 7;

  // Help button: always in DOM so spotlight can find it on last step.
  // Hidden (invisible, non-interactive) during tour except on the final step.
  const helpBtnStyle = visible && !isLastStep
    ? { opacity: 0, pointerEvents: "none" }
    : {};

  return (
    <>
      {/* Help / reopen button — always rendered for spotlight targeting */}
      <button
        className="tour-reopen-btn"
        style={helpBtnStyle}
        onClick={!visible ? () => { setIdx(0); setVisible(true); } : undefined}
        title={id ? "Buka panduan" : "Open guide"}
        aria-hidden={visible && !isLastStep}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </button>

      {visible && (
        <>
          {/* Dark backdrop — spotlight handles bg for targeted steps */}
          {(!hasTarget || !rect) && <div className="tour-overlay" />}

          {/* Spotlight cutout */}
          {hasTarget && rect && (
            <div className="tour-spotlight" style={{
              top:    rect.top    - spotPad,
              left:   rect.left   - spotPad,
              width:  rect.width  + spotPad * 2,
              height: rect.height + spotPad * 2,
            }} />
          )}

          {/* Card */}
          <div key={animKey} className="tour-card-anim">
            <TourCard
              step={step} idx={idx} total={allSteps.length}
              rect={rect} isMobile={isMobile}
              onNext={() => idx < allSteps.length - 1 ? goTo(idx + 1) : finish()}
              onPrev={() => goTo(Math.max(0, idx - 1))}
              onSkip={finish}
            />
          </div>
        </>
      )}
    </>
  );
}
