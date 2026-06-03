import { useEffect, useMemo } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import { humanizeRainfall } from "../lib/humanize";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";
import ChatBot from "../components/ChatBot";
import { useT, useApp } from "../lib/appContext";

/* ── Constants ─────────────────────────────────────────── */

// Bias values derived from BPBD flood event frequency 2024-2026 (scripts/process_bpbd.py)
// Higher bias = more flood-prone based on actual kejadian data
const BASE_ZONES = [
  { zone: "Kebayoran",   district: "Jakarta Selatan", bias: +20, tma_base: 340, is_ood: false },
  { zone: "Penjaringan", district: "Jakarta Utara",   bias:  +6, tma_base: 900, is_ood: false },
  { zone: "Jatinegara",  district: "Jakarta Timur",   bias:  +6, tma_base: 750, is_ood: true  },
  { zone: "Kalideres",   district: "Jakarta Barat",   bias:  +4, tma_base: 640, is_ood: false },
  { zone: "Cengkareng",  district: "Jakarta Barat",   bias:  -1, tma_base: 820, is_ood: false },
];

function getAgentStatuses(level, t) {
  const map = {
    aman: [
      { name: "Prediction Agent",   status: "idle",     actionKey: "agent.idle1" },
      { name: "Decision Agent",     status: "idle",     actionKey: "agent.idle2" },
      { name: "Coordination Agent", status: "idle",     actionKey: "agent.idle3" },
      { name: "Execution Agent",    status: "idle",     actionKey: "agent.idle4" },
    ],
    waspada: [
      { name: "Prediction Agent",   status: "running",   actionKey: "agent.w1" },
      { name: "Decision Agent",     status: "analyzing", actionKey: "agent.w2" },
      { name: "Coordination Agent", status: "idle",      actionKey: "agent.w3" },
      { name: "Execution Agent",    status: "idle",      actionKey: "agent.idle4" },
    ],
    siaga: [
      { name: "Prediction Agent",   status: "running",    actionKey: "agent.s1" },
      { name: "Decision Agent",     status: "analyzing",  actionKey: "agent.s2" },
      { name: "Coordination Agent", status: "escalating", actionKey: "agent.s3" },
      { name: "Execution Agent",    status: "active",     actionKey: "agent.s4" },
    ],
    bahaya: [
      { name: "Prediction Agent",   status: "running",    actionKey: "agent.d1" },
      { name: "Decision Agent",     status: "analyzing",  actionKey: "agent.d2" },
      { name: "Coordination Agent", status: "escalating", actionKey: "agent.d3" },
      { name: "Execution Agent",    status: "active",     actionKey: "agent.d4" },
    ],
  };
  return (map[level] ?? map.waspada).map(a => ({ ...a, action: t(a.actionKey) }));
}

