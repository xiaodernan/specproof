# SpecCraft 商业化终极计划书 — 逐条差距审计与执行映射 (AGENT_PLAN_GAP_AUDIT)

审计日期: 2026-08-18 · 依据: docs/代码开发Agent商业化终极计划书.md (1005 行, 已逐条通读)
原则: 每条要求 → 现状(证据) → 差距 → 行动车道; 数字来自真实运行; 持续更新。

## A. §22 首批 12 任务逐条映射

| # | 任务 | 现状 | 行动 |
|---|---|---|---|
| 1 | AgentTask/Plan/Step/ToolCall/Approval/Artifact/ChangeBundle Schema | ✅ 已完成 (R 车道 2026-08-18): craft/schemas.py 全量 Schema — AgentTask (task_id/text/repo/base_sha/execution_mode/budget/desired_checks/network_policy/model_policy/idempotency_key) + ToolCall {tool,version,call_id,arguments,budget_cost,requires_approval} + ToolResult + Approval + Artifact (sha256 digest 校验) + ChangeBundle (含 specproof_result); PlanSchema/StepSchema 与 planner dataclass 双向适配 (plan_to_schema/plan_from_schema 复用 DAG 校验: 唯一 id/依赖次序/≤12 步); 全模型 schema_version=1 强制版本门; tests/unit/test_craft_schemas.py 27 测试 | 完成; 后续: M5 ChangeBundle->accept 接线 (O 车道) |
| 2 | 工具注册表+版本化 Envelope (read/search/diff/patch/test/build/git_status) | ✅ 已完成 (R 车道 2026-08-18): craft/tools.py ToolRegistry — 13 工具 v1 (read_file/tree/glob/grep/symbol_search[接 repo_graph 只读]/git_status/git_diff[GitPython 只读]/apply_patch/create_file/run_test/run_build/run_lint/run_typecheck[executor 白名单]); 每工具 {version, param schema(类型/长度/范围), risk readonly|low_write|controlled_exec|high, requires_approval 判定, budget_cost}; dispatch 门链: 未知工具→版本→参数→审批→路径(owned_paths 越界拒绝)→执行; 12 稳定错误码 ([CODE] 前缀); 结果截断+秘密脱敏 (sk-/Bearer/私钥头)+untrusted 标签; envelope_block() 版本化且结果零泄漏; 参数非法实测不执行; tests/unit/test_craft_tools.py 36 测试 (含 loop 诊断路径经注册表 dispatch 接线回归: 共享审计链, report.tool_registry 上账) | 完成; 后续: provider tools 参数原生支持 (网关 strict_tool_calls=400 已降级 envelope) + M4 批准服务持久化 |
| 3 | 持久化 Job 投影/取消/租约/恢复 | ✅ 已完成 (W30 任务3 2026-08-19): storage/agent_jobs.py — AgentJobStore 协议 + InMemory/SQLite/MySQL 三后端; 投影 create/get/list/update_status/set_plan/set_progress; 原子租约 lease (单条条件 UPDATE: 过期或同 owner 才授予)/renew/release; cancel 无条件胜出租约 (终态下租约/投影/状态迁移全拒, 取消幂等); spec_digest=sha256(spec_text); SQL 全静态语句+占位符 (bandit B608 零抑制), 终态字面量与状态元组一致性由测试守护; tests/unit/test_agent_jobs.py 55 用例全绿 (租约争用/过期接管/精确边界/renew 续期/cancel-胜出租约/终态不可变/digest 稳定/状态迁移/SQLite×InMemory 双后端一致性); MySQL 集成测试 MYSQL_URL 门控干净跳过 (tests/integration/test_agent_jobs_mysql.py); 门禁 ruff/mypy strict/bandit 全绿 (mypy strict 2 文件 0 问题); CraftLoop 接线见模块末尾 Integration note (create/lease/set_progress/update_status/cancel 位置已标注, 不占 craft/ 车道) | R 车道接线: CraftLoop 按 Integration note; 恢复 = from_checkpoint 后重租约 (note §6) |
| 4 | 仓库规则摄取 (AGENTS.md/CLAUDE.md/README/CI) | ✅ 已完成 (R 车道 2026-08-18): craft/rules.py RepositoryRules.load(repo) — AGENTS.md/CLAUDE.md/README/CONTRIBUTING/SECURITY.md/.github CI workflows + 子目录 AGENTS.md/CLAUDE.md (限深 4/≤30, node_modules 等跳过, 单文件 200KB/总量 1MB 截断诚实标注); 每条 {source,digest(sha256),text,section,priority}; 优先级 7 级实现 security>organization>repository>directory>task>default>model_suggestion (内置平台安全策略封顶, SECURITY.md 归 security 层); 冲突检测: 含"忽略(所有)安全"字样 → conflict 标记 + 冲突列表 + security 层降级 (绝不视为高优先级); prompt_block() 全量数据段包裹 (craft.llm.wrap_data_section, 注入防御: 规则文本只进数据段); tests/unit/test_craft_rules.py 17 测试 | 完成; 后续: 组织策略注入接口 (org 层无标准文件名, 预留) |
| 5 | 4 语言最小符号索引 + 30 条检索基准 | ✅ 已完成+实测 (S 车道 2026-08-18): retrieval/symbols.py 四语言索引 (py=ast / ts+go=保守正则 / java=repo_graph 同风格), 30 查询黄金集 (retrieval/bench_queries.py), scripts/bench_retrieval.py 真实 ES 实测: BM25 recall@10=82.2% MRR=0.656; BM25+图谱=48.9%/0.528 (top-8 种子插值语义, 详因见报告); symbol-index 查表=75.6%/0.683 (找回 4000 字符截断丢失的符号); 门禁 ruff/mypy/bandit 全绿; 详情 docs/eval/retrieval-bench.md | 已完成; 后续消融: 向量/RRF/重排 (L 车道 retrieval/hybrid.py 已有, 未并入本轮数字) |
| 6 | editor stale digest + 用户改动分类 + 结构化 Diff | ✅ 部分完成 (R 车道 2026-08-18): craft/editor.py — sha256 digest (raw bytes): read_file_meta/FileRead/file_digest; write_file/apply_edit 可选 expected_digest → 不匹配 StaleContextError(STALE_CONTEXT) 拒绝写入 (实测文件不被覆盖/不备份), 旧调用零行为变化 (134 既有测试全绿); 审计条目带 before_digest/after_digest (audit.jsonl 含全字段); classify_workspace_changes(git status --porcelain) → {user_changes, agent_changes, unknown} (冲突对 DD/AU/UD/UA/DU/AA/UU、未跟踪、重命名归 unknown); tests/unit/test_craft_editor_stale.py 22 测试 | 结构化 Diff 仍缺 (待 M4: AST 编辑+跨文件重构, 与任务 9 并行) |
| 7 | 测试/构建/类型/安全/SpecProof 自校验门禁 | 部分: O 在做 M3 自校验 (checker+密钥); 分层门禁缺 | O (在途) + R 车道组合 |
| 8 | Web 任务向导/计划审阅/实时工具流/审批/Diff | ✗ (9 页验证控制台, 无 Agent 工作台) | U 车道 (后端 Task API 先行) |
| 9 | 只读 Explorer/Test/Security 并行 (不共写同文件) | ✗ | R/U 之后: craft/agents.py |
| 10 | 50 代码任务+20 对抗+10 恢复+10 审批 评测集 | 部分: 10 微基准 (含 1 陷阱); 对抗/恢复/审批集缺 | V 车道 (本轮): bench/ 扩展 |
| 11 | OIDC/租户/RBAC/审计/配额 | 部分: CP tenant/user 实体; 其余缺 | 工业化指南阶段 1 (T 车道) |
| 12 | GitHub/GitLab PR 自动化, IDE, MCP 客户端, 计费, 私有化 | 部分: GitHub App+fix PR, MCP 服务端; 其余缺 | 后续阶段 (M10/M8/M9 对应) |

