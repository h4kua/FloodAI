import { useState, useRef } from "react";
import { humanizeRiskLevel } from "../lib/humanize";
import EvacuationMap, { DESTINATIONS, findNearestShelter } from "../components/EvacuationMap";
import EmergencyContacts from "../components/EmergencyContacts";
import ChatBot from "../components/ChatBot";
import { useT } from "../lib/appContext";

const STEP_KEYS = ["1","2","3","4","5"];

async function geocodeAddress(address) {
  const q = encodeURIComponent(address + ", Jakarta, Indonesia");
  const url = `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=1&countrycodes=id`;
  const res = await fetch(url, {
    headers: { "Accept-Language": "id", "User-Agent": "deFlood.ai/1.0" },
  });
  if (!res.ok) throw new Error("Geocoding gagal");
  const data = await res.json();
  if (!data.length) throw new Error("Alamat tidak ditemukan. Coba tambahkan kelurahan atau kecamatan.");
  return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon) };
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
  const [addressInput, setAddressInput] = useState("");
  const [userLocation, setUserLocation] = useState(null);
  const [destId, setDestId]             = useState(null);
  const [geocoding, setGeocoding]       = useState(false);
  const [geoError, setGeoError]         = useState("");
  const [suggestions, setSuggestions]   = useState([]);
  const [showSugg, setShowSugg]         = useState(false);
  const debounceRef = useRef(null);

  const config       = humanizeRiskLevel(riskLevel);
  const selectedDest = destId ? DESTINATIONS.find((d) => d.id === destId) ?? null : null;

  const fetchSuggestions = async (query) => {
    const q = encodeURIComponent(query + " Jakarta");
    const url = `https://nominatim.openstreetmap.org/search?q=${q}&format=json&limit=6&countrycodes=id&addressdetails=1`;
    try {
      const res = await fetch(url, {
        headers: { "Accept-Language": "id", "User-Agent": "deFlood.ai/1.0" },
      });
      const data = await res.json();
      setSuggestions(data.slice(0, 6));
      setShowSugg(data.length > 0);
    } catch {
      setSuggestions([]);
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

            {userLocation && selectedDest && (
              <>
                <span className="route-sep">→</span>
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
              </>
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

          {geoError && (
            <div className="geo-error-banner">{geoError}</div>
          )}

          {/* Map */}
          <div className="panel evac-map-panel">
            <EvacuationMap origin={userLocation} dest={selectedDest} />
          </div>

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

        {/* Right: status + steps + contacts */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
          <div className="panel panel-body" style={{ background: `linear-gradient(160deg,${config.color}0d,${config.color}06)`, border: `1px solid ${config.color}22`, textAlign: "center" }}>
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.66rem", color: config.color, letterSpacing: "0.14em", textTransform: "uppercase", marginBottom: "0.5rem" }}>{t("evac.status")}</p>
            <p style={{ fontFamily: "'Space Grotesk',sans-serif", fontSize: "2.25rem", fontWeight: 800, letterSpacing: "-0.03em", color: config.color, lineHeight: 1, marginBottom: "0.5rem" }}>
              {config.label}
            </p>
            <p style={{ fontSize: "0.83rem", color: "var(--muted)", lineHeight: 1.5 }}>{config.desc}</p>
          </div>

          <div className="panel panel-body">
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

          <EmergencyContacts />
        </div>
      </div>

      <ChatBot riskContext={{ level: riskLevel, rainfall }} />
    </>
  );
}
