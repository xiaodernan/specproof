# 工业化商业化终极指南 — 逐条差距审计与执行映射 (GUIDE_GAP_AUDIT)

> 更新: 2026-08-20 最终复核

审计日期: 2026-08-18 · 依据: docs/工业化商业化终极开发指南.md (727 行, 已逐条通读)
格式: 每条要求 → 现状 (证据) → 差距 → 行动 (车道/轮次)。持续更新, 数字来自真实运行。

## A. §14 首批 15 任务逐条审计

| # | 任务 | 现状 | 差距/行动 |
|---|---|---|---|
| 1 | domain-model.md 冻结领域对象 | ✅ 完成: docs/architecture/domain-model.md 已落盘 (COMPLETION_MAP §3.1) | 已完成 |
| 2 | 统一 request_id/trace_id/错误码/审计 Envelope | ✅ 完成 (P 车道): request_id (J/W14) + trace_id (observability) + api/errors.py 稳定错误码表 (AUTH_REQUIRED/TENANT_FORBIDDEN/QUOTA_EXCEEDED/JOB_NOT_FOUND/PROVIDER_UNAVAILABLE/EVIDENCE_UNVERIFIED/RATE_LIMITED/PAYLOAD_TOO_LARGE/VALIDATION_FAILED/INTERNAL + STATE_CONFLICT(409)); 全部错误响应 = {detail(原文保留), error:{code,message,request_id}, schema_version:1} (api/server.py 全局 exception handler; middleware 413 直发 envelope) | 已完成+证据: tests/unit/test_api_errors.py 15 用例全绿 + test_api_jobs/test_web_api/test_webhook_endpoint/test_middleware/test_dashboard_api 83 用例全绿 (detail 兼容) + ruff/mypy/bandit 全绿 |
| 3 | 全部 API tenant scope 设计 | ✅ 完成 (W37): docs/architecture/MULTI_TENANT_DESIGN.md 定稿 + api/identity (principal/oidc/tokens/rbac) + repository 层 scoped SQL + 迁移 0005 (成对); 跨租户 404+审计 实测; 无 auth 配置时保持旧单租户行为 (兼容 124 测试全绿) | 每作业成本会计 ⏳ (账本/配额 ✅ W40; 计费路由 ✅ W101); /agent/* 租户中间件修复 ✅ (W110) |
| 4 | OpenAPI schema diff 门禁 + 事件 Envelope 合同测试 | ✅ 完成 (P 车道): scripts/openapi_diff.py (added/removed/changed 端点+响应码, --allow/--update) + CI job openapi-schema-diff + docs/openapi/baseline.json (16 paths, OpenAPI 3.1.0, 已入库待提交); contracts/events.py build_envelope/payload_digest (§3.4 12 字段, uuid4hex event_id, 密钥脱敏, 确定性 sha256 digest) + storage/outbox_relay.py 平铺兼容 (老字段不变, 新增 schema_version/payload_digest/idempotency_key 等) | 已完成+证据: openapi_diff 实测 (基线生成 exit 0 → 无变更 exit 0 → 篡改基线 exit 1 且 --allow 豁免 exit 0) + tests/contract/test_event_envelope.py 12 用例全绿 + tests/unit/test_outbox.py 全绿 (wire 兼容) |
| 5 | Playwright 前端场景 (向导/详情/权限/降级) | ✅ 完成 (W39): Playwright 9 用例全绿 — 向导/详情/权限/降级 四场景, 真实 Vite+API fixture, 无 DOM mock (已合流 1adfa98) | — |
| 6 | Contract immutable version/approval/checker version/lineage | ✅ 完成 (W38, 0b13de4): ContractRecord 带 checker_version (checkers 声明 CHECKER_VERSION 2.0.0/1.0.0/1.0.0, 编译时盖章); registry 追加式 propose + CAS approve/reject 绑定精确 (id,version), 内容变更抛 ContractVersionError; 迁移 0006 复合主键 (id,version) SQL 层禁就地改; 血缘节点 contract:<id>@v<N> 精确版本引用, legacy 无版本上下文逐字节兼容 (19 既有测试全绿) | 结构化 Diff/AST 编辑 (M4); forbidden_changes 持久化 (预研) |
| 7 | 证书/Capsule/Replay 走对象元数据查询而非路径推断 | ✅ 完成 (W38): storage/object_metadata.py 三后端 (InMemory/SQLite/MySQL) — {object_id uuid4hex, kind: certificate|capsule|replay_report, payload_sha256, job_id, contract_ids, path_hint}; by_job/by_kind/by_digest/by_contract 查询; verify/replay 经 resolve_object (digest 校验) 优先, legacy 路径回退兼容 (测试证明空库+旧路径可用) | rejection notice 暂不落元数据 (kind 集按规格); api/web + MCP 路径迁移 (车道禁区, 后续) |
| 8 | Worker 取消检查/租约指标/阶段耗时/异常分类 | ✅ 完成 (W85B+W106): node 级取消检查点 (Maven 前后/LLM 前) + classify_job_error {system|repo|provider|policy|unknown} | 租约指标 (阶段0) ⏳ |
| 9 | Provider 每租户预算/模型路由/调用摘要/成本账本 | ✅ 大部分 (W40): 租户级配额预检 (hard-stop/soft-overage/80% 软限额通知) + usage_ledger (event_id 幂等, LLM 四类 token 计量) + invoices 对账; TokenBudget 全局预算与调用摘要已有 | 模型路由 (M9); 每作业成本会计 ⏳; LLM 中途配额强制 (预检覆盖作业级, LLM 超额计入发票) |
| 10 | 执行适配器接口 (ExecutionAdapter) + 兼容矩阵 | ✅ Q 车道已落地: experiments/adapters.py (Protocol 五方法 + registry + JavaMavenAdapter 声明镜像 digest/工具链/离线策略/已知限制), run_differential/generate_counterexamples 已改经适配器执行 (行为逐参数保持), 矩阵 docs/architecture/EXECUTION_COMPATIBILITY.md; Python 适配器 ✅ (W78/W105: experiments/adapters.py PythonAdapter local-first + experiments/minimize.py ddmin); Gradle/Node/Go = 规划 (detect 抛 AdapterNotImplemented) | 保持: 每季度重跑兼容矩阵; 阶段4 逐步实现 Gradle/Node/Go 适配器并实测后改"已支持" |
| 11 | 跨租户/路径穿越/Webhook 重放/注入/沙箱边界安全测试 | ✅ 跨租户完成 (W37) + 租户中间件修复 ✅ (W110): A 租户读 B 租户 job → 404 + audit(attempted_tenant); tenant_id 仅取 principal (参数覆盖无效, 已测); RBAC 矩阵 4×4 断言; OIDC 签名/过期/错 issuer/错 aud 用例; 路径穿越/注入/沙箱/webhook 验签已有 | Webhook 重放测试 (阶段1 出口补) |
| 12 | 金案例扩展计划拆成案例表 (expected evidence 先行) | ✅ 100 案例全绿: Recall/Precision/F1 = 100.0% (63/63, FP 0) — 五 chunk 修复后全重跑 (docs/eval/eval-c1-rerun.results.json / eval-c2-rerun / eval-c3-rerun / eval-c4-rerun / eval-rem3-rerun); 总表 docs/eval/eval-100-segments.md; 段1 六案例 25/33/29 → 100/100/100 (docs/eval/eval-seg1-fixed.results.json) | 200 案例路线表 (阶段4) |
| 13 | httpx/Starlette TestClient 弃用警告处理 | ✅ 已消解 (2026-08-19): 多次定向+全量运行 (15/71/168/195/990/1086 用例) 均无警告汇总 — 上游依赖演进后该弃用警告不再出现; 若未来复现, 既定决策 = pytest filterwarnings 记录并注明"fastapi.testclient 上游弃用, 待 fastapi 升级移除", 不静默吞其他警告 | 无需行动 (持续观察) |
| 14 | 数据保留/删除/导出/备份恢复操作手册 + 文档演练 | 部分: RUNBOOK 有备份章节 + W89 演练已执行 (docs/operations/DRILLS.md: Drill1 真实 worker kill 6 检查点 → 9.09s resume → BLOCKED=control; Drill2 provider outage 真实 (3× APITimeoutError, breaker open, degrade_reasons 记录); Drill4 outbox 崩溃 → exactly-once; Drill3 安全桌面推演 9 可执行/4 需开发) | 补删除/导出/保留策略 (阶段5); 主机备份工具 ⏳ (DRILLS 4 需开发) |
| 15 | 代码/文档持续区分 已实现/本地验证/需真实基础设施/规划中 | 部分: 各报告有实测标注惯例 | 制度化: LEVEL_ASSESSMENT + STACK_INVENTORY 已立, 每轮更新 |

## B. §12 八阶段现状映射

| 阶段 | 现状 | 差距 |
|---|---|---|
| 0 基线冻结 | 部分 (门禁全绿/文档多) | Python 依赖锁 snapshot ⏳ (DEPENDENCY_LOCK.md 治理文档 ✅ W103); 事件清单 (数据字典 ✅ W103 DATA_DICTIONARY.md) |
| 1 身份多租户 | ✅ 核心完成 (W37): OIDC JWKS RS256 + sp_* 本地 Token; RBAC 4×4 矩阵; Python 侧 tenant scope (repository scoped SQL); 前端登录/租户切换/用户与 Token 管理; 迁移 0005 | SAML (阶段2+); OIDC logout ⏳ (DRILLS 4 需开发); 邀请流; live-MySQL 迁移 up/down 实测 |
| 2 完整工作流前端 | ✅ Agent 工作台 20 路由 (W31 已交付: 任务向导/计划与步骤审阅/SSE 实时工具流/事件/编辑/门禁/统一+分栏 Diff/审批收件箱/设置; 8 API 端点走 agent_jobs 投影) + Playwright e2e 9 用例全绿 (W39) | 批量操作/通知中心/移动端/错误边界 |
| 3 集成与策略 | 部分 (GitHub App webhook/checks/评论/fix; Policy DSL + 豁免流 ✅ W102: agent/policy_dsl.py + agent/waiver.py, 42 测试) | GitLab/Gerrit, 分支保护建议 |
| 4 验证深度生态 | 部分 (mvn+沙箱+变异+状态快照; Python 适配器 ✅ W78/W105 + ddmin 反例最小化 ✅ W105) | Gradle/Node/Go 适配器 ⏳, 状态机测试 ⏳, 200 案例路线表 ⏳ (反例最小化 ✅ W105; 100 案例 ✅ 100.0%) |
| 5 证书合规私有化 | 部分 (Ed25519+血缘+密钥策略; 恢复演练 ✅ W89 DRILLS) | KMS/HSM ⏳, 证书撤销 ⏳ (DRILLS 4 需开发), 对象加密 ⏳, 私有 Provider/镜像 ⏳ |
| 6 计费运营 | ✅ 后端完成 (W40): plans/subscriptions/usage_ledger/invoices 三后端 (0007 迁移+down 对); event_id 幂等账本; 计量钩子 (验证作业/Agent 作业/LLM 四类 token, 默认关零行为变化); 作业创建配额预检→QUOTA_EXCEEDED(429)+80% 软限额通知; /api/v1/billing RBAC+跨租户隔离; 发票 total=Σline_items 对账; 195 测试 (兼容 168+新增 27) 队长复跑全绿; 计费路由 ✅ (W101 前端) | 每作业成本会计 ⏳; 月账单 cron; 发票签发流; LLM 中途配额强制 |
| 7 SpecCraft 生产闭环 | 大幅推进: Schema+工具注册表+规则摄取+stale 保护 ✅ (W33, R 车道 102 测试+236 回归); Job 持久化/租约/取消 ✅ (W30, 三后端 55 单元+65 安全, 队长复跑全绿); 门禁组合+并行只读子代理 ✅ (W34); 变更预览/人工批准 ✅ (W31) | craft→verify 强制闭环 (accept) ✅ 已接线 (W35 craft/accept.py); 账单化 ✅ (W40 后端 + W101 计费路由) |
| 8 平台生态 | 部分 (MCP 服务端) | 插件市场 ⏳, MCP 客户端 ⏳, 通知连接器 ⏳ (notify wiring — DRILLS 4 需开发), 行业规则包 ⏳ |

## C. §15 发布验收清单映射

代码构建: ✅ 大部分 (unit 2369 passed/3 skipped, 2026-08-20 实测; ruff 全仓绿/mypy 绿/bandit Medium+=0/密钥泄漏 0; frontend build 全绿; OpenAPI diff 门禁 ✅ W28 实测: 基线生成 0 → 无变更 0 → 篡改 1 → --allow 豁免 0; Python 依赖锁 snapshot 未做; 迁移前向/回滚测试未做)。
功能证据: ✅ 大部分 (契约审批/Job 全态/Finding 反查/Capsule 重放 25/25=100.0% (Go/No-Go #4 PASS; docs/eval/replay-results.md 六轮 28.57→35.71→42.86→82.14→92.0→100.0%)/证书验证; UNVERIFIED 政策已固化)。
安全治理: ✅ 大部分 (fail-closed/验签/限流/路径校验/脱敏/沙箱 12 项/审计; 密钥泄漏 0 + bandit Medium+=0)。
运营商业: 部分 (套餐/账本 ✅ W40 后端 + 计费路由 ✅ W101; 恢复演练 ✅ W89 DRILLS; Grafana/SLO 面板 ⏳; 每作业成本会计 ⏳)。

## D. 本轮执行 (任务 1 + 13 + 首批)

1. 建 docs/architecture/domain-model.md (任务 1)。
2. httpx 弃用警告 (任务 13): 定位来源 (fastapi.testclient 上游) → 决策: 在 pytest 配置
   filterwarnings 记录并注明"上游弃用, 待 fastapi 版本升级后移除", 或在 dev 依赖换 httpx2
   (若可用) — 实测决定, 不静默吞掉其他警告。
3. P 车道派发: 稳定错误码表 + OpenAPI diff 门禁 + 事件 Envelope 合同测试 (任务 2/4)。
4. Q 车道 (任务 10) ✅ 完成: ExecutionAdapter 协议 + Java/Maven 适配器 + 兼容矩阵
   (experiments/adapters.py + docs/architecture/EXECUTION_COMPATIBILITY.md; 两个节点已接线,
   tests/unit/test_adapters.py 27 例全绿)。
5. P 车道 (任务 2/4) ✅ 完成 (W28): 稳定错误码表 + OpenAPI diff 门禁 + 事件信封
   (api/errors.py + scripts/openapi_diff.py + contracts/events.py; 27 新测试, unit+contract
   655 passed; 假密钥字面量拼接纪律 → 安全门禁 31/31)。
6. S 车道 ✅ 完成 (W29): 四语言符号索引 + 30 查询检索基准 (retrieval/symbols.py 等;
   15 新测试; ES 实测 BM25 82.2% / symbol-index 75.6% @1.3ms, 见 docs/eval/retrieval-bench.md)。
7. R 车道 (任务 1/2/4/6) ✅ 完成 (W33): craft 核心工程底座 (schemas/tools/rules/stale);
   102 新测试, craft 全套 236 绿, ruff/mypy/bandit 全绿。
8. 已完成车道 (2026-08-20 回填): W30 Job 持久化/租约 ✅ (storage/agent_jobs.py, 55 用例) ·
   W31 Agent 工作台 20 路由 ✅ · W32 评测集 50+20+10+10 ✅ (90 任务落盘+确定性全量实测) ·
   W34 门禁组合+并行只读子代理 ✅ (五道门+只读并行, 62 测试) — 本表已回填。