// waterLevelRatio: real sensor reading from DSDADKI (0–1.5 scale).
// TMA now tracks real sensor data — when WLR rises, all zone TMA values rise.
// Per-zone bias (z.bias / 200) preserves flood-frequency differentiation
// (Kebayoran historically more flood-prone = higher TMA estimate than Cengkareng).
function deriveZones(riskScore, realRainfall = 0, waterLevelRatio = 0.5) {
  const wlr = Math.max(0.3, Math.min(1.5, waterLevelRatio));
  return BASE_ZONES.map((z) => {
    const prob = Math.max(0.04, Math.min(0.97, (riskScore + z.bias) / 100));
    let risk_level;
    if (prob >= 0.80) risk_level = "SIAGA_1";
    else if (prob >= 0.55) risk_level = "SIAGA_2";
    else if (prob >= 0.30) risk_level = "WASPADA";
    else risk_level = "NORMAL";
    // TMA uses real WLR + per-zone historical bias so the value changes when
    // sensors report rising water, not only when ML probability changes.
    const wlrBiased = Math.min(1.5, Math.max(0.3, wlr + z.bias / 200));
    return {
      ...z,
      probability: prob,
      tma: Math.round(z.tma_base * wlrBiased),
      rainfall: realRainfall,
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
  const t = useT();
  const cls = riskClass(level);
  return (
    <span className={`risk-badge badge-${cls}`}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor", display: "inline-block" }} />
      {t(`risk.${level}`) || level.replace("_", " ")}
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
  const t = useT();
  const ts = lastSync?.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
  if (siaga1Count > 0) return (
    <div className="alert-ribbon siaga1">
      <span className="ribbon-dot" />
      <span>{t("ribbon.s1", { n: siaga1Count })}</span>
      {ts && <span className="ribbon-ts">{ts} WIB</span>}
    </div>
  );
  if (siaga2Count > 0) return (
    <div className="alert-ribbon siaga2">
      <span className="ribbon-dot" />
      <span>{t("ribbon.s2", { n: siaga2Count })}</span>
      {ts && <span className="ribbon-ts">{ts} WIB</span>}
    </div>
  );
  return null;
}

function MetricsRow({ siaga1, siaga2, zones, score, rainfall }) {
  const t = useT();
  const { lang } = useApp();
  const waspada = zones.filter((z) => z.risk_level === "WASPADA").length;
  const wargaEst = (siaga1 * 4800 + siaga2 * 3200 + waspada * 800).toLocaleString("id-ID");
  const rainMm = rainfall ?? 0;

  const cards = [
    {
      label: t("metric.alertZones"),
      value: siaga1 + siaga2,
      sub: t("metric.alertSub", { s1: siaga1, s2: siaga2 }),
      note: t("metric.est"),
      color: siaga1 > 0 ? "red" : siaga2 > 0 ? "orange" : "green",
    },
    {
      label: t("metric.affected"),
      value: (siaga1 + siaga2 + waspada) > 0 ? `~${wargaEst}` : "0",
      sub: t("metric.affectedSub", { n: waspada }),
      note: t("metric.est"),
      color: siaga1 > 0 ? "red" : siaga2 > 0 ? "orange" : "green",
    },
    {
      label: t("metric.riskScore"),
      value: score,
      sub: t("metric.riskSub"),
      note: t("metric.real"),
      color: score >= 70 ? "red" : score >= 45 ? "orange" : "green",
    },
    {
      label: t("metric.rainfall"),
      // Use humanizeRainfall so 0 shows "Tidak ada hujan" instead of plain "0"
      value: humanizeRainfall(rainMm, lang),
      sub: rainMm > 0 ? `${Math.round(rainMm)} mm/jam` : t("metric.rainSub"),
      note: t("metric.real"),
      color: rainMm >= 50 ? "red" : rainMm >= 20 ? "orange" : "green",
    },
  ];

  return (
    <div className="cmd-metrics">
      {cards.map((c) => (
        <div key={c.label} className={`metric-card ${c.color}`}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span className="metric-label">{c.label}</span>
            {c.note && (
              <span style={{
                fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem",
                color: c.note === "data real" ? "var(--safe)" : "var(--muted-2)",
                letterSpacing: "0.06em", opacity: 0.8,
              }}>
                {c.note === "data real" ? "● real" : "○ est."}
              </span>
            )}
          </div>
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
  const t = useT();
  if (alertZones.length === 0) return (
    <div className="panel panel-body">
      <p className="panel-title">{t("alert.title")}</p>
      <p style={{ fontSize: "0.8rem", color: "var(--muted)", fontFamily: "'JetBrains Mono',monospace" }}>
        {t("alert.none")}
      </p>
    </div>
  );
  return (
    <div className="panel panel-body">
      <p className="panel-title">{t("alert.title")}</p>
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

function AgentPanel({ level }) {
  const t = useT();
  const agents = useMemo(() => getAgentStatuses(level, t), [level, t]);

  return (
    <div className="panel panel-body">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>{t("agent.title")}</p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)", letterSpacing: "0.06em" }}>
          {t("agent.sim")}
        </span>
      </div>
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

function SensorStrip({ riskData }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!riskData) return null;

  const wlr   = riskData.waterLevelRatio;
  const delta = riskData.waterLevelDelta;   // real per-15-min change in WLR
  const wlColor  = wlr >= 0.90 ? "var(--s1)" : wlr >= 0.75 ? "var(--wsp)" : "var(--safe)";
  const riskTrend = riskData.trendState?.risk_trend;
  const trendLabel = riskTrend === "increasing"
    ? (isId ? "↑ Naik" : "↑ Rising")
    : riskTrend === "decreasing"
    ? (isId ? "↓ Turun" : "↓ Falling")
    : (isId ? "→ Stabil" : "→ Stable");
  const trendColor = riskTrend === "increasing" ? "var(--wsp)" : riskTrend === "decreasing" ? "var(--safe)" : "var(--muted)";

  // Water level delta direction (real 15-min sensor change, not ML trend)
  const wldSign  = delta != null ? (delta > 0.015 ? "↑" : delta < -0.015 ? "↓" : "→") : null;
  const wldColor = delta != null
    ? (delta > 0.015 ? "var(--wsp)" : delta < -0.015 ? "var(--safe)" : "var(--muted)")
    : "var(--muted)";

  // 3h rainfall accumulation (complementary to 6h already shown)
  const acc3h = riskData.rainfallAcc3h;
  // Rainfall trend mm/h (positive = intensifying, negative = easing)
  const rfTrend = riskData.rainfallTrendMmH;

  return (
    <div className="sensor-strip fade-in">
      {/* Water level — real ratio + direction arrow from sensor delta */}
      {wlr !== null && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Muka Air" : "Water Level"}</span>
          <span className="sensor-chip-value" style={{ color: wlColor }}>
            {Math.round(wlr * 100)}%
            {wldSign && (
              <span style={{ marginLeft: 3, fontSize: "0.7rem", color: wldColor }}>{wldSign}</span>
            )}
          </span>
        </div>
      )}

      {riskData.temperature !== null && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Suhu" : "Temp"}</span>
          <span className="sensor-chip-value">{riskData.temperature?.toFixed(1)}°C</span>
        </div>
      )}
      {riskData.humidity !== null && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Kelembapan" : "Humidity"}</span>
          <span className="sensor-chip-value">{Math.round(riskData.humidity)}%</span>
        </div>
      )}

      {/* 3h accumulation — more immediate than 6h for sudden rain events */}
      {acc3h != null && acc3h > 0 && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Akum. 3j" : "3h Accum"}</span>
          <span className="sensor-chip-value" style={{ color: acc3h >= 15 ? "var(--wsp)" : undefined }}>
            {acc3h.toFixed(1)} mm
          </span>
        </div>
      )}
      {riskData.rainfallAcc6h != null && riskData.rainfallAcc6h > 0 && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Akum. 6j" : "6h Accum"}</span>
          <span className="sensor-chip-value" style={{ color: riskData.rainfallAcc6h >= 20 ? "var(--wsp)" : undefined }}>
            {riskData.rainfallAcc6h} mm
          </span>
        </div>
      )}

      {/* Rainfall trend: positive = rain intensifying */}
      {rfTrend != null && Math.abs(rfTrend) >= 1 && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Tren Hujan" : "Rain Trend"}</span>
          <span className="sensor-chip-value" style={{ color: rfTrend > 0 ? "var(--wsp)" : "var(--safe)" }}>
            {rfTrend > 0 ? `↑ +${rfTrend.toFixed(1)}` : `↓ ${rfTrend.toFixed(1)}`} mm/j
          </span>
        </div>
      )}

      {riskData.bmkgAlerts > 0 && (
        <div className="sensor-chip sensor-chip-warn">
          <span className="sensor-chip-label">BMKG</span>
          <span className="sensor-chip-value" style={{ color: "var(--wsp)" }}>
            {riskData.bmkgAlerts} alert
          </span>
        </div>
      )}

      {riskTrend && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Tren Risiko" : "Risk Trend"}</span>
          <span className="sensor-chip-value" style={{ color: trendColor }}>{trendLabel}</span>
        </div>
      )}

      {/* Monsoon season context */}
      {riskData.monsoonSeason === 1 && (
        <div className="sensor-chip">
          <span className="sensor-chip-label">{isId ? "Musim" : "Season"}</span>
          <span className="sensor-chip-value" style={{ color: "var(--wsp)" }}>
            {isId ? "Hujan" : "Wet"}
          </span>
        </div>
      )}

      {/* Anomaly spike — from sensor spike-detection, separate from OOD */}
      {riskData.anomalyDetected && (
        <div className="sensor-chip sensor-chip-warn">
          <span className="sensor-chip-label">{isId ? "Anomali" : "Anomaly"}</span>
          <span className="sensor-chip-value" style={{ color: "var(--wsp)" }}>
            {riskData.anomalyType === "spike"
              ? (isId ? "Spike" : "Spike")
              : (isId ? "Akumulasi" : "Buildup")}
          </span>
        </div>
      )}

      {/* OOD badge — only when WLR < 0.75 (high WLR suppressed at backend) */}
      {riskData.isOutlier && (riskData.waterLevelRatio ?? 0) < 0.75 && (
        <div className="sensor-chip sensor-chip-warn">
          <span className="sensor-chip-label">OOD</span>
          <span className="sensor-chip-value" style={{ color: "var(--wsp)" }}>
            {isId ? "Anomali" : "Anomaly"}
          </span>
        </div>
      )}
    </div>
  );
}

function RecommendationsPanel({ alertZones, recommendedActions = [] }) {
  const t = useT();
  const zone1 = alertZones.find((z) => z.risk_level === "SIAGA_1");
  const zone2 = alertZones.find((z) => z.risk_level === "SIAGA_2");

  const actions = [
    zone1
      ? { label: t("rec.evacuate", { zone: zone1.zone }), primary: true,  icon: "!" }
      : { label: t("rec.monitor"),   primary: false, icon: "◉" },
    zone2
      ? { label: t("rec.route", { zone: zone2.zone }), primary: false, icon: "↗" }
      : { label: t("rec.weather"),  primary: false, icon: "↻" },
    { label: t("rec.notify"), primary: false, icon: "✉" },
  ];

  return (
    <div className="panel panel-body">
      <p className="panel-title">{t("rec.title")}</p>
      {recommendedActions.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.75rem" }}>
          {recommendedActions.map((action, i) => (
            <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--cyan)", flexShrink: 0, marginTop: "0.15rem" }}>›</span>
              <p style={{ fontSize: "0.75rem", color: "var(--muted)", lineHeight: 1.55, margin: 0 }}>{action}</p>
            </div>
          ))}
        </div>
      )}
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

const WEATHER_ICON = {
  "Cerah": "☀", "Cerah Berawan": "⛅", "Berawan": "☁", "Berawan Tebal": "☁",
  "Udara Kabur": "🌫", "Asap": "🌫", "Hujan Ringan": "🌧", "Hujan Sedang": "🌧",
  "Hujan Lebat": "⛈", "Hujan Petir": "⛈", "Hujan Es": "🌨",
};

function ForecastPanel({ forecast }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!forecast || forecast.length === 0) return null;

  return (
    <div className="panel panel-body fade-in">
      <p className="panel-title">{isId ? "Prakiraan Cuaca BMKG" : "BMKG Weather Forecast"}</p>
      <div style={{ display: "flex", gap: "0.625rem", flexWrap: "wrap" }}>
        {forecast.map((slot, i) => {
          const dt = new Date(slot.local_datetime);
          const timeStr = dt.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
          const dateStr = dt.toLocaleDateString("id-ID", { day: "numeric", month: "short" });
          const icon = WEATHER_ICON[slot.weather_desc] ?? "🌤";
          const isRain = slot.weather_desc?.toLowerCase().includes("hujan");
          return (
            <div key={i} style={{
              flex: "1 1 120px",
              background: isRain ? "rgba(0,120,255,0.06)" : "rgba(0,229,160,0.04)",
              border: `1px solid ${isRain ? "rgba(0,120,255,0.15)" : "var(--border)"}`,
              borderRadius: "10px",
              padding: "0.625rem 0.75rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.25rem",
              minWidth: 0,
            }}>
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)", letterSpacing: "0.06em" }}>
                {dateStr} · {timeStr}
              </span>
              <span style={{ fontSize: "1.25rem" }}>{icon}</span>
              <span style={{ fontSize: "0.72rem", color: "var(--text)", lineHeight: 1.3, fontWeight: 500 }}>{slot.weather_desc}</span>
              {slot.tmin != null && (
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted)" }}>
                  {slot.tmin}–{slot.tmax}°C · {slot.humin}–{slot.humax}%
                </span>
              )}
            </div>
          );
        })}
      </div>
      <p style={{ marginTop: "0.5rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)" }}>
        {isId ? "Sumber: BMKG cuaca.json — DKI Jakarta" : "Source: BMKG cuaca.json — DKI Jakarta"}
      </p>
    </div>
  );
}

