import type { Locale } from "../i18n/strings";

/** Copy for the Matrix page, per locale. The zh side preserves every Chinese
 *  string pinned by Matrix.test.tsx byte-for-byte. */
export interface MatrixCopy {
  eyebrow: string;
  title: string;
  description: string;
  viewFull: string;
  newButton: string;
  briefStrong: string;
  briefBody: string;
  briefTermContract: string;
  briefTermEvidence: string;
  briefTail: string;
  selectLabel: string;
  selectPlaceholder: string;
  selectOption: string;
  refresh: string;
  uninitializedTitle: string;
  readFailedTitle: string;
  loadingJobsTitle: string;
  selectJobTitle: string;
  waitingJobsTitle: string;
  jobsEmptyTitle: string;
  jobsEmptyDescription: string;
  jobsErrorDescription: string;
  matrixReadFailedTitle: string;
  matrixReadFailedDescription: string;
  matrixLoadingJobsDescription: string;
  matrixHasJobsDescription: string;
  matrixNoJobsDescription: string;
  reload: string;
  degradedFallback: string;
  colReq: string;
  colExpected: string;
  colChecker: string;
  colResult: string;
  colDiff: string;
  colEvidence: string;
  createFirst: string;
  metricTotal: string;
  metricPassed: string;
  metricFailed: string;
  metricUnverified: string;
  unmeasured: string;
  attributionUnknown: string;
  noDifferentialExperiment: string;
  missingSide: string;
  nextStepPrefix: string;
  missingEvidenceStrong: (n: number) => string;
  truncationStrong: (shown: number, total: number) => string;
  truncationNote: string;
  truncationNullNote: string;
  matrixPanelTitle: string;
  filterAria: string;
  filterPlaceholder: string;
  clearFilter: string;
  viewFull2: string;
  totalNullTitle: string;
  totalNullDescription: string;
  totalZeroTitle: string;
  totalZeroDescription: string;
  totalPositiveEmptyTitle: string;
  totalPositiveEmptyDescription: string;
  filterNoMatchTitle: string;
  filterNoMatchDescription: string;
  noRequirement: string;
  noExpected: string;
  evidenceEmpty: string;
}

const zh: MatrixCopy = {
  eyebrow: "REQUIREMENT COVERAGE",
  title: "每条需求，都有落点。",
  description: "把需求、检查结果和证据逐条对应。先看未通过与证据不足的部分，再决定这次变更能否交付。",
  viewFull: "查看完整验证 →",
  newButton: "新建验证 →",
  briefStrong: "通过不等于全覆盖。",
  briefBody: "这里呈现已提取",
  briefTermContract: "规则",
  briefTermEvidence: "证据",
  briefTail: "的结果；未识别的需求、尚未执行的检查或缺少",
  selectLabel: "选择验证任务",
  selectPlaceholder: "选择一个任务，查看需求覆盖",
  selectOption: "?",
  refresh: "刷新",
  uninitializedTitle: "等待初始化",
  readFailedTitle: "暂时无法读取验证",
  loadingJobsTitle: "正在加载验证任务",
  selectJobTitle: "选择一个验证任务开始查看",
  waitingJobsTitle: "等待验证任务",
  jobsEmptyTitle: "还没有可读取的验证",
  jobsEmptyDescription: "先创建一条验收，就能看到每条需求对应的处境。",
  jobsErrorDescription: "稍后恢复；记录不会丢。",
  matrixReadFailedTitle: "暂时无法读取这个验证",
  matrixReadFailedDescription: "稍后重试，也可以先去外部验证页继续。",
  matrixLoadingJobsDescription: "等待一个验收完成，就能看到覆盖情况。",
  matrixHasJobsDescription: "选择一个任务，或者先创建一条验收。",
  matrixNoJobsDescription: "先创建一条验收，就能看到需求覆盖情况。",
  reload: "重新加载",
  degradedFallback: "数据不完整——建议稍后刷新。",
  colReq: "需求 / 契约",
  colExpected: "期望行为",
  colChecker: "验证方式",
  colResult: "检查结果",
  colDiff: "改前 / 改后对照",
  colEvidence: "证据 / 未知",
  createFirst: "创建第一条验证 →",
  metricTotal: "已审查需求",
  metricPassed: "已通过",
  metricFailed: "未通过",
  metricUnverified: "证据不足",
  unmeasured: "未统计",
  attributionUnknown: "归因未知",
  noDifferentialExperiment: "未做改前/改后差分实验",
  missingSide: "无观测",
  nextStepPrefix: "下一步：",
  missingEvidenceStrong: (n) => `共有 ${n} 条没有留下证据`,
  truncationStrong: (shown, total) => `仅展示前 ${shown} 条（共 ${total} 条）`,
  truncationNote: "其余已被服务端截断——上方计数与本表不一致属正常现象。",
  truncationNullNote: "管线没有计入总数——其余已被服务端截断，本表只展示已拉取部分，所以上方不做推算。",
  matrixPanelTitle: "验收矩阵",
  filterAria: "搜索需求",
  filterPlaceholder: "搜索需求、契约号",
  clearFilter: "清除搜索",
  viewFull2: "查看完整验证 →",
  totalNullTitle: "这一轮没有留下矩阵统计",
  totalNullDescription: "还没有计入任何规则——不等于没有需求。这一轮统计本体为空，所以上方不做推算。",
  totalZeroTitle: "这次验证记录为 0 条规则",
  totalZeroDescription: "管线记录为 0 条规则——没有规则不能视为验收通过，请确认这次验证是否真的编译出契约。",
  totalPositiveEmptyTitle: "有统计数字，但读不到逐条结果",
  totalPositiveEmptyDescription: "总计存在但逐条拉取不到——按铁律绝不补零补绿，请核对这次验证记录并重跑。",
  filterNoMatchTitle: "没有匹配的需求",
  filterNoMatchDescription: "换一个关键词再搜——需求、契约号与检查结论都可以搜索。",
  noRequirement: "未提供需求",
  noExpected: "未提供",
  evidenceEmpty: "未知",
};

