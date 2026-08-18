# 全栈架构盘点 (STACK INVENTORY) — 完整前端/后端/中间件证据

日期: 2026-08-18 · 状态: 已实测 (本文件所有数字来自真实运行)
对标: Claude Code / Codex (docs/design/AGENT_STATE_OF_ART.md 差距矩阵)

## 1. 层次与规模 (文件数, 不含生成物/备份)

| 层 | 组件 | 文件 | 角色 |
|---|---|---|---|
| 前端 | apps/web (React18+Vite5+TS, 9 页 SPA) | 13 src + dist 产物 | 登录/Dashboard/Jobs/JobDetail(SSE)/Matrix/Finding/Contracts/Eval/Health |
| 后端-API | api/ (FastAPI) | 9 | 14+ 端点: jobs/webhooks/9 个 /api/v1 只读聚合 + SSE + /metrics |
| 后端-CP | services/control-plane (Spring Boot 3) | 22 java | 租户/用户/job 只读投影/webhook 验签/outbox/审计, 迁移 0001-0004 |
| 后端-Worker | agent/ (LangGraph 14 节点) + storage/ (MySQL/Mongo/ES/Redis/RabbitMQ/MinIO) | 36+10 | 验证管线 + 任务消费 + 可靠性 (outbox/幂等/10态) |
| 中间件 | api/middleware.py + auth/rate-limit/CORS/metrics/tracing/logging | — | RequestID → Payload(10MB) → Auth(fail-closed) → RateLimit → CORS → 路由; SSE 豁免 |
| 协议 | mcp/ (stdio JSON-RPC 2024-11-05) | 3 | 6 工具: verify/contracts/eval/craft_plan/health/replay_info |
| Agent 开发 | craft/ (SpecCraft) | 8 | 规划(确定性+LLM)/编辑器/执行/收敛循环/预算/LLM 客户端 |
| LLM 工程 | providers/ | 8 | 11 维探测/降级/thinking 分层/缓存友好模板/预算账本 |
| RAG | retrieval/ + storage/elasticsearch + agent/repo_graph | 4+ | BM25+向量→RRF→图谱邻域→重排(三层降级) |
| 验证核心 | evidence/ (5) + experiments/ (3) + sandbox/ (2) + integrations/ (4) | 14 | 证书/血缘/报告/变异/状态快照/沙箱/GitHub App |
| 可观测 | observability/ (6) + infra/ (otel/prometheus/grafana) | 6+ | 日志(结构化+request_id)/指标/OTel/Grafana 15 面板+7 告警 |
| 评测 | bench/ (10 任务微基准) + golden-cases (100) + tests (600+) | 40+ | 验证侧/开发侧/安全/故障四层评测 |
| 部署 | compose×3 + docker/ + scripts/ | — | infra + app + observability 三文件组合, 单机 16-32GB |

## 2. 全链路实测证据 (2026-08-18, 本轮)

- 三文件 compose config: exit 0
- 前端 npm run build: 174.95kB JS (gzip 55.57kB) / 2.08s
- uvicorn 实测 (真实基础设施): /api/v1/health = ok (6 依赖), /api/v1/dashboard = 558 任务聚合, / = SPA 200
- 全量门禁: ruff 全绿 + mypy 107 文件 + bandit 0 Medium+ + 635 tests passed
- MCP 冒烟: health 6 依赖 8.7-91ms; uvicorn request-id 逐字回显
- 真实 LLM: probe 8/11; 100 案例基线 (发现率 100%/严格归因 0%/5 误报); SpecCraft M2 两个真实任务均 1 次迭代收敛 (KV 缓存命中 512)

## 3. 与 Claude Code/Codex 的差距状态 (矩阵 §7 结论)

同级/更严: agent 循环(规划-执行-验证-预算-断点)、编辑安全、沙箱(非root/断网/ro)、
安全治理(密钥/注入-实测 0 影响)、上下文(稳定前缀 KV 缓存-实测命中)、GitHub App、
可观测全链路。系统性超出: 契约编译/差分实验室/变异/证据链+签名证书/血缘/100 案例基准。
已补齐: MCP 工具服务 (外部 Agent 可直接调用我们的验证)、完整前后端中间件、
10 任务微基准。剩余路线: MCP 客户端、子代理并行、仓库策略摄取、语义缓存 (矩阵 §7 已排期)。

## 4. 维护方式

- 本文件随每次架构级改动更新; 数字必须来自真实运行, 禁止凭记忆写入。
- 全栈验收命令: compose config ×3 / npm run build / 全量门禁 / API 冒烟四件套。
