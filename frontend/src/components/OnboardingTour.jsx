import { useState, useEffect, useCallback } from "react";
import { useApp } from "../lib/appContext";

const TOUR_KEY = "deflood_tour_v1_done";

const steps = (id) => [
  {
    key: "welcome",
    selector: null,
    position: "center",
    icon: "🌊",
    title: id ? "Selamat datang di deFlood.ai" : "Welcome to deFlood.ai",
    desc: id
      ? "Sistem pemantauan banjir Jakarta berbasis AI yang menggabungkan 38 sensor TMA, XGBoost ML, dan prakiraan BMKG secara realtime. Panduan singkat ini akan menjelaskan fitur-fitur utama."
      : "Jakarta's AI-powered flood monitoring system — combining 38 TMA sensors, XGBoost ML, and live BMKG forecasts. This quick tour explains the key features.",
  },
  {
    key: "nav-home",
    selector: ".nav-btn:first-child",
    position: "bottom",
    icon: "🗺️",
    title: id ? "Command Center" : "Command Center",
    desc: id
      ? "Halaman utama. Tampilkan peta banjir Jakarta realtime, level risiko AI, status 38 stasiun TMA (Siaga 1–4), dan alert BMKG terkini."
      : "Main dashboard. Shows the live Jakarta flood map, AI risk level, status of 38 TMA water-level stations (Siaga 1–4), and latest BMKG alerts.",
  },
  {
    key: "nav-alert",
    selector: ".nav-btn:nth-child(2)",
    position: "bottom",
    icon: "🚨",
    title: id ? "Evakuasi & Rute Aman" : "Evacuation & Safe Routes",
    desc: id
      ? "Cari rute aman dari banjir. Masukkan titik asal dan tujuan untuk mendapatkan rekomendasi rute yang menghindari zona banjir aktif dan menuju shelter terdekat."
      : "Find flood-safe routes. Enter origin and destination to get route recommendations that avoid active flood zones and reach the nearest shelter.",
  },
  {
    key: "nav-about",
    selector: ".nav-btn:nth-child(3)",
    position: "bottom",
    icon: "ℹ️",
    title: id ? "Tentang & Tim" : "About & Team",
    desc: id
      ? "Informasi lengkap tentang sistem, sumber data (BMKG, DSDADKI, OpenWeather), model ML, dan tim pengembang."
      : "Full details about the system, data sources (BMKG, DSDADKI, OpenWeather), ML model specs, and the development team.",
  },
  {
    key: "lang-toggle",
    selector: ".topbar-toggle:first-of-type",
    position: "bottom-left",
    icon: "🌐",
    title: id ? "Ganti Bahasa" : "Switch Language",
    desc: id
      ? "Klik untuk beralih antara Bahasa Indonesia dan English. Semua teks antarmuka akan menyesuaikan secara otomatis."
      : "Click to switch between Bahasa Indonesia and English. All interface text updates automatically.",
  },
  {
    key: "theme-toggle",
    selector: ".topbar-toggle:last-of-type",
    position: "bottom-left",
    icon: "🌙",
    title: id ? "Mode Gelap / Terang" : "Dark / Light Mode",
    desc: id
      ? "Ganti tampilan antara mode gelap (navy) dan mode terang (krem hangat) sesuai preferensi."
      : "Switch between dark mode (navy) and light mode (warm cream) based on your preference.",
  },
  {
    key: "chatbot",
    selector: ".chatbot-toggle",
    position: "top-left",
    icon: "🤖",
    title: id ? "Asisten AI deFlood" : "deFlood AI Assistant",
    desc: id
      ? "Tanya apa saja seputar banjir Jakarta — evakuasi, shelter terdekat, status sungai, atau prakiraan cuaca. Dijawab dalam Bahasa Indonesia maupun Inggris menggunakan Llama 3.3 70B."
      : "Ask anything about Jakarta flooding — evacuation, nearest shelter, river status, or weather forecast. Answered in Indonesian or English using Llama 3.3 70B.",
  },
  {
    key: "done",
    selector: null,
    position: "center",
    icon: "✅",
    title: id ? "Siap memantau banjir!" : "Ready to monitor floods!",
    desc: id
      ? "Kamu sudah mengenal semua fitur utama deFlood.ai. Tour ini bisa diakses kembali kapan saja melalui tombol '?' di pojok bawah. Semoga membantu!"
      : "You now know all the key features of deFlood.ai. This tour can be reopened anytime via the '?' button. Stay safe!",
  },
];

