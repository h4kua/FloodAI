import { useState, useEffect, useCallback, useRef } from "react";
import { MapContainer, CircleMarker, Polyline, Popup, useMap, useMapEvents } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";
import InvalidateMapSize from "./InvalidateMapSize";
import BaseTiles from "./BaseTiles";

// DKI Jakarta boundary for panning lock (slightly wider than risk map to allow
// route planning near borders without fighting the maxBounds constraint).
const JAKARTA_BOUNDS = [[-6.42, 106.66], [-6.06, 107.06]];

export const DESTINATIONS = [
  // Jakarta Utara
  { id: "kemayoran",  name: "GOR Kemayoran",            area: "Jakarta Utara",   address: "Jl. Benyamin Sueb, Kemayoran",          phone: "021-4207177", capacity: 2000, lat: -6.1528, lng: 106.8559 },
  { id: "ancol",      name: "Taman Impian Ancol",       area: "Jakarta Utara",   address: "Jl. Lodan Timur No.7, Ancol",           phone: "021-64710618", capacity: 1500, lat: -6.1246, lng: 106.8350 },
  // Jakarta Timur
  { id: "tmii",       name: "TMII (Pos Darurat)",       area: "Jakarta Timur",   address: "Jl. Raya Taman Mini, Cipayung",         phone: "021-8409215", capacity: 3000, lat: -6.2726, lng: 106.9020 },
  { id: "velodrome",  name: "Velodrome Rawamangun",     area: "Jakarta Timur",   address: "Jl. Pemuda, Rawamangun",               phone: "021-4758881", capacity: 1200, lat: -6.1943, lng: 106.8912 },
  // Jakarta Selatan
  { id: "gbk",        name: "GBK Senayan",              area: "Jakarta Selatan", address: "Jl. Pintu Satu Senayan, Gelora",        phone: "021-5703755", capacity: 5000, lat: -6.2181, lng: 106.8022 },
  { id: "cipete",     name: "Puskesmas Cipete Utara",   area: "Jakarta Selatan", address: "Jl. Cipete Raya No.12, Cipete",        phone: "021-7690521", capacity: 400,  lat: -6.2824, lng: 106.8043 },
  { id: "ragunan",    name: "Kebun Binatang Ragunan",   area: "Jakarta Selatan", address: "Jl. Harsono RM No.1, Pasar Minggu",    phone: "021-7884053", capacity: 2000, lat: -6.3126, lng: 106.8205 },
  // Jakarta Barat
  { id: "istiqlal",  name: "GOR Cengkareng",            area: "Jakarta Barat",   address: "Jl. Kamal Raya No.1, Cengkareng",      phone: "021-5406630", capacity: 1500, lat: -6.1450, lng: 106.7420 },
  { id: "jiexpo",    name: "JIExpo Kemayoran",           area: "Jakarta Utara",   address: "Jl. Benyamin Sueb, Kemayoran",         phone: "021-6541435", capacity: 4000, lat: -6.1598, lng: 106.8499 },
  // Jakarta Pusat
  { id: "monas",     name: "Lapangan Monas",             area: "Jakarta Pusat",   address: "Jl. Medan Merdeka Utara, Gambir",      phone: "021-3457603", capacity: 5000, lat: -6.1751, lng: 106.8272 },
  { id: "gelora",    name: "Gelanggang Olahraga Ragunan",area: "Jakarta Selatan", address: "Jl. Ragunan No.1, Pasar Minggu",       phone: "021-7800062", capacity: 800,  lat: -6.2940, lng: 106.8227 },
];

export function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

