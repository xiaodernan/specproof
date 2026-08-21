// Pure helpers for the SpecCraft agent console (unit-testable, no DOM).

import { AgentApproval, AgentDiffFile } from "../api";

export interface AgentStatusMeta {
  label: string;
  tone: "ok" | "bad" | "warn" | "info" | "mute";
}

export const AGENT_STATUS_META: Record<string, AgentStatusMeta> = {
  PLANNING: { label: "规划中 Planning", tone: "info" },
  AWAITING_APPROVAL: { label: "等待审批 Awaiting approval", tone: "warn" },
  EXECUTING: { label: "执行中 Executing", tone: "info" },
  COMPLETED: { label: "已完成 Completed", tone: "ok" },
  FAILED: { label: "失败 Failed", tone: "bad" },
  CANCELLED: { label: "已取消 Cancelled", tone: "mute" },
};

export function agentStatusMeta(status: string | undefined): AgentStatusMeta {
  return AGENT_STATUS_META[status || ""] || { label: status || "UNKNOWN", tone: "mute" };
}

// ── New-job wizard ──────────────────────────────────────────────────────────

export interface WizardGates {
  run_tests: boolean;
  run_lint: boolean;
  run_typecheck: boolean;
  require_gate: boolean;
}

export type WizardExecutionMode = "deterministic" | "llm";

export interface WizardDraft {
  repo_path: string;
  base_ref: string;
  head_ref: string;
  task_name: string;
  spec_text: string;
  execution_mode: WizardExecutionMode;
  gates: WizardGates;
  budget_minutes: number;
  max_steps: number;
}

export const EMPTY_WIZARD_DRAFT: WizardDraft = {
  repo_path: "",
  base_ref: "",
  head_ref: "",
  task_name: "",
  spec_text: "",
  execution_mode: "deterministic",
  gates: { run_tests: true, run_lint: true, run_typecheck: true, require_gate: true },
  budget_minutes: 60,
  max_steps: 12,
};

const WIZARD_KEY = "specproof_agent_wizard";

export function loadWizardDraft(): WizardDraft {
  try {
    const raw = window.sessionStorage.getItem(WIZARD_KEY);
    if (!raw) return { ...EMPTY_WIZARD_DRAFT };
    const parsed = JSON.parse(raw) as Partial<WizardDraft>;
    return { ...EMPTY_WIZARD_DRAFT, ...parsed };
  } catch {
    return { ...EMPTY_WIZARD_DRAFT };
  }
}

export function saveWizardDraft(draft: WizardDraft): void {
  try {
    window.sessionStorage.setItem(WIZARD_KEY, JSON.stringify(draft));
  } catch {
    // storage unavailable; draft lives in component state only
  }
}

export function clearWizardDraft(): void {
  try {
    window.sessionStorage.removeItem(WIZARD_KEY);
  } catch {
    // ignore
  }
}

export function validateRepoStep(draft: WizardDraft): string | null {
  if (!draft.repo_path.trim()) return "仓库路径不能为空 Repo path required";
  if (draft.repo_path.trim().length > 1024) return "仓库路径过长 (≤1024)";
  return null;
}

export function validateSpecStep(draft: WizardDraft): string | null {
  if (!draft.spec_text.trim()) return "需求规格不能为空 Spec text required";
  if (draft.spec_text.length > 200000) return "需求规格过长 (≤200000 字符)";
  return null;
}

// The backend only persists repo_path + spec_text today; the gate options
// travel as an explicit constraints block appended to the spec so nothing
// the user configured is silently dropped.
export function buildSpecText(draft: WizardDraft): string {
  const g = draft.gates;
  const gates = [
    g.run_tests ? "run_tests" : null,
    g.run_lint ? "run_lint" : null,
    g.run_typecheck ? "run_typecheck" : null,
    g.require_gate ? "require_gate_approval" : null,
  ].filter((x): x is string => x !== null);
  const appendix =
    "\n\n--- SPECPROOF WIZARD CONSTRAINTS ---\n" +
    "base_ref: " + (draft.base_ref.trim() || "(unset)") + "\n" +
    "head_ref: " + (draft.head_ref.trim() || "(unset)") + "\n" +
    "execution_mode: " + draft.execution_mode + "\n" +
    "budget_minutes: " + draft.budget_minutes + "\n" +
    "max_steps: " + draft.max_steps + "\n" +
    "gates: " + (gates.length > 0 ? gates.join(",") : "none") + "\n";
  return draft.spec_text.trimEnd() + appendix;
}

// ── Diff rendering ──────────────────────────────────────────────────────────

export interface DiffRenderRow {
  key: string;
  type: "add" | "del" | "context";
  oldNo: number | null;
  newNo: number | null;
  text: string;
}

export function rowsForFile(file: AgentDiffFile): DiffRenderRow[] {
  const rows: DiffRenderRow[] = [];
  file.hunks.forEach((hunk, hi) => {
    hunk.lines.forEach((line, li) => {
      rows.push({
        key: hi + ":" + li,
        type: line.type,
        oldNo: line.old_no,
        newNo: line.new_no,
        text: line.text,
      });
    });
  });
  return rows;
}

// ── Approvals inbox aggregation ─────────────────────────────────────────────

export function aggregateApprovals(
  perJob: { job_id: string; approvals: AgentApproval[] }[]
): AgentApproval[] {
  const all = perJob.flatMap((entry) => entry.approvals);
  return all.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
}

// ── Event / step labels ─────────────────────────────────────────────────────

export function eventKindLabel(type: string): string {
  const labels: Record<string, string> = {
    plan: "计划 Plan",
    tool_call: "工具调用 Tool call",
    tool_result: "工具结果 Tool result",
    edit: "编辑 Edit",
    gate: "门禁 Gate",
    progress: "进度 Progress",
  };
  return labels[type] || type;
}

export function stepStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "待审 Pending",
    approved: "已批准 Approved",
    rejected: "已拒绝 Rejected",
  };
  return labels[status] || status;
}
