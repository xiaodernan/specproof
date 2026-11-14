import type { Locale } from "../i18n/strings";

/** Copy for the Billing page, per locale. zh preserves exact literals pinned by Billing.test.tsx. */
export interface BillingCopy {
  title: string;
  sub: string;
  subActivePlan: string;
  subYesPlan: string;
  subNoPlan: string;
  usageLabel: (month: string) => string;
  invoicesLabel: (month: string) => string;
  plansTitle: string;
  subTitle: string;
  usageTitle: (month: string) => string;
  invoicesTitle: (month: string) => string;
  freePlan: string;
  hardStop: string;
  noOverage: string;
  colPlan: string;
  colMonthly: string;
  colQuotas: string;
  colOverage: string;
  colTime: string;
  colMetric: string;
  colUnits: string;
  colUnit: string;
  colEvent: string;
  colTenant: string;
  colPeriod: string;
  colInvoice: string;
  colLineItems: string;
  colTotal: string;
  colStatus: string;
  missingUnit: string;
  forbiddenReasonIdentity: string;
  forbiddenReasonServer: string;
  forbiddenPanelScope: string;
  forbiddenScopeValue: (roles: string) => string;
  forbiddenPanelSource: string;
  forbiddenSourceValue: string;
  forbiddenHint: string;
  monthAria: string;
  downloadCsv: string;
  perMonth: string;
  noSubscription: string;
  noUsageTitle: string;
  noUsageDescription: string;
  noInvoicesTitle: string;
  noInvoicesDescription: string;
  noPlansTitle: string;
  noPlansDescription: string;
  noSubscriptionChip: string;
  loading: string;
  subscriptionLabels: Record<string, string>;
  invoiceLabels: Record<string, string>;
}

const zh: BillingCopy = {
  title: "用量与账单 Billing & Usage",
  sub: "BILLING · PLANS / SUBSCRIPTION / USAGE LEDGER / INVOICES (RBAC: billing:read)",
  subActivePlan: "当前计划",
  subYesPlan: "active",
  subNoPlan: "无订阅",
  usageLabel: (month) => `本期用量 Usage (${month})`,
  invoicesLabel: (month) => `本期发票 Invoices (${month})`,
  plansTitle: "计划 Plans",
  subTitle: "当前订阅 Subscription",
  usageTitle: (month) => `用量 Usage · ${month} (JSON)`,
  invoicesTitle: (month) => `发票 Invoices · ${month}`,
  freePlan: "免费 Free",
  hardStop: "硬上限 Hard stop",
  noOverage: "硬上限 Hard stop",
  colPlan: "计划 Plan",
  colMonthly: "月费 Monthly",
  colQuotas: "配额 Quotas",
  colOverage: "超量 Overage",
  colTime: "时间 Time",
  colMetric: "指标 Metric",
  colUnits: "用量 Units",
  colUnit: "单位 Unit",
  colEvent: "事件 Event",
  colTenant: "租户 Tenant",
  colPeriod: "周期 Period",
  colInvoice: "发票 Invoice",
  colLineItems: "行项目行数 Line items",
  colTotal: "总额 Total",
  colStatus: "状态 Status",
  missingUnit: "—",
  forbiddenReasonIdentity: "TENANT_FORBIDDEN — 当前角色不能读取账单 billing:read (仅 admin / operator / auditor)",
  forbiddenReasonServer: "TENANT_FORBIDDEN — 服务端拒绝账单读取 billing:read (RBAC fail-closed)",
  forbiddenPanelScope: "范围 Scope",
  forbiddenScopeValue: (roles) =>
    `账单读取 billing:read 仅对 ${roles} 角色开放；viewer 同样会被服务端以 TENANT_FORBIDDEN (403) 拒绝`,
  forbiddenPanelSource: "来源 Source",
  forbiddenSourceValue:
    "权限源自 /auth/me 返回的当前角色 (sp_* API key 或 OIDC id_token)；本页只做显隐，不做判决，RBAC fail-closed 是真实来源",
  forbiddenHint:
    "需要访问？请联系管理员 Contact admin，在 Identity 页调整角色为 admin / operator / auditor，或签发相应范围的令牌。",
  monthAria: "账单月份 Billing period",
  downloadCsv: "下载 CSV Download",
  perMonth: "/月",
  noSubscription: "当前租户暂无订阅 No active subscription for this tenant",
  noUsageTitle: "本期暂无用量记录",
  noUsageDescription: "meter 事件写入时间窗口 [from, to) 内显示空白，没有任何伪造的数字。",
  noInvoicesTitle: "本期暂无发票",
  noInvoicesDescription: "GET /billing/invoices?period= 为空代表本月未出草稿发票",
  noPlansTitle: "没有可读取的计划",
  noPlansDescription: "等待部署时创建的 free / pro 计划",
  noSubscriptionChip: "未订阅 No subscription",
  loading: "加载中 LOADING…",
  subscriptionLabels: { active: "生效中", canceled: "已取消", past_due: "逾期未付", trialing: "试用中" },
  invoiceLabels: { draft: "草稿", issued: "已签发", paid: "已支付", void: "作废" },
};

