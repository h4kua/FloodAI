import { useState, useEffect, useMemo } from "react";
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

/* ── Station helpers ───────────────────────────────────── */
// Classify a station by its ratio (tinggi_air / siaga1).
function stationRiskLevel(ratio) {
  if (ratio >= 1.0)  return "SIAGA_1";
  if (ratio >= 0.75) return "SIAGA_2";
  if (ratio >= 0.50) return "WASPADA";
  return "NORMAL";
}
function stationClass(ratio) {
  if (ratio >= 1.0)  return "s1";
  if (ratio >= 0.75) return "s2";
  if (ratio >= 0.50) return "wsp";
  return "ok";
}

/* ── Sub-components ────────────────────────────────────── */

// AlertRibbon uses REAL station counts from DSDADKI sensors.
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

const WEATHER_ICON = {
  "Cerah": "☀", "Cerah Berawan": "⛅", "Berawan": "☁", "Berawan Tebal": "☁",
  "Udara Kabur": "🌫", "Asap": "🌫", "Hujan Ringan": "🌧", "Hujan Sedang": "🌧",
  "Hujan Lebat": "⛈", "Hujan Petir": "⛈", "Hujan Es": "🌨",
};

function MetricsRow({ siaga1, siaga2, totalStations, score, rainfall, wilayahSummary }) {
  const t = useT();
  const { lang } = useApp();
  const isId = lang === "id";
  const rainMm = rainfall ?? 0;
  const hasWilayah = (wilayahSummary?.length ?? 0) > 0;
  const anyRain = hasWilayah && wilayahSummary.some(
    w => w.forecast?.[0]?.weather_desc?.toLowerCase().includes("hujan")
  );

  const firstThree = [
    { label: t("metric.alertZones"), value: siaga1 + siaga2, sub: t("metric.alertSub", { s1: siaga1, s2: siaga2 }), color: siaga1 > 0 ? "red" : siaga2 > 0 ? "orange" : "green" },
    { label: t("metric.activeStations"), value: totalStations ?? "—", sub: t("metric.activeStationsSub"), color: "green" },
    { label: t("metric.riskScore"), value: score, sub: t("metric.riskSub"), color: score >= 70 ? "red" : score >= 45 ? "orange" : "green" },
  ];

  const rainfallColor = hasWilayah ? (anyRain ? "orange" : "green") : (rainMm >= 50 ? "red" : rainMm >= 20 ? "orange" : "green");
  const noteStyle = { fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em", opacity: 0.85 };

  return (
    <div className="cmd-metrics">
      {firstThree.map((c) => (
        <div key={c.label} className={`metric-card ${c.color}`}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span className="metric-label">{c.label}</span>
            <span style={noteStyle}>● real</span>
          </div>
          <div>
            <div className={`metric-value ${c.color}`}>{c.value}</div>
            <div className="metric-sub">{c.sub}</div>
          </div>
        </div>
      ))}

      {/* Card 4: per-wilayah rainfall from BMKG — replaces single OpenWeather point */}
      <div className={`metric-card ${rainfallColor}`}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "6px" }}>
          <span className="metric-label">{isId ? "Curah Hujan" : "Rainfall"}</span>
          <span style={noteStyle}>● {hasWilayah ? "BMKG" : "real"}</span>
        </div>
        {hasWilayah ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
            {wilayahSummary.map(w => {
              const cf = w.forecast?.[0];
              const isRain = cf?.weather_desc?.toLowerCase().includes("hujan");
              const icon = WEATHER_ICON[cf?.weather_desc] ?? "☁";
              return (
                <div key={w.wilayah} style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                  <span style={{ fontSize: "0.68rem", flexShrink: 0 }}>{icon}</span>
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.55rem", color: "var(--muted-2)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {w.wilayah.replace("Jakarta ", "")}
                  </span>
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.54rem", color: isRain ? "var(--wsp)" : "var(--muted)", fontWeight: isRain ? 700 : 400, flexShrink: 0 }}>
                    {cf?.weather_desc ?? "—"}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div>
            <div className={`metric-value ${rainfallColor}`}>{humanizeRainfall(rainMm, lang)}</div>
            <div className="metric-sub">{rainMm > 0 ? `${Math.round(rainMm)} mm/jam` : t("metric.rainSub")}</div>
          </div>
        )}
      </div>
    </div>
  );
}

// AlertPanel: shows REAL DSDADKI stations in alert state (ratio >= 0.75).
// Previously showed fake zone derivations — now 100% from sensor readings.
function AlertPanel({ stations }) {
  const t = useT();
  const alertStations = (stations || []).filter(s => s.ratio >= 0.75).slice(0, 5);

  if (alertStations.length === 0) return (
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
        {alertStations.map((s, i) => (
          <div key={i} className={`alert-item ${stationClass(s.ratio)}`}>
            <span className="alert-dot" />
            <div style={{ minWidth: 0 }}>
              <p className="alert-zone-name" style={{ fontSize: "0.78rem" }}>{s.nama}</p>
              <p className="alert-zone-sub">TMA {s.tinggi_air} cm · {Math.round(s.ratio * 100)}% siaga</p>
            </div>
            <RiskBadge level={stationRiskLevel(s.ratio)} />
          </div>
        ))}
      </div>
      <p style={{ marginTop: "0.5rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)" }}>
        ● Sensor DSDADKI realtime
      </p>
    </div>
  );
}

// StationPanel: full table of ALL real DSDADKI stations with live readings.
// Shows top 6 by default; user can expand to see all.
function StationPanel({ stations }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const [showAll, setShowAll] = useState(false);

  if (!stations || stations.length === 0) return null;

  const PREVIEW = 6;
  const displayed = showAll ? stations : stations.slice(0, PREVIEW);
  const hasMore = stations.length > PREVIEW;

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Sensor Ketinggian Air — DSDADKI" : "Water Level Sensors — DSDADKI"}
        </p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em" }}>● real</span>
      </div>
      <div className="zone-table-wrap">
        <table className="zone-table">
          <thead>
            <tr>
              <th>{isId ? "Pos Pantau" : "Station"}</th>
              <th>{isId ? "Tinggi Air" : "Water Level"}</th>
              <th>{isId ? "Ambang" : "Threshold"}</th>
              <th>{isId ? "Persentase" : "Percent"}</th>
              <th>{isId ? "Status" : "Status"}</th>
            </tr>
          </thead>
          <tbody>
            {displayed.map((s, i) => (
              <tr key={i}>
                <td>
                  <span className="zone-name" style={{ fontSize: "0.72rem" }}>{s.nama}</span>
                </td>
                <td style={{ fontVariantNumeric: "tabular-nums", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.82rem", color: s.ratio >= 0.75 ? "var(--wsp)" : "var(--text)" }}>
                  {s.tinggi_air} cm
                </td>
                <td style={{ fontVariantNumeric: "tabular-nums", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.82rem", color: "var(--muted)" }}>
                  {s.siaga1} cm
                </td>
                <td><ProbBar value={Math.min(s.ratio, 1.0)} /></td>
                <td><RiskBadge level={stationRiskLevel(s.ratio)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <button
          className="btn btn-ghost"
          onClick={() => setShowAll(v => !v)}
          style={{ marginTop: "0.75rem", width: "100%", justifyContent: "center" }}
        >
          {showAll
            ? (isId ? "Tampilkan lebih sedikit ↑" : "Show less ↑")
            : (isId ? `Lihat semua ${stations.length} pos pantau ↓` : `Show all ${stations.length} stations ↓`)}
        </button>
      )}
      <p style={{ marginTop: "0.75rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.62rem", color: "var(--muted-2)" }}>
        {isId
          ? "● Sensor pintu air & pos pantau DSDADKI · Persentase = Tinggi Air ÷ Ambang Siaga 1 · Update tiap 15 menit"
          : "● DSDADKI water gate & monitoring station sensors · Percent = Water Level ÷ Siaga-1 Threshold · Updates every 15 min"}
      </p>
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
        <div className="sensor-chip secondary">
          <span className="sensor-chip-label">{isId ? "Suhu" : "Temp"}</span>
          <span className="sensor-chip-value">{riskData.temperature?.toFixed(1)}°C</span>
        </div>
      )}
      {riskData.humidity !== null && (
        <div className="sensor-chip secondary">
          <span className="sensor-chip-label">{isId ? "Kelembapan" : "Humidity"}</span>
          <span className="sensor-chip-value">{Math.round(riskData.humidity)}%</span>
        </div>
      )}

      {/* 3h accumulation */}
      {acc3h != null && acc3h > 0 && (
        <div className="sensor-chip secondary">
          <span className="sensor-chip-label">{isId ? "Akum. 3j" : "3h Accum"}</span>
          <span className="sensor-chip-value" style={{ color: acc3h >= 15 ? "var(--wsp)" : undefined }}>
            {acc3h.toFixed(1)} mm
          </span>
        </div>
      )}
      {riskData.rainfallAcc6h != null && riskData.rainfallAcc6h > 0 && (
        <div className="sensor-chip secondary">
          <span className="sensor-chip-label">{isId ? "Akum. 6j" : "6h Accum"}</span>
          <span className="sensor-chip-value" style={{ color: riskData.rainfallAcc6h >= 20 ? "var(--wsp)" : undefined }}>
            {riskData.rainfallAcc6h} mm
          </span>
        </div>
      )}

      {/* Rainfall trend */}
      {rfTrend != null && Math.abs(rfTrend) >= 1 && (
        <div className="sensor-chip secondary">
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
        <div className="sensor-chip secondary">
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
        <div className="sensor-chip sensor-chip-warn secondary">
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

/* ── Stale data warning — tampil kalau snapshot > 30 menit ─────────────── */
function StaleDataBanner({ snapshotFetchedAt }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!snapshotFetchedAt) return null;
  const ageMin = Math.round((Date.now() - new Date(snapshotFetchedAt).getTime()) / 60000);
  if (ageMin < 30) return null;
  return (
    <div style={{
      background: "rgba(245,166,35,0.08)", border: "1px solid rgba(245,166,35,0.25)",
      borderRadius: "10px", padding: "0.625rem 1rem",
      display: "flex", alignItems: "center", gap: "0.75rem",
      fontSize: "0.78rem", color: "var(--wsp)",
    }}>
      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem", fontWeight: 700, flexShrink: 0 }}>⚠</span>
      <span>
        {isId
          ? `Data sensor terakhir diperbarui ${ageMin} menit lalu — scraper mungkin mengalami gangguan. Refresh manual atau hubungi admin.`
          : `Sensor data was last updated ${ageMin} minutes ago — scraper may be experiencing issues. Try manual refresh or contact admin.`}
      </span>
    </div>
  );
}

/* ── Status Hero — the FIRST thing user sees: "apakah ada risiko banjir?" ── */
function StatusHero({ riskData }) {
  const { lang } = useApp();
  const isId = lang === "id";

  const level    = riskData?.level ?? "waspada";
  const score    = riskData?.riskScore ?? 0;
  const wlr      = riskData?.waterLevelRatio;
  const rainfall = riskData?.rainfall ?? 0;
  const riskTrend = riskData?.trendState?.risk_trend;
  const snapshotFetchedAt = riskData?.snapshotFetchedAt;

  const cfgMap = {
    aman: {
      label: isId ? "Aman" : "Safe",
      color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)",
      desc: isId
        ? "Jakarta saat ini aman dari risiko banjir. Tidak ada tanda-tanda mengkhawatirkan."
        : "Jakarta is currently safe from flood risk. No concerning signs.",
    },
    waspada: {
      label: isId ? "Waspada" : "Watch",
      color: "var(--wsp)", bg: "var(--wsp-soft)", border: "var(--wsp-border)",
      desc: isId
        ? "Ada tanda awal yang perlu diperhatikan. Pantau ketinggian air secara berkala."
        : "Early signs worth monitoring. Check water levels periodically.",
    },
    siaga: {
      label: isId ? "Siaga" : "Alert",
      color: "var(--s2)", bg: "var(--s2-soft)", border: "var(--s2-border)",
      desc: isId
        ? "Ketinggian air cukup tinggi dan perlu diwaspadai. Siapkan tas darurat dan terus pantau perkembangan."
        : "Water levels are elevated. Prepare an emergency bag and keep monitoring.",
    },
    bahaya: {
      label: isId ? "Bahaya!" : "Danger!",
      color: "var(--s1)", bg: "var(--s1-soft)", border: "var(--s1-border)",
      desc: isId
        ? "KONDISI KRITIS! Ikuti instruksi BPBD segera. Bersiap untuk evakuasi sekarang."
        : "CRITICAL CONDITIONS! Follow BPBD instructions immediately. Prepare to evacuate now.",
    },
  };
  const cfg = cfgMap[level] ?? cfgMap.waspada;

  let snapTimeStr = null;
  if (snapshotFetchedAt) {
    const wib = new Date(new Date(snapshotFetchedAt).getTime() + 7 * 60 * 60 * 1000);
    snapTimeStr = `${String(wib.getUTCHours()).padStart(2,"0")}:${String(wib.getUTCMinutes()).padStart(2,"0")}`;
  }

  const trendLabel = riskTrend === "increasing"
    ? (isId ? "↑ Naik" : "↑ Rising")
    : riskTrend === "decreasing"
    ? (isId ? "↓ Turun" : "↓ Falling")
    : (isId ? "→ Stabil" : "→ Stable");
  const trendColor = riskTrend === "increasing" ? "var(--wsp)" : riskTrend === "decreasing" ? "var(--safe)" : "var(--muted)";

  // Mini sparkline dari recent_probabilities (3–5 data points dari trend history)
  const probs = riskData?.trendState?.recent_probabilities ?? [];
  const sparkW = Math.max(probs.length, 2) * 22;
  const sparkH = 32;
  const sparkY = (p) => sparkH - 4 - Math.round(Math.min(p, 1) * (sparkH - 8));

  return (
    <div className="status-hero fade-in" style={{
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      borderLeft: `4px solid ${cfg.color}`,
    }}>
      <div className="status-hero-main">
        <div style={{
          fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem",
          color: cfg.color, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.25rem",
        }}>
          {isId ? "STATUS JAKARTA" : "JAKARTA STATUS"}
          {snapTimeStr && <span style={{ opacity: 0.65, marginLeft: "0.5rem" }}>· {snapTimeStr} WIB</span>}
        </div>
        <div className="status-hero-level" style={{ color: cfg.color }}>{cfg.label}</div>
        <p className="status-hero-desc">{cfg.desc}</p>
      </div>
      <div className="status-hero-stats">
        {wlr != null && (
          <div className="hero-stat">
            <div className="hero-stat-value" style={{ color: cfg.color }}>{Math.round(wlr * 100)}%</div>
            <div className="hero-stat-label">{isId ? "Ketinggian Air" : "Water Level"}</div>
          </div>
        )}
        <div className="hero-stat">
          <div className="hero-stat-value" style={{ color: cfg.color }}>{score}</div>
          <div className="hero-stat-label">{isId ? "Skor Risiko" : "Risk Score"}</div>
        </div>
        <div className="hero-stat">
          <div className="hero-stat-value" style={{ color: trendColor, fontSize: "1.1rem" }}>{trendLabel}</div>
          <div className="hero-stat-label">{isId ? "Tren Risiko" : "Risk Trend"}</div>
        </div>
        {rainfall > 0 && (
          <div className="hero-stat">
            <div className="hero-stat-value" style={{ color: "var(--wsp)" }}>{Math.round(rainfall)}</div>
            <div className="hero-stat-label">mm/jam</div>
          </div>
        )}
        {probs.length >= 2 && (
          <div className="hero-stat secondary">
            <svg width={sparkW} height={sparkH} style={{ display: "block" }}>
              {probs.map((p, i, arr) => i === 0 ? null : (
                <line key={i}
                  x1={(i - 1) * 22 + 11} y1={sparkY(arr[i - 1])}
                  x2={i * 22 + 11}       y2={sparkY(p)}
                  stroke={cfg.color} strokeWidth="1.5" strokeLinecap="round"
                />
              ))}
              {probs.map((p, i) => (
                <circle key={i}
                  cx={i * 22 + 11} cy={sparkY(p)}
                  r={i === probs.length - 1 ? 3 : 2}
                  fill={cfg.color}
                />
              ))}
            </svg>
            <div className="hero-stat-label">{isId ? "Tren 3 titik" : "3-pt trend"}</div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Wilayah helpers ───────────────────────────────────── */
const WILAYAH_STATUS_STYLE = {
  "Siaga 1": { color: "var(--s1)", bg: "var(--s1-soft)", border: "var(--s1-border)" },
  "Siaga 2": { color: "var(--s2)", bg: "var(--s2-soft)", border: "var(--s2-border)" },
  "Siaga 3": { color: "var(--wsp)", bg: "var(--wsp-soft)", border: "var(--wsp-border)" },
  "Normal":  { color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)" },
};

function WilayahGrid({ wilayahSummary }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!wilayahSummary || wilayahSummary.length === 0) return null;

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Kondisi per Wilayah Jakarta" : "Jakarta District Conditions"}
        </p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)", letterSpacing: "0.06em" }}>
          ● DSDADKI · BMKG
        </span>
      </div>

      <div className="wilayah-grid">
        {wilayahSummary.map((w) => {
          const cf = w.forecast?.[0];
          const icon = WEATHER_ICON[cf?.weather_desc] ?? "🌤";
          const isRain = cf?.weather_desc?.toLowerCase().includes("hujan");
          const style = WILAYAH_STATUS_STYLE[w.worst_status] ?? WILAYAH_STATUS_STYLE["Normal"];
          const shortName = w.wilayah.replace("Jakarta ", "Jkt ");

          return (
            <div key={w.wilayah} className="wilayah-card"
              style={{ borderTopColor: style.color, borderTopWidth: "2px" }}>

              {/* Wilayah + status */}
              <div style={{ marginBottom: "0.5rem" }}>
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", fontWeight: 700, color: "var(--muted)", letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: "0.3rem" }}>
                  {shortName}
                </div>
                <span className="wilayah-status-badge"
                  style={{ background: style.bg, color: style.color, borderColor: style.border }}>
                  {w.worst_status}
                </span>
              </div>

              {/* Weather icon + description */}
              <div style={{ marginBottom: "0.5rem" }}>
                <div style={{ fontSize: "1.4rem", lineHeight: 1, marginBottom: "0.2rem" }}>{icon}</div>
                <div style={{ fontSize: "0.7rem", color: isRain ? "var(--cyan)" : "var(--text)", fontWeight: 500, lineHeight: 1.3 }}>
                  {cf?.weather_desc ?? "—"}
                </div>
                {cf?.tmin != null && (
                  <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted)", marginTop: "0.15rem" }}>
                    {cf.tmin}–{cf.tmax}°C · {cf.humin}–{cf.humax}%
                  </div>
                )}
              </div>

              {/* TMA count + siaga badges */}
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.25rem", marginBottom: "0.5rem" }}>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)" }}>
                  {w.tma_count} TMA
                </span>
                {w.siaga1_count > 0 && (
                  <span className="wilayah-siaga-pip" style={{ background: "var(--s1-soft)", color: "var(--s1)", borderColor: "var(--s1-border)" }}>
                    {w.siaga1_count}×S1
                  </span>
                )}
                {w.siaga2_count > 0 && (
                  <span className="wilayah-siaga-pip" style={{ background: "var(--s2-soft)", color: "var(--s2)", borderColor: "var(--s2-border)" }}>
                    {w.siaga2_count}×S2
                  </span>
                )}
                {w.siaga3_count > 0 && (
                  <span className="wilayah-siaga-pip" style={{ background: "var(--wsp-soft)", color: "var(--wsp)", borderColor: "var(--wsp-border)" }}>
                    {w.siaga3_count}×S3
                  </span>
                )}
              </div>

              {/* Next forecast slots — show time + weather desc */}
              {w.forecast?.length > 1 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                  {w.forecast.slice(1, 3).map((slot, i) => {
                    const slotIcon = WEATHER_ICON[slot.weather_desc] ?? "🌤";
                    const dt = new Date(slot.local_datetime);
                    const timeStr = dt.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
                    const isRainSlot = slot.weather_desc?.toLowerCase().includes("hujan");
                    return (
                      <div key={i} style={{
                        display: "flex", alignItems: "center", gap: "4px",
                        background: "var(--panel-3)", borderRadius: "5px", padding: "3px 6px",
                      }}>
                        <span style={{ fontSize: "0.78rem", flexShrink: 0 }}>{slotIcon}</span>
                        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.53rem", color: "var(--muted-2)", flexShrink: 0 }}>{timeStr}</span>
                        <span style={{ fontSize: "0.58rem", color: isRainSlot ? "var(--cyan)" : "var(--muted)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {slot.weather_desc}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footnote explaining rainfall context */}
      <p style={{ marginTop: "0.75rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", lineHeight: 1.6 }}>
        {isId
          ? "● Status TMA dari sensor DSDADKI realtime · Prakiraan dari BMKG per wilayah · Curah hujan 0 mm = tidak hujan di titik sensor OpenWeather — TMA bisa naik karena hujan di hulu (Bogor/Depok)"
          : "● TMA from DSDADKI realtime · Forecast from BMKG per district · 0 mm rainfall = no rain at OpenWeather sensor point — TMA may rise from upstream rain (Bogor/Depok)"}
      </p>
    </div>
  );
}

function ForecastPanel({ forecast }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!forecast || forecast.length === 0) return null;

  return (
    <div className="panel panel-body fade-in">
      <p className="panel-title">{isId ? "Prakiraan Cuaca BMKG — DKI Jakarta" : "BMKG Weather Forecast — DKI Jakarta"}</p>
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
              border: `1px solid ${isRain ? "rgba(0,120,255,0.15)" : "var(--line)"}`,
              borderRadius: "10px", padding: "0.625rem 0.75rem",
              display: "flex", flexDirection: "column", gap: "0.25rem", minWidth: 0,
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
        {isId ? "Sumber: BMKG cuaca.json — rata-rata DKI Jakarta" : "Source: BMKG cuaca.json — DKI Jakarta average"}
      </p>
    </div>
  );
}

function ZoneCards({ zones }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const colorMap = { s1: "var(--s1)", s2: "var(--s2)", wsp: "var(--wsp)", ok: "var(--safe)" };

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Estimasi Risiko per Wilayah" : "Risk Estimate by Area"}
        </p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)", letterSpacing: "0.06em" }}>
          {isId ? "○ estimasi ML" : "○ ML estimate"}
        </span>
      </div>
      <div className="zone-cards">
        {zones.map((z, i) => {
          const cls = riskClass(z.risk_level);
          const color = colorMap[cls] ?? "var(--safe)";
          return (
            <div key={i} className="zone-card">
              <div className="zone-card-top">
                <div>
                  <p className="zone-card-name">{z.zone}</p>
                  <p className="zone-card-area">{z.district}</p>
                </div>
                <RiskBadge level={z.risk_level} />
              </div>
              <div className="zone-card-bar">
                <div className="zone-card-fill" style={{ width: `${Math.min(z.probability, 1) * 100}%`, background: color }} />
              </div>
              <p className="zone-card-pct" style={{ color }}>
                {Math.round(z.probability * 100)}%
                <span style={{ color: "var(--muted-2)", fontWeight: 400, marginLeft: 4 }}>
                  {isId ? "kemungkinan banjir" : "flood chance"}
                </span>
              </p>
            </div>
          );
        })}
      </div>
      <p style={{ marginTop: "0.75rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.62rem", color: "var(--muted-2)" }}>
        {isId
          ? "○ Estimasi dari XGBoost + bias historis BPBD per zona. Bukan data sensor per-kecamatan."
          : "○ Estimate from XGBoost + historical BPBD bias per zone. Not per-district sensor data."}
      </p>
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

  // ── Real station counts from DSDADKI sensors (NOT derived from ML zones) ──
  const stations    = riskData?.stations ?? [];
  const realSiaga1  = useMemo(() => stations.filter(s => s.ratio >= 1.0).length,  [stations]);
  const realSiaga2  = useMemo(() => stations.filter(s => s.ratio >= 0.75 && s.ratio < 1.0).length, [stations]);
  const totalStations = riskData?.tmaStationsActive ?? (stations.length || null);

  // ── ML-derived geographic zones — used for map & zone table only ──────────
  const zones = useMemo(
    () => deriveZones(score, riskData?.rainfall ?? 0, riskData?.waterLevelRatio ?? 0.5),
    [score, riskData?.rainfall, riskData?.waterLevelRatio],
  );
  // alertZones still used for RecommendationsPanel context (ML estimate)
  const alertZones = zones.filter(z => ["SIAGA_1", "SIAGA_2"].includes(z.risk_level));

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
      {/* Alert ribbon — real station counts */}
      <AlertRibbon siaga1Count={realSiaga1} siaga2Count={realSiaga2} lastSync={lastUpdated} />

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

      {/* Stale data warning — tampil kalau snapshot lebih dari 30 menit */}
      <StaleDataBanner snapshotFetchedAt={riskData?.snapshotFetchedAt} />

      {/* Status Hero — plain-language summary visible immediately */}
      <StatusHero riskData={riskData} />

      {/* 4 Metric cards — all real data */}
      <MetricsRow siaga1={realSiaga1} siaga2={realSiaga2} totalStations={totalStations} score={score} rainfall={riskData?.rainfall} wilayahSummary={riskData?.wilayahSummary} />

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
            <FloodMap riskScore={score} stations={stations} />
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
          <AlertPanel stations={stations} />
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

      {/* Real DSDADKI station table — all live sensor readings */}
      <StationPanel stations={stations} />

      {/* Zone cards — ML geographic estimate (not per-sensor) */}
      <ZoneCards zones={zones} />

      {/* Per-wilayah conditions: TMA status + BMKG forecast combined */}
      <WilayahGrid wilayahSummary={riskData?.wilayahSummary} />

      {/* BMKG weather forecast — DKI aggregate (shown when wilayah grid unavailable) */}
      {(!riskData?.wilayahSummary?.length) && <ForecastPanel forecast={riskData?.bmkgForecast} />}

      {/* Floating chatbot */}
      <ChatBot riskContext={{ level, rainfall: riskData?.rainfall }} />
    </>
  );
}
