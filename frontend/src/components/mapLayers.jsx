/* ── Map layers shared by the water-level map and the evacuation map ──────
   Both maps draw the monitoring posts and the active flood-prone areas with
   these components, so the same post has the same colour on both, and every
   red area names the post that made it active.
*/
import { useEffect, useMemo, useRef, useState } from "react";
import { Circle, CircleMarker, Polyline, Popup } from "react-leaflet";
import { useApp } from "../lib/appContext";
import { RISK_RADIUS_M, areasByPost, riverForPost } from "../lib/floodRoads";
import { postClass } from "../lib/dashboardHelpers";
import postRivers from "../data/postRivers.json";

export const AREA_COLOR = "#c8102e";
// The river of an open post.
const RIVER_COLOR = "#1d4ed8";


// Post colour by its ratio to Siaga 1 (same bands as the map legend).
const POST_COLOR = { s1: "#c8102e", s2: "#c2410c", wsp: "#e0a400", ok: "#15803d" };
/** Marker colour from the post's own DSDA band (ratio only as a fallback). */
export const stationColor = (station) => POST_COLOR[postClass(station)];

const titleCase = (s) => (s || "").toLowerCase().split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
const siagaWord = (status) => (status || "").replace(/^Status\s*:\s*/i, "");
const popupPad = { autoPan: true, autoPanPaddingTopLeft: [8, 64], autoPanPaddingBottomRight: [8, 8] };

/**
 * Monitoring posts with validated coordinates, coloured by their DSDA band.
 * While a post's popup is open, the river it measures is drawn in blue around it
 * (src/data/postRivers.json), and the popup counts the active flood-prone areas
 * (`floodPoints`) the post makes active.
 */
export function StationMarkers({ stations = [], floodPoints = [], small = false }) {
  const { theme, lang } = useApp();
  const isId = lang === "id";
  const [openPost, setOpenPost] = useState(null);
  const openPopup = useRef(null);
  // The river line is added to the popup after it opens, so Leaflet's auto-pan
  // measured a shorter popup and left the top cut off: lay it out and pan again.
  useEffect(() => {
    if (openPost && openPopup.current?.isOpen()) openPopup.current.update();
  }, [openPost]);
  const byPost = useMemo(() => areasByPost(floodPoints), [floodPoints]);
  const placed = stations.filter((s) => s.lat != null && s.lon != null);
  const open = placed.find((s) => s.nama === openPost);
  const openRiver = open ? riverForPost(open, postRivers) : null;

  // A white casing under the blue keeps the river readable on a blue "rain" kota.
  const lines = (openRiver?.lines || []).flatMap((line, i) => [
    <Polyline key={`rv-case-${i}`} positions={line} interactive={false}
      pathOptions={{ color: "#ffffff", weight: 8, opacity: 0.85, lineCap: "round", lineJoin: "round" }} />,
    <Polyline key={`rv-${i}`} positions={line} interactive={false}
      pathOptions={{ color: RIVER_COLOR, weight: 5, opacity: 0.9, lineCap: "round", lineJoin: "round" }} />,
  ]);
  // A post that stands away from the channel (Cipinang Hulu, ~800 m): dashed line to it.
  if (openRiver?.link) {
    lines.push(<Polyline key="rv-link" positions={openRiver.link} interactive={false}
      pathOptions={{ color: RIVER_COLOR, weight: 3, opacity: 0.75, dashArray: "6 6" }} />);
  }

  const markers = placed.map((s) => {
    const cls = postClass(s);
    const color = POST_COLOR[cls];
    const radius = (cls === "s1" || cls === "s2" ? 11 : 8) - (small ? 2 : 0);
    const activated = (byPost.get(s.nama) || []).length;
    const river = s.nama === openPost ? openRiver : null;
    return (
      <CircleMarker
        key={`st-${s.nama}`}
        center={[s.lat, s.lon]}
        radius={radius}
        eventHandlers={{
          popupopen: (e) => { openPopup.current = e.popup; setOpenPost(s.nama); },
          popupclose: () => setOpenPost((cur) => (cur === s.nama ? null : cur)),
        }}
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
              {/* ratio = water / the Siaga 1 (top) limit; say so, a bare "alert limit" read as Siaga 3 */}
              {s.ratio > 0
                ? (isId
                  ? `Air ${Math.round(s.tinggi_air)} cm · ${Math.round(s.ratio * 100)}% dari batas Siaga 1 (${Math.round(s.tinggi_air / s.ratio)} cm)`
                  : `Water ${Math.round(s.tinggi_air)} cm · ${Math.round(s.ratio * 100)}% of the Siaga 1 limit (${Math.round(s.tinggi_air / s.ratio)} cm)`)
                : (isId ? `Air ${Math.round(s.tinggi_air)} cm` : `Water ${Math.round(s.tinggi_air)} cm`)}
            </p>
            {river?.rivers?.length > 0 && (
              <p style={{ fontSize: 12, color: RIVER_COLOR, fontWeight: 600, margin: "4px 0 0" }}>
                {isId ? "Sungai" : "River"}: {river.rivers.join(" & ")}{" "}
                {river.lines.length
                  ? (river.upstream
                    ? (isId ? "(garis biru; pos hulu, airnya mengalir ke seluruh sungai di Jakarta)" : "(blue line; upstream post, its water flows down the whole river in Jakarta)")
                    : (isId ? "(garis biru)" : "(blue line)"))
                  // Upstream posts (Bogor, Depok) lie outside the Jakarta waterway map.
                  : (isId ? "(di luar peta sungai Jakarta, tidak digambar)" : "(outside the Jakarta river map, not drawn)")}
              </p>
            )}
            {activated > 0 && (
              <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0 0" }}>
                {isId
                  ? `Membuat ${activated} area rawan di sungainya aktif`
                  : `Makes ${activated} flood-prone area${activated > 1 ? "s" : ""} on its river active`}
              </p>
            )}
          </div>
        </Popup>
      </CircleMarker>
    );
  });
  return [...lines, ...markers];
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
            {p.relocated && (
              // scripts/check_flood_prone_points.py: BPBD's coordinates lay far outside this kelurahan
              <p style={{ fontSize: 11, color: "var(--muted)", fontStyle: "italic", marginBottom: 4 }}>
                {isId
                  ? "Lokasi diperkirakan (tengah kelurahan): koordinat dari BPBD berada jauh di luar kelurahan ini."
                  : "Place estimated (kelurahan centre): BPBD's coordinates lay far outside this kelurahan."}
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
