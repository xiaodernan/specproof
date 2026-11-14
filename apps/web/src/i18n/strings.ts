/**
 * The shared string table — one key, two locales, no mixing.
 *
 * `apps/web/src/i18n/__tests__/i18n.parity.test.ts` fails the build when a key
 * exists in one locale and not the other. A mixed screen is a bug, not a
 * fallback.
 */

export type Locale = "zh" | "en";

const zh = {
  // ── navigation ────────────────────────────────────────────────
  "nav.dashboard": "工作台",
  "nav.jobs": "变更验收",
  "nav.agent": "AI 开发",
  "nav.explorer": "案件档案",
  "nav.matrix": "需求覆盖",
  "nav.contracts": "验收规则",
  "nav.eval": "效果评测",
  "nav.identity": "团队与权限",
  "nav.billing": "用量与账单",
  "nav.usage": "缓存健康",
  "nav.audit": "审计轨迹",
  "nav.settings": "模型连接",
  "nav.health": "服务状态",
  "nav.epic": "史诗",
  "nav.tour": "巡览",

  // ── groups ─────────────────────────────────────────────────────
  "group.workspace": "工作空间",
  "group.evidence": "质量与证据",
  "group.admin": "管理",

  // ── topbar ─────────────────────────────────────────────────────
  "topbar.search": "搜索页面与操作",
  "topbar.help": "使用帮助",
  "topbar.switchTheme": "切换主题",
  "topbar.switchLocale": "切换语言",
  "topbar.breadcrumb.workspace": "工作空间",

  // ── common ─────────────────────────────────────────────────────
  "common.copy": "复制",
  "common.copied": "已复制",
  "common.retry": "重试",
  "common.refresh": "刷新",
  "common.close": "关闭",
  "common.cancel": "取消",
  "common.confirm": "确认",
  "common.loading": "加载中",
  "common.unknown": "未知",
  "common.notProvided": "未提供",
  "common.back": "返回",
  "common.next": "下一步",
  "common.previous": "上一步",
  "common.more": "更多",
  "common.open": "打开",
  "common.download": "下载",
  "common.signIn": "连接工作区",
  "common.signOut": "退出",
  "common.credentialMissing": "没有凭据",
  "common.credentialPresent": "凭据已配置",

  // ── Epic page ──────────────────────────────────────────────────
  "epic.title": "史诗",
  "epic.subtitle": "THE CHRONICLES OF SPECPROOF",
  "epic.lead":
    "一部关于「验收」的史书——为 AI 写下的每一行代码验明来路、坐实铁证、定谳如山。本页每一卷都对应本项目仓库中的真实实录；翻到哪一卷，都该能在 git 历史和账本里找到同一件事。",
  "epic.scrolls": "卷",
  "epic.chronicleNote": "可核验",
  "epic.colophon":
    "本页由史官（也就是这个仓库里的每一次提交）立下：2026-09 → 今。账本在 docs/operations/DEEP_OPTIMIZATION_PLAN.md，路线图在 docs/operations/PRODUCT_ROADMAP.md；铁证不因多而更硬，也不因少而失重。",
  "epic.readWorld": "读全本《铁证之书》",
  "epic.readLexicon": "查铁证词典",

  // ── Tour page ──────────────────────────────────────────────────
  "tour.title": "巡览",
  "tour.subtitle": "THE GRAND TOUR OF SPECPROOF",
  "tour.lead":
    "六卷：连接 · 阅读 · 查证 · 读痕迹 · 落笔 · 盖印——每卷都是真实查验，不是指南里的第一百个链接。完成一卷盖一卷，盖完六枚，成「验讫」。",
  "tour.prologue":
    "巡览不是清单，是第一夜之旅。所谓「走完巡览」——不是每一页都点过，而是每一桩真实的查验都被你按了一次手印。六卷盖了五枚，你比进来的你更像验收官；盖了第六枚，章上的字便从「访客」变成「验收官」。",
  "tour.chapter": "卷",
  "tour.task": "行",
  "tour.tip": "授意",
  "tour.seal": "盖上此卷",
  "tour.unseal": "撕掉此卷（反悔）",
  "tour.progress": "卷已盖",
  "tour.sealedTitle": "六卷齐盖，章落。",
  "tour.sealedBody":
    "SpecProof 的史官记下了这一页——你不是本产品的访客了，而是知道这件事、做这件事、敢盖章的人。",
  "tour.hint": "空着的印记才有意义——每一页你盖上去，都是给自己的。",
  "tour.reset": "重新巡览（擦除本机印记）",
  "tour.colophon":
    "巡览状态仅保存在本机 localStorage；换浏览器、换电脑、换无痕窗口，一切重新走起。这不是缺陷，这是 SpecProof 的一贯性情：你的信任必须从零捡起。",
  "tour.corrupted": "本机巡览进度读不出来",
  "tour.corruptedBody":
    "localStorage 里的巡览进度解析失败——可能是手动改坏了，或者浏览器换了 profile。这不等于没走过：本页按全新状态呈现，旧印记已被隔离。",
  "tour.saveFailed": "盖下的印刻不进去了",
  "tour.saveFailedBody":
    "本机存储被禁用（可能是无痕模式或策略）。此处的「完成」不会在刷新后保留——界面如实告诉你这一点，而不是骗你「已保存」。",

  // ── Explorer page ──────────────────────────────────────────────
  "explorer.title": "案件档案",
  "explorer.subtitle": "THE CASE FILE",
  "explorer.lead":
    "一份装订机与印章构成的案卷——所有字句都来自服务器返回的数字，没有 LLM 给的文学一致性。",
  "explorer.sealPanel": "印章",
  "explorer.loading": "装订前翻检…",
  "explorer.empty": "本机没有一桩验收记录尚可装订。先去完成一次验收，再来翻案。",
  "explorer.repo": "仓库",
  "explorer.change": "变更",
  "explorer.opened": "开卷日期",
  "explorer.caseNo": "案卷号",
  "explorer.conditions": "验收条件",
  "explorer.passed": "已通过",
  "explorer.failed": "未通过",
  "explorer.unverified": "未验证",
  "explorer.evidencePanel": "铁证清单",
  "explorer.noFindings":
    "此案无发现——这不等于没有缺陷，只等于本次验收未逮到。缺什么铁证，就该补什么证据。",
  "explorer.tally": "此案被判为「{verdict}」。AI 在本案中没有作决定，证据替它开口。",
  "explorer.capsulePanel": "案卷索取",
  "explorer.noCapsule": "本卷未交出复现包（可能是 DEMO 演示卷——请看全程）",
  "explorer.reportPath": "报告路径",
  "explorer.status": "执行轨迹",
  "explorer.tierIron": "铁",
  "explorer.tierSemiIron": "半铁",
  "explorer.tierQuiet": "静",
  "explorer.tierBroken": "坏",
  "explorer.tierScript": "文",
  "explorer.tierUnknown": "?",

  // ── Usage page ─────────────────────────────────────────────────
  "usage.title": "缓存健康",
  "usage.subtitle": "CACHE HEALTH",
  "usage.lead":
    "LLM 每次调用 token 的实测账本——命中率、流式占比、延迟、按类型拆分，一览无余。命中率只按网关真正上报的调用计，绝不补零。",
  "usage.window": "窗口",
  "usage.window.1h": "1 小时",
  "usage.window.24h": "24 小时",
  "usage.window.7d": "7 天",
  "usage.window.30d": "30 天",
  "usage.hitRate": "缓存命中率",
  "usage.savedTokens": "缓存节省 token",
  "usage.totalTokens": "总 token",
  "usage.calls": "调用次数",
  "usage.p50": "延迟 P50",
  "usage.p95": "延迟 P95",
  "usage.basis":
    "命中率只统计网关上报 cached_tokens 的调用（本窗口 {basis} 次）；未上报的调用计入调用次数、不计入命中率；网关未上报时命中率显示为「—」，绝不补零。",
  "usage.errorRate": "错误率",
  "usage.streamRatio": "流式占比",
  "usage.streamAria": "流式占比",
  "usage.streamShare": "流式调用占比",
  "usage.byKind": "按调用类型拆分",
  "usage.trend": "每小时趋势",
  "usage.trendEmpty": "窗口内没有任何小时桶——等真实调用落一批再看趋势。",
  "usage.callsOnly": "调用次数",
  "usage.hitRateLegend": "命中率（null = 网关未上报 → 折线断档，不画假点）",
  "usage.generatedAt": "生成于",
  "usage.emptyTitle": "缓存健康",
  "usage.emptyText":
    "账本尚无记录——等真实 LLM 调用跑一批后，这里会开始累计命中率、流式占比与延迟；空账本不编造任何数字。",
  "usage.degraded":
    "LLM 用量账本（只读聚合端点 /api/v1/llm/usage/summary）暂时不可用——本页不伪造任何数据；等端点恢复后自动恢复显示。",
} as const;

