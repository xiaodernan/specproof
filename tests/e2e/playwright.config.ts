import { defineConfig } from "@playwright/test";

// SpecProof e2e (industrialization guide §A task 5 + 阶段2 exit).
//
// Backend = the REAL FastAPI app (tests/e2e/fixture_server.py) on :8000 —
// the port apps/web/vite.config.ts already proxies — and the REAL Vite dev
// server on :5174 (5173 may be occupied; the proxy target stays :8000).
// No DOM mocks: the browser drives the real SPA against the real API.
export default defineConfig({
  testDir: ".",
  outputDir: "test-results",
  testMatch: /(wizard|detail|permissions)\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  globalSetup: "./global-setup.ts",
  use: {
    baseURL: "http://127.0.0.1:5174",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "specproof-e2e" }],
  webServer: [
    {
      command: "python fixture_server.py --port 8010 --state .state/e2e-state.json",
      url: "http://127.0.0.1:8010/health",
      timeout: 90_000,
      reuseExistingServer: false,
    },
    {
      command: "cd ..\\..\\apps\\web && npm run dev -- --config ../../apps/web/vite.e2e.config.ts",
      url: "http://127.0.0.1:5174",
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