function useHighlight(selector, active) {
  const [rect, setRect] = useState(null);

  useEffect(() => {
    if (!active || !selector) { setRect(null); return; }
    const el = document.querySelector(selector);
    if (!el) { setRect(null); return; }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
  }, [selector, active]);

  return rect;
}

function TooltipCard({ step, idx, total, onNext, onPrev, onSkip, rect }) {
  const { lang } = useApp();
  const id = lang === "id";
  const isFirst = idx === 0;
  const isLast = idx === total - 1;

  let style = {};
  const PAD = 16;
  const CARD_W = 320;

  if (step.position === "center" || !rect) {
    style = {
      position: "fixed",
      top: "50%",
      left: "50%",
      transform: "translate(-50%, -50%)",
      width: CARD_W,
    };
  } else if (step.position === "bottom") {
    style = {
      position: "fixed",
      top: rect.top + rect.height + PAD,
      left: Math.max(PAD, Math.min(rect.left + rect.width / 2 - CARD_W / 2, window.innerWidth - CARD_W - PAD)),
      width: CARD_W,
    };
  } else if (step.position === "bottom-left") {
    style = {
      position: "fixed",
      top: rect.top + rect.height + PAD,
      left: Math.max(PAD, rect.right - CARD_W),
      width: CARD_W,
    };
  } else if (step.position === "top-left") {
    style = {
      position: "fixed",
      bottom: window.innerHeight - rect.top + PAD,
      right: window.innerWidth - rect.right - PAD,
      width: CARD_W,
    };
  }

  return (
    <div className="tour-card" style={style}>
      <div className="tour-card-header">
        <span className="tour-icon">{step.icon}</span>
        <div className="tour-step-count">{idx + 1} / {total}</div>
      </div>
      <p className="tour-title">{step.title}</p>
      <p className="tour-desc">{step.desc}</p>
      <div className="tour-actions">
        {!isFirst && (
          <button className="tour-btn tour-btn-ghost" onClick={onPrev}>
            {id ? "← Kembali" : "← Back"}
          </button>
        )}
        <button className="tour-btn tour-btn-skip" onClick={onSkip}>
          {id ? "Lewati" : "Skip"}
        </button>
        <button className="tour-btn tour-btn-next" onClick={onNext}>
          {isLast ? (id ? "Selesai 🎉" : "Done 🎉") : (id ? "Lanjut →" : "Next →")}
        </button>
      </div>
    </div>
  );
}

export default function OnboardingTour() {
  const { lang } = useApp();
  const id = lang === "id";
  const [visible, setVisible] = useState(false);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (!localStorage.getItem(TOUR_KEY)) {
      setTimeout(() => setVisible(true), 600);
    }
  }, []);

  const finish = useCallback(() => {
    localStorage.setItem(TOUR_KEY, "1");
    setVisible(false);
  }, []);

  const allSteps = steps(id);
  const step = allSteps[idx];
  const rect = useHighlight(step.selector, visible);

  if (!visible) {
    return (
      <button
        className="tour-reopen-btn"
        onClick={() => { setIdx(0); setVisible(true); }}
        title={id ? "Buka panduan" : "Open tour guide"}
      >
        ?
      </button>
    );
  }

  return (
    <>
      {/* Dark overlay */}
      <div className="tour-overlay" onClick={() => {}} />

      {/* Spotlight ring around target */}
      {rect && (
        <div
          className="tour-spotlight"
          style={{
            top: rect.top - 6,
            left: rect.left - 6,
            width: rect.width + 12,
            height: rect.height + 12,
          }}
        />
      )}

      {/* Tooltip card */}
      <TooltipCard
        step={step}
        idx={idx}
        total={allSteps.length}
        rect={rect}
        onNext={() => idx < allSteps.length - 1 ? setIdx(i => i + 1) : finish()}
        onPrev={() => setIdx(i => Math.max(0, i - 1))}
        onSkip={finish}
      />
    </>
  );
}
