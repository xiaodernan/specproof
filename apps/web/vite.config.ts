import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA is served by the FastAPI server (apps/web/dist) in production;
// the dev server proxies API calls to a local uvicorn on :8000.
//
// base: default "/" keeps the FastAPI static mount working as-is. The
// GitHub Pages static demo lives under /specproof-web/, so the Pages build
// must set VITE_BASE_PATH=/specproof-web/ — CI/deploy does it like:
//   PowerShell:  $env:VITE_BASE_PATH='/specproof-web/'; npm run build
//   POSIX:       VITE_BASE_PATH=/specproof-web/ npm run build
// Defaulting here instead of a hardcoded "/specproof-web/" is deliberate:
// one artifact must not silently break the other host.
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? "/",
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/agent": "http://localhost:8000",
      "/jobs": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/metrics": "http://localhost:8000",
      "/observe": "http://localhost:8000",
    },
  },
});
