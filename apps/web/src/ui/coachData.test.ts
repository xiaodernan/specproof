import { beforeEach, describe, expect, it, vi } from "vitest";
import { COACH_MARKS, coachToggleEvent, readCoachEnabled, writeCoachEnabled } from "./coachData";

describe("coach marks store", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("defaults to enabled on first visit (no stored preference)", () => {
    expect(readCoachEnabled()).toBe(true);
  });

  it("persists explicit disable, and re-enable", () => {
    writeCoachEnabled(false);
    expect(readCoachEnabled()).toBe(false);
    writeCoachEnabled(true);
    expect(readCoachEnabled()).toBe(true);
  });

  it("degrades to false when storage is unavailable (private mode)", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    expect(readCoachEnabled()).toBe(false);
  });

  it("every mark key is unique, and every record is bilingual", () => {
    const keys = COACH_MARKS.map((m) => m.key);
    expect(new Set(keys).size).toBe(keys.length);
    for (const mark of COACH_MARKS) {
      expect(mark.title.zh).toBeTruthy();
      expect(mark.title.en).toBeTruthy();
      expect(mark.body.zh).toBeTruthy();
      expect(mark.body.en).toBeTruthy();
    }
  });

  it("toggle event name is stable", () => {
    expect(coachToggleEvent()).toBe("specproof-coach-marks:toggle");
  });
});
