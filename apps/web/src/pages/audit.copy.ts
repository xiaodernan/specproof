import type { Locale } from "../i18n/strings";

/** Copy for the audit-trail page, per locale. zh keeps the exact literals pinned by Audit.test.tsx. */
export interface AuditCopy {
  forbiddenText: string;
  panelTitle: string;
  scopeLabel: string;
  scopeValuePrefix: string;
  scopeValueSuffix: string;
  hint: string;
  trailTitle: string;
  jobInputLabel: string;
  jobInputPlaceholder: string;
  query: string;
  clearFilter: string;
  limitLabel: string;
  limitRows: (n: number) => string;
  reload: string;
  authDisabledPrefix: string;
  authDisabledHint: string;
  deniedPrefix: string;
  deniedHint: (roles: string) => string;
  genericFailurePrefix: string;
  unknownError: string;
  emptyTitle: string;
  emptyDescription: string;
  colTime: string;
  colActor: string;
  colAction: string;
  colTransition: string;
  colJob: string;
  colDisposition: string;
  actorEmpty: string;
  transitionEmpty: string;
  noJob: string;
  filterNotePrefix: string;
  filterNoteMissingWithRows: string;
  filterNoteMissingNoRows: string;
  filterNotePresent: string;
  filterNoteUnknown: string;
  filterNoteLink: string;
  scopeNoteNull: string;
  scopeNotePartial: (total: number, shown: number, rest: number) => string;
  scopeNoteAll: (total: number) => string;
  scopeNoteTail: string;
  statLoaded: string;
  statPresent: string;
  statPurged: string;
  statUnexplained: string;
  missingJobTitle: string;
  missingJobBody: (job: string) => string;
  noRowsTitle: string;
  noRowsBody: (job: string) => string;
  unknownPresenceTitle: string;
  unknownPresenceBody: string;
  howToReadTitle: string;
  howToReadBody: string;
}

const zh: AuditCopy = {
  forbiddenText: "当前身份没有审计读取权限。",
  panelTitle: "权限说明 Permission explanation",
  scopeLabel: "范围 Scope",
  scopeValuePrefix: "审计读取仅对 ",
  scopeValueSuffix: " 角色开放；operator 与 viewer 会被服务端以 TENANT_FORBIDDEN (403) 拒绝。",
  hint: "需要访问？请联系租户管理员，在 Identity 页调整角色，或签发相应范围的令牌。",
  trailTitle: "审计轨迹 Audit trail",
  jobInputLabel: "按作业号过滤 Job id",
  jobInputPlaceholder: "粘贴作业号查询",
  query: "查询",
  clearFilter: "清除筛选",
  limitLabel: "读取条数 Limit",
  limitRows: (n) => `最近 ${n} 条`,
  reload: "重新读取",
  authDisabledPrefix: "这个部署没有开启多租户鉴权，审计接口不可用（不是没有记录）：",
  authDisabledHint: "审计视图按租户鉴权暴露。开启方式：设置 SPECPROOF_AUTH_ENABLED=true，或配置 OIDC_ISSUER 后重启 API。",
  deniedPrefix: "服务端拒绝了本次审计读取：",
  deniedHint: (roles: string) => `审计读取仅限 ${roles} 角色，请联系管理员调整。`,
  genericFailurePrefix: "审计读取失败：",
  unknownError: "未知错误",
  emptyTitle: "最近没有审计记录",
  emptyDescription: "完成一次验收或取消操作后，这里会出现对应的审计行。",
  colTime: "时间 Time",
  colActor: "操作员 Actor",
  colAction: "动作 Action",
  colTransition: "状态转换 Transition",
  colJob: "作业 Job",
  colDisposition: "作业去向 Disposition",
  actorEmpty: "—",
  transitionEmpty: "—",
  noJob: "无作业",
  filterNotePrefix: "当前按作业号 ",
  filterNoteMissingWithRows: "库里已无这条作业，下面这些是它留下的审计行；作业详情已经打不开",
  filterNoteMissingNoRows: "库里既没有这条作业，也没有它留下的审计行（见下方说明）；作业详情无从链接",
  filterNotePresent: "作业在册 · ",
  filterNoteUnknown: "服务端未回传作业是否存在 · ",
  filterNoteLink: "查看作业详情",
  scopeNoteNull: "服务端未回传命中总数，因此无法判断是否还有未加载的历史。",
  scopeNotePartial: (total, shown, rest) =>
    `这次查询共命中 ${total} 条，这里显示最近的 ${shown} 条，另有 ${rest} 条未加载。`,
  scopeNoteAll: (total) => `这次查询共命中 ${total} 条，已全部显示。`,
  scopeNoteTail: "统计卡只数本页已加载的行。",
  statLoaded: "已加载条数",
  statPresent: "作业在册",
  statPurged: "已按生命周期删除",
  statUnexplained: "引用无法解释",
  missingJobTitle: "没有找到这个作业",
  missingJobBody: (job) =>
    `库里既没有 ${job} 这条作业，也没有它留下的任何审计行。审计行不会因为作业被删除而消失，所以这通常意味着作业号抄错了。`,
  noRowsTitle: "作业在册，但没有审计行",
  noRowsBody: (job) =>
    `${job} 存在于 verification_jobs，却没有记录任何状态转换或取消动作。新建后尚未被 worker 领取的作业就是这样；如果它已经跑完，说明有写入路径绕过了审计。`,
  unknownPresenceTitle: "这个作业号没有返回审计行",
  unknownPresenceBody:
    "服务端没有回传该作业是否存在（job_present 为空），所以无法区分“抄错作业号”与“作业在但没有审计行”。请确认 API 版本已支持按作业检索。",
  howToReadTitle: "怎么读这张表 How to read",
  howToReadBody:
    "每条审计只保存作业号，不保存作业本身。删除作业记录时，系统会在同一事务里补一条 job_records_deleted 说明，因此“作业已删除”是可解释的正常状态；三者都对不上的行会被标为“引用无法解释”，它需要人工排查，而不是被隐藏。排查某一个作业时请用上方的作业号检索：整张表只返回最近若干条，一个作业的轨迹通常根本不在这个窗口里。",
};