const en: MatrixCopy = {
  eyebrow: "REQUIREMENT COVERAGE",
  title: "Every requirement gets its place.",
  description: "Requirement, check and evidence, lined up row by row. Read the gaps before the greens — then decide whether this change may ship.",
  viewFull: "View full verification →",
  newButton: "New verification →",
  briefStrong: "Passing is not full coverage.",
  briefBody: "This page shows the results of the extracted",
  briefTermContract: "rules",
  briefTermEvidence: "evidence",
  briefTail: "; requirements never recognized, checks not yet run, or results missing ",
  selectLabel: "Choose a verification",
  selectPlaceholder: "Pick one to see requirement coverage",
  selectOption: "?",
  refresh: "Refresh",
  uninitializedTitle: "Initializing",
  readFailedTitle: "Cannot read the verifications right now",
  loadingJobsTitle: "Loading verifications",
  selectJobTitle: "Pick a verification to inspect",
  waitingJobsTitle: "Waiting for verifications",
  jobsEmptyTitle: "No verifications to read yet",
  jobsEmptyDescription: "Create one acceptance run and every requirement will find its place.",
  jobsErrorDescription: "It will recover; the records are safe.",
  matrixReadFailedTitle: "Cannot read this verification right now",
  matrixReadFailedDescription: "Try again, or open the verification page instead.",
  matrixLoadingJobsDescription: "Wait for an acceptance run — the coverage will appear.",
  matrixHasJobsDescription: "Pick a job, or create an acceptance run first.",
  matrixNoJobsDescription: "Create an acceptance run to see requirement coverage.",
  reload: "Reload",
  degradedFallback: "Data is incomplete — refresh shortly.",
  colReq: "Requirement / contract",
  colExpected: "Expected behavior",
  colChecker: "Checker",
  colResult: "Verdict",
  colDiff: "Base → Head comparison",
  colEvidence: "Evidence / unknown",
  createFirst: "Create your first verification →",
  metricTotal: "Requirements reviewed",
  metricPassed: "Passed",
  metricFailed: "Failed",
  metricUnverified: "Evidence missing",
  unmeasured: "NOT MEASURED",
  attributionUnknown: "Attribution unknown",
  noDifferentialExperiment: "No differential experiment ran",
  missingSide: "No observation",
  nextStepPrefix: "Next: ",
  missingEvidenceStrong: (n) => `${n} rows carry no evidence`,
  truncationStrong: (shown, total) => `Showing the first ${shown} rows (of ${total})`,
  truncationNote: "The rest were truncated by the server — the counts above and this table disagreeing is expected.",
  truncationNullNote: "The pipeline counted nothing — the rest were truncated; this table shows only what was fetched. No inference is drawn above.",
  matrixPanelTitle: "Verification Matrix",
  filterAria: "Search requirements",
  filterPlaceholder: "Search requirements, contract ids",
  clearFilter: "Clear search",
  viewFull2: "View full verification →",
  totalNullTitle: "This run left no matrix statistics",
  totalNullDescription: "Nothing counted yet — which is not the same as no requirements. This run's statistics are absent; no inference is drawn above.",
  totalZeroTitle: "This verification recorded 0 rules",
  totalZeroDescription: "The pipeline recorded 0 rules — zero rules cannot count as accepted. Confirm this run actually compiled contracts.",
  totalPositiveEmptyTitle: "There are statistics, but no per-row results",
  totalPositiveEmptyDescription: "The total exists but the rows cannot be fetched — per our iron law we never fabricate zeros or greens. Check this run and re-execute.",
  filterNoMatchTitle: "Nothing matches the filter",
  filterNoMatchDescription: "Try a different keyword — requirement text, contract ids and verdicts are all searchable.",
  noRequirement: "Requirement not provided",
  noExpected: "Not provided",
  evidenceEmpty: "UNKNOWN",
};

export const MATRIX_BY_LOCALE: Record<Locale, MatrixCopy> = { zh, en };
