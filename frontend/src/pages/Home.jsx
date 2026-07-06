import { useEffect, useMemo } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";
import ChatBot from "../components/ChatBot";
import { useT, useApp } from "../lib/appContext";

import CollapsibleSection from "../components/shell/CollapsibleSection";
import DecisionHero from "../components/dashboard/DecisionHero";
import ActionCard from "../components/dashboard/ActionCard";
import GlanceChips from "../components/dashboard/GlanceChips";
import { StationPanel, SensorStrip } from "../components/dashboard/StationSection";
import { StaleDataBanner, ModelOutputCard } from "../components/dashboard/StatusModelSection";
import {
  WilayahForecastGrid,
  ForecastPanel,
  KecamatanZones,
} from "../components/dashboard/ForecastSection";
import { WeatherCurrentCard } from "../components/dashboard/WeatherSection";
import { CrewAnalysisPanel } from "../components/dashboard/CrewAnalysisPanel";

/* ── Beranda — citizen-first, decision-first ───────────────────────────────
   Per the FloodGuard HCI spec, the page answers three questions in order:
   1. "Is my area at risk right now?"  → DecisionHero
   2. "What should I do?"              → ActionCard (≤3 actions, 1 primary CTA)
   3. "Show me the situation"          → GlanceChips + live map
   Everything technical (AI analysis, sensor tables, forecasts) sits behind
   progressive-disclosure sections so a stressed user is never flooded with
   data they didn't ask for.
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
      {/* Slim page header — title + refresh only */}
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{t("home.title")}</h1>
        </div>
        <div className="header-actions">
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", color: "var(--muted-2)" }}>
            {lastUpdated
              ? t("home.sync", { time: lastUpdated.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) })
              : t("home.syncing")}
          </span>
          <button className="btn btn-ghost" onClick={refresh} disabled={refreshing} style={refreshing ? { opacity: 0.55, cursor: "wait" } : {}}>
            {refreshing ? "..." : t("home.refresh")}
          </button>
        </div>
      </div>

      {/* Data-integrity warning stays on top — trust before anything else */}
      <StaleDataBanner
        snapshotFetchedAt={riskData?.snapshotFetchedAt}
        onRefresh={refresh}
        refreshing={refreshing}
      />

      {/* 1 — Is my area at risk right now? */}
      <DecisionHero riskData={riskData} siaga1Count={realSiaga1} siaga2Count={realSiaga2} />

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
      </div>

      {/* Progressive disclosure — technical depth only on request */}
      <CollapsibleSection
        icon="⬡"
        iconBg="var(--cyan-soft)"
        iconColor="var(--cyan)"
        title={t("section.ai")}
        subtitle={t("section.aiSub")}
      >
        <div className="bento-2">
          <ModelOutputCard riskData={riskData} score={score} />
          <CrewAnalysisPanel />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        icon="◇"
        iconBg="var(--safe-soft)"
        iconColor="var(--safe)"
        title={t("section.sensors")}
        subtitle={t("section.sensorsSub", { n: stations.length })}
      >
        <SensorStrip riskData={riskData} />
        <div className="bento-2">
          <StationPanel stations={stations} quality={riskData?.stationQuality} />
          <KecamatanZones
            stations={stations}
            wilayahSummary={riskData?.wilayahSummary}
            globalProbability={score}
            districtRiskBreakdown={riskData?.districtRiskBreakdown}
          />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        icon="☂"
        iconBg="var(--wsp-soft)"
        iconColor="var(--wsp)"
        title={t("section.weather")}
        subtitle={t("section.weatherSub")}
      >
        <WeatherCurrentCard riskData={riskData} />
        <WilayahForecastGrid wilayahSummary={riskData?.wilayahSummary} />
        {(!riskData?.wilayahSummary?.length) && <ForecastPanel forecast={riskData?.bmkgForecast} />}
      </CollapsibleSection>

      {/* Floating chatbot — needs Home's riskContext, stays mounted here */}
      <ChatBot riskContext={{ ...riskData, level }} />
    </>
  );
}
