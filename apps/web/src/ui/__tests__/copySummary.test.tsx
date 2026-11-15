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

  it("produces a Chinese digest with zero EnglishResidue bleeding into the prose", () => {
    const md = buildMarkdownSummary(
      {
        job,
        summary: {
          verdict: "VERIFIED",
          contracts_total: 2,
          matrix_passed: 2,
          matrix_failed: 0,
          matrix_unverified: 0,
          errors: [],
        },
        findings: [
          { severity: "MAJOR", contract_id: "UNIQUE-01", evidence_type: "static_analysis" },
        ],
      },
      "zh",
    );
    expect(md).toContain("## SpecProof 验收");
    // English-prose-only phrases must not appear in zh output
    expect(md).not.toContain("Verdict");
    expect(md).not.toContain("Risk findings");
    expect(md).not.toContain("not provided");
    expect(md).not.toContain("Reproduction capsule");
    // product tokens that must survive both locales
    expect(md).toContain("#/jobs/verify-abc123");
  });

  it("renders a complete digest in English, not a translated hybrid", () => {
    const md = buildMarkdownSummary(
      {
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
        ],
      },
      "en",
    );
    expect(md).toContain("## SpecProof verification: verify-abc123");
    expect(md).toContain("Verdict: **BLOCKER**");
    expect(md).toContain("Acceptance contracts: 2 (1 passed / 1 failed / 0 unverified)");
    expect(md).toContain("### Risk findings");
    expect(md).toContain("AUTH-01");
    expect(md).toContain("Reproduction capsule");
    expect(md).not.toContain("验收");
    expect(md).not.toContain("未提供");
    expect(md).not.toContain("undefined");
  });

  it("caps the findings list at five entries but keeps severity counts exact", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({
      severity: i < 3 ? "MAJOR" : "MINOR",
      contract_id: `CONTRACT-${String(i + 1).padStart(2, "0")}`,
      evidence_type: "static_analysis",
    }));
    const md = buildMarkdownSummary(
      {
        job,
        summary: {
          verdict: "NEEDS_REVIEW",
          contracts_total: 2,
          matrix_passed: 2,
          matrix_failed: 0,
          matrix_unverified: 0,
          errors: [],
        },
        findings: many,
      },
      "en",
    );
    expect(md).toContain("**MAJOR**: 3");
    expect(md).toContain("**MINOR**: 5");
    expect(md).toContain("CONTRACT-05");
    expect(md).not.toContain("CONTRACT-06");
  });

  it("keeps an unknown severity visible verbatim instead of inventing a tier", () => {
    const md = buildMarkdownSummary(
      {
        job,
        summary: {
          verdict: "VERIFIED",
          contracts_total: 1,
          matrix_passed: 1,
          matrix_failed: 0,
          matrix_unverified: 0,
          errors: [],
        },
        findings: [{ severity: "deep-weird", contract_id: "X-C1", evidence_type: "mystery" }],
      },
      "en",
    );
    expect(md).toContain("**DEEP-WEIRD**");
    expect(md).toContain("1");
    expect(md).not.toContain("undefined");
  });

  it("renders the literal job id even when every optional field is missing", () => {
    const md = buildMarkdownSummary({ job: { id: "bare-1" }, summary: null, findings: [] }, "en");
    expect(md).toContain("## SpecProof verification: bare-1");
    expect(md).toContain("#/jobs/bare-1");
    expect(md).toContain("(not provided)");
    expect(md).not.toContain("undefined");
    expect(md).not.toContain("null");
  });

  it("emits job-branch-to-job-branch verbatim regardless of which ref is right", () => {
    const md = buildMarkdownSummary(
      {
        job: { id: "j-8", base_ref: "a", head_ref: "b", created_at: 1_700_000_000 },
        summary: null,
        findings: [],
      },
      "zh",
    );
    expect(md).toContain("#/jobs/j-8");
    expect(md).toContain("`a` → `b`");
  });

  it("renders an explicit locale argument even over a stored preference", () => {
    try {
      window.localStorage.setItem("specproof_locale", "zh");
      const md = buildMarkdownSummary(
        {
          job,
          summary: {
            verdict: "VERIFIED",
            contracts_total: 1,
            matrix_passed: 1,
            matrix_failed: 0,
            matrix_unverified: 0,
            errors: [],
          },
          findings: [],
        },
        "en",
      );
      expect(md).toContain("## SpecProof verification");
      expect(md).not.toContain("验收");
    } finally {
      window.localStorage.removeItem("specproof_locale");
    }
  });

  it("uses the stored zh preference when no locale argument is passed", () => {
    try {
      window.localStorage.setItem("specproof_locale", "zh");
      const md = buildMarkdownSummary({
        job,
        summary: {
          verdict: "VERIFIED",
          contracts_total: 1,
          matrix_passed: 1,
          matrix_failed: 0,
          matrix_unverified: 0,
          errors: [],
        },
        findings: [],
      });
      expect(md).toContain("## SpecProof 验收");
    } finally {
      window.localStorage.removeItem("specproof_locale");
    }
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
