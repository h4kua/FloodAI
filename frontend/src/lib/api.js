// Backend origin. Empty in development (Vite proxies the API paths); in
// production VITE_API_BASE_URL is baked in at build time. Trailing slashes and
// dots are dropped so "https://host.fly.dev/" or "https://host.fly.dev." still
// yield valid request URLs.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/[./]+$/, "");
