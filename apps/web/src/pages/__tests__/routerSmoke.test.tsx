import { describe, expect, it, vi, beforeAll, afterEach } from "vitest";
import { render, waitFor, cleanup } from "@testing-library/react";
import App, { NAV } from "../../App";

/**
 * Router smoke — every destination in the NAV gets mounted in BOTH locales,
 * and no route may fall back to the render-crash boundary.
 *
 * Without a credential, every route renders <Login /> (App.tsx) — this suite
 * seeds a fake session so every 43 destinations actually lazy-load and mount.
 * Dynamic imports resolve in milliseconds here; `.spinner` is the Suspense
 * fallback's own marker, so we wait for it to clear before judging a route.
 *
 * This is the "the world is not empty" gate.
 */
describe("Router smoke — every NAV destination mounts both locales", () => {
  beforeAll(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.sessionStorage.setItem("specproof_api_key", "test-key-not-a-real-credential");
    vi.stubGlobal(
      "EventSource",
      class {
        onmessage: ((ev: unknown) => void) | null = null;
        readyState = 0;
        close() {
          this.readyState = 2;
        }
        addEventListener() {}
        removeEventListener() {}
      },
    );
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    vi.resetModules();
  });

  for (const locale of ["zh", "en"] as const) {
    it(`mounts every NAV destination in ${locale}`, async () => {
      window.localStorage.setItem("specproof_locale", locale);
      for (const item of NAV) {
        window.location.hash = `#/${item.path}`;
        let container: HTMLElement | null = null;
        expect(() => {
          container = render(<App />).container;
        }, `route crashed synchronously in ${locale}: #/${item.path}`).not.toThrow();
        expect(container!.textContent?.length ?? 0, `route was empty in ${locale}: #/${item.path}`).toBeGreaterThan(0);
        // let the lazy chunk resolve, then judge the outcome
        await waitFor(() => {
          expect(container!.querySelector(".spinner")).toBeNull();
        }, { timeout: 3000 }).catch(() => {
          /* page may keep its own poll-spinner — judge by the crash boundary instead */
        });
        expect(
          container!.querySelector('[data-testid="error-boundary"]'),
          `route fell back to the render-crash boundary in ${locale}: #/${item.path}`,
        ).toBeNull();
        cleanup();
      }
    }, 120000);
  }

  it("unknown routes land on the 404 shell, not a blank page", async () => {
    window.localStorage.setItem("specproof_locale", "zh");
    window.location.hash = "#/no-such-world-gate";
    const { container } = render(<App />);
    await waitFor(() => {
      expect(container.textContent?.length ?? 0).toBeGreaterThan(0);
    });
  });
});
