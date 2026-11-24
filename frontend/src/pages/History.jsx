/* ── Riwayat — what the site said, and what it saw, over the last days ─────
   Backend /history/summary (services/history_service.py): the decision log
   (one row per 15-minute refresh), satellite rain per day from the daily
   model, and each river post's highest Siaga band per day. Rows before the
   server logged its own decisions were replayed from the stored snapshots.
*/
import { useEffect, useMemo, useState } from "react";
import { useApp } from "../lib/appContext";
import { API_BASE } from "../lib/api";
import { LEVEL_COLOR, formatChance, formatWibAt, modelLevelKey } from "../lib/dashboardHelpers";
import { RiskBadge } from "../components/dashboard/primitives";
import { DayBars, TimeLine } from "../components/charts";
import LoadingSpinner from "../components/LoadingSpinner";

const RANGES = [7, 14, 30];
const TELEGRAM_URL = (import.meta.env.VITE_TELEGRAM_URL ?? "").trim();
const LEVELS = ["SAFE", "PRE_ALERT", "WARNING", "DANGER"];
const LEVEL_NAME = {
  id: { SAFE: "Aman", PRE_ALERT: "Waspada", WARNING: "Siaga", DANGER: "Bahaya" },
  en: { SAFE: "Safe", PRE_ALERT: "Watch", WARNING: "Alert", DANGER: "Danger" },
};
const BAND_COLOR = ["var(--safe)", "var(--wsp)", "var(--s2)", "var(--s1)"];
const BAND_NAME = ["Normal", "Siaga 3", "Siaga 2", "Siaga 1"];

// The learned layer's chance at which it raises each level; a level above what the chance reached was
// set by a safety rule (a post at Siaga 1 or water rising fast, or a BMKG warning).
const LEVEL_FROM = { PRE_ALERT: 0.2, WARNING: 0.65, DANGER: 0.8 };
function periodNote(p, isId) {
  const ruled = p.peak_chance == null || p.peak_chance < (LEVEL_FROM[p.peak_level] ?? 0);
  if (ruled) {
    return isId
      ? "dinaikkan aturan keselamatan (pos Siaga 1, air naik cepat, atau peringatan BMKG)"
      : "raised by a safety rule (a post at Siaga 1, water rising fast, or a BMKG warning)";
  }
  return isId ? `peluang tertinggi ${formatChance(p.peak_chance)}` : `peak chance ${formatChance(p.peak_chance)}`;
}

function dayLabel(iso, isId) {
  return new Date(`${iso}T00:00:00+07:00`).toLocaleDateString(isId ? "id-ID" : "en-GB",
    { day: "numeric", month: "short", timeZone: "Asia/Jakarta" });
}

function shortPost(name) {
  return (name || "").replace(/^(P\.A\.|P\.S\.|Pompa|Rumah Pompa|Bendung\.?)\s*/i, "").replace(/\s+\d+$/, "");
}

