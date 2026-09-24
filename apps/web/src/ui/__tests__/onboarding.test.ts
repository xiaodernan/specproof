import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  EMPTY_PROGRESS,
  ONBOARDING_STEPS,
  loadOnboardingProgress,
  recordRouteVisit,
  routeKeyFor,
  saveOnboardingProgress,
  stepState,
  summarize,
  toggleManualStep,
  type OnboardingProgress,
  type StepSignals,
} from "../onboarding";

const KEY = "specproof_onboarding_v1";

const signals = (over: Partial<StepSignals> = {}): StepSignals => ({
  progressUnreadable: false,
  credential: "present",
  connection: "ok",
  verificationCount: 1,
  ...over,
});

const step = (id: string) => {
  const found = ONBOARDING_STEPS.find((s) => s.id === id);
  if (!found) throw new Error("unknown step id " + id);
  return found;
};

const progress = (over: Partial<OnboardingProgress> = {}): OnboardingProgress => ({
  manual: {},
  visited: {},
  ...over,
});

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("loadOnboardingProgress", () => {
  it("treats an empty store as a genuine fresh start", () => {
    expect(loadOnboardingProgress().status).toBe("absent");
  });

  it("does not read a corrupt record as a fresh start", () => {
    window.localStorage.setItem(KEY, "{not json");
    const read = loadOnboardingProgress();
    expect(read.status).toBe("unreadable");
  });

  it("rejects half a record instead of silently dropping the unreadable half", () => {
    window.localStorage.setItem(KEY, JSON.stringify({ manual: { connect: "2026-08-18T00:00:00Z" } }));
    expect(loadOnboardingProgress().status).toBe("unreadable");
  });

  it("survives a blocked storage API as unreadable, not absent", () => {
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
      expect(loadOnboardingProgress().status).toBe("unreadable");
      // A tick that cannot be persisted must report failure rather than
      // silently pretend it will survive a reload.
      expect(saveOnboardingProgress(progress({ manual: { prepare_spec: "t" } }))).toBe(false);
    } finally {
      Object.defineProperty(window, "localStorage", { configurable: true, value: original });
    }
  });

  it("round-trips a saved record", () => {
    expect(saveOnboardingProgress(progress({ visited: { job_detail: "x" } }))).toBe(true);
    const read = loadOnboardingProgress();
    expect(read.status).toBe("ok");
    expect(read.progress.visited.job_detail).toBe("x");
  });
});

describe("stepState", () => {
  it("never calls an unreadable connection 'not done'", () => {
    // While the probe is in flight a step is unknown, not pending-todo.
    expect(stepState(step("connect"), EMPTY_PROGRESS, signals({ connection: "pending" }))).toBe("unknown");
    expect(stepState(step("connect"), EMPTY_PROGRESS, signals({ connection: "failed" }))).toBe("unknown");
    expect(stepState(step("connect"), EMPTY_PROGRESS, signals())).toBe("done");
  });

  it("reads a missing local credential as a fact, not as a failed probe", () => {
    // The guide is public, so most readers have never logged in. Telling them
    // "cannot confirm" would be the least useful possible answer.
    const absent = signals({ credential: "absent", connection: "pending", verificationCount: null });
    expect(stepState(step("connect"), EMPTY_PROGRESS, absent)).toBe("todo");
    // ...but the workspace-side steps stay unknown: another device may already
    // have run a verification we cannot see from here.
    expect(stepState(step("create_verification"), EMPTY_PROGRESS, absent)).toBe("unknown");
  });

  it("only says a verification is missing when the list really answered zero", () => {
    const create = step("create_verification");
    expect(stepState(create, EMPTY_PROGRESS, signals({ verificationCount: 0 }))).toBe("todo");
    expect(stepState(create, EMPTY_PROGRESS, signals({ verificationCount: 3 }))).toBe("done");
    expect(stepState(create, EMPTY_PROGRESS, signals({ verificationCount: null }))).toBe("unknown");
  });

  it("keeps an unreadable tick from being rendered as 'never started'", () => {
    const prepare = step("prepare_spec");
    expect(stepState(prepare, EMPTY_PROGRESS, signals())).toBe("todo");
    expect(
      stepState(prepare, EMPTY_PROGRESS, signals({ progressUnreadable: true }))
    ).toBe("unknown");
    const read = step("read_results");
    expect(
      stepState(read, progress({ manual: { read_results: "t" } }), signals({ progressUnreadable: true }))
    ).toBe("unknown");
  });

  it("counts a visited result page as seen, and reports unknowns separately", () => {
    const read = step("read_results");
    expect(stepState(read, progress({ visited: { job_detail: "t" } }), signals())).toBe("done");
    expect(stepState(read, EMPTY_PROGRESS, signals())).toBe("todo");
    const sum = summarize(ONBOARDING_STEPS, EMPTY_PROGRESS, signals({ connection: "failed", verificationCount: null }));
    expect(sum.done).toBe(0);
    // Two steps ride on the unreadable probe; "看结论" genuinely has nothing
    // recorded, and an empty local record is a real answer, not a missing one.
    expect(sum.unknown).toBe(2);
    expect(sum.total).toBe(ONBOARDING_STEPS.length);
  });
});

describe("route recording", () => {
  it("recognises result pages but not the list or the create form", () => {
    expect(routeKeyFor("#/jobs/job-9")).toBe("job_detail");
    expect(routeKeyFor("#/agent/jobs/job-9")).toBe("agent_job_detail");
    expect(routeKeyFor("#/jobs")).toBeNull();
    expect(routeKeyFor("#/jobs/new")).toBeNull();
    expect(routeKeyFor("#/dashboard")).toBeNull();
  });

  it("records a visit without clobbering the other keys", () => {
    saveOnboardingProgress(progress({ manual: { prepare_spec: "kept" } }));
    recordRouteVisit("#/jobs/job-9");
    const read = loadOnboardingProgress();
    expect(read.progress.visited.job_detail).toBeTruthy();
    expect(read.progress.manual.prepare_spec).toBe("kept");
  });

  it("will not overwrite an unreadable store with a single navigation", () => {
    window.localStorage.setItem(KEY, "{broken");
    recordRouteVisit("#/jobs/job-9");
    expect(window.localStorage.getItem(KEY)).toBe("{broken");
  });

  it("ignores routes that are not evidence of anything", () => {
    recordRouteVisit("#/dashboard");
    expect(loadOnboardingProgress().status).toBe("absent");
  });
});

describe("toggleManualStep", () => {
  it("ticks and unticks without mutating the previous state", () => {
    const next = toggleManualStep(EMPTY_PROGRESS, "prepare_spec", "2026-08-18T00:00:00Z");
    expect(EMPTY_PROGRESS.manual).toEqual({});
    expect(next.manual.prepare_spec).toBe("2026-08-18T00:00:00Z");
    expect(toggleManualStep(next, "prepare_spec", "x").manual).toEqual({});
  });
});