const en: AuditCopy = {
  forbiddenText: "This identity does not hold audit-read access.",
  panelTitle: "Permission explanation",
  scopeLabel: "Scope",
  scopeValuePrefix: "Audit read is limited to the roles: ",
  scopeValueSuffix: "; the server answers TENANT_FORBIDDEN (403) to operator and viewer.",
  hint: "Need access? Ask your tenant administrator — in Identity, or issue a token scoped to the audit role.",
  trailTitle: "Audit trail",
  jobInputLabel: "Filter by job id",
  jobInputPlaceholder: "Paste a job id to query",
  query: "Query",
  clearFilter: "Clear filter",
  limitLabel: "Rows to read",
  limitRows: (n) => `Last ${n} rows`,
  reload: "Reload",
  authDisabledPrefix: "This deployment has not enabled multi-tenant auth; the audit endpoint is unavailable (this is not the absence of records): ",
  authDisabledHint: "The audit view is exposed behind tenant auth. Enable it with SPECPROOF_AUTH_ENABLED=true, or set OIDC_ISSUER and restart the API.",
  deniedPrefix: "The server refused this audit read: ",
  deniedHint: (roles: string) => `Audit reads are limited to the roles ${roles}; contact your administrator.`,
  genericFailurePrefix: "Audit read failed: ",
  unknownError: "unknown error",
  emptyTitle: "No audit records in the recent window",
  emptyDescription: "Complete a verification or a cancellation and the corresponding audit row appears here.",
  colTime: "Time",
  colActor: "Actor",
  colAction: "Action",
  colTransition: "Status transition",
  colJob: "Job",
  colDisposition: "Disposition",
  actorEmpty: "—",
  transitionEmpty: "—",
  noJob: "NO JOB",
  filterNotePrefix: "Currently filtering by job ",
  filterNoteMissingWithRows: "the job is gone — these are the audit rows it left behind; the job detail will not open",
  filterNoteMissingNoRows: "neither the job nor any audit rows it left behind exist (see below); no job detail link is possible",
  filterNotePresent: "job is on roster · ",
  filterNoteUnknown: "the server did not report whether the job exists · ",
  filterNoteLink: "View the job detail",
  scopeNoteNull: "the server did not return the match total, so it is unknown whether older history remains unloaded.",
  scopeNotePartial: (total, shown, rest) =>
    `this query matched ${total} rows; showing the most recent ${shown} — ${rest} more remain unloaded.`,
  scopeNoteAll: (total) => `this query matched ${total} rows, all displayed.`,
  scopeNoteTail: "The stat cards count only rows loaded on this page.",
  statLoaded: "Rows loaded",
  statPresent: "Job on roster",
  statPurged: "Purged by lifecycle, as expected",
  statUnexplained: "Reference cannot be explained",
  missingJobTitle: "That job was not found",
  missingJobBody: (job) =>
    `There is no job ${job} in the store, nor any audit rows it left behind. Audit rows do not vanish when a job is deleted, so this usually means the id was mistyped.`,
  noRowsTitle: "The job is on roster, but there are no audit rows",
  noRowsBody: (job) =>
    `${job} exists in verification_jobs but recorded no status transition or cancellation. A freshly created job not yet claimed by a worker looks like this; if it has already finished, a write path bypassed the audit trail.`,
  unknownPresenceTitle: "This job id returned no audit rows",
  unknownPresenceBody:
    "The server did not report whether the job exists (job_present is null), so “mistyped id” and “job exists but no audit rows” are indistinguishable here. Confirm the API supports per-job retrieval.",
  howToReadTitle: "How to read this table",
  howToReadBody:
    "Each audit row stores only the job id, not the job itself. When a job record is deleted, the system writes an explaining job_records_deleted row in the same transaction — so “job deleted” is an explainable, normal state; rows where none of the three line up are marked “reference cannot be explained” and need human review, not hiding. When hunting one job, use the job-id search above: the table only returns the most recent window, and one job's trail may simply not be inside it.",
};

export const AUDIT_BY_LOCALE: Record<Locale, AuditCopy> = { zh, en };
