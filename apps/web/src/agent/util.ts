// Pure helpers for the SpecCraft agent console (unit-testable, no DOM).

import { AgentApproval, AgentDiffFile } from "../api";
import { STRINGS, storedLocale } from "../i18n/strings";

// Console labels are rendered per stored locale — zh mode shows 规划中, en mode
// shows Planning; never a mixed "规划中 Planning" string on a screen.
// AGENT_STATUS_META itself stays the verbatim mirror of the backend's
// STATUS_LABELS (pinned by tests/unit/test_agent_console_terminal_vocabulary_parity.py)
// and is not rendered directly anymore.
const isZh = (): boolean => storedLocale() === "zh";
function gloss(key: string): string {
  return STRINGS[isZh() ? "zh" : "en"][key] ?? key;
}

export interface AgentStatusMeta {
  label: string;
  tone: "ok" | "bad" | "warn" | "info" | "mute";
}

export const AGENT_STATUS_META: Record<string, AgentStatusMeta> = {
  PLANNING: { label: "规划中 Planning", tone: "info" },
  AWAITING_APPROVAL: { label: "等待计划审批 Awaiting approval", tone: "warn" },
  EXECUTING: { label: "执行中 Executing", tone: "info" },
  COMPLETED: { label: "已完成 Completed", tone: "ok" },
  FAILED: { label: "失败 Failed", tone: "bad" },
  CANCELLED: { label: "已取消 Cancelled", tone: "mute" },
};

const AGENT_STATUS_GLOSS: Record<string, { zh: string; en: string }> = {
  PLANNING: { zh: "规划中", en: "Planning" },
  AWAITING_APPROVAL: { zh: "等待计划审批", en: "Awaiting approval" },
  EXECUTING: { zh: "执行中", en: "Executing" },
  COMPLETED: { zh: "已完成", en: "Completed" },
  FAILED: { zh: "失败", en: "Failed" },
  CANCELLED: { zh: "已取消", en: "Cancelled" },
};

export function agentStatusMeta(status: string | undefined): AgentStatusMeta {
  const token = status || "";
  const tone = AGENT_STATUS_META[token]?.tone ?? "mute";
  const glossed = AGENT_STATUS_GLOSS[token];
  if (glossed) return { label: isZh() ? glossed.zh : glossed.en, tone };
  if (!token) return { label: gloss("ui.unknown"), tone: "mute" };
  return { label: token, tone: "mute" };
}

// ── Run phase (the terminal/active split the console pages gate on) ─────────
//
// `api/agent_runtime.py::console_status_label` is the single source of the
// console vocabulary, and since #69 its last line is `return str(job.status)`:
// a store status outside the mapping reaches the browser VERBATIM (its own
// docstring promises "the UI's own unknown handling decides how to show it").
// That promise is only kept if the page can tell three things apart — a run
// still going, a run that ended, and a token this vocabulary does not hold.
// Gating on `!terminal` would answer the third case with "still running",
// which is the same invention #69 removed on the backend.
//
// The terminal list is the one the API enforces: `_require_cancellable` and
// the approvals route both refuse on membership in
// `api/routes/agent_console.py::_TERMINAL_CONSOLE_STATUSES`. The active list is
// therefore the COMPLEMENT of that set over the console vocabulary — which is
// exactly what the cancel rule allows, so the gate checks it against the rule
// rather than against a second declaration. (A `_CANCELLABLE_STATUSES` copy used
// to live on the backend; nothing read it and it was deleted in #173-1, with a
// clause here that fails if one comes back.)
//
// Both lists, plus `AGENT_STATUS_META` against the mapped tokens, are pinned
// by `tests/unit/test_agent_console_terminal_vocabulary_parity.py`; the pages
// import these helpers instead of writing a sixth copy.

export const AGENT_ACTIVE_STATUSES: readonly string[] = [
  "PLANNING",
  "AWAITING_APPROVAL",
  "EXECUTING",
];

export const AGENT_TERMINAL_STATUSES: readonly string[] = [
  "COMPLETED",
  "FAILED",
  "CANCELLED",
];

export type AgentRunPhase = "active" | "terminal" | "unknown";

