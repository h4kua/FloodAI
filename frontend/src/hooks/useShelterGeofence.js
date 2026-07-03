import { useEffect, useRef } from "react";
import { haversineKm } from "../components/EvacuationMap";

const TRIGGER_RADIUS_M = 100;

/**
 * Watches the device's live position while `shelter` is set and fires
 * `onArrive(position)` once when the device comes within TRIGGER_RADIUS_M of
 * the shelter. One-shot per shelter selection (a ref flag prevents re-firing
 * on every position update); resets when `shelter` changes.
 */
export function useShelterGeofence(shelter, onArrive) {
  const firedRef = useRef(false);

  useEffect(() => {
    firedRef.current = false;
    if (!shelter || !navigator.geolocation) return undefined;

    const watchId = navigator.geolocation.watchPosition(
      (pos) => {
        if (firedRef.current) return;
        const distanceM = haversineKm(pos.coords.latitude, pos.coords.longitude, shelter.lat, shelter.lng) * 1000;
        if (distanceM <= TRIGGER_RADIUS_M) {
          firedRef.current = true;
          onArrive(pos);
        }
      },
      () => {},
      { enableHighAccuracy: true, maximumAge: 15000, timeout: 20000 }
    );

    return () => navigator.geolocation.clearWatch(watchId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shelter]);
}
