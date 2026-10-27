/* ── Map layers shared by the water-level map and the evacuation map ──────
   Both maps draw the monitoring posts and the active flood-prone areas with
   these components, so the same post has the same colour on both, and every
   red area names the post that made it active.
*/
import { Circle, CircleMarker, Popup } from "react-leaflet";
import { useApp } from "../lib/appContext";
import { RISK_RADIUS_M } from "../lib/floodRoads";
import { postClass } from "../lib/dashboardHelpers";

export const AREA_COLOR = "#c8102e";

// Post colour by its ratio to Siaga 1 (same bands as the map legend).
const POST_COLOR = { s1: "#c8102e", s2: "#c2410c", wsp: "#e0a400", ok: "#15803d" };
/** Marker colour from the post's own DSDA band (ratio only as a fallback). */
export const stationColor = (station) => POST_COLOR[postClass(station)];

const titleCase = (s) => (s || "").toLowerCase().split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
const siagaWord = (status) => (status || "").replace(/^Status\s*:\s*/i, "");
const popupPad = { autoPan: true, autoPanPaddingTopLeft: [8, 64], autoPanPaddingBottomRight: [8, 8] };

/** Monitoring posts with validated coordinates, coloured by their DSDA band. */
export function StationMarkers({ stations = [], small = false }) {
  const { theme, lang } = useApp();
  const isId = lang === "id";
  return stations.filter((s) => s.lat != null && s.lon != null).map((s) => {
    const cls = postClass(s);
    const color = POST_COLOR[cls];
    const radius = (cls === "s1" || cls === "s2" ? 11 : 8) - (small ? 2 : 0);
    return (
      <CircleMarker
        key={`st-${s.nama}`}
        center={[s.lat, s.lon]}
        radius={radius}
        pathOptions={{
          fillColor: color,
          fillOpacity: 0.95,
          // Dark outline on the light basemap (pale amber vanishes on grey
          // otherwise); white outline on the dark basemap.
          color: theme === "dark" ? "#ffffff" : "#15171a",
          weight: 1.5,
          opacity: 0.9,
        }}
      >
        <Popup {...popupPad}>
          <div style={{ minWidth: 180 }}>
            <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>{s.nama}</p>
            <p style={{ fontSize: 12, color, fontWeight: 700, marginBottom: 4 }}>{s.status_siaga}</p>
            <p style={{ fontSize: 12, color: "var(--muted)", margin: 0 }}>
              {isId
                ? `Air ${Math.round(s.ratio * 100)}% dari batas siaga (${Math.round(s.tinggi_air)} cm)`
                : `Water at ${Math.round(s.ratio * 100)}% of the alert limit (${Math.round(s.tinggi_air)} cm)`}
            </p>
          </div>
        </Popup>
      </CircleMarker>
    );
  });
}

/** Active flood-prone areas (500 m), each naming the post or rain that activated it. */
export function ActiveFloodAreas({ points = [] }) {
  const { lang } = useApp();
  const isId = lang === "id";
  return points.map((p, i) => {
    const posts = (p.causes || []).map((s) => `${s.nama} (${siagaWord(s.status_siaga)})`).join(", ");
    return (
      <Circle key={`fa-${i}`} center={[p.lat, p.lon]} radius={RISK_RADIUS_M}
        pathOptions={{ color: AREA_COLOR, weight: 1, opacity: 0.35, fillColor: AREA_COLOR, fillOpacity: 0.1 }}
      >
        <Popup {...popupPad}>
          <div style={{ minWidth: 200 }}>
            <p style={{ fontWeight: 700, marginBottom: 4, fontSize: 13 }}>
              {p.reason === "post"
                ? (isId ? `Sekitar pos ${p.causes[0].nama}` : `Around post ${p.causes[0].nama}`)
                : `${isId ? "Area rawan banjir" : "Flood-prone area"} · ${titleCase(p.kelurahan)}`}
            </p>
            {p.rivers?.length > 0 && (
              <p style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                {isId ? "Sungai" : "River"}: {p.rivers.map(titleCase).join(", ")}
              </p>
            )}
            <p style={{ fontSize: 12, color: AREA_COLOR, fontWeight: 600, margin: 0 }}>
              {p.reason === "rain"
                ? (isId ? "Aktif karena hujan deras" : "Active because of heavy rain")
                : (isId ? `Aktif karena pos ${posts}` : `Active because of post ${posts}`)}
            </p>
          </div>
        </Popup>
      </Circle>
    );
  });
}
