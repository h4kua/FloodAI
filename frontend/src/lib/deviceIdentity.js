/* ── Device identity ──────────────────────────────────────────────────────
   Lightweight identity for features that need "this device" without a login
   system: a client-generated UUID persisted in localStorage, an optional
   display name/phone profile, and an optional family code linking this
   device to a household group. No password, no server-side session.
*/

const DEVICE_ID_KEY = "deflood_device_id";
const PROFILE_KEY = "deflood_profile";
const FAMILY_CODE_KEY = "deflood_family_code";

export function getDeviceId() {
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

export function getProfile() {
  try {
    return JSON.parse(localStorage.getItem(PROFILE_KEY)) || { name: "", phone: "" };
  } catch {
    return { name: "", phone: "" };
  }
}

export function setProfile({ name, phone }) {
  localStorage.setItem(PROFILE_KEY, JSON.stringify({ name, phone }));
}

export function getFamilyCode() {
  return localStorage.getItem(FAMILY_CODE_KEY) || "";
}

export function setFamilyCode(code) {
  if (code) {
    localStorage.setItem(FAMILY_CODE_KEY, code);
  } else {
    localStorage.removeItem(FAMILY_CODE_KEY);
  }
}
