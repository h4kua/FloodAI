// A random ID per browser, so a resident can vote once per report and take a
// vote back. Not tied to any account; clearing site data gives a new one.
const KEY = "deflood_device_id";

export function getDeviceId() {
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = crypto.randomUUID?.() ?? `d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    return null; // storage blocked: the page still works, without votes
  }
}