export function findNearestShelter(lat, lng) {
  return DESTINATIONS.reduce((best, d) => {
    const dist = haversineKm(lat, lng, d.lat, d.lng);
    return dist < best.dist ? { ...d, dist } : best;
  }, { ...DESTINATIONS[0], dist: Infinity });
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

export default function EvacuationMap({ origin = null, dest = null, onMapClick = null, onLocateMe = null }) {
  const t = useT();
  const { theme } = useApp();

  const [route, setRoute]           = useState(null);
  const [routeInfo, setRouteInfo]   = useState(null);
  const [navSteps, setNavSteps]     = useState([]);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState(null);
  const [flyTarget, setFlyTarget]   = useState(null);

  const fetchRoute = useCallback(async () => {
    if (!origin || !dest) { setRoute(null); setRouteInfo(null); setNavSteps([]); setError(null); return; }
    setLoading(true); setError(null); setRoute(null); setRouteInfo(null); setNavSteps([]);
    try {
      const url = `https://router.project-osrm.org/route/v1/driving/${origin.lng},${origin.lat};${dest.lng},${dest.lat}?overview=full&geometries=geojson&steps=true`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("OSRM " + res.status);
      const data = await res.json();
      if (!data.routes?.length) throw new Error("no route");
      const r = data.routes[0];
      setRoute(r.geometry.coordinates.map(([lng, lat]) => [lat, lng]));
      setRouteInfo({ distance: r.distance, duration: r.duration });
      setNavSteps(r.legs?.[0]?.steps ?? []);
    } catch { setError(t("evac.noroute")); }
    finally { setLoading(false); }
  }, [origin?.lat, origin?.lng, dest?.lat, dest?.lng]);

  useEffect(() => { fetchRoute(); }, [fetchRoute]);

  // Expose a pan function to parent via ref pattern
  const handleLocateMeClick = useCallback((lat, lng) => {
    setFlyTarget({ lat, lng });
    if (onLocateMe) onLocateMe(lat, lng);
  }, [onLocateMe]);

  const currentStep = navSteps[0];
  const nextStep    = navSteps[1];

  return (
    <div style={{ position: "relative", flex: 1, minHeight: "420px", display: "flex", flexDirection: "column" }}>
      <MapContainer
        center={[-6.23, 106.85]}
        zoom={12}
        minZoom={11}
        maxZoom={17}
        maxBounds={JAKARTA_BOUNDS}
        maxBoundsViscosity={0.9}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", minHeight: "420px", flex: 1 }}
      >
        <BaseTiles theme={theme} />
        <InvalidateMapSize />
        <FitJakartaDefault />
        {onMapClick && <MapClickHandler onMapClick={onMapClick} />}
        {flyTarget && <FlyTo lat={flyTarget.lat} lng={flyTarget.lng} />}

        {route && (
          <>
            <Polyline positions={route} pathOptions={{ color: "#1d4ed8", weight: 5, opacity: 0.85, lineJoin: "round" }} />
            <FitBounds positions={route} />
          </>
        )}

        {/* Origin marker */}
        {origin && !origin.isGPS && (
          <CircleMarker center={[origin.lat, origin.lng]} radius={12}
            pathOptions={{ fillColor: "#c8102e", fillOpacity: 0.9, color: "#c8102e", weight: 2 }}
          >
            <Popup>
              <div>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{origin.name}</p>
                <p style={{ fontSize: 11, color: "var(--s1)", margin: 0 }}>{t("evac.depart")}</p>
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

        {/* Destination / Shelter */}
        {dest && (
          <CircleMarker center={[dest.lat, dest.lng]} radius={12}
            pathOptions={{ fillColor: "#15803d", fillOpacity: 0.9, color: "#15803d", weight: 2 }}
          >
            <Popup>
              <div>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{dest.name}</p>
                <p style={{ fontSize: 11, color: "var(--safe)", margin: 0 }}>{t("evac.dest")}</p>
                {routeInfo && (
                  <p style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
                    {metersToKm(routeInfo.distance)} · {secToMin(routeInfo.duration)}
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
          {nextStep && (
            <div className="nav-step-next">
              <span style={{ opacity: 0.6 }}>{maneuverArrow(nextStep.maneuver)}</span>
              <span>{nextStep.name || "—"}</span>
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

      {/* Route info overlay */}
      {(loading || error || routeInfo) && (
        <div style={{ position: "absolute", bottom: 12, right: 12, zIndex: 1000, background: "var(--panel)", border: "1px solid var(--line-2)", borderRadius: 8, boxShadow: "var(--shadow-sm)", padding: "0.75rem 1rem", fontSize: "0.72rem" }}>
          {loading && <span style={{ color: "var(--muted)" }}>{t("evac.calc")}</span>}
          {error   && <span style={{ color: "var(--s1)" }}>{error}</span>}
          {routeInfo && !loading && (
            <div style={{ display: "flex", gap: "1rem" }}>
              <span style={{ color: "var(--cyan)", fontWeight: 700 }}>{metersToKm(routeInfo.distance)}</span>
              <span style={{ color: "var(--muted)" }}>{secToMin(routeInfo.duration)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
