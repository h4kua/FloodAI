/* ── CrewAnalysisPanel — opt-in "Analisis Mendalam" inside the AI card ─────
   Calls GET /predict/crew-realtime (public, no API key), which runs 3
   specialist agents server-side. The UI keeps it minimal: one button, then
   one explanation + at most 3 actions. Per-agent breakdowns stay out of view.
*/
import { useState, useEffect, useRef } from "react";
import { useApp } from "../../lib/appContext";

import { API_BASE } from "../../lib/api";

export function CrewAnalysisPanel() {
  const { lang } = useApp();
  const isId = lang === "id";
  const [status, setStatus]   = useState("idle"); // idle | loading | success | error
  const [data,   setData]     = useState(null);
  const [errMsg, setErrMsg]   = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef(null);

  useEffect(() => () => clearInterval(timerRef.current), []);

  const run = async () => {
    setStatus("loading");
    setElapsed(0);
    setData(null);
    setErrMsg(null);
    timerRef.current = setInterval(() => setElapsed(v => v + 1), 1000);
    try {
      const res = await fetch(`${API_BASE}/predict/crew-realtime`);
      if (!res.ok) throw new Error(`${res.status}`);
      setData(await res.json());
      setStatus("success");
    } catch (e) {
      setErrMsg(e.message || "Terjadi kesalahan");
      setStatus("error");
    } finally {
      clearInterval(timerRef.current);
    }
  };

  const reset = () => { setStatus("idle"); setData(null); setErrMsg(null); setElapsed(0); };

  const crew       = data?.analisis_crew;
  const isFallback = crew?._crew_fallback === true;
  const actions    = (crew?.tindakan ?? []).slice(0, 3);

  return (
    <div className="crew-deep">
      {status === "idle" && (
        <button className="crew-run-btn" onClick={run}>
          <span>{isId ? "Analisis mendalam dengan AI" : "Deep analysis with AI"}</span>
          <small>{isId ? "10–30 dtk" : "10–30 s"}</small>
        </button>
      )}

      {status === "loading" && (
        <div className="crew-loading">
          <span className="crew-dots">
            {[0, 1, 2].map(i => <i key={i} style={{ animationDelay: `${i * 0.2}s` }} />)}
          </span>
          <span>{isId ? "AI sedang menganalisis…" : "AI is analysing…"} {elapsed}s</span>
        </div>
      )}

      {status === "error" && (
        <div className="crew-error">
          <span>{isId ? `Analisis gagal (${errMsg}).` : `Analysis failed (${errMsg}).`}</span>
          <button className="ai-card-more" onClick={reset}>{isId ? "Coba lagi" : "Retry"}</button>
        </div>
      )}

      {status === "success" && crew && (
        <div className="crew-result">
          <p className="crew-result-text">{crew.penjelasan}</p>

          {actions.length > 0 && (
            <ul className="crew-actions">
              {actions.map((act, i) => <li key={i}>{act}</li>)}
            </ul>
          )}

          <div className="crew-result-foot">
            <span>
              {isFallback
                ? (isId ? "Template otomatis (agen AI tidak tersedia)" : "Automatic template (AI agents unavailable)")
                : (isId ? "Dianalisis oleh 3 agen AI" : "Analysed by 3 AI agents")}
            </span>
            <button className="ai-card-more" onClick={reset}>{isId ? "Tutup" : "Close"}</button>
          </div>
        </div>
      )}
    </div>
  );
}
