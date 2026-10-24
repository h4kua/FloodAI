import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // In dev, proxy /predict/* and /api/* to the backend so the browser
  // never makes a cross-origin request (no CORS issues, no preflight).
  // In production (Vercel) this block is irrelevant — VITE_API_BASE_URL
  // in the Vercel dashboard points the frontend directly to Railway/Fly.
  const backendUrl = env.VITE_API_BASE_URL || "http://localhost:8080";

  return {
    plugins: [react()],
    build: {
      outDir: "dist",
      sourcemap: false,
    },
    server: {
      port: 3000,
      proxy: {
        "/predict":  { target: backendUrl, changeOrigin: true },
        "/api":      { target: backendUrl, changeOrigin: true },
        "/healthz":  { target: backendUrl, changeOrigin: true },
        "/shelters": { target: backendUrl, changeOrigin: true },
      },
    },
  };
});
