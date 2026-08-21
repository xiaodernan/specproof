import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// e2e-only Vite config (used by tests/e2e/playwright*.config.ts webServer).
// Same app, same plugins as vite.config.ts, but the dev proxy targets the
// e2e fixture on :8010 instead of :8000 — so the suite never collides with
// a developer's real API server running on the documented dev port, and the
// IPv4 loopback is pinned explicitly (localhost can resolve to ::1 here).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5174,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": "http://127.0.0.1:8010",
      "/auth": "http://127.0.0.1:8010",
      "/agent": "http://127.0.0.1:8010",
      "/jobs": "http://127.0.0.1:8010",
      "/health": "http://127.0.0.1:8010",
      "/metrics": "http://127.0.0.1:8010",
    },
  },
});
