import { describe, expect, it } from "vitest";
import { MANUAL } from "../manual.copy";

/**
 * The embedded pocket card is the user's first read — every public lane must
 * appear in it, in BOTH locales, or a newcomer cannot discover the feature.
 * Pin the model-driven routing lane (#2065) into the manual.
 */
describe("Embedded manual documents the model-router lane", () => {
  it("names /model-router in both locales with the honest no-verdict floor", () => {
    const allZh = MANUAL.sections.flatMap((s) => s.rows.zh).join("\n");
    const allEn = MANUAL.sections.flatMap((s) => s.rows.en).join("\n");
    expect(allZh).toMatch(/\/model-router/);
    expect(allEn).toMatch(/\/model-router/);
    expect(allZh).toMatch(/模型选路/);
    expect(allEn).toMatch(/Model Router/);
    // the guard is stated, not just the feature
    expect(allZh).toMatch(/不判|裁决/);
    expect(allEn.toLowerCase()).toMatch(/never grades|never rule/);
  });
});
