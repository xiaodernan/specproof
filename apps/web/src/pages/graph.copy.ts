import type { Locale } from "../i18n/strings";

/**
 * LangGraph view of SpecProof's own verify pipeline.
 * The node list is hand-mirrored from agent/graph.py — kept small, honest,
 * and reviewed by the same two-way gate that keeps that file from drifting.
 */

export interface PipelineNode {
  id: string;
  label: string;
  guard?: boolean;
  blurb: Record<Locale, string>;
}

export const GRAPH_GROUPS = [
  {
    id: "guard",
    title: { zh: "一 · 入院与关口", en: "I. The gate" },
    blurb: { zh: "先看环境，再谈对错。环境不满足的任何一步都不会被编进来。", en: "The environment gates every later claim — a missing toolchain is not a review." },
    nodes: ["intake", "preflight", "compile_contracts", "contract_review"] as readonly string[],
  },
  {
    id: "workspace",
    title: { zh: "二 · 双工作区", en: "II. Two worlds" },
    blurb: { zh: "base 与 head 各自起一个工作区——它们永远不互相继承除 git 以外的任何环境。", en: "Base and head each get a worktree; nothing carries over except git." },
    nodes: ["prepare_base", "prepare_head"],
  },
  {
    id: "static",
    title: { zh: "三 · 差分之前", en: "III. Before the diff" },
    blurb: { zh: "先看见变动，再问问题。变动之前 SpecProof 别无他人。", en: "Look at the change first; the tree is the truth before any verdict is spoken." },
    nodes: ["collect_diff", "retrieve_repository_context", "run_static_checks"],
  },
  {
    id: "core",
    title: { zh: "四 · 对账与反证", en: "IV. The crucible" },
    blurb: { zh: "找出“变更之后崩溃”的证据，而不是“变更之前能通”的梦想。", en: "We mine for the broken after, not the dreamt before." },
    nodes: ["generate_counterexamples", "run_differential", "run_deep_experiments"],
  },
  {
    id: "pack",
    title: { zh: "五 · 证据封装", en: "V. The court and the capsule" },
    blurb: { zh: "评审庭定案，capsule 封印，两条独立的铁路线同时发车。", en: "The court rules, the capsule seals — two independent railways leave at once." },
    nodes: ["review_court", "create_capsule", "build_matrix", "collect_evidence"],
  },
  {
    id: "report",
    title: { zh: "六 · 交割", en: "VI. The hand-over" },
    blurb: { zh: "发布检查只读取已经发生的东西——它不补做任何判断。", en: "Release checks read what already happened; they do not re-adjudicate it." },
    nodes: ["run_release_checks", "publish_report"],
  },
] as const;

export const NODE_INFO: Record<string, PipelineNode> = {
  intake: { id: "intake", label: "intake", blurb: { zh: "元请求入院：校验并装进 typed state", en: "Meta-intake: validate and pack the request" } },
  preflight: { id: "preflight", label: "preflight", guard: true, blurb: { zh: "环境探针 — 工具链不齐则直接 503（环境不满足不算验收）", en: "Environment probe — missing toolchain → explicit 503" } },
  compile_contracts: { id: "compile_contracts", label: "compile_contracts", blurb: { zh: "需求→契约：DSL 词汇被编译成 checker 列表", en: "requirement→contracts: DSL vocabulary compiled to checkers" } },
  contract_review: { id: "contract_review", label: "contract_review", blurb: { zh: "人工契约审核站 — PROPOSED→APPROVED，不经此门不予验收", en: "human sign-off on the contracts — PROPOSED→APPROVED or nothing runs" } },
  prepare_base: { id: "prepare_base", label: "prepare_base", blurb: { zh: "准备基准版本的工作区", en: "Build the base worktree" } },
  prepare_head: { id: "prepare_head", label: "prepare_head", guard: true, blurb: { zh: "准备待检查版本的工作区", en: "Build the head worktree" } },
  collect_diff: { id: "collect_diff", label: "collect_diff", blurb: { zh: "git diff 三范围的切片：文件 → 行级 → 意图摘要", en: "git diff tri-split: files → lines → intent" } },
  retrieve_repository_context: { id: "retrieve_repository_context", label: "retrieve_repository_context", blurb: { zh: "RAG 检索仓库图谱 — 管线会反复读自己的仓库", en: "RAG over the repository graph — the pipeline reads its own home" } },
  run_static_checks: { id: "run_static_checks", label: "run_static_checks", blurb: { zh: "静态检查器 — 代码不执行就看得出来的问题", en: "Checkers that need no execution" } },
  generate_counterexamples: { id: "generate_counterexamples", label: "generate_counterexamples", blurb: { zh: "敌人视角生成反例 —— LLM 生成可执行的 JUnit", en: "the red corner: executable JUnit counterexamples from an LLM" } },
  run_differential: { id: "run_differential", label: "run_differential", blurb: { zh: "base vs head 差分执行 — base_pass_head_fail 是王炸", en: "base vs head, rerun twice — base_pass_head_fail is the fingerprint" } },
  run_deep_experiments: { id: "run_deep_experiments", label: "run_deep_experiments", blurb: { zh: "DEEP 深核：变异战役 + 状态 delta", en: "DEEP drill: mutation campaign + state deltas" } },
  collect_evidence: { id: "collect_evidence", label: "collect_evidence", blurb: { zh: "从 Redis/Streams/对象存储收集铁证 — 证据链必须可重放", en: "gather into capsule from Redis/Streams/object store" } },
  review_court: { id: "review_court", label: "review_court", blurb: { zh: "评审法庭：BLOCKER / MAJOR / MINOR 裁决", en: "the court: BLOCKER / MAJOR / MINOR arbitrated by rules" } },
  build_matrix: { id: "build_matrix", label: "build_matrix", blurb: { zh: "需求 × 证据类型 × 结论 的铁证矩阵", en: "contracts × evidence × verdict — the iron matrix" } },
  create_capsule: { id: "create_capsule", label: "create_capsule", blurb: { zh: "复现包：证据 + 环境 + 源码快照 一颗胶囊", en: "the replayable evidence capsule" } },
  run_release_checks: { id: "run_release_checks", label: "run_release_checks", blurb: { zh: "发布前检查 — 只读已发生的事实，不补决定", en: "pre-release gate — read what happened; never invent it" } },
  publish_report: { id: "publish_report", label: "publish_report", blurb: { zh: "输出验证报告 — 让证据替你说话", en: "publish the verification report — the iron speaks for itself" } },
};
