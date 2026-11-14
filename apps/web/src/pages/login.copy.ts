import type { Locale } from "../i18n/strings";

/** Copy for the login/connect screen, per locale. zh keeps the exact literals pinned by Login.test.tsx. */
export interface LoginCopy {
  brandSuffix: string;
  eyebrow: string;
  welcomeH1: [string, string];
  welcomeDescription: string;
  flowAria: string;
  flow: Array<{ step: string; title: string; text: string }>;
  exampleLabel: string;
  exampleTag: string;
  exampleText: string;
  exampleFindingStrong: string;
  exampleFindingSmall: string;
  guideLink: string;
  cardEyebrow: string;
  cardTitle: string;
  cardDescription: string;
  modesAria: string;
  modeToken: string;
  modeKey: string;
  labelToken: string;
  labelKey: string;
  placeholderToken: string;
  placeholderKey: string;
  reveal: string;
  hide: string;
  revealAriaShow: string;
  revealAriaHide: string;
  hintToken: string;
  hintKey: string;
  connect: string;
  connecting: string;
  oidcNote: string;
  oidcButton: string;
  configError: string;
  noCredential: string;
  noCredentialBody: string;
  localBody: string;
  localCommand: string;
  localBodyWindows: string;
  nonLocalBody: string;
  foot: string;
  error401: string;
  error403: string;
  error429: string;
  error5xxProvider: (detail: string) => string;
  error5xxAnswered: (status: number, detail: string) => string;
  errorNetwork: string;
  emptyCredentialKey: string;
  emptyCredentialToken: string;
}

const zh: LoginCopy = {
  brandSuffix: " SpecProof",
  eyebrow: "从需求到证据，每次交付都有依据",
  welcomeH1: ["代码改好了？", "需求，真的实现了吗？"],
  welcomeDescription:
    "SpecProof 帮团队验收代码变更：把你写下的需求与改动前后的代码放在一起检查，给出通过、阻断或待确认的结果，并保留可追溯的证据。",
  flowAria: "验证流程",
  flow: [
    { step: "01", title: "写清需求", text: "你希望代码做到什么" },
    { step: "02", title: "对比变更", text: "检查改动前后的行为" },
    { step: "03", title: "查看证据", text: "知道哪里通过、哪里有风险" },
  ],
  exampleLabel: "一个典型场景",
  exampleTag: "权限变更",
  exampleText: "需求：“只有管理员可以修改用户邮箱。”",
  exampleFindingStrong: "发现改动移除了权限检查",
  exampleFindingSmall: "查看失败条件、受影响代码和可重放证据，再决定是否合并。",
  guideLink: "第一次使用？先看使用指南 ",
  cardEyebrow: "你的工作区",
  cardTitle: "连接后，开始第一次验收",
  cardDescription: "使用管理员提供的凭据，访问团队的验证任务与交付证据。",
  modesAria: "连接方式",
  modeToken: "访问令牌",
  modeKey: "API Key",
  labelToken: "工作区访问令牌",
  labelKey: "工作区 API Key",
  placeholderToken: "粘贴 sp_ 开头的访问令牌",
  placeholderKey: "粘贴管理员提供的 API Key",
  reveal: "显示",
  hide: "隐藏",
  revealAriaShow: "显示凭据",
  revealAriaHide: "隐藏凭据",
  hintToken: "这里填写工作区管理员签发的访问令牌。凭据仅保存在当前浏览器会话中。",
  hintKey: "这里填写 SpecProof 工作区的登录密钥；模型服务商的 API Key 在进入工作区后单独配置。凭据仅保存在当前浏览器会话中。",
  connect: "连接工作区",
  connecting: "正在验证连接…",
  oidcNote: "或使用组织账号",
  oidcButton: "企业单点登录",
  configError: "暂时未获取到工作区配置。仍可尝试使用 API Key 连接；连接失败时请检查服务是否已启动。",
  noCredential: "还没有凭据，如何开始？",
  noCredentialBody: "团队用户：请向工作区管理员索取 API Key、访问令牌或单点登录入口。",
  localBody: "本机体验：在项目根目录运行下方命令，等待服务启动后，使用终端输出的登录密钥。",
  localCommand: "pwsh scripts/start_local.ps1",
  localBodyWindows: "初次运行需要 Python 3.12、Node.js 18+ 和 Docker Desktop。",
  nonLocalBody: "自己部署：按项目的本地体验指南启动服务，在后端配置工作区凭据。",
  foot: "先看证据，再做交付决策",
  error401: "凭据未通过验证。请检查是否复制完整，或向工作区管理员获取新的凭据。",
  error403: "当前凭据没有工作区访问权限，请联系管理员。",
  error429: "连接请求过于频繁，请稍后重试。",
  error5xxProvider: (detail: string) => `后端已响应，但工作区登录未在服务端开启。服务端说明：${detail}`,
  error5xxAnswered: (status: number, detail: string) =>
    `后端已响应，但没能完成这次请求（HTTP ${status}）。服务端说明：${detail}`,
  errorNetwork: "无法连接到服务。请确认本地启动脚本已完成，或联系工作区管理员检查服务地址。",
  emptyCredentialKey: "请先输入工作区 API Key。",
  emptyCredentialToken: "请先输入管理员提供的访问令牌。",
};

