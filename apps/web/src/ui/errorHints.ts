// Shared mapper from raw pipeline/worker error strings (English stderr /
// provider messages) into an actionable Chinese explanation. Known
// infrastructure / git / model failure signatures become "what to do next"
// guidance; anything unrecognised is returned verbatim so we never fabricate a
// meaning for a message we do not know. The raw string stays available for
// hover/audit via the caller's `title` attribute.

import { describePreflightError } from "./preflight";

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
    "路径不存在或不可读：执行服务找不到你填写的仓库路径或需求文件。请确认路径对执行服务可见（不是本机临时目录），"
    + "且目录确实是 Git 仓库、需求文件确实存在，然后重新验证。"],
  [/does not belong to the repository|unknown revision|ambiguous argument|bad revision|did not resolve to a commit|ref .{0,40}does not (exist|resolve)/i,
    "版本引用无法解析：你填写的基准或待检查版本在该仓库里找不到对应提交。请改用真实存在的分支名、标签或完整的提交 SHA"
    + "（例如先 `git fetch` 拉取该分支），确认两者指向同一仓库后重新验证。"],
  [/failed to checkout|worktree not created|cannot checkout/i,
    "版本检出失败：引用虽能解析，但执行服务无法创建工作区。常见于仓库过大、磁盘不足或该提交缺少工作树所需文件。"
    + "请换一个可检出的分支/提交，或检查执行服务所在环境的磁盘与权限后重试。"],
  [/git diff (for .+ )?failed|could not access|not a git repository/i,
    "无法比较两个版本：仓库可能不是 Git 仓库，或两个引用之间无法生成差异。请确认路径为有效 Git 仓库且基准与待检查版本不同、均存在。"],
  [/no head workspace|cannot generate tests|error preparing (base|head) workspace/i,
    "工作区准备失败：执行服务无法基于你选择的版本检出或创建工作副本，因此无法生成并运行验证用例。"
    + "请确认仓库路径与版本引用有效，且执行环境有足够磁盘与权限，然后重新验证。"],
  [/failed to compile on head|compilation error|build failure|cannot find symbol/i,
    "验证用例在目标版本上编译 / 构建未通过。这可能是待检查版本确实与需求不符，也可能是该项目无法在当前构建环境下编译"
    + "（依赖缺失、构建配置等原因）。请结合需求覆盖与证据判断；若为环境问题，修复后重新验证。"],
  [/only supports the demo repository|demo repository \(com\.specproof\)/i,
    "当前自动反例生成器针对 Java/Spring 演示仓库；此仓库或语言还无法自动生成可执行反例。请以上方"
    + "「需求覆盖」和静态检查结论为准，或为该仓库补充验收条件 / 接入对应检查器后重新验证。"],
  [/no (generated )?counterexample test|no test produced|non[- ]reproducible/i,
    "本次未能生成可执行的反例测试，因此没有形成动态验证证据。请查看需求覆盖与已确认风险；"
    + "如需动态验证，请确认仓库可构建并补充对应语言的检查器。"],
  [/no pom\.xml|pom\.xml not found|no build config/i,
    "未找到构建配置（如 pom.xml），无法编译并运行验证用例。请确实验证的项目路径与分支正确，"
    + "或改用支持该项目的验证方式。"],
  [/llm (generation )?failed|llm contract compilation failed|provider unavailable|no api key/i,
    "模型服务暂时不可用，反例生成未完成。请检查模型配置（API 密钥 / 服务地址）后重新验证，"
    + "或先在轻量模式下查看静态检查结论。"],
];

export function describePipelineError(raw: string): string {
  // 环境预检（Phase 1.4）的阻断原因有结构化来源，交给专门的映射处理，
  // 避免与流水线错误签名互相误命中。
  if (/^Preflight:\s*/i.test(raw)) return describePreflightError(raw);
  for (const [pattern, hint] of PIPELINE_ERROR_HINTS) {
    if (pattern.test(raw)) return hint;
  }
  return raw;
}

// "降级 DEGRADED" notices carry short, dynamic strings emitted at the API
// source (e.g. `redis: Connection refused`, `mysql: ...`). They are technical
// and mix English subsystem names with raw provider errors, so we gloss the
// known ones into an actionable Chinese line while still exposing the raw
// string via the caller's `title`. Anything unrecognized is returned verbatim
// so we never fabricate a meaning for a subsystem we do not know.
const DEGRADED_HINTS: Array<[RegExp, string]> = [
  [/^redis\b/i, "实时进度缓存（Redis）暂时不可用：任务状态与结果仍会保存并展示，"
    + "但执行过程中的进度更新可能会延迟或需要手动点「刷新」才会出现。"],
  [/^mysql\b/i, "主数据库（MySQL）暂时不可用：当前只能显示能够读取到的部分结果，"
    + "完整的验证记录可能要等服务恢复后再刷新。"],
  [/persistence failed|job NOT accepted/i, "任务未能写入存储：这次请求没有被受理，通常不会开始执行。"
    + "请检查执行服务连接后重新提交。"],
];

export function describeDegradedReason(raw: string): string {
  for (const [pattern, hint] of DEGRADED_HINTS) {
    if (pattern.test(raw)) return hint;
  }
  return raw;
}
