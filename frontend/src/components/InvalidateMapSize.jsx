import { useEffect } from "react";
import { useMap } from "react-leaflet";

/* ── InvalidateMapSize — leaflet resize guard ──────────────────────────────
   Drop inside any <MapContainer>. Leaflet caches its container size at mount;
   when a CollapsibleSection above the map opens/closes (or the grid reflows),
   the cached size goes stale and tiles render gray. A ResizeObserver on the
   container keeps the map honest.
*/
export default function InvalidateMapSize() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(container);
    return () => observer.disconnect();
  }, [map]);

  return null;
}