const en: LoginCopy = {
  brandSuffix: " SpecProof",
  eyebrow: "From requirement to evidence — every delivery has its proof",
  welcomeH1: ["The code is ready.", "But is the requirement really implemented?"],
  welcomeDescription:
    "SpecProof verifies code changes for teams: it puts what you wrote down next to the code before and after, and hands back pass / blocked / review with traceable evidence.",
  flowAria: "The verification flow",
  flow: [
    { step: "01", title: "Write the requirement", text: "Say what the code must do" },
    { step: "02", title: "Compare the change", text: "Check behavior before and after" },
    { step: "03", title: "Read the evidence", text: "Know what passed and what is risky" },
  ],
  exampleLabel: "A typical scenario",
  exampleTag: "Authorization change",
  exampleText: "Requirement: “Only admins may edit a user's email.”",
  exampleFindingStrong: "The change removed the permission check",
  exampleFindingSmall: "Look at the failing condition, the affected code and the replayable evidence — then decide whether to merge.",
  guideLink: "First time here? Start with the guide ",
  cardEyebrow: "Your workspace",
  cardTitle: "Connect, and run your first verification",
  cardDescription: "Use the credential your administrator gave you; reach the team's verification tasks and delivery evidence.",
  modesAria: "Connection mode",
  modeToken: "Access token",
  modeKey: "API Key",
  labelToken: "Workspace access token",
  labelKey: "Workspace API Key",
  placeholderToken: "Paste the access token starting with sp_",
  placeholderKey: "Paste the API Key from your administrator",
  reveal: "Show",
  hide: "Hide",
  revealAriaShow: "Show credential",
  revealAriaHide: "Hide credential",
  hintToken: "The access token your administrator issued for the workspace. Credentials are kept in this browser session only.",
  hintKey: "The login key for the SpecProof workspace; model-provider API Keys are configured separately after you are inside. Credentials are kept in this browser session only.",
  connect: "Connect workspace",
  connecting: "Verifying the connection…",
  oidcNote: "Or use your organization's single sign-on",
  oidcButton: "Enterprise SSO",
  configError: "Could not load the workspace configuration. You can still try an API Key; if that fails too, check that the service is running.",
  noCredential: "No credential yet? Here's how to start",
  noCredentialBody: "Team members: ask your workspace administrator for an API Key, an access token, or the SSO entry point.",
  localBody: "Local experience: run the command below in the project root, wait for the service to come up, then use the login key the terminal prints.",
  localCommand: "pwsh scripts/start_local.ps1",
  localBodyWindows: "First run needs Python 3.12, Node.js 18+ and Docker Desktop.",
  nonLocalBody: "Self-hosting: follow the local-experience guide to start the service, then configure workspace credentials in the backend.",
  foot: "Look at the evidence first, then make the delivery call",
  error401: "This credential did not pass verification. Check whether it was copied completely, or ask your administrator to issue a new one.",
  error403: "This credential does not have workspace access; contact your administrator.",
  error429: "Too many connection attempts; try again shortly.",
  error5xxProvider: (detail: string) => `The backend answered, but workspace login is not enabled server-side. Server message: ${detail}`,
  error5xxAnswered: (status: number, detail: string) =>
    `The backend answered, but could not complete this request (HTTP ${status}). Server message: ${detail}`,
  errorNetwork: "Could not reach the service. Confirm the local start script finished, or ask your administrator about the service address.",
  emptyCredentialKey: "Enter your workspace API Key first.",
  emptyCredentialToken: "Enter the access token your administrator provided.",
};

export const LOGIN_BY_LOCALE: Record<Locale, LoginCopy> = { zh, en };
