// 执行阶段节点名 → 中文步骤说明。内部 LangGraph 节点 id 是稳定契约，
// 这里只做展示层翻译；未收录的节点原样返回真实 id，绝不臆造步骤含义。
export const STAGE_LABELS: Record<string, string> = {
  intake: "接收任务 · 校验输入",
  preflight: "检查执行环境（工具链）",
  compile_contracts: "解析需求为验收条件",
  prepare_base: "准备基准版本环境",
  prepare_head: "准备待检查版本环境",
  collect_diff: "收集代码改动",
  retrieve_repository_context: "检索仓库上下文",
  run_static_checks: "运行静态检查",
  generate_counterexamples: "生成反例测试",
  run_differential: "运行差分验证（改动前后对比）",
  run_deep_experiments: "运行深度验证实验",
  review_court: "复核与裁决",
  build_matrix: "汇总需求覆盖矩阵",
  create_capsule: "打包复现证据",
  run_release_checks: "运行发布前检查",
  publish_report: "生成验证报告",
};

/** 返回中文步骤名；未知节点原样透传真实 id，便于排查而非被猜测掩盖。 */
export function stageLabel(node: string | undefined | null): string {
  if (!node) return "—";
  return STAGE_LABELS[node] || node;
}
