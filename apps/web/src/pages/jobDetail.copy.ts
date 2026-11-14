/**
 * Copy for the Job Detail page — zh extracted verbatim from the previous
 * inline source (byte-identical, tests stay green); en authored.
 */

import type { Locale } from "../i18n/strings";

export interface JobDetailCopy {
  pendingTitle: string;
  pendingBody: string;
  queuedTitle: string;
  queuedBody: string;
  preparingTitle: string;
  preparingBody: string;
  contractReviewTitle: string;
  contractReviewBody: string;
  runningTitle: string;
  runningBody: string;
  reviewingTitle: string;
  reviewingBody: string;
  waitingProviderTitle: string;
  waitingProviderBody: string;
  verifiedTitle: string;
  verifiedBody: string;
  blockedTitle: string;
  blockedBody: string;
  needsReviewTitle: string;
  needsReviewBody: string;
  failedTitle: string;
  failedBody: string;
  cancelledTitle: string;
  cancelledBody: string;
  staleTitle: string;
  staleBody: string;
  expiredTitle: string;
  expiredBody: string;
  errorTitle: string;
  errorBody: string;
  depthFast: string;
  depthStandard: string;
  depthDeep: string;
  classificationStable: string;
  classificationFlaky: string;
  classificationSingle: string;
  classificationNoRuns: string;
  classificationContaminated: string;
  invoiceDraft: string;
  invoiceIssued: string;
  invoicePaid: string;
  invoiceVoid: string;
  colSeverity: string;
  colCondition: string;
  colEvidence: string;
  colConfidence: string;
  colDescription: string;
  colCapsule: string;
  viewDetails: string;
  download: string;
  backToJobs: string;
  refresh: string;
  retry: string;
  taskNotFound: string;
  viewThisVerdict: string;
  followMatrix: string;
  viewFindingsBlocked: string;
  viewCertificate: string;
  learnGaps: string;
  viewUnverified: string;
  jobsLabel: string;
  detailLabel: string;
  demoLabel: string;
  verdictAndEvidence: string;
  notVerifiedConfirmation: string;
  preflightManual: string;
  runStepsInline: string;
  evidenceArtifacts: string;
  reportPath: string;
  retrievalNote: string;
  executionLog: string;
  capsuleLabel: string;
  evidenceFold: string;
  downloadsLabel: string;
  deepDisclosure: string;
  verdictStability: string;
  verdictRepeat: string;
  cacheIntegrity: string;
  deepReport: string;
  summaryLoadFailedView: string;
  activeRunView: string;
  failedTerminalView: string;
  failedTerminalBody: string;
  terminalNoSummary: string;
  terminalNoSummaryBody: string;
  unknownState: string;
  unknownStateBody: string;
  taskInfo: string;
  repoPath: string;
  compareRefs: string;
  specPath: string;
  verifyMode: string;
  retryCount: string;
  createdAt: string;
  updatedAt: string;
  lastErrorLabel: string;
  executionStages: string;
  realtime: string;
  connecting: string;
  terminal: string;
  noStagesYet: string;
  realtimeLog: string;
  findingsLabel: string;
  findingsLoadFailedView: string;
  noFindings: string;
  certificate: string;
  signedStatement: string;
  noSignedFile: string;
  certificateContent: string;
  fixIssues: string;
  coverageSalon: string;
  verdictNotDecided: string;
  verdictUnmeasurable: string;
  verdictCannotConfirm: string;
  verdictEvidenceOk: string;
  notPassed: string;
  unverified: string;
  notPassedConfirmation: string;
  notPassedSummary: string;
  aiReading: string;
  aiReadingHint: string;
  aiReadingNotVerdict: string;
  aiReadingThis: string;
  aiReadingUnavailable: string;
  alreadyIssued: string;
  alreadyPaid: string;
  amountLabel: string;
  artifactLoadFailed: string;
  auditTrail: string;
  cacheHit: string;
  cannotConfirm: string;
  capsuleHeaderTitle: string;
  certificateFile: string;
  checkFailed: string;
  copiedBadge: string;
  copyEpicCertificate: string;
  copyFailed: string;
  copyMarkdown: string;
  copyReviewLink: string;
  copySummary: string;
  deepExplanation: string;
  emptyParen: string;
  evidenceFoldSuffix: (n: number) => string;
  explainInterrupted: string;
  explaining: string;
  failedAtPrefix: string;
  findingsBlocked: (n: number) => string;
  frames: string;
  invoiceReadFailed: string;
  invoiceReadFailedPrefix: string;
  issueButton: string;
  lineItemsLabel: string;
  markPaid: string;
  memoryOnly: string;
  metricLabel: string;
  modelDirect: string;
  nextStepColon: string;
  nextSteps: string;
  noCapsule: string;
  noLineItems: string;
  periodNoInvoice: string;
  quantityLabel: string;
  readingEvidence: string;
  reexplain: string;
  repeatRunsPrefix: (n: number) => string;
  reportLoadFailed: string;
  reportPending: string;
  reviewLinkExplain: string;
  signatureMaterials: string;
  signedFile: string;
  sseProgress: string;
  stages: string;
  startedAtPrefix: string;
  statusLabel: string;
  streamingDesc: string;
  tabInvoice: string;
  tabOverview: string;
  tabReport: string;
  totalLabel: string;
  unitPriceLabel: string;
  unknownStateTail: string;
  unnamedRepo: string;
  verdictLabel: string;
  viewCoverage: string;
  waitingProgress: string;
  waitingProgressEvents: string;
  zeroFrames: string;
}

