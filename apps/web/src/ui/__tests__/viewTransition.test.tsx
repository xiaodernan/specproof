import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { withViewTransition } from "../viewTransition";

function stubMatchMedia(matches: boolean): void {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)" ? matches : false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  );
}

describe("withViewTransition", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", undefined);
    delete (document as unknown as { startViewTransition?: unknown }).startViewTransition;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (document as unknown as { startViewTransition?: unknown }).startViewTransition;
  });

  it("runs the update synchronously when the browser lacks the API", () => {
    stubMatchMedia(false);
    const update = vi.fn();
    withViewTransition(update);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("wraps the update in startViewTransition when the browser supports it", () => {
    stubMatchMedia(false);
    const calls: Array<() => void> = [];
    (document as unknown as { startViewTransition: (cb: () => void) => unknown }).startViewTransition =
      (cb: () => void) => {
        calls.push(cb);
        return {};
      };
    const update = vi.fn();
    withViewTransition(update);
    expect(calls).toHaveLength(1);
    expect(update).not.toHaveBeenCalled(); // wrapped, not run eagerly
    calls[0]();
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("never wraps when the user prefers reduced motion", () => {
    stubMatchMedia(true); // prefers-reduced-motion: reduce
    let wrapped = false;
    (document as unknown as { startViewTransition: (cb: () => void) => unknown }).startViewTransition =
      () => {
        wrapped = true;
        return {};
      };
    const update = vi.fn();
    withViewTransition(update);
    expect(wrapped).toBe(false);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("treats a missing matchMedia as no preference signal, still wraps", () => {
    delete (window as unknown as { matchMedia?: unknown }).matchMedia;
    let wrapped = false;
    (document as unknown as { startViewTransition: (cb: () => void) => unknown }).startViewTransition =
      (cb: () => void) => {
        wrapped = true;
        cb();
        return {};
      };
    const update = vi.fn();
    withViewTransition(update);
    expect(wrapped).toBe(true);
    expect(update).toHaveBeenCalledTimes(1);
  });
});
