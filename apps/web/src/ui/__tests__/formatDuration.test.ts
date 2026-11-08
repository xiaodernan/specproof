import { describe, expect, it } from "vitest";

import { fmtDurationSeconds } from "../util";

// §3.1: the stages tab shows per-step elapsed time. The backend computes
// it (first stamp → last); the frontend must never dress an absent or
// unparseable stamp up as a real measurement.
describe("fmtDurationSeconds", () => {
  it("renders a sub-second stage as a precise stamp", () => {
    expect(fmtDurationSeconds(0.42)).toBe("0.42 秒");
    expect(fmtDurationSeconds(0)).toBe("0.00 秒");
  });

  it("renders seconds with one decimal", () => {
    expect(fmtDurationSeconds(1)).toBe("1.0 秒");
    expect(fmtDurationSeconds(42.34)).toBe("42.3 秒");
  });

  it("promotes to minutes past 60 seconds", () => {
    expect(fmtDurationSeconds(60)).toBe("1 分 0 秒");
    expect(fmtDurationSeconds(95)).toBe("1 分 35 秒");
  });

  it("promotes to hours past 60 minutes", () => {
    expect(fmtDurationSeconds(3661)).toBe("1 小时 1 分");
  });

  it("refuses to render null/undefined/invalid as a measurement", () => {
    expect(fmtDurationSeconds(null)).toBe("—");
    expect(fmtDurationSeconds(undefined)).toBe("—");
    expect(fmtDurationSeconds(Number.NaN)).toBe("—");
    expect(fmtDurationSeconds(-5)).toBe("—");
  });
});