export function agentRunPhase(status: string | undefined): AgentRunPhase {
  const token = status || "";
  if (AGENT_TERMINAL_STATUSES.includes(token)) return "terminal";
  if (AGENT_ACTIVE_STATUSES.includes(token)) return "active";
  return "unknown";
}

export function isAgentTerminal(status: string | undefined): boolean {
  return agentRunPhase(status) === "terminal";
}

/**
 * The page's own words for a status token it does not hold. Empty for known
 * values, so callers can append it unconditionally.
 */
export function agentUnknownNotice(status: string | undefined): string {
  if (agentRunPhase(status) !== "unknown") return "";
  return isZh()
    ? `这一轮上报的状态「${status || "空"}」不在本页的词表里：` +
      "无法判断它是否已经结束，因此这里既不按“仍在执行”处理，也不按“已终态”处理。"
    : `The status “${status || "unknown"}” reported this round is not in this page's vocabulary: ` +
      "whether it has ended cannot be determined — it is treated neither as “still running” nor as “terminal”.";
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
  if (!draft.repo_path.trim()) return isZh() ? "仓库路径不能为空" : "Repo path is required";
  if (draft.repo_path.trim().length > 1024) return isZh() ? "仓库路径过长 (≤1024)" : "Repo path too long (≤1024)";
  return null;
}

