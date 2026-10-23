import { useMemo, useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";
import InvalidateMapSize from "./InvalidateMapSize";
import floodProneZones from "../data/floodProneZones.json";

const TILE_DARK  = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
const TILE_LIGHT = "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
const TILE_ATTR  = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>';

// Single muted slate-blue for ALL historical BNPB flood-prone points so the
// overlay reads as a uniform "background context" layer rather than a second
// system of markers. River association is still surfaced in each point's
// popup — colour just isn't doing duplicate work anymore. This was the fix
// to the 10-hue overload that made the map feel cluttered.
const PRONE_COLOR = "#6b8aa3";

function proneAccentColor(rivers) {
  // Accent only used inside the popup (river name line) — not on the dot.
  return rivers?.length > 0 ? "#8aa8c4" : "#8f96a9";
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
  if (ratio >= 1.0)  return "#c8102e";
  if (ratio >= 0.75) return "#d9530f";
  if (ratio >= 0.50) return "#e0a400";
  return "#15803d";
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
    <div style={{ position: "relative", flex: 1, minHeight: "clamp(280px, 45vh, 460px)" }}>
      <MapContainer
        center={[-6.23, 106.85]}
        zoom={12}
        minZoom={12}
        maxZoom={16}
        maxBounds={JAKARTA_BOUNDS}
        maxBoundsViscosity={1.0}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", minHeight: "clamp(280px, 45vh, 460px)" }}
      >
        <TileLayer url={tileUrl} attribution={TILE_ATTR} />
        <FitJakarta />
        <InvalidateMapSize />

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
              color: "var(--muted)",
              weight: 1,
              opacity: hasRealStations ? 0.15 : 0.40,
              dashArray: "4 4",
            }}
          >
            <Popup autoPan autoPanPaddingTopLeft={[8, 64]} autoPanPaddingBottomRight={[8, 8]}>
              <div style={{ minWidth: 180 }}>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 14 }}>{d.name}</p>
                <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
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
            radius={2}
            pathOptions={{
              fillColor: PRONE_COLOR,
              fillOpacity: 0.42,
              weight: 0,        // no border — sensor markers have a white stroke, BNPB dots don't
              opacity: 0,
            }}
          >
            <Popup autoPan autoPanPaddingTopLeft={[8, 64]} autoPanPaddingBottomRight={[8, 8]}>
              <div style={{ minWidth: 180 }}>
                <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>
                  {titleCase(p.kelurahan)}
                </p>
                <p style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                  {titleCase(p.kecamatan)} · {titleCase((p.wilayah || "").replace("KOTA ADM. ", ""))}
                </p>
                {p.rivers?.length > 0 ? (
                  <p style={{ fontSize: 11, color: proneAccentColor(p.rivers), fontWeight: 600, marginBottom: 4 }}>
                    {isId ? "Sungai" : "River"}: {p.rivers.map(titleCase).join(", ")}
                  </p>
                ) : (
                  <p style={{ fontSize: 10, color: "var(--muted)", fontStyle: "italic", marginBottom: 4 }}>
                    {isId ? "Tidak terkait sungai utama" : "Not tied to a major river"}
                  </p>
                )}
                <p style={{ fontSize: 10, color: "var(--muted-2)", margin: 0, marginTop: 4 }}>
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
                <div style={{ minWidth: 180 }}>
                  <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{s.nama}</p>
                  <p style={{ fontSize: 12, color, fontWeight: 700, marginBottom: 4 }}>
                    {s.status_siaga}
                  </p>
                  <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
                    {isId
                      ? `Air ${Math.round(s.ratio * 100)}% dari batas siaga (${s.tinggi_air} cm)`
                      : `Water at ${Math.round(s.ratio * 100)}% of the alert limit (${s.tinggi_air} cm)`}
                  </p>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>

      <div className="map-legend">
        <p style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text)", marginBottom: 4 }}>
          {t("legend.title")}
        </p>
        {[
          ["legend.danger",  "#c8102e"],
          ["legend.alert",   "#d9530f"],
          ["legend.warning", "#e0a400"],
          ["legend.safe",    "#15803d"],
        ].map(([key, color]) => (
          <div className="legend-row" key={key}>
            <span className="legend-dot" style={{ background: color }} />
            {t(key)}
          </div>
        ))}
        {/* Flood-prone overlay toggle — single compact line, no second color key */}
        <div style={{ marginTop: 5, borderTop: "1px solid var(--line)", paddingTop: 5 }}>
          <button
            type="button"
            onClick={() => setShowProne(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 6, width: "100%",
              background: "transparent", border: "none", padding: 0, cursor: "pointer",
              color: "var(--muted)", fontSize: "0.78rem",
            }}
            title={isId
              ? "Tampilkan/sembunyikan daerah yang pernah banjir (data BNPB)"
              : "Show/hide areas that have flooded before (BNPB data)"}
          >
            <span style={{
              width: 9, height: 9, borderRadius: 2,
              border: `1.5px solid ${showProne ? PRONE_COLOR : "var(--line-2)"}`,
              background: showProne ? PRONE_COLOR : "transparent",
              flexShrink: 0,
            }} />
            <span style={{ flex: 1, textAlign: "left" }}>
              {isId ? "Daerah pernah banjir" : "Previously flooded areas"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
