import { STRINGS, storedLocale } from "../i18n/strings";

function gloss(key: string): string {
  return STRINGS[storedLocale()][key] ?? key;
}

// Shared mapper from raw pipeline/worker error strings (English stderr /
// provider messages) into an actionable Chinese explanation. Known
// infrastructure / git / model failure signatures become "what to do next"
// guidance; anything unrecognised is returned verbatim so we never fabricate a
// meaning for a message we do not know. The raw string stays available for
// hover/audit via the caller's `title` attribute.

import { describePreflightError } from "./preflight";
import { stageLabel } from "./stages";

// Honest distinction between "the resource genuinely isn't there (404)" and
// "the read failed (network / 5xx / backend down)". Collapsing these is a
// correctness bug: a page that shows its "no data yet" empty state on a request
// failure asserts a benign state it cannot actually know. `ApiError` carries a
// numeric `status`; we duck-type it so this module stays free of an api.ts
// import cycle and works for any error object that reports its HTTP status.
export function isNotFound(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    (err as { status?: number }).status === 404
  );
}

// True when there IS an error and it is not a clean 404 — i.e. an actual load
// failure that must never be dressed up as an empty state.
export function loadFailed(err: unknown): boolean {
  return !!err && !isNotFound(err);
}

const PIPELINE_ERROR_HINTS: Array<[RegExp, string]> = [
  [/(path|file)[^:]{0,30}does not exist|is not a directory|repo_path 不存在/i,
    "hint.pipeline.repoPathInvalid"],
  [/does not belong to the repository|unknown revision|ambiguous argument|bad revision|did not resolve to a commit|ref .{0,40}does not (exist|resolve)/i,
    "hint.pipeline.badRef"],
  [/failed to checkout|worktree not created|cannot checkout/i,
    "hint.pipeline.checkoutFailed"],
  [/git diff (for .+ )?failed|could not access|not a git repository/i,
    "hint.pipeline.notGitRepo"],
  [/no head workspace|cannot generate tests|error preparing (base|head) workspace/i,
    "hint.pipeline.headWorkspaceMissing"],
  [/failed to compile on head|compilation error|build failure|cannot find symbol/i,
    "hint.pipeline.headCompileFailed"],
  [/only supports the demo repository|demo repository \(com\.specproof\)/i,
    "hint.pipeline.demoRepoOnly"],
  [/no (generated )?counterexample test|no test produced|non[- ]reproducible/i,
    "hint.pipeline.noCounterexample"],
  [/no pom\.xml|pom\.xml not found|no build config/i,
    "hint.pipeline.noPom"],
  [/llm (generation )?failed|llm contract compilation failed|provider unavailable|no api key/i,
    "hint.pipeline.llmFailed"],
];

export function describePipelineError(raw: string): string {
  // 环境预检（Phase 1.4）的阻断原因有结构化来源，交给专门的映射处理，
  // 避免与流水线错误签名互相误命中。
  if (/^Preflight:\s*/i.test(raw)) return describePreflightError(raw);
  for (const [pattern, hint] of PIPELINE_ERROR_HINTS) {
    if (pattern.test(raw)) return STRINGS[storedLocale()][hint] ?? hint;
  }
  return raw;
}

/**
 * 失败位置的披露（#13.6-3 的 Web 侧读者）。
 *
 * 终态失败行的 last_error 是一个 JSON 信封，`failed_after_stage` 记录流里
 * 最后一个**完成**的阶段——措辞必须是「X 之后失败」而不是「死在 X」
 * （流没有节点开始事件，后者是推断；见 PRODUCT_ROADMAP §20.2）。解析不了
 * （老行、别的错误形状、1024 截断把 JSON 切坏）一律返回 null：页面就不
 * 渲染这一行，绝不猜测。
 */
export function terminalStageNote(raw: string): string | null {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const stage = (parsed as Record<string, unknown>)["failed_after_stage"];
    if (typeof stage !== "string" || !stage.trim()) return null;
    return gloss("hint.terminalStageFailed").replace("{stage}", stageLabel(stage));
  } catch {
    return null;
  }
}

// "降级 DEGRADED" notices carry short, dynamic strings emitted at the API
// source (e.g. `redis: Connection refused`, `mysql: ...`). They are technical
// and mix English subsystem names with raw provider errors, so we gloss the
// known ones into an actionable Chinese line while still exposing the raw
// string via the caller's `title`. Anything unrecognized is returned verbatim
// so we never fabricate a meaning for a subsystem we do not know.
const DEGRADED_HINTS: Array<[RegExp, string]> = [
  [/^redis\b/i, "hint.degraded.redis"],
  [/^mysql\b/i, "hint.degraded.mysql"],
  [/persistence failed|job NOT accepted/i, "hint.degraded.persistence"],
];

export function describeDegradedReason(raw: string): string {
  for (const [pattern, hint] of DEGRADED_HINTS) {
    if (pattern.test(raw)) return STRINGS[storedLocale()][hint] ?? hint;
  }
  return raw;
}
