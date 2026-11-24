/* ── Cek daerahku — one kelurahan or kecamatan at a glance ─────────────────
   Today's chance from the daily kecamatan model, the days BPBD recorded a
   flood there in 2013–2025 (src/data/areaProfiles.json, from
   scripts/build_area_profiles.py), the nearest water-level posts and the
   nearest shelter candidates (/shelters/nearby). The choice is remembered on
   this device only.
*/
import { useEffect, useMemo, useState } from "react";
import { useApp } from "../../lib/appContext";
import { API_BASE } from "../../lib/api";
import { distanceKm, formatChance, modelLevelKey } from "../../lib/dashboardHelpers";
import profiles from "../../data/areaProfiles.json";
import { RiskBadge } from "./primitives";

const STORE_KEY = "deflood.area";

function buildOptions() {
  const out = [];
  for (const k of profiles.kecamatan) {
    out.push({ label: `Kecamatan ${k.name}, ${k.kota}`, kec: k, kel: null });
    for (const kel of k.kelurahan) out.push({ label: `${kel.name} (Kec. ${k.name})`, kec: k, kel });
  }
  return out;
}

function readStored() {
  try { return window.localStorage.getItem(STORE_KEY) || ""; } catch { return ""; }
}
function writeStored(v) {
  try { if (v) window.localStorage.setItem(STORE_KEY, v); else window.localStorage.removeItem(STORE_KEY); } catch { /* private mode */ }
}

const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, "");

