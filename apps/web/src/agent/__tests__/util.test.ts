import { describe, expect, it } from "vitest";
import {
  EMPTY_WIZARD_DRAFT,
  WizardDraft,
  aggregateApprovals,
  buildSpecText,
  eventKindLabel,
  rowsForFile,
  validateRepoStep,
  validateSpecStep,
} from "../util";
import { AgentApproval, AgentDiffFile } from "../../api";

function draft(patch: Partial<WizardDraft>): WizardDraft {
  return { ...EMPTY_WIZARD_DRAFT, ...patch };
}

describe("wizard validation", () => {
  it("rejects an empty repo path", () => {
    expect(validateRepoStep(draft({ repo_path: "  " }))).not.toBeNull();
  });

  it("accepts a repo path", () => {
    expect(validateRepoStep(draft({ repo_path: "D:/repos/svc" }))).toBeNull();
  });

  it("rejects an empty spec", () => {
    expect(validateSpecStep(draft({ spec_text: "" }))).not.toBeNull();
  });

  it("rejects an oversized spec", () => {
    expect(validateSpecStep(draft({ spec_text: "x".repeat(200001) }))).not.toBeNull();
  });

  it("accepts a normal spec", () => {
    expect(validateSpecStep(draft({ spec_text: "add pagination" }))).toBeNull();
  });
});

describe("buildSpecText", () => {
  it("appends the gate constraints block", () => {
    const spec = buildSpecText(
      draft({
        spec_text: "add pagination",
        gates: { run_tests: true, run_lint: false, run_typecheck: true, require_gate: false },
        budget_minutes: 45,
        max_steps: 8,
      })
    );
    expect(spec).toContain("add pagination");
    expect(spec).toContain("SPECPROOF WIZARD CONSTRAINTS");
    expect(spec).toContain("budget_minutes: 45");
    expect(spec).toContain("max_steps: 8");
    expect(spec).toContain("gates: run_tests,run_typecheck");
  });

  it("renders 'none' when every gate is off", () => {
    const spec = buildSpecText(
      draft({
        gates: { run_tests: false, run_lint: false, run_typecheck: false, require_gate: false },
      })
    );
    expect(spec).toContain("gates: none");
  });
});

describe("rowsForFile", () => {
  const file: AgentDiffFile = {
    path: "a.py",
    status: "modified",
    insertions: 1,
    deletions: 1,
    hunks: [
      {
        old_start: 1,
        old_count: 2,
        new_start: 1,
        new_count: 2,
        lines: [
          { type: "context", old_no: 1, new_no: 1, text: "def f():" },
          { type: "del", old_no: 2, new_no: null, text: "    old" },
          { type: "add", old_no: null, new_no: 2, text: "    new" },
        ],
      },
    ],
  };

  it("flattens hunks into ordered rows with keys", () => {
    const rows = rowsForFile(file);
    expect(rows.map((r) => r.type)).toEqual(["context", "del", "add"]);
    expect(rows.map((r) => r.key)).toEqual(["0:0", "0:1", "0:2"]);
  });
});

describe("aggregateApprovals", () => {
  const a1: AgentApproval = {
    id: "a1",
    job_id: "j1",
    target: "plan",
    step_index: null,
    decision: "approve",
    note: null,
    actor: "console",
    created_at: "2026-08-18T10:00:00+00:00",
  };
  const a2: AgentApproval = {
    id: "a2",
    job_id: "j2",
    target: "gate",
    step_index: null,
    decision: "reject",
    note: "tests red",
    actor: "console",
    created_at: "2026-08-18T11:00:00+00:00",
  };

  it("merges per-job records newest first", () => {
    const all = aggregateApprovals([
      { job_id: "j1", approvals: [a1] },
      { job_id: "j2", approvals: [a2] },
    ]);
    expect(all.map((a) => a.id)).toEqual(["a2", "a1"]);
  });

  it("returns empty for no records", () => {
    expect(aggregateApprovals([])).toEqual([]);
  });
});

describe("eventKindLabel", () => {
  it("maps known event types", () => {
    expect(eventKindLabel("tool_call")).toBe("工具调用 Tool call");
    expect(eventKindLabel("plan")).toBe("计划 Plan");
    expect(eventKindLabel("unknown")).toBe("unknown");
  });
});
