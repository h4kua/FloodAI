import { useMemo, useEffect, useState } from "react";
import { MapContainer, CircleMarker, Popup, useMap } from "react-leaflet";
import { useApp, useT } from "../lib/appContext";
import InvalidateMapSize from "./InvalidateMapSize";
import BaseTiles from "./BaseTiles";
import floodProneZones from "../data/floodProneZones.json";
import { activeFloodPoints } from "../lib/floodRoads";
import { ActiveFloodAreas, AREA_COLOR, StationMarkers } from "./mapLayers";


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
export default function FloodMap({ riskScore = 45, stations = [], rainfall = 0 }) {
  const t = useT();
  const { theme, lang } = useApp();
  const isId = lang === "id";
  const [showProne, setShowProne] = useState(false); // off by default — it buries the post markers
  // On phones the open legend covers a third of the map, so it starts folded.
  const [legendOpen, setLegendOpen] = useState(() => typeof window === "undefined" || window.innerWidth > 640);

  // Only plot stations that have validated Jakarta coordinates.
  const mappedStations = useMemo(
    () => stations.filter(s => s.lat != null && s.lon != null),
    [stations],
  );
  const hasRealStations = mappedStations.length > 0;
  const pronePoints = floodProneZones.points ?? [];
  // Same rule as the evacuation map: points on a river whose post is at Siaga, or all in heavy rain.
  const floodPoints = useMemo(
    () => activeFloodPoints(pronePoints, stations, rainfall),
    [pronePoints, stations, rainfall],
  );

  return (
    <div style={{ position: "relative", flex: 1, minHeight: "clamp(340px, 58vh, 600px)" }}>
      <MapContainer
        center={[-6.23, 106.85]}
        zoom={12}
        minZoom={12}
        maxZoom={16}
        maxBounds={JAKARTA_BOUNDS}
        maxBoundsViscosity={1.0}
        zoomControl={true}
        scrollWheelZoom={true}
        style={{ height: "100%", width: "100%", minHeight: "clamp(340px, 58vh, 600px)" }}
      >
        <BaseTiles theme={theme} />
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

        {/* Active flood-prone areas, then the posts on top (shared with the evacuation map) */}
        <ActiveFloodAreas points={floodPoints} />
        <StationMarkers stations={mappedStations} />
      </MapContainer>

      <div className={`map-legend${legendOpen ? "" : " is-collapsed"}`}>
        <button
          type="button"
          className="map-legend-toggle"
          aria-expanded={legendOpen}
          onClick={() => setLegendOpen((open) => !open)}
        >
          <span>{t("legend.title")}</span>
          <span aria-hidden="true" className="map-legend-chevron">▾</span>
        </button>
        {legendOpen && <>
        {[
          ["legend.danger",  "#c8102e"],
          ["legend.alert",   "#c2410c"],
          ["legend.warning", "#e0a400"],
          ["legend.safe",    "#15803d"],
        ].map(([key, color]) => (
          <div className="legend-row" key={key}>
            <span className="legend-dot" style={{ background: color }} />
            {t(key)}
          </div>
        ))}
        <div className="legend-row">
          <span className="legend-dot" style={{ background: "rgba(200, 16, 46, 0.12)", border: `1.5px solid ${AREA_COLOR}` }} />
          {floodPoints.length > 0
            ? (isId ? `Area rawan aktif (${floodPoints.length})` : `Active flood-prone areas (${floodPoints.length})`)
            : (isId ? "Tidak ada area rawan aktif" : "No active flood-prone area")}
        </div>
        {/* Flood-prone overlay toggle — single compact line, no second color key */}
        <div style={{ marginTop: 5, borderTop: "1px solid var(--line)", paddingTop: 5 }}>
          <button
            type="button"
            onClick={() => setShowProne(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 6, width: "100%", minHeight: 32,
              background: "transparent", border: "none", padding: "4px 0", cursor: "pointer",
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
        </>}
      </div>
    </div>
  );
}
