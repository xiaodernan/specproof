# SpecCraft 商业化终极计划书 — 逐条差距审计与执行映射 (AGENT_PLAN_GAP_AUDIT)

审计日期: 2026-08-18 · 依据: docs/代码开发Agent商业化终极计划书.md (1005 行, 已逐条通读)
原则: 每条要求 → 现状(证据) → 差距 → 行动车道; 数字来自真实运行; 持续更新。

## A. §22 首批 12 任务逐条映射

| # | 任务 | 现状 | 行动 |
|---|---|---|---|
| 1 | AgentTask/Plan/Step/ToolCall/Approval/Artifact/ChangeBundle Schema | 部分: TaskSpec/Plan/Step 已有 (craft/spec+planner), ToolCall/Approval/Artifact/ChangeBundle 缺 | R 车道: craft/schemas.py 全量 Schema (O 完成后) |
| 2 | 工具注册表+版本化 Envelope (read/search/diff/patch/test/build/git_status) | 部分: editor/executor 直连, 无注册表/版本化信封 | R 车道: craft/tools.py |
| 3 | 持久化 Job 投影/取消/租约/恢复 | 部分: 本地 checkpoint+resume (M1/M2); 无 MySQL agent_jobs | R 车道 + 阶段 3 (需 craft/ 空闲) |
| 4 | 仓库规则摄取 (AGENTS.md/CLAUDE.md/README/CI) | ✗ | R 车道: craft/rules.py + 优先级 (安全>组织>仓库>目录>任务>默认>模型建议) |
| 5 | 4 语言最小符号索引 + 30 条检索基准 | ✅ 已完成+实测 (S 车道 2026-08-18): retrieval/symbols.py 四语言索引 (py=ast / ts+go=保守正则 / java=repo_graph 同风格), 30 查询黄金集 (retrieval/bench_queries.py), scripts/bench_retrieval.py 真实 ES 实测: BM25 recall@10=82.2% MRR=0.656; BM25+图谱=48.9%/0.528 (top-8 种子插值语义, 详因见报告); symbol-index 查表=75.6%/0.683 (找回 4000 字符截断丢失的符号); 门禁 ruff/mypy/bandit 全绿; 详情 docs/eval/retrieval-bench.md | 已完成; 后续消融: 向量/RRF/重排 (L 车道 retrieval/hybrid.py 已有, 未并入本轮数字) |
| 6 | editor stale digest + 用户改动分类 + 结构化 Diff | 部分: 唯一匹配+原子写+备份+审计 (F); digest/stale 分类缺 | R 车道: editor 扩展 |
| 7 | 测试/构建/类型/安全/SpecProof 自校验门禁 | 部分: O 在做 M3 自校验 (checker+密钥); 分层门禁缺 | O (在途) + R 车道组合 |
| 8 | Web 任务向导/计划审阅/实时工具流/审批/Diff | ✗ (9 页验证控制台, 无 Agent 工作台) | U 车道 (后端 Task API 先行) |
| 9 | 只读 Explorer/Test/Security 并行 (不共写同文件) | ✗ | R/U 之后: craft/agents.py |
| 10 | 50 代码任务+20 对抗+10 恢复+10 审批 评测集 | 部分: 10 微基准 (含 1 陷阱); 对抗/恢复/审批集缺 | V 车道 (本轮): bench/ 扩展 |
| 11 | OIDC/租户/RBAC/审计/配额 | 部分: CP tenant/user 实体; 其余缺 | 工业化指南阶段 1 (T 车道) |
| 12 | GitHub/GitLab PR 自动化, IDE, MCP 客户端, 计费, 私有化 | 部分: GitHub App+fix PR, MCP 服务端; 其余缺 | 后续阶段 (M10/M8/M9 对应) |

## B. M0-M11 里程碑现状映射

| 里程碑 | 现状 | 差距 |
|---|---|---|
| M0 现状冻结 | ✅ 大部分 (craft 基线/10 任务基准/边界文档) | 统一 Schema 缺 (任务1) |
| M1 工具协议执行器 | 部分 (editor/executor 白名单) | 注册表+信封+批准服务 (任务2) |
| M2 仓库理解 | 部分 (BM25+向量+图谱; 规则摄取缺) | S+R 车道 |
| M3 稳定计划循环 | ✅ 大部分 (DAG/checkpoint/预算/STUCK/暂停恢复) | MySQL 投影 (任务3) |
| M4 代码编辑跨语言 | 部分 (唯一匹配编辑; Q 在做执行适配器) | AST 编辑/stale 保护 (任务6) |
| M5 SpecProof 闭环 | 部分 (O 做自校验; accept 接线待) | ChangeBundle+accept (任务1/7) |
| M6 Web+IDE | 部分 (验证控制台 9 页) | Agent 工作台 20 路由 (任务8) |
| M7 并行子代理 | ✗ | 任务9 |
| M8-M11 企业/模型/生态/评测 | 部分 (provider 治理 W13, 微基准) | 工业化指南阶段 1/6/7 对齐 |

## C. §3.3 目标指标当前值

| 指标 | 目标 | 实测 |
|---|---|---|
| 10 微基准完成率 | ≥90% | 90.0% (确定性+LLM 双档实测) ✅ |
| 陷阱拦截率 | 100% | 100% (1/1) ✅ |
| 50 中型任务完成率 | ≥80% | 未测 (V 车道补) |
| 编辑成功率 / stale 覆盖 0 | 98% / 0 | 未量化 (R 车道补) |
| Worker 恢复率 | ≥99.9% | 未量化 |
| 预算超限进入终态 | 100% | ✅ (M1 实测 FAILED/EXPIRED/STUCK 语义) |

## D. 本轮执行

1. 本审计文档落盘并提交。
2. S 车道: 4 语言最小符号索引 + 30 条检索基准 (任务5) — ✅ 已完成, 实测数字见上表与 docs/eval/retrieval-bench.md。
3. V 车道: 评测集扩展 50+20+10+10 (任务10, bench 数据面)。
4. R 车道 (O 完成后立即): craft/schemas.py + tools.py 注册表 + rules.py 摄取 +
   editor stale-digest (任务 1/2/4/6) — 这是"完整商业化代码开发 Agent"的核心工程。
5. 其余 (8/9/11/12) 按依赖顺序推进, 每轮更新本表。
