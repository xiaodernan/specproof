import type { Locale } from "../i18n/strings";
import type { ProductIconName } from "../ui/ProductIcon";

export interface ActionCopy {
  href: string;
  icon: ProductIconName;
  title: string;
  text: string;
  label: string;
}

export interface QuickstartCopy {
  step: string;
  title: string;
  text: string;
  href: string;
  cta: string;
}

/** Every sentence the Dashboard shows, per locale. Replacing copy means editing DATA, not markup. */
export interface DashboardCopy {
  eyebrow: string;
  h1: string;
  h1Dot: string;
  lead: string;
  newButton: string;
  welcomeAria: string;
  welcomeKicker: string;
  welcomeH1: [string, string];
  welcomeP: [string, string?];
  welcomeGuideLink: string;
  diagramLabel: string;
  diagramNodeContracts: { strong: string; small: string };
  diagramNodeVerify: { strong: string; small: string };
  diagramCore: string;
  diagramCaption: [string, string, string];
  quickstartAria: string;
  quickstartTitle: string;
  quickstartHint: string;
  actionsTitle: string;
  actionsHint: string;
  metricsTitle: string;
  refresh: string;
  errorLead: string;
  degradedTitle: string;
  degradedTrail: string;
  degradedRawSummary: string;
  timelineTitle: string;
  timelineAria: string;
  timelineEmpty: string;
  statusTitle: string;
  statusTotalBefore: string;
  statusCenterLabel: string;
  statusAria: string;
  statusEmpty: string;
  recentTitle: string;
  recentViewAll: string;
  loadingRecords: string;
  errorTitle: string;
  emptyTitle: string;
  errorCopy: string;
  emptyCopy: string;
  errorCta: string;
  emptyCta: string;
  thRepo: string;
  thStatus: string;
  thCreated: string;
  thView: string;
  ariaViewJob: string;
  demoLabel: string;
  recentNote: string;
  activityTitle: string;
  activityUnit: string;
  activityTotal: string;
  activityEmpty: string;
  activityNoData: string;
  activityViewJobs: string;
  timelineAriaLabel: string;
  summaryNeedsAttention: (n: number) => string;
  activityCalm: string;
  activityAttention: string;
  calmCopy: string;
  attentionCopy: string;
  pendingChecks: string;
  statusJob: Record<string, string>;
  actions: ActionCopy[];
  quickstart: QuickstartCopy[];
  metric: { label: string; hint: string }[];
  failedSuffix: (n: number) => string;
}

