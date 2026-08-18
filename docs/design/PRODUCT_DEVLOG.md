# SpecProof 产品化开发记录 (2026-08-17, 第四轮)

目标: 完整的前端+后端+中间件+RAG 综合 Agent 产品形态。

## 本轮新增

### 1. 代码符号图谱 RAG (创新点)
- agent/repo_graph.py: 确定性符号图 (类/方法/调用点), 不依赖外部向量服务。
  检索命中后按调用图 1 跳扩展 (callee/caller/同类别名), 让契约编译看到
  "验证上下文" 而不只是关键词命中。5 个单测。
- retrieve_repository_context 节点: ES BM25 → 图谱扩展 → 16 条上下文;
- compile_contracts LLM prompt 正式接入 repo_context (RAG 的 Generation 步,
  此前检索结果采集后从未使用 — 本轮打通端到端)。

### 2. P2-b 宪法检查器
- agent/checkers/constitution.py: 需求中的 "forbidden changes" 条款
  (must not remove auth / never publish twice / token invalidation /
  schema fields) 映射为 Base/Head diff 上的确定性检查器, 产出
  constitution_check 证据。4 个单测。已接入 run_static_checks。

### 3. Job 摘要持久化 + Web Dashboard (前端+后端)
- 迁移 0003: verification_jobs.summary JSON 列;
- MySQLStore.save/get_job_summary; worker 与 verify CLI 完成后写摘要
  (判定/矩阵/findings/capsules/report/retrieval_note/errors);
- GET /jobs/{id}/summary;
- api/static/index.html: 暗色 Dashboard (任务列表/详情/矩阵统计/
  findings 表/证据与检索/SSE 实时进度), API Key 前端配置;
- 5 个 Dashboard API 测试 (鉴权/404/静态页/metrics)。

### 4. 可观测性 (中间件)
- api/metrics.py: 无外部依赖的 Prometheus 文本指标 (进程级计数器);
- GET /metrics 抓取端点; 每请求计数中间件 (5xx 计数);
- (OTel 全链路接入仍在下轮 — 指标基线先落地)

### 5. 部署物
- docker/Dockerfile.api / Dockerfile.worker (python:3.12-slim);
- compose.production.yml: api + worker 服务 (密钥 fail-closed 校验、
  健康依赖、worker 挂 docker.sock 以启用沙箱)。

## 实测
- 本批新增测试全部通过 (repo_graph 5 + constitution 4 + dashboard 5)
- ruff / mypy 全绿
- 全套回归见本轮最终 pytest 运行
