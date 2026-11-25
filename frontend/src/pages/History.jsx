/* ── Riwayat — what the site said over the last days, one tile per day ─────
   Backend /history/summary (services/history_service.py): the decision log (one row per 15-minute refresh), the
   satellite rain per day and each river post's highest Siaga band per day. Tap a day for its detail; the long
   chart and the post table sit under "Lebih rinci". Rows before the server logged its own decisions were replayed
   from the stored snapshots with the current models.
*/
import { useEffect, useMemo, useState } from "react";
import { useApp } from "../lib/appContext";
import { API_BASE } from "../lib/api";
import { LEVEL_COLOR, formatChance, formatWibAt } from "../lib/dashboardHelpers";
import { TimeLine } from "../components/charts";
import LoadingSpinner from "../components/LoadingSpinner";

const RANGES = [7, 14, 30];
const TELEGRAM_URL = (import.meta.env.VITE_TELEGRAM_URL ?? "").trim();
const LEVELS = ["SAFE", "PRE_ALERT", "WARNING", "DANGER"];
const RANK = { SAFE: 0, PRE_ALERT: 1, WARNING: 2, DANGER: 3 };
const NAMES = {
  id: { SAFE: "Aman", PRE_ALERT: "Waspada", WARNING: "Siaga", DANGER: "Bahaya" },
  en: { SAFE: "Safe", PRE_ALERT: "Watch", WARNING: "Alert", DANGER: "Danger" },
};
// The learned layer's chance at which it raises each level; a level above what the chance reached was set by a
// safety rule (a post at Siaga 1, water rising fast on a high post, or a BMKG warning).
const LEVEL_FROM = { PRE_ALERT: 0.2, WARNING: 0.65, DANGER: 0.8 };
const BAND_COLOR = ["var(--safe)", "var(--wsp)", "var(--s2)", "var(--s1)"];
const BAND_NAME = ["Normal", "Siaga 3", "Siaga 2", "Siaga 1"];

// Days whose recorded status is known to be wrong, with the reason: shown under the day instead of rewriting the log.
const KNOWN_ISSUES = {
  "2026-11-24": {
    id: "Bahaya pada hari ini sebagian besar adalah kesalahan sistem: aturan keselamatan membaca kenaikan kecil di Bendung Katulampa sebagai banjir kiriman. Sudah diperbaiki pada 25 Nov.",
    en: "Most of today's Danger was a system error: a safety rule read a small rise at Bendung Katulampa as an upstream flood surge. Fixed on 25 Nov.",
  },
  "2026-11-25": {
    id: "Bahaya sampai sekitar pukul 09.35 WIB adalah kesalahan sistem yang sama dengan 24 Nov, sudah diperbaiki. Setelah itu statusnya Waspada.",
    en: "Danger until about 09:35 WIB was the same system error as on 24 Nov, now fixed. After that the status was Watch.",
  },
};

const wibKey = (ts) => new Date(ts).toLocaleDateString("sv-SE", { timeZone: "Asia/Jakarta" });
const keyDate = (key) => new Date(`${key}T12:00:00+07:00`);
const fmt = (key, isId, opts) => keyDate(key).toLocaleDateString(isId ? "id-ID" : "en-GB", { timeZone: "Asia/Jakarta", ...opts });
const mm = (v) => (v == null ? "–" : `${Math.round(v)} mm`);
const shortPost = (name) => (name || "").replace(/^(P\.A\.|P\.S\.|Pompa|Rumah Pompa|Bendung\.?)\s*/i, "").replace(/\s+\d+$/, "");

function lastDays(n) {
  const out = [];
  const now = Date.now();
  for (let i = n - 1; i >= 0; i -= 1) out.push(wibKey(now - i * 86400000));
  return out;
}

