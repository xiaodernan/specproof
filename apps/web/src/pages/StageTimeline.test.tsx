import { describe, expect, it } from "vitest";

import { skippableRows, stageSpans } from "./StageTimeline";

// §3.1: the stage-timeline paints each stage as a bar positioned by its
// started_at and scaled by its duration_seconds. Rows that lack either
// measurement must never be dressed up as bars — they are reported as
// skipped, loudly, instead of faking an axis position.
describe("stage timeline math", () => {
  const base = {
    status: "COMPLETED",
  };

  it("keeps rows with a resolvable start and a non-negative duration", () => {
    const rows = [
      { node: "b", started_at: "2026-11-14T10:00:10Z", duration_seconds: 3, ...base },
      { node: "a", started_at: "2026-11-14T10:00:00Z", duration_seconds: 10, ...base },
    ];
    const spans = stageSpans(rows);
    expect(spans.map((s) => s.node)).toEqual(["a", "b"]);
    expect(spans[0].endMs - spans[0].startMs).toBe(10_000);
    expect(skippableRows(rows)).toEqual([]);
  });

  it("drops rows whose started_at is missing or unparseable", () => {
    const rows = [
      { node: "no-start", started_at: null, duration_seconds: 5, ...base },
      { node: "bad-start", started_at: "not-a-date", duration_seconds: 5, ...base },
      { node: "good", started_at: "2026-11-14T10:00:00Z", duration_seconds: 5, ...base },
    ];
    const spans = stageSpans(rows);
    expect(spans.map((s) => s.node)).toEqual(["good"]);
    expect(skippableRows(rows).map((r) => r.node)).toEqual(["no-start", "bad-start"]);
  });

  it("drops rows with missing, negative or non-number durations", () => {
    const rows = [
      { node: "no-dur", started_at: "2026-11-14T10:00:00Z", duration_seconds: null, ...base },
      { node: "neg-dur", started_at: "2026-11-14T10:00:00Z", duration_seconds: -1, ...base },
      { node: "str-dur", started_at: "2026-11-14T10:00:00Z", duration_seconds: "5" as unknown as number, ...base },
      { node: "ok", started_at: "2026-11-14T10:00:00Z", duration_seconds: 0, ...base },
    ];
    const spans = stageSpans(rows);
    expect(spans.map((s) => s.node)).toEqual(["ok"]);
    expect(skippableRows(rows).map((r) => r.node)).toEqual(["no-dur", "neg-dur", "str-dur"]);
  });

  it("breaks start-time ties by node name for a stable order", () => {
    const rows = [
      { node: "zeta", started_at: "2026-11-14T10:00:00Z", duration_seconds: 1, ...base },
      { node: "alpha", started_at: "2026-11-14T10:00:00Z", duration_seconds: 1, ...base },
    ];
    expect(stageSpans(rows).map((s) => s.node)).toEqual(["alpha", "zeta"]);
  });

  it("a zero-duration stage is a real (degenerate) span, not a skip", () => {
    const rows = [
      { node: "instant", started_at: "2026-11-14T10:00:00Z", duration_seconds: 0, ...base },
    ];
    const spans = stageSpans(rows);
    expect(spans).toHaveLength(1);
    expect(spans[0].endMs).toBe(spans[0].startMs);
    expect(skippableRows(rows)).toHaveLength(0);
  });
});