export default function AreaCheck({ riskData }) {
  const { lang } = useApp();
  const isId = lang === "id";
  const options = useMemo(buildOptions, []);
  const [text, setText] = useState(readStored);
  const [chosen, setChosen] = useState(() => options.find((o) => o.label === readStored()) ?? null);
  const [shelters, setShelters] = useState(null);

  const pick = (value) => {
    setText(value);
    const exact = options.find((o) => o.label === value);
    if (exact) { setChosen(exact); writeStored(exact.label); }
  };
  const submit = (e) => {
    e.preventDefault();
    const q = norm(text);
    if (!q) return;
    // Two kecamatan can list a kelurahan of the same name: take the one with more flood days.
    const byName = options.filter((o) => norm(o.kel?.name ?? "") === q).sort((a, b) => b.kel.flood_days - a.kel.flood_days);
    const hit = options.find((o) => o.label === text)
      ?? byName[0]
      ?? options.find((o) => !o.kel && norm(o.kec.name) === q)
      ?? options.find((o) => norm(o.label).includes(q));
    if (hit) { setChosen(hit); setText(hit.label); writeStored(hit.label); }
    else setChosen(null);
  };

  // "Pakai lokasi saya": the nearest area with a known centre (kelurahan where we have one, else kecamatan).
  const [locating, setLocating] = useState(false);
  const useMyLocation = () => {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition((pos) => {
      const { latitude: la, longitude: lo } = pos.coords;
      const near = options
        .map((o) => ({ o, la: o.kel ? o.kel.lat : o.kec.lat, lo: o.kel ? o.kel.lon : o.kec.lon }))
        .filter((x) => x.la != null)
        .map((x) => ({ ...x, d: distanceKm(la, lo, x.la, x.lo) }))
        .sort((a, b) => a.d - b.d)[0];
      setLocating(false);
      if (near && near.d < 15) { setChosen(near.o); setText(near.o.label); writeStored(near.o.label); }
    }, () => setLocating(false), { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 });
  };

  const lat = chosen?.kel?.lat ?? chosen?.kec.lat;
  const lon = chosen?.kel?.lon ?? chosen?.kec.lon;

  useEffect(() => {
    if (lat == null) return undefined;
    const ctrl = new AbortController();
    setShelters(null);
    fetch(`${API_BASE}/shelters/nearby?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}&limit=5`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => setShelters((d.shelters ?? []).slice(0, 3)))
      .catch((e) => { if (e.name !== "AbortError") setShelters([]); });
    return () => ctrl.abort();
  }, [lat, lon]);

  const posts = useMemo(() => {
    if (lat == null) return [];
    return (riskData?.stations ?? [])
      .filter((s) => s.lat != null && s.lon != null)
      .map((s) => ({ ...s, km: distanceKm(lat, lon, s.lat, s.lon) }))
      .sort((a, b) => a.km - b.km)
      .slice(0, 3);
  }, [riskData?.stations, lat, lon]);

  const today = chosen ? riskData?.dailyModel?.kecamatan?.[chosen.kec.slug] : null;
  const km = (v) => {
    const txt = v < 0.1 ? "< 0.1" : v < 10 ? v.toFixed(1) : String(Math.round(v));
    return `${isId ? txt.replace(".", ",") : txt} km`;
  };

  return (
    <section className="panel panel-body fade-in" aria-labelledby="area-check-title">
      <p id="area-check-title" className="station-title">{isId ? "Cek daerahku" : "Check my area"}</p>
      <p className="station-sub" style={{ marginBottom: 0 }}>
        {isId
          ? "Ketik nama kelurahan atau kecamatan di Jakarta. Pilihan disimpan di perangkat ini saja."
          : "Type a kelurahan or kecamatan in Jakarta. Your choice is kept on this device only."}
      </p>
      <form className="area-check-form" onSubmit={submit} role="search">
        <input list="area-check-options" value={text} onChange={(e) => pick(e.target.value)}
               placeholder={isId ? "mis. Kampung Melayu" : "e.g. Kampung Melayu"}
               aria-label={isId ? "Nama kelurahan atau kecamatan" : "Kelurahan or kecamatan name"} />
        <datalist id="area-check-options">
          {options.map((o) => <option key={o.label} value={o.label} />)}
        </datalist>
        <button type="submit" className="btn btn-ghost">{isId ? "Cek" : "Check"}</button>
      </form>
      {"geolocation" in navigator && (
        <button type="button" className="area-check-locate" onClick={useMyLocation} disabled={locating}>
          {locating ? (isId ? "Mencari lokasi..." : "Finding you...") : (isId ? "Pakai lokasi saya" : "Use my location")}
        </button>
      )}

      {!chosen && text && (
        <p className="station-sub" style={{ margin: 0 }}>
          {isId ? "Belum ketemu. Pilih dari daftar yang muncul saat mengetik." : "Not found. Pick from the list that appears as you type."}
        </p>
      )}

      {chosen && (
        <div className="area-check-grid">
          <div className="area-check-cell">
            <h4>{isId ? "Peluang banjir hari ini" : "Flood chance today"}</h4>
            {today ? (
              <>
                <p className="area-check-big">{formatChance(today.probability)}</p>
                <p style={{ display: "flex", gap: "0.4rem", alignItems: "center", flexWrap: "wrap" }}>
                  <RiskBadge level={modelLevelKey(today.risk_level)} />
                  <span>{isId ? `Kecamatan ${chosen.kec.name}, model harian` : `${chosen.kec.name} kecamatan, daily model`}</span>
                </p>
              </>
            ) : (
              <p>{isId ? "Model harian belum tersedia saat ini." : "The daily model is not available right now."}</p>
            )}
          </div>
          <div className="area-check-cell">
            <h4>{isId ? "Riwayat banjir 2013–2025" : "Flood history 2013–2025"}</h4>
            <p className="area-check-big">{chosen.kel ? chosen.kel.flood_days : chosen.kec.flood_days} {isId ? "hari" : "days"}</p>
            <p>
              {chosen.kel
                ? (isId
                  ? `di Kelurahan ${chosen.kel.name}. Seluruh Kecamatan ${chosen.kec.name}: ${chosen.kec.flood_days} hari, terbanyak ke-${chosen.kec.rank} dari ${profiles.count} kecamatan.`
                  : `in ${chosen.kel.name}. All of ${chosen.kec.name}: ${chosen.kec.flood_days} days, ${chosen.kec.rank} of ${profiles.count} kecamatan by flood days.`)
                : (isId
                  ? `Terbanyak ke-${chosen.kec.rank} dari ${profiles.count} kecamatan.`
                  : `${chosen.kec.rank} of ${profiles.count} kecamatan by flood days.`)}
            </p>
          </div>
          <div className="area-check-cell">
            <h4>{isId ? "Pos pantau air terdekat" : "Nearest water-level posts"}</h4>
            {posts.length ? (
              <ul>
                {posts.map((p) => (
                  <li key={p.nama}>
                    <b>{p.nama}</b>
                    <span>{isId ? `${km(p.km)} dari sini, ${(p.status_siaga || "").replace(/^Status\s*:\s*/i, "")}` : `${km(p.km)} away, ${(p.status_siaga || "").replace(/^Status\s*:\s*/i, "")}`}</span>
                  </li>
                ))}
              </ul>
            ) : <p>{isId ? "Data pos belum tersedia." : "No post data yet."}</p>}
          </div>
          <div className="area-check-cell">
            <h4>{isId ? "Tempat aman terdekat" : "Nearest safe places"}</h4>
            {shelters == null ? <p>{isId ? "Memuat..." : "Loading..."}</p>
              : shelters.length ? (
                <ul>
                  {shelters.map((s) => (
                    <li key={s.id ?? s.name}>
                      <b>{s.name}</b>
                      <span>{isId ? `${km(s.distance_km ?? distanceKm(lat, lon, s.lat, s.lon))} dari sini` : `${km(s.distance_km ?? distanceKm(lat, lon, s.lat, s.lon))} away`}</span>
                    </li>
                  ))}
                </ul>
              ) : <p>{isId ? "Tidak bisa dimuat saat ini." : "Could not be loaded right now."}</p>}
            <p>{isId ? "Kandidat dari survei OSM/InAWARE, bukan daftar resmi. Rute ada di halaman Evakuasi." : "Candidates from the OSM/InAWARE survey, not an official list. Routes are on the Evacuation page."}</p>
          </div>
        </div>
      )}
      {chosen && (
        <p className="area-check-foot">
          {isId
            ? "Riwayat: hari dengan banjir yang dicatat BPBD DKI; catatan 2023–2025 belum lengkap. Peluang hari ini berlaku untuk seluruh kecamatan."
            : "History: days with a flood recorded by BPBD DKI; 2023–2025 records are incomplete. Today's chance is for the whole kecamatan."}
        </p>
      )}
    </section>
  );
}
