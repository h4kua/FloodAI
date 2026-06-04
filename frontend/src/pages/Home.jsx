import { useState, useEffect, useMemo } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";
import ChatBot from "../components/ChatBot";
import { useT, useApp } from "../lib/appContext";

/* ── Station name cleaner ───────────────────────────────── */
function cleanStationName(nama) {
  return (nama || "")
    .replace(/^P\.A\.\s*/i, "")
    .replace(/^P\.S\.\s*/i, "")
    .replace(/^Bendung\.\s*/i, "Bendung ")
    .trim();
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
            <span className="metric-real-badge" style={noteStyle}>● real</span>
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

function RecommendationsPanel({ riskData, stations = [], onNavigate }) {
  const t = useT();
  const { lang } = useApp();
  const isId = lang === "id";

  const rainfall  = riskData?.rainfall ?? 0;
  const riskTrend = riskData?.trendState?.risk_trend;
  const wSummary  = riskData?.wilayahSummary ?? [];

  const s1 = [...stations].filter(s => s.ratio >= 1.0).sort((a, b) => b.ratio - a.ratio);
  const s2 = [...stations].filter(s => s.ratio >= 0.75 && s.ratio < 1.0).sort((a, b) => b.ratio - a.ratio);

  const dangerW = [...wSummary]
    .filter(w => ["Siaga 1","Siaga 2","Siaga 3"].includes(w.worst_status))
    .sort((a, b) => ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[b.worst_status] ?? 0) - ({ "Siaga 1":3,"Siaga 2":2,"Siaga 3":1 }[a.worst_status] ?? 0));
  const topW = dangerW[0];

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

  // ── Functional buttons ────────────────────────────────────
  const goEvac = () => { if (onNavigate) { window.scrollTo(0, 0); onNavigate("alert"); } };
  const callBPBD = () => { window.location.href = "tel:117"; };
  const scrollSensors = () => {
    document.getElementById("station-panel-anchor")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const buttons = [];
  if (s1.length > 0) {
    const nm = s1[0].nama.split(/[\s/]/)[0];
    buttons.push({
      label: isId ? `Evakuasi — area ${nm}` : `Evacuate — ${nm} area`,
      primary: true, icon: "!",
      onClick: goEvac,
      title: isId ? "Buka halaman rute evakuasi" : "Open evacuation route page",
    });
  } else {
    buttons.push({
      label: isId ? "Pantau kondisi sensor" : "Monitor sensor conditions",
      primary: false, icon: "◉",
      onClick: scrollSensors,
      title: isId ? "Scroll ke tabel sensor" : "Scroll to sensor table",
    });
  }
  buttons.push({
    label: topW
      ? (isId ? `Rute evakuasi — ${topW.wilayah.replace("Jakarta ", "")}` : `Evacuation route — ${topW.wilayah.replace("Jakarta ", "")}`)
      : (isId ? "Cek rute evakuasi" : "Check evacuation routes"),
    primary: false, icon: "↗",
    onClick: goEvac,
    title: isId ? "Buka peta rute evakuasi" : "Open evacuation map",
  });
  buttons.push({
    label: isId ? "BPBD Jakarta — 117" : "BPBD Emergency: 117",
    primary: false, icon: "📞",
    onClick: callBPBD,
    title: isId ? "Telepon BPBD sekarang" : "Call BPBD now",
    isCall: true,
  });

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
          <button
            key={i}
            className={`action-btn${a.primary ? " primary" : ""}${a.isCall ? " action-btn-call" : ""}`}
            onClick={a.onClick}
            title={a.title}
          >
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

/* ── Model Output Card — realtime ML analysis with signal chips ─────────── */
function ModelOutputCard({ riskData, score }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!riskData?.interpretation) return null;

  const rainfall   = riskData.rainfall ?? 0;
  const wlr        = riskData.waterLevelRatio ?? 0;
  const riskTrend  = riskData.trendState?.risk_trend;
  const level      = riskData.level ?? "waspada";

  let snapTimeStr = null;
  if (riskData.snapshotFetchedAt) {
    const wib = new Date(new Date(riskData.snapshotFetchedAt).getTime() + 7 * 3_600_000);
    snapTimeStr = `${String(wib.getUTCHours()).padStart(2,"0")}:${String(wib.getUTCMinutes()).padStart(2,"0")}`;
  }

  const trendText = riskTrend === "increasing"
    ? (isId ? "↑ Naik" : "↑ Rising")
    : riskTrend === "decreasing"
    ? (isId ? "↓ Turun" : "↓ Falling")
    : (isId ? "→ Stabil" : "→ Stable");
  const trendColor = riskTrend === "increasing" ? "var(--wsp)" : riskTrend === "decreasing" ? "var(--safe)" : "var(--muted)";

  const scoreColor = score >= 70 ? "var(--s1)" : score >= 45 ? "var(--wsp)" : "var(--safe)";
  const levelColor = { aman: "var(--safe)", waspada: "var(--wsp)", siaga: "var(--s2)", bahaya: "var(--s1)" }[level] ?? "var(--wsp)";
  const levelLabel = { aman: isId ? "Aman" : "Safe", waspada: isId ? "Waspada" : "Watch",
    siaga: isId ? "Siaga" : "Alert", bahaya: isId ? "Bahaya" : "Danger" }[level] ?? "—";

  return (
    <div className="model-output-card fade-in">
      {/* Header row */}
      <div className="model-output-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <div className="model-output-icon">⬡</div>
          <div>
            <div className="model-output-title">
              {isId ? "ANALISIS MODEL" : "MODEL ANALYSIS"}
            </div>
            <div className="model-output-sub">
              XGBoost · {isId ? "14 fitur · update 15 mnt" : "14 features · 15 min update"}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "2px" }}>
          {snapTimeStr && (
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)" }}>
              {snapTimeStr} WIB
            </span>
          )}
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em" }}>● real</span>
        </div>
      </div>

      {/* Interpretation text */}
      <p className="model-output-text">{riskData.interpretation}</p>

      {/* Signal chips — key inputs the model is reading */}
      <div className="model-signal-chips">
        <div className="model-signal-chip">
          <span>{isId ? "Skor" : "Score"}</span>
          <strong style={{ color: scoreColor }}>{score}</strong>
        </div>
        <div className="model-signal-chip">
          <span>{isId ? "Status" : "Status"}</span>
          <strong style={{ color: levelColor }}>{levelLabel}</strong>
        </div>
        {wlr > 0 && (
          <div className="model-signal-chip">
            <span>{isId ? "Muka Air" : "Water Lvl"}</span>
            <strong style={{ color: wlr >= 0.75 ? "var(--wsp)" : "var(--text)" }}>{Math.round(wlr * 100)}%</strong>
          </div>
        )}
        {rainfall > 0 && (
          <div className="model-signal-chip">
            <span>{isId ? "Hujan" : "Rain"}</span>
            <strong style={{ color: "var(--cyan)" }}>{Math.round(rainfall)} mm/j</strong>
          </div>
        )}
        {riskTrend && (
          <div className="model-signal-chip">
            <span>{isId ? "Tren" : "Trend"}</span>
            <strong style={{ color: trendColor }}>{trendText}</strong>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Stale data warning — tampil kalau snapshot > 30 menit ─────────────── */
function StaleDataBanner({ snapshotFetchedAt, onRefresh, refreshing }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!snapshotFetchedAt) return null;
  const ageMin = Math.round((Date.now() - new Date(snapshotFetchedAt).getTime()) / 60000);
  if (ageMin < 30) return null;

  const ageLabel = ageMin >= 60
    ? (isId ? `${Math.floor(ageMin / 60)} jam ${ageMin % 60} mnt` : `${Math.floor(ageMin / 60)}h ${ageMin % 60}m`)
    : (isId ? `${ageMin} menit` : `${ageMin} min`);

  return (
    <div style={{
      background: "rgba(245,166,35,0.08)", border: "1px solid rgba(245,166,35,0.30)",
      borderRadius: "10px", padding: "0.625rem 1rem",
      display: "flex", alignItems: "center", gap: "0.75rem",
      fontSize: "0.78rem", color: "var(--wsp)",
    }}>
      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.85rem", fontWeight: 700, flexShrink: 0 }}>⚠</span>
      <span style={{ flex: 1, lineHeight: 1.5 }}>
        {isId
          ? `Data sensor sudah ${ageLabel} tidak diperbarui. Scraper otomatis mungkin mengalami gangguan.`
          : `Sensor data hasn't updated for ${ageLabel}. The automatic scraper may be down.`}
      </span>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={refreshing}
          style={{
            flexShrink: 0, background: "rgba(245,166,35,0.15)",
            border: "1px solid rgba(245,166,35,0.40)", borderRadius: "8px",
            padding: "0.35rem 0.75rem", color: "var(--wsp)",
            fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem",
            fontWeight: 700, cursor: refreshing ? "wait" : "pointer",
            letterSpacing: "0.04em", opacity: refreshing ? 0.5 : 1,
          }}
        >
          {refreshing ? "…" : (isId ? "↻ Refresh" : "↻ Refresh")}
        </button>
      )}
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

  // Trend badge — displayed as a pill so users immediately understand direction
  const trendCfg = riskTrend === "increasing"
    ? { text: isId ? "↑ Risiko Naik" : "↑ Risk Rising", color: "var(--wsp)", bg: "var(--wsp-soft)", border: "var(--wsp-border)",
        hint: isId ? "Sensor menunjukkan kondisi memburuk" : "Sensors show deteriorating conditions" }
    : riskTrend === "decreasing"
    ? { text: isId ? "↓ Risiko Turun" : "↓ Risk Falling", color: "var(--safe)", bg: "var(--safe-soft)", border: "var(--safe-border)",
        hint: isId ? "Kondisi mulai membaik" : "Conditions improving" }
    : { text: isId ? "→ Stabil" : "→ Stable", color: "var(--muted)", bg: "rgba(255,255,255,0.04)", border: "var(--line)",
        hint: isId ? "Tidak ada perubahan signifikan" : "No significant change" };

  // Mini sparkline from recent_probabilities — shows risk score over last ~45 min
  const probs = riskData?.trendState?.recent_probabilities ?? [];
  const sparkW = Math.max(probs.length, 2) * 22;
  const sparkH = 32;
  const sparkY = (p) => sparkH - 4 - Math.round(Math.min(p, 1) * (sparkH - 8));

  return (
    <div className={`status-hero fade-in level-${level}`}>
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
        {/* Trend pill badge — more user-friendly than raw arrow text */}
        <div className="hero-stat">
          <div style={{
            display: "inline-flex", alignItems: "center",
            background: trendCfg.bg, border: `1px solid ${trendCfg.border}`,
            borderRadius: "999px", padding: "0.3rem 0.75rem",
            fontFamily: "'JetBrains Mono',monospace",
            fontSize: "0.72rem", fontWeight: 700, color: trendCfg.color,
            letterSpacing: "0.03em", whiteSpace: "nowrap",
          }}>
            {trendCfg.text}
          </div>
          <div className="hero-stat-label" style={{ marginTop: "0.3rem" }}>{trendCfg.hint}</div>
        </div>
        {rainfall > 0 && (
          <div className="hero-stat">
            <div className="hero-stat-value" style={{ color: "var(--wsp)" }}>{Math.round(rainfall)} mm/j</div>
            <div className="hero-stat-label">{isId ? "Curah Hujan" : "Rainfall"}</div>
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
            <div className="hero-stat-label">{isId ? "Skor ~45 mnt" : "Score ~45 min"}</div>
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

/* ── Wilayah Forecast Grid — compact 12-hour BMKG timeline ──
   Differentiated from WilayahRainfallStrip (current snapshot).
   Shows WHERE and WHEN rain arrives over the next 1-12 hours.
   Design: compact rows, fixed-width slot cards, rain incoming pills.
*/
function WilayahForecastGrid({ wilayahSummary }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!wilayahSummary || wilayahSummary.length === 0) return null;

  const now = new Date();
  const getTimeLabel = (slot, i) => {
    if (!slot?.local_datetime) return i === 0 ? (isId ? "Skrg" : "Now") : `+${i * 6}j`;
    const dt = new Date(slot.local_datetime);
    const diffH = Math.round((dt - now) / 3_600_000);
    if (diffH <= 1) return isId ? "Skrg" : "Now";
    const rounded = diffH <= 4 ? diffH : Math.round(diffH / 3) * 3;
    return isId ? `+${rounded}j` : `+${rounded}h`;
  };

  // Sort by worst rank so most dangerous wilayah is at top
  const sorted = [...wilayahSummary].sort((a, b) => (b.worst_rank ?? 0) - (a.worst_rank ?? 0));
  const timeSlots = (sorted[0]?.forecast || []).slice(0, 4);

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Prakiraan Cuaca 1–12 Jam ke Depan" : "1–12 Hour Weather Forecast"}
        </p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em" }}>
          ● BMKG
        </span>
      </div>

      <div className="forecast-table">
        {/* Header: time labels */}
        <div className="forecast-table-header">
          <div className="fct-label-cell" />
          {timeSlots.map((slot, i) => (
            <div key={i} className="fct-time-header">
              {getTimeLabel(slot, i)}
            </div>
          ))}
          {/* Fill remaining columns if fewer than 4 slots */}
          {Array.from({ length: Math.max(0, 4 - timeSlots.length) }).map((_, i) => (
            <div key={`empty-h-${i}`} className="fct-time-header" style={{ color: "var(--muted-2)" }}>—</div>
          ))}
        </div>

        {/* Data rows per wilayah */}
        {sorted.map((w) => {
          const wstyle     = WILAYAH_STATUS_STYLE[w.worst_status] ?? WILAYAH_STATUS_STYLE["Normal"];
          const shortName  = w.wilayah.replace("Jakarta ", "");
          const slots      = (w.forecast || []).slice(0, 4);
          const firstRainI = slots.findIndex((s, idx) => idx > 0 && s.weather_desc?.toLowerCase().includes("hujan"));

          return (
            <div key={w.wilayah} className="forecast-table-row">
              {/* Label cell */}
              <div className="fct-label-cell">
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", fontWeight: 700,
                  color: "var(--text)", letterSpacing: "0.02em" }}>
                  {shortName}
                </div>
                <span className="wilayah-status-badge"
                  style={{ background: wstyle.bg, color: wstyle.color, borderColor: wstyle.border, marginTop: "0.2rem", display: "inline-block" }}>
                  {w.worst_status}
                </span>
                <div style={{ display: "flex", gap: "2px", flexWrap: "wrap", marginTop: "0.2rem" }}>
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
                  {firstRainI > 0 && (
                    <span className="forecast-rain-alert" style={{ marginTop: 0 }}>
                      🌧 {getTimeLabel(slots[firstRainI], firstRainI)}
                    </span>
                  )}
                </div>
              </div>

              {/* Forecast cells — always render 4, fill with dash if no data */}
              {[0, 1, 2, 3].map((i) => {
                const slot = slots[i];
                if (!slot) {
                  return (
                    <div key={i} className="fct-cell fct-cell-empty">
                      <span>—</span>
                    </div>
                  );
                }
                const isRain = slot.weather_desc?.toLowerCase().includes("hujan");
                const icon   = WEATHER_ICON[slot.weather_desc] ?? "🌤";
                return (
                  <div key={i} className={`fct-cell${isRain ? " rain" : ""}`}>
                    <span className="fct-icon">{icon}</span>
                    <span className={`fct-desc${isRain ? " rain" : ""}`}>{slot.weather_desc ?? "—"}</span>
                    {slot.tmin != null && (
                      <span className="fct-temp">{slot.tmin}–{slot.tmax}°</span>
                    )}
                    {slot.humin != null && (
                      <span className="fct-hum">{slot.humin}%</span>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <p style={{ marginTop: "0.875rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", lineHeight: 1.6 }}>
        {isId
          ? "● Prakiraan BMKG per kota administrasi · 🌧 = hujan akan masuk · Slot interval ~6 jam · TMA bisa naik meski tidak hujan di Jakarta (kiriman Bogor/Depok)"
          : "● BMKG per administrative city · 🌧 = rain incoming · ~6h slot interval · TMA may rise without local rain (upstream Bogor/Depok)"}
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

/* ── KecamatanZones — replaces ZoneCards; uses real DSDADKI station data ── */

// Infer Jakarta wilayah from lat/lon when backend wilayah field is absent.
// Boundaries are intentionally simple — priority order handles overlaps.
function inferWilayah(lat, lon) {
  if (!lat || !lon) return "";
  if (lat > -6.16 && lon > 106.75) return "Jakarta Utara";
  if (lon > 106.875)                return "Jakarta Timur";
  if (lat < -6.25)                  return "Jakarta Selatan";
  if (lon < 106.825)                return "Jakarta Barat";
  return "Jakarta Pusat";
}

function KecamatanZones({ stations }) {
  const { lang } = useApp();
  const isId = lang === "id";

  const JAKARTA_ORDER = ["Jakarta Utara","Jakarta Barat","Jakarta Selatan","Jakarta Timur","Jakarta Pusat"];
  const OTHER_LABEL   = isId ? "Hulu / Luar Jakarta" : "Upstream / Outside Jakarta";

  // Group by wilayah field or geo-inferred fallback
  const byWilayah = {};
  for (const s of (stations || [])) {
    const raw = s.wilayah || inferWilayah(s.lat, s.lon);
    const key = JAKARTA_ORDER.includes(raw) ? raw : OTHER_LABEL;
    (byWilayah[key] = byWilayah[key] || []).push(s);
  }
  Object.values(byWilayah).forEach(g => g.sort((a, b) => b.ratio - a.ratio));

  const jakartaGroups = JAKARTA_ORDER
    .filter(w => byWilayah[w]?.length)
    .map(w => ({ wilayah: w, stations: byWilayah[w] }))
    .sort((a, b) => b.stations[0].ratio - a.stations[0].ratio);

  const allGroups = [
    ...jakartaGroups,
    ...(byWilayah[OTHER_LABEL]?.length
      ? [{ wilayah: OTHER_LABEL, stations: byWilayah[OTHER_LABEL] }]
      : []),
  ];

  if (allGroups.length === 0) return null;

  // Default: first 2 groups (highest risk) open, rest collapsed
  const [openSet, setOpenSet] = useState(
    () => new Set(allGroups.slice(0, 2).map(g => g.wilayah))
  );

  const toggle = (w) => setOpenSet(prev => {
    const next = new Set(prev);
    next.has(w) ? next.delete(w) : next.add(w);
    return next;
  });

  const allOpen = openSet.size >= allGroups.length;
  const toggleAll = () =>
    setOpenSet(allOpen ? new Set() : new Set(allGroups.map(g => g.wilayah)));

  const colorMap = { s1: "var(--s1)", s2: "var(--s2)", wsp: "var(--wsp)", ok: "var(--safe)" };

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Estimasi Risiko per Kecamatan / Area" : "Risk by Sub-District / Area"}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <button onClick={toggleAll} className="kec-toggle-all-btn">
            {allOpen ? (isId ? "Tutup Semua ↑" : "Collapse All ↑") : (isId ? "Buka Semua ↓" : "Expand All ↓")}
          </button>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em" }}>
            ● realtime
          </span>
        </div>
      </div>

      <div className="kec-zones-list">
        {allGroups.map(({ wilayah, stations: grpStns }) => {
          const maxRatio   = grpStns[0]?.ratio ?? 0;
          const worstLevel = stationRiskLevel(maxRatio);
          const isUpstream = wilayah === OTHER_LABEL;
          const isOpen     = openSet.has(wilayah);

          return (
            <div key={wilayah} className={`kec-group${isUpstream ? " kec-group-upstream" : ""}`}>
              {/* Clickable accordion header */}
              <button
                className="kec-group-header kec-group-btn"
                onClick={() => toggle(wilayah)}
                aria-expanded={isOpen}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span className="kec-chevron" style={{ transform: isOpen ? "rotate(90deg)" : "rotate(0deg)" }}>
                    ▶
                  </span>
                  <span className="kec-group-title">{wilayah}</span>
                  <span className="kec-group-count">{grpStns.length} pos</span>
                </div>
                <RiskBadge level={worstLevel} />
              </button>

              {/* Collapsible body */}
              <div className={`kec-rows-wrapper${isOpen ? " open" : ""}`}>
                <div className="kec-rows">
                  {grpStns.map((s, i) => {
                    const cls   = stationClass(s.ratio);
                    const color = colorMap[cls] ?? "var(--safe)";
                    const label = cleanStationName(s.nama);
                    return (
                      <div key={i} className="kec-row">
                        <div className="kec-row-identity">
                          <span className="kec-row-name">{label}</span>
                          {s.lokasi && <span className="kec-row-area">{s.lokasi}</span>}
                        </div>
                        <div className="kec-row-bar">
                          <div className="kec-row-fill"
                            style={{ width: `${Math.min(s.ratio, 1) * 100}%`, background: color }} />
                        </div>
                        <span className="kec-row-pct" style={{ color }}>
                          {Math.round(s.ratio * 100)}%
                        </span>
                        <RiskBadge level={stationRiskLevel(s.ratio)} />
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p style={{ marginTop: "0.75rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", lineHeight: 1.5 }}>
        {isId
          ? "● Klik wilayah untuk expand/collapse · Sensor DSDADKI realtime · Diurutkan risiko tertinggi → terendah"
          : "● Click district to expand/collapse · Realtime DSDADKI sensors · Sorted highest → lowest risk"}
      </p>
    </div>
  );
}

/* ── WeatherCurrentCard — OpenWeather current conditions ────────────────── */
function windDirection(deg, isId) {
  if (deg == null) return "—";
  const id = ["U","TL","T","TG","S","BD","B","BL"];
  const en = ["N","NE","E","SE","S","SW","W","NW"];
  const idx = Math.round(deg / 45) % 8;
  return isId ? id[idx] : en[idx];
}

const OWM_ICON_MAP = {
  Clear: "☀", Clouds: "☁", Rain: "🌧", Drizzle: "🌦",
  Thunderstorm: "⛈", Snow: "❄", Mist: "🌫", Fog: "🌁",
  Haze: "🌫", Dust: "💨", Smoke: "🌫",
};

// WeatherCurrentCard — shows per-wilayah OWM data when available,
// falls back to single-point when openweatherWilayah is empty.
function WeatherCurrentCard({ riskData }) {
  const { lang } = useApp();
  const isId     = lang === "id";
  const owWilayah = riskData?.openweatherWilayah ?? {};
  const owCenter  = riskData?.openweather;
  const hasWilayah = Object.keys(owWilayah).length > 0;

  // ── Fallback: single-point card ───────────────────────────
  if (!hasWilayah) {
    const ow       = owCenter;
    const rainfall = riskData?.rainfall ?? 0;
    const temp     = ow?.temp ?? riskData?.temperature;
    const humidity = ow?.humidity ?? riskData?.humidity;
    if (!temp && !ow) return null;

    const weatherIcon = OWM_ICON_MAP[ow?.weather_main] ?? (rainfall > 5 ? "🌧" : "🌤");
    const descRaw = ow?.weather_desc ?? (rainfall > 20 ? "hujan lebat" : rainfall > 5 ? "hujan ringan" : "berawan");
    const desc = descRaw.charAt(0).toUpperCase() + descRaw.slice(1);

    const chips = [
      temp     != null && { icon: "🌡", label: isId ? "Suhu" : "Temp",     value: `${temp.toFixed(1)}°C`,       sub: ow?.feels_like != null ? `feels ${ow.feels_like.toFixed(1)}°` : null },
      humidity != null && { icon: "💧", label: isId ? "Lembap" : "Humidity", value: `${Math.round(humidity)}%` },
      { icon: "🌧", label: isId ? "Hujan" : "Rainfall", value: rainfall > 0 ? `${Math.round(rainfall)} mm/j` : (isId ? "Tidak hujan" : "No rain"), color: rainfall > 0 ? "var(--cyan)" : "var(--safe)" },
      ow?.wind_speed  != null && { icon: "💨", label: isId ? "Angin" : "Wind",    value: `${ow.wind_speed.toFixed(1)} m/s`, sub: windDirection(ow.wind_deg, isId) },
      ow?.pressure    != null && { icon: "📊", label: isId ? "Tekanan" : "Pressure", value: `${ow.pressure} hPa` },
      ow?.clouds      != null && { icon: "☁",  label: isId ? "Tutupan" : "Cloud",  value: `${ow.clouds}%` },
      ow?.visibility  != null && { icon: "👁",  label: isId ? "Pandang" : "Visibility", value: `${(ow.visibility / 1000).toFixed(0)} km` },
    ].filter(Boolean);

    return (
      <div className="weather-current-card fade-in">
        <div className="weather-current-header">
          <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
            <span style={{ fontSize: "2.75rem", lineHeight: 1 }}>{weatherIcon}</span>
            <div>
              <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.56rem", color: "var(--muted-2)", letterSpacing: "0.12em", textTransform: "uppercase", marginBottom: "0.1rem" }}>
                {isId ? "Cuaca Jakarta Sekarang" : "Jakarta Current Weather"}
              </div>
              <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1.1rem", fontWeight: 700, color: "var(--text)", letterSpacing: "-0.01em" }}>{desc}</div>
              {temp != null && (
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted)", marginTop: "0.1rem" }}>
                  {temp.toFixed(1)}°C
                  {ow?.feels_like != null && <span style={{ marginLeft: "0.4rem", color: "var(--muted-2)" }}>feels {ow.feels_like.toFixed(1)}°</span>}
                </div>
              )}
            </div>
          </div>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em", flexShrink: 0 }}>● OpenWeather</span>
        </div>
        <div className="weather-chips-grid">
          {chips.map((c, i) => (
            <div key={i} className="weather-chip">
              <span className="weather-chip-icon">{c.icon}</span>
              <div>
                <div className="weather-chip-label">{c.label}</div>
                <div className="weather-chip-value" style={c.color ? { color: c.color } : {}}>{c.value}</div>
                {c.sub && <div className="weather-chip-sub">{c.sub}</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // ── Per-wilayah grid (5 kota administrasi) ────────────────
  const WILAYAH_ORDER = ["Jakarta Utara","Jakarta Barat","Jakarta Selatan","Jakarta Timur","Jakarta Pusat"];
  const wilayahEntries = WILAYAH_ORDER
    .filter(w => owWilayah[w])
    .map(w => ({ wilayah: w, short: w.replace("Jakarta ", ""), ow: owWilayah[w] }));

  return (
    <div className="weather-current-card fade-in">
      <div className="weather-current-header" style={{ marginBottom: "0.875rem" }}>
        <div>
          <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.56rem", color: "var(--muted-2)", letterSpacing: "0.12em", textTransform: "uppercase" }}>
            {isId ? "Cuaca Per Wilayah Jakarta" : "Jakarta Weather by District"}
          </div>
          <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "0.88rem", fontWeight: 600, color: "var(--text)", marginTop: "0.15rem" }}>
            {isId ? "Data realtime 5 kota administrasi" : "Realtime data — 5 administrative cities"}
          </div>
        </div>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em", flexShrink: 0 }}>● OpenWeather</span>
      </div>

      <div className="ow-wilayah-grid">
        {wilayahEntries.map(({ wilayah, short, ow }) => {
          const icon    = OWM_ICON_MAP[ow.weather_main] ?? "🌤";
          const isRain  = ow.rainfall_1h > 0 || ow.weather_main === "Rain" || ow.weather_main === "Drizzle";
          const desc    = ow.weather_desc
            ? ow.weather_desc.charAt(0).toUpperCase() + ow.weather_desc.slice(1)
            : (isId ? "Berawan" : "Cloudy");
          return (
            <div key={wilayah} className={`ow-wilayah-card${isRain ? " rain" : ""}`}>
              <div className="ow-wilayah-card-header">
                <div className="ow-wilayah-name">{short}</div>
                <div className="ow-wilayah-icon">{icon}</div>
              </div>
              {ow.temp != null && (
                <div className="ow-wilayah-temp">{ow.temp.toFixed(1)}°C</div>
              )}
              <div className={`ow-wilayah-desc${isRain ? " rain" : ""}`}>{desc}</div>
              <div className="ow-wilayah-chips">
                {ow.humidity != null && (
                  <span className="ow-mini-chip">💧 {Math.round(ow.humidity)}%</span>
                )}
                {ow.wind_speed != null && (
                  <span className="ow-mini-chip">💨 {ow.wind_speed.toFixed(1)}m/s</span>
                )}
                {isRain && ow.rainfall_1h > 0 && (
                  <span className="ow-mini-chip rain">🌧 {ow.rainfall_1h.toFixed(1)}mm/j</span>
                )}
              </div>
              {ow.feels_like != null && (
                <div className="ow-wilayah-feels">feels {ow.feels_like.toFixed(1)}°</div>
              )}
            </div>
          );
        })}
      </div>

      <p style={{ marginTop: "0.625rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)", lineHeight: 1.5 }}>
        {isId
          ? "● Titik representatif per kota administrasi · Update tiap 15 menit bersama scraper"
          : "● Representative point per administrative city · Updates every 15 min with scraper"}
      </p>
    </div>
  );
}

/* ── Page ──────────────────────────────────────────────── */
export default function Home({ setRiskContext, riskLevel, onNavigate }) {
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
          <div className="header-info-col" style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.15rem" }}>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "var(--muted-2)" }}>
              {lastUpdated
                ? t("home.sync", { time: lastUpdated.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) })
                : t("home.syncing")}
            </span>
            {riskData?.snapshotFetchedAt && (() => {
              const snapTime = new Date(riskData.snapshotFetchedAt);
              const wibMs = snapTime.getTime() + 7 * 60 * 60 * 1000;
              const wibDate = new Date(wibMs);
              const hh = String(wibDate.getUTCHours()).padStart(2, "0");
              const mm = String(wibDate.getUTCMinutes()).padStart(2, "0");
              const stationsLabel = riskData.tmaStationsActive != null
                ? ` · ${riskData.tmaStationsActive} stasiun TMA`
                : "";
              return (
                <span className="header-sensor-time" style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", opacity: 0.7 }}>
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
      <StaleDataBanner
        snapshotFetchedAt={riskData?.snapshotFetchedAt}
        onRefresh={refresh}
        refreshing={refreshing}
      />

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
          <RecommendationsPanel riskData={riskData} stations={stations} onNavigate={onNavigate} />
        </div>
      </div>

      {/* Model analysis card — realtime ML output with signal chips */}
      <ModelOutputCard riskData={riskData} score={score} />

      {/* Real DSDADKI station table — all live sensor readings */}
      <div id="station-panel-anchor" />
      <StationPanel stations={stations} />

      {/* Kecamatan / area risk breakdown — real sensor data grouped by wilayah, sorted by ratio */}
      <KecamatanZones stations={stations} />

      {/* OpenWeather current conditions */}
      <WeatherCurrentCard riskData={riskData} />

      {/* Per-wilayah 12h BMKG forecast — table layout */}
      <WilayahForecastGrid wilayahSummary={riskData?.wilayahSummary} />

      {/* BMKG fallback when wilayah grid unavailable */}
      {(!riskData?.wilayahSummary?.length) && <ForecastPanel forecast={riskData?.bmkgForecast} />}

      {/* Floating chatbot */}
      <ChatBot riskContext={{ level, rainfall: riskData?.rainfall }} />
    </>
  );
}
