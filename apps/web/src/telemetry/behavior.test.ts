import { describe, expect, it } from "vitest";
import { appendHeat, deriveHeat, type HeatEvent } from "./behavior";

const ev = (t: HeatEvent["t"], extra: Record<string, unknown>): HeatEvent =>
  ({ t, ...extra } as HeatEvent);

describe("appendHeat", () => {
  it("keeps the ring buffer bounded", () => {
    let buf: HeatEvent[] = [];
    for (let i = 0; i < 1300; i += 1) {
      buf = appendHeat(buf, ev("view", { path: "/a", at: i }));
    }
    expect(buf.length).toBe(1200);
    expect(buf[buf.length - 1]).toMatchObject({ at: 1299 });
    expect(buf[0]).toMatchObject({ at: 100 });
  });
});

describe("deriveHeat", () => {
  it("counts views, per-route dwell, rage taps and quick bounces", () => {
    const events: HeatEvent[] = [
      ev("view", { path: "/jobs", at: 1000 }),
      ev("dwell", { path: "/jobs", ms: 9000, at: 10000 }),
      ev("view", { path: "/tour", at: 10000 }),
      ev("dwell", { path: "/tour", ms: 2500, at: 12500 }),
      ev("view", { path: "/jobs", at: 12000 }),
      ev("dwell", { path: "/jobs", ms: 3000, at: 15000 }),
      ev("rage", { target: "button.btn|Go", path: "/jobs", at: 13000 }),
      ev("rage", { target: "button.btn|Go", path: "/jobs", at: 13500 }),
      ev("rage", { target: "a.link|", path: "/jobs", at: 14000 }),
    ];
    const d = deriveHeat(events);
    expect(d.views).toBe(3);
    expect(d.distinctRoutes).toBe(2);
    expect(d.quickBounces).toBe(2);
    expect(d.rageTotal).toBe(3);
    expect(d.rageTop[0]).toEqual({ target: "button.btn|Go", count: 2 });
    expect(d.spanMin).toBe(0); // < 1 minute
    const jobs = d.routes.find((r) => r.path === "/jobs");
    expect(jobs?.views).toBe(2);
    expect(jobs?.dwellMs).toBe(12000);
  });

  it("handles an empty ledger", () => {
    const d = deriveHeat([]);
    expect(d.views).toBe(0);
    expect(d.medianDwellSec).toBe(0);
    expect(d.rageTop).toEqual([]);
  });
});