const zh: DashboardCopy = {
  eyebrow: "YOUR DELIVERY WORKSPACE",
  h1: "每一次交付都有铁证",
  h1Dot: ".",
  lead: "提交变更，让铁证回答：它真的生效了么？",
  newButton: "新建验证",
  welcomeAria: "SpecProof 是什么",
  welcomeKicker: "这个仓库本身 · 只证明一件事：证据",
  welcomeH1: ["你写完了。", "但它经受了验证。"],
  welcomeP: [
    "SpecProof 不听“应该”，它要看差分：",
    "base 怎么判、head 怎么判——两个结论，摆在你眼前。",
  ],
  welcomeGuideLink: "看懂 SpecProof，从这里开始 ",
  diagramLabel: "FROM CHANGE TO CONFIDENCE",
  diagramNodeContracts: { strong: "需求契约", small: "要验证什么" },
  diagramNodeVerify: { strong: "验证结果", small: "实际验证了什么" },
  diagramCore: "铁证",
  diagramCaption: ["契约编译", "Base → Head", "铁证落定"],
  quickstartAria: "5 分钟快速体验",
  quickstartTitle: "5 分钟快速体验",
  quickstartHint: "按顺序走一遍，就知道 SpecProof 为你做什么",
  actionsTitle: "先从这里开一条线",
  actionsHint: "选一个合适你当前阶段的开工方式",
  metricsTitle: "这周的工作台",
  refresh: "刷新数据",
  errorLead: "暂时无法获取数据。刷新试试，或先去",
  degradedTitle: "后端数据暂时不完整",
  degradedTrail: " · 可能是完整库字段读不到",
  degradedRawSummary: "查看原文",
  timelineTitle: "24 小时验证时间线",
  timelineAria: "过去 24 小时的验证记录次数",
  timelineEmpty: "过去 24 小时还没有验收记录",
  statusTitle: "验收状态",
  statusTotalBefore: "共 ",
  statusCenterLabel: "验收记录",
  statusAria: "验收结果分布",
  statusEmpty: "本页还没有验收记录",
  recentTitle: "最近验收",
  recentViewAll: "查看全部 ",
  loadingRecords: "正在加载工作区记录",
  errorTitle: "暂时读不了工作区",
  emptyTitle: "还没有任何一次验收",
  errorCopy: "上方给出了原因；记录表格因此保持空白。",
  emptyCopy: "带上仓库路径、base/head 两个版本、需求文件——它就能跑起来。",
  errorCta: "查看服务状态",
  emptyCta: "跑一次验证",
  thRepo: "仓库 / 版本",
  thStatus: "验收状态",
  thCreated: "提交时间",
  thView: "查看记录",
  ariaViewJob: "查看记录 ",
  demoLabel: "演示",
  recentNote: "标着“演示”的记录是示意数据；只有真实 VERIFIED 才是生产级铁证。",
  activityTitle: "当前动态",
  activityUnit: "次验收提交",
  activityTotal: "过去 24 小时",
  activityEmpty: "过去 24 小时还没有验收记录",
  activityNoData: "接入可观测后才能查看动态",
  activityViewJobs: "查看验收列表 ",
  timelineAriaLabel: "过去 24 小时按小时验收记录",
  summaryNeedsAttention: (n) => `${n} 项验收需要关注`,
  activityCalm: "暂无未完成的风险",
  activityAttention: "有失败的验证需要关注",
  calmCopy: "最近的验收已完成——都被白名单覆盖。",
  attentionCopy: "顺着最新的原始报错往下看，找到失败的那一次执行。",
  pendingChecks: "等待验收记录中",
  statusJob: {
    VERIFIED: "验收通过", BLOCKED: "需要处理", RUNNING: "执行中", QUEUED: "排队中",
    FAILED: "失败", ERROR: "错误", CANCELLED: "已取消", PENDING: "等待中",
  },
  actions: [
    { href: "#/jobs/new", icon: "verify", title: "跑一次验证", text: "填好参数，按你的节奏跑一遍——结果会直接落在这里。", label: "开始验证" },
    { href: "#/agent/new", icon: "agent", title: "让 AI 自动交付", text: "把一个需求交给它：计划 → 修改 → 复验，全链路自己走完。", label: "开启自动交付" },
    { href: "#/guide", icon: "guide", title: "不知道从哪开始", text: "按顺序走一遍演示路径，一页一页把这把铁验玩明白。", label: "查看上手指南" },
  ],
  quickstart: [
    { step: "01", title: "看看演示验证", text: "用现成的演示，你会看到 VERIFIED 或 BLOCKED——这就是铁证的样子。", href: "#/jobs", cta: "查看演示列表" },
    { step: "02", title: "跑一条真实验收", text: "新建页填一个真实场景：base/head 在手、需求文件在手，报告里就有 base_pass_head_fail。", href: "#/jobs/new", cta: "连接真实验收" },
    { step: "03", title: "让 AI 改一个 Bug", text: "AI 按需求把演示任务改完，再自检自验，把结果喂回来。", href: "#/agent/new", cta: "进入 AI 建交付" },
    { step: "04", title: "连接真实模型", text: "把网关切到你自己的接口，之后每一次验收都走你的真实模型。", href: "#/settings", cta: "连接模型" },
  ],
  metric: [
    { label: "当前验收", hint: "本工作区的验收总数" },
    { label: "验收通过", hint: "通过验收的变更" },
    { label: "待处理", hint: "被铁证判为不可合并的变更" },
    { label: "排队中", hint: "排队 / 运行中的任务" },
  ],
  failedSuffix: (n) => `失败 ${n} 次`,
};

