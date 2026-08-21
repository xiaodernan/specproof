import { describe, expect, it } from "vitest";
import { resultPill, severityPill } from "../toneMap";

describe("severityPill — severity has its own tone map", () => {
  it("maps BLOCKER red, MAJOR orange, MINOR yellow, INFO neutral", () => {
    expect(severityPill("BLOCKER")).toEqual({ cls: "pill-bad", label: "BLOCKER" });
    expect(severityPill("MAJOR")).toEqual({ cls: "pill-major", label: "MAJOR" });
    expect(severityPill("MINOR")).toEqual({ cls: "pill-minor", label: "MINOR" });
    expect(severityPill("INFO")).toEqual({ cls: "pill-mute", label: "INFO" });
  });

  it("is case-insensitive and canonicalizes the label", () => {
    expect(severityPill("blocker")).toEqual({ cls: "pill-bad", label: "BLOCKER" });
    expect(severityPill("minor")).toEqual({ cls: "pill-minor", label: "MINOR" });
  });

  it("renders 未知 for absent, empty or unknown severities — never green", () => {
    for (const s of [undefined, null, "", "WEIRD"]) {
      const p = severityPill(s);
      expect(p.cls).toBe("pill-mute");
      expect(p.label).toContain("未知");
      expect(p.cls).not.toMatch(/pill-ok|pill-pass/);
    }
  });

  it("never returns a green tone for any severity", () => {
    for (const s of ["BLOCKER", "MAJOR", "MINOR", "INFO", "BOGUS"]) {
      expect(severityPill(s).cls).not.toMatch(/pill-ok|pill-pass/);
    }
  });
});

describe("resultPill — result/evidence status map", () => {
  it("maps PASS green, FAIL red, UNVERIFIED amber, DEGRADED neutral", () => {
    expect(resultPill("PASS")).toEqual({ cls: "pill-ok", label: "PASS" });
    expect(resultPill("FAIL")).toEqual({ cls: "pill-bad", label: "FAIL" });
    expect(resultPill("UNVERIFIED")).toEqual({ cls: "pill-unverified", label: "UNVERIFIED" });
    expect(resultPill("DEGRADED")).toEqual({ cls: "pill-mute", label: "DEGRADED" });
  });

  it("renders 未知 for unknown results — never green", () => {
    for (const r of [undefined, null, "", "PENDING", "?"]) {
      const p = resultPill(r);
      expect(p.cls).toBe("pill-mute");
      expect(p.label).toContain("未知");
      expect(p.cls).not.toMatch(/pill-ok|pill-pass/);
    }
  });

  it("keeps the two maps separate: statuses never bleed into the severity map", () => {
    expect(severityPill("UNVERIFIED")).toEqual({ cls: "pill-mute", label: "未知 UNKNOWN" });
    expect(severityPill("PASS")).toEqual({ cls: "pill-mute", label: "未知 UNKNOWN" });
    expect(resultPill("BLOCKER")).toEqual({ cls: "pill-mute", label: "未知 UNKNOWN" });
  });
});
