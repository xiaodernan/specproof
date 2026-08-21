# SpecProof 前端 e2e (Playwright)

工业化指南 §A 任务 5 + 阶段2 出口 (docs/architecture/GUIDE_GAP_AUDIT.md row 5):
前端 Playwright 场景 — 向导 / 详情 / 权限 / 降级。

## 场景清单

| 场景 | 文件 | 断言 |
|---|---|---|
| 向导 wizard | wizard.spec.ts | 通过现有 4 步 Agent 向导 (仓库→需求→门禁→提交) 走真实 POST /agent/jobs 创建任务, 重定向到达详情页 (#/agent/jobs/:id), 时间线/状态/规格渲染 |
| 详情 detail | detail.spec.ts | 验证任务详情页渲染矩阵摘要 (Verdict/PASS/FAIL/UNVERIFIED)、证据与产物 (报告路径)、阶段时间线、Findings、证书文档; 需求矩阵页渲染合约行 |
| 权限 permissions | permissions.spec.ts | W37 身份 UI: admin 可见身份控制台 (新建用户/角色管理); viewer 看不到 admin 专属控件 (身份页无权限提示 + 控件不渲染, 侧栏入口随 App.tsx 导航门隐藏或点击后仍被拦; 只读页面仍可用); 未认证访客只能看到登录门 |
| 降级 degradation | degradation.spec.ts | 后端完全不启动: 登录页/总览/任务/向导均渲染优雅错误提示 (data-testid=errorbox), 无白屏; 应用级 ErrorBoundary 兜底渲染崩溃 |

## 架构: 真实应用, 不 mock DOM

Playwright (chromium headless)
  -> http://127.0.0.1:5174  真实的 Vite dev server (apps/web, 使用专用
                             vite.e2e.config.ts: 端口 5174 + proxy 指向 8010)
       -> proxy /api /auth /agent /jobs /health /metrics -> http://127.0.0.1:8010
            -> fixture_server.py 用 uvicorn 启动真实的 api.server.app

- 后端 = 现有 API 服务本身。tests/e2e/fixture_server.py 不做任何 DOM mock, 也不修改
  api/ 代码: 它只按单元测试同款手法 (tests/unit/test_api_jobs.py) 把存储后端换成内存假件 —
  MySQL 校验任务路由 + Redis 进度流, 预置一个 VERIFIED 任务 (summary/matrix/findings/
  stages/merge-certificate) 供详情场景使用; Agent 控制台保留真实内存后端
  (SPECPROOF_AGENT_JOBS_URL=""), 向导走真实 POST /agent/jobs -> GET /agent/jobs/:id。
- 多租户身份开启 (SPECPROOF_AUTH_ENABLED=true + sqlite 身份库): fixture 只引导 1 个
  admin sp_* token; viewer 用户与 token 由 global-setup.ts 通过真实 /api/v1/admin/*
  HTTP 端点创建 (RBAC 路径即生产路径)。
- 降级场景: playwright.degradation.config.ts 有意不启动后端, 所有 API 经 Vite proxy
  连接失败, 断言优雅降级。该配置在主配置之后运行 (共用 5174 端口)。
- 无 LLM 调用: Agent 控制台是投影层, 创建任务不会触发 worker/LLM; e2e 全程无外呼。

## 运行

前置: apps/web 已 npm install (含 @playwright/test) 且 npx playwright install chromium
已执行; python 环境含 fastapi/uvicorn/bcrypt/pymysql (与后端测试同环境)。

从 apps/web (Windows):

    npm run test:e2e

等价于:

    set NODE_PATH=node_modules&& ^
    playwright test --config=../../tests/e2e/playwright.config.ts && ^
    playwright test --config=../../tests/e2e/playwright.degradation.config.ts

(PowerShell: 先执行 $env:NODE_PATH=(Resolve-Path .).Path+'\node_modules' 再逐条运行。
NODE_PATH 让位于 tests/e2e 的配置与用例能解析 apps/web/node_modules 中的
@playwright/test — 依赖仍只声明在 apps/web devDependencies。)

单独跑一个场景:

    $env:NODE_PATH=(Resolve-Path .).Path+'\node_modules'
    npx playwright test --config=../../tests/e2e/playwright.config.ts -g "向导"

## 端口与产物

- 8010: fixture API (e2e 专用 vite.e2e.config.ts 的 proxy 目标; 与开发用 8000 端口
  互不冲突, 开发者本地的 api 服务器照常运行)
- 5174: Vite dev server (通过 vite.e2e.config.ts 固定端口, 占用会直接报错)
- 8000: 不占用 — 该端口留给文档中的开发命令 (python -m uvicorn api.server:app)
- .state/: fixture 引导凭据 + 运行期产物 (gitignored)
- test-results/, playwright-report/: Playwright 报告 (gitignored, 失败保留 trace)

## 约束

- 不修改 api/、docs/、storage/ 等受保护区; 唯一 Python 文件是
  tests/e2e/fixture_server.py (ruff/mypy 全绿)。
- apps/web/src 仅最小增量: data-testid (identity-forbidden / wizard-repo / wizard-task /
  wizard-spec / wizard-submit), useIdentityAccess 身份控制台可见性门 (服务端 RBAC 仍是权威)。
  注意: App.tsx 身份导航门与 ErrorBoundary 组件 (errorbox/error-boundary testid) 已随并行
  UI 车道 (W41 设计系统) 合入其提交; 本套件对两者保持兼容 (errorbox 用稳定 class 断言)。
