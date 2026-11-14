import type { Locale } from "../i18n/strings";

/** Copy for the Contracts (acceptance rules) page, per locale.
 *  Status pill text is owned by ../ui (CONTRACT_STATUS_CN) and stays untranslated. */
export interface ContractsCopy {
  eyebrow: string;
  title: string;
  description: string;
  refresh: string;
  briefStrong: string;
  briefBodyBefore: string;
  briefTerm: string;
  briefBodyAfter: string;
  briefGuideLink: string;
  filterStatusLabel: string;
  filterRepoLabel: string;
  filterRepoPlaceholder: string;
  allStatuses: string;
  clearFilters: string;
  emptyReadTitle: string;
  emptyReadDescription: string;
  retry: string;
  degradedReason: string;
  metricCounting: string;
  metricApproved: string;
  metricProposed: string;
  metricRejected: string;
  metricsAria: string;
  matrixTitle: string;
  matrixNote: string;
  emptyFilteredTitle: string;
  emptyFilteredDescription: string;
  emptyAllTitle: string;
  emptyAllDescription: string;
  noRequirement: string;
  noExpected: string;
  requirementRef: string;
  colRequirement: string;
  colExpected: string;
  colStatus: string;
  colChecker: string;
  colRepo: string;
  ctaNewJobs: string;
}

const zh: ContractsCopy = {
  eyebrow: "ACCEPTANCE RULES",
  title: "验收规则，逐条钉住",
  description: "每条契约都说清：它要证明什么、用什么 checker 类型、现在处于什么状态、被谁批准——都如实记账。",
  refresh: "刷新列表",
  briefStrong: "不知道什么是契约",
  briefBodyBefore: "——一条",
  briefTerm: "契约",
  briefBodyAfter: "就是一份给机器的验收规则：描述你到底要系统证明什么、什么算证据。《铁证之书》里有中文解释。",
  briefGuideLink: "了解契约，从指南开始 →",
  filterStatusLabel: "状态",
  filterRepoLabel: "仓库路径",
  filterRepoPlaceholder: "搜索仓库路径（精确匹配）",
  allStatuses: "全部状态",
  clearFilters: "清除过滤",
  emptyReadTitle: "暂时无法读取契约",
  emptyReadDescription: "确认服务连接，稍后点击刷新；读取失败不会把契约当成空。",
  retry: "重新加载",
  degradedReason: "契约数据不完整——显示的可能不全，请以完整库为准。",
  metricCounting: "当前过滤契约",
  metricApproved: "已批准",
  metricProposed: "提议",
  metricRejected: "被拒绝 / 被撤销",
  metricsAria: "当前过滤结果计数",
  matrixTitle: "验收契约",
  matrixNote: "状态与生成时间",
  emptyFilteredTitle: "没有匹配的契约",
  emptyFilteredDescription: "换一个状态或仓库路径过滤——仓库路径需要精确匹配。",
  emptyAllTitle: "还没有一条契约建立",
  emptyAllDescription: "批准是契约的默认——生成一条契约，让机器知道到底要证明什么。",
  noRequirement: "未提供需求",
  noExpected: "未提供",
  requirementRef: "需求来源：",
  colRequirement: "需求 Requirement",
  colExpected: "期望行为",
  colStatus: "状态",
  colChecker: "验证方式",
  colRepo: "仓库 / 生成时间",
  ctaNewJobs: "去创建验收 →",
};

const en: ContractsCopy = {
  eyebrow: "ACCEPTANCE RULES",
  title: "Acceptance rules, pinned one by one",
  description: "Every contract spells out what it must prove, which checker type validates it, its current state, and who approved it — all recorded honestly.",
  refresh: "Refresh",
  briefStrong: "Don't know what a contract is",
  briefBodyBefore: "— a ",
  briefTerm: "contract",
  briefBodyAfter: " is an acceptance rule for the machine: what it must prove, and what counts as evidence. The Book of Iron Evidence explains it in Chinese and English.",
  briefGuideLink: "Open the guide →",
  filterStatusLabel: "Status",
  filterRepoLabel: "Repository",
  filterRepoPlaceholder: "Search a repository path (exact match)",
  allStatuses: "All statuses",
  clearFilters: "Clear filters",
  emptyReadTitle: "Cannot read contracts right now",
  emptyReadDescription: "Check the service connection, then refresh; a failed read never turns contracts into zero.",
  retry: "Retry",
  degradedReason: "Contract data is incomplete — the list may be partial; the full schema is the source of truth.",
  metricCounting: "Matching contracts",
  metricApproved: "Approved",
  metricProposed: "Proposed",
  metricRejected: "Rejected / Revoked",
  metricsAria: "Current filtered counts",
  matrixTitle: "Verification contracts",
  matrixNote: "State and created",
  emptyFilteredTitle: "No contracts match",
  emptyFilteredDescription: "Try a different status or a repo path — repository paths are exact matches.",
  emptyAllTitle: "No contract exists yet",
  emptyAllDescription: "Approval is the default for a contract — create one and tell the machine what it must prove.",
  noRequirement: "Requirement not provided",
  noExpected: "Not provided",
  requirementRef: "Source:",
  colRequirement: "Requirement",
  colExpected: "Expected behavior",
  colStatus: "Status",
  colChecker: "Checker",
  colRepo: "Repository / created",
  ctaNewJobs: "Go create an acceptance run →",
};

export const CONTRACTS_BY_LOCALE: Record<Locale, ContractsCopy> = { zh, en };
