import { useEffect, useMemo, useState } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";
import ChatBot from "../components/ChatBot";
import { useT, useApp } from "../lib/appContext";

import { SectionDivider } from "../components/dashboard/primitives";
import {
  AlertRibbon,
  MetricsRow,
  AlertPanel,
  StationPanel,
  SensorStrip,
} from "../components/dashboard/StationSection";
import {
  StaleDataBanner,
  StatusHero,
  ModelOutputCard,
  RecommendationsPanel,
} from "../components/dashboard/StatusModelSection";
import {
  WilayahForecastGrid,
  ForecastPanel,
  KecamatanZones,
} from "../components/dashboard/ForecastSection";
import { WeatherCurrentCard } from "../components/dashboard/WeatherSection";
import { CrewAnalysisPanel } from "../components/dashboard/CrewAnalysisPanel";

/* Collapsed-by-default teaser for secondary panels (progressive disclosure) —
   avoids showing two full cards' worth of detail before the user asks for it. */
function SectionTeaser({ icon, iconBg, iconColor, title, subtitle, onExpand }) {
  return (
    <button className="panel panel-body section-teaser" onClick={onExpand}>
      <div className="section-teaser-icon" style={{ background: iconBg, color: iconColor }}>{icon}</div>
      <div style={{ textAlign: "left", minWidth: 0 }}>
        <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.63rem", fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: iconColor }}>
          {title}
        </div>
        <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", marginTop: 2 }}>
          {subtitle}
        </div>
      </div>
      <span className="section-teaser-chevron" style={{ color: iconColor }}>▾</span>
    </button>
  );
}

/* ── Page ──────────────────────────────────────────────────────────────────
   Home composes the dashboard from the feature sections under
   components/dashboard/*. All presentational components and pure helpers were
   extracted there; this file owns only the data wiring and the layout zones.
*/
export default function Home({ setRiskContext, riskLevel, onNavigate }) {
  const t = useT();
  const { lang } = useApp();
  const isId = lang === "id";
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

  // Progressive disclosure — secondary/duplicate-adjacent panels start collapsed.
  const [showDeepAnalysis, setShowDeepAnalysis] = useState(false);
  const [showDistrictBreakdown, setShowDistrictBreakdown] = useState(false);


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
      <MetricsRow siaga1={realSiaga1} siaga2={realSiaga2} totalStations={totalStations} calibratedStations={stations.length || null} score={score} />

      {/* Sensor detail strip — quick-read chips right under the headline metrics */}
      <SensorStrip riskData={riskData} />

      {/* ══ ZONE: Peta risiko & tindakan ══════════════════════════ */}
      <SectionDivider label={isId ? "Peta Risiko & Tindakan" : "Risk Map & Actions"} />
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

      {/* ══ ZONE: Analisis AI — ML selalu tampil, multi-agen di balik teaser ═ */}
      <SectionDivider label={isId ? "Analisis Kecerdasan Buatan" : "AI Analysis"} />
      <div className="bento-2">
        <ModelOutputCard riskData={riskData} score={score} />
        {showDeepAnalysis ? (
          <CrewAnalysisPanel />
        ) : (
          <SectionTeaser
            icon="◈" iconBg="rgba(168,85,247,0.08)" iconColor="#a855f7"
            title={isId ? "Analisis Multi-Agen AI" : "Multi-Agent AI Analysis"}
            subtitle={isId ? "3 agen spesialis · klik untuk analisis mendalam" : "3 specialist agents · click for deep analysis"}
            onExpand={() => setShowDeepAnalysis(true)}
          />
        )}
      </div>

      {/* ══ ZONE: Sensor & wilayah ══════════════════════════════════ */}
      <SectionDivider
        label={isId ? "Sensor & Wilayah" : "Sensors & Districts"}
        count={stations.length > 0 ? (isId ? `${stations.length} pos pantau` : `${stations.length} stations`) : null}
      />
      <div id="station-panel-anchor" />
      {/* Paired views: flat sorted sensor table ‖ per-district grouped probability
          (the latter starts collapsed — it re-derives from the same station data). */}
      <div className="bento-2">
        <StationPanel stations={stations} quality={riskData?.stationQuality} />
        {showDistrictBreakdown ? (
          <KecamatanZones
            stations={stations}
            wilayahSummary={riskData?.wilayahSummary}
            globalProbability={score}
            districtRiskBreakdown={riskData?.districtRiskBreakdown}
          />
        ) : (
          <SectionTeaser
            icon="◇" iconBg="var(--cyan-soft)" iconColor="var(--cyan)"
            title={isId ? "Kemungkinan Banjir per Wilayah" : "Flood Probability by District"}
            subtitle={isId ? "Rincian per kecamatan · klik untuk buka" : "Per-district breakdown · click to open"}
            onExpand={() => setShowDistrictBreakdown(true)}
          />
        )}
      </div>

      {/* ══ ZONE: Cuaca & prakiraan ═════════════════════════════════ */}
      <SectionDivider label={isId ? "Cuaca & Prakiraan" : "Weather & Forecast"} />

      {/* OpenWeather current conditions per district (observed) */}
      <WeatherCurrentCard riskData={riskData} />

      {/* Per-wilayah 12h BMKG forecast — full-width time-series table.
          This already includes the current slot, so a separate BMKG
          "rainfall strip" would duplicate it — removed. */}
      <WilayahForecastGrid wilayahSummary={riskData?.wilayahSummary} />

      {/* BMKG fallback when wilayah grid unavailable */}
      {(!riskData?.wilayahSummary?.length) && <ForecastPanel forecast={riskData?.bmkgForecast} />}

      {/* Floating chatbot */}
      <ChatBot riskContext={{ ...riskData, level }} />
    </>
  );
}
