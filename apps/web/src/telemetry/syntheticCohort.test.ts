import { describe, expect, it } from "vitest";
import {
  PERSONA_MIX,
  simulateCohort,
  SYNTHETIC_SEED,
  type PersonaKind,
} from "./syntheticCohort";

describe("syntheticCohort", () => {
  it("is deterministic — same seed, byte-identical summary", () => {
    const a = simulateCohort(240, SYNTHETIC_SEED);
    const b = simulateCohort(240, SYNTHETIC_SEED);
    expect(a).toEqual(b);
  });

  it("mixes personas to within binomial tolerance of the calibration", () => {
    const cohort = simulateCohort(2000, SYNTHETIC_SEED);
    for (const kind of Object.keys(PERSONA_MIX) as PersonaKind[]) {
      const share = cohort.personaSummaries.find((p) => p.persona === kind)!.share;
      // 2000 draws: sd of a p·(1-p) proportion is ≤ ~1.2%; allow ±4% slack.
      expect(Math.abs(share - PERSONA_MIX[kind])).toBeLessThan(0.04);
    }
  });

  it("funnel never grows as stages advance", () => {
    const cohort = simulateCohort(240, SYNTHETIC_SEED);
    const counts = cohort.funnel.map((s) => s.count);
    for (let i = 1; i < counts.length; i += 1) {
      expect(counts[i]).toBeLessThanOrEqual(counts[i - 1]);
    }
    expect(counts[0]).toBe(cohort.size);
  });

  it("rage events only come from the rager persona", () => {
    const cohort = simulateCohort(240, SYNTHETIC_SEED);
    const rager = cohort.personaSummaries.find((p) => p.persona === "rager")!;
    const others = cohort.personaSummaries
      .filter((p) => p.persona !== "rager")
      .reduce((acc, p) => acc + p.rageEvents, 0);
    expect(rager.rageEvents).toBeGreaterThan(0);
    expect(others).toBe(0);
    expect(cohort.totalRageEvents).toBe(rager.rageEvents);
  });

  it("bouncers never register engagement beyond their one silent dwell", () => {
    const cohort = simulateCohort(240, SYNTHETIC_SEED);
    const bouncers = cohort.personaSummaries.find((p) => p.persona === "bouncer")!;
    expect(bouncers.medianDwellMs).not.toBeNull();
    expect(bouncers.rageEvents).toBe(0);
  });

  it("impatient share stays within the calibrated 30%–65% band", () => {
    const cohort = simulateCohort(240, SYNTHETIC_SEED);
    expect(cohort.impatientRate).toBeGreaterThanOrEqual(0.3);
    expect(cohort.impatientRate).toBeLessThanOrEqual(0.65);
  });
});
