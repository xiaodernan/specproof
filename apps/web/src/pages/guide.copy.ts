import type { Locale } from "../i18n/strings";

/** Copy for the Onboarding Guide page, per locale. zh keeps the exact literals pinned by Guide.test.tsx. */
export interface GuideCopy {
  eyebrow: string;
  title: string;
  intro: string;
  actionNew: string;
  actionDashboard: string;
  degradedStrong: string;
  degradedBody: string;
  choiceAria: string;
  choice1Kicker: string;
  choice1Title: string;
  choice1Body: string;
  choice1Link: string;
  choice2Kicker: string;
  choice2Title: string;
  choice2Body: string;
  choice2Link: string;
  choice3Kicker: string;
  choice3Title: string;
  choice3Body: string;
  choice3Link: string;
  startKicker: string;
  startTitle: string;
  startBody: string;
  checklistTitle: (done: number, total: number) => string;
  checklistBasis: string;
  unknownBadge: (n: number) => string;
  unreadableNote: string;
  unreadableNoteBody: string;
  saveFailedNote: string;
  manualCheckbox: string;
  stateDone: string;
  stateTodo: string;
  stateUnknown: string;
  stepkindManual: string;
  stepkindAuto: string;
  stepTitles: Record<string, string>;
  stepBasis: Record<string, string>;
  stepDetail: Record<string, string>;
  connectBodyBefore: string;
  connectBodyLink: string;
  connectBodyAfter: string;
  connectPending: string;
  connectAbsent: string;
  connectFailed: string;
  countDone: (n: number) => string;
  countAbsent: string;
  countPending: string;
  countNoTotal: string;
  countFailed: string;
  exampleKicker: string;
  exampleTitle: string;
  exampleBody: string;
  expectedKicker: string;
  expectedTitle: string;
  expectedBodyBefore: string;
  expectedBodyAfter: string;
  demoHeadline: string;
  demoBody: string;
  demoCta: string;
  demoNote: string;
  verifyNow: string;
  demoCommands: string;
  resultsKicker: string;
  resultsTitle: string;
  resultsBody: string;
  verdictVerified: string;
  verdictVerifiedBody: string;
  verdictBlocked: string;
  verdictBlockedBody: string;
  verdictFailed: string;
  verdictFailedBody: string;
  verdictUnverified: string;
  verdictUnverifiedBody: string;
  glossaryTitle: string;
  shortcutsTitle: string;
  shortcutsBodyBefore: string;
  shortcutsBodyMid: string;
  shortcutsBodyEnd: string;
  kbPalette: string;
  kbEscape: string;
  kbCtrlK: string;
  localKicker: string;
  localTitle: string;
  localBody: string;
  copyCommand: string;
  copiedOk: string;
  copyFailed: string;
  preflightLine: string;
  glossaries: Record<string, { label: string; definition: string }>;
}

