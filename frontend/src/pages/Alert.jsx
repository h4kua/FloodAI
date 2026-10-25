import { useState, useRef, useMemo } from "react";
import { humanizeRiskLevel } from "../lib/humanize";
import EvacuationMap, { DESTINATIONS, EVAC_COLORS, findNearestShelter, haversineKm } from "../components/EvacuationMap";
import floodProneZones from "../data/floodProneZones.json";
import { activeFloodPoints } from "../lib/floodRoads";
import { useFloodRisk } from "../hooks/useFloodRisk";
import ChatBot from "../components/ChatBot";
import { useT, useApp } from "../lib/appContext";


async function geocodeAddress(address) {
  const q = encodeURIComponent(address + ", Jakarta, Indonesia");
  const url = `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1&countrycodes=id`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(url, {
      headers: { "Accept-Language": "id", "User-Agent": "deFlood.ai/1.0" },
      signal: controller.signal,
    });
    if (!res.ok) throw new Error("Geocoding gagal");
    const data = await res.json();
    if (!data.length) throw new Error("Alamat tidak ditemukan. Coba tambahkan kelurahan atau kecamatan.");
    return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
  } catch (err) {
    if (err.name === "AbortError") throw new Error("Pencarian alamat timeout. Coba lagi.");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function searchPlaces(query) {
  const q = encodeURIComponent(query + " Jakarta");
  const url = `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=6&countrycodes=id&addressdetails=1`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  try {
    const res = await fetch(url, {
      headers: { "Accept-Language": "id", "User-Agent": "deFlood.ai/1.0" },
      signal: controller.signal,
    });
    const data = await res.json();
    return data.slice(0, 6);
  } catch {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

// The home address stays in this browser (localStorage), never on the server.
const HOME_KEY = "deflood.home";

function loadHome() {
  try {
    const v = JSON.parse(localStorage.getItem(HOME_KEY));
    return v && Number.isFinite(v.lat) && Number.isFinite(v.lng) ? { ...v, isHome: true } : null;
  } catch {
    return null;
  }
}

function saveHome(home) {
  try {
    localStorage.setItem(HOME_KEY, JSON.stringify({ lat: home.lat, lng: home.lng, name: home.name }));
  } catch {
    // Private mode or blocked storage: the home still works for this visit.
  }
}

function suggestionLabel(s) {
  const { main, sub } = formatSuggestion(s);
  return sub ? `${main}, ${sub}` : main;
}

// The "Rumah" entry in the destination dropdown.
const HOME_OPTION = "__home";

// "Kembangan Selatan, Kembangan, Jakarta Barat" → "Kembangan Selatan"
const shortPlace = (name) => (name || "").split(",")[0].trim();

function Suggestions({ items, onPick }) {
  return (
    <div className="suggestions-dropdown">
      {items.map((s, i) => {
        const { main, sub } = formatSuggestion(s);
        return (
          <div key={i} className="suggestion-item" onMouseDown={() => onPick(s)}>
            <span className="suggestion-main">{main}</span>
            {sub && <span className="suggestion-sub">{sub}</span>}
          </div>
        );
      })}
    </div>
  );
}

function formatSuggestion(s) {
  const addr = s.address ?? {};
  const main =
    addr.road || addr.pedestrian || addr.path ||
    addr.neighbourhood || addr.name ||
    s.display_name.split(",")[0].trim();
  const sub = [addr.suburb || addr.neighbourhood, addr.city_district, addr.city || addr.town]
    .filter(Boolean)
    .filter((v, i, arr) => arr.indexOf(v) === i)
    .slice(0, 2)
    .join(", ");
  return { main, sub };
}

export default function Alert({ riskLevel = "waspada", rainfall = 0 }) {
  const t = useT();
  const { lang } = useApp();

  const [addressInput, setAddressInput] = useState("");
  const [userLocation, setUserLocation] = useState(null);
  const [destId, setDestId]             = useState(null);
  const [geocoding, setGeocoding]       = useState(false);
  const [geoError, setGeoError]         = useState("");
  const [suggestions, setSuggestions]   = useState([]);
  const [showSugg, setShowSugg]         = useState(false);
  const [locating, setLocating]         = useState(false);
  const [locateError, setLocateError]   = useState("");
  const debounceRef = useRef(null);

  const config       = humanizeRiskLevel(riskLevel, lang);
  const selectedDest = destId ? DESTINATIONS.find((d) => d.id === destId) ?? null : null;

  // Destination: a shelter (default, nearest) or home.
  const [destMode, setDestMode]         = useState("shelter");
  const [home, setHome]                 = useState(loadHome);
  const [homeInput, setHomeInput]       = useState(() => loadHome()?.name ?? "");
  const [homeSugg, setHomeSugg]         = useState([]);
  const [showHomeSugg, setShowHomeSugg] = useState(false);
  const [editingHome, setEditingHome]   = useState(false);
  const homeDebounceRef = useRef(null);
  const destination = destMode === "home" ? home : selectedDest;
  const shelterChosen = destMode === "shelter" && selectedDest;

  // Shelters nearest-first from where the user starts.
  const shelterOptions = useMemo(() => (
    userLocation
      ? [...DESTINATIONS].sort((a, b) =>
          haversineKm(userLocation.lat, userLocation.lng, a.lat, a.lng)
          - haversineKm(userLocation.lat, userLocation.lng, b.lat, b.lng))
      : DESTINATIONS
  ), [userLocation]);
  const nearestId = userLocation ? shelterOptions[0].id : null;
  const destValue = destMode === "home" ? HOME_OPTION : (destId ?? "");

  const handleDestChange = (e) => {
    const value = e.target.value;
    if (value === HOME_OPTION) {
      setDestMode("home");
    } else {
      setDestMode("shelter");
      setDestId(value);
    }
  };

  // Flood-prone areas that count right now: BPBD points on a river whose post
  // is at Siaga, or all of them in heavy rain.
  const { riskData } = useFloodRisk();
  const floodPoints = useMemo(
    () => activeFloodPoints(floodProneZones.points, riskData?.stations ?? [], riskData?.rainfall ?? 0),
    [riskData],
  );

  const fetchSuggestions = async (query) => {
    const data = await searchPlaces(query);
    setSuggestions(data);
    setShowSugg(data.length > 0);
  };

  const handleHomeInputChange = (e) => {
    const val = e.target.value;
    setHomeInput(val);
    clearTimeout(homeDebounceRef.current);
    if (val.trim().length >= 3) {
      homeDebounceRef.current = setTimeout(async () => {
        const data = await searchPlaces(val);
        setHomeSugg(data);
        setShowHomeSugg(data.length > 0);
      }, 400);
    } else {
      setHomeSugg([]);
      setShowHomeSugg(false);
    }
  };

  const handleSelectHome = (s) => {
    const name = suggestionLabel(s);
    const next = { lat: parseFloat(s.lat), lng: parseFloat(s.lon), name, isHome: true };
    setHome(next);
    saveHome(next);
    setEditingHome(false);
    setHomeInput(name);
    setHomeSugg([]);
    setShowHomeSugg(false);
  };

  const handleInputChange = (e) => {
    const val = e.target.value;
    setAddressInput(val);
    clearTimeout(debounceRef.current);
    if (val.trim().length >= 3) {
      debounceRef.current = setTimeout(() => fetchSuggestions(val), 400);
    } else {
      setSuggestions([]);
      setShowSugg(false);
    }
  };

  const handleSelectSuggestion = (s) => {
    const label = suggestionLabel(s);
    setAddressInput(label);
    setSuggestions([]);
    setShowSugg(false);
    setGeoError("");
    const lat = parseFloat(s.lat);
    const lng = parseFloat(s.lon);
    const nearest = findNearestShelter(lat, lng);
    setUserLocation({ lat, lng, name: label });
    setDestId(nearest.id);
  };

  const handleLocateMe = () => {
    if (!navigator.geolocation) {
      setLocateError(lang === "en" ? "Geolocation not supported by your browser." : "Browser tidak mendukung geolocation.");
      return;
    }
    setLocating(true);
    setLocateError("");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        try {
          const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&accept-language=${lang}`;
          const res = await fetch(url, { headers: { "User-Agent": "deFlood.ai/1.0" } });
          const data = await res.json();
          const name = data.display_name
            ? data.display_name.split(",").slice(0, 3).join(", ")
            : `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
          setAddressInput(name);
          const nearest = findNearestShelter(lat, lng);
          setUserLocation({ lat, lng, name, isGPS: true });
          setDestId(nearest.id);
          setGeoError("");
        } catch {
          const name = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
          setAddressInput(name);
          const nearest = findNearestShelter(lat, lng);
          setUserLocation({ lat, lng, name, isGPS: true });
          setDestId(nearest.id);
        }
        setLocating(false);
      },
      (err) => {
        setLocating(false);
        const msg = err.code === 1
          ? (lang === "en" ? "Location access denied. Please allow location in browser settings." : "Akses lokasi ditolak. Izinkan lokasi di pengaturan browser.")
          : (lang === "en" ? "Could not get your location. Try again." : "Tidak dapat mengambil lokasi. Coba lagi.");
        setLocateError(msg);
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }
    );
  };

  const handleMapClick = async (lat, lng) => {
    setGeoError("");
    setSuggestions([]);
    setShowSugg(false);
    setGeocoding(true);
    setUserLocation(null);
    setDestId(null);
    try {
      // Reverse geocode clicked point
      const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&accept-language=${lang}`;
      const res = await fetch(url, { headers: { "User-Agent": "deFlood.ai/1.0" } });
      const data = await res.json();
      const name = data.display_name
        ? data.display_name.split(",").slice(0, 3).join(", ")
        : `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
      setAddressInput(name);
      const nearest = findNearestShelter(lat, lng);
      setUserLocation({ lat, lng, name });
      setDestId(nearest.id);
    } catch {
      const name = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
      setAddressInput(name);
      const nearest = findNearestShelter(lat, lng);
      setUserLocation({ lat, lng, name });
      setDestId(nearest.id);
    } finally {
      setGeocoding(false);
    }
  };

  const handleGeocode = async () => {
    const addr = addressInput.trim();
    if (!addr) return;
    setSuggestions([]);
    setShowSugg(false);
    setGeocoding(true);
    setGeoError("");
    setUserLocation(null);
    setDestId(null);
    try {
      const loc = await geocodeAddress(addr);
      const nearest = findNearestShelter(loc.lat, loc.lng);
      setUserLocation({ lat: loc.lat, lng: loc.lng, name: addr });
      setDestId(nearest.id);
    } catch (e) {
      setGeoError(e.message ?? "Alamat tidak ditemukan.");
    } finally {
      setGeocoding(false);
    }
  };

  return (
    <>
      {/* Page header */}
      <div className="page-header fade-in">
        <div>
          <h1 className="page-title">{t("evac.title")}</h1>
        </div>
        <span
          className={`risk-badge badge-${{ aman: "ok", waspada: "wsp", siaga: "s2", bahaya: "s1", unknown: "unknown" }[riskLevel] ?? "wsp"}`}
          style={{ fontSize: "0.85rem", padding: "0.35rem 0.7rem" }}
        >
          Status: {config.label}
        </span>
      </div>

      <div className="evac-col-left fade-in">
        {/* Primary CTA — one tap: GPS → nearest shelter → route (decision-first).
            Hidden once a location is set; the search panel takes over. */}
        {!userLocation && (
          <button className="evac-primary-cta" onClick={handleLocateMe} disabled={locating}>
            <span className="evac-primary-cta-icon" aria-hidden="true">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="3 11 22 2 13 21 11 13 3 11" />
              </svg>
            </span>
            <span className="evac-primary-cta-text">
              <strong>{locating ? t("evac.locatingYou") : t("evac.ctaNearest")}</strong>
              <small>{t("evac.ctaNearestSub")}</small>
            </span>
          </button>
        )}

        {/* From / To — one field per row */}
        <div className="panel route-controls">
          <label className="route-label" htmlFor="route-from">{t("evac.from")}</label>
          <div className="route-field">
            <input
              id="route-from"
              className="route-input"
              type="text"
              placeholder={geocoding ? t("evac.searching") : t("evac.placeholder")}
              value={addressInput}
              onChange={handleInputChange}
              onFocus={() => suggestions.length > 0 && setShowSugg(true)}
              onBlur={() => setTimeout(() => setShowSugg(false), 180)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !geocoding) { setShowSugg(false); handleGeocode(); }
                if (e.key === "Escape") setShowSugg(false);
              }}
              disabled={geocoding}
            />
            <button
              className="route-field-btn"
              onClick={handleLocateMe}
              disabled={locating}
              title={lang === "en" ? "Use my current location" : "Gunakan lokasi saya"}
              aria-label={lang === "en" ? "Use my current location" : "Gunakan lokasi saya"}
            >
              {locating ? "…" : "⊕"}
            </button>
            {showSugg && suggestions.length > 0 && (
              <Suggestions items={suggestions} onPick={handleSelectSuggestion} />
            )}
          </div>

          {userLocation && (
            <>
              <label className="route-label" htmlFor="route-to">{t("evac.shelter")}</label>
              <div className="route-field">
                <select id="route-to" className="route-select" value={destValue} onChange={handleDestChange}>
                  {shelterOptions.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.id === nearestId ? `${d.name} (${lang === "en" ? "nearest" : "terdekat"})` : d.name}
                    </option>
                  ))}
                  <option value={HOME_OPTION}>
                    {home ? `${lang === "en" ? "Home" : "Rumah"} — ${shortPlace(home.name)}` : (lang === "en" ? "Home…" : "Rumah…")}
                  </option>
                </select>
              </div>
            </>
          )}

          {userLocation && destMode === "home" && (home === null || editingHome) && (
            <div className="route-field route-field-sub">
              <input
                className="route-input"
                type="text"
                autoFocus
                placeholder={lang === "en" ? "Your home address…" : "Alamat rumah Anda…"}
                value={homeInput}
                onChange={handleHomeInputChange}
                onFocus={() => homeSugg.length > 0 && setShowHomeSugg(true)}
                onBlur={() => setTimeout(() => setShowHomeSugg(false), 180)}
                onKeyDown={(e) => { if (e.key === "Escape") setShowHomeSugg(false); }}
              />
              {showHomeSugg && homeSugg.length > 0 && (
                <Suggestions items={homeSugg} onPick={handleSelectHome} />
              )}
            </div>
          )}
          {userLocation && destMode === "home" && home && !editingHome && (
            <button className="route-link route-field-sub" onClick={() => setEditingHome(true)}>
              {lang === "en" ? "Change home address" : "Ubah alamat rumah"}
            </button>
          )}
        </div>

        {(geoError || locateError) && (
          <div className="geo-error-banner">{geoError || locateError}</div>
        )}

        {/* Map — klik atau GPS untuk set lokasi */}
        <div className="panel evac-map-panel" style={{ cursor: "crosshair" }}>
          <EvacuationMap
            origin={userLocation}
            dest={destination}
            floodPoints={floodPoints}
            onMapClick={handleMapClick}
            onLocateMe={handleLocateMe}
          />
        </div>

        {/* The chosen shelter, in one line */}
        {shelterChosen && (
          <div className="shelter-line">
            <i style={{ background: EVAC_COLORS.dest }} aria-hidden="true" />
            <div>
              <p><strong>{selectedDest.name}</strong>{selectedDest.address ? ` · ${selectedDest.address}` : ""}</p>
              <p className="shelter-line-meta">
                {selectedDest.capacity && (lang === "en"
                  ? `Room for about ${selectedDest.capacity.toLocaleString()} people`
                  : `Muat ±${selectedDest.capacity.toLocaleString("id-ID")} orang`)}
                {selectedDest.phone && (
                  <> · <a href={`tel:${selectedDest.phone}`}>{selectedDest.phone}</a></>
                )}
              </p>
            </div>
          </div>
        )}

        {/* What the map colours mean, and what the red is based on */}
        <div className="evac-legend">
          <ul>
            {userLocation && (
              <>
                <li><i className="dot" style={{ background: EVAC_COLORS.from }} />{t("evac.leg.from")}</li>
                <li><i className="dot" style={{ background: EVAC_COLORS.dest }} />
                  {destMode === "home" ? (lang === "en" ? "Home" : "Rumah") : t("evac.leg.shelter")}</li>
                <li><i className="line" style={{ background: EVAC_COLORS.safe }} />{lang === "en" ? "Road likely clear" : "Jalan relatif aman"}</li>
                <li><i className="line" style={{ background: EVAC_COLORS.risky }} />{lang === "en" ? "Road through a flood-prone area" : "Jalan lewat area rawan banjir"}</li>
              </>
            )}
            <li><i className="area" style={{ borderColor: EVAC_COLORS.risky }} />
              {floodPoints.length > 0
                ? (lang === "en" ? `${floodPoints.length} flood-prone areas active now` : `${floodPoints.length} area rawan banjir aktif sekarang`)
                : (lang === "en" ? "No flood-prone area is active now" : "Tidak ada area rawan banjir yang aktif sekarang")}</li>
          </ul>
          <p>
            {lang === "en"
              ? "An estimate from BPBD flood-prone points near rivers whose water-level post is on alert (all points in heavy rain) — not live road conditions. Check the road yourself before you go."
              : "Perkiraan dari titik rawan banjir BPBD di sungai yang pos pantaunya berstatus Siaga (semua titik saat hujan deras) — bukan kondisi jalan langsung. Tetap cek kondisi jalan sebelum berangkat."}
          </p>
        </div>
      </div>

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />
    </>
  );
}
