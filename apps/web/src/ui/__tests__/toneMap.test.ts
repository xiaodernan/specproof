import { describe, expect, it } from "vitest";
import { resultPill, severityPill, severityHint, severityRank, acceptSeverityLabel, acceptSeverityTone, ACCEPT_SEVERITY_BLOCKING, evidenceLabel, checkerLabel, contractStatusLabel, healthStatusLabel, attributionLabel, executionSurfaceLabel, executionSurfaceTone, SEVERITIES, SEVERITY_STOREABLE } from "../toneMap";

// The severity vocabulary is reconciled against the MySQL ENUM, the HTTP
// request pattern and the pipeline's own emission sites by
// tests/unit/test_severity_vocabulary_parity.py. These cases hold the UI half
// of that contract: a value the column can hold must have a word, and a word
// must have a value that can reach it.

describe("severityPill — severity has its own tone map", () => {
  it("glosses every severity the findings column can store", () => {
    expect(severityPill("BLOCKER")).toEqual({ cls: "pill-bad", label: "BLOCKER" });
    expect(severityPill("MAJOR")).toEqual({ cls: "pill-major", label: "MAJOR" });
    expect(severityPill("MINOR")).toEqual({ cls: "pill-minor", label: "MINOR" });
    // NEEDS_CONFIRMATION is a legal findings.severity value and used to have
    // no word at all: the pill rendered it as 未知 UNKNOWN, which is what a
    // reviewer sees for a typo, so the one verdict that asks for human review
    // looked like broken data.
    expect(severityPill("NEEDS_CONFIRMATION")).toEqual({
      cls: "pill-unverified",
      label: "NEEDS_CONFIRMATION",
    });
    expect(severityHint("NEEDS_CONFIRMATION")).toMatch(/人工确认/);
  });

  it("names the two pipeline events that carry a severity but cannot be stored", () => {
    // NONE: a checker crashed or the target has no checker (registry.py);
    // ERROR: the counterexample generator could not compile (agent/nodes).
    // Both used to render as 未知 UNKNOWN — the same words used for garbage,
    // hiding the most actionable line on the page.
    expect(severityPill("NONE")).toEqual({ cls: "pill-mute", label: "NONE" });
    expect(severityHint("NONE")).toMatch(/不构成风险判定/);
    expect(severityHint("NONE")).toMatch(/未验证/);
    expect(severityPill("ERROR")).toEqual({ cls: "pill-mute", label: "ERROR" });
    expect(severityHint("ERROR")).toMatch(/反例/);
    // ...and neither can be voted on, because the column cannot hold them.
    expect(SEVERITY_STOREABLE).not.toContain("NONE");
    expect(SEVERITY_STOREABLE).not.toContain("ERROR");
  });

  it("keeps INFO out of the vocabulary: no column, no producer, no badge", () => {
    // INFO used to have its own neutral badge. Nothing in the product can
    // produce it, so the gloss was decoration nobody would ever see — and the
    // reason a reviewer trusted the map to be complete.
    expect(Object.keys(SEVERITIES)).not.toContain("INFO");
    expect(severityPill("INFO")).toEqual({ cls: "pill-mute", label: "未知 UNKNOWN" });
    expect(severityHint("INFO")).toBeUndefined();
  });

  it("ranks the storable severities most-actionable-first and sinks the unknown", () => {
    // JobDetail used to keep a private rank map with CRITICAL/HIGH/MEDIUM/LOW
    // (values that exist nowhere else) while NEEDS_CONFIRMATION was missing and
    // so sorted as unknown.
    expect(
      ["NEEDS_CONFIRMATION", "MINOR", "MAJOR", "BLOCKER"].map(severityRank)
    ).toEqual([3, 2, 1, 0]);
    expect(severityRank("CRITICAL")).toBe(99);
    expect(severityRank(undefined)).toBe(99);
    expect(severityRank("needs_confirmation")).toBe(3);
  });

  it("declares exactly the findings.severity values as voteable", () => {
    expect(SEVERITY_STOREABLE).toEqual(["BLOCKER", "MAJOR", "MINOR", "NEEDS_CONFIRMATION"]);
    for (const token of SEVERITY_STOREABLE) {
      expect(SEVERITIES[token].storeable).toBe(true);
    }
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
    for (const s of [...Object.keys(SEVERITIES), "BOGUS"]) {
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

describe("acceptSeverityLabel — 独立验收用的是另一套刻度 (#86)", () => {
  it("glosses the scanner scale without borrowing the verification ENUM's meanings", () => {
    expect(acceptSeverityLabel("CRITICAL")).toBe("关键（凭证已泄漏，计入验收阻断） · CRITICAL");
    expect(acceptSeverityLabel("high")).toContain("高危");
    expect(acceptSeverityLabel("MEDIUM")).toContain("不阻断验收");
    expect(acceptSeverityLabel("LOW")).toContain("不阻断验收");
    // Only these two are counted as blocking by craft's gates, so nothing else
    // may wear the blocking colour.
    expect(ACCEPT_SEVERITY_BLOCKING).toEqual(["CRITICAL", "HIGH"]);
    expect(acceptSeverityTone("CRITICAL")).toBe("bad");
    expect(acceptSeverityTone("BLOCKER")).toBe("mute");
  });

  it("passes an unrecognised severity through as written, and names a missing one", () => {
    expect(acceptSeverityLabel("wuzzy")).toBe("wuzzy");
    expect(acceptSeverityLabel("")).toBe("未记录严重程度");
    expect(acceptSeverityLabel(undefined)).toBe("未记录严重程度");
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
    // #87: the keys here are agent/evidence_kinds.py's declared domain, kept
    // equal by tests/unit/test_evidence_vocabulary_parity.py. runtime_test /
    // static / differential / review used to be glossed and are gone — nothing
    // in the product emits them.
    expect(evidenceLabel("java_source_diff")).toContain("Java 源码差分");
    expect(evidenceLabel("java_source_diff")).toContain("java_source_diff"); // token preserved
    expect(evidenceLabel("java_source_diff")).toMatch(/没有执行任何代码/);
    expect(evidenceLabel("base_pass_head_fail")).toContain("改前通过、改后失败");
    // A crashing checker must never read as "checked and clean".
    expect(evidenceLabel("checker_failed")).toMatch(/不等于没有问题/);
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

describe("attributionLabel — 差分归因 keeps its canonical token visible", () => {
  it("glosses the matrix_policy vocabulary and preserves the raw value", () => {
    // These are the only values agent/matrix_policy._merged_attribution can
    // emit; "head" is the one a reviewer must never mistake for a base bug.
    expect(attributionLabel("head")).toBe("本次变更引入 · head");
    expect(attributionLabel("base")).toBe("改前既有 · base");
    expect(attributionLabel("not_attributed")).toBe("无法归因 · not_attributed");
    expect(attributionLabel("none")).toBe("无需归因 · none");
    expect(attributionLabel("unknown")).toBe("归因未知 · unknown");
  });

  it("is case-insensitive because the pipeline stores lowercase words", () => {
    expect(attributionLabel("HEAD")).toBe("本次变更引入 · head");
  });

  it("passes an unrecognized value through verbatim instead of inventing one", () => {
    expect(attributionLabel("flake_suspected")).toBe("flake_suspected");
    expect(attributionLabel("flake_suspected")).not.toContain("归因未知");
  });

  it("renders missing as a dash, never as 无需归因", () => {
    // "none" already means "no attribution needed" — a missing value must not
    // borrow that meaning and imply a passing comparison.
    expect(attributionLabel(undefined)).toBe("—");
    expect(attributionLabel("   ")).toBe("—");
  });
});

describe("executionSurfaceLabel — where the change's own tests actually ran", () => {
  // This is a safety disclosure, not decoration: a host-surface differential
  // executed the untrusted change's own tests on the operator's machine.
  it("translates the three surfaces the pipeline can report, keeping the token", () => {
    expect(executionSurfaceLabel("docker_sandbox")).toBe("容器沙箱执行 · docker_sandbox");
    expect(executionSurfaceLabel("local_host_no_sandbox")).toBe(
      "本机执行 · 无沙箱 · local_host_no_sandbox"
    );
    expect(executionSurfaceLabel("unconfirmed")).toBe("执行面未确认 · unconfirmed");
  });

  it("passes an unknown surface through verbatim, never as 容器沙箱执行", () => {
    expect(executionSurfaceLabel("wasm_sandbox")).toBe("wasm_sandbox");
    expect(executionSurfaceLabel("wasm_sandbox")).not.toContain("容器沙箱");
  });

  it("returns empty for a missing surface so the caller renders nothing", () => {
    // Empty (not "容器沙箱执行") — an absent value must not become a reassurance.
    expect(executionSurfaceLabel(undefined)).toBe("");
    expect(executionSurfaceLabel(null)).toBe("");
    expect(executionSurfaceLabel("")).toBe("");
  });

  it("only grants the ok tone to a confirmed container run", () => {
    expect(executionSurfaceTone("docker_sandbox")).toBe("ok");
    expect(executionSurfaceTone("local_host_no_sandbox")).toBe("warn");
    // Unattributable fails closed, exactly like the backend's label derivation.
    expect(executionSurfaceTone("unconfirmed")).toBe("warn");
    expect(executionSurfaceTone(undefined)).toBe("mute");
    expect(executionSurfaceTone("wasm_sandbox")).toBe("mute");
  });
});
