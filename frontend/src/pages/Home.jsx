import { useState, useEffect, useMemo } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
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


// Maps each zone to its Jakarta kota administrasi (administrative city).
// Used to pull realtime TMA + BMKG data per zone from wilayahSummary.
const ZONE_WILAYAH_MAP = {
  "Kebayoran":   "Jakarta Selatan",
  "Penjaringan": "Jakarta Utara",
  "Jatinegara":  "Jakarta Timur",
  "Kalideres":   "Jakarta Barat",
  "Cengkareng":  "Jakarta Barat",
};

// Bonus added to risk probability based on DSDADKI worst-status per wilayah.
const STATUS_RISK_BONUS = { "Siaga 1": 35, "Siaga 2": 22, "Siaga 3": 12, "Normal": 0 };

// deriveRealtimeZones: blends global ML score with per-wilayah DSDADKI sensor counts
// and BMKG forecast. Falls back to pure ML when wilayahSummary is empty.
function deriveRealtimeZones(riskScore, wilayahSummary = [], rainfall = 0, waterLevelRatio = 0.5) {
  const wlr = Math.max(0.3, Math.min(1.5, waterLevelRatio));
  const summaryMap = {};
  (wilayahSummary || []).forEach(w => { summaryMap[w.wilayah] = w; });
  const hasRealtime = Object.keys(summaryMap).length > 0;

  return BASE_ZONES.map((z) => {
    const wilayahName = ZONE_WILAYAH_MAP[z.zone];
    const ws = summaryMap[wilayahName];

    let prob;
    if (hasRealtime && ws) {
      // Realtime path: TMA status + siaga sensor counts + BMKG forecast + bias
      const statusBonus = STATUS_RISK_BONUS[ws.worst_status] ?? 0;
      const siagaBonus  = (ws.siaga1_count ?? 0) * 8 + (ws.siaga2_count ?? 0) * 4 + (ws.siaga3_count ?? 0) * 2;
      const isRaining   = ws.forecast?.[0]?.weather_desc?.toLowerCase().includes("hujan");
      const rainBonus   = isRaining ? (rainfall > 20 ? 12 : 6) : 0;
      // 40% global ML + realtime sensor signals + historical bias
      const blended = riskScore * 0.4 + statusBonus + siagaBonus + rainBonus + z.bias;
      prob = Math.max(0.04, Math.min(0.97, blended / 100));
    } else {
      // Fallback: original ML derivation
      prob = Math.max(0.04, Math.min(0.97, (riskScore + z.bias) / 100));
    }

    let risk_level;
    if (prob >= 0.80) risk_level = "SIAGA_1";
    else if (prob >= 0.55) risk_level = "SIAGA_2";
    else if (prob >= 0.30) risk_level = "WASPADA";
    else risk_level = "NORMAL";

    const wlrBiased = Math.min(1.5, Math.max(0.3, wlr + z.bias / 200));
    return {
      ...z,
      probability: prob,
      tma: Math.round(z.tma_base * wlrBiased),
      rainfall,
      risk_level,
      // realtime extras — shown in ZoneCards when available
      worstStatus:  ws?.worst_status ?? null,
      siaga1Count:  ws?.siaga1_count ?? 0,
      siaga2Count:  ws?.siaga2_count ?? 0,
      siaga3Count:  ws?.siaga3_count ?? 0,
      tmaCount:     ws?.tma_count ?? 0,
      isRealtime:   hasRealtime && !!ws,
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

function MetricsRow({ siaga1, siaga2, totalStations, score }) {
  const t = useT();
  const noteStyle = { fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em", opacity: 0.85 };
  const cards = [
    { label: t("metric.alertZones"), value: siaga1 + siaga2, sub: t("metric.alertSub", { s1: siaga1, s2: siaga2 }), color: siaga1 > 0 ? "red" : siaga2 > 0 ? "orange" : "green" },
    { label: t("metric.activeStations"), value: totalStations ?? "—", sub: t("metric.activeStationsSub"), color: "green" },
    { label: t("metric.riskScore"), value: score, sub: t("metric.riskSub"), color: score >= 70 ? "red" : score >= 45 ? "orange" : "green" },
  ];

  return (
    <div className="cmd-metrics">
      {cards.map((c) => (
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
    </div>
  );
}

/* ── Wilayah Rainfall Strip ────────────────────────────────
   Dedicated full-width row showing per-wilayah weather from BMKG.
   Placed immediately after the 3 metric cards so users see it
   without scrolling. Falls back to OpenWeather overall rainfall
   when BMKG per-wilayah data is unavailable.
*/
function WilayahRainfallStrip({ wilayahSummary, rainfall, lang }) {
  const isId = lang === "id";
  const hasWilayah = (wilayahSummary?.length ?? 0) > 0;
  const rainMm = rainfall ?? 0;

  const noteStyle = {
    fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem",
    color: "var(--safe)", letterSpacing: "0.06em", opacity: 0.85,
  };

  return (
    <div className="rainfall-strip fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.62rem", color: "var(--muted)", letterSpacing: "0.07em", textTransform: "uppercase" }}>
          {isId ? "Curah Hujan per Wilayah Jakarta" : "Rainfall per Jakarta District"}
        </span>
        <span style={noteStyle}>● {hasWilayah ? "BMKG" : "OpenWeather"}</span>
      </div>

      {hasWilayah ? (
        <div className="rainfall-wilayah-cards">
          {wilayahSummary.map((w) => {
            const cf = w.forecast?.[0];
            const isRain = cf?.weather_desc?.toLowerCase().includes("hujan");
            const icon = WEATHER_ICON[cf?.weather_desc] ?? "☁";
            const shortName = w.wilayah.replace("Jakarta ", "Jkt ");
            const statusStyle = WILAYAH_STATUS_STYLE[w.worst_status] ?? WILAYAH_STATUS_STYLE["Normal"];
            return (
              <div key={w.wilayah} className={`rain-card ${isRain ? "raining" : "clear"}`}>
                <div className="rain-card-top">
                  <span className="rain-card-name">{shortName}</span>
                  <span className="rain-card-badge"
                    style={{ background: statusStyle.bg, color: statusStyle.color, borderColor: statusStyle.border }}>
                    {w.worst_status}
                  </span>
                </div>
                <div className="rain-card-icon">{icon}</div>
                <div className={`rain-card-desc${isRain ? " raining" : ""}`}>
                  {cf?.weather_desc ?? (isId ? "Tidak ada data" : "No data")}
                </div>
                {cf?.tmin != null && (
                  <div className="rain-card-temp">{cf.tmin}–{cf.tmax}°C · {cf.humin}–{cf.humax}%</div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        /* Fallback: no BMKG per-wilayah — show single OpenWeather reading */
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <span style={{ fontSize: "2rem" }}>{rainMm > 20 ? "🌧" : rainMm > 0 ? "🌦" : "☁"}</span>
          <div>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: rainMm > 0 ? "var(--cyan)" : "var(--text)" }}>
              {rainMm > 0 ? `${Math.round(rainMm)} mm/jam` : (isId ? "Tidak Hujan" : "No Rain")}
            </div>
            <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted)", marginTop: "2px" }}>
              {isId ? "Data OpenWeather — titik pusat Jakarta" : "OpenWeather — Jakarta center point"}
            </div>
          </div>
        </div>
      )}

      <div style={{ marginTop: "0.625rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem", color: "var(--muted-2)", lineHeight: 1.5 }}>
        {hasWilayah
          ? (isId
            ? "● Prakiraan BMKG per kota administrasi · Status TMA dari sensor DSDADKI realtime · Update tiap 15 menit"
            : "● BMKG forecast per administrative city · TMA status from DSDADKI realtime sensors · Updates every 15 min")
          : (isId
            ? "● Data OpenWeather — satu titik pengukuran untuk seluruh Jakarta. Curah hujan bisa berbeda tiap wilayah."
            : "● OpenWeather — single measurement point for all Jakarta. Rainfall varies by district.")}
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

function RecommendationsPanel({ riskData, stations = [] }) {
  const t = useT();
  const { lang } = useApp();
  const isId = lang === "id";

  const rainfall   = riskData?.rainfall ?? 0;
  const riskTrend  = riskData?.trendState?.risk_trend;
  const wSummary   = riskData?.wilayahSummary ?? [];

  // Sort stations by severity, pick top alerts
  const s1 = [...stations].filter(s => s.ratio >= 1.0).sort((a, b) => b.ratio - a.ratio);
  const s2 = [...stations].filter(s => s.ratio >= 0.75 && s.ratio < 1.0).sort((a, b) => b.ratio - a.ratio);

  // Most dangerous wilayah by status
  const dangerW = [...wSummary]
    .filter(w => ["Siaga 1","Siaga 2","Siaga 3"].includes(w.worst_status))
    .sort((a, b) => ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[b.worst_status] ?? 0) - ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[a.worst_status] ?? 0));
  const topW = dangerW[0];

  // Build dynamic realtime action list
  const dynActions = [];

  if (s1.length > 0) {
    const st = s1[0];
    dynActions.push(isId
      ? `🔴 ${st.nama} sudah ${Math.round(st.ratio * 100)}% ambang Siaga 1 (TMA ${st.tinggi_air} cm). Warga bantaran terdekat: siapkan evakuasi segera.`
      : `🔴 ${st.nama} at ${Math.round(st.ratio * 100)}% of Alert-1 threshold (${st.tinggi_air} cm). Nearby residents: prepare immediate evacuation.`
    );
  }

  if (s2.length > 0) {
    const st = s2[0];
    dynActions.push(isId
      ? `🟠 ${st.nama} Siaga 2 (${Math.round(st.ratio * 100)}%, TMA ${st.tinggi_air} cm) — pantau setiap 15 mnt, siapkan tas darurat.`
      : `🟠 ${st.nama} at Alert 2 (${Math.round(st.ratio * 100)}%, ${st.tinggi_air} cm) — monitor every 15 min, prepare emergency bag.`
    );
  }

  if (topW) {
    const sensorsNote = topW.siaga1_count > 0
      ? (isId ? `${topW.siaga1_count} sensor Siaga 1 aktif` : `${topW.siaga1_count} active Alert-1 sensors`)
      : (isId ? `${topW.siaga2_count} sensor Siaga 2` : `${topW.siaga2_count} Alert-2 sensors`);
    dynActions.push(isId
      ? `📍 ${topW.wilayah} — ${topW.worst_status}, ${sensorsNote}. Kurangi aktivitas di luar ruangan di wilayah ini.`
      : `📍 ${topW.wilayah} — ${topW.worst_status}, ${sensorsNote}. Reduce outdoor activities in this district.`
    );
  }

  if (rainfall > 20) {
    dynActions.push(isId
      ? `🌧 Curah hujan ${Math.round(rainfall)} mm/jam — potensi genangan cepat di titik rendah. Hindari bantaran kali dan underpass.`
      : `🌧 Rainfall ${Math.round(rainfall)} mm/h — rapid pooling risk at low points. Avoid riverbanks and underpasses.`
    );
  } else if (rainfall > 5) {
    dynActions.push(isId
      ? `🌦 Hujan ringan ${Math.round(rainfall)} mm/jam — pantau apakah intensitas meningkat dalam 30 menit ke depan.`
      : `🌦 Light rain ${Math.round(rainfall)} mm/h — monitor if intensity rises over the next 30 minutes.`
    );
  }

  if (riskTrend === "increasing" && dynActions.length < 3) {
    dynActions.push(isId
      ? `↑ Tren risiko sedang naik — persiapkan evakuasi mandiri dan koordinasi dengan RT/RW setempat.`
      : `↑ Risk trend rising — prepare self-evacuation plan and coordinate with local RT/RW.`
    );
  }

  if (dynActions.length === 0) {
    dynActions.push(isId
      ? "✅ Kondisi saat ini terpantau normal. Tetap pantau sensor tiap 15 menit selama musim hujan."
      : "✅ Current conditions appear normal. Keep monitoring sensors every 15 min during rain season."
    );
  }

  // Buttons — contextual to most critical situation
  const buttons = [];
  if (s1.length > 0) {
    const nm = s1[0].nama.split(/[\s/]/)[0];
    buttons.push({ label: isId ? `Evakuasi — area ${nm}` : `Evacuate — ${nm} area`, primary: true, icon: "!" });
  } else {
    buttons.push({ label: isId ? "Pantau kondisi sensor" : "Monitor sensor conditions", primary: false, icon: "◉" });
  }
  buttons.push({
    label: topW
      ? (isId ? `Rute alternatif — ${topW.wilayah.replace("Jakarta ", "")}` : `Alt route — ${topW.wilayah.replace("Jakarta ", "")}`)
      : (isId ? "Cek rute evakuasi" : "Check evacuation routes"),
    primary: false, icon: "↗",
  });
  buttons.push({ label: isId ? "BPBD Jakarta — 117" : "BPBD Emergency: 117", primary: false, icon: "✉" });

  return (
    <div className="panel panel-body">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>{t("rec.title")}</p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em" }}>● real</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "0.75rem" }}>
        {dynActions.map((action, i) => (
          <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--cyan)", flexShrink: 0, marginTop: "0.15rem" }}>›</span>
            <p style={{ fontSize: "0.75rem", color: "var(--muted)", lineHeight: 1.55, margin: 0 }}>{action}</p>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {buttons.map((a, i) => (
          <button key={i} className={`action-btn${a.primary ? " primary" : ""}`}>
            <span className="action-icon">{a.icon}</span>
            {a.label}
          </button>
        ))}
      </div>
      <p style={{ marginTop: "0.625rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)" }}>
        ● {isId ? "Rekomendasi dari sensor DSDADKI + BMKG realtime" : "Based on realtime DSDADKI sensors + BMKG data"}
      </p>
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

/* ── Dynamic status description ─────────────────────────────
   Generates a plain-language summary from actual realtime sensor data.
   Replaces the four static hand-written strings that lived in cfgMap.
*/
function buildStatusDesc(riskData, isId) {
  const level      = riskData?.level ?? "waspada";
  const wlr        = riskData?.waterLevelRatio ?? 0;
  const rainfall   = riskData?.rainfall ?? 0;
  const riskTrend  = riskData?.trendState?.risk_trend;
  const stations   = riskData?.stations ?? [];
  const wSummary   = riskData?.wilayahSummary ?? [];

  const s1 = [...stations].filter(s => s.ratio >= 1.0).sort((a, b) => b.ratio - a.ratio);
  const s2 = [...stations].filter(s => s.ratio >= 0.75 && s.ratio < 1.0).sort((a, b) => b.ratio - a.ratio);
  const dangerW = [...wSummary]
    .filter(w => ["Siaga 1","Siaga 2","Siaga 3"].includes(w.worst_status))
    .sort((a, b) => ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[b.worst_status] ?? 0) - ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[a.worst_status] ?? 0));
  const topW = dangerW[0];

  if (level === "bahaya") {
    const stNote = s1.length > 0
      ? (isId ? `${s1.length} sensor melewati ambang Siaga 1 — terparah: ${s1[0].nama}` : `${s1.length} sensor(s) past Alert-1 threshold — worst: ${s1[0].nama}`)
      : "";
    const rfNote = rainfall > 0 ? (isId ? `, hujan ${Math.round(rainfall)} mm/jam` : `, rain ${Math.round(rainfall)} mm/h`) : "";
    return isId
      ? `KONDISI KRITIS! ${stNote}${rfNote}. Ikuti instruksi BPBD segera — hubungi 117. Bersiap evakuasi sekarang.`
      : `CRITICAL! ${stNote}${rfNote}. Follow BPBD instructions immediately — call 117. Prepare to evacuate now.`;
  }

  if (level === "siaga") {
    const wlrPct = Math.round(wlr * 100);
    const sNote  = s2.length > 0
      ? (isId ? ` ${s2.length} sensor Siaga 2${s1.length > 0 ? `, ${s1.length} Siaga 1` : ""}.` : ` ${s2.length} Alert-2 sensor(s)${s1.length > 0 ? `, ${s1.length} Alert-1` : ""}.`)
      : "";
    const wNote  = topW
      ? (isId ? ` ${topW.wilayah} status ${topW.worst_status}.` : ` ${topW.wilayah} at ${topW.worst_status}.`)
      : "";
    return isId
      ? `Ketinggian air ${wlrPct}% dari ambang siaga.${sNote}${wNote} Siapkan tas darurat dan pantau setiap 15 menit.`
      : `Water level at ${wlrPct}% of alert threshold.${sNote}${wNote} Prepare emergency bag and monitor every 15 min.`;
  }

  if (level === "waspada") {
    const tNote = riskTrend === "increasing"
      ? (isId ? " Tren risiko sedang naik." : " Risk trend is rising.")
      : riskTrend === "decreasing"
      ? (isId ? " Situasi mulai membaik." : " Situation improving.")
      : "";
    const alertCount = s1.length + s2.length;
    const sNote = alertCount > 0
      ? (isId ? ` ${alertCount} sensor dalam kondisi siaga.` : ` ${alertCount} sensor(s) in alert state.`)
      : "";
    const rfNote = rainfall > 5
      ? (isId ? ` Curah hujan ${Math.round(rainfall)} mm/jam.` : ` Rainfall ${Math.round(rainfall)} mm/h.`)
      : "";
    return isId
      ? `Ada tanda awal yang perlu dipantau.${sNote}${tNote}${rfNote} Cek ketinggian air berkala.`
      : `Early warning signs detected.${sNote}${tNote}${rfNote} Check water levels regularly.`;
  }

  // aman
  const totalSt = stations.length;
  const sNote = totalSt > 0
    ? (isId ? ` Semua ${totalSt} sensor dalam batas normal.` : ` All ${totalSt} sensors within normal range.`)
    : "";
  return isId
    ? `Jakarta saat ini aman dari risiko banjir.${sNote} Tidak ada tanda-tanda mengkhawatirkan.`
    : `Jakarta is currently safe from flood risk.${sNote} No concerning signs detected.`;
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
    aman:    { label: isId ? "Aman"     : "Safe",    color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)" },
    waspada: { label: isId ? "Waspada"  : "Watch",   color: "var(--wsp)",  bg: "var(--wsp-soft)",  border: "var(--wsp-border)"  },
    siaga:   { label: isId ? "Siaga"    : "Alert",   color: "var(--s2)",   bg: "var(--s2-soft)",   border: "var(--s2-border)"   },
    bahaya:  { label: isId ? "Bahaya!"  : "Danger!", color: "var(--s1)",   bg: "var(--s1-soft)",   border: "var(--s1-border)"   },
  };
  const cfg = cfgMap[level] ?? cfgMap.waspada;
  // Dynamic description built from realtime sensor data — not hand-written strings
  const dynamicDesc = buildStatusDesc(riskData, isId);

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
        <p className="status-hero-desc">{dynamicDesc}</p>
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

/* ── Wilayah Forecast Grid — 12-hour BMKG timeline per district ──
   Differentiated from WilayahRainfallStrip (which shows current BMKG snapshot).
   This shows WHERE and WHEN rain will arrive in the next 1-12 hours.
*/
function WilayahForecastGrid({ wilayahSummary }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!wilayahSummary || wilayahSummary.length === 0) return null;

  const now = new Date();

  const getTimeLabel = (slot, i) => {
    if (!slot?.local_datetime) return i === 0 ? (isId ? "Skrg" : "Now") : `+${i * 3}j`;
    const dt = new Date(slot.local_datetime);
    const diffH = Math.round((dt - now) / 3_600_000);
    if (i === 0 || diffH <= 0) return isId ? "Skrg" : "Now";
    return isId ? `+${diffH}j` : `+${diffH}h`;
  };

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Prakiraan Cuaca 1–12 Jam ke Depan" : "1–12 Hour Weather Forecast"}
        </p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em" }}>
          ● BMKG
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column" }}>
        {wilayahSummary.map((w) => {
          const style  = WILAYAH_STATUS_STYLE[w.worst_status] ?? WILAYAH_STATUS_STYLE["Normal"];
          const shortName = w.wilayah.replace("Jakarta ", "Jkt ");
          const slots  = (w.forecast || []).slice(0, 4);
          // Detect first upcoming rain slot (excluding slot 0 = "now")
          const firstRainIdx = slots.findIndex((s, i) => i > 0 && s.weather_desc?.toLowerCase().includes("hujan"));
          const firstRainSlot = firstRainIdx > 0 ? slots[firstRainIdx] : null;

          return (
            <div key={w.wilayah} className="forecast-row">
              {/* Left label: wilayah name + TMA status */}
              <div className="forecast-row-label">
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", fontWeight: 700,
                  color: "var(--muted)", letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: "0.25rem" }}>
                  {shortName}
                </div>
                <span className="wilayah-status-badge"
                  style={{ background: style.bg, color: style.color, borderColor: style.border }}>
                  {w.worst_status}
                </span>
                {/* TMA sensor count */}
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.52rem", color: "var(--muted-2)", marginTop: "0.25rem" }}>
                  {w.tma_count > 0 && `${w.tma_count} TMA`}
                  {w.siaga1_count > 0 && (
                    <span className="wilayah-siaga-pip" style={{ background: "var(--s1-soft)", color: "var(--s1)", borderColor: "var(--s1-border)", marginLeft: 3 }}>
                      {w.siaga1_count}×S1
                    </span>
                  )}
                  {w.siaga2_count > 0 && (
                    <span className="wilayah-siaga-pip" style={{ background: "var(--s2-soft)", color: "var(--s2)", borderColor: "var(--s2-border)", marginLeft: 3 }}>
                      {w.siaga2_count}×S2
                    </span>
                  )}
                </div>
                {/* Rain-incoming alert */}
                {firstRainSlot && (
                  <div className="forecast-rain-alert" style={{ marginTop: "0.25rem" }}>
                    🌧 {getTimeLabel(firstRainSlot, firstRainIdx)}
                  </div>
                )}
              </div>

              {/* Forecast timeline slots */}
              <div className="forecast-slots">
                {slots.length > 0 ? slots.map((slot, i) => {
                  const isRain = slot.weather_desc?.toLowerCase().includes("hujan");
                  const icon = WEATHER_ICON[slot.weather_desc] ?? "🌤";
                  return (
                    <div key={i} className={`forecast-slot${isRain ? " rain" : ""}`}>
                      <span className="forecast-slot-time">{getTimeLabel(slot, i)}</span>
                      <span className="forecast-slot-icon">{icon}</span>
                      <span className="forecast-slot-desc">{slot.weather_desc ?? "—"}</span>
                      {slot.tmin != null && (
                        <span className="forecast-slot-temp">{slot.tmin}–{slot.tmax}°</span>
                      )}
                    </div>
                  );
                }) : (
                  <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted-2)", padding: "0.5rem" }}>
                    {isId ? "Tidak ada data prakiraan" : "No forecast data"}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p style={{ marginTop: "0.875rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", lineHeight: 1.6 }}>
        {isId
          ? "● Prakiraan BMKG per kota administrasi · Slot tiap ~3 jam · 🌧 menandakan hujan akan masuk · TMA bisa naik karena kiriman dari Bogor/Depok meski tidak hujan di Jakarta"
          : "● BMKG forecast per administrative city · Slots every ~3 hrs · 🌧 = rain incoming · TMA may rise from upstream Bogor/Depok flow even without local rain"}
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
  const anyRealtime = zones.some(z => z.isRealtime);

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Estimasi Risiko per Wilayah" : "Risk Estimate by Area"}
        </p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", letterSpacing: "0.06em", color: anyRealtime ? "var(--safe)" : "var(--muted-2)" }}>
          {anyRealtime ? (isId ? "● realtime + ML" : "● realtime + ML") : (isId ? "○ estimasi ML" : "○ ML estimate")}
        </span>
      </div>
      <div className="zone-cards">
        {zones.map((z, i) => {
          const cls = riskClass(z.risk_level);
          const color = colorMap[cls] ?? "var(--safe)";
          const wsStyle = z.worstStatus ? (WILAYAH_STATUS_STYLE[z.worstStatus] ?? WILAYAH_STATUS_STYLE["Normal"]) : null;
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
              {/* Realtime TMA detail when available */}
              {z.isRealtime && (z.siaga1Count > 0 || z.siaga2Count > 0 || z.tmaCount > 0) && (
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.25rem", marginTop: "0.1rem" }}>
                  {z.tmaCount > 0 && (
                    <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.55rem", color: "var(--muted-2)" }}>
                      {z.tmaCount} TMA
                    </span>
                  )}
                  {z.siaga1Count > 0 && (
                    <span className="wilayah-siaga-pip" style={{ background: "var(--s1-soft)", color: "var(--s1)", borderColor: "var(--s1-border)" }}>
                      {z.siaga1Count}×S1
                    </span>
                  )}
                  {z.siaga2Count > 0 && (
                    <span className="wilayah-siaga-pip" style={{ background: "var(--s2-soft)", color: "var(--s2)", borderColor: "var(--s2-border)" }}>
                      {z.siaga2Count}×S2
                    </span>
                  )}
                  {z.siaga3Count > 0 && (
                    <span className="wilayah-siaga-pip" style={{ background: "var(--wsp-soft)", color: "var(--wsp)", borderColor: "var(--wsp-border)" }}>
                      {z.siaga3Count}×S3
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p style={{ marginTop: "0.75rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.62rem", color: "var(--muted-2)" }}>
        {anyRealtime
          ? (isId
            ? "● Dihitung dari sensor DSDADKI realtime + prakiraan BMKG + bobot historis BPBD per wilayah"
            : "● Calculated from realtime DSDADKI sensors + BMKG forecast + historical BPBD weights per area")
          : (isId
            ? "○ Estimasi dari XGBoost + bias historis BPBD per zona. Data sensor wilayah belum tersedia."
            : "○ XGBoost estimate + historical BPBD bias per zone. District sensor data unavailable.")}
      </p>
    </div>
  );
}

/* ── Page ──────────────────────────────────────────────── */
export default function Home({ setRiskContext, riskLevel }) {
  const t = useT();
  const { lang } = useApp();
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

  // ── Realtime zone derivation — blends ML with DSDADKI sensor counts + BMKG ──
  const zones = useMemo(
    () => deriveRealtimeZones(
      score,
      riskData?.wilayahSummary ?? [],
      riskData?.rainfall ?? 0,
      riskData?.waterLevelRatio ?? 0.5,
    ),
    [score, riskData?.wilayahSummary, riskData?.rainfall, riskData?.waterLevelRatio],
  );

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

      {/* 3 core metric cards — all real sensor data */}
      <MetricsRow siaga1={realSiaga1} siaga2={realSiaga2} totalStations={totalStations} score={score} />

      {/* Per-wilayah rainfall — full-width, clearly readable */}
      <WilayahRainfallStrip
        wilayahSummary={riskData?.wilayahSummary}
        rainfall={riskData?.rainfall}
        lang={lang ?? "id"}
      />

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
          <RecommendationsPanel riskData={riskData} stations={stations} />
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

      {/* Per-wilayah 12h forecast — differentiated from rainfall strip above */}
      <WilayahForecastGrid wilayahSummary={riskData?.wilayahSummary} />

      {/* BMKG weather forecast — DKI aggregate (shown when wilayah grid unavailable) */}
      {(!riskData?.wilayahSummary?.length) && <ForecastPanel forecast={riskData?.bmkgForecast} />}

      {/* Floating chatbot */}
      <ChatBot riskContext={{ level, rainfall: riskData?.rainfall }} />
    </>
  );
}
