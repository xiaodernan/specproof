import { describe, expect, it } from "vitest";
import { resultPill, severityPill, severityHint, evidenceLabel, checkerLabel, contractStatusLabel, healthStatusLabel } from "../toneMap";

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

describe("terminology gloss — plain-Chinese actionability without inventing meaning", () => {
  it("gives each known severity a concrete 'what to do' hint", () => {
    expect(severityHint("BLOCKER")).toMatch(/必须修复/);
    expect(severityHint("major")).toMatch(/建议/);
    expect(severityHint("MINOR")).toBeTruthy();
  });

  it("returns undefined for unknown/absent severity instead of guessing", () => {
    expect(severityHint("BOGUS")).toBeUndefined();
    expect(severityHint(undefined)).toBeUndefined();
  });

  it("annotates known evidence types with Chinese, passes unknown through verbatim", () => {
    expect(evidenceLabel("runtime_test")).toContain("运行时测试");
    expect(evidenceLabel("runtime_test")).toContain("runtime_test"); // canonical token preserved
    // #50/#54: a repo self-test differential may have run in the Docker
    // sandbox (Node) or unsandboxed on the host (opt-in). The evidence kind
    // alone cannot say which, so the label must stay neutral and let the
    // finding's own description carry the surface — claiming either one here
    // would be a lie for the other case.
    expect(evidenceLabel("self_test_diff")).toContain("仓库自带测试差分");
    expect(evidenceLabel("self_test_diff")).toContain("self_test_diff");
    expect(evidenceLabel("self_test_diff")).not.toContain("无沙箱");
    expect(evidenceLabel("self_test_diff")).not.toContain("沙箱");
    expect(evidenceLabel("mystery_kind")).toBe("mystery_kind");
    expect(evidenceLabel(null)).toBe("—");
  });

  it("glosses known checker_type values, preserves the token, passes unknown through", () => {
    expect(checkerLabel("http")).toBe("HTTP 接口检查 · http");
    expect(checkerLabel("openapi")).toContain("OpenAPI");
    expect(checkerLabel("junit")).toBe("junit"); // not in the enum set -> verbatim
    expect(checkerLabel("")).toBe("尚未指定");
    expect(checkerLabel(undefined)).toBe("尚未指定");
  });
});

describe("healthStatusLabel — the /api/v1/health status enum speaks Chinese", () => {
  it("translates the two documented values instead of shouting them in English", () => {
    // The 整体状态 tile used to render status.toUpperCase() -> "OK"/"DEGRADED".
    expect(healthStatusLabel("ok")).toBe("正常");
    expect(healthStatusLabel("degraded")).toBe("降级");
    expect(healthStatusLabel("OK")).toBe("正常");
  });

  it("passes an unknown status through verbatim — never claims 正常 it did not see", () => {
    expect(healthStatusLabel("maintenance")).toBe("maintenance");
    expect(healthStatusLabel("maintenance")).not.toBe("正常");
  });

  it("reports a missing status as 未知 rather than assuming health", () => {
    expect(healthStatusLabel(undefined)).toBe("未知");
    expect(healthStatusLabel(null)).toBe("未知");
    expect(healthStatusLabel("")).toBe("未知");
  });
});

describe("contractStatusLabel — 规则审核状态 keeps its canonical token visible", () => {
  it("glosses the four documented review statuses and preserves the enum", () => {
    // The pill used to render 已批准 alone (English enum dropped) and
    // 状态未知 for anything new (raw token hidden). Both broke the
    // "中文 · TOKEN, unknown verbatim" red-line.
    expect(contractStatusLabel("approved")).toBe("已批准 · APPROVED");
    expect(contractStatusLabel("PROPOSED")).toBe("待审核 · PROPOSED");
    expect(contractStatusLabel("rejected")).toContain("已驳回");
    expect(contractStatusLabel("revoked")).toContain("REVOKED");
  });

  it("passes an unrecognized status through verbatim instead of claiming 状态未知", () => {
    expect(contractStatusLabel("pending_legal_review")).toBe("PENDING_LEGAL_REVIEW");
    expect(contractStatusLabel("pending_legal_review")).not.toContain("状态未知");
  });

  it("renders a missing status as a dash, not a fake approval word", () => {
    expect(contractStatusLabel(undefined)).toBe("—");
    expect(contractStatusLabel(null)).toBe("—");
    expect(contractStatusLabel("")).toBe("—");
  });
});