/** One WIB day from its decision rows: highest level, chance, time above Safe. */
function summariseDay(rows) {
  if (!rows.length) return null;
  let top = "SAFE";
  rows.forEach((r) => { if ((RANK[r.level] ?? 0) > RANK[top]) top = r.level; });
  const atTop = rows.filter((r) => r.level === top);
  const chances = rows.map((r) => r.chance).filter((c) => c != null);
  const peak = chances.length ? Math.max(...chances) : null;
  const ruled = top !== "SAFE" && !atTop.some((r) => r.chance != null && r.chance >= (LEVEL_FROM[top] ?? 0));
  const above = rows.filter((r) => r.level !== "SAFE" && r.level !== "UNKNOWN");
  return {
    top, peak, ruled, rows,
    aboveHours: above.length * 0.25,
    from: above[0]?.t ?? null,
    to: above[above.length - 1]?.t ?? null,
  };
}

function hoursText(h, isId) {
  const v = Math.max(0.25, h);
  const txt = v < 1 ? v.toFixed(2).replace(/0$/, "") : String(Math.round(v));
  return isId ? txt.replace(".", ",") : txt;
}

function Details({ title, children }) {
  return (
    <details className="hist-details">
      <summary>{title}</summary>
      <div className="hist-details-body">{children}</div>
    </details>
  );
}

