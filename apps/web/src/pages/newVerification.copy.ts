import type { Locale } from "../i18n/strings";

/** Copy for the New Verification page, per locale. zh keeps the exact literals pinned by NewVerification.test.tsx. */
export interface NewVerificationCopy {
  breadcrumbJobs: string;
  breadcrumbNew: string;
  eyebrow: string;
  title: string;
  description: string;
  demoFormAria: string;
  demoBannerBody: string;
  demoBannerButton: string;
  section01Title: string;
  section01Body: string;
  repoLabel: string;
  repoPlaceholder: string;
  repoHint: string;
  repoRequired: string;
  specLabel: string;
  specPlaceholder: string;
  specHint: string;
  specRequired: string;
  section02Title: string;
  section02Body: string;
  baseLabel: string;
  basePlaceholder: string;
  baseHint: string;
  baseRequired: string;
  headLabel: string;
  headPlaceholder: string;
  headHint: string;
  headRequired: string;
  headSameAsBase: string;
  demoFill: string;
  demoFillNote: string;
  submit: string;
  submitting: string;
  submitNote: string;
  benefitsTitle: string;
  benefitContractsStrong: string;
  benefitContractsBefore: string;
  benefitContractsTerm: string;
  benefitContractsAfter: string;
  benefitFindingsStrong: string;
  benefitFindingsBefore: string;
  benefitFindingsTerm: string;
  benefitFindingsAfter: string;
  benefitJudgesStrong: string;
  benefitJudgesBody: string;
  exampleTitle: string;
  exampleBodyBefore: string;
  exampleBodyCode: string;
  exampleBodyAfter: string;
  exampleTail: string;
  prefillTitle: string;
  prefillBodyBefore: string;
  prefillStrong: string;
  prefillBodyAfter: string;
  prefillBodyCode: string;
  prefillBodyTail: string;
  prefillFill: string;
  prefillPrepared: string;
  preparing: string;
  prepareDemo: string;
  needApiKey: string;
  prepareFailed: string;
  noJobId: string;
  createdOk: (refs: string) => string;
  alreadyPresent: string;
  error503: string;
  errorNetwork: string;
  errorFallback: string;
  openGuide: string;
  note: string;
}

