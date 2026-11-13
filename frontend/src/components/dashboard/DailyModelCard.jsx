/* ── Daily kecamatan model — today's flood chance per kecamatan ────────────
   Backend `daily_model` (realtime_native/daily_model.py): a calibrated chance
   that BPBD records a flood in each kecamatan today, from satellite rain up to
   `rain_through` and yesterday's river posts. Hidden when the model is off.
*/
import { useApp } from "../../lib/appContext";
import { dailyTopKecamatan, formatChance } from "../../lib/dashboardHelpers";

const LEVEL_COLOR = { aman: "var(--safe)", waspada: "var(--wsp)", siaga: "var(--s2)", bahaya: "var(--s1)" };

function shortDate(iso, isId) {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00+07:00`);
  return d.toLocaleDateString(isId ? "id-ID" : "en-GB", { day: "numeric", month: "short", timeZone: "Asia/Jakarta" });
}

export default function DailyModelCard({ dailyModel }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const top = dailyTopKecamatan(dailyModel, 5);
  if (!top.length) return null;
  const highest = top[0].probability || 1;
  const rainDate = shortDate(dailyModel.rain_through, isId);

  return (
    <div className="panel panel-body ai-card daily-card fade-in">
      <div className="ai-card-head">
        <span className="ai-card-label">{isId ? "Peluang banjir hari ini" : "Flood chance today"}</span>
        <span className="ai-card-time">{isId ? `hujan s.d. ${rainDate}` : `rain to ${rainDate}`}</span>
      </div>
      <ol className="daily-list">
        {top.map((k) => (
          <li key={k.slug} className="daily-row">
            <span className="daily-name">{k.name}</span>
            <span className="daily-bar" aria-hidden="true">
              <span style={{ width: `${Math.max(4, (k.probability / highest) * 100)}%`, background: LEVEL_COLOR[k.level] }} />
            </span>
            <span className="daily-pct">{formatChance(k.probability)}</span>
          </li>
        ))}
      </ol>
      <p className="daily-note">
        {isId
          ? `Kemungkinan BPBD mencatat banjir di kecamatan itu hari ini, dihitung dari hujan satelit sampai ${rainDate}, status pos sungai kemarin, riwayat banjir, dan musim.`
          : `The chance that BPBD records a flood in that kecamatan today, from satellite rain up to ${rainDate}, yesterday's river posts, past floods and the season.`}
      </p>
    </div>
  );
}
