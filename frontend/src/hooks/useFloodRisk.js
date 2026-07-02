import { useState, useEffect, useCallback, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
// Poll every 5 minutes. The backend snapshot refreshes every 15 min, but the
// ML inference is cheap and the response includes snapshot_fetched_at so users
// can always see exactly how old the underlying sensor data is.
const POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

const RETRY_DELAY_MS = 30_000;

export function useFloodRisk() {
  const [riskData, setRiskData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const isInitialLoad = useRef(true);
  const retryTimer = useRef(null);

  const fetchRisk = useCallback(async (manual = false) => {
    setError(null);
    if (retryTimer.current) {
      clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
    if (manual) setRefreshing(true);
    try {
      const url = `${API_BASE}/predict/realtime-native`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Server membalas ${res.status}`);
      const json = await res.json();

      const levelMap = {
        SAFE: "aman",
        PRE_ALERT: "waspada",
        WARNING: "siaga",
        DANGER: "bahaya",
      };
      setRiskData({
        level: levelMap[json.risk_level] ?? "waspada",
        rainfall: json.features?.rainfall_mm ?? 0,
        riskScore: (() => {
          const v = (json.probability ?? 0) * 100;
          return v > 0 && v < 1 ? 1 : Math.round(v);
        })(),
        interpretation: json.risk_interpretation ?? "",
        humidity: json.features?.humidity_pct ?? null,
        temperature: json.features?.temperature_c ?? null,
        waterLevelRatio: json.features?.water_level_ratio ?? null,
        waterLevelDelta: json.features?.water_level_delta ?? null,
        rainfallAcc6h: json.diagnostics?.rainfall_acc_6h ?? null,
        bmkgAlerts: json.diagnostics?.bmkg_alerts_total ?? 0,
        trendState: json.diagnostics?.trend_state ?? null,
        recommendedActions: json.recommended_action ?? [],
        isOutlier: json.ood_detection?.is_outlier ?? false,
        bmkgForecast: json.bmkg_forecast ?? [],
        // Sensor snapshot freshness
        snapshotFetchedAt: json.snapshot_fetched_at || null,
        tmaStationsActive: json.diagnostics?.water_level_records ?? null,
        // Rainfall accumulation details
        rainfallAcc3h: json.diagnostics?.rainfall_acc_3h ?? null,
        rainfallTrendMmH: json.diagnostics?.rainfall_trend_mm_h ?? null,
        // Trend detail
        riskDelta1h: json.diagnostics?.trend_state?.risk_delta_1h ?? null,
        // Anomaly detection from IsolationForest / spike detection
        anomalyDetected: json.diagnostics?.trend_state?.anomaly_detected ?? false,
        anomalyType: json.diagnostics?.trend_state?.anomaly_type ?? null,
        // Seasonal context — 1 = Nov–Mar (wet season), 0 = Apr–Oct (dry)
        monsoonSeason: json.features?.monsoon_season ?? null,
        // Temporal feature reliability (false = not enough history yet)
        temporalFeaturesReady: json.diagnostics?.temporal_features_ready ?? false,
        // Real DSDADKI station readings sorted by siaga ratio desc.
        // Each entry: { nama, tinggi_air, siaga1, ratio, status_siaga }
        stations: json.stations ?? [],
        // Transparent 18-vs-38 breakdown: { total, scored, excluded_uncalibrated[],
        // excluded_pump[], excluded_bad_datum[] } — explains why fewer stations
        // are shown than exist at the DSDADKI source.
        stationQuality: json.diagnostics?.station_quality ?? null,
        // Per-wilayah TMA + BMKG forecast summary
        wilayahSummary: json.wilayah_summary ?? [],
        // Real per-kecamatan ML probability (additive — does not affect the
        // citywide risk_level/probability above). { kecamatan: { probability, risk_level, stations_used } }
        districtRiskBreakdown: json.district_risk_breakdown ?? {},
        // OpenWeather current conditions — pusat Jakarta
        openweather: json.openweather_current ?? null,
        // OpenWeather per kota administrasi Jakarta (5 wilayah)
        openweatherWilayah: json.openweather_wilayah ?? {},
      });
      setLastUpdated(new Date());
    } catch (err) {
      const msg = err?.message ?? "";
      if (msg.includes("fetch") || msg.includes("NetworkError") || msg.includes("Failed")) {
        setError("Backend tidak terjangkau. Mencoba lagi dalam 30 detik...");
      } else {
        setError(`Gagal memuat data: ${msg}`);
      }
      // Auto-retry after 30s so user doesn't need to manually refresh
      retryTimer.current = setTimeout(() => fetchRisk(false), RETRY_DELAY_MS);
    } finally {
      setLoading(false);
      setRefreshing(false);
      isInitialLoad.current = false;
    }
  }, []);

  const refresh = useCallback(() => fetchRisk(true), [fetchRisk]);

  useEffect(() => {
    fetchRisk();
    const interval = setInterval(() => fetchRisk(false), POLL_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      if (retryTimer.current) clearTimeout(retryTimer.current);
    };
  }, [fetchRisk]);

  return { riskData, loading, refreshing, lastUpdated, error, refresh };
}