const zh: JobDetailCopy = {
  pendingTitle: "验证已创建，正在排队",
  pendingBody: "系统已受理，等待执行服务接手。进度会自动出现在这里，可以先离开。",
  queuedTitle: "验证已创建，等待执行",
  queuedBody: "执行服务接手后，进度会自动出现在这里。可以先离开，稍后从验证记录继续查看。",
  preparingTitle: "正在准备验证环境",
  preparingBody: "正在准备 Base/Head 工作区与依赖，尚未开始执行检查。准备完成后会自动进入验收。",
  contractReviewTitle: "等待契约审批",
  contractReviewBody: "需求契约已编译出来，等待人工批准。批准后本次验证继续执行；未批准的契约不能支撑阻断级结论。",
  runningTitle: "正在检查代码与需求",
  runningBody: "系统正在分析改动、收集证据并核对需求。完成后会自动更新结论。",
  reviewingTitle: "评审裁决中",
  reviewingBody: "差分实验已完成，正在由评审庭按证据政策裁决结论。裁决完成后会自动更新结论。",
  waitingProviderTitle: "正在等待模型服务",
  waitingProviderBody: "任务已保存，模型服务恢复可用后将继续处理。",
  verifiedTitle: "本次验证通过",
  verifiedBody: "已验证的需求具备支持证据。合并前建议确认需求覆盖范围，以及是否仍有未验证项。",
  blockedTitle: "发现需要处理的问题",
  blockedBody: "先查看风险发现及其证据，再决定如何修改代码。需求矩阵可帮助定位受影响的验收条件。",
  needsReviewTitle: "需要人工判断",
  needsReviewBody: "证据不足以自动下结论：既没有确认回归，也没有证明通过。请查看需求矩阵与未验证项后人工判断。",
  failedTitle: "本次验证未能完成",
  failedBody: "执行失败不代表代码有问题。请查看任务信息中的错误原因，处理环境或服务问题后重新验证。",
  cancelledTitle: "验证已取消",
  cancelledBody: "本次执行已停止，需要继续时可以创建新的验证任务。",
  staleTitle: "本次验证已过期",
  staleBody: "代码版本可能已变化，请基于最新提交重新验证。",
  expiredTitle: "本次验证已超时",
  expiredBody: "执行超过了允许的时限，已被回收。请缩小范围或调整环境后重新验证。",
  errorTitle: "执行遇到错误",
  errorBody: "请查看错误原因，处理执行环境或服务问题后重新验证。",
  depthFast: "快速验证",
  depthStandard: "标准验证",
  depthDeep: "深度验证",
  classificationStable: "结论稳定",
  classificationFlaky: "结论不稳定",
  classificationSingle: "仅单次运行",
  classificationNoRuns: "无重复运行",
  classificationContaminated: "环境受污染",
  invoiceDraft: "草稿",
  invoiceIssued: "已开具",
  invoicePaid: "已支付",
  invoiceVoid: "已作废",
  colSeverity: "严重程度",
  colCondition: "验收条件",
  colEvidence: "证据方式",
  colConfidence: "置信度",
  colDescription: "描述",
  colCapsule: "复现包",
  viewDetails: "查看详情",
  download: "下载",
  backToJobs: "返回任务列表",
  refresh: "刷新结果",
  retry: "重试",
  taskNotFound: "任务不存在（404）",
  viewThisVerdict: "查看本次验证结果",
  followMatrix: "结合需求覆盖与风险证据判断本次改动，未验证项需要进一步确认。",
  viewFindingsBlocked: "查看",
  viewCertificate: "查看验证报告 →",
  learnGaps: "了解支持的验收方式 →",
  viewUnverified: "逐项查看未确认的验收条件 →",
  jobsLabel: "验证记录",
  detailLabel: "验证详情",
  demoLabel: "演示",
  verdictAndEvidence: "本次验收结论未能确认",
  notVerifiedConfirmation: "覆盖不足，暂不能确认验收通过",
  preflightManual: "本次没有形成可执行的检查项。请完善验收条件，或接入对应检查器后重新验收。",
  runStepsInline: " 项检查，结论仍不能确认为通过。请查看上方原因，并结合需求覆盖与风险证据判断。",
  evidenceArtifacts: "证据与产物",
  reportPath: "报告路径",
  retrievalNote: "检索说明",
  executionLog: "执行记录",
  capsuleLabel: "复现包",
  evidenceFold: "证据折叠",
  downloadsLabel: " 份可下载材料",
  deepDisclosure: "DEEP 深度验证披露",
  verdictStability: "结论稳定度",
  verdictRepeat: " 次重复运行）",
  cacheIntegrity: "缓存完整度",
  deepReport: "深度报告",
  summaryLoadFailedView: "验证结果暂时无法读取（请求失败）。这不代表没有结果，请点击刷新重试。",
  activeRunView: "验证仍在执行中，完成后这里会展示结论、需求覆盖与风险证据。",
  failedTerminalView: "这一轮以执行失败结束，记录里没有验证摘要。",
  failedTerminalBody: "失败不会随刷新补出摘要：结论、覆盖与风险要在一次新的验证里重新产生。下方“最近执行错误”说明这一轮失败的原因；“执行进度”说明它停在哪一步。",
  terminalNoSummary: "任务已进入终态，但记录里没有验证摘要。",
  terminalNoSummaryBody: "这条不会随刷新补上。终态与摘要现在是同一条写入，因此读不到摘要意味着这一轮的证据当时就没有落库（多为该改动之前完成的历史任务）。可以用“执行进度”与“风险发现”判断这一轮走到哪里，需要结论时重新发起验证。",
  unknownState: "任务状态为 ",
  unknownStateBody: "未识别状态既不等于已终态，也不等于仍在执行，所以这里不下结论。",
  taskInfo: "任务信息",
  repoPath: "项目路径",
  compareRefs: "比较版本",
  specPath: "需求文件",
  verifyMode: "验证模式",
  retryCount: "重试次数",
  createdAt: "创建时间",
  updatedAt: "更新时间",
  lastErrorLabel: "最近执行错误",
  executionStages: "执行阶段 · ",
  realtime: "实时更新中",
  connecting: "正在连接进度",
  terminal: "执行已结束",
  noStagesYet: "暂无执行进度，任务可能尚未开始。",
  realtimeLog: "实时执行日志",
  findingsLabel: "风险发现",
  findingsLoadFailedView: "风险扫描结果暂时无法读取（请求失败）。无法确认是否存在风险，请勿据此判定为安全；点击刷新重试。",
  noFindings: "暂未发现已确认的问题。请同时检查需求覆盖情况；没有风险记录不代表所有需求均已验证。",
  certificate: "合并证书 / 拒绝通知",
  signedStatement: "签名声明（in-toto 风格，供审计核验）",
  noSignedFile: "暂无 Ed25519 签名文件（未配置签名密钥时，仅提供未签名摘要 — 如实呈现，不伪造可信签名）。",
  certificateContent: "证书内容（原始 JSON）",
  fixIssues: "发现需要处理的问题",
  coverageSalon: "查看验证报告 →",
  verdictNotDecided: "本次验收结论未能确认",
  verdictUnmeasurable: "本次不能确认验收通过",
  verdictCannotConfirm: "覆盖不足，暂不能确认验收通过",
  verdictEvidenceOk: "已通过",
  notPassed: "未通过",
  unverified: "尚未验证",
  notPassedConfirmation: "本次没有形成可执行的检查项。请完善验收条件，或接入对应检查器后重新验收。",
  notPassedSummary: "本次已形成",
  aiReading: "AI 解读",
  aiReadingHint: "点一下「AI 解读本次验收」，把结论编译成评审者能直接读的一段话。判决仍沿用上方的确定性证据，AI 不做判决。",
  aiReadingNotVerdict: "AI 解读 · 不是判决",
  aiReadingThis: "AI 解读本次验收",
  aiReadingUnavailable: "AI 解读不可用",
  alreadyIssued: "已开具",
  alreadyPaid: "已支付",
  amountLabel: "金额 Amount",
  artifactLoadFailed: "部分验证结果暂时无法读取，任务状态仍可查看。点击刷新可重试。",
  auditTrail: "查看这个作业的审计轨迹",
  cacheHit: "Redis 缓存命中",
  cannotConfirm: "覆盖不足，暂不能确认验收通过",
  capsuleHeaderTitle: "复现包下载 · 评审链接",
  certificateFile: "证书文件",
  checkFailed: "请查看上方原因，并结合需求覆盖与风险证据判断本次结论。",
  copiedBadge: "已复制",
  copyEpicCertificate: "复制史诗纪要",
  copyFailed: "无法写入剪贴板（浏览器拒绝了权限）。",
  copyMarkdown: "复制 Markdown 摘要",
  copyReviewLink: "复制评审链接",
  copySummary: "复制摘要",
  deepExplanation: "执行说明",
  emptyParen: "（空）",
  evidenceFoldSuffix: (n) => ` · ${n} 份可下载材料`,
  explainInterrupted: "以上文本已到达但解读被中断，下面是完整错误。",
  explaining: "正在解读…",
  failedAtPrefix: "失败于",
  findingsBlocked: (n) => `查看 ${n} 条风险并处理 →`,
  frames: "个帧",
  invoiceReadFailed: "发票读取失败",
  invoiceReadFailedPrefix: "读取发票失败：",
  issueButton: "开票 Issued",
  lineItemsLabel: "行项目 Line Items",
  markPaid: "标记支付 Paid",
  memoryOnly: "本地内存可见",
  metricLabel: "指标 Metric",
  modelDirect: "模型直出",
  nextStepColon: "下一步：",
  nextSteps: "下一步操作",
  noCapsule: "本次没有生成复现包（结论靠可执行证据判定，不依赖下载材料）",
  noLineItems: "无行项目",
  periodNoInvoice: "该周期暂无发票。计费 cron 在次月月初会自动生成草稿。",
  quantityLabel: "数量 Amount",
  readingEvidence: "正在读取证据、编译解读…",
  reexplain: "重新解读",
  repeatRunsPrefix: (n) => `（${n} 次重复运行）`,
  reportLoadFailed: "报告读取失败",
  reportPending: "暂未生成验证报告，任务完成后可再次查看。",
  reviewLinkExplain: "链接指向同一个租户的同一份证据：复制给有权限的同事，他打开就能看到本次验收的结论、契约与证据。资格审查仍走租户权限。",
  signatureMaterials: "签名材料",
  signedFile: "签名文件",
  sseProgress: "流式进度",
  stages: "执行进度",
  startedAtPrefix: "开始：",
  statusLabel: "状态 Status",
  streamingDesc: "正在流式生成…（按帧到达，约为上文）",
  tabInvoice: "发票 Invoice",
  tabOverview: "验证概览",
  tabReport: "验证报告",
  totalLabel: "合计 Total",
  unitPriceLabel: "单价 Unit Price",
  unknownStateTail: "，这是本页面未识别的状态，且记录里没有验证摘要。",
  unnamedRepo: "验证",
  verdictLabel: "验证结论",
  viewCoverage: "查看需求覆盖 →",
  waitingProgress: "等待执行进度",
  waitingProgressEvents: "等待进度事件…",
  zeroFrames: "0 个帧",
};

