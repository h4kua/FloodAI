import { useState, useRef, useCallback } from "react";
import { humanizeRiskLevel } from "../lib/humanize";
import EvacuationMap, { DESTINATIONS, findNearestShelter } from "../components/EvacuationMap";
import EmergencyContacts from "../components/EmergencyContacts";
import ChatBot from "../components/ChatBot";
import SafeArrival from "./SafeArrival";
import { useT, useApp } from "../lib/appContext";
import { use3DTilt } from "../hooks/use3DTilt";
import { useShelterGeofence } from "../hooks/useShelterGeofence";
import { getDeviceId, getFamilyCode } from "../lib/deviceIdentity";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const STEP_KEYS = ["1","2","3","4","5"];

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
  const statusTiltRef = use3DTilt({ maxTilt: 5 });
  const shelterTiltRef = use3DTilt({ maxTilt: 6 });
  const stepsTiltRef = use3DTilt({ maxTilt: 4 });
  const checklistTiltRef = use3DTilt({ maxTilt: 4 });

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

  const [safeArrivalShelter, setSafeArrivalShelter] = useState(null);
  const [checkingIn, setCheckingIn] = useState(false);

  const confirmArrival = useCallback(async (position, shelter, auto) => {
    if (!shelter) return;
    setCheckingIn(true);
    try {
      const res = await fetch(`${API_BASE}/shelters/checkin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          device_id: getDeviceId(),
          shelter_id: shelter.id,
          shelter_name: shelter.name,
          shelter_lat: shelter.lat,
          shelter_lon: shelter.lng,
          lat: position.coords.latitude,
          lon: position.coords.longitude,
          auto,
          family_code: getFamilyCode() || null,
        }),
      });
      if (res.ok) setSafeArrivalShelter(shelter.name);
    } catch {
      // Best-effort — arrival confirmation is not on the critical path.
    } finally {
      setCheckingIn(false);
    }
  }, []);

  useShelterGeofence(selectedDest, (position) => confirmArrival(position, selectedDest, true));

  const handleManualArrival = () => {
    if (!selectedDest || !navigator.geolocation) return;
    setCheckingIn(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => confirmArrival(pos, selectedDest, false),
      () => setCheckingIn(false),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const fetchSuggestions = async (query) => {
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
      setSuggestions(data.slice(0, 6));
      setShowSugg(data.length > 0);
    } catch {
      setSuggestions([]);
    } finally {
      clearTimeout(timer);
    }
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
    const { main, sub } = formatSuggestion(s);
    const label = sub ? `${main}, ${sub}` : main;
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
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.875rem", borderRadius: "999px", border: `1px solid ${config.color}33`, background: `${config.color}0d` }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: config.color, animation: "blink 1.2s infinite", flexShrink: 0 }} />
          <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem", fontWeight: 700, color: config.color, letterSpacing: "0.1em" }}>
            {config.label}
          </span>
        </div>
      </div>

      <div className="evac-grid fade-in">
        {/* Left: search + map — evac-col-left stretches to match right column height */}
        <div className="evac-col-left">

          {/* Search panel — above the map, NOT overlaid */}
          <div className="panel route-controls">
            <span className="route-label from">{t("evac.from")}</span>
            <div className="route-input-row">
              <input
                className="route-input"
                type="text"
                placeholder={t("evac.placeholder")}
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
                className="route-search-btn"
                onClick={() => { setShowSugg(false); handleGeocode(); }}
                disabled={geocoding || !addressInput.trim()}
              >
                {geocoding ? t("evac.searching") : t("evac.search")}
              </button>
              <button
                className="locate-me-btn"
                onClick={handleLocateMe}
                disabled={locating}
                title={lang === "en" ? "Use my current location" : "Gunakan lokasi saya"}
              >
                {locating ? "…" : "⊕"}
              </button>
            </div>

            {userLocation && selectedDest && (
              <div className="route-dest-row">
                <span className="route-label to">{t("evac.shelter")}</span>
                <select
                  className="route-select"
                  value={destId}
                  onChange={(e) => setDestId(e.target.value)}
                >
                  {DESTINATIONS.map((d) => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>
            )}

            {showSugg && suggestions.length > 0 && (
              <div className="suggestions-dropdown">
                {suggestions.map((s, i) => {
                  const { main, sub } = formatSuggestion(s);
                  return (
                    <div key={i} className="suggestion-item" onMouseDown={() => handleSelectSuggestion(s)}>
                      <span className="suggestion-main">{main}</span>
                      {sub && <span className="suggestion-sub">{sub}</span>}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {(geoError || locateError) && (
            <div className="geo-error-banner">{geoError || locateError}</div>
          )}

          {/* Map — klik atau GPS untuk set lokasi */}
          <div className="panel evac-map-panel" style={{ cursor: "crosshair" }}>
            <EvacuationMap
              origin={userLocation}
              dest={selectedDest}
              onMapClick={handleMapClick}
              onLocateMe={handleLocateMe}
            />
          </div>
          {!userLocation && (
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted-2)", textAlign: "center" }}>
              {lang === "en" ? "Tip: Type address above or click directly on the map" : "Tip: Ketik alamat di atas atau klik langsung di peta"}
            </p>
          )}

          {/* Legend */}
          <div style={{ display: "flex", gap: "1.5rem", padding: "0.1rem 0.25rem" }}>
            {[["#ff3d5a","evac.leg.from"],["#00cfff","evac.leg.route"],["#00e5a0","evac.leg.shelter"]].map(([c, k]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: c, boxShadow: `0 0 6px ${c}88`, flexShrink: 0 }} />
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.65rem", color: "var(--muted-2)" }}>{t(k)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right: status + shelter detail + steps + contacts */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          {/* Status card */}
          <div ref={statusTiltRef} className="panel panel-body card-3d" style={{ background: `linear-gradient(160deg,${config.color}0d,${config.color}06)`, border: `1px solid ${config.color}22`, textAlign: "center" }}>
            <div className="card-3d-content">
              <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.66rem", color: config.color, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.5rem" }}>{t("evac.status")}</p>
              <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "2.25rem", fontWeight: 800, letterSpacing: "-0.03em", color: config.color, lineHeight: 1, marginBottom: "0.5rem" }}>
                {config.label}
              </p>
              <p style={{ fontSize: "0.83rem", color: "var(--muted)", lineHeight: 1.5 }}>{config.desc}</p>
            </div>
          </div>

          {/* Shelter detail card — shown when a shelter is selected */}
          {selectedDest && (
            <div ref={shelterTiltRef} className="panel panel-body shelter-detail-card card-3d">
              <div className="card-3d-content">
                <p className="panel-title" style={{ marginBottom: "0.625rem" }}>
                  {lang === "en" ? "Selected Shelter" : "Shelter Dipilih"}
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  <div style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "1rem", fontWeight: 700, color: "var(--text)" }}>
                    {selectedDest.name}
                  </div>
                  {selectedDest.area && (
                    <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.56rem", color: "var(--muted-2)", letterSpacing: "0.06em", textTransform: "uppercase", flexShrink: 0 }}>{lang === "en" ? "Area" : "Wilayah"}</span>
                      <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>{selectedDest.area}</span>
                    </div>
                  )}
                  {selectedDest.address && (
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.45rem" }}>
                      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.56rem", color: "var(--muted-2)", letterSpacing: "0.06em", textTransform: "uppercase", marginTop: "0.15rem", flexShrink: 0 }}>{lang === "en" ? "Addr" : "Alamat"}</span>
                      <span style={{ fontSize: "0.78rem", color: "var(--muted)", lineHeight: 1.4 }}>{selectedDest.address}</span>
                    </div>
                  )}
                  <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.25rem", flexWrap: "wrap" }}>
                    {selectedDest.capacity && (
                      <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem", color: "var(--safe)" }}>
                        {selectedDest.capacity.toLocaleString()} {lang === "en" ? "cap." : "kapasitas"}
                      </span>
                    )}
                    {selectedDest.phone && (
                      <a href={`tel:${selectedDest.phone}`} style={{ display: "flex", alignItems: "center", gap: "0.3rem", textDecoration: "none" }}>
                        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.56rem", color: "var(--muted-2)", letterSpacing: "0.06em", textTransform: "uppercase" }}>{lang === "en" ? "Tel" : "Telp"}</span>
                        <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.7rem", color: "var(--cyan)" }}>
                          {selectedDest.phone}
                        </span>
                      </a>
                    )}
                  </div>
                </div>
                <p style={{ marginTop: "0.5rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.57rem", color: "var(--muted-2)" }}>
                  ● {lang === "en" ? "Tap phone to call · Route shown on map" : "Tap telepon untuk hubungi · Rute ditampilkan di peta"}
                </p>
                <button
                  className="btn"
                  style={{ marginTop: "0.75rem", width: "100%", justifyContent: "center", background: "var(--safe-soft)", color: "var(--safe)", border: "1px solid var(--safe-border)" }}
                  onClick={handleManualArrival}
                  disabled={checkingIn}
                >
                  {checkingIn ? t("evac.checkingIn") : t("evac.iveArrived")}
                </button>
              </div>
            </div>
          )}

          {/* Evacuation steps */}
          <div ref={stepsTiltRef} className="panel panel-body card-3d">
            <div className="card-3d-content">
              <p className="panel-title">{t("evac.steps")}</p>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {STEP_KEYS.map((k) => (
                  <div key={k} className="step">
                    <span className="step-num">{k}</span>
                    <div>
                      <p className="step-title">{t(`step.${k}.t`)}</p>
                      <p className="step-desc">{t(`step.${k}.d`)}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Emergency bag checklist */}
          <div ref={checklistTiltRef} className="panel panel-body card-3d">
            <div className="card-3d-content">
              <p className="panel-title">{lang === "en" ? "Emergency Kit Checklist" : "Isi Tas Darurat"}</p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.35rem" }}>
                {(lang === "en" ? [
                  "ID & documents", "Medicines (3+ days)", "Clothes (3 days)", "Flashlight + batteries",
                  "Power bank", "Drinking water", "Non-perishable food", "Phone + charger",
                  "Cash", "First aid kit",
                ] : [
                  "KTP & dokumen penting", "Obat-obatan (3+ hari)", "Pakaian (3 hari)", "Senter + baterai",
                  "Power bank", "Air minum", "Makanan tahan lama", "HP + charger",
                  "Uang tunai", "P3K",
                ]).map((item, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.75rem", color: "var(--muted)", lineHeight: 1.4 }}>
                    <span style={{ flexShrink: 0 }}>›</span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <EmergencyContacts />
        </div>
      </div>

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />

      {safeArrivalShelter && (
        <SafeArrival shelterName={safeArrivalShelter} onClose={() => setSafeArrivalShelter(null)} />
      )}
    </>
  );
}
