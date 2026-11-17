import { useMemo, useEffect, useState } from "react";
import { MapContainer, CircleMarker, Marker, Pane, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import { useApp, useT } from "../lib/appContext";
import InvalidateMapSize from "./InvalidateMapSize";
import BaseTiles from "./BaseTiles";
import floodProneZones from "../data/floodProneZones.json";
import postRivers from "../data/postRivers.json";
import { activeFloodPoints } from "../lib/floodRoads";
import { ActiveFloodAreas, AREA_COLOR, StationMarkers } from "./mapLayers";
import WeatherLayer, { WeatherPatterns, weatherKey } from "./WeatherLayer";
import { byWilayahKey } from "../lib/wilayahWeather";
import { formatChance, proneAreaChances } from "../lib/dashboardHelpers";


// Single muted slate-blue for ALL historical BNPB flood-prone points so the
// overlay reads as a uniform "background context" layer rather than a second
// system of markers. River association is still surfaced in each point's
// popup — colour just isn't doing duplicate work anymore. This was the fix
// to the 10-hue overload that made the map feel cluttered.
const PRONE_COLOR = "#6b8aa3";
// A kecamatan the daily model puts at Waspada today: its flood-prone points and label turn amber.
const PRONE_WATCH_COLOR = "#e0a400";

// The % label of a kecamatan's flood-prone areas (a small chip, cached per text + level).
const chipIcons = {};
function chanceChip(text, watch) {
  const key = `${text}|${watch}`;
  return (chipIcons[key] ??= L.divIcon({
    className: `chance-chip${watch ? " is-watch" : ""}`,
    html: `<span>${text}</span>`,
    iconSize: null,
  }));
}

function proneAccentColor(rivers) {
  // Accent only used inside the popup (river name line) — not on the dot.
  return rivers?.length > 0 ? "#8aa8c4" : "#8f96a9";
}

function titleCase(s) {
  return (s || "").toLowerCase().split(" ").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}

const WEATHER_KEY = "deflood.homeMapWeather";

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
// weatherWilayah: the backend's OpenWeather reading per kota (riskData.openweatherWilayah),
// the same data as the "Weather now by area" cards; onWeatherPick(kota) opens those cards.
// dailyModel: riskData.dailyModel; its per-kecamatan chance labels the flood-prone areas.
export default function FloodMap({ riskScore = 45, stations = [], rainfall = 0, weatherWilayah = {}, onWeatherPick, pickedWilayah = null,
                                   dailyModel = null }) {
  const t = useT();
  const { theme, lang } = useApp();
  const isId = lang === "id";
  // Flood-prone areas with today's chance: on by default (small dots and chips under the posts).
  const [showProne, setShowProne] = useState(true);
  // Weather per wilayah: on by default, the choice is remembered.
  const [showWeather, setShowWeather] = useState(() => {
    try { return localStorage.getItem(WEATHER_KEY) !== "0"; } catch { return true; }
  });
  const toggleWeather = () => setShowWeather((on) => {
    try { localStorage.setItem(WEATHER_KEY, on ? "0" : "1"); } catch { /* private mode */ }
    return !on;
  });
  const weather = useMemo(() => byWilayahKey(weatherWilayah), [weatherWilayah]);
  // Desktop: the legend floats on the map and can be folded. Phones: CSS puts
  // it under the map, always open, so it neither covers the map nor hides.
  const [legendOpen, setLegendOpen] = useState(true);

  // Only plot stations that have validated Jakarta coordinates.
  const mappedStations = useMemo(
    () => stations.filter(s => s.lat != null && s.lon != null),
    [stations],
  );
  const hasRealStations = mappedStations.length > 0;
  const pronePoints = floodProneZones.points ?? [];
  // Per kecamatan: today's chance from the daily model, its points and their centre (null without the model).
  const proneAreas = useMemo(() => proneAreaChances(pronePoints, dailyModel), [pronePoints, dailyModel]);
  const areaByPoint = useMemo(() => {
    const out = {};
    for (const a of proneAreas ?? []) for (const p of a.points) out[`${p.lat},${p.lon}`] = a;
    return out;
  }, [proneAreas]);
  // Same rule as the evacuation map: points along the river stretch of a post at Siaga, or all in heavy rain.
  const floodPoints = useMemo(
    () => activeFloodPoints(pronePoints, stations, rainfall, postRivers),
    [pronePoints, stations, rainfall],
  );

  return (
    <div className="flood-map-wrap" style={{ position: "relative", flex: 1, minHeight: "clamp(340px, 58vh, 600px)" }}>
      {showWeather && <WeatherPatterns weather={weather} />}
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
        {/* Grey basemap only: the weather colours each kota, a street map underneath was too busy. */}
        <BaseTiles theme={theme} variant="canvas" />
        <FitJakarta />
        <InvalidateMapSize />

        {showWeather && <WeatherLayer weather={weather} lang={lang} theme={theme} onPick={onWeatherPick} picked={pickedWilayah} />}

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
        {showProne && pronePoints.map((p, i) => {
          const area = areaByPoint[`${p.lat},${p.lon}`];
          const watch = area?.level && area.level !== "SAFE";
          return (
          <CircleMarker
            key={`p-${i}`}
            center={[p.lat, p.lon]}
            radius={area ? 3.5 : 2}
            pathOptions={{
              fillColor: watch ? PRONE_WATCH_COLOR : PRONE_COLOR,
              fillOpacity: area ? 0.7 : 0.42,
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
                {area && (
                  <p style={{ fontSize: 12, fontWeight: 700, color: watch ? "#9a6b00" : "var(--text)", margin: "4px 0" }}>
                    {isId
                      ? `Peluang banjir hari ini di Kec. ${area.name}: ${formatChance(area.probability)}`
                      : `Flood chance today in ${area.name}: ${formatChance(area.probability)}`}
                  </p>
                )}
                <p style={{ fontSize: 10, color: "var(--muted-2)", margin: 0, marginTop: 4 }}>
                  ● {isId ? "Titik rawan historis (BNPB)" : "Historical flood-prone point (BNPB)"}
                </p>
              </div>
            </Popup>
          </CircleMarker>
          );
        })}

        {/* Today's chance per kecamatan, one chip at the centre of its flood-prone points. Its own pane
            sits under the posts (460), so a chip never covers a post. */}
        {showProne && proneAreas && (
          <Pane name="prone-chance" style={{ zIndex: 455 }}>
            {proneAreas.map((a) => {
              const watch = a.level && a.level !== "SAFE";
              return (
                <Marker key={a.slug} position={[a.lat, a.lon]} icon={chanceChip(formatChance(a.probability), watch)}
                        pane="prone-chance" keyboard={false}
                        title={isId ? `Kec. ${a.name}: peluang banjir hari ini ${formatChance(a.probability)}`
                                    : `${a.name}: flood chance today ${formatChance(a.probability)}`}>
                  <Popup autoPan autoPanPaddingTopLeft={[8, 64]} autoPanPaddingBottomRight={[8, 8]}>
                    <div style={{ minWidth: 200 }}>
                      <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>
                        {isId ? `Kec. ${a.name}` : a.name} · {formatChance(a.probability)}
                      </p>
                      <p style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                        {isId
                          ? `Peluang BPBD mencatat banjir di kecamatan ini hari ini, dari model harian (hujan satelit sampai ${dailyModel?.rain_through ?? "-"}).`
                          : `Chance that BPBD records a flood in this kecamatan today, from the daily model (satellite rain up to ${dailyModel?.rain_through ?? "-"}).`}
                      </p>
                      <p style={{ fontSize: 11, color: "var(--muted)", margin: 0 }}>
                        {isId
                          ? `${a.points.length} titik rawan banjir di kecamatan ini.`
                          : `${a.points.length} flood-prone point${a.points.length > 1 ? "s" : ""} in this kecamatan.`}
                      </p>
                    </div>
                  </Popup>
                </Marker>
              );
            })}
          </Pane>
        )}

        {/* Active flood-prone areas, then the posts on top (shared with the evacuation map) */}
        <ActiveFloodAreas points={floodPoints} />
        <StationMarkers stations={mappedStations} floodPoints={floodPoints} />
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
              ? "Tampilkan/sembunyikan titik rawan banjir (BPBD/BNPB) dengan peluang banjir hari ini di kecamatannya (model harian)"
              : "Show/hide flood-prone points (BPBD/BNPB) with today's flood chance in their kecamatan (daily model)"}
          >
            <span style={{
              width: 9, height: 9, borderRadius: 2,
              border: `1.5px solid ${showProne ? PRONE_COLOR : "var(--line-2)"}`,
              background: showProne ? PRONE_COLOR : "transparent",
              flexShrink: 0,
            }} />
            <span style={{ flex: 1, textAlign: "left" }}>
              {proneAreas
                ? (isId ? "Area rawan banjir · peluang hari ini" : "Flood-prone areas · today's chance")
                : (isId ? "Daerah pernah banjir" : "Previously flooded areas")}
            </span>
          </button>
          <button
            type="button"
            onClick={toggleWeather}
            aria-pressed={showWeather}
            style={{
              display: "flex", alignItems: "center", gap: 6, width: "100%", minHeight: 32,
              background: "transparent", border: "none", padding: "4px 0", cursor: "pointer",
              color: "var(--muted)", fontSize: "0.78rem",
            }}
            title={isId
              ? "Awan dan hujan saat ini per wilayah (OpenWeather, satu titik per kota). Ketuk kartu wilayah untuk detail di bawah peta."
              : "Current cloud and rain per area (OpenWeather, one point per city). Tap an area's card for details under the map."}
          >
            <span style={{
              width: 9, height: 9, borderRadius: 2,
              border: `1.5px solid ${showWeather ? "#64748b" : "var(--line-2)"}`,
              background: showWeather ? "#64748b" : "transparent",
              flexShrink: 0,
            }} />
            <span style={{ flex: 1, textAlign: "left" }}>
              {isId ? "Cuaca per wilayah" : "Weather per area"}
            </span>
          </button>
          {showWeather && (
            <div className="wx-key">
              {/* Only the states on the map now; tap a kota's card for its details */}
              {weatherKey(weather, lang, theme === "dark").map(({ id, name, color }) => (
                <span key={id}><i style={{ background: color }} />{name}</span>
              ))}
            </div>
          )}
        </div>
        </>}
      </div>
    </div>
  );
}