const zh: GuideCopy = {
  eyebrow: "认识 SpecProof",
  title: "从需求到证据，立验代码。",
  intro: "Spec 是需求，Proof 是验证需求的证据。SpecProof 把它们照在同一束光里。",
  actionNew: "新建验证",
  actionDashboard: "先回到工作台",
  degradedStrong: "你的代码改变后。",
  degradedBody: "AI 能按指令定位。但系统仍然需要一个入口的 Java / Spring 版本——否则只能看到代码差异，看不到契约是否成立。",
  choiceAria: "选择使用方式",
  choice1Kicker: "你已经在写代码",
  choice1Title: "让变更接受验收",
  choice1Body: "提供仓库、基线、需求文件，让变更经受验收。",
  choice1Link: "开始验证",
  choice2Kicker: "需求还要给 AI 实现",
  choice2Title: "让 AI 替你改完",
  choice2Body: "在沙箱里踢一踢，看代码自己动起来。",
  choice2Link: "开启自动交付",
  choice3Kicker: "想先大概看看",
  choice3Title: "先看验收规则",
  choice3Body: "看验收报告的样子：覆盖率、发现与判决。",
  choice3Link: "查看验收记录",
  startKicker: "01",
  startTitle: "第一次使用，需要就位什么",
  startBody: "从这里开始准备演示环境，让系统先正确执行一次验收。",
  checklistTitle: (done, total) => `${done} / ${total}`,
  checklistBasis: "系统能确认的",
  unknownBadge: (n) => `其中 ${n} 项无法检测`,
  unreadableNote: "本机进度记录读不出来",
  unreadableNoteBody: "这不代表你从未开始；你之前点过的步骤会一直显示为“无法确认”，系统不会把你当成新用户。",
  saveFailedNote: "手动操作的结果无法写入本地存储——刷新页面后会丢失。",
  manualCheckbox: "我已完成",
  stateDone: "已完成",
  stateTodo: "未完成",
  stateUnknown: "无法确认",
  stepkindManual: "手动勾选",
  stepkindAuto: "系统检测",
  stepTitles: {
    connect: "连接工作区",
    prepare_spec: "准备一份可验证的需求",
    create_verification: "创建验证，选好对比范围",
    read_results: "打开结果页，看懂铁证",
  },
  stepBasis: {
    connect: "本页是否成功登录，从第一就是否有凭据看",
    prepare_spec: "系统不可能自己知道一份需求写得对不对，只能由你自己确认",
    create_verification: "从这个工作区已有的验证次数判断",
    read_results: "看记录里是否出现了打开结论页的入口",
  },
  stepDetail: {
    prepare_spec: "选一个可以真实验证的需求——别纠结格式，越具体越好：给出明确的条件、期望结果和禁止行为。",
    create_verification: "指定 Git 仓库路径、对比范围（基准 Base → 检查 Head）、需求文件路径；提交后可以直接查看运行进度和结论。",
    read_results: "打开结论页，找到“判决”“风险发现”“证据”的位置——失败时看证据与代码位置，修好再提交一次。",
  },
  connectBodyBefore: "可以本地连接：API Key 或 OIDC 令牌都可以。模型服务商的 API Key 在进入之后单独配置。请去",
  connectBodyLink: "模型连接",
  connectBodyAfter: "页签生成自己的密钥。",

  connectAbsent: "本浏览器缺少凭据——未登录也无法自动检测。这不等于连接失败。",
  connectPending: "正在检测工作区连接…",
  connectFailed: "连接请求失败——无法判断是否成功连接。这不等于没有连接。",
  countDone: (n) => `工作区里已有 ${n} 次验证`,
  countAbsent: "这个浏览器里还没有工作区凭据，无法确认是否已经建过验证。",
  countPending: "正在读取工作区的验证列表…",
  countNoTotal: "工作区回复成功，但没有给出验证总次数，无法确认是否已经建过验证。",
  countFailed: "读不到验证任务列表，无法确认是否已经建过验证。",
  exampleKicker: "02",
  exampleTitle: "一个权限变更的完整故事",
  exampleBody: "仓库来自 Spring 演示项目，用这次改动教你提交验证。",
  expectedKicker: "你会在屏幕上看到",
  expectedTitle: "权限被任意撤销的沉默——正是问题的样子",
  expectedBodyBefore: "需求只是一句话，但演示的",
  expectedBodyAfter: "版本删掉了邮箱接口的权限检查——验证预期看到",
  demoHeadline: "或者让 AI 直接动手",
  demoBody: "也可以让 AI 接手任务：已知的演示任务里，它会按验收规则自我修复。",
  demoCta: "用演示任务开始 AI 交付 →",
  demoNote: "约需 2 分钟，完成后可如实回答你的问题。",
  verifyNow: "跑一遍真实验收 →",
  demoCommands: "初次运行需要先执行",
  resultsKicker: "03",
  resultsTitle: "这些结果分别是什么意思？",
  resultsBody: "执行验证会给出不同的结果，绝不只用红绿灯糊弄你。",
  verdictVerified: "验收通过",
  verdictVerifiedBody: "当前对比范围内的需求全都满足。残留风险在覆盖范围之外，请结合代码审查。",
  verdictBlocked: "发现问题",
  verdictBlockedBody: "发现了确定被破坏的证据——不要在看到证据后继续相信，修好再验证。",
  verdictFailed: "执行失败",
  verdictFailedBody: "验证执行本身出了问题，未能得出结论。需要排障后再判。",
  verdictUnverified: "证据不足",
  verdictUnverifiedBody: "某些需求没有足够证据。设计上不给你一个虚假的绿灯。",
  glossaryTitle: "术语表，你也能自己查",
  shortcutsTitle: "键盘的咬合",
  shortcutsBodyBefore: "按",
  shortcutsBodyMid: "打开键盘帮助",
  shortcutsBodyEnd: "唤起命令面板；页面没法切换时，按",
  kbPalette: "Ctrl K",
  kbEscape: "Esc",
  kbCtrlK: "Ctrl K",
  localKicker: "本地运行",
  localTitle: "自己装到本机就行",
  localBody: "需预先安装 Python 3.12、Node.js 18+、Docker Desktop；在项目根目录安装 Python 依赖：",
  copyCommand: "复制启动指令",
  copiedOk: "已复制到剪贴板",
  copyFailed: "请选中后手工复制",
  preflightLine: "初次运行需",
  glossaries: {
    matrix: { label: "需求矩阵", definition: "逐条列出“要求是什么、如何检查、结果如何、证据在哪里”的验收清单。导航里的「需求覆盖」就是它。" },
    contract: { label: "契约", definition: "从需求整理出来的具体检查规则。你可以在验收规则页面查看审批状态和版本。" },
    finding: { label: "风险发现", definition: "一次检查发现的具体问题，包括影响、严重程度、代码位置与证据。" },
    feedback: { label: "验收反馈", definition: "人对某条风险判定给出的接受或打回意见。同一人对同一条风险只计一票；没有反馈不等于已接受。" },
    capsule: { label: "证据包（Bug Capsule）", definition: "供下载、排查或重放问题的材料。以任务实际生成的文件为准。" },
    certificate: { label: "合并证书", definition: "关联验证结果的签名记录，用于交付追溯。它只覆盖本次已验证的范围。" },
    craft: { label: "开发助手（SpecCraft）", definition: "帮助规划和实现代码的 Agent。开发完成后，仍需要独立验证来支持交付判断。" },
    preflight: { label: "环境预检", definition: "在跑构建之前先确认工具链（JDK / Node / Python 等）是否就绪，避免几分钟后才吐出看不懂的构建错误。" },
    evidence: { label: "证据", definition: "支撑某条结论的可复核材料，例如测试输出、改动前后的行为差异、接口响应。只有结论没有证据时，状态会显示为「证据不足」。" },
  },
};

