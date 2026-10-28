import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { MapContainer, CircleMarker, Polyline, Popup, useMap, useMapEvents } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";
import { googleMapsUrl, safestRouteIndex, splitRouteByRisk } from "../lib/floodRoads";
import { ActiveFloodAreas, StationMarkers } from "./mapLayers";
import InvalidateMapSize from "./InvalidateMapSize";
import BaseTiles from "./BaseTiles";

// DKI Jakarta boundary for panning lock (slightly wider than risk map to allow
// route planning near borders without fighting the maxBounds constraint).
const JAKARTA_BOUNDS = [[-6.42, 106.66], [-6.06, 107.06]];

// Offline fallback when /shelters/nearby cannot be reached: large public venues
// only, without phone numbers (none of them could be verified).
export const DESTINATIONS = [
  // Jakarta Utara
  { id: "kemayoran",  name: "GOR Kemayoran",            area: "Jakarta Utara",   address: "Jl. Benyamin Sueb, Kemayoran",          capacity: 2000, lat: -6.1528, lng: 106.8559 },
  { id: "ancol",      name: "Taman Impian Ancol",       area: "Jakarta Utara",   address: "Jl. Lodan Timur No.7, Ancol",           capacity: 1500, lat: -6.1246, lng: 106.8350 },
  // Jakarta Timur
  { id: "tmii",       name: "TMII (Pos Darurat)",       area: "Jakarta Timur",   address: "Jl. Raya Taman Mini, Cipayung",         capacity: 3000, lat: -6.2726, lng: 106.9020 },
  { id: "velodrome",  name: "Velodrome Rawamangun",     area: "Jakarta Timur",   address: "Jl. Pemuda, Rawamangun",               capacity: 1200, lat: -6.1943, lng: 106.8912 },
  // Jakarta Selatan
  { id: "gbk",        name: "GBK Senayan",              area: "Jakarta Selatan", address: "Jl. Pintu Satu Senayan, Gelora",        capacity: 5000, lat: -6.2181, lng: 106.8022 },
  { id: "ragunan",    name: "Kebun Binatang Ragunan",   area: "Jakarta Selatan", address: "Jl. Harsono RM No.1, Pasar Minggu",    capacity: 2000, lat: -6.3126, lng: 106.8205 },
  // Jakarta Barat
  { id: "istiqlal",  name: "GOR Cengkareng",            area: "Jakarta Barat",   address: "Jl. Kamal Raya No.1, Cengkareng",      capacity: 1500, lat: -6.1450, lng: 106.7420 },
  { id: "jiexpo",    name: "JIExpo Kemayoran",           area: "Jakarta Utara",   address: "Jl. Benyamin Sueb, Kemayoran",         capacity: 4000, lat: -6.1598, lng: 106.8499 },
  // Jakarta Pusat
  { id: "monas",     name: "Lapangan Monas",             area: "Jakarta Pusat",   address: "Jl. Medan Merdeka Utara, Gambir",      capacity: 5000, lat: -6.1751, lng: 106.8272 },
  { id: "gelora",    name: "Gelanggang Olahraga Ragunan",area: "Jakarta Selatan", address: "Jl. Ragunan No.1, Pasar Minggu",       capacity: 800,  lat: -6.2940, lng: 106.8227 },
];

export function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}


function maneuverArrow(maneuver) {
  const type = maneuver?.type;
  const mod  = maneuver?.modifier ?? "";
  if (type === "arrive")                              return "●";
  if (type === "depart")                              return "↑";
  if (mod.includes("slight left"))                   return "↖";
  if (mod.includes("slight right"))                  return "↗";
  if (mod.includes("left")  || mod.includes("uturn left"))  return "←";
  if (mod.includes("right") || mod.includes("uturn right")) return "→";
  return "↑";
}

// Fits to DKI Jakarta on first mount only — does not override route FitBounds.
function FitJakartaDefault() {
  const map = useMap();
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current) return;
    fitted.current = true;
    map.fitBounds(JAKARTA_BOUNDS, { padding: [12, 12], animate: false });
  }, [map]);
  return null;
}

function FitBounds({ positions }) {
  const map = useMap();
  useEffect(() => {
    if (positions?.length >= 2) {
      try { map.fitBounds(positions.map(p => [p[0], p[1]]), { padding: [48, 48] }); } catch (_) {}
    }
  }, [map, positions]);
  return null;
}

function MapClickHandler({ onMapClick }) {
  useMapEvents({ click(e) { if (onMapClick) onMapClick(e.latlng.lat, e.latlng.lng); } });
  return null;
}

// Pans map to a lat/lng
function FlyTo({ lat, lng, zoom = 15 }) {
  const map = useMap();
  useEffect(() => {
    if (lat && lng) map.flyTo([lat, lng], zoom, { duration: 1.2 });
  }, [lat, lng]);
  return null;
}

