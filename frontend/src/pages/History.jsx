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
    id: "Sebagian besar Bahaya hari ini adalah galat sistem (kenaikan kecil di Katulampa terbaca sebagai banjir kiriman). Sudah diperbaiki 25 Nov.",
    en: "Most of this Danger was a system error (a small rise at Katulampa read as an upstream surge). Fixed 25 Nov.",
  },
  "2026-11-25": {
    id: "Bahaya sampai 09.35 WIB adalah galat yang sama, sudah diperbaiki. Setelah itu Waspada.",
    en: "Danger until 09:35 WIB was the same error, now fixed. Watch after that.",
  },
};

const wibKey = (ts) => new Date(ts).toLocaleDateString("sv-SE", { timeZone: "Asia/Jakarta" });
const keyDate = (key) => new Date(`${key}T12:00:00+07:00`);
const fmt = (key, isId, opts) => keyDate(key).toLocaleDateString(isId ? "id-ID" : "en-GB", { timeZone: "Asia/Jakarta", ...opts });
const mm = (v) => (v == null ? "–" : `${Math.round(v)} mm`);
const shortPost = (name) => (name || "").replace(/^(P\.A\.|P\.S\.|Pompa|Rumah Pompa|Bendung\.?)\s*/i, "").replace(/\s+\d+$/, "");

