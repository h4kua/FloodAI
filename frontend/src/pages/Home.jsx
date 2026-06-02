import { useEffect, useMemo } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import { humanizeRainfall } from "../lib/humanize";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";
import ChatBot from "../components/ChatBot";

/* ── Constants ─────────────────────────────────────────── */
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const BASE_ZONES = [
  { zone: "Penjaringan", district: "Jakarta Utara", bias: +15, tma_base: 900, is_ood: false },
  { zone: "Cengkareng",  district: "Jakarta Barat",  bias: +8,  tma_base: 820, is_ood: false },
  { zone: "Jatinegara",  district: "Jakarta Timur",  bias: +2,  tma_base: 750, is_ood: true  },
  { zone: "Kalideres",   district: "Jakarta Barat",  bias: -8,  tma_base: 640, is_ood: false },
  { zone: "Kebayoran",   district: "Jakarta Selatan", bias: -22, tma_base: 340, is_ood: false },
];

const MOCK_AGENTS = [
  { name: "Prediction Agent",   status: "running",    action: "Memproses data sensor Penjaringan" },
  { name: "Decision Agent",     status: "analyzing",  action: "Evaluasi protokol Siaga aktif"     },
  { name: "Coordination Agent", status: "escalating", action: "Koordinasi zona aktif"             },
  { name: "Execution Agent",    status: "active",     action: "Notifikasi dikirim ke kelurahan"   },
];

function deriveZones(riskScore) {
  return BASE_ZONES.map((z) => {
    const prob = Math.max(0.04, Math.min(0.97, (riskScore + z.bias) / 100));
    let risk_level;
    if (prob >= 0.80) risk_level = "SIAGA_1";
    else if (prob >= 0.55) risk_level = "SIAGA_2";
    else if (prob >= 0.30) risk_level = "WASPADA";
    else risk_level = "NORMAL";
    return {
      ...z,
      probability: prob,
      tma: Math.round(z.tma_base * (0.7 + prob * 0.5)),
      rainfall: Math.round(prob * 85 + 5),
      risk_level,
    };
  });
}

/* ── Risk helpers ──────────────────────────────────────── */
function riskClass(rl) {
  if (rl === "SIAGA_1") return "s1";
  if (rl === "SIAGA_2") return "s2";
  if (rl === "WASPADA") return "wsp";
  return "ok";
}

function RiskBadge({ level }) {
  const cls = riskClass(level);
  return (
    <span className={`risk-badge badge-${cls}`}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor", display: "inline-block" }} />
      {level.replace("_", " ")}
    </span>
  );
}

function ProbBar({ value }) {
  let color = "#00e5a0";
  if (value >= 0.80) color = "#ff3d5a";
  else if (value >= 0.55) color = "#f97316";
  else if (value >= 0.30) color = "#f5a623";
  return (
    <div className="prob-wrap">
      <div className="prob-track">
        <div className="prob-fill" style={{ width: `${value * 100}%`, background: color }} />
      </div>
      <span className="prob-text">{Math.round(value * 100)}%</span>
    </div>
  );
}

/* ── Sub-components ────────────────────────────────────── */
function AlertRibbon({ siaga1Count, siaga2Count, lastSync }) {
  if (siaga1Count > 0) return (
    <div className="alert-ribbon siaga1">
      <span className="ribbon-dot" />
      <span>
        SIAGA 1 AKTIF — <strong>{siaga1Count} zona</strong> memerlukan evakuasi segera.
        Segera hubungi BPBD 117.
      </span>
      <span className="ribbon-ts">
        {lastSync?.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })} WIB
      </span>
    </div>
  );
  if (siaga2Count > 0) return (
    <div className="alert-ribbon siaga2">
      <span className="ribbon-dot" />
      <span>SIAGA 2 — <strong>{siaga2Count} zona</strong> membutuhkan perhatian. Pantau perkembangan.</span>
      <span className="ribbon-ts">
        {lastSync?.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })} WIB
      </span>
    </div>
  );
  return null;
}

