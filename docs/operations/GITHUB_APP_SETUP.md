# GitHub App 配置指南 (Required Check 上线步骤)

对应 PRODUCTION_SPEC 第 13 节。Check Run 主体已实现
(integrations/github_checks.py + CP webhook + worker 终态 + CLI
--publish-check); 本文档给出把 specproof/verify 变成合入门槛的操作步骤。

## 1. 创建 GitHub App

1. 组织 Settings -> Developer settings -> GitHub Apps -> New GitHub App。
2. 权限 (最小权限原则, 与规格 13 一致):
   - Metadata: read (默认)
   - Contents: read
   - Pull requests: read
   - Checks: write
   - (仅启用 Fix 功能时) Contents: write
3. 订阅事件: pull_request, issue_comment, installation,
   installation_repositories。
4. Webhook URL 二选一:
   - 直连 Runtime: https://<host>/webhooks/github (Python)
   - 或 Control Plane: https://<host>:8081/api/v1/webhooks/github
   - 二选一, 不要同时启用 (同一 delivery 两个端点会各建一个 job)。
5. Webhook secret: 生成强随机值, 填入 GITHUB_WEBHOOK_SECRET。
6. 生成 Private key (PEM), 下载保存; 记录 App ID。
7. Install App 到目标仓库 (记录 Installation ID — 在安装 URL 的
   installation_id 参数里)。

## 2. 环境变量

    GITHUB_WEBHOOK_SECRET=<webhook secret>
    GITHUB_APP_ID=<App ID>
    GITHUB_APP_INSTALLATION_ID=<Installation ID>
    GITHUB_APP_PRIVATE_KEY=<PEM 内容, 生产用 Docker Secret/Secret Manager>
    SPECPROOF_PUBLIC_URL=https://specproof.example.com

半配置 (缺任一 App 变量) 会响亮报错并跳过发布; 完全不配置则静默跳过
(验收结果不受影响)。

## 3. 验证 Check Run

1. 向仓库开一个 PR -> webhook 建单 -> Check Run 显示
   specproof/verify (in_progress, 带 dashboard 链接)。
2. 等待 worker 终态 -> Check Run 变为 completed:
   - VERIFIED -> success (绿色)
   - BLOCKED/FAILED -> failure (红色, 拦合并)
   - CANCELLED/NEEDS REVIEW -> neutral (灰色)
3. 本地复现 (无 PR): specproof verify ... --depth RELEASE --publish-check。

## 4. 设为 Required Check

1. 仓库 Settings -> Branches -> Add branch protection rule。
2. Branch name pattern: main (或 master)。
3. 勾选 "Require status checks to pass before merging"。
4. 搜索并选中 specproof/verify。
5. (建议) 勾选 "Require conversation resolution" 配合 Inline Finding 工作流。

至此 specproof/verify 成为合入门槛: 验收为 VERIFIED 才能合入,
BLOCKED/FAILED 会拦住 PR — 这正是产品核心承诺的机器可执行形态。

## 5. 安全注意

- 私钥只放 Secret Manager; 轮换时 GitHub App 支持双密钥共存, 先激活
  新密钥再删除旧密钥。
- Webhook secret 轮换期间 GitHub 会重投, delivery 幂等兜底 (Python
  内存键 + CP 唯一索引), 不会产生重复 job。
- Fork PR 更严格: 沙箱已 --network none + --cap-drop ALL +
  no-new-privileges, 规格 12 的 fork 强化在试点阶段验证。