export default function History() {
  const { lang } = useApp();
  const isId = lang === "id";
  const names = NAMES[isId ? "id" : "en"];
  const [days, setDays] = useState(14);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [picked, setPicked] = useState(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setError(false);
    fetch(`${API_BASE}/history/summary?days=${days}`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => { setData(d); setPicked(null); })
      .catch((e) => { if (e.name !== "AbortError") setError(true); });
    return () => ctrl.abort();
  }, [days]);

  const decisions = data?.decisions ?? [];
  const keys = useMemo(() => lastDays(days), [days]);
  const byDay = useMemo(() => {
    const groups = {};
    decisions.forEach((d) => { (groups[wibKey(d.t)] ??= []).push(d); });
    return Object.fromEntries(keys.map((k) => [k, summariseDay(groups[k] ?? [])]));
  }, [decisions, keys]);
  const rainBy = useMemo(() => {
    const m = Object.fromEntries((data?.rain?.days ?? []).map((d) => [d.date, d]));
    const t = data?.rain?.today;
    if (t) m[wibKey(Date.now())] = { jakarta_mean: t.jakarta_mean, jakarta_max: t.jakarta_max, bogor: t.bogor, partial: t.through };
    return m;
  }, [data]);

  const share = useMemo(() => {
    const n = Math.max(1, decisions.length);
    return LEVELS.map((l) => ({ level: l, share: decisions.filter((d) => d.level === l).length / n }));
  }, [decisions]);
  const dayCounts = useMemo(() => {
    const c = Object.fromEntries(LEVELS.map((l) => [l, 0]));
    keys.forEach((k) => { if (byDay[k]) c[byDay[k].top] += 1; });
    return c;
  }, [byDay, keys]);
  const worst = useMemo(() => {
    const logged = keys.filter((k) => byDay[k]);
    return logged.reduce((best, k) => (!best || RANK[byDay[k].top] >= RANK[byDay[best].top] ? k : best), null);
  }, [byDay, keys]);

  const selected = picked ?? (worst && byDay[worst].top !== "SAFE" ? worst : keys[keys.length - 1]);
  const sel = byDay[selected];
  const selRain = rainBy[selected];

  const logged = keys.filter((k) => byDay[k]).length;
  const hot = dayCounts.WARNING + dayCounts.DANGER;
  const summary = !logged
    ? (isId ? "Belum ada data untuk rentang ini." : "No data for this range yet.")
    : isId
      ? `Dalam ${days} hari terakhir, ${dayCounts.SAFE} dari ${logged} hari tercatat Aman sepanjang hari.${hot ? ` Status Siaga atau Bahaya muncul di ${hot} hari.` : " Status tidak pernah mencapai Siaga."}`
      : `Over the last ${days} days, ${dayCounts.SAFE} of ${logged} days stayed Safe all day.${hot ? ` Alert or Danger showed on ${hot} days.` : " The status never reached Alert."}`;

  const rainDays = data?.rain?.days ?? [];
  const postRows = useMemo(() => {
    const all = Object.entries(data?.posts_daily ?? {}).map(([name, d]) => ({ name, d, top: Math.max(0, ...Object.values(d)) }));
    return {
      moved: all.filter((p) => p.top > 0).sort((a, b) => b.top - a.top || a.name.localeCompare(b.name)),
      calm: all.filter((p) => p.top === 0).length,
    };
  }, [data]);
  const postDays = useMemo(() => [...new Set(Object.values(data?.posts_daily ?? {}).flatMap((d) => Object.keys(d)))].sort(), [data]);

  const longPoints = useMemo(() => decisions.map((d) => ({ t: Date.parse(d.t), y: d.chance, level: d.level })), [decisions]);
  const selPoints = useMemo(() => (sel?.rows ?? []).map((d) => ({ t: Date.parse(d.t), y: d.chance, level: d.level })), [sel]);
  const thresholds = [
    { y: 0.8, label: `${names.DANGER} 80%`, color: "var(--s1)" },
    { y: 0.65, label: `${names.WARNING} 65%`, color: "var(--s2)" },
    { y: 0.2, label: `${names.PRE_ALERT} 20%`, color: "var(--wsp)" },
  ];

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{isId ? "Riwayat" : "History"}</h1>
          <p className="page-sub">
            {isId
              ? "Status yang ditampilkan situs ini tiap hari, dan hujan yang turun. Ketuk satu hari untuk melihat rinciannya."
              : "The status this site showed each day, and the rain that fell. Tap a day for its detail."}
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
        <p className="hist-note" role="alert">
          {isId ? "Riwayat belum bisa dimuat. Coba lagi sebentar lagi." : "The history could not be loaded. Try again shortly."}
        </p>
      )}
      {!data && !error && <LoadingSpinner message={isId ? "Memuat riwayat..." : "Loading history..."} />}

      {data && (
        <div className="hist fade-in">
          {/* 1 — one sentence and the share of time at each level */}
          <section className="hist-summary" aria-label={isId ? "Ringkasan" : "Summary"}>
            <p className="hist-lead">{summary}</p>
            <div className="hist-share" role="img"
                 aria-label={share.map((s) => `${names[s.level]} ${Math.round(s.share * 100)}%`).join(", ")}>
              {share.map((s) => (s.share > 0 ? <i key={s.level} style={{ flex: s.share, background: LEVEL_COLOR[s.level] }} /> : null))}
            </div>
            <ul className="hist-share-legend">
              {share.map((s) => (
                <li key={s.level}><i style={{ background: LEVEL_COLOR[s.level] }} />{names[s.level]} <b>{Math.round(s.share * 100)}%</b></li>
              ))}
              <li className="hist-share-note">{isId ? "dari seluruh waktu yang tercatat" : "of all recorded time"}</li>
            </ul>
          </section>

          {/* 2 — the calendar */}
          <section aria-label={isId ? "Kalender status" : "Status calendar"}>
            <div className="hist-cal">
              {keys.map((k) => {
                const d = byDay[k];
                const rain = rainBy[k];
                const level = d?.top ?? null;
                return (
                  <button key={k} type="button" className={`hist-day${k === selected ? " is-selected" : ""}${d ? "" : " is-empty"}`}
                          style={level ? { "--c": LEVEL_COLOR[level] } : undefined} aria-pressed={k === selected}
                          aria-label={`${fmt(k, isId, { weekday: "long", day: "numeric", month: "long" })}: ${level ? names[level] : (isId ? "tidak ada data" : "no data")}${rain ? `, ${isId ? "hujan" : "rain"} ${mm(rain.jakarta_mean)}` : ""}`}
                          onClick={() => setPicked(k)}>
                    <span className="hist-day-wd">{fmt(k, isId, { weekday: "short" })}</span>
                    <span className="hist-day-n">{fmt(k, isId, { day: "numeric" })}</span>
                    <span className="hist-day-level">{level ? names[level] : "–"}</span>
                    <span className="hist-day-rain">{rain ? mm(rain.jakarta_mean) : "–"}</span>
                  </button>
                );
              })}
            </div>
            <p className="hist-legend-note">
              {isId ? "Warna: status tertinggi hari itu. Angka bawah: rata-rata hujan satelit di Jakarta." : "Colour: the highest status that day. Bottom number: average satellite rain over Jakarta."}
            </p>
          </section>

          {/* 3 — the picked day */}
          <section className="hist-detail" aria-live="polite">
            <h2>{fmt(selected, isId, { weekday: "long", day: "numeric", month: "long" })}</h2>
            {sel ? (
              <>
                <p>
                  {isId ? "Status tertinggi: " : "Highest status: "}<b style={{ color: LEVEL_COLOR[sel.top] }}>{names[sel.top]}</b>
                  {sel.top === "SAFE"
                    ? (isId ? ". Sepanjang hari tercatat Aman." : ". Safe all day.")
                    : isId
                      ? `. Di atas Aman selama sekitar ${hoursText(sel.aboveHours, true)} jam (${formatWibAt(sel.from, true, { date: false })}–${formatWibAt(sel.to, true, { date: false })} WIB).`
                      : `. Above Safe for about ${hoursText(sel.aboveHours, false)} h (${formatWibAt(sel.from, false, { date: false })}–${formatWibAt(sel.to, false, { date: false })} WIB).`}
                </p>
                {sel.top !== "SAFE" && (
                  <p className="hist-muted">
                    {sel.ruled
                      ? (isId ? "Statusnya dinaikkan aturan keselamatan (pos di Siaga 1, air di pos yang sudah tinggi naik cepat, atau peringatan BMKG), bukan oleh peluang model."
                              : "The status was raised by a safety rule (a post at Siaga 1, a high post rising fast, or a BMKG warning), not by the model's chance.")
                      : (isId ? `Peluang ada genangan di salah satu kecamatan paling tinggi ${formatChance(sel.peak)}.`
                              : `The chance of waterlogging in at least one kecamatan peaked at ${formatChance(sel.peak)}.`)}
                  </p>
                )}
                {KNOWN_ISSUES[selected] && (
                  <p className="hist-issue" role="note">{KNOWN_ISSUES[selected][isId ? "id" : "en"]}</p>
                )}
                {selRain && (
                  <p className="hist-muted">
                    {isId
                      ? `Hujan satelit${selRain.partial ? ` sampai ${selRain.partial} WIB` : ""}: Jakarta rata-rata ${mm(selRain.jakarta_mean)}, tertinggi ${mm(selRain.jakarta_max)}; Bogor ${mm(selRain.bogor)}.`
                      : `Satellite rain${selRain.partial ? ` up to ${selRain.partial} WIB` : ""}: Jakarta ${mm(selRain.jakarta_mean)} on average, wettest ${mm(selRain.jakarta_max)}; Bogor ${mm(selRain.bogor)}.`}
                  </p>
                )}
                {selPoints.length > 1 && sel.peak != null && (
                  <TimeLine points={selPoints} yMax={1} levelStrip height={110} thresholds={thresholds}
                            xLabels={[selPoints[0].t, (selPoints[0].t + selPoints[selPoints.length - 1].t) / 2, selPoints[selPoints.length - 1].t].map((t) => formatWibAt(t, isId, { date: false }))}
                            ariaLabel={isId ? "Peluang banjir sepanjang hari" : "Flood chance through the day"} />
                )}
              </>
            ) : (
              <p className="hist-muted">{isId ? "Tidak ada data untuk hari ini." : "No data for this day."}</p>
            )}
          </section>

          {data.replayed_until && (
            <p className="hist-note">
              {isId
                ? `Sampai ${formatWibAt(data.replayed_until, true)} WIB, status dihitung ulang dari data tersimpan dengan model yang sekarang; setelah itu tercatat langsung saat itu juga.`
                : `Up to ${formatWibAt(data.replayed_until, false)} WIB the status was recomputed from stored data with the current models; after that it was logged live.`}
            </p>
          )}

          <Details title={isId ? "Lebih rinci: grafik seluruh periode" : "More detail: chart of the whole period"}>
            {longPoints.length > 1 ? (
              <TimeLine points={longPoints} yMax={1} levelStrip height={170} thresholds={thresholds}
                        xLabels={[0, 0.25, 0.5, 0.75, 1].map((f) => formatWibAt(longPoints[0].t + f * (longPoints[longPoints.length - 1].t - longPoints[0].t), isId, { time: false }))}
                        ariaLabel={isId ? "Peluang banjir Jakarta" : "Jakarta flood chance"} />
            ) : <p className="hist-muted">{isId ? "Belum cukup data." : "Not enough data yet."}</p>}
            <p className="hist-muted">
              {isId ? "Garis: peluang ada genangan di salah satu kecamatan, dihitung model keputusan tiap 15 menit. Pita bawah: status yang tampil."
                    : "Line: the chance of waterlogging in at least one kecamatan, from the decision model every 15 minutes. Band below: the status shown."}
            </p>
          </Details>

          <Details title={isId ? "Lebih rinci: pos pantau air per hari" : "More detail: water-level posts by day"}>
            {postRows.moved.length ? (
              <div className="post-grid-wrap">
                <table className="post-grid">
                  <thead>
                    <tr>
                      <th scope="col">{isId ? "Pos" : "Post"}</th>
                      {postDays.map((d) => <th key={d} scope="col">{fmt(d, isId, { day: "numeric" })}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {postRows.moved.map((p) => (
                      <tr key={p.name}>
                        <th scope="row">{shortPost(p.name)}</th>
                        {postDays.map((d) => {
                          const band = p.d[d];
                          return <td key={d} title={`${shortPost(p.name)} · ${fmt(d, isId, { day: "numeric", month: "short" })} · ${band == null ? "-" : BAND_NAME[band]}`}
                                     style={{ background: band == null ? "transparent" : BAND_COLOR[band] }} />;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="hist-muted">{isId ? "Semua pos tetap Normal." : "Every post stayed Normal."}</p>}
            {postRows.calm > 0 && (
              <p className="hist-muted">
                {isId ? `${postRows.calm} pos lain tetap Normal sepanjang periode ini, jadi tidak ditampilkan.` : `${postRows.calm} other posts stayed Normal for the whole period, so they are not listed.`}
              </p>
            )}
            <ul className="history-share">
              {BAND_NAME.map((b, i) => <li key={b}><i style={{ background: BAND_COLOR[i] }} /><span>{b}</span></li>)}
            </ul>
            <p className="hist-muted">
              {isId ? "Status resmi DSDA tiap pos. Ketuk pos di peta Beranda untuk grafik tinggi airnya." : "Each post's official DSDA status. Tap a post on the home map for its water-level chart."}
            </p>
          </Details>

          {rainDays.length > 0 && (
            <Details title={isId ? "Lebih rinci: hujan satelit per hari" : "More detail: satellite rain by day"}>
              <div className="hist-rain">
                {rainDays.slice(-days).map((d) => (
                  <div key={d.date} className="hist-rain-row">
                    <span>{fmt(d.date, isId, { day: "numeric", month: "short" })}</span>
                    <i style={{ width: `${Math.min(100, ((d.jakarta_mean ?? 0) / 60) * 100)}%` }} />
                    <b>{mm(d.jakarta_mean)}</b>
                    <small>{isId ? `tertinggi ${mm(d.jakarta_max)}, Bogor ${mm(d.bogor)}` : `wettest ${mm(d.jakarta_max)}, Bogor ${mm(d.bogor)}`}</small>
                  </div>
                ))}
              </div>
              <p className="hist-muted">
                {isId ? "NASA GPM IMERG Early, hari WIB yang sudah lengkap; datanya tiba sekitar 5 jam setelah hujan. Batang penuh = 60 mm."
                      : "NASA GPM IMERG Early, complete WIB days; the data arrives about 5 hours after the rain. A full bar = 60 mm."}
              </p>
            </Details>
          )}

          {TELEGRAM_URL && (
            <aside className="hist-telegram">
              <div>
                <h2>{isId ? "Dapatkan peringatan di Telegram" : "Get alerts on Telegram"}</h2>
                <p>
                  {isId ? "Pesan dikirim saat status Jakarta naik ke Siaga atau Bahaya, dan saat turun lagi. Tanpa akun di situs ini dan tanpa nomor telepon."
                        : "A message goes out when Jakarta's status rises to Alert or Danger, and when it falls again. No account here and no phone number needed."}
                </p>
              </div>
              <a className="btn btn-ghost" href={TELEGRAM_URL} target="_blank" rel="noopener noreferrer">
                {isId ? "Buka kanal Telegram" : "Open the Telegram channel"}
              </a>
            </aside>
          )}
        </div>
      )}
    </>
  );
}