const en: BillingCopy = {
  title: "Billing & Usage",
  sub: "BILLING · PLANS / SUBSCRIPTION / USAGE LEDGER / INVOICES (RBAC: billing:read)",
  subActivePlan: "Current plan",
  subYesPlan: "active",
  subNoPlan: "No subscription",
  usageLabel: (month) => `Usage (${month})`,
  invoicesLabel: (month) => `Invoices (${month})`,
  plansTitle: "Plans",
  subTitle: "Subscription",
  usageTitle: (month) => `Usage · ${month} (JSON)`,
  invoicesTitle: (month) => `Invoices · ${month}`,
  freePlan: "Free",
  hardStop: "Hard stop",
  noOverage: "Hard stop",
  colPlan: "Plan",
  colMonthly: "Monthly",
  colQuotas: "Quotas",
  colOverage: "Overage",
  colTime: "Time",
  colMetric: "Metric",
  colUnits: "Units",
  colUnit: "Unit",
  colEvent: "Event",
  colTenant: "Tenant",
  colPeriod: "Period",
  colInvoice: "Invoice",
  colLineItems: "Line items",
  colTotal: "Total",
  colStatus: "Status",
  missingUnit: "—",
  forbiddenReasonIdentity: "TENANT_FORBIDDEN — this identity cannot read billing:read (admin / operator / auditor only)",
  forbiddenReasonServer: "TENANT_FORBIDDEN — the server refused the billing:read request (RBAC fail-closed)",
  forbiddenPanelScope: "Scope",
  forbiddenScopeValue: (roles) =>
    `billing:read is limited to ${roles}; viewer also receives TENANT_FORBIDDEN (403) from the server`,
  forbiddenPanelSource: "Source",
  forbiddenSourceValue:
    "Access comes from /auth/me's current role (sp_* API key or OIDC id_token); this page only gates visibility — the server enforces fail-closed",
  forbiddenHint:
    "Need access? Contact admin — set the role to admin / operator / auditor in Identity, or issue a token with the corresponding scope.",
  monthAria: "Billing period",
  downloadCsv: "Download CSV",
  perMonth: "/month",
  noSubscription: "There is no active subscription for this tenant",
  noUsageTitle: "No usage recorded this period",
  noUsageDescription: "Meter events within the [from, to) window render blank — nothing is fabricated.",
  noInvoicesTitle: "No invoices this period",
  noInvoicesDescription: "GET /billing/invoices?period= being empty means no draft was issued this month",
  noPlansTitle: "No plans available",
  noPlansDescription: "Wait for the free / pro plans to be created at deploy time",
  noSubscriptionChip: "No subscription",
  loading: "LOADING…",
  subscriptionLabels: { active: "Active", canceled: "Canceled", past_due: "Past due", trialing: "Trialing" },
  invoiceLabels: { draft: "Draft", issued: "Issued", paid: "Paid", void: "Void" },
};

export const BILLING_BY_LOCALE: Record<Locale, BillingCopy> = { zh, en };
