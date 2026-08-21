import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vitest config for the SpecProof SPA unit tests (jsdom environment).
// `npm run test` runs `vitest run` from apps/web.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    // globals:true lets @testing-library/react auto-register cleanup
    // (afterEach) so renders never leak between tests.
    globals: true,
  },
});
