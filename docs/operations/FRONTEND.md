# SpecProof 前端 (apps/web React SPA) 与 Web API — 使用/架构说明

## 1. 组件与文件

- apps/web/** — React 18 + Vite 5 + TypeScript SPA (深色工业风, 手写 CSS,
  无外部 UI 运行时依赖; 仅 devDeps: vite/typescript/@vitejs/plugin-react)。
  - src/api.ts — 统一 API client (fetch + SSE EventSource) + 全部响应类型。
  - src/App.tsx — 极简 hash 路由 (无路由库) + 侧栏布局 + 鉴权门。
  - src/pages/* — Login / Dashboard / Jobs / JobDetail / Matrix /
    FindingDetail / Contracts / Eval / Health 九个页面。
  - src/components.tsx — StatusPill / Panel / StatCard / Degraded /
    ErrorBox / Empty / Spinner 等共享组件。
  - src/styles.css — 主题 (GitHub-dark 系配色, 等宽字体强调工业风)。
- api/routes/web.py — 全部 /api/v1 只读端点 (Task A)。
- api/server.py — 挂载 web 路由 + SPA 静态目录与 fallback。
- scripts/build_web.ps1 — 一键构建脚本 (npm install + npm run build)。
- tests/unit/test_web_api.py — 新端点全覆盖 (假存储, 不依赖真实基础设施)。

## 2. 运行方式

1. 构建前端: cd apps/web; npm install; npm run build
   (或 .\scripts\build_web.ps1)
2. 启动后端: $env:SPECPROOF_API_KEY=...; python -m api.server
3. 打开 http://localhost:8000/ — 输入 API Key 登录 (sessionStorage,
   每次请求以 X-API-Key 头发送)。
4. 开发模式: cd apps/web; npm run dev (5173 端口, vite proxy 转发
   /api /jobs /health /metrics 到 localhost:8000)。

## 3. 挂载与回退语义

- 存在 apps/web/dist/index.html 时: GET / 与所有非 API 深链
  (如 /jobs/abc) 返回 SPA index.html (SPA fallback); /assets/* 静态直出;
  api/ jobs metrics health webhooks dashboard docs redoc openapi.json
  前缀不受 fallback 影响, 未匹配仍 404。
- 不存在 dist 时: 回退旧行为 — /dashboard 重定向到
  /dashboard/static/index.html (旧静态页)。

## 4. 鉴权与 SSE

- 所有 /api/v1/* 与 /jobs/* 走 require_api_key (fail-closed) +
  enforce_rate_limit (Redis 计数, fail-open)。
- SPECPROOF_API_KEY 未配置 -> 503; 密钥错误/缺失 -> 401。
- EventSource 无法设置请求头: SSE 进度流 /jobs/{id}/progress 支持
  ?key=<api-key> 或 ?api_key=<api-key> 查询参数 (api/auth.py 的最小适配,
  恒定时间比较; 本应用不记录查询串)。普通 fetch 一律走 X-API-Key 头。

## 5. 端点清单与降级语义 (api/routes/web.py)

| 方法 | 路径 | 数据源 | 降级/缺失语义 |
|---|---|---|---|
| GET | /api/v1/dashboard | MySQL (verification_jobs) | MySQL 不可用 -> 200 + degraded:true + 空聚合与 reasons; 成本/token 账本未持久化 -> available:false + 说明 (绝不伪造) |
| GET | /api/v1/jobs/{id}/stages | Redis 进度流 (xread_progress) | 任务不存在 -> 404; Redis 不可用 -> 200 + degraded:true + stages:[] |
| GET | /api/v1/jobs/{id}/matrix | MySQL contracts 表 + summary 计数 | 任务不存在 -> 404; 表为空 -> rows:[] + summary 计数 |
| GET | /api/v1/jobs/{id}/findings | summary JSON + findings 表合并 | 任务不存在 -> 404; 均无 -> findings:[] (诚实空) |
| GET | /api/v1/jobs/{id}/certificate | reports/ 目录证书产物 (merge-certificate-*/rejection-notice-* + signed-*) | 无产物 -> 404 (绝不现场重造证书) |
| GET | /api/v1/jobs/{id}/capsule | capsules/ 目录 zip (校验 PK 魔数, 仅 basename, 防路径穿越) | 无 zip -> 404; ?name= 指定 |
| GET | /api/v1/contracts?status=...&repo_path= | MySQL contract_registry | MySQL 不可用 -> 503 (注册表是持久业务状态, 与 registry.py 语义一致) |
| GET | /api/v1/eval/latest | docs/eval/eval-report.results.json | 文件不存在 -> 404 + 说明; 不可读 -> 503 |
| GET | /api/v1/health | 6 依赖逐项探测 (mysql/mongodb/es/redis/rabbitmq/minio), 带 latency_ms | 任一失败 -> status:degraded + degraded:true (绝不抛错) |

## 6. 环境变量

- SPECPROOF_CAPSULE_DIR — capsule zip 搜索目录 (默认 <repo>/capsules, cwd/capsules)
- SPECPROOF_REPORTS_DIR — 证书/拒绝通知目录 (默认 <repo>/reports)
- SPECPROOF_EVAL_REPORT_PATH — 评测报告路径 (默认 <repo>/docs/eval/eval-report.results.json)
- 其余沿用既有: SPECPROOF_API_KEY / SPECPROOF_RATE_LIMIT_PER_MIN / CORS 等。

## 7. 已知限制 (诚实记录)

- 成本与 Token 汇总: 管线未持久化任何成本/token 账本 (Redis 预算键仅按任务
  且未被使用), Dashboard 以 available:false 显式呈现。
- 证书: 由 CLI verify 流程写入 reports/; API 任务 (worker 路径) 当前不产出
  证书文件, 对应端点返回 404。
- jobs 列表: 沿用既有 GET /jobs (limit=200 内前端筛选/分页)。
