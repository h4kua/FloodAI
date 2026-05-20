import { useCallback, useEffect, useMemo, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const BULAN_ID = [
  "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
  "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
];

const STATUS = {
  AMAN: {
    label: "AMAN",
    className: "aman",
    emoji: "🟢",
    ringkasan: "Aktivitas normal",
    pesan: "Kondisi aman. Tidak ada indikasi banjir saat ini.",
  },
  WASPADA: {
    label: "WASPADA",
    className: "waspada",
    emoji: "🟡",
    ringkasan: "Tetap waspada",
    pesan: "Mulai ada tanda peningkatan risiko. Pantau perkembangan cuaca.",
  },
  SIAGA: {
    label: "SIAGA",
    className: "siaga",
    emoji: "🟠",
    ringkasan: "Siapkan evakuasi",
    pesan: "Risiko banjir meningkat. Siapkan barang penting dan rencana evakuasi.",
  },
  BAHAYA: {
    label: "BAHAYA",
    className: "bahaya",
    emoji: "🔴",
    ringkasan: "Evakuasi segera",
    pesan: "Potensi banjir tinggi. Segera menuju titik aman yang lebih tinggi.",
  },
};

const pad = (value) => String(value).padStart(2, "0");

const formatWaktuWIB = (date) => {
  const wib = new Date(date.getTime() + (7 * 60 + date.getTimezoneOffset()) * 60000);
  const tanggal = `${pad(wib.getDate())} ${BULAN_ID[wib.getMonth()]} ${wib.getFullYear()}`;
  const jam = `${pad(wib.getHours())}:${pad(wib.getMinutes())}`;
  return `${tanggal} ${jam} WIB`;
};

// Map the model's probability onto the four public-facing tiers using the
// thresholds the backend itself reports — no fabricated numbers.
const tierFromProbability = (probability, thresholds) => {
  const preAlert = thresholds?.pre_alert ?? 0.07;
  const warning = thresholds?.warning ?? 0.142;
  const danger = thresholds?.danger ?? 0.242;
  if (probability >= danger) return STATUS.BAHAYA;
  if (probability >= warning) return STATUS.SIAGA;
  if (probability >= preAlert) return STATUS.WASPADA;
  return STATUS.AMAN;
};

const trenLabel = (value) => {
  const map = {
    increasing: "meningkat",
    rising: "naik",
    decreasing: "menurun",
    falling: "turun",
    stable: "stabil",
    easing: "mereda",
    insufficient_data: "data belum cukup",
  };
  return map[value] ?? "data belum cukup";
};

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(null);

  const muatData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/predict/realtime-native`);
      if (!res.ok) {
        throw new Error(`Server membalas ${res.status}`);
      }
      const json = await res.json();
      setData(json);
      setUpdatedAt(new Date());
    } catch (_) {
      setError(
        `Tidak dapat terhubung ke server data di ${API_BASE_URL}. ` +
          "Pastikan layanan banjir sedang berjalan, lalu coba lagi."
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    muatData();
  }, [muatData]);

  const status = useMemo(() => {
    if (!data) return null;
    return tierFromProbability(data.probability ?? 0, data.risk_thresholds);
  }, [data]);

  const fitur = data?.features ?? {};
  const diagnostics = data?.diagnostics ?? {};
  const rekomendasi = Array.isArray(data?.recommended_action)
    ? data.recommended_action
    : [];

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">de</span>Flood
          <span className="brand-dot">.ai</span>
        </div>
        <p className="brand-sub">Pemantau Banjir Jakarta</p>
      </header>

      <main className="content">
        <section className="intro">
          <h1>Status Banjir Jakarta</h1>
          <p>
            Informasi kondisi banjir terkini untuk wilayah DKI Jakarta,
            diperbarui dari data cuaca, peringatan resmi, dan kondisi muka air.
          </p>
        </section>

        {error ? (
          <div className="notice error">
            <strong>Gagal memuat data</strong>
            <p>{error}</p>
            <button className="btn-update" type="button" onClick={muatData} disabled={isLoading}>
              {isLoading ? "Memuat..." : "Coba Lagi"}
            </button>
          </div>
        ) : !data ? (
          <div className="notice loading">
            <span className="spinner" />
            <p>Memuat status banjir terkini...</p>
          </div>
        ) : (
          <>
            <section className={`status-card ${status.className}`}>
              <div className="status-top">
                <span className="status-emoji" aria-hidden="true">{status.emoji}</span>
                <div>
                  <p className="status-eyebrow">Status saat ini · Jakarta</p>
                  <h2 className="status-label">{status.label}</h2>
                </div>
              </div>
              <p className="status-recommendation">{status.ringkasan}</p>
              <p className="status-message">
                {data.risk_interpretation || status.pesan}
              </p>
            </section>

            <section className="metrics">
              <div className="metric">
                <span className="metric-label">Curah hujan</span>
                <span className="metric-value">
                  {Math.round(fitur.rainfall_mm ?? 0)}
                  <small> mm/jam</small>
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Tren muka air</span>
                <span className="metric-value text">
                  {trenLabel(diagnostics?.trend_state?.water_level_trend)}
                </span>
              </div>
              <div className="metric">
                <span className="metric-label">Tren risiko</span>
                <span className="metric-value text">
                  {trenLabel(diagnostics?.trend_state?.risk_trend)}
                </span>
              </div>
            </section>

            {rekomendasi.length > 0 ? (
              <section className="recommendation-block">
                <h3>Yang sebaiknya dilakukan</h3>
                <ul>
                  {rekomendasi.map((item, index) => (
                    <li key={index}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            <div className="update-row">
              <span className="updated-at">
                {updatedAt ? `Diperbarui: ${formatWaktuWIB(updatedAt)}` : ""}
              </span>
              <button
                className="btn-update"
                type="button"
                onClick={muatData}
                disabled={isLoading}
              >
                {isLoading ? "Memuat..." : "Perbarui Data"}
              </button>
            </div>
          </>
        )}
      </main>

      <footer className="footer">
        <span>© {new Date().getFullYear()} deFlood.ai — Pemantau Banjir Jakarta</span>
        <span className="footer-note">
          Penilaian berlaku untuk wilayah Jakarta secara keseluruhan.
        </span>
      </footer>
    </div>
  );
}