const en: Record<keyof typeof zh, string> = {
  "nav.dashboard": "Dashboard",
  "nav.jobs": "Verifications",
  "nav.agent": "AI Developer",
  "nav.explorer": "Case File",
  "nav.matrix": "Requirement Coverage",
  "nav.contracts": "Contracts",
  "nav.eval": "Effectiveness",
  "nav.identity": "Team & Access",
  "nav.billing": "Usage & Billing",
  "nav.usage": "Cache Health",
  "nav.audit": "Audit Trail",
  "nav.settings": "Model Connection",
  "nav.health": "Service Status",
  "nav.epic": "Chronicles",
  "nav.tour": "Grand Tour",

  "group.workspace": "Workspace",
  "group.evidence": "Quality & Evidence",
  "group.admin": "Administration",

  "topbar.search": "Search pages and actions",
  "topbar.help": "Help",
  "topbar.switchTheme": "Switch theme",
  "topbar.switchLocale": "Switch language",
  "topbar.breadcrumb.workspace": "Workspace",

  "common.copy": "Copy",
  "common.copied": "Copied",
  "common.retry": "Retry",
  "common.refresh": "Refresh",
  "common.close": "Close",
  "common.cancel": "Cancel",
  "common.confirm": "Confirm",
  "common.loading": "Loading…",
  "common.unknown": "Unknown",
  "common.notProvided": "Not provided",
  "common.back": "Back",
  "common.next": "Next",
  "common.previous": "Previous",
  "common.more": "More",
  "common.open": "Open",
  "common.download": "Download",
  "common.signIn": "Connect workspace",
  "common.signOut": "Sign out",
  "common.credentialMissing": "No credential",
  "common.credentialPresent": "Credential configured",

  "epic.title": "Chronicles",
  "epic.subtitle": "THE CHRONICLES OF SPECPROOF",
  "epic.lead":
    "A history of verification — every line AI writes is traced, proven with iron evidence, and judged. Each scroll in this page maps to a real record in this repository; wherever you turn, you will find the same event in the git history and the ledger.",
  "epic.scrolls": "Scroll",
  "epic.chronicleNote": "Verifiable",
  "epic.colophon":
    "Written by the chronicler (that is, by every commit in this repository): 2026-09 → today. The ledger lives in docs/operations/DEEP_OPTIMIZATION_PLAN.md, the roadmap in docs/operations/PRODUCT_ROADMAP.md; iron evidence is neither stronger for being plentiful nor weaker for being scarce.",
  "epic.readWorld": "Read the whole Book of Iron Evidence",
  "epic.readLexicon": "Open the Iron Lexicon",

  "tour.title": "Grand Tour",
  "tour.subtitle": "THE GRAND TOUR OF SPECPROOF",
  "tour.lead":
    "Six stations — connect · read · verify · trace · record · seal. Each one is a real verification, not the hundredth link in a guide. Finish a station and stamp it; six stamps make 「验讫」.",
  "tour.prologue":
    "The tour is not a checklist; it is the first night's journey. To have 'finished the tour' is not to have clicked every page, but to have pressed the seal yourself on every real verification. Five seals in, you are more like an acceptance officer than when you arrived; the sixth turns the word on the seal from 'visitor' to 'officer'.",
  "tour.chapter": "Station",
  "tour.task": "Act",
  "tour.tip": "Counsel",
  "tour.seal": "Seal this station",
  "tour.unseal": "Unseal (changed your mind)",
  "tour.progress": "sealed",
  "tour.sealedTitle": "Six seals, and the stamp falls.",
  "tour.sealedBody":
    "The chronicler of SpecProof has recorded this page — you are no longer a visitor, but someone who knows this, does this, and dares to sign.",
  "tour.hint": "An empty seal is the point — every page you seal, you seal for yourself.",
  "tour.reset": "Restart the tour (erase this browser's seals)",
  "tour.colophon":
    "Tour progress lives only in this browser's localStorage; a new browser, a new machine, a private window — the walk starts over. That is not a defect; it is SpecProof's temperament: your trust has to be picked up from zero.",
  "tour.corrupted": "This browser's tour progress cannot be read",
  "tour.corruptedBody":
    "The stored tour progress failed to parse — hand-edited, or the browser changed profile. That does not mean the walk never happened: this page presents a fresh start and isolates the old seals.",
  "tour.saveFailed": "The seal did not stick",
  "tour.saveFailedBody":
    "Local storage is disabled (private mode or policy). 'Done' here will not survive a reload — the interface tells you so rather than pretending it saved.",

  "explorer.title": "Case File",
  "explorer.subtitle": "THE CASE FILE",
  "explorer.lead":
    "A case file assembled from a stamping machine and a seal — every phrase comes from numbers the server returned; no literary consistency was handed to it by an LLM.",
  "explorer.sealPanel": "Seal",
  "explorer.loading": "Checking before binding…",
  "explorer.empty": "This browser holds no verification worth binding yet. Run one, then come back to read the file.",
  "explorer.repo": "Repository",
  "explorer.change": "Change",
  "explorer.opened": "Opened",
  "explorer.caseNo": "Case no.",
  "explorer.conditions": "Contracts",
  "explorer.passed": "Passed",
  "explorer.failed": "Failed",
  "explorer.unverified": "Unverified",
  "explorer.evidencePanel": "Evidence list",
  "explorer.noFindings":
    "This case carries no findings — that is not the same as 'no defects', only that this verification caught nothing. Missing iron evidence means missing evidence, not a victory lap.",
  "explorer.tally": "This case was judged 「{verdict}」. The AI did not decide; the evidence spoke.",
  "explorer.capsulePanel": "Evidence requested",
  "explorer.noCapsule": "This case handed over no reproduction capsule (it may be a DEMO run — read the whole trail)",
  "explorer.reportPath": "Report path",
  "explorer.status": "Execution trail",
  "explorer.tierIron": "Iron",
  "explorer.tierSemiIron": "Half-iron",
  "explorer.tierQuiet": "Quiet",
  "explorer.tierBroken": "Broken",
  "explorer.tierScript": "Scripted",
  "explorer.tierUnknown": "?",

  "usage.title": "Cache Health",
  "usage.subtitle": "CACHE HEALTH",
  "usage.lead":
    "A measured ledger of every LLM call — hit rate, streaming share, latency, per-kind breakdown. The hit rate counts only the calls the gateway actually reported; a missing number is never invented.",
  "usage.window": "Window",
  "usage.window.1h": "1 hour",
  "usage.window.24h": "24 hours",
  "usage.window.7d": "7 days",
  "usage.window.30d": "30 days",
  "usage.hitRate": "Cache hit rate",
  "usage.savedTokens": "Tokens saved by cache",
  "usage.totalTokens": "Total tokens",
  "usage.calls": "Calls",
  "usage.p50": "Latency P50",
  "usage.p95": "Latency P95",
  "usage.basis":
    "The hit rate counts only calls the gateway reported cached_tokens for ({basis} calls in this window); calls without a report still count as calls but not as hits; when the gateway reports nothing the rate shows as 「—」, never as a fabricated zero.",
  "usage.errorRate": "Error rate",
  "usage.streamRatio": "Streaming share",
  "usage.streamAria": "Streaming share",
  "usage.streamShare": "Streaming share",
  "usage.byKind": "Breakdown by kind",
  "usage.trend": "Hourly trend",
  "usage.trendEmpty": "No hourly bucket in this window — real calls will fill it.",
  "usage.callsOnly": "Calls",
  "usage.hitRateLegend": "Hit rate (null = gateway reported nothing → the line breaks; no fake point is drawn)",
  "usage.generatedAt": "Generated at",
  "usage.emptyTitle": "Cache Health",
  "usage.emptyText":
    "The ledger holds no records yet — after a batch of real LLM calls it will accumulate hit rate, streaming share and latency; an empty ledger invents nothing.",
  "usage.degraded":
    "The LLM usage ledger (read-only aggregate endpoint /api/v1/llm/usage/summary) is unavailable — this page fabricates no data; it recovers on its own when the endpoint returns.",
};

export const STRINGS: Record<Locale, Record<string, string>> = { zh, en };
