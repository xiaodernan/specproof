import { STRINGS, storedLocale } from "../i18n/strings";

function gloss(key: string): string {
  return STRINGS[storedLocale()][key] ?? key;
}

// 执行阶段节点名 → 中文步骤说明。内部 LangGraph 节点 id 是稳定契约，
// 这里只做展示层翻译；未收录的节点原样返回真实 id，绝不臆造步骤含义。
// 末尾三项不是流水线阶段，而是 worker 直接写出的事件名（进度流里的
// 终止/取消/租约事件），它们同样要有一句人话，否则时间线只能显示英文标识。
export const STAGE_LABELS: Record<string, string> = {
  intake: "stage.intake",
  preflight: "stage.preflight",
  compile_contracts: "stage.compile_contracts",
  contract_review: "stage.contract_review",
  prepare_base: "stage.prepare_base",
  prepare_head: "stage.prepare_head",
  collect_diff: "stage.collect_diff",
  retrieve_repository_context: "stage.retrieve_repository_context",
  run_static_checks: "stage.run_static_checks",
  generate_counterexamples: "stage.generate_counterexamples",
  run_differential: "stage.run_differential",
  run_deep_experiments: "stage.run_deep_experiments",
  review_court: "stage.review_court",
  create_capsule: "stage.create_capsule",
  build_matrix: "stage.build_matrix",
  collect_evidence: "stage.collect_evidence",
  run_release_checks: "stage.run_release_checks",
  publish_report: "stage.publish_report",
  terminal: "stage.terminal",
  cancel_checkpoint: "stage.cancel_checkpoint",
  lease: "stage.lease",
};

/** 返回中文步骤名；未知节点原样透传真实 id，便于排查而非被猜测掩盖。 */
export function stageLabel(node: string | undefined | null): string {
  if (!node) return gloss("stage.missing");
  return gloss(STAGE_LABELS[node] ?? "") || node;
}
