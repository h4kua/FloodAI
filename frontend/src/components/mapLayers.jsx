/* ── Map layers shared by the water-level map and the evacuation map ──────
   Both maps draw the monitoring posts and the active flood-prone areas with
   these components, so the same post has the same colour on both, and every
   red area names the post that made it active.
*/
import { useMemo, useRef, useState } from "react";
import { Circle, CircleMarker, Pane, Polyline, Popup, useMapEvents } from "react-leaflet";
import { useApp } from "../lib/appContext";
import { RISK_RADIUS_M, areasByPost, riverForPost } from "../lib/floodRoads";
import { postClass } from "../lib/dashboardHelpers";
import postRivers from "../data/postRivers.json";
import areaChance from "../data/activeAreaChance.json";
import PostTrend from "./PostTrend";

export const AREA_COLOR = "#c8102e";
// The river of an open post.
const RIVER_COLOR = "#1d4ed8";


// Post colour by its ratio to Siaga 1 (same bands as the map legend).
const POST_COLOR = { s1: "#c8102e", s2: "#c2410c", wsp: "#e0a400", ok: "#15803d" };
/** Marker colour from the post's own DSDA band (ratio only as a fallback). */
export const stationColor = (station) => POST_COLOR[postClass(station)];

const titleCase = (s) => (s || "").toLowerCase().split(" ").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
const siagaWord = (status) => (status || "").replace(/^Status\s*:\s*/i, "");

/* How often such an area flooded on days its post reached that band (DSDA 2016-2021 vs BPBD records,
   scripts/active_area_chance.py), from the highest band among the posts that activated it. */
function areaChanceNote(p, isId) {
  const bands = (p.causes || []).map((s) => /siaga\s*[1-3]/i.exec(s.status_siaga || "")?.[0]).filter(Boolean)
    .map((b) => b.replace(/\s+/, " ").replace(/^s/, "S"));
  const band = bands.sort()[0];  // "Siaga 1" < "Siaga 2" < "Siaga 3"
  const rate = band && areaChance.by_status?.[band];
  if (rate == null) return null;
  const pct = (v) => `${Math.round(v * 100)}%`;
  return isId
    ? `Pada hari pos di ${band} (2016–2021), area di sepanjang sungainya tercatat banjir pada sekitar ${pct(rate)} hari (hari biasa ${pct(areaChance.normal)}).`
    : `On days a post was at ${band} (2016–2021), areas along its river had a recorded flood on about ${pct(rate)} of days (normal days ${pct(areaChance.normal)}).`;
}
// pane: a popup inside the "posts" <Pane> would otherwise open in that pane, under the other posts and the weather cards.
const popupPad = { pane: "popupPane", autoPan: true, autoPanPaddingTopLeft: [8, 64], autoPanPaddingBottomRight: [8, 8] };

/* Content added after a popup opens (the river name, the water chart) makes it taller than Leaflet
   measured, and Leaflet skips the auto-pan that follows its own (its `_autopanning` flag), so a post
   near the map's top edge had its popup cut off. Re-lay it out, then pan by what still sticks out. */
export function keepPopupInView(popup, pad = 12) {
  const map = popup?._map;
  if (!map || !popup.isOpen()) return;
  popup.update();
  requestAnimationFrame(() => {
    const el = popup.getElement();
    if (!el || !popup._map) return;
    const m = map.getContainer().getBoundingClientRect();
    const r = el.getBoundingClientRect();
    let dx = 0;
    let dy = 0;
    if (r.top < m.top + pad) dy = r.top - m.top - pad;
    else if (r.bottom > m.bottom - pad) dy = Math.min(r.bottom - m.bottom + pad, r.top - m.top - pad);
    if (r.left < m.left + pad) dx = r.left - m.left - pad;
    else if (r.right > m.right - pad) dx = r.right - m.right + pad;
    if (dx || dy) map.panBy([dx, dy], { animate: true });
  });
}

/** Every popup on the map stays fully inside it, also when its content grows after opening.
    The maps keep the view inside Jakarta (maxBounds, viscosity 1), which also blocked the pan a popup
    near the edge needs (Marina Ancol on the coast was cut off): the limit is lifted while a popup is
    open and put back when it closes, which brings the view back inside Jakarta. */
export function PopupKeeper() {
  const saved = useRef(null);
  const open = useRef(0);
  const map = useMapEvents({
    popupopen: (e) => {
      const popup = e.popup;
      open.current += 1;
      if (map.options.maxBounds) {
        saved.current = map.options.maxBounds;
        map.setMaxBounds(null);
      }
      keepPopupInView(popup);
      const el = popup.getElement()?.querySelector(".leaflet-popup-content");
      if (!el || typeof ResizeObserver === "undefined") return;
      let last = el.offsetHeight;
      const ro = new ResizeObserver(() => {
        if (Math.abs(el.offsetHeight - last) < 2) return;
        last = el.offsetHeight;
        keepPopupInView(popup);
      });
      ro.observe(el);
      popup.once("remove", () => ro.disconnect());
    },
    popupclose: () => {
      open.current = Math.max(0, open.current - 1);
      // One marker to the next closes A before B opens: restore only if nothing opened meanwhile.
      setTimeout(() => {
        if (open.current === 0 && saved.current) {
          map.setMaxBounds(saved.current);
          saved.current = null;
        }
      }, 0);
    },
  });
  return null;
}

/**
 * Monitoring posts with validated coordinates, coloured by their DSDA band.
 * While a post's popup is open, the river it measures is drawn in blue around it
 * (src/data/postRivers.json), and the popup counts the active flood-prone areas
 * (`floodPoints`) the post makes active.
 */
export function StationMarkers({ stations = [], floodPoints = [], small = false, withTrend = false }) {
  const { theme, lang } = useApp();
  const isId = lang === "id";
  const [openPost, setOpenPost] = useState(null);
  // The river line is added to the popup after it opens: PopupKeeper re-pans once it grows.
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
          popupopen: () => setOpenPost(s.nama),
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
            {withTrend && s.nama === openPost && (
              <PostTrend name={s.nama} isId={isId} />
            )}
          </div>
        </Popup>
      </CircleMarker>
    );
  });
  // Posts get their own pane above everything else drawn on the map (the home
  // map's weather cards sit at 450), so a card can never cover or swallow a post.
  return [...lines, <Pane key="posts" name="posts" style={{ zIndex: 460 }}>{markers}</Pane>];
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
            {areaChanceNote(p, isId) && (
              <p style={{ fontSize: 11, color: "var(--muted)", margin: "4px 0 0" }}>{areaChanceNote(p, isId)}</p>
            )}
          </div>
        </Popup>
      </Circle>
    );
  });
}
