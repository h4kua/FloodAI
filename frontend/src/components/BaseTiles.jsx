import { TileLayer } from "react-leaflet";

/* ── Base map tiles shared by both maps ─────────────────────────────────────
   "canvas" (home map): Esri Gray Canvas (keyless), a quiet grey basemap with a
   separate label layer, in matching light and dark variants, so the posts
   stand out. "street" (evacuation map): Esri World Street Map (keyless), with
   every street and its name, which a resident needs to follow a route; it has
   no dark variant, so dark mode inverts it with a CSS filter (.tiles-dark).
   CARTO basemaps now return an "API KEY REQUIRED" watermark for keyless
   requests, so they are not used.
*/
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const ATTR = "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors";

export default function BaseTiles({ theme, variant = "canvas" }) {
  if (variant === "street") {
    // className is read once when the layer is created, so a theme change remounts it.
    return (
      <TileLayer
        key={theme}
        url={`${ESRI}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`}
        attribution={ATTR}
        maxNativeZoom={19}
        maxZoom={19}
        className={theme === "dark" ? "tiles-dark" : undefined}
      />
    );
  }
  const tone = theme === "dark" ? "Dark" : "Light";
  return (
    <>
      <TileLayer
        url={`${ESRI}/Canvas/World_${tone}_Gray_Base/MapServer/tile/{z}/{y}/{x}`}
        attribution={ATTR}
        maxNativeZoom={16}
      />
      <TileLayer
        url={`${ESRI}/Canvas/World_${tone}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`}
        maxNativeZoom={16}
      />
    </>
  );
}
