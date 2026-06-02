import { useState, useEffect, useCallback } from "react";
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, useMap } from "react-leaflet";

const TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

export const ORIGINS = [
  { id: "barat",   name: "Jakarta Barat",   lat: -6.182, lng: 106.751 },
  { id: "utara",   name: "Jakarta Utara",   lat: -6.121, lng: 106.900 },
  { id: "timur",   name: "Jakarta Timur",   lat: -6.217, lng: 106.952 },
  { id: "pusat",   name: "Jakarta Pusat",   lat: -6.186, lng: 106.834 },
  { id: "selatan", name: "Jakarta Selatan", lat: -6.261, lng: 106.810 },
];

// Verified safe shelters / higher-ground destinations
export const DESTINATIONS = [
  { id: "kemayoran", name: "Kemayoran (Shelter)",     lat: -6.1528, lng: 106.8559 },
  { id: "ancol",     name: "Ancol (Pos Evakuasi)",    lat: -6.1246, lng: 106.8350 },
  { id: "tmii",      name: "TMII (Pos Darurat)",      lat: -6.2726, lng: 106.9020 },
  { id: "gbk",       name: "GBK Senayan (Shelter)",   lat: -6.2181, lng: 106.8022 },
  { id: "cipete",    name: "Cipete (Pos Aman)",       lat: -6.2824, lng: 106.8043 },
];

function FitBounds({ positions }) {
  const map = useMap();
  useEffect(() => {
    if (positions && positions.length >= 2) {
      try {
        map.fitBounds(positions.map((p) => [p[0], p[1]]), { padding: [48, 48] });
      } catch (_) {}
    }
  }, [map, positions]);
  return null;
}

function metersToKm(m) {
  return m >= 1000 ? (m / 1000).toFixed(1) + " km" : Math.round(m) + " m";
}
function secToMin(s) {
  const m = Math.round(s / 60);
  return m < 60 ? m + " menit" : Math.floor(m / 60) + " j " + (m % 60) + " m";
}

export default function EvacuationMap({ originId = "barat", destId = "kemayoran" }) {
  const [route, setRoute] = useState(null);
  const [routeInfo, setRouteInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const origin = ORIGINS.find((o) => o.id === originId) ?? ORIGINS[0];
  const dest   = DESTINATIONS.find((d) => d.id === destId) ?? DESTINATIONS[0];

  const fetchRoute = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRoute(null);
    setRouteInfo(null);
    try {
      const url = `https://router.project-osrm.org/route/v1/driving/${origin.lng},${origin.lat};${dest.lng},${dest.lat}?overview=full&geometries=geojson`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("OSRM error " + res.status);
      const data = await res.json();
      if (!data.routes?.length) throw new Error("No route found");
      const coords = data.routes[0].geometry.coordinates.map(([lng, lat]) => [lat, lng]);
      setRoute(coords);
      setRouteInfo({
        distance: data.routes[0].distance,
        duration: data.routes[0].duration,
      });
    } catch (e) {
      setError("Rute tidak tersedia.");
    } finally {
      setLoading(false);
    }
  }, [origin.lat, origin.lng, dest.lat, dest.lng]);

  useEffect(() => { fetchRoute(); }, [fetchRoute]);

  const center = [-6.2, 106.83];

  return (
    <div style={{ position: "relative", height: "520px" }}>
      <MapContainer
        center={center}
        zoom={11}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "520px", width: "100%" }}
      >
        <TileLayer url={TILE_URL} attribution={TILE_ATTR} />

        {route && (
          <>
            <Polyline
              positions={route}
              pathOptions={{ color: "#00cfff", weight: 5, opacity: 0.85, lineJoin: "round" }}
            />
            <FitBounds positions={route} />
          </>
        )}

        {/* Origin marker */}
        <CircleMarker
          center={[origin.lat, origin.lng]}
          radius={12}
          pathOptions={{ fillColor: "#ff3d5a", fillOpacity: 0.9, color: "#ff3d5a", weight: 2 }}
        >
          <Popup>
            <div style={{ fontFamily: "'Inter',sans-serif" }}>
              <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{origin.name}</p>
              <p style={{ fontSize: 11, color: "#ff9dac", margin: 0 }}>Titik keberangkatan</p>
            </div>
          </Popup>
        </CircleMarker>

        {/* Destination marker */}
        <CircleMarker
          center={[dest.lat, dest.lng]}
          radius={12}
          pathOptions={{ fillColor: "#00e5a0", fillOpacity: 0.9, color: "#00e5a0", weight: 2 }}
        >
          <Popup>
            <div style={{ fontFamily: "'Inter',sans-serif" }}>
              <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{dest.name}</p>
              <p style={{ fontSize: 11, color: "#8cffd8", margin: 0 }}>Titik evakuasi aman</p>
              {routeInfo && (
                <p style={{ fontSize: 11, color: "#8f96a9", marginTop: 4 }}>
                  {metersToKm(routeInfo.distance)} · {secToMin(routeInfo.duration)}
                </p>
              )}
            </div>
          </Popup>
        </CircleMarker>
      </MapContainer>

      {/* Route info overlay */}
      {(loading || error || routeInfo) && (
        <div style={{
          position: "absolute", bottom: 12, right: 12, zIndex: 1000,
          background: "rgba(13,13,15,0.9)", backdropFilter: "blur(8px)",
          border: "1px solid rgba(255,255,255,0.07)", borderRadius: 12,
          padding: "0.75rem 1rem",
          fontFamily: "'JetBrains Mono',monospace", fontSize: "0.72rem",
        }}>
          {loading && <span style={{ color: "#8f96a9" }}>Menghitung rute...</span>}
          {error   && <span style={{ color: "#ff9dac" }}>Rute tidak tersedia</span>}
          {routeInfo && !loading && (
            <div style={{ display: "flex", gap: "1rem" }}>
              <span style={{ color: "#00cfff" }}>{metersToKm(routeInfo.distance)}</span>
              <span style={{ color: "#8fe9ff" }}>{secToMin(routeInfo.duration)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
