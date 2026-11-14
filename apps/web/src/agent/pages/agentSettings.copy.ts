import type { Locale } from "../../i18n/strings";

/** Copy for the Agent Settings (model connection) page, per locale. zh keeps the exact literals pinned by AgentSettings.test.tsx. */
export interface AgentSettingsCopy {
  eyebrow: string;
  title: string;
  intro: string;
  credentialStrong: string;
  credentialBody: string;
  forbiddenTitle: string;
  forbiddenBody: string;
  forbiddenLink: string;
  loadFailedTitle: string;
  retry: string;
  configTitle: string;
  managedText: string;
  urlLabel: string;
  urlPlaceholder: string;
  urlHint: string;
  modelLabel: string;
  modelPlaceholder: string;
  modelHint: string;
  apiKeyLabel: string;
  apiKeyPlaceholderConfigured: string;
  apiKeyPlaceholderMissing: string;
  apiKeyHintConfigured: string;
  apiKeyHintMissing: string;
  protocolLabel: string;
  protocolResponses: string;
  protocolChat: string;
  protocolHint: string;
  reasoningLabel: string;
  reasoningDefault: string;
  reasoningLow: string;
  reasoningMedium: string;
  reasoningHigh: string;
  reasoningXhigh: string;
  reasoningMax: string;
  reasoningHint: string;
  save: string;
  testing: string;
  test: string;
  saveAnywaySave: string;
  saveError: string;
  saved: string;
  dirtyStatus: string;
  passStatus: string;
  failStatus: string;
  configuredStatus: string;
  missingStatus: string;
  dirtyHint: string;
  testHint: string;
  helpKicker: string;
  helpTitle: string;
  helpIntro: string;
  helpStep1: string;
  helpStep2: string;
  helpStep3: string;
  helpLink: string;
  missingKey: string;
  notConfigured: string;
  resultPassTitle: string;
  resultFailTitle: string;
  resultMeta: (model: string, protocol: string, seconds: number) => string;
  resultSuccessCta: string;
  resultFailHint: string;
}

const zh: AgentSettingsCopy = {
  eyebrow: "AI CONNECTION",
  title: "模型连接",
  intro: "连接你的 AI 模型服务为该工作区的默认模型；这是第一次真实连接，耐心等它答复。",
  credentialStrong: "模型服务商的 API Key",
  credentialBody:
    "连接凭据只保存在本机和你的 SpecProof 工作区；这个 Key 从只用于真实模型调用，不会上传到别处。",
  forbiddenTitle: "由部署管理员管理",
  forbiddenBody:
    "模型连接是整个部署共享的配置。请联系部署管理员设置模型服务；团队访问令牌不能修改共享模型配置。",
  forbiddenLink: "返回 AI 开发 →",
  loadFailedTitle: "暂时无法加载模型配置",
  retry: "重试",
  configTitle: "模型服务配置",
  managedText: "当前配置由部署环境变量管理。如需修改，请联系部署管理员更新配置并重启服务。",
  urlLabel: "模型服务地址",
  urlPlaceholder: "https://your-model-service.example/v1",
  urlHint: "使用服务商提供的接口地址。系统会统一处理 /v1 或完整接口路径。",
  modelLabel: "模型名称",
  modelPlaceholder: "填写服务商实际支持的模型 ID",
  modelHint: "模型名称需要与服务商提供的 ID 完全一致。",
  apiKeyLabel: "模型 API Key",
  apiKeyPlaceholderConfigured: "已配置；重新配置时会直接覆盖",
  apiKeyPlaceholderMissing: "粘贴模型服务商提供的 API Key",
  apiKeyHintConfigured: "重新输入时会替换旧密钥；密钥仅保存本机，不进入日志。",
  apiKeyHintMissing: "只用于本次调用你提供的模型；不进入任何人可读的日志。",
  protocolLabel: "接口协议",
  protocolResponses: "Responses API",
  protocolChat: "Chat Completions API",
  protocolHint: "选择服务商实际支持的接口协议。",
  reasoningLabel: "推理强度",
  reasoningDefault: "模型默认",
  reasoningLow: "Low · 较快",
  reasoningMedium: "Medium · 均衡",
  reasoningHigh: "High · 深入",
  reasoningXhigh: "XHigh · 更深入",
  reasoningMax: "Max · 最细",
  reasoningHint: "推理强度控制响应时间与价格；仅影响支持它的模型。",
  save: "保存配置",
  testing: "正在请求模型…",
  test: "测试连接",
  saveAnywaySave: "保存配置",
  saveError: "请填写模型服务地址、模型名称和模型服务商提供的 API Key。",
  saved: "模型配置已保存。点击测试连接，确认服务能够实际返回内容。",
  dirtyStatus: "有未保存更改",
  passStatus: "连接已验证",
  failStatus: "连接测试失败",
  configuredStatus: "已配置 · 待测试",
  missingStatus: "尚未配置",
  dirtyHint: "配置已更改，请保存后再测试。",
  testHint: "测试会发起一次小型模型请求，可能产生少量费用；最长等待约 50 秒。",
  helpKicker: "连接说明",
  helpTitle: "连接不上的话",
  helpIntro: "保存成功后，AI 开发界面仍会用你保存的模型服务连接。遇到错误时，先自查下面三格：",
  helpStep1: "确认模型服务地址有效",
  helpStep2: "确认 API Key 拥有模型权限",
  helpStep3: "确认模型支持所选协议与推理强度",
  helpLink: "查看上手指南 →",
  missingKey: "未设置",
  notConfigured: "未配置",
  resultPassTitle: "连接测试通过",
  resultFailTitle: "连接测试未通过",
  resultMeta: (model, protocol, seconds) => `${model} · ${protocol} · ${seconds.toFixed(1)} 秒`,
  resultSuccessCta: "开始 AI 开发 →",
  resultFailHint: "检查网络后再试一次",
};

