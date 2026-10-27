import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useFloodRisk } from "../hooks/useFloodRisk";
import FloodMap from "../components/FloodMap";
import LoadingSpinner from "../components/LoadingSpinner";
import { useT } from "../lib/appContext";
import { postRiskLevel } from "../lib/dashboardHelpers";

import CollapsibleSection from "../components/shell/CollapsibleSection";
import DecisionHero from "../components/dashboard/DecisionHero";
import WilayahStatus from "../components/dashboard/WilayahStatus";
import { StationPanel } from "../components/dashboard/StationSection";
import { StaleDataBanner, ModelOutputCard } from "../components/dashboard/StatusModelSection";
import { WilayahForecastGrid, ForecastPanel } from "../components/dashboard/ForecastSection";
import { WeatherCurrentCard } from "../components/dashboard/WeatherSection";
import { CrewAnalysisPanel } from "../components/dashboard/CrewAnalysisPanel";

// The chatbot (and its ~60 KB offline knowledge base) loads after the page,
// so the status card is not held up by it.
const ChatBot = lazy(() => import("../components/ChatBot"));

const DETAIL_TABS = [
  { id: "ai",      labelKey: "section.tabAi" },
  { id: "sensors", labelKey: "section.tabSensors" },
  { id: "weather", labelKey: "section.tabWeather" },
];

/* ── Beranda — citizen-first, decision-first ───────────────────────────────
   Per the FloodGuard HCI spec, the page answers three questions in order:
   1. "Is my area at risk right now?"  → DecisionHero + WilayahStatus (per wilayah)
   2. "Show me the situation"          → live map, full width
   Everything technical (AI analysis, sensor tables, forecasts) sits behind
   ONE collapsed "Detail" section with tabs, so a stressed user is never
   flooded with data they didn't ask for and only one panel shows at a time.
*/
export default function Home({ setRiskContext, riskLevel }) {
  const t = useT();
  const { riskData, loading, refreshing, error, refresh } = useFloodRisk();
  const level = riskData?.level ?? riskLevel ?? "waspada";
  const score = riskData?.riskScore ?? 45;
  const [detailTab, setDetailTab] = useState("ai");

  // WAI-ARIA tabs: arrow keys / Home / End move between tabs (roving tabindex).
  const onTabKeyDown = (e) => {
    const ids = DETAIL_TABS.map((tab) => tab.id);
    const i = ids.indexOf(detailTab);
    const next = { ArrowRight: (i + 1) % ids.length, ArrowLeft: (i - 1 + ids.length) % ids.length,
                   Home: 0, End: ids.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    setDetailTab(ids[next]);
    document.getElementById(`detail-tab-${ids[next]}`)?.focus();
  };

  useEffect(() => {
    if (riskData?.level) {
      setRiskContext({ level: riskData.level, rainfall: riskData.rainfall ?? 0 });
    }
  }, [riskData, setRiskContext]);

  // ── Real station counts from DSDADKI sensors (NOT derived from ML zones) ──
  const stations    = riskData?.stations ?? [];
  const realSiaga1  = useMemo(() => stations.filter(s => postRiskLevel(s) === "SIAGA_1").length, [stations]);
  const realSiaga2  = useMemo(() => stations.filter(s => postRiskLevel(s) === "SIAGA_2").length, [stations]);

  if (loading) return <LoadingSpinner message="Mengambil data realtime..." />;

  if (error) return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem", padding: "3rem 1rem", textAlign: "center" }}>
      <p style={{ fontWeight: 700, color: "var(--text)" }}>{t("error.load")}</p>
      <p style={{ fontSize: "0.82rem", color: "var(--muted)" }}>{error === "unreachable" ? t("error.unreachable") : error}</p>
      <button className="btn btn-ghost" aria-label={t("home.refresh")} onClick={refresh}>{t("error.retry")}</button>
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
            <span aria-hidden="true">↻</span>
            <span className="btn-label">{refreshing ? "…" : t("home.refresh")}</span>
          </button>
        </div>
      </div>

      {/* Data-integrity warning stays on top — trust before anything else */}
      <StaleDataBanner snapshotFetchedAt={riskData?.snapshotFetchedAt} />

      {/* 1 — Is my area at risk right now? */}
      <DecisionHero riskData={riskData} siaga1Count={realSiaga1} siaga2Count={realSiaga2} />

      {/* 1b — …and in MY part of Jakarta? */}
      <WilayahStatus riskData={riskData} />

      {/* 2 — Show me: the map, full width */}
      <div className="panel map-panel fade-in" id="map-anchor">
        <div className="panel-body" style={{ paddingBottom: "0.75rem" }}>
          <p className="panel-title" style={{ marginBottom: 0 }}>{t("map.title")}</p>
        </div>
        <FloodMap riskScore={score} stations={stations} rainfall={riskData?.rainfall ?? 0} />
      </div>

      {/* Progressive disclosure — one collapsed section, one tab visible at a time */}
      <CollapsibleSection
        icon="☰"
        iconBg="var(--cyan-soft)"
        iconColor="var(--cyan)"
        title={t("section.detail")}
        subtitle={t("section.detailSub")}
      >
        <div className="detail-tabs" role="tablist" aria-label={t("section.detail")} onKeyDown={onTabKeyDown}>
          {DETAIL_TABS.map((tab) => (
            <button
              key={tab.id}
              id={`detail-tab-${tab.id}`}
              role="tab"
              aria-selected={detailTab === tab.id}
              aria-controls="detail-tabpanel"
              tabIndex={detailTab === tab.id ? 0 : -1}
              className={`detail-tab${detailTab === tab.id ? " active" : ""}`}
              onClick={() => setDetailTab(tab.id)}
            >
              {t(tab.labelKey)}
            </button>
          ))}
        </div>

        <div id="detail-tabpanel" role="tabpanel" aria-labelledby={`detail-tab-${detailTab}`} tabIndex={0}
             style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
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
        </div>
      </CollapsibleSection>

      {/* Floating chatbot — needs Home's riskContext, stays mounted here */}
      <Suspense fallback={null}>
        <ChatBot riskContext={{ ...riskData, level }} />
      </Suspense>
    </>
  );
}
