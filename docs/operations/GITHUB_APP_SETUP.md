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

### 2.1 这些名字要靠载体抵达容器 (#257)

上面四个 GitHub 名字过去只有 `.env.example` 在 advertise, compose 一个都不插值——
按本节在 `.env` 里填好之后, api 与 worker 进程仍然读不到它们 (webhook 恒 503,
Check Run 恒跳过), 而本节读起来像是已经配好了。现在
`compose.production.yml` 把它们带进容器: api 拿全部四个 (webhook secret 只有 api
的 `integrations/github.py` 读), worker 拿 App 三件套 (终态发布在 worker)。
载体一律是 `${X:-}` 空值透传: `GitHubAppConfig.from_env()` 与 webhook 校验都按
**真值**判断, 空串等同未设置, 所以没填 `.env` 的栈与改动前逐字节同行为。
这件事由 `tests/unit/test_env_knobs_reach_the_process_that_reads_them.py` 钉住
(#257 D02: 清单声明的旋钮必须有抵达读它的进程的载体; D04: 空值透传的行必须是空行)。

两个仍在平面外的选项, 不是笔误:
- `GITHUB_APP_PRIVATE_KEY_FILE` 没有载体 (compose 不插值这个名字), 所以
  "/run/secrets/github-app-key.pem" 这条路径只在宿主机/CLI 平面可用; 容器里请改用
  `GITHUB_APP_PRIVATE_KEY` 内联 PEM (Secret Manager 注入)。
- `SPECPROOF_PUBLIC_URL` 是刻意不交付的 (#257 D02 的登记项): 它的三个读者带着两套
  默认值 (verify 命令与 webhook 路由回落空串, `api/routes/admin.py` 回落自己的
  origin), 任何一个 fallback 都会改变某个未改动栈的行为。门 #235 L10 钉住这个分歧。

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
