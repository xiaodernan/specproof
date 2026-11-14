import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  TOUR_STATIONS,
  isTourSealed,
  loadTourProgress,
  resetTourProgress,
  saveTourProgress,
  toggleStation,
  tourCompletionCount,
  type TourProgress,
} from "../tour";

const KEY = "specproof_tour_v1";
const fresh = (): TourProgress => ({ completed: [], completed_at: {}, sealed_at: null });

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("loadTourProgress", () => {
  it("an empty store is a genuine fresh start", () => {
    const read = loadTourProgress();
    expect(read.corrupted).toBe(false);
    expect(read.progress.completed).toEqual([]);
    expect(read.progress.sealed_at).toBeNull();
  });

  it("flagging parse failures as corrupted rather than a fresh start", () => {
    window.localStorage.setItem(KEY, "{not json");
    expect(loadTourProgress().corrupted).toBe(true);
  });

  it("rejects unknown station ids instead of guessing", () => {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ completed: ["gate", "nope", "billing_page"], completed_at: {}, sealed_at: null }),
    );
    expect(loadTourProgress().progress.completed).toEqual(["gate"]);
  });

  it("survives storage disabled as corrupted, not a fresh tour", () => {
    const original = window.localStorage;
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem() {
          throw new Error("storage disabled");
        },
        setItem() {
          throw new Error("storage disabled");
        },
      },
    });
    try {
      expect(loadTourProgress().corrupted).toBe(true);
    } finally {
      Object.defineProperty(window, "localStorage", { configurable: true, value: original });
    }
  });

  it("round-trips a saved record", () => {
    expect(saveTourProgress(fresh())).toBe(true);
    expect(loadTourProgress().corrupted).toBe(false);
  });
});

describe("toggleStation", () => {
  it("marks a station complete with a completion stamp", () => {
    const next = toggleStation(fresh(), "gate");
    expect(next.completed).toEqual(["gate"]);
    expect(typeof next.completed_at.gate).toBe("string");
    expect(next.sealed_at).toBeNull();
  });

  it("awards the seal as soon as all stations are complete", () => {
    let p = fresh();
    for (const s of TOUR_STATIONS) p = toggleStation(p, s.id);
    expect(isTourSealed(p)).toBe(true);
    expect(typeof p.sealed_at).toBe("string");
  });

  it("un-completing a station revokes the seal", () => {
    let p = fresh();
    for (const s of TOUR_STATIONS) p = toggleStation(p, s.id);
    expect(isTourSealed(p)).toBe(true);
    p = toggleStation(p, "epic");
    expect(isTourSealed(p)).toBe(false);
    expect(p.sealed_at).toBeNull();
    expect(tourCompletionCount(p)).toBe(TOUR_STATIONS.length - 1);
  });

  it("toggling the same station twice returns to default", () => {
    const once = toggleStation(fresh(), "matrix");
    expect(once.completed).toEqual(["matrix"]);
    const twice = toggleStation(once, "matrix");
    expect(twice.completed).toEqual([]);
    expect(twice.completed_at).toEqual({});
  });
});

describe("resetTourProgress", () => {
  it("wipes the stored seal", () => {
    let p = fresh();
    for (const s of TOUR_STATIONS) p = toggleStation(p, s.id);
    expect(saveTourProgress(p)).toBe(true);
    const reset = resetTourProgress();
    expect(reset.completed).toEqual([]);
    expect(loadTourProgress().progress.completed).toEqual([]);
  });
});

describe("tourCompletionCount", () => {
  it("counts only known stations", () => {
    const p: TourProgress = { completed: ["gate", "matrix", "findings"], completed_at: {}, sealed_at: null };
    expect(tourCompletionCount(p)).toBe(3);
  });
});