const en: GuideCopy = {
  eyebrow: "Meet SpecProof",
  title: "From requirement to evidence, prove code now.",
  intro: "Spec is the requirement; Proof is the evidence the requirement is actually satisfied. SpecProof lays them in the same light.",
  actionNew: "New verification",
  actionDashboard: "Back to Dashboard",
  degradedStrong: "Your code changed.",
  degradedBody: "AI can follow instructions, but the system still needs Java / Spring at the boundary — otherwise it only sees code diffs, never whether a contract holds.",
  choiceAria: "Choose how to step in",
  choice1Kicker: "You are already writing code",
  choice1Title: "Put the change on trial",
  choice1Body: "Bring a repo, a baseline, a requirement file — let the change face the iron.",
  choice1Link: "Start a verification",
  choice2Kicker: "The requirement still needs an author",
  choice2Title: "Let the AI write and self-repair",
  choice2Body: "Kick it around in the sandbox and watch the code come alive.",
  choice2Link: "Start autonomous delivery",
  choice3Kicker: "Want a quick look first",
  choice3Title: "Read the acceptance rules",
  choice3Body: "See what a verification report looks like: coverage, findings, verdict.",
  choice3Link: "View the verification record",
  startKicker: "01",
  startTitle: "What has to be in place on day one",
  startBody: "Start by preparing the demo environment — the system then runs one verification end to end.",
  checklistTitle: (done, total) => `${done} / ${total}`,
  checklistBasis: "system-confirmable",
  unknownBadge: (n) => `${n} cannot be detected`,
  unreadableNote: "This browser's progress record cannot be read",
  unreadableNoteBody: "Local storage failed — every tick you previously pressed renders as “checking”; the system will not mistake you for a brand-new user.",
  saveFailedNote: "Your manual check could not be written to local storage — it is lost on refresh.",
  manualCheckbox: "I did this",
  stateDone: "Done",
  stateTodo: "Not done",
  stateUnknown: "Cannot confirm",
  stepkindManual: "manual tick",
  stepkindAuto: "system detected",
  stepTitles: {
    connect: "Connect the workspace",
    prepare_spec: "Prepare a verifiable requirement",
    create_verification: "Create a verification, pick the compare range",
    read_results: "Open the verdict — know the iron",
  },
  stepBasis: {
    connect: "Whether this page succeeded in signing in, read from the first request's credential state",
    prepare_spec: "The system cannot judge whether a requirement document is any good — only you can",
    create_verification: "Decided from this workspace's existing verifications",
    read_results: "Whether the record shows you opened a verdict page",
  },
  stepDetail: {
    prepare_spec: "Pick a requirement you can actually verify — don't fuss over the format; the more concrete, the better: explicit conditions, expected results, forbidden behavior.",
    create_verification: "Name the Git repository path, the compare range (base → head), and the requirement file; submit, then watch the run and its verdict unfold live.",
    read_results: "Open the verdict page — find where the verdict, the findings and the evidence live. When it fails, read the evidence and the code location, fix, re-submit.",
  },
  connectBodyBefore: "Connect locally: an API Key or an OIDC token both work. Model-provider API keys are configured separately once you are inside. Head to",
  connectBodyLink: "Model connection",
  connectBodyAfter: "to mint your own key.",

  connectAbsent: "This browser holds no workspace credential; without logging in, nothing can be auto-detected.",
  connectPending: "Detecting workspace connection…",
  connectFailed: "The connection request failed — it cannot tell whether it succeeded. That is not the same as not connected.",
  countDone: (n) => `This workspace already has ${n} verification(s)`,
  countAbsent: "This browser holds no workspace credential, so it cannot tell whether a verification was ever created.",
  countPending: "Reading the workspace's verification list…",
  countNoTotal: "The workspace answered but gave no total count, so it cannot tell whether a verification was created.",
  countFailed: "Cannot read the verification list; cannot tell whether a verification was created.",
  exampleKicker: "02",
  exampleTitle: "A complete story about an authorization change",
  exampleBody: "The repo comes from the Spring demo — this change is how you learn to submit verifications.",
  expectedKicker: "What you will see on screen",
  expectedTitle: "The silence of an authorization removed — that is what the problem looks like",
  expectedBodyBefore: "The requirement is one sentence, but the demo's",
  expectedBodyAfter: "version removed the permission check on the email endpoint — expect a",
  demoHeadline: "Or let the AI just do it",
  demoBody: "Hand the task to the AI: the demo it is given is known — it will self-repair against the acceptance rules.",
  demoCta: "Start AI delivery with the demo task →",
  demoNote: "Takes about 2 minutes; it will answer your questions honestly.",
  verifyNow: "Run a real verification →",
  demoCommands: "First time? Run",
  resultsKicker: "03",
  resultsTitle: "What these results actually mean",
  resultsBody: "A verification lands on one of these — never a bare red-green traffic light.",
  verdictVerified: "Verified",
  verdictVerifiedBody: "Every requirement in the compared range held. Residual risk lives beyond the range — pair with code review.",
  verdictBlocked: "Blocked",
  verdictBlockedBody: "Evidence shows a real regression — do not keep believing after seeing it; fix and re-verify.",
  verdictFailed: "Failed",
  verdictFailedBody: "The verification run itself broke; no verdict was produced. Diagnose and re-run.",
  verdictUnverified: "Evidence missing",
  verdictUnverifiedBody: "Some requirements lack evidence — by design you are never handed a fake green.",
  glossaryTitle: "Glossary — look it up yourself",
  shortcutsTitle: "The keyboard bites",
  shortcutsBodyBefore: "Press",
  shortcutsBodyMid: "for the keyboard help",
  shortcutsBodyEnd: "to open the command palette; when a page cannot reach, press",
  kbPalette: "Ctrl K",
  kbEscape: "Esc",
  kbCtrlK: "Ctrl K",
  localKicker: "Local",
  localTitle: "Install it locally",
  localBody: "You need Python 3.12, Node.js 18+, Docker Desktop; install the Python deps in the repo root:",
  copyCommand: "Copy start command",
  copiedOk: "Copied to clipboard",
  copyFailed: "Select and copy it manually",
  preflightLine: "First run needs",
  glossaries: {
    matrix: { label: "Requirement Matrix", definition: "The acceptance ledger listing requirement, check, result and evidence row by row. “Requirement Coverage” in the sidebar is exactly this." },
    contract: { label: "Contract", definition: "A concrete check rule distilled from the requirement. See its approval state and version in the contracts page." },
    finding: { label: "Finding", definition: "One concrete problem discovered by a check — impact, severity, code location and evidence." },
    feedback: { label: "Finding Feedback", definition: "A human accepts or rejects a finding. One person, one vote per finding; silence is not acceptance." },
    capsule: { label: "Bug Capsule", definition: "The artifact for reproducing, filing or replaying the issue. Whatever the job actually produced governs." },
    certificate: { label: "Merge Certificate", definition: "A signed record linking the verdict, used for delivery traceability. It only covers what was verified in this run." },
    craft: { label: "SpecCraft", definition: "The agent that plans and implements code. Even after it finishes, an independent verification is still required before shipping." },
    preflight: { label: "Preflight", definition: "Before the build runs, confirm the toolchain (JDK / Node / Python) is present — no cryptic mid-build failures minutes later." },
    evidence: { label: "Evidence", definition: "Reviewable material backing a verdict — test output, before/after behavior, API responses. A verdict without evidence renders as “Evidence missing”, never green." },
  },
};

export const GUIDE_BY_LOCALE: Record<Locale, GuideCopy> = { zh, en };
