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

  // "Pakai lokasi saya": the kecamatan whose centre is nearest, then its kelurahan if we know one within 1 km.
  // Kelurahan centres exist for only 94 of 253, so the kecamatan is chosen first (the nearest kelurahan
  // with a centre could belong to the next kecamatan over).
  const [locating, setLocating] = useState(false);
  const [geoNote, setGeoNote] = useState("");
  const locateMe = () => {
    setGeoNote("");
    if (!navigator.geolocation) {
      setGeoNote(isId ? "Browser ini tidak bisa membaca lokasi. Ketik nama daerah Anda di atas." : "This browser cannot read your location. Type your area above.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude: la, longitude: lo } = pos.coords;
        const kecs = options.filter((o) => !o.kel)
          .map((o) => ({ o, d: distanceKm(la, lo, o.kec.lat, o.kec.lon) }))
          .sort((a, b) => a.d - b.d);
        setLocating(false);
        if (!kecs.length || kecs[0].d > 15) {
          setGeoNote(isId ? "Lokasi Anda sepertinya di luar Jakarta. Ketik nama daerah di Jakarta yang ingin dicek." : "You seem to be outside Jakarta. Type the Jakarta area you want to check.");
          return;
        }
        const kecOption = kecs[0].o;
        const kel = options
          .filter((o) => o.kel && o.kec.slug === kecOption.kec.slug && o.kel.lat != null)
          .map((o) => ({ o, d: distanceKm(la, lo, o.kel.lat, o.kel.lon) }))
          .sort((a, b) => a.d - b.d)[0];
        const hit = kel && kel.d <= 1 ? kel.o : kecOption;
        setChosen(hit);
        setText(hit.label);
        writeStored(hit.label);
        setGeoNote(isId ? `Lokasi Anda terbaca dekat ${hit.kel ? hit.kel.name : `Kecamatan ${hit.kec.name}`}. Salah? Ketik nama daerah yang benar di atas.`
                        : `Your location is near ${hit.kel ? hit.kel.name : `${hit.kec.name} kecamatan`}. Wrong? Type the right area above.`);
      },
      (err) => {
        setLocating(false);
        setGeoNote(err.code === 1
          ? (isId ? "Izin lokasi ditolak. Aktifkan lokasi untuk situs ini di pengaturan browser, atau ketik nama daerah Anda." : "Location permission was denied. Allow location for this site in your browser settings, or type your area.")
          : err.code === 3
            ? (isId ? "Lokasi terlalu lama dibaca. Coba lagi, atau ketik nama daerah Anda." : "Reading your location took too long. Try again, or type your area.")
            : (isId ? "Lokasi Anda belum bisa dibaca. Coba lagi, atau ketik nama daerah Anda." : "Your location could not be read. Try again, or type your area."));
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
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
          ? "Ketik kelurahan atau kecamatan. Disimpan di perangkat ini saja."
          : "Type a kelurahan or kecamatan. Kept on this device only."}
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
      <button type="button" className="area-check-locate" onClick={locateMe} disabled={locating}>
        {locating ? (isId ? "Mencari lokasi..." : "Finding you...") : (isId ? "Pakai lokasi saya" : "Use my location")}
      </button>
      {geoNote && <p className="area-check-geo" role="status">{geoNote}</p>}

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
            <p>{isId ? "Kandidat dari survei OSM, bukan daftar resmi." : "Candidates from an OSM survey, not an official list."}</p>
          </div>
        </div>
      )}
      {chosen && (
        <p className="area-check-foot">
          {isId
            ? "Riwayat = hari banjir menurut BPBD (2023–2025 belum lengkap)."
            : "History = flood days per BPBD (2023–2025 incomplete)."}
        </p>
      )}
    </section>
  );
}
