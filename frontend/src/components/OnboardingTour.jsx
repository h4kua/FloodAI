import { useState, useEffect, useCallback, useLayoutEffect, useRef } from "react";
import { useApp } from "../lib/appContext";

const TOUR_KEY = "deflood_tour_v8_done";
// The "?" button in the top bar fires this to reopen the guide.
export const OPEN_GUIDE_EVENT = "deflood:open-guide";

/* ── SVG icons ──────────────────────────────────────────── */
const Icons = {
  wave:   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12c1.5-2 3-4 5-4s3.5 4 6 4 4-4 6-4"/><path d="M2 18c1.5-1 3-2 5-2s3.5 2 6 2 4-2 6-2" opacity=".4"/></svg>,
  shield: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  bot:   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><circle cx="8.5" cy="16" r="1" fill="currentColor"/><circle cx="15.5" cy="16" r="1" fill="currentColor"/></svg>,
  check:  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>,
  gauge:  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>,
  grid:   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18"/></svg>,
  map:    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/></svg>,
  list:   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>,
  report: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>,
  info:   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>,
  globe:  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/></svg>,
};

/* ── Steps (plain text, no markup) ─────────────────────────
   Beranda steps point at the page's own sections; a step whose element is
   not on screen (another page open, data still loading) shows centred. */
const STEPS = (id) => [
  {
    key: "welcome", selector: null, icon: Icons.wave, accent: "var(--cyan)",
    title: id ? "Selamat datang di deFlood.ai" : "Welcome to deFlood.ai",
    desc: id
      ? "Panduan singkat ini menunjukkan cara membaca status banjir, mencari rute evakuasi, dan mengirim laporan. Sekitar satu menit."
      : "This short guide shows how to read the flood status, find an evacuation route and send a report. About a minute.",
  },
  {
    key: "status", selector: ".status-hero", icon: Icons.gauge, accent: "var(--s2)",
    title: id ? "Status Jakarta saat ini" : "Jakarta's status now",
    desc: id
      ? "Satu kata: Aman, Waspada, Siaga, atau Bahaya. Diperbarui tiap 15 menit dari pos pantau air DSDA, cuaca, dan peringatan BMKG. Kotak kecilnya menghitung pos pantau per status."
      : "One word: Safe, Watch, Alert or Danger. Updated every 15 minutes from DSDA water posts, the weather and BMKG warnings. The small panel counts the posts at each status.",
  },
  {
    key: "wilayah", selector: ".wilayah-status-list", icon: Icons.grid, accent: "var(--wsp)",
    title: id ? "Status per wilayah" : "Status by area",
    desc: id
      ? "Cek wilayah tempat Anda tinggal atau bekerja. Warnanya mengikuti pos pantau dengan status terparah di wilayah itu."
      : "Check the area where you live or work. Its colour follows the worst water post in that area.",
  },
  {
    key: "map", selector: "#map-anchor", icon: Icons.map, accent: "var(--safe)",
    title: id ? "Peta kondisi air" : "Water map",
    desc: id
      ? "Tiap titik adalah pos pantau, warnanya sama dengan statusnya. Lingkaran merah adalah area rawan banjir yang sedang aktif. Ketuk titik untuk melihat ketinggian airnya."
      : "Each dot is a water post, coloured by its status. Red circles are flood-prone areas that are active now. Tap a dot to see its water level.",
  },
  {
    key: "detail", selector: ".collapsible-section", icon: Icons.list, accent: "var(--cyan)",
    title: id ? "Lihat detail" : "See details",
    desc: id
      ? "Buka bagian ini untuk analisis AI, ketinggian air tiap pos, dan prakiraan cuaca."
      : "Open this for the AI analysis, the water level at every post and the weather forecast.",
  },
  {
    key: "nav-evac", selector: "[data-tour='nav-evac']", icon: Icons.shield, accent: "var(--s1)",
    title: id ? "Evakuasi" : "Evacuation",
    desc: id
      ? "Rute ke rumah Anda atau ke tempat pengungsian terdekat. Jalan hijau aman, jalan merah melewati area rawan banjir. Setelah rutenya cocok, buka di Google Maps untuk navigasi."
      : "A route home or to the nearest shelter. Green roads are clear, red roads pass flood-prone areas. Once the route looks right, open it in Google Maps to navigate.",
  },
  {
    key: "nav-reports", selector: "[data-tour='nav-reports']", icon: Icons.report, accent: "var(--s2)",
    title: id ? "Laporan warga" : "Community reports",
    desc: id
      ? "Lihat dan kirim kabar kondisi air di sekitar Anda, boleh dengan foto. Laporan belum diverifikasi, tampil 6 jam, dan tidak mengubah status resmi."
      : "Read and send updates on the water near you, with a photo if you like. Reports are unverified, shown for 6 hours and never change the official status.",
  },
  {
    key: "nav-about", selector: "[data-tour='nav-about']", icon: Icons.info, accent: "var(--muted)",
    title: id ? "Tentang" : "About",
    desc: id
      ? "Cara kerja deFlood.ai dan batasannya. Tetap ikuti arahan resmi BPBD."
      : "How deFlood.ai works and where its limits are. Always follow official BPBD guidance.",
  },
  {
    key: "settings", selector: ".topbar-right", icon: Icons.globe, accent: "var(--cyan)",
    title: id ? "Bahasa dan tema" : "Language and theme",
    desc: id
      ? "Ganti bahasa Indonesia/English dan mode terang/gelap di sini."
      : "Switch between Indonesian and English, and between light and dark mode, here.",
  },
  {
    key: "chat", selector: ".chatbot-toggle", icon: Icons.bot, accent: "var(--cyan)",
    title: id ? "Tanya AI" : "Ask the AI",
    desc: id
      ? "Ada pertanyaan soal banjir? Ketuk tombol ini dan tanyakan saja."
      : "Questions about flooding? Tap this button and just ask.",
  },
  {
    key: "done", selector: "[data-tour='guide']", icon: Icons.check, accent: "var(--safe)",
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
    // Scroll a page section into view first (the navs and floating buttons
    // are fixed, so they are left alone). On phones the section goes to the
    // top, leaving the lower part of the screen for the card.
    const target = [...document.querySelectorAll(selector)].find((c) => c.getBoundingClientRect().height > 0);
    if (target?.closest(".main")) {
      const r = target.getBoundingClientRect();
      if (window.innerWidth <= 640) {
        if (r.top < 64 || r.top > 140) target.scrollIntoView({ block: "start" });
      } else if (r.top < 64 || r.bottom > window.innerHeight - 80) {
        target.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? "start" : "center" });
      }
    }
    run();
    window.addEventListener("resize", run);
    window.addEventListener("scroll", run, { passive: true });
    return () => {
      window.removeEventListener("resize", run);
      window.removeEventListener("scroll", run);
    };
  }, [selector, active, dep]);
  return rect;
}

