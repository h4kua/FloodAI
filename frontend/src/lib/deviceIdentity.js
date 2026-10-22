/* ── Device identity ──────────────────────────────────────────────────────
   Lightweight identity for features that need "this device" without a login
   system: a client-generated UUID persisted in localStorage, and the family
   code a device may have joined (read-only here — sent along with a shelter
   check-in). No password, no server-side session.
*/

const DEVICE_ID_KEY = "deflood_device_id";
const FAMILY_CODE_KEY = "deflood_family_code";

export function getDeviceId() {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

export function getFamilyCode() {
  return localStorage.getItem(FAMILY_CODE_KEY) || "";
}
