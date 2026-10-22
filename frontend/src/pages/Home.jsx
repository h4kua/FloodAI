import { useEffect, useMemo, useState } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";
import ChatBot from "../components/ChatBot";
import { useT } from "../lib/appContext";

import CollapsibleSection from "../components/shell/CollapsibleSection";
import DecisionHero from "../components/dashboard/DecisionHero";
import WilayahStatus from "../components/dashboard/WilayahStatus";
import ActionCard from "../components/dashboard/ActionCard";
import GlanceChips from "../components/dashboard/GlanceChips";
import { StationPanel } from "../components/dashboard/StationSection";
import { StaleDataBanner, ModelOutputCard } from "../components/dashboard/StatusModelSection";
import { WilayahForecastGrid, ForecastPanel } from "../components/dashboard/ForecastSection";
import { WeatherCurrentCard } from "../components/dashboard/WeatherSection";
import { CrewAnalysisPanel } from "../components/dashboard/CrewAnalysisPanel";

const DETAIL_TABS = [
  { id: "ai",      labelKey: "section.tabAi" },
  { id: "sensors", labelKey: "section.tabSensors" },
  { id: "weather", labelKey: "section.tabWeather" },
];

/* ── Beranda — citizen-first, decision-first ───────────────────────────────
   Per the FloodGuard HCI spec, the page answers three questions in order:
   1. "Is my area at risk right now?"  → DecisionHero + WilayahStatus (per wilayah)
   2. "What should I do?"              → ActionCard (≤3 actions, 1 primary CTA)
   3. "Show me the situation"          → GlanceChips + live map
   Everything technical (AI analysis, sensor tables, forecasts) sits behind
   ONE collapsed "Detail" section with tabs, so a stressed user is never
   flooded with data they didn't ask for and only one panel shows at a time.
*/
export default function Home({ setRiskContext, riskLevel, onNavigate }) {
  const t = useT();
  const { riskData, loading, refreshing, error, refresh } = useFloodRisk();
  const level = riskData?.level ?? riskLevel ?? "waspada";
  const score = riskData?.riskScore ?? 45;
  const [detailTab, setDetailTab] = useState("ai");

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
      {/* Slim page header — title + refresh only (data time lives in the hero) */}
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{t("home.title")}</h1>
        </div>
        <div className="header-actions">
          <button className="btn btn-ghost" onClick={refresh} disabled={refreshing} style={refreshing ? { opacity: 0.55, cursor: "wait" } : {}}>
            {refreshing ? "…" : `↻ ${t("home.refresh")}`}
          </button>
        </div>
      </div>

      {/* Data-integrity warning stays on top — trust before anything else */}
      <StaleDataBanner snapshotFetchedAt={riskData?.snapshotFetchedAt} />

      {/* 1 — Is my area at risk right now? */}
      <DecisionHero riskData={riskData} siaga1Count={realSiaga1} siaga2Count={realSiaga2} />

      {/* 1b — …and in MY part of Jakarta? */}
      <WilayahStatus riskData={riskData} />

      {/* 2 + 3 — What do I do? / Show me. Desktop: map left, action+chips right */}
      <div className="home-main fade-in">
        <div className="home-action">
          <ActionCard riskData={riskData} stations={stations} onNavigate={onNavigate} />
        </div>
        <div className="home-glance">
          <GlanceChips
            riskData={riskData}
            siaga1={realSiaga1}
            siaga2={realSiaga2}
            totalStations={totalStations}
            calibratedStations={stations.length || null}
          />
        </div>
        <div className="home-map" id="map-anchor">
          <div className="panel map-panel">
            <div className="panel-body" style={{ paddingBottom: "0.75rem" }}>
              <p className="panel-title" style={{ marginBottom: 0 }}>{t("map.title")}</p>
            </div>
            <FloodMap riskScore={score} stations={stations} />
          </div>
        </div>
      </div>

      {/* Progressive disclosure — one collapsed section, one tab visible at a time */}
      <CollapsibleSection
        icon="☰"
        iconBg="var(--cyan-soft)"
        iconColor="var(--cyan)"
        title={t("section.detail")}
        subtitle={t("section.detailSub")}
      >
        <div className="detail-tabs" role="tablist">
          {DETAIL_TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={detailTab === tab.id}
              className={`detail-tab${detailTab === tab.id ? " active" : ""}`}
              onClick={() => setDetailTab(tab.id)}
            >
              {t(tab.labelKey)}
            </button>
          ))}
        </div>

        {detailTab === "ai" && (
          <ModelOutputCard riskData={riskData}>
            <CrewAnalysisPanel />
          </ModelOutputCard>
        )}

        {detailTab === "sensors" && <StationPanel stations={stations} />}

        {detailTab === "weather" && (
          <>
            <WeatherCurrentCard riskData={riskData} />
            <WilayahForecastGrid wilayahSummary={riskData?.wilayahSummary} />
            {(!riskData?.wilayahSummary?.length) && <ForecastPanel forecast={riskData?.bmkgForecast} />}
          </>
        )}
      </CollapsibleSection>

      {/* Floating chatbot — needs Home's riskContext, stays mounted here */}
      <ChatBot riskContext={{ ...riskData, level }} />
    </>
  );
}
