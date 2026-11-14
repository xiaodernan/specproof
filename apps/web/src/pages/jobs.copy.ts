import type { Locale } from "../i18n/strings";

/** Copy for the Jobs list page, per locale — page chrome only; status pill text is owned by ../ui/toneMap. */
export interface JobsCopy {
  eyebrow: string;
  title: string;
  description: string;
  newButton: string;
  summaryAria: string;
  summaryMatched: string;
  summaryActive: string;
  summaryVerified: string;
  summaryAttention: string;
  panelTitle: string;
  searchAria: string;
  searchPlaceholder: string;
  statusAria: string;
  allStatuses: string;
  refresh: string;
  freshnessTitle: string;
  freshnessLabel: string;
  unnamedRepo: string;
  errorReadTitle: string;
  queryEmptyTitle: string;
  firstEmptyTitle: string;
  errorCopy: string;
  queryEmptyCopy: string;
  firstEmptyCopy: string;
  clearFilters: string;
  emptyDemoHint: string;
  emptyAction: string;
  thRepo: string;
  thRefs: string;
  thStatus: string;
  thUpdated: string;
  thView: string;
  ariaView: string;
  viewLink: string;
  demoLabel: string;
  statusUnknown: string;
  paginationTotal: (n: number) => string;
  previousPage: string;
  nextPage: string;
}

const zh: JobsCopy = {
  eyebrow: "VERIFICATION HISTORY",
  title: "每一次验收都有电报",
  description: "提交的验证，矩阵盖章到人——最重要的一次，被它自己记下。",
  newButton: "＋ 新建验证",
  summaryAria: "当前页列表统计",
  summaryMatched: "个匹配的验证",
  summaryActive: "个正在跑的",
  summaryVerified: "个通过",
  summaryAttention: "个需要关注",
  panelTitle: "验证记录",
  searchAria: "搜索验证",
  searchPlaceholder: "搜索仓库路径，支持模糊",
  statusAria: "验证状态",
  allStatuses: "全部状态",
  refresh: "刷新",
  freshnessTitle: "列表是按照这一刻拉取的，换页或自动刷新会改变时间戳",
  freshnessLabel: "更新于",
  unnamedRepo: "未命名仓库",
  errorReadTitle: "暂时无法读取验证记录",
  queryEmptyTitle: "没有找到匹配的验证",
  firstEmptyTitle: "从第一次验证开始",
  errorCopy: "没连上服务器；稍后刷新，记录就会自己回来。",
  queryEmptyCopy: "试试更短的关键词，或清掉状态过滤，就能看到全部记录。",
  firstEmptyCopy: "给定一个 Git ref 和需求文件，系统就会跑起来——并且把结果如实记账。",
  clearFilters: "清除过滤",
  emptyDemoHint: "「演示」标记的行是示意数据",
  emptyAction: "创建第一次验证 →",
  thRepo: "项目 / 验证编号",
  thRefs: "比对版本",
  thStatus: "验证状态",
  thUpdated: "提交时间",
  thView: "",
  ariaView: "查看验证 ",
  viewLink: "查看 →",
  demoLabel: "演示",
  statusUnknown: "状态未知",
  paginationTotal: (n) => `共 ${n} 条验证`,
  previousPage: "上一页",
  nextPage: "下一页",
};

const en: JobsCopy = {
  eyebrow: "VERIFICATION HISTORY",
  title: "Every change left a telegram",
  description: "Submitted verifications, stamped by the matrix — the most important one is the one it remembers.",
  newButton: "+ New verification",
  summaryAria: "Current list statistics",
  summaryMatched: "matching verifications",
  summaryActive: "active on this page",
  summaryVerified: "verified",
  summaryAttention: "needing attention",
  panelTitle: "Verifications",
  searchAria: "Search verifications",
  searchPlaceholder: "Search a repo path (substring)",
  statusAria: "Verdict status",
  allStatuses: "All statuses",
  refresh: "Refresh",
  freshnessTitle: "The list was fetched at this moment; it changes when the page refreshes",
  freshnessLabel: "Updated",
  unnamedRepo: "unnamed repository",
  errorReadTitle: "Cannot read verification records right now",
  queryEmptyTitle: "No verifications match the filter",
  firstEmptyTitle: "Start with the first verification",
  errorCopy: "The server did not connect; give it a refresh — the records will come back on their own.",
  queryEmptyCopy: "Try a shorter keyword, or clear the status filter to see everything.",
  firstEmptyCopy: "Give it a Git ref and a requirement file — it will run and record the verdict honestly.",
  clearFilters: "Clear filters",
  emptyDemoHint: "Rows marked DEMO are seed data",
  emptyAction: "Create a verification →",
  thRepo: "Repository / verification",
  thRefs: "Comparing refs",
  thStatus: "Verdict",
  thUpdated: "Submitted",
  thView: "",
  ariaView: "View verification ",
  viewLink: "View →",
  demoLabel: "DEMO",
  statusUnknown: "UNKNOWN",
  paginationTotal: (n) => `${n} verifications`,
  previousPage: "Previous",
  nextPage: "Next",
};

export const JOBS_BY_LOCALE: Record<Locale, JobsCopy> = { zh, en };
