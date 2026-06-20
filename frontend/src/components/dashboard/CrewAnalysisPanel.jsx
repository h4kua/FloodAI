/* ── CrewAnalysisPanel — "Analisis Mendalam" multi-agent AI button ─────────
   Calls GET /predict/crew-realtime (public, no API key) and displays the
   output from 3 specialized CrewAI agents: AhliCuaca, AhliHidrologi,
   and KoordinatorRisiko.
*/
import { useState, useEffect, useRef } from "react";
import { useApp } from "../../lib/appContext";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const CREW_PURPLE        = "#a855f7";
const CREW_PURPLE_SOFT   = "rgba(168,85,247,0.08)";
const CREW_PURPLE_BORDER = "rgba(168,85,247,0.20)";
const CREW_STATUS_CFG = {
  AMAN:    { color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)" },
  WASPADA: { color: "var(--wsp)",  bg: "var(--wsp-soft)",  border: "var(--wsp-border)"  },
  BAHAYA:  { color: "var(--s1)",   bg: "var(--s1-soft)",   border: "var(--s1-border)"   },
};

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
  const tech       = data?.data_teknis;
  const isFallback = crew?._crew_fallback === true;
  const statusKey  = (crew?.status_banjir || "WASPADA").toUpperCase();
  const statusCfg  = CREW_STATUS_CFG[statusKey] ?? CREW_STATUS_CFG.WASPADA;

  // Simulated agent progress based on elapsed time
  const agentPhase = Math.min(Math.floor(elapsed / 8), 2);

  return (
    <div className="crew-panel fade-in">
      {/* Header */}
      <div className="crew-panel-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <div className="crew-panel-icon">◈</div>
          <div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.63rem", fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: CREW_PURPLE }}>
              {isId ? "ANALISIS MULTI-AGEN AI" : "MULTI-AGENT AI ANALYSIS"}
            </div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem", color: "var(--muted-2)", marginTop: 2 }}>
              CrewAI · {isId ? "3 agen spesialis · Groq LLaMA-3.3" : "3 specialist agents · Groq LLaMA-3.3"}
            </div>
          </div>
        </div>
        {status === "success" && crew?.status_banjir ? (
          <div style={{
            background: statusCfg.bg, border: `1px solid ${statusCfg.border}`,
            borderRadius: "999px", padding: "0.3rem 0.875rem",
            fontFamily: "'JetBrains Mono',monospace", fontSize: "0.72rem",
            fontWeight: 700, color: statusCfg.color, letterSpacing: "0.03em",
          }}>
            {crew.status_banjir}
          </div>
        ) : (
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: CREW_PURPLE, letterSpacing: "0.06em", opacity: 0.8 }}>● AI</span>
        )}
      </div>

      {/* ── Idle ── */}
      {status === "idle" && (
        <div>
          <p style={{ fontSize: "0.825rem", color: "var(--muted)", lineHeight: 1.65, marginBottom: "0.875rem" }}>
            {isId
              ? "Dapatkan analisis mendalam dari 3 agen AI spesialis yang berdiskusi khusus tentang kondisi banjir Jakarta saat ini:"
              : "Get a deep analysis from 3 specialist AI agents deliberating on Jakarta's current flood conditions:"}
          </p>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "1rem" }}>
            {[
              isId ? "Ahli Cuaca" : "Weather Agent",
              isId ? "Ahli Hidrologi" : "Hydrology Agent",
              isId ? "Koordinator Risiko" : "Risk Coordinator",
            ].map(a => (
              <span key={a} style={{
                fontFamily: "'JetBrains Mono',monospace", fontSize: "0.62rem",
                color: CREW_PURPLE, background: CREW_PURPLE_SOFT,
                border: `1px solid ${CREW_PURPLE_BORDER}`,
                borderRadius: "6px", padding: "0.25rem 0.5rem",
              }}>{a}</span>
            ))}
          </div>
          <button
            onClick={run}
            style={{
              width: "100%", padding: "0.75rem", borderRadius: "10px",
              background: CREW_PURPLE_SOFT, border: `1px solid ${CREW_PURPLE_BORDER}`,
              color: CREW_PURPLE, fontFamily: "'JetBrains Mono',monospace",
              fontSize: "0.78rem", fontWeight: 700, letterSpacing: "0.05em",
              cursor: "pointer",
            }}
          >
            {isId ? "▶  Mulai Analisis Mendalam" : "▶  Start Deep Analysis"}
          </button>
          <p style={{ marginTop: "0.5rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem", color: "var(--muted-2)", textAlign: "center" }}>
            {isId ? "Estimasi waktu: 10–30 detik" : "Estimated time: 10–30 seconds"}
          </p>
        </div>
      )}

      {/* ── Loading ── */}
      {status === "loading" && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "1rem", padding: "0.75rem 0" }}>
          <div style={{ display: "flex", gap: "0.375rem" }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{
                width: 8, height: 8, borderRadius: "50%", background: CREW_PURPLE,
                animation: `crew-dot-pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
              }} />
            ))}
          </div>
          <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.72rem", color: CREW_PURPLE, margin: 0, textAlign: "center" }}>
            {isId ? "3 agen AI sedang berdiskusi..." : "3 AI agents deliberating..."}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", width: "100%", maxWidth: 320 }}>
            {[
              [isId ? "Ahli Cuaca" : "Weather Agent",     isId ? "menganalisis kondisi atmosfer & BMKG..." : "analyzing atmosphere & BMKG..."],
              [isId ? "Ahli Hidrologi" : "Hydrology Agent", isId ? "meninjau data TMA & hidrologi sungai..." : "reviewing TMA & river hydrology..."],
              [isId ? "Koordinator" : "Coordinator",         isId ? "menyusun laporan risiko akhir..." : "compiling final risk report..."],
            ].map(([name, action], i) => {
              const done   = i < agentPhase;
              const active = i === agentPhase;
              return (
                <div key={name} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", flexShrink: 0, marginTop: 1, color: done ? "var(--safe)" : active ? CREW_PURPLE : "var(--muted-2)" }}>
                    {done ? "✓" : active ? "●" : "○"}
                  </span>
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.62rem", color: active ? "var(--text)" : "var(--muted-2)", lineHeight: 1.5 }}>
                    {name}{active ? <span style={{ opacity: 0.7 }}> — {action}</span> : ""}
                  </span>
                </div>
              );
            })}
          </div>
          <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", margin: 0 }}>
            {elapsed}s
          </p>
        </div>
      )}

      {/* ── Error ── */}
      {status === "error" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <p style={{ fontSize: "0.8rem", color: "var(--wsp)", margin: 0 }}>
            {isId ? `Analisis gagal: ${errMsg}` : `Analysis failed: ${errMsg}`}
          </p>
          <button
            onClick={reset}
            style={{
              alignSelf: "flex-start", padding: "0.5rem 1rem", borderRadius: "8px",
              background: "rgba(245,166,35,0.08)", border: "1px solid rgba(245,166,35,0.25)",
              color: "var(--wsp)", fontFamily: "'JetBrains Mono',monospace",
              fontSize: "0.65rem", cursor: "pointer",
            }}
          >
            {isId ? "↩ Coba Lagi" : "↩ Retry"}
          </button>
        </div>
      )}

      {/* ── Success ── */}
      {status === "success" && crew && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          {/* Main explanation */}
          <p style={{ fontSize: "0.875rem", color: "var(--text)", lineHeight: 1.75, margin: 0, opacity: 0.9 }}>
            {crew.penjelasan}
          </p>

          {/* Agent analyses — hidden if fallback (no real LLM output) */}
          {!isFallback && (crew.analisis_cuaca || crew.analisis_hidrologi) && (
            <div className="crew-agent-cards">
              {crew.analisis_cuaca && (
                <div style={{
                  background: "rgba(56,189,248,0.06)", border: "1px solid rgba(56,189,248,0.15)",
                  borderRadius: "8px", padding: "0.625rem 0.75rem",
                }}>
                  <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.55rem", color: "var(--cyan)", letterSpacing: "0.08em", marginBottom: "0.35rem" }}>
                    {isId ? "AHLI CUACA" : "WEATHER AGENT"}
                  </div>
                  <p style={{ fontSize: "0.72rem", color: "var(--muted)", lineHeight: 1.6, margin: 0 }}>{crew.analisis_cuaca}</p>
                </div>
              )}
              {crew.analisis_hidrologi && (
                <div style={{
                  background: "rgba(0,229,160,0.05)", border: "1px solid rgba(0,229,160,0.15)",
                  borderRadius: "8px", padding: "0.625rem 0.75rem",
                }}>
                  <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.55rem", color: "var(--safe)", letterSpacing: "0.08em", marginBottom: "0.35rem" }}>
                    {isId ? "AHLI HIDROLOGI" : "HYDROLOGY AGENT"}
                  </div>
                  <p style={{ fontSize: "0.72rem", color: "var(--muted)", lineHeight: 1.6, margin: 0 }}>{crew.analisis_hidrologi}</p>
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          {crew.tindakan?.length > 0 && (
            <div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem", color: "var(--muted-2)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.5rem" }}>
                {isId ? "Tindakan yang Direkomendasikan" : "Recommended Actions"}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
                {crew.tindakan.map((act, i) => (
                  <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: CREW_PURPLE, flexShrink: 0, marginTop: "0.15rem" }}>›</span>
                    <p style={{ fontSize: "0.75rem", color: "var(--muted)", lineHeight: 1.55, margin: 0 }}>{act}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Officer message */}
          {crew.pesan_petugas && (
            <div style={{
              background: CREW_PURPLE_SOFT, border: `1px solid ${CREW_PURPLE_BORDER}`,
              borderRadius: "8px", padding: "0.625rem 0.875rem",
              display: "flex", gap: "0.625rem", alignItems: "flex-start",
            }}>
              <span style={{ width: 6, height: 6, borderRadius: 2, background: CREW_PURPLE, flexShrink: 0, marginTop: 5 }} />
              <div>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.55rem", color: CREW_PURPLE, letterSpacing: "0.08em", marginBottom: "0.25rem" }}>
                  {isId ? "PESAN PETUGAS LAPANGAN" : "FIELD OFFICER MESSAGE"}
                </div>
                <p style={{ fontSize: "0.75rem", color: "var(--text)", margin: 0, lineHeight: 1.55 }}>{crew.pesan_petugas}</p>
              </div>
            </div>
          )}

          {/* Footer: confidence + source + reset */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem", color: "var(--muted-2)", margin: 0, lineHeight: 1.6 }}>
              {crew.tingkat_kepercayaan ? `Kepercayaan: ${crew.tingkat_kepercayaan} · ` : ""}
              {isFallback
                ? (isId ? "Template deterministik (agen AI tidak tersedia)" : "Deterministic template (AI agents unavailable)")
                : (isId ? "Groq LLaMA-3.3 · 3 agen aktif" : "Groq LLaMA-3.3 · 3 active agents")}
              {tech?.pipeline_execution_ms > 0 ? ` · pipeline ${Math.round(tech.pipeline_execution_ms)}ms` : ""}
            </p>
            <button
              onClick={reset}
              style={{
                background: "none", border: "1px solid var(--line)", borderRadius: "6px",
                padding: "0.22rem 0.6rem", cursor: "pointer",
                fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem",
                color: "var(--muted)", letterSpacing: "0.03em",
              }}
            >
              {isId ? "↩ Ulang" : "↩ Reset"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
