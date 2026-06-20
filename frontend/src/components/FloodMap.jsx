import { useMemo, useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";
import floodProneZones from "../data/floodProneZones.json";

const TILE_DARK  = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_LIGHT = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR  = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

// River-coded palette for historically flood-prone points. Mapped from the
// "by_kelurahan" join in river_flood_zones.json so neighbouring points along
// the same river share a colour and form a visual "spine" on the map.
const RIVER_COLORS = {
  "CILIWUNG":                          "#ef4444",
  "CILIWUNG ARAH ISTANA NEGARA":       "#f97316",
  "CILIWUNG ARAH KANAL BANJIR BARAT":  "#fb923c",
  "SUNTER":                            "#3b82f6",
  "KRUKUT":                            "#10b981",
  "PESANGGRAHAN":                      "#a855f7",
  "PESANGGRAHAN & ANGKE":              "#c084fc",
  "ANGKE":                             "#f59e0b",
  "CIPINANG":                          "#eab308",
};
const PRONE_DEFAULT_COLOR = "#64748b";

function proneColor(rivers) {
  const r = rivers?.[0];
  return RIVER_COLORS[r] ?? PRONE_DEFAULT_COLOR;
}

function titleCase(s) {
  return (s || "").toLowerCase().split(" ").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

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
  const { theme, lang } = useApp();
  const isId = lang === "id";
  const tileUrl = theme === "light" ? TILE_LIGHT : TILE_DARK;
  const [showProne, setShowProne] = useState(true);

  // Only plot stations that have validated Jakarta coordinates.
  const mappedStations = useMemo(
    () => stations.filter(s => s.lat != null && s.lon != null),
    [stations],
  );
  const hasRealStations = mappedStations.length > 0;
  const pronePoints = floodProneZones.points ?? [];

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
            <Popup autoPan autoPanPaddingTopLeft={[8, 64]} autoPanPaddingBottomRight={[8, 8]}>
              <div style={{ fontFamily: "'Inter', sans-serif", minWidth: 180 }}>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 14 }}>{d.name}</p>
                <p style={{ fontSize: 11, color: "#8f96a9", margin: 0 }}>
                  {t("map.popupEstNote")}
                </p>
              </div>
            </Popup>
          </CircleMarker>
        ))}

        {/* BNPB historical flood-prone points — bundled reference data.
            154 points joined with river_flood_zones.json (130/154 carry a
            river association) so the layer doubles as a soft "river spine"
            overlay even though no polylines are drawn. Rendered BEFORE
            sensor markers so the live readings sit on top. */}
        {showProne && pronePoints.map((p, i) => (
          <CircleMarker
            key={`p-${i}`}
            center={[p.lat, p.lon]}
            radius={4}
            pathOptions={{
              fillColor: proneColor(p.rivers),
              fillOpacity: 0.55,
              color: proneColor(p.rivers),
              weight: 0.8,
              opacity: 0.75,
            }}
          >
            <Popup autoPan autoPanPaddingTopLeft={[8, 64]} autoPanPaddingBottomRight={[8, 8]}>
              <div style={{ fontFamily: "'Inter', sans-serif", minWidth: 180 }}>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>
                  {titleCase(p.kelurahan)}
                </p>
                <p style={{ fontSize: 11, color: "#8f96a9", marginBottom: 4 }}>
                  {titleCase(p.kecamatan)} · {titleCase((p.wilayah || "").replace("KOTA ADM. ", ""))}
                </p>
                {p.rivers?.length > 0 ? (
                  <p style={{ fontSize: 11, color: proneColor(p.rivers), fontWeight: 600, marginBottom: 4 }}>
                    {isId ? "Sungai" : "River"}: {p.rivers.map(titleCase).join(", ")}
                  </p>
                ) : (
                  <p style={{ fontSize: 10, color: "#8f96a9", fontStyle: "italic", marginBottom: 4 }}>
                    {isId ? "Tidak terkait sungai utama" : "Not tied to a major river"}
                  </p>
                )}
                <p style={{ fontSize: 10, color: "#6b7280", margin: 0, marginTop: 4 }}>
                  ● {isId ? "Titik rawan historis (BNPB)" : "Historical flood-prone point (BNPB)"}
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
              <Popup autoPan autoPanPaddingTopLeft={[8, 64]} autoPanPaddingBottomRight={[8, 8]}>
                <div style={{ fontFamily: "'Inter', sans-serif", minWidth: 180 }}>
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

        {/* Flood-prone overlay toggle + per-river colour key */}
        <div style={{ marginTop: 6, borderTop: "1px solid rgba(255,255,255,0.07)", paddingTop: 6 }}>
          <button
            type="button"
            onClick={() => setShowProne(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 6, width: "100%",
              background: "transparent", border: "none", padding: 0, cursor: "pointer",
              color: "var(--muted-2)", fontFamily: "'JetBrains Mono',monospace",
              fontSize: "0.62rem", letterSpacing: "0.04em",
            }}
            title={isId ? "Toggle titik rawan historis" : "Toggle historical flood-prone points"}
          >
            <span style={{
              width: 10, height: 10, borderRadius: 2,
              border: `1.5px solid ${showProne ? "var(--cyan, #38bdf8)" : "rgba(143,150,169,0.45)"}`,
              background: showProne ? "var(--cyan, #38bdf8)" : "transparent",
              flexShrink: 0,
            }} />
            {isId ? `Titik rawan BNPB (${pronePoints.length})` : `BNPB flood-prone (${pronePoints.length})`}
          </button>
          {showProne && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2px 8px", marginTop: 6 }}>
              {[
                ["Ciliwung",     RIVER_COLORS.CILIWUNG],
                ["Sunter",       RIVER_COLORS.SUNTER],
                ["Krukut",       RIVER_COLORS.KRUKUT],
                ["Pesanggrahan", RIVER_COLORS.PESANGGRAHAN],
                ["Angke",        RIVER_COLORS.ANGKE],
                ["Cipinang",     RIVER_COLORS.CIPINANG],
              ].map(([name, color]) => (
                <div key={name} className="legend-row" style={{ fontSize: "0.58rem" }}>
                  <span className="legend-dot" style={{ background: color, width: 6, height: 6 }} />
                  {name}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
