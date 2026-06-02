import { useState, useEffect, useCallback } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, useMap } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";

const TILE_DARK  = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_LIGHT = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR  = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';
const JAKARTA_BOUNDS = [[-6.55, 106.55], [-5.95, 107.15]];

export const DESTINATIONS = [
  { id: "kemayoran", name: "Kemayoran (Shelter)",   lat: -6.1528, lng: 106.8559 },
  { id: "ancol",     name: "Ancol (Pos Evakuasi)",  lat: -6.1246, lng: 106.8350 },
  { id: "tmii",      name: "TMII (Pos Darurat)",    lat: -6.2726, lng: 106.9020 },
  { id: "gbk",       name: "GBK Senayan (Shelter)", lat: -6.2181, lng: 106.8022 },
  { id: "cipete",    name: "Cipete (Pos Aman)",     lat: -6.2824, lng: 106.8043 },
];

function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function findNearestShelter(lat, lng) {
  return DESTINATIONS.reduce((best, d) => {
    const dist = haversineKm(lat, lng, d.lat, d.lng);
    return dist < best.dist ? { ...d, dist } : best;
  }, { ...DESTINATIONS[0], dist: Infinity });
}

function FitBounds({ positions }) {
  const map = useMap();
  useEffect(() => {
    if (positions && positions.length >= 2) {
      try { map.fitBounds(positions.map((p) => [p[0], p[1]]), { padding: [48, 48] }); } catch (_) {}
    }
  }, [map, positions]);
  return null;
}

function metersToKm(m) {
  return m >= 1000 ? (m / 1000).toFixed(1) + " km" : Math.round(m) + " m";
}
function secToMin(s) {
  const m = Math.round(s / 60);
  return m < 60 ? m + " min" : Math.floor(m / 60) + "h " + (m % 60) + "m";
}

export default function EvacuationMap({ origin = null, dest = null }) {
  const t = useT();
  const { theme } = useApp();
  const tileUrl = theme === "light" ? TILE_LIGHT : TILE_DARK;

  const [route, setRoute]       = useState(null);
  const [routeInfo, setRouteInfo] = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);

  const fetchRoute = useCallback(async () => {
    if (!origin || !dest) { setRoute(null); setRouteInfo(null); setError(null); return; }
    setLoading(true); setError(null); setRoute(null); setRouteInfo(null);
    try {
      const url = `https://router.project-osrm.org/route/v1/driving/${origin.lng},${origin.lat};${dest.lng},${dest.lat}?overview=full&geometries=geojson`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("OSRM " + res.status);
      const data = await res.json();
      if (!data.routes?.length) throw new Error("no route");
      setRoute(data.routes[0].geometry.coordinates.map(([lng, lat]) => [lat, lng]));
      setRouteInfo({ distance: data.routes[0].distance, duration: data.routes[0].duration });
    } catch { setError(t("evac.noroute")); }
    finally { setLoading(false); }
  }, [origin?.lat, origin?.lng, dest?.lat, dest?.lng]);

  useEffect(() => { fetchRoute(); }, [fetchRoute]);

  return (
    <div style={{ position: "relative", flex: 1, minHeight: "420px" }}>
      <MapContainer
        center={[-6.2, 106.83]}
        zoom={11}
        minZoom={10}
        maxBounds={JAKARTA_BOUNDS}
        maxBoundsViscosity={1.0}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", minHeight: "420px" }}
      >
        <TileLayer url={tileUrl} attribution={TILE_ATTR} />

        {route && (
          <>
            <Polyline positions={route} pathOptions={{ color: "var(--cyan,#00cfff)", weight: 5, opacity: 0.85, lineJoin: "round" }} />
            <FitBounds positions={route} />
          </>
        )}

        {origin && (
          <CircleMarker center={[origin.lat, origin.lng]} radius={12}
            pathOptions={{ fillColor: "#ff3d5a", fillOpacity: 0.9, color: "#ff3d5a", weight: 2 }}
          >
            <Popup>
              <div style={{ fontFamily: "'Inter',sans-serif" }}>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{origin.name}</p>
                <p style={{ fontSize: 11, color: "#ff9dac", margin: 0 }}>{t("evac.depart")}</p>
              </div>
            </Popup>
          </CircleMarker>
        )}

        {dest && (
          <CircleMarker center={[dest.lat, dest.lng]} radius={12}
            pathOptions={{ fillColor: "#00e5a0", fillOpacity: 0.9, color: "#00e5a0", weight: 2 }}
          >
            <Popup>
              <div style={{ fontFamily: "'Inter',sans-serif" }}>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{dest.name}</p>
                <p style={{ fontSize: 11, color: "#8cffd8", margin: 0 }}>{t("evac.dest")}</p>
                {routeInfo && (
                  <p style={{ fontSize: 11, color: "#8f96a9", marginTop: 4 }}>
                    {metersToKm(routeInfo.distance)} · {secToMin(routeInfo.duration)}
                  </p>
                )}
              </div>
            </Popup>
          </CircleMarker>
        )}
      </MapContainer>

      {!origin && (
        <div style={{ position: "absolute", inset: 0, zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
          <div style={{ background: "rgba(9,9,13,0.82)", backdropFilter: "blur(10px)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 14, padding: "1rem 1.5rem", textAlign: "center" }}>
            <p style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: "0.72rem", color: "var(--cyan)", letterSpacing: "0.08em", marginBottom: "0.3rem" }}>
              {t("evac.hint.title")}
            </p>
            <p style={{ fontSize: "0.8rem", color: "var(--muted)", margin: 0 }}>{t("evac.hint.desc")}</p>
          </div>
        </div>
      )}

      {(loading || error || routeInfo) && (
        <div style={{ position: "absolute", bottom: 12, right: 12, zIndex: 1000, background: "rgba(13,13,15,0.9)", backdropFilter: "blur(8px)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 12, padding: "0.75rem 1rem", fontFamily: "'JetBrains Mono',monospace", fontSize: "0.72rem" }}>
          {loading && <span style={{ color: "#8f96a9" }}>{t("evac.calc")}</span>}
          {error   && <span style={{ color: "#ff9dac" }}>{error}</span>}
          {routeInfo && !loading && (
            <div style={{ display: "flex", gap: "1rem" }}>
              <span style={{ color: "var(--cyan,#00cfff)" }}>{metersToKm(routeInfo.distance)}</span>
              <span style={{ color: "#8fe9ff" }}>{secToMin(routeInfo.duration)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
