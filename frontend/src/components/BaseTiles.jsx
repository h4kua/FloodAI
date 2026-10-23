import { TileLayer } from "react-leaflet";

/* ── Base map tiles shared by both maps ─────────────────────────────────────
   Esri Gray Canvas (keyless): a quiet grey basemap with a separate label
   layer, in matching light and dark variants. CARTO basemaps now return an
   "API KEY REQUIRED" watermark for keyless requests, so they are not used.
*/
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas";
const ATTR = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";
const MAX_NATIVE_ZOOM = 16;

export default function BaseTiles({ theme }) {
  const tone = theme === "dark" ? "Dark" : "Light";
  return (
    <>
      <TileLayer
        url={`${ESRI}/World_${tone}_Gray_Base/MapServer/tile/{z}/{y}/{x}`}
        attribution={ATTR}
        maxNativeZoom={MAX_NATIVE_ZOOM}
      />
      <TileLayer
        url={`${ESRI}/World_${tone}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`}
        maxNativeZoom={MAX_NATIVE_ZOOM}
      />
    </>
  );
}
