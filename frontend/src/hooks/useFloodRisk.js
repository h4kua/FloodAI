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
      const url = API_BASE ? `${API_BASE}/predict/realtime-native` : null;

      if (!url) {
        setError("Backend URL belum dikonfigurasi.");
        return;
      }

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
        rainfall: Math.round(json.features?.rainfall_mm ?? 0),
        riskScore: (() => { const v = (json.probability ?? 0) * 100; return v > 0 && v < 1 ? 1 : Math.round(v); })(),
        interpretation: json.risk_interpretation ?? "",
      });
      setLastUpdated(new Date());
    } catch {
      setError("Gagal memuat data. Coba lagi.");
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
