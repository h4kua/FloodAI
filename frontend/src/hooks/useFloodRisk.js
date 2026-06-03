import { useState, useEffect, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const POLL_INTERVAL_MS = 15 * 60 * 1000; // 15 minutes

export function useFloodRisk() {
  const [riskData, setRiskData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);

  const fetchRisk = useCallback(async () => {
    setError(null);
    try {
      // Use relative path when API_BASE is empty so the Vite dev proxy
      // forwards the request to the backend (no CORS issues in dev).
      // In production, VITE_API_BASE_URL is the full backend URL.
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
        // Sensor readings from feature vector
        humidity: json.features?.humidity_pct ?? null,
        temperature: json.features?.temperature_c ?? null,
        waterLevelRatio: json.features?.water_level_ratio ?? null,
        waterLevelDelta: json.features?.water_level_delta ?? null,
        // Diagnostic context
        rainfallAcc6h: json.diagnostics?.rainfall_acc_6h ?? null,
        bmkgAlerts: json.diagnostics?.bmkg_alerts_total ?? 0,
        trendState: json.diagnostics?.trend_state ?? null,
        // Model output
        recommendedActions: json.recommended_action ?? [],
        isOutlier: json.ood_detection?.is_outlier ?? false,
      });
      setLastUpdated(new Date());
    } catch (err) {
      const msg = err?.message ?? "";
      if (msg.includes("fetch") || msg.includes("NetworkError") || msg.includes("Failed")) {
        setError("Backend tidak terjangkau. Pastikan server berjalan di port 8080.");
      } else {
        setError(`Gagal memuat data: ${msg}`);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRisk();
    const interval = setInterval(fetchRisk, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchRisk]);

  return { riskData, loading, lastUpdated, error, refresh: fetchRisk };
}
