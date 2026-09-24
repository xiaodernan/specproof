// Onboarding checklist state (Phase 3.3 second half).
//
// Pure and DOM-free so the honesty rules are unit-testable: a step may only
// read as "done" when something actually observed it, and a signal we could
// not read must stay "unknown" instead of falling back to "not started".

export type OnboardingEvidence = "detected" | "manual";

export type OnboardingStepId =
  | "connect"
  | "prepare_spec"
  | "create_verification"
  | "read_results";

export interface OnboardingStep {
  id: OnboardingStepId;
  title: string;
  evidence: OnboardingEvidence;
  /** What the reader is told the completion mark is based on. */
  basis: string;
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: "connect",
    title: "启动并连接工作区",
    evidence: "detected",
    basis: "本页成功读到了一次后端请求",
  },
  {
    id: "prepare_spec",
    title: "准备一份可验收的需求",
    evidence: "manual",
    basis: "系统看不到你手头的文档，只能由你自己确认",
  },
  {
    id: "create_verification",
    title: "新建验证，选定比较范围",
    evidence: "detected",
    basis: "工作区里已经存在验证任务",
  },
  {
    id: "read_results",
    title: "看结论，也看依据",
    evidence: "detected",
    basis: "本机记录到你打开过某次验证的结果页（仅浏览记录）",
  },
];

// ── Persisted progress ──────────────────────────────────────────────────────

export interface OnboardingProgress {
  /** stepId -> ISO timestamp of when the user ticked it */
  manual: Record<string, string>;
  /** observed route key -> ISO timestamp */
  visited: Record<string, string>;
}

export const EMPTY_PROGRESS: OnboardingProgress = { manual: {}, visited: {} };

const STORAGE_KEY = "specproof_onboarding_v1";

export type ProgressReadStatus = "ok" | "absent" | "unreadable";

export interface ProgressRead {
  status: ProgressReadStatus;
  progress: OnboardingProgress;
}

/**
 * `absent` is a genuine fresh start; `unreadable` is "we cannot tell" and must
 * never be rendered as one (same red line as a failed load vs. an empty list).
 */
export function loadOnboardingProgress(): ProgressRead {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return { status: "unreadable", progress: { manual: {}, visited: {} } };
  }
  if (raw === null || raw === "") return { status: "absent", progress: { ...EMPTY_PROGRESS } };
  const parsed = parseProgress(raw);
  if (!parsed) return { status: "unreadable", progress: { manual: {}, visited: {} } };
  return { status: "ok", progress: parsed };
}

function isStringMap(value: unknown): value is Record<string, string> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  return Object.values(value as Record<string, unknown>).every((v) => typeof v === "string");
}

function parseProgress(raw: string): OnboardingProgress | null {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) return null;
  const { manual, visited } = data as Record<string, unknown>;
  // Half a record is not a record: silently dropping the unreadable half would
  // erase ticks the user actually made.
  if (!isStringMap(manual) || !isStringMap(visited)) return null;
  return { manual: { ...manual }, visited: { ...visited } };
}

/** false means the tick will not survive a reload — the caller must say so. */
export function saveOnboardingProgress(progress: OnboardingProgress): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
    return true;
  } catch {
    return false;
  }
}

export function toggleManualStep(
  progress: OnboardingProgress,
  stepId: OnboardingStepId,
  at: string
): OnboardingProgress {
  const manual = { ...progress.manual };
  if (manual[stepId] !== undefined) delete manual[stepId];
  else manual[stepId] = at;
  return { ...progress, manual };
}

/** Route keys we are allowed to turn into a completion mark. */
const RESERVED_RESULT_SEGMENTS = new Set(["new"]);

function resultSegment(path: string, prefix: string): string | null {
  const match = new RegExp("^" + prefix + "/([^/]+)$").exec(path);
  if (!match || RESERVED_RESULT_SEGMENTS.has(match[1])) return null;
  return match[1];
}

export function routeKeyFor(hash: string): string | null {
  const path = hash.replace(/^#/, "").split("?")[0];
  // "#/jobs/new" is the create form, not a result; "#/jobs" alone is the list.
  if (resultSegment(path, "/jobs")) return "job_detail";
  if (resultSegment(path, "/agent/jobs")) return "agent_job_detail";
  return null;
}

export function recordRouteVisit(hash: string): void {
  const key = routeKeyFor(hash);
  if (!key) return;
  const current = loadOnboardingProgress();
  // A corrupt store is not overwritten by a single navigation: that would turn
  // "we cannot read it" into "you have done nothing".
  if (current.status === "unreadable") return;
  if (current.progress.visited[key]) return;
  saveOnboardingProgress({
    ...current.progress,
    visited: { ...current.progress.visited, [key]: new Date().toISOString() },
  });
}

// ── Step status ─────────────────────────────────────────────────────────────

export type OnboardingState = "done" | "todo" | "unknown";

export interface StepSignals {
  /** reading persisted progress failed */
  progressUnreadable: boolean;
  /**
   * Whether this browser holds a workspace credential. "absent" is itself an
   * observation, not a failed probe — a reader who has never logged in must
   * not be told "we can't tell", they are exactly the person the guide is for.
   */
  credential: "present" | "absent";
  /** the /jobs probe this page ran; "pending" must not read as a failure */
  connection: "pending" | "ok" | "failed";
  verificationCount: number | null;
}

export function stepState(
  step: OnboardingStep,
  progress: OnboardingProgress,
  signals: StepSignals
): OnboardingState {
  if (step.id === "connect") {
    if (signals.credential === "absent") return "todo";
    return signals.connection === "ok" ? "done" : "unknown";
  }
  if (step.id === "create_verification") {
    if (signals.verificationCount === null) return "unknown";
    return signals.verificationCount > 0 ? "done" : "todo";
  }
  if (step.id === "read_results") {
    if (progress.visited.job_detail || progress.visited.agent_job_detail) return "done";
    // Ticks we cannot read are not ticks we can deny.
    return signals.progressUnreadable ? "unknown" : "todo";
  }
  // manual step
  if (progress.manual[step.id]) return "done";
  return signals.progressUnreadable ? "unknown" : "todo";
}

export function summarize(
  steps: OnboardingStep[],
  progress: OnboardingProgress,
  signals: StepSignals
): { done: number; total: number; unknown: number } {
  const states = steps.map((step) => stepState(step, progress, signals));
  return {
    done: states.filter((s) => s === "done").length,
    total: steps.length,
    unknown: states.filter((s) => s === "unknown").length,
  };
}