const zh: NewVerificationCopy = {
  breadcrumbJobs: "验证记录",
  breadcrumbNew: "新建验证",
  eyebrow: "START A VERIFICATION",
  title: "让这次改动接受审判",
  description: "选择待检的两个版本、提供需求文件——SpecProof 会把变更与证据摆到一起，每条契约都会被执行与验证。",
  demoFormAria: "新建验证",
  demoBannerBody: "第一次使用？填一个能跑通的演示——权限不需折腾开发环境，提交证明就能让你见到真实的结论。",
  demoBannerButton: "填入演示参数",
  section01Title: "选择项目",
  section01Body: "仓库必须位于执行服务可访问的目录中。",
  repoLabel: "Git 仓库路径",
  repoPlaceholder: "例如 /workspace/my-service",
  repoHint: "仓库需已存在。执行服务会在变更对比时检出两个版本。",
  repoRequired: "请填写执行服务可访问的 Git 仓库路径。",
  specLabel: "需求文件路径",
  specPlaceholder: "例如 /workspace/my-service/spec.md",
  specHint: "用自然语言描述这次改动的人类阅读方式；需求是基本事实，不是假设。",
  specRequired: "请填写描述预期行为的需求文件路径。",
  section02Title: "确认对比范围",
  section02Body: "基准版本与待检版本，不要指向同一提交。",
  baseLabel: "基准版本",
  basePlaceholder: "main",
  baseHint: "通常为 main，也可使用提交 SHA。",
  baseRequired: "请填写用于比较的基准分支或提交。",
  headLabel: "待检版本",
  headPlaceholder: "HEAD",
  headHint: "通常为 HEAD，也可为分支名。",
  headRequired: "请填写待检查的分支或提交。",
  headSameAsBase: "请选择与基准不同的版本，否则无法比较差异。",
  demoFill: "填入演示参数",
  demoFillNote: "使用当前默认的演示配置",
  submit: "开始验证 →",
  submitting: "正在创建验证",
  submitNote: "使用当前默认的演示配置",
  benefitsTitle: "这是你将得到的",
  benefitContractsStrong: "需求逐条对应",
  benefitContractsBefore: "看到每条",
  benefitContractsTerm: "验收条件",
  benefitContractsAfter: "的检查结果，以及尚未覆盖的部分。",
  benefitFindingsStrong: "问题有据可查",
  benefitFindingsBefore: "查看",
  benefitFindingsTerm: "风险发现",
  benefitFindingsAfter: "、影响位置与可用的复现证据。",
  benefitJudgesStrong: "评审更有依据",
  benefitJudgesBody: "用验证报告支持代码评审；证据不足会明确标注。",
  exampleTitle: "需求可以这样写",
  exampleBodyBefore: "未登录用户调用",
  exampleBodyCode: "POST /orders",
  exampleBodyAfter: "时应返回 401，且不得创建订单。",
  exampleTail: "明确条件、预期结果和禁止行为，比“优化订单功能”更容易验证。",
  prefillTitle: "想立刻看到效果？",
  prefillBodyBefore: "项目自带一个演示仓库：改动前的版本权限检查完整，改动后的版本移除了邮箱修改接口的权限检查。提交验证后，预期结论为 ",
  prefillStrong: "发现风险",
  prefillBodyAfter: "（",
  prefillBodyCode: "BLOCKED",
  prefillBodyTail: "）——你会看到具体风险、代码位置和证据。",
  prefillFill: "填入演示案例",
  prefillPrepared: "演示案例已填入，可直接点击开始验证。",
  preparing: "正在准备演示仓库…",
  prepareDemo: "一键创建演示仓库",
  needApiKey: "需要先配置 API 密钥（见「模型连接 / 设置」）才能创建演示仓库。",
  prepareFailed: "演示仓库创建失败，请稍后重试。",
  noJobId: "任务未返回 ID——刷新验证记录列表，确认是否已创建成功。",
  createdOk: (refs) => `已创建演示仓库（${refs}），演示案例已填入左侧表单。`,
  alreadyPresent: "演示仓库已存在，演示案例已填入左侧表单。",
  error503: "验证服务暂时不可用：网页版需要 MySQL / Redis 等后端服务。若你在使用免 Docker 的轻量模式，请改用命令行 `specproof verify`，或先启动这些服务后重试。",
  errorNetwork: "无法连接到验证服务，任务未提交。请确认后端已启动、地址填写正确（见「模型连接 / 设置」中的 API 地址），然后重试。",
  errorFallback: "任务创建失败，请检查服务连接后重试。",
  openGuide: "查看新手使用指南 →",
  note: "目前验证支持 Java / Spring Boot 项目；非 Spring 项目也不会被误判。提交前执行服务会先检出对比范围，再进入模型侧。",
};

