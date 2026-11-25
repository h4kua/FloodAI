/* ── A post's water level over the last 2 days, inside its map popup ────────
   Backend /history/post (services/history_service.post_series): every stored
   15-minute reading of that post, in cm, with its own DSDA Siaga limits.
   Loaded only when the reader asks for it, so the map stays light.
*/
import { useState } from "react";
import { API_BASE } from "../lib/api";
import { formatWibAt } from "../lib/dashboardHelpers";
import { TimeLine } from "./charts";

const LIMITS = [
  { key: "siaga1", label: "Siaga 1", color: "var(--s1)" },
  { key: "siaga2", label: "Siaga 2", color: "var(--s2)" },
  { key: "siaga3", label: "Siaga 3", color: "var(--wsp)" },
];

export default function PostTrend({ name, isId }) {
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [series, setSeries] = useState(null);

  const load = () => {
    setState("loading");
    fetch(`${API_BASE}/history/post?name=${encodeURIComponent(name)}&days=2`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data) => { setSeries(data); setState("done"); })
      .catch(() => setState("error"));
  };

  // A click inside a Leaflet popup must not reach the map: Leaflet tells "clicked inside the popup" by walking
  // up from the clicked element, and this button is swapped out as soon as the state changes, so the walk
  // found nothing and the map took the click and closed the popup before the chart could load.
  const press = (e) => { e.stopPropagation(); load(); };

  if (state === "idle") {
    return (
      <div className="post-trend">
        <button type="button" className="post-trend-btn" onClick={press}>
          {isId ? "Lihat grafik 2 hari terakhir" : "Show the last 2 days"}
        </button>
      </div>
    );
  }
  if (state === "loading") return <p className="post-trend-note">{isId ? "Memuat grafik..." : "Loading chart..."}</p>;
  if (state === "error") {
    return (
      <div className="post-trend">
        <p className="post-trend-note">{isId ? "Grafik belum bisa dimuat." : "The chart could not be loaded."}</p>
        <button type="button" className="post-trend-btn" onClick={press}>{isId ? "Coba lagi" : "Try again"}</button>
      </div>
    );
  }

  const points = (series?.points ?? []).filter((p) => p.cm != null).map((p) => ({ t: Date.parse(p.t), y: p.cm }));
  if (points.length < 2) return <p className="post-trend-note">{isId ? "Belum ada cukup data untuk pos ini." : "Not enough data for this post yet."}</p>;
  const limits = series.limits ?? {};
  const top = Math.max(...points.map((p) => p.y));
  // Show the Siaga lines only when the water comes within reach of them, so a calm post's line is not flattened.
  const lines = LIMITS.filter((l) => limits[l.key] != null && limits[l.key] <= Math.max(top * 1.4, top + 50));
  const lowest = Math.min(...points.map((p) => p.y));
  const high = Math.max(top, ...lines.map((l) => limits[l.key]));
  const pad = Math.max(10, (high - lowest) * 0.12);
  const yMin = Math.max(0, lowest - pad);
  const yMax = high + pad;
  const t0 = points[0].t;
  const t1 = points[points.length - 1].t;
  const xLabels = [t0, (t0 + t1) / 2, t1].map((t) => formatWibAt(t, isId));

  return (
    <div className="post-trend">
      <TimeLine points={points} yMin={yMin} yMax={yMax} height={110} xLabels={xLabels}
                ariaLabel={isId ? `Tinggi air ${name}, 2 hari terakhir` : `${name} water level, last 2 days`}
                thresholds={lines.map((l) => ({ y: limits[l.key], label: `${l.label} ${Math.round(limits[l.key])}`, color: l.color }))} />
      <p className="post-trend-note">
        {isId
          ? `Tinggi air (cm), terendah ${Math.round(lowest)}, tertinggi ${Math.round(top)}.`
          : `Water level (cm), lowest ${Math.round(lowest)}, highest ${Math.round(top)}.`}
      </p>
    </div>
  );
}