const ZONE_COLS = [
  { key: "zone.zone" },
  { key: "zone.area" },
  { key: "zone.tma",  note: "est" },
  { key: "zone.rain", note: "real" },
  { key: "zone.prob" },
  { key: "zone.status" },
];

function ZoneTable({ zones }) {
  const t = useT();
  return (
    <div className="panel panel-body fade-in">
      <p className="panel-title">{t("zone.title")}</p>
      <div className="zone-table-wrap">
        <table className="zone-table">
          <thead>
            <tr>
              {ZONE_COLS.map(({ key, note }) => (
                <th key={key}>
                  {t(key)}
                  {note && (
                    <span style={{ fontSize: "0.56rem", marginLeft: 3, color: note === "real" ? "var(--safe)" : "var(--muted-2)", letterSpacing: "0.04em" }}>
                      {note === "real" ? "●" : "○"}
                    </span>
                  )}
                </th>
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
                <td style={{
                  fontVariantNumeric: "tabular-nums",
                  color: z.rainfall >= 50 ? "var(--s1)" : z.rainfall >= 20 ? "var(--wsp)" : "var(--safe)",
                  fontFamily: "'JetBrains Mono',monospace",
                  fontSize: "0.82rem",
                }}>{z.rainfall > 0 ? `${z.rainfall} mm` : "–"}</td>
                <td><ProbBar value={z.probability} /></td>
                <td><RiskBadge level={z.risk_level} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ padding: "0.5rem 0.75rem", background: "rgba(0,229,160,0.05)", border: "1px solid rgba(0,229,160,0.12)", borderRadius: "8px", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--safe)", flexShrink: 0 }} />
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted-2)" }}>
            {t("zone.dataNote")}
          </span>
        </div>
        <div style={{ padding: "0.5rem 0.75rem", background: "rgba(245,166,35,0.06)", border: "1px solid rgba(245,166,35,0.15)", borderRadius: "8px", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--wsp)", flexShrink: 0 }} />
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted-2)" }}>
            {t("zone.ood")}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Page ──────────────────────────────────────────────── */
export default function Home({ setRiskContext, riskLevel }) {
  const t = useT();
  const { riskData, loading, refreshing, error, refresh, lastUpdated } = useFloodRisk();
  const level = riskData?.level ?? riskLevel ?? "waspada";
  const score = riskData?.riskScore ?? 45;

  useEffect(() => {
    if (riskData?.level) {
      setRiskContext({ level: riskData.level, rainfall: riskData.rainfall ?? 0 });
    }
  }, [riskData, setRiskContext]);

  const zones       = useMemo(() => deriveZones(score, riskData?.rainfall ?? 0, riskData?.waterLevelRatio ?? 0.5), [score, riskData?.rainfall, riskData?.waterLevelRatio]);
  const siaga1Count = zones.filter((z) => z.risk_level === "SIAGA_1").length;
  const siaga2Count = zones.filter((z) => z.risk_level === "SIAGA_2").length;
  const alertZones  = zones.filter((z) => ["SIAGA_1", "SIAGA_2"].includes(z.risk_level));

  if (loading) return <LoadingSpinner message="Mengambil data realtime..." />;

  if (error) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem", padding: "3rem 1rem", textAlign: "center" }}>
      <p style={{ fontWeight: 700, color: "var(--text)" }}>{t("error.load")}</p>
      <p style={{ fontSize: "0.82rem", color: "var(--muted)" }}>{error}</p>
      <button className="btn btn-ghost" onClick={refresh}>{t("error.retry")}</button>
    </div>
  );

  return (
    <>
      {/* Alert ribbon */}
      <AlertRibbon siaga1Count={siaga1Count} siaga2Count={siaga2Count} lastSync={lastUpdated} />

      {/* Page header */}
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{t("home.title")}</h1>
        </div>
        <div className="header-actions">
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.15rem" }}>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "var(--muted-2)" }}>
              {lastUpdated
                ? t("home.sync", { time: lastUpdated.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) })
                : t("home.syncing")}
            </span>
            {/* Show when sensor snapshot was built — different from lastUpdated (=last API call) */}
            {riskData?.snapshotFetchedAt && (() => {
              const snapTime = new Date(riskData.snapshotFetchedAt);
              // Convert UTC → WIB (+7)
              const wibMs = snapTime.getTime() + 7 * 60 * 60 * 1000;
              const wibDate = new Date(wibMs);
              const hh = String(wibDate.getUTCHours()).padStart(2, "0");
              const mm = String(wibDate.getUTCMinutes()).padStart(2, "0");
              const stationsLabel = riskData.tmaStationsActive != null
                ? ` · ${riskData.tmaStationsActive} stasiun TMA`
                : "";
              return (
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", opacity: 0.7 }}>
                  Data sensor {hh}:{mm} WIB{stationsLabel}
                </span>
              );
            })()}
          </div>
          <button className="btn btn-ghost" onClick={refresh} disabled={refreshing} style={refreshing ? { opacity: 0.55, cursor: "wait" } : {}}>
            {refreshing ? "..." : t("home.refresh")}
          </button>
        </div>
      </div>

      {/* 4 Metric cards */}
      <MetricsRow siaga1={siaga1Count} siaga2={siaga2Count} zones={zones} score={score} rainfall={riskData?.rainfall} />

      {/* Sensor detail strip */}
      <SensorStrip riskData={riskData} />

      {/* Map + Sidebar */}
      <div className="cmd-main fade-in">
        {/* Left: Map — cmd-left stretches to match sidebar */}
        <div className="cmd-left">
          <div className="panel map-panel">
            <div className="panel-body" style={{ paddingBottom: "0.75rem" }}>
              <p className="panel-title" style={{ marginBottom: 0 }}>{t("map.title")}</p>
            </div>
            <FloodMap riskScore={score} level={level} />
            <div className="map-footer">
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.63rem", color: "var(--muted-2)" }}>
                {t("map.estNote")}
              </span>
              <span style={{ marginLeft: "auto", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.63rem", color: "var(--muted-2)" }}>
                {t("map.clickDetail")}
              </span>
            </div>
          </div>
        </div>

        {/* Right: Sidebar */}
        <div className="cmd-sidebar">
          <AlertPanel alertZones={alertZones} />
          <AgentPanel level={level} />
          <RecommendationsPanel alertZones={alertZones} recommendedActions={riskData?.recommendedActions} />
        </div>
      </div>

      {/* Model interpretation — full width, no gap */}
      {riskData?.interpretation && (
        <div className="fade-in" style={{ background: "rgba(0,207,255,0.05)", border: "1px solid rgba(0,207,255,0.15)", borderLeft: "3px solid var(--cyan)", borderRadius: "12px", padding: "0.875rem 1.25rem", fontSize: "0.82rem", color: "var(--muted)", lineHeight: 1.7 }}>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--cyan)", letterSpacing: "0.1em", textTransform: "uppercase", marginRight: 10 }}>{t("home.modelOut")}</span>
          {riskData.interpretation}
        </div>
      )}

      {/* Zone table */}
      <ZoneTable zones={zones} />

      {/* BMKG weather forecast */}
      <ForecastPanel forecast={riskData?.bmkgForecast} />

      {/* Floating chatbot */}
      <ChatBot riskContext={{ level, rainfall: riskData?.rainfall }} />
    </>
  );
}