const en: NewVerificationCopy = {
  breadcrumbJobs: "Verifications",
  breadcrumbNew: "New verification",
  eyebrow: "START A VERIFICATION",
  title: "Put this change on trial",
  description: "Pick the two refs, provide the requirement file — SpecProof puts the change and the evidence side by side, executing and checking every contract.",
  demoFormAria: "New verification",
  demoBannerBody: "First time? Fill in a runnable demo — no environment to prepare, the moment you submit you see a real verdict.",
  demoBannerButton: "Fill demo values",
  section01Title: "Pick the project",
  section01Body: "The repo must live in a directory reachable by the execution service.",
  repoLabel: "Git repository path",
  repoPlaceholder: "e.g. /workspace/my-service",
  repoHint: "The repo must exist. The execution service checks out both refs.",
  repoRequired: "Provide a Git repository path accessible to the execution service.",
  specLabel: "Requirement file path",
  specPlaceholder: "e.g. /workspace/my-service/spec.md",
  specHint: "Describe the change in plain language; the requirement is the fact, not an assumption.",
  specRequired: "Provide the path of the requirement file describing the expected behavior.",
  section02Title: "Confirm the comparison scope",
  section02Body: "The baseline and the candidate must not point at the same commit.",
  baseLabel: "Baseline ref",
  basePlaceholder: "main",
  baseHint: "Usually main, or a commit SHA.",
  baseRequired: "Provide the baseline branch or commit used for comparison.",
  headLabel: "Candidate ref",
  headPlaceholder: "HEAD",
  headHint: "Usually HEAD, or a branch name.",
  headRequired: "Provide the branch or commit to verify.",
  headSameAsBase: "Pick a different ref from the baseline, or there is nothing to compare.",
  demoFill: "Fill demo values",
  demoFillNote: "Uses the current built-in demo configuration",
  submit: "Start verification →",
  submitting: "Creating the verification",
  submitNote: "Uses the current built-in demo configuration",
  benefitsTitle: "What you get",
  benefitContractsStrong: "Requirements, one by one",
  benefitContractsBefore: "See every",
  benefitContractsTerm: "acceptance condition",
  benefitContractsAfter: "'s check result — and what remains uncovered.",
  benefitFindingsStrong: "Findings with receipts",
  benefitFindingsBefore: "See",
  benefitFindingsTerm: "risk findings",
  benefitFindingsAfter: ", where they land, and the reproduction evidence to hand.",
  benefitJudgesStrong: "Sharper reviews",
  benefitJudgesBody: "Back your code review with the verification report; thin evidence is marked as such.",
  exampleTitle: "How a requirement reads",
  exampleBodyBefore: "When an anonymous user calls",
  exampleBodyCode: "POST /orders",
  exampleBodyAfter: ", it must return 401 and create no order.",
  exampleTail: "Explicit conditions, expected results, forbidden behavior — far easier to verify than “optimize the order feature”.",
  prefillTitle: "Want to see this instantly?",
  prefillBodyBefore: "This project ships a demo repo: the base ref has full permission checks and the head removed the permission check from the email-edit endpoint. After you submit, the expected verdict is ",
  prefillStrong: "risk found",
  prefillBodyAfter: " (",
  prefillBodyCode: "BLOCKED",
  prefillBodyTail: ") — you will see the concrete risk, the code location, and the evidence.",
  prefillFill: "Fill demo values",
  prefillPrepared: "Demo case filled — you can start the verification now.",
  preparing: "Preparing the demo repo…",
  prepareDemo: "Create demo repo in one click",
  needApiKey: "You need to configure an API key first (see Model Connection / Settings) to create the demo repo.",
  prepareFailed: "Creating the demo repo failed; try again later.",
  noJobId: "The job id was not returned — refresh the verification list and check whether it was created.",
  createdOk: (refs) => `Demo repo created (${refs}); the demo case has been filled into the form on the left.`,
  alreadyPresent: "Demo repo already exists; the demo case has been filled into the form on the left.",
  error503: "Verification service is temporarily unavailable: the web app needs backend services (MySQL / Redis). If you are in Docker-less light mode, use `specproof verify` from the CLI, or start those services and retry.",
  errorNetwork: "Could not reach the verification service; nothing was submitted. Confirm the backend is running and the address is correct (see Model Connection / Settings), then retry.",
  errorFallback: "Failed to create the verification; check the service connection and retry.",
  openGuide: "Open the onboarding guide →",
  note: "For now, verification targets Java / Spring Boot repos; non-Spring repos will not be misjudged either. Before submitting, the execution service checks out the compared refs — then the model only sees evidence.",
};

export const NEW_VERIFICATION_BY_LOCALE: Record<Locale, NewVerificationCopy> = { zh, en };