export function validateSpecStep(draft: WizardDraft): string | null {
  if (!draft.spec_text.trim()) return isZh() ? "需求规格不能为空" : "Spec text is required";
  if (draft.spec_text.length > 200000) return isZh() ? "需求规格过长 (≤200000 字符)" : "Spec text too long (≤200,000 chars)";
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

/**
 * The canonical vocabulary of SSE event kinds emitted by the agent console.
 * Hoisted from the function body so structure gates and readers can enumerate
 * it without calling the labeler. Unknown tokens pass through verbatim — an
 * unrecognised kind is still evidence, not a lie.
 */
const EVENT_KIND_GLOSS: Record<string, { zh: string; en: string }> = {
  plan: { zh: "计划", en: "Plan" },
  tool_call: { zh: "工具调用", en: "Tool call" },
  tool_result: { zh: "工具结果", en: "Tool result" },
  edit: { zh: "编辑", en: "Edit" },
  gate: { zh: "门禁", en: "Gate" },
  progress: { zh: "进度", en: "Progress" },
  model_output: { zh: "模型实时输出", en: "Model output" },
};

export function eventKindLabel(type: string): string {
  const g = EVENT_KIND_GLOSS[type];
  return g ? (isZh() ? g.zh : g.en) : type;
}

const STEP_STATUS_GLOSS: Record<string, { zh: string; en: string }> = {
  pending: { zh: "待审", en: "Pending" },
  approved: { zh: "已批准", en: "Approved" },
  rejected: { zh: "已拒绝", en: "Rejected" },
};
export function stepStatusLabel(status: string): string {
  const g = STEP_STATUS_GLOSS[status];
  return g ? (isZh() ? g.zh : g.en) : status;
}

const APPROVAL_DECISION_GLOSS: Record<string, { zh: string; en: string }> = {
  approve: { zh: "批准", en: "Approve" },
  reject: { zh: "拒绝", en: "Reject" },
};
export function approvalDecisionLabel(decision: string): string {
  const g = APPROVAL_DECISION_GLOSS[decision];
  return g ? (isZh() ? g.zh : g.en) : decision;
}

const APPROVAL_TARGET_GLOSS: Record<string, { zh: string; en: string }> = {
  plan: { zh: "计划", en: "Plan" },
  step: { zh: "步骤", en: "Step" },
  gate: { zh: "门禁", en: "Gate" },
};
export function approvalTargetLabel(target: string): string {
  const g = APPROVAL_TARGET_GLOSS[target];
  return g ? (isZh() ? g.zh : g.en) : target;
}

const SSE_STATE_GLOSS: Record<string, { zh: string; en: string }> = {
  connecting: { zh: "连接中", en: "connecting" },
  open: { zh: "已连接", en: "open" },
  closed: { zh: "已断开", en: "closed" },
  error: { zh: "连接错误", en: "error" },
};
export function sseStateLabel(state: string): string {
  const g = SSE_STATE_GLOSS[state];
  return g ? (isZh() ? g.zh : g.en) : state;
}

const DIFF_FILE_STATUS_GLOSS: Record<string, { zh: string; en: string }> = {
  added: { zh: "新增", en: "Added" },
  modified: { zh: "修改", en: "Modified" },
  deleted: { zh: "删除", en: "Deleted" },
  renamed: { zh: "重命名", en: "Renamed" },
};
export function diffFileStatusLabel(status: string): string {
  const g = DIFF_FILE_STATUS_GLOSS[status];
  return g ? (isZh() ? g.zh : g.en) : status;
}

const DIFF_MODE_GLOSS: Record<string, { zh: string; en: string }> = {
  unified: { zh: "统一视图", en: "Unified view" },
  split: { zh: "分栏视图", en: "Split view" },
};
export function diffModeLabel(mode: string): string {
  const g = DIFF_MODE_GLOSS[mode];
  return g ? (isZh() ? g.zh : g.en) : mode;
}

// ── Craft gate labels ───────────────────────────────────────────────────────
// Shared by the development result (job.result.gates) and the independent
// accept projection (job.accept.gates): both are GateResult.to_dict() rows
// from craft/gates.py, so one vocabulary must serve both. Unknown names and
// statuses pass through verbatim — an unrecognised gate is still evidence.

const GATE_GLOSS: Record<string, { zh: string; en: string }> = {
  run_test: { zh: "相关测试", en: "Related tests" },
  run_build: { zh: "项目构建", en: "Project build" },
  run_typecheck: { zh: "类型检查", en: "Type check" },
  security: { zh: "敏感信息检查", en: "Secrets scan" },
  self_verify: { zh: "改动自检", en: "Self verification" },
};

const GATE_STATUS_GLOSS: Record<string, { zh: string; en: string }> = {
  passed: { zh: "通过", en: "Passed" },
  failed: { zh: "未通过", en: "Failed" },
  skipped: { zh: "未执行", en: "Skipped" },
  error: { zh: "执行出错", en: "Error" },
};

export function gateLabel(gate: string): string {
  const g = GATE_GLOSS[gate];
  if (g) return isZh() ? g.zh : g.en;
  return gate || (isZh() ? "未命名门禁" : "Unnamed gate");
}

export function gateStatusLabel(status: string): string {
  const g = GATE_STATUS_GLOSS[status];
  if (g) return isZh() ? g.zh : g.en;
  return status || (isZh() ? "状态未知" : "Unknown status");
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
    return isZh()
      ? "此通道的 BLOCKED 来自内部门禁 FAIL：有门禁未通过（见下方逐条结果与关联发现），因此未签发合并证书。"
      : "This channel's BLOCKED comes from an internal gate FAIL: at least one gate did not pass (see the per-gate results and linked findings below), so no merge certificate was issued.";
  if (meaning === "closure_deferred")
    return isZh()
      ? "此通道的 BLOCKED 表示门禁摘要已通过，但尚未签发合并证书（完整闭包需 git base/head 与签名密钥，由 craft accept 执行）。它不代表下方门禁未通过。"
      : "This channel's BLOCKED means the gate summary passed but no merge certificate was issued yet (the full closure needs git base/head and signing keys, performed by craft accept). It does NOT mean a gate below failed.";
  return isZh()
    ? "此通道的 BLOCKED 表示尚未签发合并证书，但投影里没有可用来判断原因的门禁摘要：本页无法区分“门禁未通过”与“闭包尚未执行”，请以上方说明或命令行为准。"
    : "This channel's BLOCKED means no merge certificate was issued, but the projection carries no gate summary to judge the cause: this page cannot tell “a gate failed” from “the closure has not run yet” — defer to the notes above or the command line.";
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
  if (v === "VERIFIED")
    return { label: isZh() ? "已签发合并证书" : "Merge certificate issued", tone: "ok" };
  if (v === "BLOCKED") {
    if (acceptBlockedMeaning(gatesOverall) === "gate_failed")
      return { label: isZh() ? "门禁未通过，未签发合并证书" : "Gate failed — no merge certificate", tone: "bad" };
    return { label: isZh() ? "未签发合并证书" : "No merge certificate", tone: "warn" };
  }
  if (v === "ERROR")
    return { label: isZh() ? "验收过程出错" : "Verification errored", tone: "bad" };
  return { label: v || (isZh() ? "无结论" : "No verdict"), tone: "mute" };
}
