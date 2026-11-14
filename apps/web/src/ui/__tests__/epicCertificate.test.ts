import { describe, expect, it } from "vitest";

import { buildEpicCertificate } from "../epicCertificate";

// 史诗验收纪要：把一次验证装订成可读给全产品的「卷宗」。
// 所有数字来自服务器返回值——缺什么就写（未提供），绝不编造。
describe("buildEpicCertificate", () => {
  const job = {
    id: "job-abc-123",
    base_ref: "base",
    head_ref: "head-v1",
    repo_path: "/repo",
    spec_path: "specs/AUTH-01.md",
    status: "VERIFIED",
    created_at: "2026-11-14T00:00:00Z",
  };

  it("assembles a complete certificate from a full payload", () => {
    const md = buildEpicCertificate({
      job,
      summary: { verdict: "BLOCKED", contracts_total: 3, matrix_passed: 1, matrix_failed: 2, matrix_unverified: 0, errors: [] },
      findings: [
        { severity: "BLOCKER", contract_id: "AUTH-01", evidence_type: "base_pass_head_fail" },
        { severity: "MAJOR", contract_id: "UNIQUE-01", evidence_type: "static_analysis" },
      ],
    });
    expect(md).toContain("史诗验收纪要 · job-abc-123");
    expect(md).toContain("受阻");
    expect(md).toContain("3 项（1 通过 / 2 未通过 / 0 未验证）");
    expect(md).toContain("**BLOCKER**");
    expect(md).toContain("AUTH-01 · base_pass_head_fail（BLOCKER）");
    expect(md).toContain("不是人工裁决");
  });

  it("renders the honest empty finding state without inventing a win", () => {
    const md = buildEpicCertificate({
      job,
      summary: { verdict: "VERIFIED", contracts_total: 2, matrix_passed: 2, matrix_failed: 0, matrix_unverified: 0, errors: [] },
      findings: [],
    });
    expect(md).toContain("此卷无发现");
    expect(md).toContain("缺什么铁证，就该补什么证据");
    expect(md).not.toContain("**BLOCKER**");
  });

  it("renders （未提供） for missing fields — never a fabricated zero", () => {
    const md = buildEpicCertificate({
      job: { id: "job-x" },
      summary: null,
      findings: [],
    });
    expect(md).toContain("job-x");
    expect(md).toContain("（未提供）");
    expect(md).not.toMatch(/0 项（0 通过/);
  });

  it("always carries the machine-generated, not-human-verdict marker", () => {
    const md = buildEpicCertificate({ job, summary: null, findings: [] });
    expect(md).toContain("机器拼奏");
    expect(md).toContain("不是人工裁决");
  });
});
