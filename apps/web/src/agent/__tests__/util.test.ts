import { describe, expect, it } from "vitest";
import {
  EMPTY_WIZARD_DRAFT,
  WizardDraft,
  aggregateApprovals,
  buildSpecText,
  diffFileStatusLabel,
  diffModeLabel,
  eventKindLabel,
  approvalDecisionLabel,
  approvalTargetLabel,
  sseStateLabel,
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
  it("preserves plain or JSON specs without unsupported constraint appendices", () => {
    expect(buildSpecText(draft({ spec_text: "  add pagination  " }))).toBe("add pagination");
    expect(buildSpecText(draft({ spec_text: '{"title":"test"}' }))).toBe('{"title":"test"}');
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

describe("diff status/mode labels", () => {
  it("maps known diff file statuses with a Chinese gloss", () => {
    expect(diffFileStatusLabel("added")).toBe("新增 Added");
    expect(diffFileStatusLabel("modified")).toBe("修改 Modified");
    expect(diffFileStatusLabel("deleted")).toBe("删除 Deleted");
    expect(diffFileStatusLabel("renamed")).toBe("重命名 Renamed");
  });

  it("passes unknown diff file statuses through verbatim", () => {
    expect(diffFileStatusLabel("copied")).toBe("copied");
    expect(diffFileStatusLabel("")).toBe("");
  });

  it("maps known diff modes", () => {
    expect(diffModeLabel("unified")).toBe("统一视图 unified");
    expect(diffModeLabel("split")).toBe("分栏视图 split");
  });

  it("passes unknown diff modes through verbatim", () => {
    expect(diffModeLabel("side-by-side")).toBe("side-by-side");
  });
});

describe("approval/sse labels", () => {
  it("maps approval decisions and passes unknowns through", () => {
    expect(approvalDecisionLabel("approve")).toBe("批准 Approve");
    expect(approvalDecisionLabel("reject")).toBe("拒绝 Reject");
    expect(approvalDecisionLabel("maybe")).toBe("maybe");
  });

  it("maps approval targets and passes unknowns through", () => {
    expect(approvalTargetLabel("plan")).toBe("计划 Plan");
    expect(approvalTargetLabel("step")).toBe("步骤 Step");
    expect(approvalTargetLabel("gate")).toBe("门禁 Gate");
    expect(approvalTargetLabel("mystery")).toBe("mystery");
  });

  it("maps SSE connection states and passes unknowns through", () => {
    expect(sseStateLabel("connecting")).toBe("连接中 connecting");
    expect(sseStateLabel("open")).toBe("已连接 open");
    expect(sseStateLabel("closed")).toBe("已断开 closed");
    expect(sseStateLabel("reconnecting")).toBe("reconnecting");
  });
});
