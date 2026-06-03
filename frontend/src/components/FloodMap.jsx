import { useMemo, useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";

const TILE_DARK  = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_LIGHT = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR  = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

// DKI Jakarta administrative boundary — used for both fitBounds and panning lock
const JAKARTA_BOUNDS = [[-6.385, 106.685], [-6.085, 107.025]];

// Bias derived from BPBD flood event frequency 2024-2026 (aggregated per kotamadya)
// Aligns with BASE_ZONES in Home.jsx to ensure map and zone table are consistent
const DISTRICT_OFFSETS = [
  { id: "selatan", name: "Jakarta Selatan", lat: -6.261, lng: 106.810, bias: +18 },
  { id: "utara",   name: "Jakarta Utara",   lat: -6.121, lng: 106.900, bias: +6  },
  { id: "timur",   name: "Jakarta Timur",   lat: -6.217, lng: 106.952, bias: +5  },
  { id: "barat",   name: "Jakarta Barat",   lat: -6.182, lng: 106.751, bias: +3  },
  { id: "pusat",   name: "Jakarta Pusat",   lat: -6.186, lng: 106.834, bias: -4  },
];

function scoreToColor(score) {
  if (score >= 80) return "#ff3d5a";
  if (score >= 60) return "#f97316";
  if (score >= 40) return "#f5a623";
  return "#00e5a0";
}

function scoreToLabelKey(score) {
  if (score >= 80) return "risk.BAHAYA";
  if (score >= 60) return "risk.SIAGA";
  if (score >= 40) return "risk.WASPADA";
  return "risk.AMAN";
}

// Fits the map to DKI Jakarta bounds on first render, regardless of container size
function FitJakarta() {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(JAKARTA_BOUNDS, { padding: [8, 8], animate: false });
  }, [map]);
  return null;
}

export default function FloodMap({ riskScore = 45 }) {
  const t = useT();
  const { theme } = useApp();
  const tileUrl = theme === "light" ? TILE_LIGHT : TILE_DARK;

  const districts = useMemo(() => {
    return DISTRICT_OFFSETS.map((d) => {
      const raw = Math.max(5, Math.min(97, riskScore + d.bias));
      return { ...d, score: Math.round(raw) };
    });
  }, [riskScore]);

  return (
    <div style={{ position: "relative", flex: 1, minHeight: "320px" }}>
      <MapContainer
        bounds={JAKARTA_BOUNDS}
        boundsOptions={{ padding: [8, 8] }}
        minZoom={11}
        maxZoom={14}
        maxBounds={JAKARTA_BOUNDS}
        maxBoundsViscosity={1.0}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", minHeight: "320px" }}
      >
        <TileLayer url={tileUrl} attribution={TILE_ATTR} />
        <FitJakarta />

        {districts.map((d) => {
          const color = scoreToColor(d.score);
          const radius = 14 + (d.score / 100) * 20;
          return (
            <CircleMarker
              key={d.id}
              center={[d.lat, d.lng]}
              radius={radius}
              pathOptions={{ fillColor: color, fillOpacity: 0.28, color, weight: 2, opacity: 0.9 }}
            >
              <Popup>
                <div style={{ fontFamily: "'Inter', sans-serif", minWidth: 160 }}>
                  <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 14 }}>{d.name}</p>
                  <p style={{ fontSize: 12, color, fontWeight: 700, marginBottom: 4 }}>
                    {t(scoreToLabelKey(d.score))} — {d.score}%
                  </p>
                  <p style={{ fontSize: 11, color: "#8f96a9", margin: 0 }}>{t("map.popupNote")}</p>
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
          ["legend.danger", "#ff3d5a"],
          ["legend.alert",  "#f97316"],
          ["legend.warning","#f5a623"],
          ["legend.safe",   "#00e5a0"],
        ].map(([key, color]) => (
          <div className="legend-row" key={key}>
            <span className="legend-dot" style={{ background: color }} />
            {t(key)}
          </div>
        ))}
      </div>
    </div>
  );
}
