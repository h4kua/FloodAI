import { useMemo, useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";

const TILE_DARK  = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_LIGHT = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR  = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

// Tight DKI Jakarta administrative boundary.
const JAKARTA_BOUNDS = [[-6.375, 106.695], [-6.095, 107.005]];

// Geographic reference points for district labels — NOT data sources.
// Shown as faint background shapes only when real station data is unavailable.
const DISTRICT_REFS = [
  { id: "selatan", name: "Jakarta Selatan", lat: -6.261, lng: 106.810 },
  { id: "utara",   name: "Jakarta Utara",   lat: -6.121, lng: 106.900 },
  { id: "timur",   name: "Jakarta Timur",   lat: -6.217, lng: 106.952 },
  { id: "barat",   name: "Jakarta Barat",   lat: -6.182, lng: 106.751 },
  { id: "pusat",   name: "Jakarta Pusat",   lat: -6.186, lng: 106.834 },
];

function stationColor(ratio) {
  if (ratio >= 1.0)  return "#ff3d5a";
  if (ratio >= 0.75) return "#f97316";
  if (ratio >= 0.50) return "#f5a623";
  return "#00e5a0";
}

// Fits the map to DKI Jakarta on mount.
function FitJakarta() {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(JAKARTA_BOUNDS, { padding: [2, 2], animate: false });
  }, [map]);
  return null;
}

// stations: real DSDADKI readings from /predict/realtime-native response.
// riskScore: passed through only for the fallback district tint when no
// station coords are available — NOT used when real stations are shown.
export default function FloodMap({ riskScore = 45, stations = [] }) {
  const t = useT();
  const { theme } = useApp();
  const tileUrl = theme === "light" ? TILE_LIGHT : TILE_DARK;

  // Only plot stations that have validated Jakarta coordinates.
  const mappedStations = useMemo(
    () => stations.filter(s => s.lat != null && s.lon != null),
    [stations],
  );
  const hasRealStations = mappedStations.length > 0;

  return (
    <div style={{ position: "relative", flex: 1, minHeight: "320px" }}>
      <MapContainer
        center={[-6.23, 106.85]}
        zoom={12}
        minZoom={12}
        maxZoom={16}
        maxBounds={JAKARTA_BOUNDS}
        maxBoundsViscosity={1.0}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", minHeight: "320px" }}
      >
        <TileLayer url={tileUrl} attribution={TILE_ATTR} />
        <FitJakarta />

        {/* District reference circles — shown faintly as geographic labels only.
            When real sensor stations are on the map these are barely visible.
            Popup tells the user this is NOT measured per-district data. */}
        {DISTRICT_REFS.map((d) => (
          <CircleMarker
            key={d.id}
            center={[d.lat, d.lng]}
            radius={hasRealStations ? 18 : 28}
            pathOptions={{
              fillColor: "#8f96a9",
              fillOpacity: hasRealStations ? 0.04 : 0.14,
              color: "#8f96a9",
              weight: 1,
              opacity: hasRealStations ? 0.15 : 0.40,
              dashArray: "4 4",
            }}
          >
            <Popup>
              <div style={{ fontFamily: "'Inter', sans-serif", minWidth: 190 }}>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 14 }}>{d.name}</p>
                <p style={{ fontSize: 11, color: "#8f96a9", margin: 0 }}>
                  {t("map.popupEstNote")}
                </p>
              </div>
            </Popup>
          </CircleMarker>
        ))}

        {/* Real DSDADKI sensor station markers.
            Position, color, and popup data all come directly from the sensor
            snapshot — nothing is derived or estimated here. */}
        {mappedStations.map((s, i) => {
          const color  = stationColor(s.ratio);
          const radius = s.ratio >= 0.75 ? 11 : 8;
          return (
            <CircleMarker
              key={i}
              center={[s.lat, s.lon]}
              radius={radius}
              pathOptions={{
                fillColor: color,
                fillOpacity: 0.92,
                color: "#fff",
                weight: 1.5,
                opacity: 0.9,
              }}
            >
              <Popup>
                <div style={{ fontFamily: "'Inter', sans-serif", minWidth: 190 }}>
                  <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{s.nama}</p>
                  <p style={{ fontSize: 12, color, fontWeight: 700, marginBottom: 6 }}>
                    {s.status_siaga} — {Math.round(s.ratio * 100)}% siaga
                  </p>
                  <p style={{ fontSize: 11, color: "#8f96a9", marginBottom: 2 }}>
                    TMA: <strong style={{ color: "var(--text, #e2e8f0)" }}>{s.tinggi_air} cm</strong>
                  </p>
                  <p style={{ fontSize: 11, color: "#8f96a9", marginBottom: 2 }}>
                    {t("map.popupThreshold")}: {s.siaga1} cm
                  </p>
                  <p style={{ fontSize: 10, color: "#6b7280", margin: 0, marginTop: 4 }}>
                    ● {t("map.popupSensorNote")}
                  </p>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>

      <div className="map-legend">
        <p style={{ fontSize: "0.65rem", color: "var(--muted-2)", fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
          {t("legend.title")}
        </p>
        {[
          ["legend.danger",  "#ff3d5a"],
          ["legend.alert",   "#f97316"],
          ["legend.warning", "#f5a623"],
          ["legend.safe",    "#00e5a0"],
        ].map(([key, color]) => (
          <div className="legend-row" key={key}>
            <span className="legend-dot" style={{ background: color }} />
            {t(key)}
          </div>
        ))}
        <div className="legend-row" style={{ marginTop: 4, borderTop: "1px solid rgba(255,255,255,0.07)", paddingTop: 4 }}>
          <span className="legend-dot" style={{ background: "#8f96a9", opacity: 0.45 }} />
          <span style={{ color: "var(--muted-2)", fontSize: "0.62rem" }}>
            {hasRealStations ? t("legend.sensorMarkers") : t("legend.mlEstimate")}
          </span>
        </div>
      </div>
    </div>
  );
}