const WEEKDAYS = { id: ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"], en: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] };
/** Monday-first column of a WIB day (0 = Monday). */
const weekdayCol = (key) => (keyDate(key).getUTCDay() + 6) % 7;

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
      ? `${dayCounts.SAFE} dari ${logged} hari Aman sepanjang hari.${hot ? ` Siaga atau Bahaya: ${hot} hari.` : ""}`
      : `${dayCounts.SAFE} of ${logged} days stayed Safe all day.${hot ? ` Alert or Danger: ${hot} days.` : ""}`;

  const rainDays = data?.rain?.days ?? [];
  const postRows = useMemo(() => {
    const all = Object.entries(data?.posts_daily ?? {}).map(([name, d]) => ({ name, d, top: Math.max(0, ...Object.values(d)) }));
    return {
      moved: all.filter((p) => p.top > 0).sort((a, b) => b.top - a.top || a.name.localeCompare(b.name)),
      calm: all.filter((p) => p.top === 0).length,
    };
  }, [data]);
  const dupShort = useMemo(() => {
    const seen = new Set();
    const dup = new Set();
    postRows.moved.forEach((p) => { const k = shortPost(p.name); (seen.has(k) ? dup : seen).add(k); });
    return dup;
  }, [postRows]);
  const postLabel = (name) => (dupShort.has(shortPost(name)) ? name : shortPost(name));
  const postDays = useMemo(() => [...new Set(Object.values(data?.posts_daily ?? {}).flatMap((d) => Object.keys(d)))].sort(), [data]);

  const longPoints = useMemo(() => decisions.map((d) => ({ t: Date.parse(d.t), y: d.chance, level: d.level })), [decisions]);
  const selPoints = useMemo(() => (sel?.rows ?? []).map((d) => ({ t: Date.parse(d.t), y: d.chance, level: d.level })), [sel]);
  const thresholds = [
    { y: 0.8, label: `${names.DANGER} 80%`, color: "var(--s1)" },
    { y: 0.65, label: `${names.WARNING} 65%`, color: "var(--s2)" },
    { y: 0.2, label: `${names.PRE_ALERT} 20%`, color: "var(--wsp)" },
  ];

  const lead = weekdayCol(keys[0]);
  const wdNames = WEEKDAYS[isId ? "id" : "en"];

  return (
    <>
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{isId ? "Riwayat" : "History"}</h1>
          <p className="page-sub">{isId ? "Status tiap hari. Ketuk satu hari untuk rinciannya." : "The status each day. Tap a day for detail."}</p>
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
            </ul>
          </section>

          <div className="hist-body">
            <section className="hist-calwrap" aria-label={isId ? "Kalender status" : "Status calendar"}>
              <div className="hist-cal-head" aria-hidden="true">{wdNames.map((w) => <span key={w}>{w}</span>)}</div>
              <div className="hist-cal">
                {Array.from({ length: lead }, (_, i) => <span key={`pad${i}`} className="hist-pad" aria-hidden="true" />)}
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
                      <span className="hist-day-level"><span className="hist-lv-full">{level ? names[level] : "–"}</span><span className="hist-lv-init" aria-hidden="true">{level ? names[level][0] : "–"}</span></span>
                      <span className="hist-day-rain">{rain ? mm(rain.jakarta_mean) : "–"}</span>
                    </button>
                  );
                })}
              </div>
              <p className="hist-legend-note">{isId ? "Warna = status tertinggi. Angka = hujan Jakarta." : "Colour = highest status. Number = Jakarta rain."}</p>
            </section>

            <section className="hist-detail" aria-live="polite">
              <h2>{fmt(selected, isId, { weekday: "long", day: "numeric", month: "long" })}</h2>
              {sel ? (
                <>
                  <p className="hist-detail-main">
                    <b style={{ color: LEVEL_COLOR[sel.top] }}>{names[sel.top]}</b>
                    {sel.top === "SAFE"
                      ? (isId ? " sepanjang hari." : " all day.")
                      : isId
                        ? ` · di atas Aman ${hoursText(sel.aboveHours, true)} jam (${formatWibAt(sel.from, true, { date: false })}–${formatWibAt(sel.to, true, { date: false })} WIB)`
                        : ` · above Safe ${hoursText(sel.aboveHours, false)} h (${formatWibAt(sel.from, false, { date: false })}–${formatWibAt(sel.to, false, { date: false })} WIB)`}
                  </p>
                  {sel.top !== "SAFE" && (
                    <p className="hist-muted">
                      {sel.ruled
                        ? (isId ? "Dinaikkan aturan keselamatan, bukan peluang model." : "Raised by a safety rule, not the model's chance.")
                        : (isId ? `Peluang genangan tertinggi ${formatChance(sel.peak)}.` : `Peak waterlogging chance ${formatChance(sel.peak)}.`)}
                    </p>
                  )}
                  {KNOWN_ISSUES[selected] && (
                    <p className="hist-issue" role="note">{KNOWN_ISSUES[selected][isId ? "id" : "en"]}</p>
                  )}
                  {selPoints.length > 1 && sel.peak != null && (
                    <TimeLine points={selPoints} yMax={1} levelStrip height={120} thresholds={thresholds}
                              xLabels={[selPoints[0].t, (selPoints[0].t + selPoints[selPoints.length - 1].t) / 2, selPoints[selPoints.length - 1].t].map((t) => formatWibAt(t, isId, { date: false }))}
                              ariaLabel={isId ? "Peluang banjir sepanjang hari" : "Flood chance through the day"} />
                  )}
                  {selRain && (
                    <p className="hist-muted">
                      {isId
                        ? `Hujan${selRain.partial ? ` s/d ${selRain.partial}` : ""}: Jakarta ${mm(selRain.jakarta_mean)}, Bogor ${mm(selRain.bogor)}`
                        : `Rain${selRain.partial ? ` to ${selRain.partial}` : ""}: Jakarta ${mm(selRain.jakarta_mean)}, Bogor ${mm(selRain.bogor)}`}
                    </p>
                  )}
                </>
              ) : (
                <p className="hist-muted">{isId ? "Tidak ada data untuk hari ini." : "No data for this day."}</p>
              )}
            </section>
          </div>

          <div className="hist-more">
            <Details title={isId ? "Grafik seluruh periode" : "Chart of the whole period"}>
              {longPoints.length > 1 ? (
                <TimeLine points={longPoints} yMax={1} levelStrip height={170} thresholds={thresholds}
                          xLabels={[0, 0.25, 0.5, 0.75, 1].map((f) => formatWibAt(longPoints[0].t + f * (longPoints[longPoints.length - 1].t - longPoints[0].t), isId, { time: false }))}
                          ariaLabel={isId ? "Peluang banjir Jakarta" : "Jakarta flood chance"} />
              ) : <p className="hist-muted">{isId ? "Belum cukup data." : "Not enough data yet."}</p>}
              <p className="hist-muted">{isId ? "Garis = peluang genangan di salah satu kecamatan. Pita bawah = status yang tampil." : "Line = chance of waterlogging in a kecamatan. Band = status shown."}</p>
            </Details>

            <Details title={isId ? "Pos pantau air" : "Water-level posts"}>
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
                          <th scope="row">{postLabel(p.name)}</th>
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
              <ul className="history-share">
                {BAND_NAME.map((b, i) => <li key={b}><i style={{ background: BAND_COLOR[i] }} /><span>{b}</span></li>)}
              </ul>
              {postRows.calm > 0 && (
                <p className="hist-muted">{isId ? `${postRows.calm} pos lain tetap Normal, tidak ditampilkan.` : `${postRows.calm} other posts stayed Normal, not shown.`}</p>
              )}
            </Details>

            {rainDays.length > 0 && (
              <Details title={isId ? "Hujan per hari" : "Rain by day"}>
                <div className="hist-rain">
                  {rainDays.slice(-days).map((d) => (
                    <div key={d.date} className="hist-rain-row">
                      <span>{fmt(d.date, isId, { day: "numeric", month: "short" })}</span>
                      <i style={{ width: `${Math.min(100, ((d.jakarta_mean ?? 0) / 60) * 100)}%` }} />
                      <b>{mm(d.jakarta_mean)}</b>
                    </div>
                  ))}
                </div>
                <p className="hist-muted">{isId ? "Rata-rata Jakarta, satelit NASA IMERG. Batang penuh = 60 mm." : "Jakarta average, NASA IMERG satellite. Full bar = 60 mm."}</p>
              </Details>
            )}

            {data.replayed_until && (
              <Details title={isId ? "Cara data dicatat" : "How this is recorded"}>
                <p className="hist-muted">
                  {isId
                    ? `Sampai ${formatWibAt(data.replayed_until, true)} WIB, status dihitung ulang dari data tersimpan. Setelah itu dicatat langsung.`
                    : `Up to ${formatWibAt(data.replayed_until, false)} WIB the status was recomputed from stored data. After that it was logged live.`}
                </p>
              </Details>
            )}
          </div>

          {TELEGRAM_URL && (
            <aside className="hist-telegram">
              <div>
                <h2>{isId ? "Peringatan di Telegram" : "Alerts on Telegram"}</h2>
                <p>{isId ? "Pesan saat status naik ke Siaga atau Bahaya, dan saat turun lagi." : "A message when the status rises to Alert or Danger, and when it falls."}</p>
              </div>
              <a className="btn btn-ghost" href={TELEGRAM_URL} target="_blank" rel="noopener noreferrer">
                {isId ? "Buka Telegram" : "Open Telegram"}
              </a>
            </aside>
          )}
        </div>
      )}
    </>
  );
}
