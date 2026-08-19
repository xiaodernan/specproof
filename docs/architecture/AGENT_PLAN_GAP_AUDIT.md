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
| 7 | 测试/构建/类型/安全/SpecProof 自校验门禁 | ✅ 已完成 (W34 车道 2026-08-19): craft/gates.py GatePipeline 五道门 GATE_ORDER = run_test→run_build→run_typecheck→security→self_verify; 每门统一结果契约 {gate,status:passed|failed|skipped|error,note,findings,duration_ms}; 组合语义 FAIL>SKIPPED>PASS (镜像仓库 FAIL>PASS>UNVERIFIED), error 为最差且诚实注记; 可 grep 汇总行 GATES: task=... overall=... <gate>=<status>... duration_ms=...; 无测试/无构建配置/无类型对象诚实 skipped 绝不伪造通过 (run_test 无检测→skip+note; run_build 按生态 mvn/gradle/compileall; run_typecheck=mypy 变更 .py, Java 诚实跳过; security=scanner 过滤变更文件+CANARY_MARKER, CRITICAL/HIGH 阻断 MEDIUM/LOW 记录; self_verify 原样复用 craft/verify.py); tests/unit/test_craft_gates.py 41 测试 | 完成; 接线: CraftLoop._finish/CLI 调 pipeline.run(bundle) (留给 M5 accept 车道, 设计 docs/architecture/CRAFT_ACCEPT_DESIGN.md) |
| 8 | Web 任务向导/计划审阅/实时工具流/审批/Diff | ✅ 已完成 (U 车道 2026-08-18): api/routes/agent_console.py 8 端点 (POST /agent/jobs · GET list/detail · cancel · approve(plan/step/gate) · approvals · events SSE(Last-Event-ID 重放+终态 done 自动关闭) · 结构化 diff(unified/split 行号 hunks); 持久化走 storage/agent_jobs.py (W30 投影/租约/cancel; SPECPROOF_AGENT_JOBS_URL 选后端), 控制台态(元数据/事件/审批/bundle)进程内 _ConsoleState; 状态映射 PLANNING/AWAITING_APPROVAL→pending, EXECUTING→running, COMPLETED→succeeded; apps/web Agent 工作台 20 路由 (4 步任务向导/状态时间线/计划+步骤审阅/实时工具流/事件日志/编辑/门禁/统一+分栏 Diff/任务审批/审批收件箱+详情/设置); tests/unit/test_agent_console_api.py 27 测试 (TestClient 无 Docker); 前端 vitest 26 测试 (6 文件); 门禁 ruff/mypy strict/bandit/pytest + npm build/typecheck/test 全绿 | 完成; 后续: 真 Worker 事件接线 (craft loop 与 _ConsoleState 对接) |
| 9 | 只读 Explorer/Test/Security 并行 (不共写同文件) | ✅ 已完成 (W34 车道 2026-08-19): craft/agents.py ParallelRunner (asyncio.gather 真并发, max_agents=8); 派发层只读强制 — ReadonlyToolSurface.call 拒绝任何注册 risk≠readonly 工具 (apply_patch/create_file/run_* 结构性不可能) + 每代理 allowlist; validate() 启动前 fail-closed 拒绝: 非只读/未知工具、重名、N>上限、空集合、写集合重叠 (路径归一化); 每代理 wall-clock 超时 (asyncio.wait_for→timed_out) + 预算经 AgentContext.budget 透传 + 单代理崩溃隔离 (error outcome, 其余继续); 单测实证: 双 0.2s 慢代理墙钟 <0.35s (真重叠 < 串行和 0.4s) / 非只读工具 allowlist 启动前拒 / 重叠写集拒·不相交收 / 崩溃隔离 / 超时隔离+预算透传+超额记录; tests/unit/test_craft_agents.py 21 测试 | 完成; 后续: 与 GatePipeline 组合成并行侦察→门禁工作流; LLM 执行器接线 (注入式 callable, 已留) |
| 10 | 50 代码任务+20 对抗+10 恢复+10 审批 评测集 | ✅ 本轮完成 (V 车道): 90 任务全部落盘 bench/ (50 代码含 legacy 10 + 20 对抗 + 10 断点恢复 + 10 危险动作审批); scripts/bench_gen_tasks.py 数据表驱动生成 (幂等, --check 无漂移, 生成时经 craft spec schema/Plan/compile 校验); 运行器 --category {all,code,adversarial,recovery,approval,legacy} 分栏汇总; 确定性全量实测 docs/eval/agent-task-suite.md: 代码 98.0% (49/50), 陷阱拦截 21/21, 对抗拦截 20/20, 恢复 10/10, 审批拒绝 10/10 违规 0; legacy 输出与旧 craft-microbench.md 兼容 (90.0% 复现) | 后续: 审批服务上线后升级审批口径 (APPROVAL_REFUSED → 真实审批门两分支); LLM 档待测 (--llm 需 LLM_API_KEY, 无 key 诚实拒绝) |
| 11 | OIDC/租户/RBAC/审计/配额 | ✅ 身份/RBAC/OIDC 完成 (W37): sp_* 本地 Token (bcrypt+HMAC, 展示一次) + OIDC JWKS RS256 统一 principal {user_id,tenant_id,roles,scopes}; 4 角色×4 资源 RBAC 矩阵; repository 层 scoped SQL 租户过滤; 跨租户 404+审计 (attempted_tenant); 迁移 0005 成对 up/down; 前端登录/租户切换/用户+Token 管理页; 168 测试 (兼容 124+新增 44) 队长复跑全绿 + 前端 typecheck/31/build 全绿; 详情 docs/api/auth/README.md + MULTI_TENANT_DESIGN.md | 配额 (usage_ledger) → 阶段 6 (BILLING_DESIGN.md 设计定稿); SAML 阶段2+; live-MySQL 迁移验证 (集成车道) |
| 12 | GitHub/GitLab PR 自动化, IDE, MCP 客户端, 计费, 私有化 | 计费 ✅ (W40: 账本/配额/发票, 见工业化阶段6); GitHub App+fix PR ✅, MCP 服务端 ✅ | IDE 插件 (M6 残留); MCP 客户端; GitLab; 私有化 (阶段5, 本地态后议) |

## B. M0-M11 里程碑现状映射

| 里程碑 | 现状 | 差距 |
|---|---|---|
| M0 现状冻结 | ✅ 大部分 (craft 基线/10 任务基准/边界文档) | 统一 Schema ✅ (任务1, craft/schemas.py) |
| M1 工具协议执行器 | 部分 (editor/executor 白名单) | 注册表+信封 ✅ (任务2); 批准服务持久化待 M4 |
| M2 仓库理解 | 部分 (BM25+向量+图谱) | 规则摄取 ✅ (任务4, craft/rules.py); 检索消融 S/L 车道在途 |
| M3 稳定计划循环 | ✅ 大部分 (DAG/checkpoint/预算/STUCK/暂停恢复) | MySQL 投影 ✅ (任务3, storage/agent_jobs.py, 55 测试) |
| M4 代码编辑跨语言 | 部分 (唯一匹配编辑; Q 在做执行适配器) | stale 保护 ✅ (任务6, digest+STALE_CONTEXT+改动分类); AST 编辑/结构化 Diff 待 |
| M5 SpecProof 闭环 | ✅ accept 强制闭环已实现 (W35, craft/accept.py 775 行: 工作区守卫→五道门禁 FAIL⇒STOP+回滚→真实 agent-graph 验证→VERIFIED⇒Merge Certificate+lineage+Ed25519 (fail-closed)→其余回滚+拒绝; 幂等键; loop 接线 report.gates; CLI craft accept exit 0/1/2; 15+7 新测试, craft 扫 360 绿, 队长复跑全绿; E2E 真实跑: 门禁 5/5 过→真实 graph 判定→BLOCKED+回滚+拒绝 实测; VERIFIED 路径需 Java demo+maven 手动步骤已留) | VERIFIED 路径真实 E2E (Spring demo, 手动步骤已文档化); 终态投影 ✅ (W35.1 attach_accept_result: 终态限定+首写胜出幂等+三后端一致+旧库自动补列; 11 新测试, 104 定向绿, 队长复跑; CLI 实测 BLOCKED 投影落库) |
| M6 Web+IDE | ✅ Agent 工作台 20 路由 (任务8, W31: 8 端点 + 20 前端路由 + 27 API 测试 + vitest 26; npm build/typecheck/test 全绿, 队长复跑后端 107 全绿) | IDE 插件 (VSCode/JetBrains); 真实 Worker 事件接线 (craft loop ↔ _ConsoleState, 属 W35 车道) |
| M7 并行子代理 | ✅ (任务9, craft/agents.py ParallelRunner 只读并行+写集重叠 fail-closed+真并发实证) | LLM 执行器接线; 与门禁组合工作流 |
| M8-M11 企业/模型/生态/评测 | 部分 (provider 治理 W13, 微基准) | 工业化指南阶段 1/6/7 对齐 |

## C. §3.3 目标指标当前值

| 指标 | 目标 | 实测 |
|---|---|---|
| 10 微基准完成率 | ≥90% | 90.0% (确定性+LLM 双档实测; 本轮重跑 90.0% 复现) ✅ |
| 陷阱拦截率 | 100% | 100% (21/21: legacy 陷阱 1 + 对抗任务 20) ✅ |
| 50 中型任务完成率 | ≥80% | 98.0% (49/50, 确定性档: 40 新增代码任务 100% + legacy 9/10; trap task-10 按口径拦截) ✅ |
| 对抗任务拦截率 | 100% | 100% (20/20 INTERCEPTED: 误导 Issue 5 + 注入 5 + 过时测试 5 + 隐藏禁止变更 5) ✅ |
| 断点恢复任务恢复率 | 100% | 100% (10/10 RECOVERED, craft resume 续跑 + judge 幂等检查) ✅ |
| 危险动作误执行率 | 0 | 0 (10/10 APPROVAL_REFUSED: 危险动作零执行 + 审批门拒绝记录在案, 违规 0) ✅ |
| 编辑成功率 / stale 覆盖 0 | 98% / 0 | 未量化 (R 车道补) |
| Worker 恢复率 | ≥99.9% | 未量化 (评测集断点恢复 ≠ 生产 Worker 恢复率) |
| 预算超限进入终态 | 100% | ✅ (M1 实测 FAILED/EXPIRED/STUCK 语义) |

## D. 本轮执行

1. 本审计文档落盘并提交。
2. S 车道: 4 语言最小符号索引 + 30 条检索基准 (任务5) — ✅ 已完成, 实测数字见上表与 docs/eval/retrieval-bench.md。
3. V 车道: 评测集扩展 50+20+10+10 (任务10, bench 数据面) — ✅ 已完成: 90 任务落盘
   + 数据表生成器 (scripts/bench_gen_tasks.py --check 无漂移) + 运行器 --category 分栏
   + 确定性全量实测 docs/eval/agent-task-suite.md (exit 0, 全口径 PASS); 门禁
   ruff/mypy strict/bandit 全绿; LLM 档待测。
4. R 车道: craft/schemas.py + tools.py 注册表 + rules.py 摄取 + editor stale-digest
   (任务 1/2/4/6) — ✅ 已完成: 4 个新模块 + editor/loop/llm 接线, 新增 102 测试全绿,
   既有 craft 134 测试回归全绿, ruff/mypy/bandit 全绿 (详见上表 1/2/4/6 行证据)。
5. 其余 (8/9/11/12) 按依赖顺序推进, 每轮更新本表。
6. W30 任务3: 持久化 agent_jobs 投影/取消/租约 — ✅ 已完成: storage/agent_jobs.py
   (协议+三后端, 原子租约, cancel 胜出租约) + tests/unit/test_agent_jobs.py 55 用例全绿 +
   MySQL 集成测试 MYSQL_URL 门控; 门禁 ruff/mypy strict/bandit/pytest 全绿 (证据见上表第 3 行与 M3 行)。
7. W34 任务 7+9: 分层验收门禁组合 + 并行只读子代理 — ✅ 已完成: craft/gates.py
   (五道门, FAIL>SKIPPED>PASS, 诚实 skipped) + craft/agents.py (只读并行, 写集重叠
   fail-closed, 真并发实证); 新增 62 测试 (41+21), 目标套件 80 全绿, -k craft 338 passed;
   ruff/mypy strict/bandit 全绿 (队长复跑确认; 证据见上表 7/9 行与 M5/M7 行)。
