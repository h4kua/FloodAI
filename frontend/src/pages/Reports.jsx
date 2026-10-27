import { useState, useEffect, useCallback } from "react";
import { useApp } from "../lib/appContext";
import ChatBot from "../components/ChatBot";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const MAX_LEN = 500;

function timeAgo(isoString, isId) {
  const mins = Math.round((Date.now() - new Date(isoString).getTime()) / 60000);
  if (mins < 1) return isId ? "baru saja" : "just now";
  if (mins < 60) return isId ? `${mins} mnt lalu` : `${mins} min ago`;
  const hours = Math.round(mins / 60);
  return isId ? `${hours} jam lalu` : `${hours} h ago`;
}

/* ── Laporan warga ───────────────────────────────────────────────────────────
   First-hand observations from residents. Shown as unverified, only from the
   last 6 hours, and never used for the official status.
*/
export default function Reports({ riskLevel = "waspada", rainfall = 0 }) {
  const { lang } = useApp();
  const isId = lang !== "en";

  const [onlyFlood, setOnlyFlood]   = useState(false);
  const [reports, setReports]       = useState([]);
  const [maxAge, setMaxAge]         = useState(6);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState("");

  const [showForm, setShowForm]     = useState(false);
  const [severity, setSeverity]     = useState("alert");
  const [message, setMessage]       = useState("");
  const [name, setName]             = useState("");
  const [coords, setCoords]         = useState(null);
  const [locating, setLocating]     = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError]   = useState("");
  const [sent, setSent]             = useState(false);

  const fetchReports = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (onlyFlood) params.set("severity", "alert");
      if (coords) {
        params.set("near_lat", coords.lat);
        params.set("near_lon", coords.lon);
      }
      const res = await fetch(`${API_BASE}/reports?${params.toString()}`);
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      setReports(data.reports || []);
      setMaxAge(data.max_age_hours || 6);
    } catch {
      setError(isId ? "Laporan belum bisa dimuat. Coba lagi sebentar." : "Reports could not be loaded. Try again shortly.");
    } finally {
      setLoading(false);
    }
  }, [onlyFlood, coords, isId]);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const handleLocate = () => {
    if (!navigator.geolocation) {
      setFormError(isId ? "Browser tidak mendukung lokasi." : "Your browser does not support location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setLocating(false);
        setFormError("");
      },
      () => {
        setLocating(false);
        setFormError(isId ? "Lokasi tidak bisa diambil. Izinkan akses lokasi di browser." : "Could not get your location. Allow location access in the browser.");
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message.trim() || !coords) {
      setFormError(isId ? "Tulis apa yang Anda lihat dan bagikan lokasi Anda." : "Describe what you see and share your location.");
      return;
    }
    setSubmitting(true);
    setFormError("");
    try {
      const res = await fetch(`${API_BASE}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          severity,
          message: message.trim(),
          lat: coords.lat,
          lon: coords.lon,
          reporter_name: name.trim() || null,
        }),
      });
      if (res.status === 429) throw new Error("rate");
      if (!res.ok) throw new Error(String(res.status));
      setMessage("");
      setShowForm(false);
      setSent(true);
      await fetchReports();
    } catch (err) {
      setFormError(err.message === "rate"
        ? (isId ? "Terlalu banyak laporan dari jaringan ini. Coba lagi beberapa menit lagi." : "Too many reports from this network. Try again in a few minutes.")
        : (isId ? "Laporan gagal dikirim. Coba lagi." : "The report could not be sent. Try again."));
    } finally {
      setSubmitting(false);
    }
  };

  const sevLabel = (s) => (s === "alert"
    ? (isId ? "Air naik / banjir" : "Water rising / flooding")
    : (isId ? "Aman / surut" : "Clear / receding"));

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{isId ? "Laporan warga" : "Community reports"}</h1>
        </div>
      </div>

      <p className="reports-note fade-in">
        {isId
          ? `Kabar langsung dari warga, belum diverifikasi, hanya ${maxAge} jam terakhir. Laporan tidak mengubah status banjir resmi.`
          : `First-hand news from residents, unverified, last ${maxAge} hours only. Reports do not change the official flood status.`}
      </p>

      <button className="evac-primary-cta fade-in" onClick={() => { setShowForm((v) => !v); setSent(false); }}>
        <span className="evac-primary-cta-icon" aria-hidden="true">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" /></svg>
        </span>
        <span className="evac-primary-cta-text">
          <strong>{showForm ? (isId ? "Tutup formulir" : "Close the form") : (isId ? "Kirim laporan" : "Send a report")}</strong>
          {!showForm && <small>{isId ? "Ceritakan kondisi air di sekitar Anda" : "Tell others about the water around you"}</small>}
        </span>
      </button>

      {sent && <p className="reports-sent fade-in">{isId ? "Terima kasih, laporan Anda sudah tampil di bawah." : "Thank you, your report is now listed below."}</p>}

      {showForm && (
        <form className="panel panel-body reports-form fade-in" onSubmit={handleSubmit}>
          <div className="reports-severity" role="group" aria-label={isId ? "Kondisi" : "Condition"}>
            {["alert", "safe"].map((s) => (
              <button type="button" key={s} aria-pressed={severity === s}
                className={`risk-badge badge-${s === "alert" ? "s1" : "ok"}${severity === s ? " active" : ""}`}
                onClick={() => setSeverity(s)}>
                {sevLabel(s)}
              </button>
            ))}
          </div>
          <textarea
            className="route-input"
            rows={3}
            maxLength={MAX_LEN}
            placeholder={isId ? "Contoh: Air setinggi lutut di Jl. Kapuk Raya, mobil kecil tidak bisa lewat." : "e.g. Knee-deep water on Jl. Kapuk Raya, small cars cannot pass."}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
          />
          <span className="reports-count">{message.length}/{MAX_LEN}</span>
          <input
            className="route-input"
            type="text"
            maxLength={80}
            placeholder={isId ? "Nama (opsional)" : "Name (optional)"}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="reports-actions">
            <button type="button" className="btn btn-ghost" onClick={handleLocate} disabled={locating}>
              {locating ? (isId ? "Mencari lokasi…" : "Locating…")
                : coords ? (isId ? "✓ Lokasi dibagikan" : "✓ Location shared")
                : (isId ? "Bagikan lokasi saya" : "Share my location")}
            </button>
            <button type="submit" className="btn" disabled={submitting}>
              {submitting ? (isId ? "Mengirim…" : "Sending…") : (isId ? "Kirim" : "Send")}
            </button>
          </div>
          {formError && <p className="reports-error">{formError}</p>}
        </form>
      )}

      <div className="reports-filter-row" role="group" aria-label={isId ? "Saring laporan" : "Filter reports"}>
        <button className={`btn${onlyFlood ? " btn-ghost" : ""}`} aria-pressed={!onlyFlood} onClick={() => setOnlyFlood(false)}>
          {isId ? "Semua" : "All"}
        </button>
        <button className={`btn${onlyFlood ? "" : " btn-ghost"}`} aria-pressed={onlyFlood} onClick={() => setOnlyFlood(true)}>
          {isId ? "Hanya banjir" : "Flooding only"}
        </button>
      </div>

      <div className="panel panel-body fade-in">
        {loading && <p className="report-meta">{isId ? "Memuat laporan…" : "Loading reports…"}</p>}
        {error && <p className="reports-error">{error}</p>}
        {!loading && !error && reports.length === 0 && (
          <p className="report-meta">
            {isId ? `Belum ada laporan dalam ${maxAge} jam terakhir.` : `No reports in the last ${maxAge} hours.`}
          </p>
        )}
        <ul className="report-list">
          {reports.map((r) => (
            <li key={r.id} className={`report-item${r.is_pinned ? " report-pinned" : ""}`}>
              <div className="report-head">
                <span className={`risk-badge badge-${r.severity === "alert" ? "s1" : "ok"}`}>{sevLabel(r.severity)}</span>
                <span className="report-meta">{timeAgo(r.created_at, isId)}</span>
              </div>
              <p className="report-text">{r.message}</p>
              <p className="report-meta">
                {r.reporter_name || (isId ? "Anonim" : "Anonymous")}
                {" · "}
                {r.verified ? (isId ? "Terverifikasi" : "Verified") : (isId ? "Belum diverifikasi" : "Unverified")}
                {r.is_pinned ? (isId ? " · Terdekat dari Anda" : " · Nearest to you") : ""}
              </p>
            </li>
          ))}
        </ul>
      </div>

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />
    </>
  );
}
