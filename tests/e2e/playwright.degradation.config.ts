import { defineConfig } from "@playwright/test";

// Degradation scenario (降级): the backend is deliberately NOT started for
// this project, so every API call through the Vite proxy fails
// (connection refused). The SPA must degrade gracefully — error notices on
// every page, never a white screen. Runs AFTER the main config so the
// shared Vite port is free again.
export default defineConfig({
  testDir: ".",
  outputDir: "test-results",
  testMatch: /degradation\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:5174",
    headless: true,
    trace: "retain-on-failure",
  },
  projects: [{ name: "specproof-degradation" }],
  webServer: [
    {
      command: "cd ..\\..\\apps\\web && npm run dev -- --config ../../apps/web/vite.e2e.config.ts",
      url: "http://127.0.0.1:5174",
      timeout: 120_000,
      reuseExistingServer: false,
    },
  ],
});