function MetricsRow({ siaga1, siaga2, zones, score }) {
  const waspada = zones.filter((z) => z.risk_level === "WASPADA").length;
  const shelterCapacity = Math.round(40 + score * 0.35);
  const wargaTerdampak = ((siaga1 * 4800 + siaga2 * 3200 + waspada * 800)).toLocaleString("id-ID");

  const cards = [
    {
      label: "Zona Siaga",
      value: siaga1 + siaga2,
      sub: `${siaga1} Siaga 1 · ${siaga2} Siaga 2`,
      color: siaga1 > 0 ? "red" : siaga2 > 0 ? "orange" : "green",
    },
    {
      label: "Warga Terdampak",
      value: wargaTerdampak,
      sub: `${waspada} zona waspada aktif`,
      color: "orange",
    },
    {
      label: "Skor Risiko",
      value: score,
      sub: `dari 100 · model XGBoost`,
      color: score >= 70 ? "red" : score >= 45 ? "orange" : "green",
    },
    {
      label: "Shelter Terisi",
      value: `${shelterCapacity}%`,
      sub: `9 shelter aktif · kapasitas terpakai`,
      color: shelterCapacity > 80 ? "orange" : "green",
    },
  ];

  return (
    <div className="cmd-metrics">
      {cards.map((c) => (
        <div key={c.label} className={`metric-card ${c.color}`}>
          <span className="metric-label">{c.label}</span>
          <div>
            <div className={`metric-value ${c.color}`}>{c.value}</div>
            <div className="metric-sub">{c.sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function AlertPanel({ alertZones }) {
  if (alertZones.length === 0) return (
    <div className="panel panel-body">
      <p className="panel-title">Alert Aktif</p>
      <p style={{ fontSize: "0.8rem", color: "var(--muted)", fontFamily: "'JetBrains Mono',monospace" }}>
        Tidak ada zona siaga aktif.
      </p>
    </div>
  );
  return (
    <div className="panel panel-body">
      <p className="panel-title">Alert Aktif</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {alertZones.map((z, i) => (
          <div key={i} className={`alert-item ${riskClass(z.risk_level)}`}>
            <span className="alert-dot" />
            <div>
              <p className="alert-zone-name">{z.zone}</p>
              <p className="alert-zone-sub">TMA {z.tma} cm · {Math.round(z.probability * 100)}%</p>
            </div>
            <RiskBadge level={z.risk_level} />
          </div>
        ))}
      </div>
    </div>
  );
}

function AgentPanel({ score }) {
  const agents = useMemo(() => {
    const base = [...MOCK_AGENTS];
    if (score < 30) base.forEach((a) => { a = { ...a, status: "idle" }; return a; });
    return base;
  }, [score]);

  return (
    <div className="panel panel-body">
      <p className="panel-title">Status Agen AI</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {agents.map((a, i) => (
          <div key={i} className="agent-row">
            <span className={`agent-dot ${a.status}`} />
            <div>
              <p className="agent-name">{a.name}</p>
              <p className="agent-action">{a.action}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecommendationsPanel({ alertZones }) {
  const zone1 = alertZones.find((z) => z.risk_level === "SIAGA_1");
  const zone2 = alertZones.find((z) => z.risk_level === "SIAGA_2");

  const actions = [
    zone1
      ? { label: `Evakuasi ${zone1.zone}`, primary: true,  icon: "!" }
      : { label: "Pantau kondisi sensor",   primary: false, icon: "◉" },
    zone2
      ? { label: `Rute alternatif ${zone2.zone}`, primary: false, icon: "↗" }
      : { label: "Perbarui data cuaca",           primary: false, icon: "↻" },
    { label: "Notifikasi zona Siaga 1", primary: false, icon: "✉" },
  ];

  return (
    <div className="panel panel-body">
      <p className="panel-title">Rekomendasi Aksi</p>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {actions.map((a, i) => (
          <button key={i} className={`action-btn${a.primary ? " primary" : ""}`}>
            <span className="action-icon">{a.icon}</span>
            {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ZoneTable({ zones }) {
  return (
    <div className="panel panel-body fade-in">
      <p className="panel-title">Status Semua Zona DKI Jakarta</p>
      <div className="zone-table-wrap">
        <table className="zone-table">
          <thead>
            <tr>
              {["Zona", "Wilayah", "TMA (cm)", "Hujan mm/j", "Probabilitas", "Status"].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {zones.map((z, i) => (
              <tr key={i}>
                <td>
                  <span className="zone-name">{z.zone}</span>
                  {z.is_ood && <span className="ood-tag">OOD</span>}
                </td>
                <td><span className="zone-district">{z.district}</span></td>
                <td style={{ fontVariantNumeric: "tabular-nums", color: "var(--text)", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.82rem" }}>{z.tma}</td>
                <td style={{ fontVariantNumeric: "tabular-nums", color: "var(--muted)", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.82rem" }}>{z.rainfall}</td>
                <td><ProbBar value={z.probability} /></td>
                <td><RiskBadge level={z.risk_level} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: "0.875rem", padding: "0.625rem 0.75rem", background: "rgba(245,166,35,0.06)", border: "1px solid rgba(245,166,35,0.15)", borderRadius: "10px", display: "flex", alignItems: "center", gap: "0.625rem" }}>
        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--wsp)", flexShrink: 0 }} />
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "var(--muted-2)" }}>
          OOD = Out-of-Distribution — data sensor di luar distribusi training. Prediksi perlu diverifikasi manual.
          Kalibrasi ECE 0.38 — confidence belum sepenuhnya dapat dipercaya.
        </span>
      </div>
    </div>
  );
}

/* ── Page ──────────────────────────────────────────────── */
export default function Home({ setRiskContext, riskLevel }) {
  const { riskData, loading, error, refresh, lastUpdated } = useFloodRisk();
  const level = riskData?.level ?? riskLevel ?? "waspada";
  const score = riskData?.riskScore ?? 45;

  useEffect(() => {
    if (riskData?.level) {
      setRiskContext({ level: riskData.level, rainfall: riskData.rainfall ?? 0 });
    }
  }, [riskData, setRiskContext]);

  const zones       = useMemo(() => deriveZones(score), [score]);
  const siaga1Count = zones.filter((z) => z.risk_level === "SIAGA_1").length;
  const siaga2Count = zones.filter((z) => z.risk_level === "SIAGA_2").length;
  const alertZones  = zones.filter((z) => ["SIAGA_1", "SIAGA_2"].includes(z.risk_level));

  if (loading) return <LoadingSpinner message="Mengambil data realtime..." />;

  if (error) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem", padding: "3rem 1rem", textAlign: "center" }}>
      <p style={{ fontWeight: 700, color: "var(--text)" }}>Gagal memuat data</p>
      <p style={{ fontSize: "0.82rem", color: "var(--muted)" }}>{error}</p>
      <button className="btn btn-ghost" onClick={refresh}>Coba Lagi</button>
    </div>
  );

  return (
    <>
      {/* Alert ribbon */}
      <AlertRibbon siaga1Count={siaga1Count} siaga2Count={siaga2Count} lastSync={lastUpdated} />

      {/* Page header */}
      <div className="page-header fade-in">
        <div>
          <p className="page-eyebrow">// Hydra · Command Center · Operator BPBD</p>
          <h1 className="page-title">Jakarta Flood Intelligence</h1>
        </div>
        <div className="header-actions">
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "var(--muted-2)" }}>
            {lastUpdated
              ? `Sync ${lastUpdated.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })} WIB`
              : "Menunggu sync"}
          </span>
          <button className="btn btn-ghost" onClick={refresh}>Refresh</button>
        </div>
      </div>

      {/* 4 Metric cards */}
      <MetricsRow siaga1={siaga1Count} siaga2={siaga2Count} zones={zones} score={score} />

      {/* Map + Sidebar */}
      <div className="cmd-main fade-in">
        {/* Left: Map + interpretation */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div className="panel map-panel">
            <div className="panel-body" style={{ paddingBottom: "0.75rem" }}>
              <p className="panel-title" style={{ marginBottom: 0 }}>Peta Risiko Banjir — DKI Jakarta · Real-time</p>
            </div>
            <FloodMap riskScore={score} level={level} />
            <div className="map-footer">
              {[
                ["Siaga 1", "#ff3d5a"], ["Siaga 2", "#f97316"],
                ["Waspada", "#f5a623"], ["Normal",  "#00e5a0"],
              ].map(([label, color]) => (
                <div className="map-legend-item" key={label}>
                  <span className="legend-swatch" style={{ background: color }} />
                  <span className="map-legend-label">{label}</span>
                </div>
              ))}
              <span style={{ marginLeft: "auto", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.63rem", color: "var(--muted-2)" }}>
                Klik wilayah untuk detail
              </span>
            </div>
          </div>

          {riskData?.interpretation && (
            <div style={{ background: "rgba(0,207,255,0.05)", border: "1px solid rgba(0,207,255,0.15)", borderLeft: "2px solid var(--cyan)", borderRadius: "12px", padding: "0.875rem 1.125rem", fontSize: "0.82rem", color: "var(--muted)", lineHeight: 1.65 }}>
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--cyan)", letterSpacing: "0.1em", textTransform: "uppercase", marginRight: 8 }}>Model Output</span>
              {riskData.interpretation}
            </div>
          )}
        </div>

        {/* Right: Sidebar */}
        <div className="cmd-sidebar">
          <AlertPanel alertZones={alertZones} />
          <AgentPanel score={score} />
          <RecommendationsPanel alertZones={alertZones} />
        </div>
      </div>

      {/* Zone table */}
      <ZoneTable zones={zones} />

      {/* Floating chatbot */}
      <ChatBot riskContext={{ level, rainfall: riskData?.rainfall }} />
    </>
  );
}