export default function History() {
  const { lang } = useApp();
  const isId = lang === "id";
  const [days, setDays] = useState(14);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const ctrl = new AbortController();
    setError(false);
    fetch(`${API_BASE}/history/summary?days=${days}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setData)
      .catch((e) => { if (e.name !== "AbortError") setError(true); });
    return () => ctrl.abort();
  }, [days]);

  const decisions = data?.decisions ?? [];
  const points = useMemo(() => decisions.map((d) => ({ t: Date.parse(d.t), y: d.chance, level: d.level })), [decisions]);
  const share = useMemo(() => {
    const counts = Object.fromEntries(LEVELS.map((l) => [l, 0]));
    decisions.forEach((d) => { if (d.level in counts) counts[d.level] += 1; });
    const n = Math.max(1, decisions.length);
    return LEVELS.map((l) => ({ level: l, share: counts[l] / n }));
  }, [decisions]);
  const xLabels = useMemo(() => {
    if (points.length < 2) return [];
    const t0 = points[0].t;
    const t1 = points[points.length - 1].t;
    return [0, 0.25, 0.5, 0.75, 1].map((f) => formatWibAt(t0 + f * (t1 - t0), isId, { time: false }));
  }, [points, isId]);
  const rainDays = data?.rain?.days ?? [];
  const postNames = Object.keys(data?.posts_daily ?? {}).sort();
  const postDays = useMemo(() => {
    const set = new Set();
    Object.values(data?.posts_daily ?? {}).forEach((d) => Object.keys(d).forEach((k) => set.add(k)));
    return [...set].sort();
  }, [data]);

  const names = LEVEL_NAME[isId ? "id" : "en"];

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{isId ? "Riwayat" : "History"}</h1>
          <p className="page-sub">
            {isId
              ? "Apa yang ditunjukkan situs ini, dan data yang dilihatnya, beberapa hari terakhir."
              : "What this site showed, and the data it saw, over the last days."}
          </p>
        </div>
        <div className="history-range" role="group" aria-label={isId ? "Rentang waktu" : "Time range"}>
          {RANGES.map((r) => (
            <button key={r} type="button" className={`history-range-btn${r === days ? " active" : ""}`}
                    aria-pressed={r === days} onClick={() => setDays(r)}>
              {isId ? `${r} hari` : `${r} days`}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="panel panel-body fade-in"><p className="station-sub" style={{ margin: 0 }}>
          {isId ? "Riwayat belum bisa dimuat. Coba lagi sebentar lagi." : "The history could not be loaded. Try again shortly."}
        </p></div>
      )}
      {!data && !error && <LoadingSpinner message={isId ? "Memuat riwayat..." : "Loading history..."} />}

      {data && (
        <>
          {/* 1 — the status the site showed */}
          <section className="panel panel-body fade-in history-card">
            <p className="station-title">{isId ? "Status Jakarta" : "Jakarta's status"}</p>
            <p className="station-sub">
              {isId
                ? "Garis: peluang banjir hari ini menurut model keputusan. Pita bawah: status yang tampil, tiap 15 menit."
                : "Line: today's flood chance from the decision model. Band below: the status shown, every 15 minutes."}
            </p>
            {points.length > 1 ? (
              <TimeLine points={points} yMax={1} levelStrip xLabels={xLabels} height={170}
                        ariaLabel={isId ? "Grafik peluang banjir Jakarta" : "Jakarta flood chance chart"}
                        thresholds={[
                          { y: 0.8, label: `${names.DANGER} 80%`, color: "var(--s1)" },
                          { y: 0.65, label: `${names.WARNING} 65%`, color: "var(--s2)" },
                          { y: 0.2, label: `${names.PRE_ALERT} 20%`, color: "var(--wsp)" },
                        ]} />
            ) : (
              <p className="station-sub">{isId ? "Belum ada data untuk rentang ini." : "No data for this range yet."}</p>
            )}
            <ul className="history-share">
              {share.map((s) => (
                <li key={s.level}>
                  <i style={{ background: LEVEL_COLOR[s.level] }} />
                  <span>{names[s.level]}</span>
                  <b>{Math.round(s.share * 100)}%</b>
                </li>
              ))}
            </ul>
            {data.replayed_until && (
              <p className="history-note">
                {isId
                  ? `Sampai ${formatWibAt(data.replayed_until, true)} WIB, status diputar ulang dari data yang tersimpan dengan model sekarang; setelahnya tercatat langsung.`
                  : `Up to ${formatWibAt(data.replayed_until, false)} WIB the status was replayed from stored data with the current models; after that it is logged live.`}
              </p>
            )}
          </section>

          {/* 2 — when the status went up */}
          <section className="panel panel-body fade-in history-card">
            <p className="station-title">{isId ? "Kapan status naik" : "When the status went up"}</p>
            {data.periods?.length ? (
              <ul className="history-periods">
                {data.periods.slice(0, 12).map((p) => (
                  <li key={p.start}>
                    <RiskBadge level={modelLevelKey(p.peak_level)} />
                    <span>
                      {formatWibAt(p.start, isId)} – {formatWibAt(p.end, isId, { date: formatWibAt(p.start, isId, { time: false }) !== formatWibAt(p.end, isId, { time: false }) })}
                    </span>
                    <small>{periodNote(p, isId)}</small>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="station-sub" style={{ marginBottom: 0 }}>
                {isId ? "Status tidak pernah naik di atas Aman dalam rentang ini." : "The status never rose above Safe in this range."}
              </p>
            )}
          </section>

          {/* 3 — satellite rain */}
          <section className="panel panel-body fade-in history-card">
            <p className="station-title">{isId ? "Hujan satelit per hari" : "Satellite rain per day"}</p>
            <p className="station-sub">
              {isId
                ? "NASA GPM IMERG Early, hari WIB yang sudah lengkap. Data tiba sekitar 5 jam setelah hujan."
                : "NASA GPM IMERG Early, complete WIB days. The data arrives about 5 hours after the rain."}
            </p>
            {rainDays.length ? (
              <DayBars unit=" mm" maxLabel={isId ? "maks" : "max"}
                       ariaLabel={isId ? "Grafik hujan harian" : "Daily rain chart"}
                       items={rainDays.slice(-days).map((d) => ({
                         label: dayLabel(d.date, isId),
                         title: `${dayLabel(d.date, isId)} · Jakarta ${d.jakarta_mean ?? "-"} mm (${isId ? "tertinggi" : "wettest"} ${d.jakarta_max ?? "-"} mm) · Bogor ${d.bogor ?? "-"} mm`,
                         values: [d.jakarta_mean, d.jakarta_max, d.bogor],
                       }))}
                       series={[
                         { name: isId ? "Jakarta rata-rata" : "Jakarta average", color: "var(--cyan)" },
                         { name: isId ? "Jakarta tertinggi" : "Jakarta wettest", color: "#8db4ff" },
                         { name: "Bogor", color: "#8a96a6" },
                       ]} />
            ) : (
              <p className="station-sub">{isId ? "Data hujan belum tersedia." : "No rain data yet."}</p>
            )}
            {data.rain?.today?.through && (
              <p className="history-note">
                {isId
                  ? `Hari ini sampai ${data.rain.today.through} WIB: Jakarta rata-rata ${data.rain.today.jakarta_mean} mm, tertinggi ${data.rain.today.jakarta_max} mm, Bogor ${data.rain.today.bogor} mm.`
                  : `Today up to ${data.rain.today.through} WIB: Jakarta ${data.rain.today.jakarta_mean} mm on average, wettest ${data.rain.today.jakarta_max} mm, Bogor ${data.rain.today.bogor} mm.`}
              </p>
            )}
          </section>

          {/* 4 — river posts per day */}
          <section className="panel panel-body fade-in history-card">
            <p className="station-title">{isId ? "Pos pantau air: status tertinggi per hari" : "Water-level posts: highest status per day"}</p>
            <p className="station-sub">
              {isId ? "Status resmi DSDA tiap pos. Ketuk pos di peta Beranda untuk grafik tinggi airnya." : "Each post's official DSDA status. Tap a post on the home map for its water-level chart."}
            </p>
            {postNames.length ? (
              <div className="post-grid-wrap">
                <table className="post-grid">
                  <thead>
                    <tr>
                      <th scope="col">{isId ? "Pos" : "Post"}</th>
                      {postDays.map((d) => <th key={d} scope="col">{dayLabel(d, isId).split(" ")[0]}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {postNames.map((name) => (
                      <tr key={name}>
                        <th scope="row">{shortPost(name)}</th>
                        {postDays.map((d) => {
                          const band = data.posts_daily[name][d];
                          return (
                            <td key={d} title={`${shortPost(name)} · ${dayLabel(d, isId)} · ${band == null ? "-" : BAND_NAME[band]}`}
                                style={{ background: band == null ? "transparent" : BAND_COLOR[band] }} />
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="station-sub">{isId ? "Data pos belum tersedia." : "No post data yet."}</p>
            )}
            <ul className="history-share">
              {BAND_NAME.map((b, i) => <li key={b}><i style={{ background: BAND_COLOR[i] }} /><span>{b}</span></li>)}
            </ul>
          </section>

          {TELEGRAM_URL && (
            <section className="panel panel-body fade-in history-card">
              <p className="station-title">{isId ? "Peringatan di Telegram" : "Alerts on Telegram"}</p>
              <p className="station-sub">
                {isId
                  ? "Gabung ke kanal Telegram deFlood.ai: pesan dikirim saat status Jakarta naik ke Siaga atau Bahaya, dan saat turun lagi. Tanpa akun di situs ini dan tanpa nomor telepon."
                  : "Join the deFlood.ai Telegram channel: a message goes out when Jakarta's status rises to Alert or Danger, and when it falls again. No account here and no phone number needed."}
              </p>
              <a className="btn btn-ghost" href={TELEGRAM_URL} target="_blank" rel="noopener noreferrer">
                {isId ? "Buka kanal Telegram" : "Open the Telegram channel"}
              </a>
            </section>
          )}
        </>
      )}
    </>
  );
}