const en: AgentSettingsCopy = {
  eyebrow: "AI CONNECTION",
  title: "Model connection",
  intro: "Connect your AI model service as this workspace's default; the first real connection — be patient for its answer.",
  credentialStrong: "The model service's API Key",
  credentialBody:
    "Credentials live only on this machine and in your SpecProof workspace; this Key is used for real model calls, never uploaded elsewhere.",
  forbiddenTitle: "Managed by the deployment administrator",
  forbiddenBody:
    "Model connection is a deployment-wide shared configuration. Ask the deployment administrator to set the model service; team access tokens cannot change it.",
  forbiddenLink: "Back to AI development →",
  loadFailedTitle: "Cannot load the model configuration right now",
  retry: "Retry",
  configTitle: "Model service configuration",
  managedText: "This configuration is managed by deployment environment variables. To change it, ask the deployment administrator to update the configuration and restart.",
  urlLabel: "Model service URL",
  urlPlaceholder: "https://your-model-service.example/v1",
  urlHint: "Use the endpoint your provider offers; the system normalizes /v1 or full paths.",
  modelLabel: "Model name",
  modelPlaceholder: "The exact model ID your provider supports",
  modelHint: "The model name must match the provider's ID exactly.",
  apiKeyLabel: "Model API Key",
  apiKeyPlaceholderConfigured: "Configured; re-enter to replace",
  apiKeyPlaceholderMissing: "Paste the API Key from your model provider",
  apiKeyHintConfigured: "Re-entering replaces the old key; keys are stored locally and never logged.",
  apiKeyHintMissing: "Used only for calls to the model you provide; never enters any readable log.",
  protocolLabel: "Protocol",
  protocolResponses: "Responses API",
  protocolChat: "Chat Completions API",
  protocolHint: "Pick the interface your provider actually supports.",
  reasoningLabel: "Reasoning effort",
  reasoningDefault: "Model default",
  reasoningLow: "Low · faster",
  reasoningMedium: "Medium · balanced",
  reasoningHigh: "High · deeper",
  reasoningXhigh: "XHigh · deeper still",
  reasoningMax: "Max · finest",
  reasoningHint: "Controls response time and price; only matters for models that support it.",
  save: "Save configuration",
  testing: "Asking the model…",
  test: "Test connection",
  saveAnywaySave: "Save configuration",
  saveError: "Please provide the model service URL, model name, and the API Key from your model provider.",
  saved: "Model configuration saved. Press Test connection to confirm the service really returns content.",
  dirtyStatus: "Unsaved changes",
  passStatus: "Connection verified",
  failStatus: "Connection test failed",
  configuredStatus: "Configured · not tested yet",
  missingStatus: "Not configured",
  dirtyHint: "Configuration changed — save it before testing.",
  testHint: "The test issues one small model request, which may cost a tiny amount; the wait is at most ~50 seconds.",
  helpKicker: "Connection 101",
  helpTitle: "If you cannot connect",
  helpIntro: "Once saved, AI development uses this as its model service. When it errors, check the three cells below:",
  helpStep1: "Confirm the model service URL resolves",
  helpStep2: "Confirm the API Key has model permission",
  helpStep3: "Confirm the model supports the chosen protocol and reasoning effort",
  helpLink: "Open the onboarding guide →",
  missingKey: "Not set",
  notConfigured: "Not configured",
  resultPassTitle: "Connection test passed",
  resultFailTitle: "Connection test failed",
  resultMeta: (model, protocol, seconds) => `${model} · ${protocol} · ${seconds.toFixed(1)}s`,
  resultSuccessCta: "Start AI development →",
  resultFailHint: "Check the network and try again",
};

export const AGENT_SETTINGS_BY_LOCALE: Record<Locale, AgentSettingsCopy> = { zh, en };
