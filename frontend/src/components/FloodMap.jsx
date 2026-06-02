import { useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";

const TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';
const JAKARTA_CENTER = [-6.2088, 106.8456];

// Historical flood risk distribution across Jakarta wilayah
// Barat & Utara are lowest elevation, most flood-prone
const DISTRICT_OFFSETS = [
  { id: "barat",   name: "Jakarta Barat",   lat: -6.182, lng: 106.751, bias: +12 },
  { id: "utara",   name: "Jakarta Utara",   lat: -6.121, lng: 106.900, bias: +6  },
  { id: "timur",   name: "Jakarta Timur",   lat: -6.217, lng: 106.952, bias: +2  },
  { id: "pusat",   name: "Jakarta Pusat",   lat: -6.186, lng: 106.834, bias: -10 },
  { id: "selatan", name: "Jakarta Selatan", lat: -6.261, lng: 106.810, bias: -18 },
];

function scoreToColor(score) {
  if (score >= 80) return "#ff3d5a";
  if (score >= 60) return "#f97316";
  if (score >= 40) return "#f5a623";
  return "#00e5a0";
}

function scoreToLabel(score) {
  if (score >= 80) return "BAHAYA";
  if (score >= 60) return "SIAGA";
  if (score >= 40) return "WASPADA";
  return "AMAN";
}

export default function FloodMap({ riskScore = 45, level = "waspada" }) {
  const districts = useMemo(() => {
    return DISTRICT_OFFSETS.map((d) => {
      const raw = Math.max(5, Math.min(97, riskScore + d.bias));
      return { ...d, score: Math.round(raw) };
    });
  }, [riskScore]);

  return (
    <div style={{ position: "relative", height: "380px" }}>
      <MapContainer
        center={JAKARTA_CENTER}
        zoom={11}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "380px", width: "100%" }}
      >
        <TileLayer url={TILE_URL} attribution={TILE_ATTR} />

        {districts.map((d) => {
          const color = scoreToColor(d.score);
          const radius = 14 + (d.score / 100) * 20;
          return (
            <CircleMarker
              key={d.id}
              center={[d.lat, d.lng]}
              radius={radius}
              pathOptions={{
                fillColor: color,
                fillOpacity: 0.28,
                color: color,
                weight: 2,
                opacity: 0.9,
              }}
            >
              <Popup>
                <div style={{ fontFamily: "'Inter', sans-serif", minWidth: 160 }}>
                  <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 14 }}>{d.name}</p>
                  <p style={{ fontSize: 12, color: color, fontWeight: 700, marginBottom: 4 }}>
                    {scoreToLabel(d.score)} — {d.score}%
                  </p>
                  <p style={{ fontSize: 11, color: "#8f96a9", margin: 0 }}>
                    Skor risiko banjir berdasarkan model XGBoost + data cuaca realtime.
                  </p>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>

      {/* Legend overlay */}
      <div className="map-legend">
        <p style={{ fontSize: "0.65rem", color: "#5a6277", fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 4 }}>
          Risiko Banjir
        </p>
        {[
          { label: "Bahaya  ≥80%", color: "#ff3d5a" },
          { label: "Siaga   ≥60%", color: "#f97316" },
          { label: "Waspada ≥40%", color: "#f5a623" },
          { label: "Aman    <40%", color: "#00e5a0" },
        ].map((r) => (
          <div className="legend-row" key={r.label}>
            <span className="legend-dot" style={{ background: r.color }} />
            {r.label}
          </div>
        ))}
        <p style={{ fontSize: "0.6rem", color: "#3d4558", fontFamily: "'JetBrains Mono',monospace", marginTop: 4 }}>
          Klik wilayah untuk detail
        </p>
      </div>
    </div>
  );
}