/* ── Card position logic ────────────────────────────────── */
/* The card always lies fully between the top bar and the bottom nav, so its
   buttons can be pressed: below the target if it fits, else above it, else
   (a target taller than the free space) on the half of the screen the
   target's centre leaves freer. ``h`` is the card's measured height. */
function getCardStyle(rect, isMobile, h) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const W = Math.min(isMobile ? 340 : 360, vw - 32);
  const GAP = 12;
  const topLimit = 72;                                  // below the top bar
  const bottomLimit = vh - (vw <= 768 ? 76 : 16);       // above the bottom nav
  const maxHeight = bottomLimit - topLimit;

  if (!rect) {
    return { position: "fixed", top: "50%", left: "50%", transform: "translate(-50%,-50%)", width: W, maxHeight };
  }

  const left = isMobile
    ? (vw - W) / 2
    : Math.max(GAP, Math.min(rect.left + rect.width / 2 - W / 2, vw - W - GAP));
  let top;
  if (rect.bottom + GAP + h <= bottomLimit) top = rect.bottom + GAP;
  else if (rect.top - GAP - h >= topLimit) top = rect.top - GAP - h;
  else top = rect.top + rect.height / 2 < vh / 2 ? bottomLimit - h : topLimit;
  top = Math.min(Math.max(top, topLimit), Math.max(topLimit, bottomLimit - h));
  return { position: "fixed", top, left, width: W, maxHeight };
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
  const cardRef = useRef(null);
  const [height, setHeight] = useState(0);
  useLayoutEffect(() => {
    if (cardRef.current) setHeight(cardRef.current.offsetHeight);
  }, [step.key, lang, isMobile]);
  const style = getCardStyle(rect, isMobile, height);

  return (
    <div ref={cardRef} className="tour-card" style={style}>
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

  useEffect(() => {
    const open = () => { setIdx(0); setAnimKey((k) => k + 1); setVisible(true); };
    window.addEventListener(OPEN_GUIDE_EVENT, open);
    return () => window.removeEventListener(OPEN_GUIDE_EVENT, open);
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

  const spotPad = isMobile ? 10 : 7;

  return (
    <>
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
