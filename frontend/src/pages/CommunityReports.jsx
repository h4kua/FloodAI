import { useState, useEffect, useCallback } from "react";
import { useT, useApp } from "../lib/appContext";
import { getDeviceId, getProfile } from "../lib/deviceIdentity";
import ChatBot from "../components/ChatBot";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const FILTERS = ["all", "urgent", "verified", "map"];

function timeAgo(isoString, lang) {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return lang === "en" ? "just now" : "baru saja";
  if (mins < 60) return lang === "en" ? `${mins}m ago` : `${mins}mnt lalu`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return lang === "en" ? `${hours}h ago` : `${hours}jam lalu`;
  return lang === "en" ? `${Math.round(hours / 24)}d ago` : `${Math.round(hours / 24)}hr lalu`;
}

export default function CommunityReports({ riskLevel = "waspada", rainfall = 0 }) {
  const t = useT();
  const { lang } = useApp();
  const [filter, setFilter] = useState("all");
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [severity, setSeverity] = useState("alert");
  const [message, setMessage] = useState("");
  const [reporterName, setReporterName] = useState(getProfile().name || "");
  const [coords, setCoords] = useState(null);
  const [locating, setLocating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");

  const fetchReports = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (filter === "urgent") params.set("severity", "alert");
      if (filter === "verified") params.set("verified", "true");
      if (coords) {
        params.set("near_lat", coords.lat);
        params.set("near_lon", coords.lon);
      }
      const res = await fetch(`${API_BASE}/reports?${params.toString()}`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setReports(data.reports || []);
    } catch (e) {
      setError(lang === "en" ? "Failed to load reports" : "Gagal memuat laporan");
    } finally {
      setLoading(false);
    }
  }, [filter, coords, lang]);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const handleLocate = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        setLocating(false);
      },
      () => setLocating(false),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message.trim() || !coords) {
      setSubmitError(lang === "en"
        ? "Please share your location and write a message."
        : "Mohon bagikan lokasi dan tulis pesan.");
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    try {
      const res = await fetch(`${API_BASE}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          severity,
          message: message.trim(),
          lat: coords.lat,
          lon: coords.lon,
          reporter_name: reporterName.trim() || null,
          device_id: getDeviceId(),
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setMessage("");
      setShowForm(false);
      await fetchReports();
    } catch (e) {
      setSubmitError(lang === "en" ? "Failed to submit report." : "Gagal mengirim laporan.");
    } finally {
      setSubmitting(false);
    }
  };

  const visibleReports = filter === "map" ? reports : reports;

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{t("reports.title")}</h1>
        </div>
        <button className="btn btn-ghost" onClick={() => setShowForm((v) => !v)}>
          {showForm ? t("reports.cancel") : t("reports.new")}
        </button>
      </div>

      {showForm && (
        <div className="panel panel-body fade-in" style={{ marginBottom: "0.875rem" }}>
          <p className="panel-title">{t("reports.formTitle")}</p>
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {["alert", "safe"].map((s) => (
                <button
                  type="button"
                  key={s}
                  onClick={() => setSeverity(s)}
                  className={`risk-badge badge-${s === "alert" ? "s1" : "ok"}`}
                  style={{ cursor: "pointer", opacity: severity === s ? 1 : 0.4, border: severity === s ? undefined : "1px solid var(--line)" }}
                >
                  {s === "alert" ? t("reports.severityAlert") : t("reports.severitySafe")}
                </button>
              ))}
            </div>
            <input
              type="text"
              placeholder={t("reports.namePlaceholder")}
              value={reporterName}
              onChange={(e) => setReporterName(e.target.value)}
              className="route-input"
              style={{ width: "100%" }}
            />
            <textarea
              placeholder={t("reports.messagePlaceholder")}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="route-input"
              style={{ width: "100%", resize: "vertical", fontFamily: "inherit" }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
              <button type="button" className="btn btn-ghost" onClick={handleLocate} disabled={locating}>
                {locating ? t("reports.locating") : coords ? t("reports.locationSet") : t("reports.useLocation")}
              </button>
              <button type="submit" className="btn" style={{ background: "var(--cyan-soft)", color: "var(--cyan)", border: "1px solid var(--cyan-border)" }} disabled={submitting}>
                {submitting ? t("reports.submitting") : t("reports.submit")}
              </button>
            </div>
            {submitError && <p style={{ color: "var(--s1)", fontSize: "0.78rem" }}>{submitError}</p>}
          </form>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.875rem", flexWrap: "wrap" }}>
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`btn ${filter === f ? "" : "btn-ghost"}`}
            style={filter === f ? { background: "var(--cyan-soft)", color: "var(--cyan)", border: "1px solid var(--cyan-border)" } : undefined}
            onClick={() => setFilter(f)}
          >
            {t(`reports.filter.${f}`)}
          </button>
        ))}
      </div>

      <div className="panel panel-body fade-in">
        {loading && <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{t("reports.loading")}</p>}
        {error && <p style={{ color: "var(--s1)", fontSize: "0.85rem" }}>{error}</p>}
        {!loading && !error && visibleReports.length === 0 && (
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{t("reports.empty")}</p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
          {visibleReports.map((r) => (
            <div key={r.id} className={`report-item${r.is_pinned ? " report-pinned" : ""}`}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
                <span className={`risk-badge badge-${r.severity === "alert" ? "s1" : "ok"}`}>
                  {r.severity === "alert" ? t("reports.severityAlert") : t("reports.severitySafe")}
                </span>
                <span className="report-meta">{timeAgo(r.created_at, lang)}</span>
              </div>
              <p style={{ fontSize: "0.85rem", color: "var(--text)", lineHeight: 1.5, margin: 0 }}>{r.message}</p>
              <div className="report-meta">
                {r.reporter_name || (lang === "en" ? "Anonymous" : "Anonim")}
                {r.verified ? ` · ${t("reports.verifiedTag")}` : ""}
                {r.is_pinned ? ` · ${t("reports.pinnedTag")}` : ""}
              </div>
            </div>
          ))}
        </div>
      </div>

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />
    </>
  );
}
