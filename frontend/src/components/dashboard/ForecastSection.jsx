/* ── Forecast section ─────────────────────────────────────────────────────
   BMKG per-wilayah 12-hour forecast grid (with a stale-snapshot empty state),
   the flat BMKG forecast fallback panel, and the per-district grouped flood
   probability list derived from realtime TMA ratios.
*/
import { useState, useEffect, useMemo } from "react";
import { useApp } from "../../lib/appContext";
import {
  WILAYAH_STATUS_STYLE,
  weatherCond,
  computeWilayahFloodProb,
  inferWilayah,
  probColor,
  stationClass,
  cleanStationName,
  stationRiskLevel,
  stationKecamatan,
} from "../../lib/dashboardHelpers";
import { WeatherGlyph, RiskBadge } from "./primitives";

/* ── Wilayah Forecast Grid — compact 12-hour BMKG timeline ──
   The single BMKG per-wilayah weather panel (includes the current slot).
   Shows WHERE and WHEN rain arrives over the next 1-12 hours.
   Design: compact rows, fixed-width slot cards, rain incoming pills.
*/
export function WilayahForecastGrid({ wilayahSummary }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!wilayahSummary || wilayahSummary.length === 0) return null;

  // Stale-snapshot fallback: the backend keeps only FUTURE BMKG slots
  // (inference.py: utc_dt >= now). When the snapshot is very old every slot is
  // in the past and gets filtered out, leaving an empty grid of dashes.
  // Show an honest "unavailable" state instead — but keep the siaga badges,
  // which still carry the last-known TMA status.
  const hasAnyForecast = wilayahSummary.some((w) => (w.forecast?.length ?? 0) > 0);
  if (!hasAnyForecast) {
    const sortedW = [...wilayahSummary].sort((a, b) => (b.worst_rank ?? 0) - (a.worst_rank ?? 0));
    return (
      <div className="panel panel-body fade-in">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
          <p className="panel-title" style={{ marginBottom: 0 }}>
            {isId ? "Prakiraan Cuaca 1–12 Jam ke Depan" : "1–12 Hour Weather Forecast"}
          </p>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em" }}>● BMKG</span>
        </div>
        <div style={{ textAlign: "center", padding: "1.25rem 1rem", border: "1px dashed var(--line-2)", borderRadius: 10 }}>
          <p style={{ fontSize: "0.85rem", color: "var(--wsp)", fontWeight: 600, margin: "0 0 0.35rem" }}>
            {isId ? "Prakiraan cuaca belum tersedia" : "Weather forecast unavailable"}
          </p>
          <p style={{ fontSize: "0.75rem", color: "var(--muted)", lineHeight: 1.55, margin: 0, maxWidth: 520, marginInline: "auto" }}>
            {isId
              ? "Semua slot prakiraan BMKG sudah lewat karena data sensor kedaluwarsa — scraper otomatis belum memperbarui. Status siaga di bawah memakai pembacaan terakhir."
              : "All BMKG forecast slots are in the past because the sensor data is stale — the auto-scraper hasn't refreshed. The alert badges below use the last reading."}
          </p>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.875rem" }}>
          {sortedW.map((w) => {
            const st = WILAYAH_STATUS_STYLE[w.worst_status] ?? WILAYAH_STATUS_STYLE["Normal"];
            return (
              <div key={w.wilayah} style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.66rem", fontWeight: 700, color: "var(--text)" }}>
                  {w.wilayah.replace("Jakarta ", "")}
                </span>
                <span className="wilayah-status-badge" style={{ background: st.bg, color: st.color, borderColor: st.border }}>
                  {w.worst_status}
                </span>
              </div>
            );
          })}
        </div>
        <p style={{ marginTop: "0.875rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", lineHeight: 1.6 }}>
          {isId
            ? "● Prakiraan akan muncul lagi setelah data sensor diperbarui"
            : "● The forecast returns once the sensor data refreshes"}
        </p>
      </div>
    );
  }

  const now = new Date();
  const getTimeLabel = (slot, i) => {
    if (!slot?.local_datetime) return i === 0 ? (isId ? "Skrg" : "Now") : `+${i * 6}j`;
    const dt = new Date(slot.local_datetime);
    const diffH = Math.round((dt - now) / 3_600_000);
    if (diffH <= 1) return isId ? "Skrg" : "Now";
    const rounded = diffH <= 4 ? diffH : Math.round(diffH / 3) * 3;
    return isId ? `+${rounded}j` : `+${rounded}h`;
  };

  // Sort by worst rank so most dangerous wilayah is at top
  const sorted = [...wilayahSummary].sort((a, b) => (b.worst_rank ?? 0) - (a.worst_rank ?? 0));
  const timeSlots = (sorted[0]?.forecast || []).slice(0, 4);

  return (
    <div className="panel panel-body fade-in">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Prakiraan Cuaca 1–12 Jam ke Depan" : "1–12 Hour Weather Forecast"}
        </p>
        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--cyan)", letterSpacing: "0.06em" }}>
          ● BMKG
        </span>
      </div>

      <div className="forecast-table">
        {/* Header: time labels */}
        <div className="forecast-table-header">
          <div className="fct-label-cell" />
          {timeSlots.map((slot, i) => (
            <div key={i} className="fct-time-header">
              {getTimeLabel(slot, i)}
            </div>
          ))}
          {/* Fill remaining columns if fewer than 4 slots */}
          {Array.from({ length: Math.max(0, 4 - timeSlots.length) }).map((_, i) => (
            <div key={`empty-h-${i}`} className="fct-time-header" style={{ color: "var(--muted-2)" }}>—</div>
          ))}
        </div>

        {/* Data rows per wilayah */}
        {sorted.map((w) => {
          const wstyle     = WILAYAH_STATUS_STYLE[w.worst_status] ?? WILAYAH_STATUS_STYLE["Normal"];
          const shortName  = w.wilayah.replace("Jakarta ", "");
          const slots      = (w.forecast || []).slice(0, 4);
          const firstRainI = slots.findIndex((s, idx) => idx > 0 && s.weather_desc?.toLowerCase().includes("hujan"));

          return (
            <div key={w.wilayah} className="forecast-table-row">
              {/* Label cell */}
              <div className="fct-label-cell">
                <div style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.68rem", fontWeight: 700,
                  color: "var(--text)", letterSpacing: "0.02em" }}>
                  {shortName}
                </div>
                <span className="wilayah-status-badge"
                  style={{ background: wstyle.bg, color: wstyle.color, borderColor: wstyle.border, marginTop: "0.2rem", display: "inline-block" }}>
                  {w.worst_status}
                </span>
                <div style={{ display: "flex", gap: "2px", flexWrap: "wrap", marginTop: "0.2rem" }}>
                  {w.siaga1_count > 0 && (
                    <span className="wilayah-siaga-pip" style={{ background: "var(--s1-soft)", color: "var(--s1)", borderColor: "var(--s1-border)" }}>
                      {w.siaga1_count}×S1
                    </span>
                  )}
                  {w.siaga2_count > 0 && (
                    <span className="wilayah-siaga-pip" style={{ background: "var(--s2-soft)", color: "var(--s2)", borderColor: "var(--s2-border)" }}>
                      {w.siaga2_count}×S2
                    </span>
                  )}
                  {firstRainI > 0 && (
                    <span className="forecast-rain-alert" style={{ marginTop: 0, display: "inline-flex", alignItems: "center", gap: 3 }}>
                      <WeatherGlyph cond="rain" size={11} /> {getTimeLabel(slots[firstRainI], firstRainI)}
                    </span>
                  )}
                </div>
              </div>

              {/* Forecast cells — always render 4, fill with dash if no data */}
              {[0, 1, 2, 3].map((i) => {
                const slot = slots[i];
                if (!slot) {
                  return (
                    <div key={i} className="fct-cell fct-cell-empty">
                      <span>—</span>
                    </div>
                  );
                }
                const isRain = slot.weather_desc?.toLowerCase().includes("hujan");
                return (
                  <div key={i} className={`fct-cell${isRain ? " rain" : ""}`}>
                    <span className="fct-icon"><WeatherGlyph cond={weatherCond(slot.weather_desc)} size={22} /></span>
                    <span className={`fct-desc${isRain ? " rain" : ""}`}>{slot.weather_desc ?? "—"}</span>
                    {slot.tmin != null && (
                      <span className="fct-temp">{slot.tmin}–{slot.tmax}°</span>
                    )}
                    {slot.humin != null && (
                      <span className="fct-hum">{slot.humin}%</span>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>

      <p style={{ marginTop: "0.875rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", lineHeight: 1.6 }}>
        {isId
          ? "● Prakiraan BMKG per kota administrasi · ikon biru = hujan akan masuk · Slot interval ~6 jam · TMA bisa naik meski tidak hujan di Jakarta (kiriman Bogor/Depok)"
          : "● BMKG per administrative city · blue icon = rain incoming · ~6h slot interval · TMA may rise without local rain (upstream Bogor/Depok)"}
      </p>
    </div>
  );
}

export function ForecastPanel({ forecast }) {
  const { lang } = useApp();
  const isId = lang === "id";
  if (!forecast || forecast.length === 0) return null;

  return (
    <div className="panel panel-body fade-in">
      <p className="panel-title">{isId ? "Prakiraan Cuaca BMKG — DKI Jakarta" : "BMKG Weather Forecast — DKI Jakarta"}</p>
      <div style={{ display: "flex", gap: "0.625rem", flexWrap: "wrap" }}>
        {forecast.map((slot, i) => {
          const dt = new Date(slot.local_datetime);
          const timeStr = dt.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
          const dateStr = dt.toLocaleDateString("id-ID", { day: "numeric", month: "short" });
          const isRain = slot.weather_desc?.toLowerCase().includes("hujan");
          return (
            <div key={i} style={{
              flex: "1 1 120px",
              background: isRain ? "rgba(0,120,255,0.06)" : "rgba(0,229,160,0.04)",
              border: `1px solid ${isRain ? "rgba(0,120,255,0.15)" : "var(--line)"}`,
              borderRadius: "10px", padding: "0.625rem 0.75rem",
              display: "flex", flexDirection: "column", gap: "0.25rem", minWidth: 0,
            }}>
              <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--muted-2)", letterSpacing: "0.06em" }}>
                {dateStr} · {timeStr}
              </span>
              <span style={{ color: isRain ? "var(--cyan)" : "var(--muted)" }}>
                <WeatherGlyph cond={weatherCond(slot.weather_desc)} size={24} />
              </span>
              <span style={{ fontSize: "0.72rem", color: "var(--text)", lineHeight: 1.3, fontWeight: 500 }}>{slot.weather_desc}</span>
              {slot.tmin != null && (
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted)" }}>
                  {slot.tmin}–{slot.tmax}°C · {slot.humin}–{slot.humax}%
                </span>
              )}
            </div>
          );
        })}
      </div>
      <p style={{ marginTop: "0.5rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)" }}>
        {isId ? "Sumber: BMKG cuaca.json — rata-rata DKI Jakarta" : "Source: BMKG cuaca.json — DKI Jakarta average"}
      </p>
    </div>
  );
}

/* ── KecamatanZones — per-district grouped flood probability ──────────────── */
export function KecamatanZones({ stations, wilayahSummary, globalProbability }) {
  const { lang } = useApp();
  const isId = lang === "id";

  const JAKARTA_ORDER = ["Jakarta Utara","Jakarta Barat","Jakarta Selatan","Jakarta Timur","Jakarta Pusat"];
  const OTHER_LABEL   = isId ? "Hulu / Luar Jakarta" : "Upstream / Outside Jakarta";

  const wMap = useMemo(() => Object.fromEntries((wilayahSummary ?? []).map(w => [w.wilayah, w])), [wilayahSummary]);

  const allGroups = useMemo(() => {
    const byWilayah = {};
    for (const s of (stations || [])) {
      const raw = s.wilayah || inferWilayah(s.lat, s.lon);
      const key = JAKARTA_ORDER.includes(raw) ? raw : OTHER_LABEL;
      (byWilayah[key] = byWilayah[key] || []).push(s);
    }
    Object.values(byWilayah).forEach(g => g.sort((a, b) => b.ratio - a.ratio));

    const gp = (globalProbability ?? 50) / 100;
    const jakartaGroups = JAKARTA_ORDER
      .filter(w => byWilayah[w]?.length)
      .map(w => ({ wilayah: w, stations: byWilayah[w], floodProb: computeWilayahFloodProb(wMap[w], byWilayah[w], gp) }))
      .sort((a, b) => b.floodProb - a.floodProb);

    return [
      ...jakartaGroups,
      ...(byWilayah[OTHER_LABEL]?.length ? [{ wilayah: OTHER_LABEL, stations: byWilayah[OTHER_LABEL], floodProb: null }] : []),
    ];
  }, [stations, wMap, globalProbability]);

  const [openSet, setOpenSet] = useState(() => new Set());
  const groupKey = allGroups.map(g => g.wilayah).join("|");
  useEffect(() => {
    if (allGroups.length > 0)
      setOpenSet(new Set(allGroups.slice(0, 2).map(g => g.wilayah)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupKey]);

  if (allGroups.length === 0) return null;

  const toggle = (w) => setOpenSet(prev => {
    const next = new Set(prev);
    next.has(w) ? next.delete(w) : next.add(w);
    return next;
  });
  const allOpen   = openSet.size >= allGroups.length;
  const toggleAll = () =>
    setOpenSet(allOpen ? new Set() : new Set(allGroups.map(g => g.wilayah)));

  const colorMap = { s1: "var(--s1)", s2: "var(--s2)", wsp: "var(--wsp)", ok: "var(--safe)" };

  return (
    <div className="panel fade-in" style={{ padding: "1.25rem 1.375rem" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
        <p className="panel-title" style={{ marginBottom: 0 }}>
          {isId ? "Kemungkinan Banjir per Wilayah" : "Flood Probability by District"}
        </p>
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <button
            type="button"
            onClick={toggleAll}
            style={{
              background: "none", border: "1px solid var(--line)", borderRadius: 6,
              padding: "0.22rem 0.6rem", cursor: "pointer",
              fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem",
              color: "var(--muted)", letterSpacing: "0.03em",
            }}
          >
            {allOpen ? (isId ? "Tutup Semua ↑" : "Collapse All ↑") : (isId ? "Buka Semua ↓" : "Expand All ↓")}
          </button>
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.58rem", color: "var(--safe)", letterSpacing: "0.06em" }}>● realtime</span>
        </div>
      </div>

      <div className="kec-zones-list">
        {allGroups.map(({ wilayah, stations: grpStns, floodProb }) => {
          const isUpstream = wilayah === OTHER_LABEL;
          const isOpen     = openSet.has(wilayah);
          const pColor     = floodProb != null ? probColor(floodProb) : "var(--muted)";

          return (
            <div key={wilayah} className={`kec-group${isUpstream ? " kec-group-upstream" : ""}`}>
              <button
                className="kec-group-header kec-group-btn"
                onClick={() => toggle(wilayah)}
                aria-expanded={isOpen}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0 }}>
                  <span className="kec-chevron" style={{ transform: isOpen ? "rotate(90deg)" : "rotate(0deg)", flexShrink: 0 }}>▶</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <span className="kec-group-title">{wilayah}</span>
                      <span className="kec-group-count">{grpStns.length} pos</span>
                    </div>
                    {floodProb != null && (
                      <div className="kec-prob-track">
                        <div className="kec-prob-fill" style={{ width: `${floodProb}%`, background: pColor }} />
                      </div>
                    )}
                  </div>
                </div>
                {floodProb != null ? (
                  <div className="wilayah-flood-prob">
                    <span className="wilayah-prob-pct" style={{ color: pColor }}>{floodProb}%</span>
                    <span className="wilayah-prob-label">{isId ? "banjir" : "flood"}</span>
                  </div>
                ) : (
                  <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.62rem", color: "var(--muted)" }}>—</span>
                )}
              </button>

              <div className={`kec-rows-wrapper${isOpen ? " open" : ""}`}>
                <div className="kec-rows">
                  {grpStns.map((s, i) => {
                    const cls    = stationClass(s.ratio);
                    const color  = colorMap[cls] ?? "var(--safe)";
                    const kec    = stationKecamatan(s.nama);
                    const label  = kec ? `Kec. ${kec.kecamatan}` : cleanStationName(s.nama);
                    const sublabel = kec ? kec.area : (s.lokasi || null);
                    return (
                      <div key={i} className="kec-row">
                        <div className="kec-row-identity">
                          <span className="kec-row-name">{label}</span>
                          {sublabel && <span className="kec-row-area">{sublabel}</span>}
                        </div>
                        <div className="kec-row-bar">
                          <div className="kec-row-fill" style={{ width: `${Math.min(s.ratio, 1) * 100}%`, background: color }} />
                        </div>
                        <span className="kec-row-pct" style={{ color }}>{Math.round(s.ratio * 100)}%</span>
                        <RiskBadge level={stationRiskLevel(s.ratio)} />
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p style={{ marginTop: "0.75rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.6rem", color: "var(--muted-2)", lineHeight: 1.5 }}>
        {isId
          ? "● Probabilitas = sensor TMA realtime + skala model XGBoost · Klik satu wilayah untuk membuka detail sensor · Diurutkan probabilitas tertinggi → terendah"
          : "● Probability = realtime TMA sensors + XGBoost model scale · Click one district to open sensor detail · Sorted highest → lowest probability"}
      </p>
    </div>
  );
}
