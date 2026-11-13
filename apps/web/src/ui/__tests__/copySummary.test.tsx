import { describe, expect, it } from "vitest";
import { buildMarkdownSummary } from "../copySummary";

const job = {
  id: "verify-abc123",
  base_ref: "main",
  head_ref: "feature-x",
  repo_path: "/srv/repos/orders",
  spec_path: "/srv/repos/orders/spec.md",
  status: "succeeded",
  created_at: 1_700_000_000,
};

describe("buildMarkdownSummary", () => {
  it("renders the full digest for a clean verdict with no findings", () => {
    const md = buildMarkdownSummary({
      job,
      summary: {
        verdict: "VERIFIED",
        contracts_total: 3,
        matrix_passed: 3,
        matrix_failed: 0,
        matrix_unverified: 0,
        errors: [],
      },
      findings: [],
    });
    expect(md).toContain("## SpecProof 验收：verify-abc123");
    expect(md).toContain("VERIFIED");
    expect(md).toContain("/srv/repos/orders");
    expect(md).toContain("3 项（3 通过 / 0 未通过 / 0 未验证）");
    expect(md).toContain("（未提供）（无发现）");
    expect(md).toContain("#/jobs/verify-abc123");
    expect(md).not.toContain("undefined");
  });

  it("marks every missing field as（未提供）rather than invent anything", () => {
    const md = buildMarkdownSummary({
      job: { id: "verify-x", head_ref: "feature-y" },
      summary: null,
      findings: [],
    });
    expect(md).toContain("（未提供）");
    expect(md).not.toContain("undefined");
    expect(md).not.toContain("null");
  });

  it("counts findings by severity and surfaces BLOCKER details", () => {
    const md = buildMarkdownSummary({
      job,
      summary: {
        verdict: "BLOCKER",
        contracts_total: 2,
        matrix_passed: 1,
        matrix_failed: 1,
        matrix_unverified: 0,
        errors: [],
      },
      findings: [
        { severity: "BLOCKER", contract_id: "AUTH-01", evidence_type: "base_pass_head_fail" },
        { severity: "MAJOR", contract_id: "UNIQUE-01", evidence_type: "static_analysis" },
      ],
    });
    expect(md).toContain("BLOCKER");
    expect(md).toContain("1 项");
    expect(md).toContain("AUTH-01 · base_pass_head_fail");
  });
});
