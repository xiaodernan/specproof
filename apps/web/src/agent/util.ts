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
  execution_mode: "llm",
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

// Execution mode is an explicit API field. Preserve structured JSON specs;
// unsupported controls must never be hidden in a prose appendix.
export function buildSpecText(draft: WizardDraft): string {
  return draft.spec_text.trim();
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
    model_output: "模型实时输出",
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

export function approvalDecisionLabel(decision: string): string {
  const labels: Record<string, string> = {
    approve: "批准 Approve",
    reject: "拒绝 Reject",
  };
  return labels[decision] || decision;
}

export function approvalTargetLabel(target: string): string {
  const labels: Record<string, string> = {
    plan: "计划 Plan",
    step: "步骤 Step",
    gate: "门禁 Gate",
  };
  return labels[target] || target;
}

export function sseStateLabel(state: string): string {
  const labels: Record<string, string> = {
    connecting: "连接中 connecting",
    open: "已连接 open",
    closed: "已断开 closed",
    error: "连接错误 error",
  };
  return labels[state] || state;
}

export function diffFileStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    added: "新增 Added",
    modified: "修改 Modified",
    deleted: "删除 Deleted",
    renamed: "重命名 Renamed",
  };
  return labels[status] || status;
}

export function diffModeLabel(mode: string): string {
  const labels: Record<string, string> = {
    unified: "统一视图 unified",
    split: "分栏视图 split",
  };
  return labels[mode] || mode;
}

// ── Craft gate labels ───────────────────────────────────────────────────────
// Shared by the development result (job.result.gates) and the independent
// accept projection (job.accept.gates): both are GateResult.to_dict() rows
// from craft/gates.py, so one vocabulary must serve both. Unknown names and
// statuses pass through verbatim — an unrecognised gate is still evidence.

export const GATE_LABELS: Record<string, string> = {
  run_test: "相关测试",
  run_build: "项目构建",
  run_typecheck: "类型检查",
  security: "敏感信息检查",
  self_verify: "改动自检",
};

export const GATE_STATUS_LABELS: Record<string, string> = {
  passed: "通过",
  failed: "未通过",
  skipped: "未执行",
  error: "执行出错",
};

export function gateLabel(gate: string): string {
  return GATE_LABELS[gate] || gate || "未命名门禁";
}

export function gateStatusLabel(status: string): string {
  return GATE_STATUS_LABELS[status] || status || "状态未知";
}

/** Pill class for one gate status: only `passed` is green. */
export function gateStatusPillClass(status: string): string {
  if (status === "passed") return "pill pill-ok";
  if (status === "skipped") return "pill pill-mute";
  if (status === "failed" || status === "error") return "pill pill-bad";
  return "pill pill-mute";
}

// ── Accept projection verdict (W35.1) ───────────────────────────────────────

export interface AcceptVerdictMeta {
  label: string;
  tone: "ok" | "bad" | "warn" | "mute";
}

export type AcceptBlockedMeaning = "gate_failed" | "closure_deferred" | "unknown";

/**
 * `BLOCKED` is not one fact but two, and only the payload tells them apart.
 * `api/agent_runtime.py::_gate_accept_projection` emits BLOCKED both when an
 * internal gate FAILed (`gates.overall === "failed"`, findings aggregated)
 * and when every gate passed but the certificate closure was left to the
 * CLI. Reading the token alone would tell a reader whose checks failed that
 * nothing had failed — the mirror image of the false-red trap.
 */
export function acceptBlockedMeaning(
  gatesOverall: string | undefined
): AcceptBlockedMeaning {
  const overall = gatesOverall || "";
  if (overall === "failed") return "gate_failed";
  if (!overall || overall === "error") return "unknown";
  return "closure_deferred";
}

export function acceptBlockedNotice(meaning: AcceptBlockedMeaning): string {
  if (meaning === "gate_failed")
    return "此通道的 BLOCKED 来自内部门禁 FAIL：有门禁未通过（见下方逐条结果与关联发现），因此未签发合并证书。";
  if (meaning === "closure_deferred")
    return "此通道的 BLOCKED 表示门禁摘要已通过，但尚未签发合并证书（完整闭包需 git base/head 与签名密钥，由 craft accept 执行）。它不代表下方门禁未通过。";
  return "此通道的 BLOCKED 表示尚未签发合并证书，但投影里没有可用来判断原因的门禁摘要：本页无法区分“门禁未通过”与“闭包尚未执行”，请以上方说明或命令行为准。";
}

/**
 * The independent accept verdict. `BLOCKED` needs care: the runtime lane
 * NEVER issues `VERIFIED` (the merge certificate + signature belong to
 * `specproof craft accept`), so a plain gate summary that passed still
 * arrives as BLOCKED. Rendering that as a red "失败" would tell the reader
 * their code failed checks that actually passed — but the opposite blanket
 * assurance is just as wrong when a gate really did fail, so the tone is
 * taken from `gates.overall`, not from the token.
 */
export function acceptVerdictLabel(
  verdict: string | undefined,
  gatesOverall?: string
): AcceptVerdictMeta {
  const v = verdict || "";
  if (v === "VERIFIED") return { label: "已签发合并证书 VERIFIED", tone: "ok" };
  if (v === "BLOCKED") {
    if (acceptBlockedMeaning(gatesOverall) === "gate_failed")
      return { label: "门禁未通过，未签发合并证书 BLOCKED", tone: "bad" };
    return { label: "未签发合并证书 BLOCKED", tone: "warn" };
  }
  if (v === "ERROR") return { label: "验收过程出错 ERROR", tone: "bad" };
  return { label: v || "无结论", tone: "mute" };
}