const en: DashboardCopy = {
  eyebrow: "YOUR DELIVERY WORKSPACE",
  h1: "Every delivery leaves evidence",
  h1Dot: ".",
  lead: "Ship your change and let someone — something — know it holds.",
  newButton: "New verification",
  welcomeAria: "What SpecProof is",
  welcomeKicker: "This repository itself · only proves one thing: evidence",
  welcomeH1: ["You write it.", "But it gets verified."],
  welcomeP: [
    "SpecProof does not trust the baseline; it wants the differential:",
    "how base judges, how head judges — both verdicts laid in front of you.",
  ],
  welcomeGuideLink: "Learn what SpecProof actually asks ",
  diagramLabel: "FROM CHANGE TO CONFIDENCE",
  diagramNodeContracts: { strong: "Contracts", small: "what is to be verified" },
  diagramNodeVerify: { strong: "Actual result", small: "what was verified" },
  diagramCore: "Iron evidence",
  diagramCaption: ["Verdict", "Between versions", "Production"],
  quickstartAria: "5-minute tour",
  quickstartTitle: "5-minute tour",
  quickstartHint: "Follow in order — this is what SpecProof does for you",
  actionsTitle: "Start one thread here",
  actionsHint: "Pick the thread that matches your current stage",
  metricsTitle: "This week's desk",
  refresh: "Refresh",
  errorLead: "Can't reach the data right now. Refresh, or go check ",
  degradedTitle: "Backend data is incomplete",
  degradedTrail: " · likely a field could not be read fully",
  degradedRawSummary: "Show raw reasons",
  timelineTitle: "24h verification timeline",
  timelineAria: "Verification record count over the last 24 hours",
  timelineEmpty: "No verification records in the last 24 hours",
  statusTitle: "Verdicts",
  statusTotalBefore: "",
  statusCenterLabel: "records",
  statusAria: "Verdict distribution",
  statusEmpty: "No verification records yet",
  recentTitle: "Recent verifications",
  recentViewAll: "View all ",
  loadingRecords: "Loading workspace records",
  errorTitle: "Can't read the workspace right now",
  emptyTitle: "No verification has been run yet",
  errorCopy: "The reason is shown above; the table is intentionally blank.",
  emptyCopy: "Set the password, the base/head versions, the requirement file — then let it run.",
  errorCta: "Check service status",
  emptyCta: "Run a first verification",
  thRepo: "Repository / refs",
  thStatus: "Verdict",
  thCreated: "Submitted",
  thView: "view record",
  ariaViewJob: "View record ",
  demoLabel: "DEMO",
  recentNote: "Demo rows labelled here are seed data; only real PASS tells you production held.",
  activityTitle: "Activity",
  activityUnit: "verification submissions",
  activityTotal: "last 24 hours",
  activityEmpty: "No verification records in the last 24 hours",
  activityNoData: "Activity will appear once observability lands",
  activityViewJobs: "View the verification list ",
  timelineAriaLabel: "Hourly verification records over the last 24 hours",
  summaryNeedsAttention: (n) => `${n} verifications need attention`,
  activityCalm: "Nothing pending right now",
  activityAttention: "Some verifications failed",
  calmCopy: "Recent verifications completed; all of them were covered by allowlist.",
  attentionCopy: "Open the raw errors or find the run that is failing.",
  pendingChecks: "Waiting for verification records",
  statusJob: {
    VERIFIED: "VERIFIED", BLOCKED: "BLOCKED", RUNNING: "RUNNING", QUEUED: "QUEUED",
    FAILED: "FAILED", ERROR: "ERROR", CANCELLED: "CANCELLED", PENDING: "PENDING",
  },
  actions: [
    { href: "#/jobs/new", icon: "verify", title: "Run a verification", text: "Fill in the details and run one at your pace — results land right here.", label: "Start verification" },
    { href: "#/agent/new", icon: "agent", title: "Let the AI build a delivery", text: "Point it at a requirement: it plans, it modifies, it verifies itself.", label: "Start autonomous delivery" },
    { href: "#/guide", icon: "guide", title: "I don't know where to start", text: "Walk the demo path in order and learn what this iron is asking of you.", label: "Open the guide" },
  ],
  quickstart: [
    { step: "01", title: "Run the demo verification", text: "One ready-made demo; you should expect VERIFIED or BLOCKED — and that's the whole point of iron.", href: "#/jobs", cta: "View the demo list" },
    { step: "02", title: "Run a real verification", text: "New verification — one real reproduction scenario, no missing permissions, base/head in hand, base_pass_head_fail in the report.", href: "#/jobs/new", cta: "Connect a real verification" },
    { step: "03", title: "Let the AI fix a bug", text: "The AI carries the demo demand through to the end, verifies its own autonomy, and feeds the result back.", href: "#/agent/new", cta: "Enter AI delivery" },
    { step: "04", title: "Connect a real model", text: "Point the gateway at your own access; every later run goes through the real model.", href: "#/settings", cta: "Connect a model" },
  ],
  metric: [
    { label: "Open verifications", hint: "Total records in this workspace" },
    { label: "Passed", hint: "Verified changes that were executed and held" },
    { label: "Blocked", hint: "Broken by verification, needs a fix first" },
    { label: "In the queue", hint: "Already queued and waiting to run" },
  ],
  failedSuffix: (n) => `${n} failed`,
};

export const DASHBOARD_BY_LOCALE: Record<Locale, DashboardCopy> = { zh, en };