const en: JobDetailCopy = {
  pendingTitle: "Verification created; waiting in the queue",
  pendingBody: "The system accepted it; the execution service will pick it up. Progress appears here automatically — feel free to leave.",
  queuedTitle: "Verification created; waiting to run",
  queuedBody: "When the execution service picks it up, progress appears here. You can leave and come back via the verification list.",
  preparingTitle: "Preparing the verification environment",
  preparingBody: "Preparing the Base/Head workspaces and dependencies; checks have not started yet. The verification begins when ready.",
  contractReviewTitle: "Waiting for contract approval",
  contractReviewBody: "The requirement contracts are compiled; waiting for a human approval. Once approved, the verification continues; unapproved contracts cannot justify blocking conclusions.",
  runningTitle: "Inspecting the code and the requirements",
  runningBody: "The system is analyzing the change, collecting evidence, and checking requirements. The verdict updates when it finishes.",
  reviewingTitle: "The Review Court is deciding",
  reviewingBody: "The differential run finished; the review court is deciding per the evidence policy. The verdict updates upon conclusion.",
  waitingProviderTitle: "Waiting for the model service",
  waitingProviderBody: "The job is saved; it continues when the model service recovers.",
  verifiedTitle: "This verification passed",
  verifiedBody: "Verified requirements carry supporting evidence. Before merging, confirm the coverage range, and whether items remain unverified.",
  blockedTitle: "Issues needing your attention",
  blockedBody: "Read the findings and their evidence first, then decide how to change the code. The coverage matrix helps locate the affected conditions.",
  needsReviewTitle: "Human judgment required",
  needsReviewBody: "The evidence does not support an automatic conclusion: no confirmed regression, no proof of passing either. Review the coverage matrix and the unverified items, then decide.",
  failedTitle: "This verification could not finish",
  failedBody: "Execution failure does not mean the code is broken. Check the error reason, fix the environment or service, and re-verify.",
  cancelledTitle: "Verification cancelled",
  cancelledBody: "Execution stopped; create a new verification task to continue.",
  staleTitle: "This verification expired",
  staleBody: "The code refs may have moved; re-verify on the latest commit.",
  expiredTitle: "This verification is overdue",
  expiredBody: "Execution exceeded the deadline and was reclaimed. Narrow the scope or adjust the environment and re-verify.",
  errorTitle: "Execution error",
  errorBody: "Check the error reason, fix the environment or service, and re-verify.",
  depthFast: "FAST verification",
  depthStandard: "STANDARD verification",
  depthDeep: "DEEP verification",
  classificationStable: "Stable verdict",
  classificationFlaky: "Unstable verdict",
  classificationSingle: "Single run only",
  classificationNoRuns: "No repeated runs",
  classificationContaminated: "Environment contaminated",
  invoiceDraft: "Draft",
  invoiceIssued: "Issued",
  invoicePaid: "Paid",
  invoiceVoid: "Void",
  colSeverity: "Severity",
  colCondition: "Condition",
  colEvidence: "Evidence kind",
  colConfidence: "Confidence",
  colDescription: "Description",
  colCapsule: "Bug capsule",
  viewDetails: "View details",
  download: "Download",
  backToJobs: "Back to jobs",
  refresh: "Refresh result",
  retry: "Retry",
  taskNotFound: "Task not found (404)",
  viewThisVerdict: "View this verification's results",
  followMatrix: "Judge this change from the coverage matrix and the evidence — unverified items need your judgment.",
  viewFindingsBlocked: "View",
  viewCertificate: "View the verification report →",
  learnGaps: "Learn how to complete verification →",
  viewUnverified: "Review the unconfirmed conditions →",
  jobsLabel: "Verifications",
  detailLabel: "Verification detail",
  demoLabel: "DEMO",
  verdictAndEvidence: "The verdict could not be confirmed",
  notVerifiedConfirmation: "Coverage is insufficient to confirm this change is safe",
  preflightManual: "No executable checks were produced. Complete the acceptance conditions, or connect the matching checker, then re-verify.",
  runStepsInline: " checks were recorded, the verdict still cannot be confirmed. See the reason above, and judge from coverage and evidence.",
  evidenceArtifacts: "Evidence and artifacts",
  reportPath: "Report path",
  retrievalNote: "Retrieval note",
  executionLog: "Execution record",
  capsuleLabel: "Bug capsule",
  evidenceFold: "Evidence (folded)",
  downloadsLabel: " downloadable artifacts",
  deepDisclosure: "DEEP deep-verification disclosure",
  verdictStability: "Verdict stability",
  verdictRepeat: " repeated runs)",
  cacheIntegrity: "Cache integrity",
  deepReport: "Deep report",
  summaryLoadFailedView: "The verification result could not be loaded (request failed). This does not mean there is no result — refresh and retry.",
  activeRunView: "Verification is still running; the verdict, coverage and evidence will appear here when it finishes.",
  failedTerminalView: "This run ended in failure; the record carries no verdict summary.",
  failedTerminalBody: "Refreshing will not back-fill a summary: verdicts, coverage and risk must be produced fresh by a new verification run. The “recent error” and the “stages” views tell you where it stopped.",
  terminalNoSummary: "The task reached a terminal state without a verdict summary.",
  terminalNoSummaryBody: "This will not back-fill by refreshing. Terminal state and summary are one write, so the absence means the evidence never landed (usually tasks finished before this change set shipped). Use “Stages” and “Findings” to see where it stopped; re-run for the verdict.",
  unknownState: "Task status is ",
  unknownStateBody: "An unrecognized status is neither terminal nor running, so no conclusion is drawn.",
  taskInfo: "Task information",
  repoPath: "Repository path",
  compareRefs: "Compared refs",
  specPath: "Requirement file",
  verifyMode: "Verification mode",
  retryCount: "Retry count",
  createdAt: "Created",
  updatedAt: "Updated",
  lastErrorLabel: "Most recent execution error",
  executionStages: "Execution stage · ",
  realtime: "Live updates",
  connecting: "Connecting to progress…",
  terminal: "Execution finished",
  noStagesYet: "No execution stages yet; the task may not have started.",
  realtimeLog: "Live execution log",
  findingsLabel: "Findings",
  findingsLoadFailedView: "The findings scan could not be loaded (request failed). Whether risks exist is unknown — do not treat this as clean; retry by refreshing.",
  noFindings: "No confirmed issues yet. Also check the coverage matrix; having no findings does not mean every requirement was verified.",
  certificate: "Merge certificate / Rejection notice",
  signedStatement: "Signature declaration (in-toto style, for audit)",
  noSignedFile: "No Ed25519 signature file yet (when no signing key is configured, only an unsigned digest is provided — presented honestly, never fabricated).",
  certificateContent: "Certificate content (raw JSON)",
  fixIssues: "Issues needing your attention",
  coverageSalon: "View the verification report →",
  verdictNotDecided: "The verdict could not be confirmed",
  verdictUnmeasurable: "Cannot confirm this change is safe to merge",
  verdictCannotConfirm: "Coverage is insufficient to confirm this change is safe",
  verdictEvidenceOk: "Passed",
  notPassed: "Not passed",
  unverified: "Unverified",
  notPassedConfirmation: "No executable checks were produced. Complete the acceptance conditions, or connect the matching checker, then re-verify.",
  notPassedSummary: "This produced",
  aiReading: "AI reading",
  aiReadingHint: "Press “AI reading of this verification” — the verdict compiles into a paragraph a reviewer can read. The judgement remains the deterministic evidence above; the AI passes no verdict.",
  aiReadingNotVerdict: "AI reading · not a verdict",
  aiReadingThis: "AI reading of this verification",
  aiReadingUnavailable: "AI reading unavailable",
  alreadyIssued: "Already issued",
  alreadyPaid: "Already paid",
  amountLabel: "Amount",
  artifactLoadFailed: "Some verification results could not be loaded; the task state is still shown. Refresh to retry.",
  auditTrail: "View this job's audit trail",
  cacheHit: "Redis cache hit",
  cannotConfirm: "Coverage is insufficient to confirm this change is safe",
  capsuleHeaderTitle: "Bug capsule download · Review link",
  certificateFile: "Certificate file",
  checkFailed: "See the reason above, and judge from coverage and evidence.",
  copiedBadge: "Copied",
  copyEpicCertificate: "Copy the epic digest",
  copyFailed: "Could not write to the clipboard (the browser rejected the permission).",
  copyMarkdown: "Copy Markdown summary",
  copyReviewLink: "Copy review link",
  copySummary: "Copy summary",
  deepExplanation: "Execution notes",
  emptyParen: "(empty)",
  evidenceFoldSuffix: (n) => ` · ${n} downloadable artifacts`,
  explainInterrupted: "The text above arrived but the reading was interrupted; the full error is below.",
  explaining: "Reading…",
  failedAtPrefix: "Failed at ",
  findingsBlocked: (n) => `View the ${n} risks →`,
  frames: "frames",
  invoiceReadFailed: "Invoice read failed",
  invoiceReadFailedPrefix: "Failed to read the invoice: ",
  issueButton: "Issue",
  lineItemsLabel: "Line items",
  markPaid: "Mark Paid",
  memoryOnly: "Visible in local memory only",
  metricLabel: "Metric",
  modelDirect: "Model direct output",
  nextStepColon: "Next: ",
  nextSteps: "Next step",
  noCapsule: "No reproduction capsule this run (the verdict rests on executable evidence, not downloadable artifacts)",
  noLineItems: "No line items",
  periodNoInvoice: "No invoice for this period. The billing cron generates the draft on the first of next month.",
  quantityLabel: "Amount",
  readingEvidence: "Reading the evidence, compiling the reading…",
  reexplain: "Read again",
  repeatRunsPrefix: (n) => ` (${n} repeated runs)`,
  reportLoadFailed: "Failed to load the report",
  reportPending: "The verification report isn't ready yet; check again when the task finishes.",
  reviewLinkExplain: "The link points at the same evidence in the same tenant: paste it to a colleague and they will see this verification's verdict, contracts and evidence. Authorization still rides on tenant access.",
  signatureMaterials: "Signature materials",
  signedFile: "Signature file",
  sseProgress: "SSE progress",
  stages: "Stages",
  startedAtPrefix: "Started: ",
  statusLabel: "Status",
  streamingDesc: "Streaming… (arrives frame by frame, roughly as above)",
  tabInvoice: "Invoice",
  tabOverview: "Overview",
  tabReport: "Verification report",
  totalLabel: "Total",
  unitPriceLabel: "Unit price",
  unknownStateTail: ", this state was not recognized by this page, and the record carries no verdict summary.",
  unnamedRepo: "Verification",
  verdictLabel: "Verdict",
  viewCoverage: "View coverage →",
  waitingProgress: "Waiting for progress",
  waitingProgressEvents: "Waiting for progress events…",
  zeroFrames: "0 frames",
};

export const JOB_DETAIL_BY_LOCALE: Record<Locale, JobDetailCopy> = { zh, en };