## B. M0-M11 里程碑现状映射

| 里程碑 | 现状 | 差距 |
|---|---|---|
| M0 现状冻结 | ✅ 大部分 (craft 基线/10 任务基准/边界文档) | 统一 Schema ✅ (任务1, craft/schemas.py) |
| M1 工具协议执行器 | 部分 (editor/executor 白名单) | 注册表+信封 ✅ (任务2); 批准服务持久化待 M4 |
| M2 仓库理解 | 部分 (BM25+向量+图谱) | 规则摄取 ✅ (任务4, craft/rules.py); 检索消融 S/L 车道在途 |
| M3 稳定计划循环 | ✅ 大部分 (DAG/checkpoint/预算/STUCK/暂停恢复) | MySQL 投影 ✅ (任务3, storage/agent_jobs.py, 55 测试) |
| M4 代码编辑跨语言 | 部分 (唯一匹配编辑; Q 在做执行适配器) | stale 保护 ✅ (任务6, digest+STALE_CONTEXT+改动分类); AST 编辑/结构化 Diff 待 |
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
4. R 车道: craft/schemas.py + tools.py 注册表 + rules.py 摄取 + editor stale-digest
   (任务 1/2/4/6) — ✅ 已完成: 4 个新模块 + editor/loop/llm 接线, 新增 102 测试全绿,
   既有 craft 134 测试回归全绿, ruff/mypy/bandit 全绿 (详见上表 1/2/4/6 行证据)。
5. 其余 (8/9/11/12) 按依赖顺序推进, 每轮更新本表。
6. W30 任务3: 持久化 agent_jobs 投影/取消/租约 — ✅ 已完成: storage/agent_jobs.py
   (协议+三后端, 原子租约, cancel 胜出租约) + tests/unit/test_agent_jobs.py 55 用例全绿 +
   MySQL 集成测试 MYSQL_URL 门控; 门禁 ruff/mypy strict/bandit/pytest 全绿 (证据见上表第 3 行与 M3 行)。
