import type { Locale } from "../i18n/strings";

/** Copy for the Eval page, per locale. */
export interface EvalCopy {
  title: string;
  sub: string;
  retry: string;
  sourceLabel: string;
  modifiedLabel: string;
  statPrecision: string;
  statRecall: string;
  statF1: string;
  statTotal: string;
  statShouldDetect: string;
  statFalsePositives: string;
  casesPanelTitle: (n: number) => string;
  emptyCasesTitle: string;
  emptyPlaceholder: string;
  notFoundText: string;
  colCase: string;
  colVerdict: string;
  colShouldDetect: string;
  colExpectedSeverity: string;
  colExpectedContract: string;
  colContractsFound: string;
  colMatchedSeverities: string;
  yesGlyph: string;
  noGlyph: string;
}

const zh: EvalCopy = {
  title: "效果评测 Evaluation",
  sub: "精确率 / 召回率 / F1 —— 这是产品自己的验收尺子，按最近一次真实报告，不美化。",
  retry: "重新加载",
  sourceLabel: "来源 Source",
  modifiedLabel: "更新时间",
  statPrecision: "Precision 精确率",
  statRecall: "Recall 召回率",
  statF1: "F1",
  statTotal: "总案例",
  statShouldDetect: "应检",
  statFalsePositives: "误报 FP",
  casesPanelTitle: (n) => `用例明细 (${n})`,
  emptyCasesTitle: "暂无用例明细",
  emptyPlaceholder: "—",
  notFoundText: "尚无评测报告——这不是读取失败；评测报告生成之后，本页才有数字可看。",
  colCase: "案例 Case",
  colVerdict: "判定 Verdict",
  colShouldDetect: "应检",
  colExpectedSeverity: "期望严重度",
  colExpectedContract: "期望契约 Contract",
  colContractsFound: "实际发现的契约",
  colMatchedSeverities: "匹配的严重度 Severities",
  yesGlyph: "是",
  noGlyph: "否",
};

const en: EvalCopy = {
  title: "Effectiveness",
  sub: "Precision / Recall / F1 — this product's own yardstick, straight from the last real report; no beautifying.",
  retry: "Retry",
  sourceLabel: "Source",
  modifiedLabel: "Updated",
  statPrecision: "Precision",
  statRecall: "Recall",
  statF1: "F1",
  statTotal: "Total cases",
  statShouldDetect: "Should detect",
  statFalsePositives: "False positives",
  casesPanelTitle: (n) => `Case details (${n})`,
  emptyCasesTitle: "No case details yet",
  emptyPlaceholder: "—",
  notFoundText: "No evaluation report has been generated yet — this is not a read failure; once a report exists, this page shows numbers.",
  colCase: "Case",
  colVerdict: "Verdict",
  colShouldDetect: "Should detect",
  colExpectedSeverity: "Expected severity",
  colExpectedContract: "Expected contract",
  colContractsFound: "Contracts found",
  colMatchedSeverities: "Matched severities",
  yesGlyph: "Yes",
  noGlyph: "No",
};

export const EVAL_BY_LOCALE: Record<Locale, EvalCopy> = { zh, en };