function metersToKm(m) {
  return m >= 1000 ? (m / 1000).toFixed(1) + " km" : Math.round(m) + " m";
}
function secToMin(s) {
  const m = Math.round(s / 60);
  return m < 60 ? m + " min" : Math.floor(m / 60) + "h " + (m % 60) + "m";
}

// Map colours: roads are green/red, so the endpoints use blue and violet.
export const EVAC_COLORS = {
  from: "#1d4ed8",
  dest: "#7c3aed",
  safe: "#15803d",
  risky: "#c8102e",
  alt: "#94a3b8",
};

export default function EvacuationMap({ origin = null, dest = null, floodPoints = [], stations = [], onMapClick = null, onLocateMe = null }) {
  const t = useT();
  const { theme, lang } = useApp();
  const isId = lang !== "en";

  const [routes, setRoutes]         = useState([]);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);
  const [flyTarget, setFlyTarget]   = useState(null);

  const fetchRoute = useCallback(async () => {
    if (!origin || !dest) { setRoutes([]); setError(null); return; }
    setLoading(true); setError(null); setRoutes([]);
    try {
      // Ask for alternatives so a drier road can be chosen over the fastest one.
      const url = `https://router.project-osrm.org/route/v1/driving/${origin.lng},${origin.lat};${dest.lng},${dest.lat}?overview=full&geometries=geojson&steps=true&alternatives=3`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("OSRM " + res.status);
      const data = await res.json();
      if (!data.routes?.length) throw new Error("no route");
      setRoutes(data.routes.map((r) => ({
        coords: r.geometry.coordinates.map(([lng, lat]) => [lat, lng]),
        distance: r.distance,
        duration: r.duration,
        steps: r.legs?.[0]?.steps ?? [],
      })));
    } catch { setError(t("evac.noroute")); }
    finally { setLoading(false); }
  }, [origin?.lat, origin?.lng, dest?.lat, dest?.lng]);

  useEffect(() => { fetchRoute(); }, [fetchRoute]);

  // Re-scored whenever the live flood data changes, without refetching routes.
  // No route without both ends: a destination can be cleared (e.g. "another
  // place" chosen but not typed yet) one render before the routes reset.
  const scored = useMemo(
    () => (origin && dest ? routes.map((r) => ({ ...r, ...splitRouteByRisk(r.coords, floodPoints) })) : []),
    [routes, floodPoints, origin, dest],
  );
  const chosenIdx = safestRouteIndex(scored);
  const chosen = chosenIdx >= 0 ? scored[chosenIdx] : null;
  const fastest = scored.length ? scored.reduce((a, b) => (b.duration < a.duration ? b : a)) : null;
  const detourMin = chosen && fastest ? Math.round((chosen.duration - fastest.duration) / 60) : 0;

  const navSteps    = chosen?.steps ?? [];
  const currentStep = navSteps[0];
  const nextStep    = navSteps[1];

  return (
    <div style={{ position: "relative", flex: 1, minHeight: "420px", display: "flex", flexDirection: "column" }}>
      <MapContainer
        center={[-6.23, 106.85]}
        zoom={12}
        minZoom={11}
        maxZoom={19}
        maxBounds={JAKARTA_BOUNDS}
        maxBoundsViscosity={0.9}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", minHeight: "420px", flex: 1 }}
      >
        <BaseTiles theme={theme} variant="street" />
        <InvalidateMapSize />
        <FitJakartaDefault />
        {onMapClick && <MapClickHandler onMapClick={onMapClick} />}
        {flyTarget && <FlyTo lat={flyTarget.lat} lng={flyTarget.lng} />}

        {/* Active flood-prone areas and the posts that drive them (shared with the water-level map) */}
        <ActiveFloodAreas points={floodPoints} />
        <StationMarkers stations={stations} small />

        {/* Other alternatives, faint; the chosen route on top in green/red runs */}
        {scored.map((r, i) => i !== chosenIdx && (
          <Polyline key={`alt-${i}`} positions={r.coords}
            pathOptions={{ color: EVAC_COLORS.alt, weight: 4, opacity: 0.55, dashArray: "6 8" }} />
        ))}
        {chosen && (
          <>
            {chosen.runs.map((run, i) => (
              <Polyline key={`run-${i}`} positions={run.positions}
                pathOptions={{ color: run.risky ? EVAC_COLORS.risky : EVAC_COLORS.safe, weight: 6, opacity: 0.9, lineJoin: "round", lineCap: "round" }} />
            ))}
            <FitBounds positions={chosen.coords} />
          </>
        )}

        {/* Origin marker */}
        {origin && !origin.isGPS && (
          <CircleMarker center={[origin.lat, origin.lng]} radius={11}
            pathOptions={{ fillColor: EVAC_COLORS.from, fillOpacity: 0.95, color: "#fff", weight: 2.5 }}
          >
            <Popup>
              <div>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{origin.name}</p>
                <p style={{ fontSize: 11, color: "var(--cyan)", margin: 0 }}>{t("evac.depart")}</p>
              </div>
            </Popup>
          </CircleMarker>
        )}

        {/* GPS current location — blue dot with pulse ring */}
        {origin?.isGPS && (
          <>
            <CircleMarker center={[origin.lat, origin.lng]} radius={22}
              pathOptions={{ fillColor: "#4285f4", fillOpacity: 0.15, color: "#4285f4", weight: 1.5, opacity: 0.5 }}
            />
            <CircleMarker center={[origin.lat, origin.lng]} radius={10}
              pathOptions={{ fillColor: "#4285f4", fillOpacity: 0.95, color: "#fff", weight: 2.5 }}
            >
              <Popup>
                <div>
                  <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{t("evac.yourLocation")}</p>
                  <p style={{ fontSize: 11, color: "var(--cyan)", margin: 0 }}>{t("evac.gpsAccurate")}</p>
                </div>
              </Popup>
            </CircleMarker>
          </>
        )}

        {/* Destination — a shelter or home */}
        {dest && (
          <CircleMarker center={[dest.lat, dest.lng]} radius={11}
            pathOptions={{ fillColor: EVAC_COLORS.dest, fillOpacity: 0.95, color: "#fff", weight: 2.5 }}
          >
            <Popup>
              <div>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{dest.name}</p>
                <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
                  {dest.isHome ? (isId ? "Rumah" : "Home") : t("evac.dest")}
                </p>
                {chosen && (
                  <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                    {metersToKm(chosen.distance)} · {secToMin(chosen.duration)}
                  </p>
                )}
              </div>
            </Popup>
          </CircleMarker>
        )}
      </MapContainer>

      {/* Nav instruction panel — shows when route + steps exist */}
      {navSteps.length > 0 && currentStep && (
        <div className="nav-panel">
          <div className="nav-step-current">
            <span className="nav-arrow">{maneuverArrow(currentStep.maneuver)}</span>
            <div className="nav-step-info">
              <p className="nav-street">{currentStep.name || (t ? t("evac.continueOn") : "Continue")}</p>
              <p className="nav-dist">{metersToKm(currentStep.distance)}</p>
            </div>
          </div>
          {nextStep && (nextStep.name || nextStep.maneuver?.type === "arrive") && (
            <div className="nav-step-next">
              <span style={{ opacity: 0.6 }}>{maneuverArrow(nextStep.maneuver)}</span>
              <span>{nextStep.name || (t ? t("evac.arrive") : "Arrive")}</span>
            </div>
          )}
        </div>
      )}

      {/* Placeholder overlay */}
      {!origin && (
        <div style={{ position: "absolute", inset: 0, zIndex: 500, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
          <div style={{ background: "var(--panel)", border: "1px solid var(--line-2)", borderRadius: 8, boxShadow: "var(--shadow)", padding: "1rem 1.5rem", textAlign: "center" }}>
            <p style={{ fontSize: "0.72rem", color: "var(--cyan)", marginBottom: "0.3rem" }}>
              {t("evac.hint.title")}
            </p>
            <p style={{ fontSize: "0.8rem", color: "var(--muted)", margin: 0 }}>{t("evac.hint.desc")}</p>
          </div>
        </div>
      )}

      {/* Route summary — distance, time, and how much of it runs through risky areas */}
      {(loading || error || chosen) && (
        <div className="route-summary">
          {loading && <span style={{ color: "var(--muted)" }}>{t("evac.calc")}</span>}
          {error   && <span style={{ color: "var(--s1)" }}>{error}</span>}
          {chosen && !loading && (
            <>
              <div style={{ display: "flex", gap: "1rem" }}>
                <span style={{ color: "var(--cyan)", fontWeight: 700 }}>{metersToKm(chosen.distance)}</span>
                <span style={{ color: "var(--muted)" }}>{secToMin(chosen.duration)}</span>
              </div>
              {chosen.riskyM > 0 ? (
                <p className="route-summary-risk">
                  {isId
                    ? `${metersToKm(chosen.riskyM)} melewati area rawan banjir`
                    : `${metersToKm(chosen.riskyM)} passes flood-prone areas`}
                  {scored.length > 1 && (isId ? " — rute lain lebih rawan." : " — the other routes are riskier.")}
                </p>
              ) : (
                <p className="route-summary-safe">
                  {isId ? "Tidak melewati area rawan yang aktif" : "Avoids the active flood-prone areas"}
                </p>
              )}
              {chosen !== fastest && detourMin > 0 && (
                <p className="route-summary-note">
                  {isId ? `Memutar ±${detourMin} mnt untuk menghindari area rawan` : `About ${detourMin} min longer to avoid flood-prone areas`}
                </p>
              )}
              {/* Hand the chosen route to Google Maps for turn-by-turn navigation */}
              <a className="route-gmaps" href={googleMapsUrl(origin, dest, chosen.coords)} target="_blank" rel="noopener noreferrer">
                {isId ? "Buka di Google Maps" : "Open in Google Maps"} ↗
              </a>
            </>
          )}
        </div>
      )}
    </div>
  );
}
