import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The SPA is served by the FastAPI server (apps/web/dist) in production;
// the dev server proxies API calls to a local uvicorn on :8000.
export default defineConfig({
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
      "/agent": "http://localhost:8000",
      "/jobs": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/metrics": "http://localhost:8000",
    },
  },
});
