/* ── Station section ──────────────────────────────────────────────────────
   Everything driven by the DSDADKI water-level sensors: the alert ribbon,
   the headline metric row, the alert panel, the full station table, the
   transparent 18-vs-38 exclusion breakdown, and the sensor detail strip.
*/
import { useState } from "react";
import { useT, useApp } from "../../lib/appContext";
import { use3DTilt } from "../../hooks/use3DTilt";
import { stationClass, stationRiskLevel } from "../../lib/dashboardHelpers";
import { RiskBadge, ProbBar, MetricCard } from "./primitives";

// AlertRibbon uses REAL station counts from DSDADKI sensors.
export function AlertRibbon({ siaga1Count, siaga2Count, lastSync }) {
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

export function MetricsRow({ siaga1, siaga2, totalStations, calibratedStations, score }) {
  const t = useT();
  const noteStyle = { fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em", opacity: 0.85 };
  const cards = [
    { label: t("metric.alertZones"), value: siaga1 + siaga2, sub: t("metric.alertSub", { s1: siaga1, s2: siaga2 }), color: siaga1 > 0 ? "red" : siaga2 > 0 ? "orange" : "green" },
    { label: t("metric.activeStations"), value: totalStations ?? "—", sub: t("metric.activeStationsSub", { cal: calibratedStations ?? "—" }), color: "green" },
    { label: t("metric.riskScore"), value: score, sub: t("metric.riskSub"), color: score >= 70 ? "red" : score >= 45 ? "orange" : "green" },
  ];

  return (
    <div className="cmd-metrics">
      {cards.map((c) => (
        <MetricCard key={c.label} c={c} noteStyle={noteStyle} />
      ))}
    </div>
  );
}

// AlertPanel: shows REAL DSDADKI stations in alert state (ratio >= 0.75).
// Previously showed fake zone derivations — now 100% from sensor readings.
export function AlertPanel({ stations }) {
  const t = useT();
  const tiltRef = use3DTilt({ maxTilt: 6 });
  const alertStations = (stations || []).filter(s => s.ratio >= 0.75).slice(0, 5);

  if (alertStations.length === 0) return (
    <div ref={tiltRef} className="panel panel-body card-3d">
      <div className="card-3d-content">
        <p className="panel-title">{t("alert.title")}</p>
        <p style={{ fontSize: "0.8rem", color: "var(--muted)", fontFamily: "'JetBrains Mono',monospace" }}>
          {t("alert.none")}
        </p>
      </div>
    </div>
  );
  return (
    <div ref={tiltRef} className="panel panel-body card-3d">
      <div className="card-3d-content">
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
    </div>
  );
}

/* ── ExcludedStationsBreakdown — transparent "why fewer than the source" list ──
   Explains the 18-vs-38 gap: lists the stations excluded from scoring,
   grouped by reason (uncalibrated / pump / non-standard datum).
*/
export function ExcludedStationsBreakdown({ quality }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const [open, setOpen] = useState(false);
  if (!quality) return null;

  const groups = [
    {
      key: "uncal",
      items: quality.excluded_uncalibrated || [],
      label: isId ? "Belum terkalibrasi" : "Uncalibrated",
      reason: isId
        ? "Ambang siaga placeholder (Siaga 1 = 2 = 3) — belum disetel di sumber DSDADKI, jadi rasio TMA tidak bermakna."
        : "Placeholder thresholds (Alert 1 = 2 = 3) — never set at the DSDADKI source, so the TMA ratio is meaningless.",
      color: "var(--muted)",
    },
    {
      key: "pump",
      items: quality.excluded_pump || [],
      label: isId ? "Stasiun pompa" : "Pump stations",
      reason: isId
        ? "Ambangnya batas operasional mesin pompa, bukan ambang peringatan banjir."
        : "Thresholds are pump-machinery operational limits, not flood-warning thresholds.",
      color: "var(--cyan)",
    },
    {
      key: "datum",
      items: quality.excluded_bad_datum || [],
      label: isId ? "Datum non-standar" : "Non-standard datum",
      reason: isId
        ? "Tinggi air di luar rentang data latih model (mis. nilai negatif)."
        : "Water level outside the model's training range (e.g. negative values).",
      color: "var(--wsp)",
    },
  ].filter((g) => g.items.length > 0);

  const totalExcluded = groups.reduce((n, g) => n + g.items.length, 0);
  if (totalExcluded === 0) return null;

  return (
    <div style={{ marginTop: "0.75rem", borderTop: "1px solid var(--line)", paddingTop: "0.75rem" }}>
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          background: "none", border: "1px solid var(--line)", borderRadius: 8,
          padding: "0.5rem 0.75rem", cursor: "pointer",
          fontFamily: "'JetBrains Mono',monospace", fontSize: "0.64rem",
          color: "var(--muted)", letterSpacing: "0.03em",
        }}
      >
        <span>
          {isId
            ? `${totalExcluded} pos pantau dikecualikan dari skoring`
            : `${totalExcluded} stations excluded from scoring`}
        </span>
        <span style={{ color: "var(--muted-2)" }}>{open ? "↑" : "↓"}</span>
      </button>

      {open && (
        <div style={{ marginTop: "0.625rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {groups.map((g) => (
            <div key={g.key}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.2rem" }}>
                <span style={{ width: 6, height: 6, borderRadius: 2, background: g.color, flexShrink: 0 }} />
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", fontWeight: 700, color: "var(--text)", letterSpacing: "0.04em", textTransform: "uppercase" }}>
                  {g.label} · {g.items.length}
                </span>
              </div>
              <p style={{ fontSize: "0.68rem", color: "var(--muted-2)", lineHeight: 1.5, margin: "0 0 0.375rem 0.85rem" }}>
                {g.reason}
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", marginLeft: "0.85rem" }}>
                {g.items.map((it, i) => (
                  <span key={i} style={{
                    fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem",
                    color: "var(--muted)", background: "var(--panel-2)",
                    border: "1px solid var(--line)", borderRadius: 5, padding: "0.18rem 0.45rem",
                  }}>
                    {it.nama}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// StationPanel: full table of ALL real DSDADKI stations with live readings.
// Shows top 6 by default; user can expand to see all.
export function StationPanel({ stations, quality }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const [showAll, setShowAll] = useState(false);

  if (!stations || stations.length === 0) return null;

  const PREVIEW = 6;
  const displayed = showAll ? stations : stations.slice(0, PREVIEW);
  const hasMore = stations.length > PREVIEW;
  const total = quality?.total ?? null;
  const scored = quality?.scored ?? stations.length;

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "0.75rem", gap: "1rem" }}>
        <div>
          <p className="panel-title" style={{ marginBottom: "0.15rem" }}>
            {isId ? "Sensor Ketinggian Air — DSDADKI" : "Water Level Sensors — DSDADKI"}
          </p>
          <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", margin: 0, letterSpacing: "0.02em" }}>
            {total != null
              ? (isId
                ? `Menampilkan ${scored} pos terkalibrasi dari ${total} total di sumber`
                : `Showing ${scored} calibrated of ${total} total at the source`)
              : (isId ? "Pos pantau terkalibrasi" : "Calibrated monitoring stations")}
          </p>
        </div>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em", flexShrink: 0, whiteSpace: "nowrap" }}>● real</span>
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

      {/* Transparent 18-vs-38: which source stations were excluded and why */}
      <ExcludedStationsBreakdown quality={quality} />
    </div>
  );
}

export function SensorStrip({ riskData }) {
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
