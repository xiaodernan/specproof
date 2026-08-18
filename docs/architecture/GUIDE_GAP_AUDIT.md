# 工业化商业化终极指南 — 逐条差距审计与执行映射 (GUIDE_GAP_AUDIT)

审计日期: 2026-08-18 · 依据: docs/工业化商业化终极开发指南.md (727 行, 已逐条通读)
格式: 每条要求 → 现状 (证据) → 差距 → 行动 (车道/轮次)。持续更新, 数字来自真实运行。

## A. §14 首批 15 任务逐条审计

| # | 任务 | 现状 | 差距/行动 |
|---|---|---|---|
| 1 | domain-model.md 冻结领域对象 | ✗ 无 | 本轮建 docs/architecture/domain-model.md |
| 2 | 统一 request_id/trace_id/错误码/审计 Envelope | ✅ 完成 (P 车道): request_id (J/W14) + trace_id (observability) + api/errors.py 稳定错误码表 (AUTH_REQUIRED/TENANT_FORBIDDEN/QUOTA_EXCEEDED/JOB_NOT_FOUND/PROVIDER_UNAVAILABLE/EVIDENCE_UNVERIFIED/RATE_LIMITED/PAYLOAD_TOO_LARGE/VALIDATION_FAILED/INTERNAL + STATE_CONFLICT(409)); 全部错误响应 = {detail(原文保留), error:{code,message,request_id}, schema_version:1} (api/server.py 全局 exception handler; middleware 413 直发 envelope) | 已完成+证据: tests/unit/test_api_errors.py 15 用例全绿 + test_api_jobs/test_web_api/test_webhook_endpoint/test_middleware/test_dashboard_api 83 用例全绿 (detail 兼容) + ruff/mypy/bandit 全绿 |
| 3 | 全部 API tenant scope 设计 | 部分: CP 有 tenant (TenantController/JobView 租户过滤), Python API 单租户默认 | 需 tenant_id 注入设计文档 + 迁移 (阶段1) |
| 4 | OpenAPI schema diff 门禁 + 事件 Envelope 合同测试 | ✅ 完成 (P 车道): scripts/openapi_diff.py (added/removed/changed 端点+响应码, --allow/--update) + CI job openapi-schema-diff + docs/openapi/baseline.json (16 paths, OpenAPI 3.1.0, 已入库待提交); contracts/events.py build_envelope/payload_digest (§3.4 12 字段, uuid4hex event_id, 密钥脱敏, 确定性 sha256 digest) + storage/outbox_relay.py 平铺兼容 (老字段不变, 新增 schema_version/payload_digest/idempotency_key 等) | 已完成+证据: openapi_diff 实测 (基线生成 exit 0 → 无变更 exit 0 → 篡改基线 exit 1 且 --allow 豁免 exit 0) + tests/contract/test_event_envelope.py 12 用例全绿 + tests/unit/test_outbox.py 全绿 (wire 兼容) |
| 5 | Playwright 前端场景 (向导/详情/权限/降级) | ✗ (无 e2e) | 阶段2 (R 车道, 需 node playwright) |
| 6 | Contract immutable version/approval/checker version/lineage | 部分: registry 有审批/版本/spec_digest; lineage (W13) 已有 DAG | 补 checker_version 字段 + 不可变版本语义 (阶段2) |
| 7 | 证书/Capsule/Replay 走对象元数据查询而非路径推断 | 部分: capsule 用 basename 防穿越 + PK 校验; 证书读 reports 目录 | 对象元数据表 + 查询 (阶段2) |
| 8 | Worker 取消检查/租约指标/阶段耗时/异常分类 | 部分: 取消有 (job 状态机 + cancel), 阶段耗时指标 (C/W14 直方图) | 取消检查点补 Maven 前后/LLM 前 (阶段4); 租约指标 (阶段0) |
| 9 | Provider 每租户预算/模型路由/调用摘要/成本账本 | 部分: TokenBudget (全局, W13), 调用摘要 (llm_usage), KV 缓存字段 | 租户级预算 + usage_ledger 表 (阶段1/6) |
| 10 | 执行适配器接口 (ExecutionAdapter) + 兼容矩阵 | ✅ Q 车道已落地: experiments/adapters.py (Protocol 五方法 + registry + JavaMavenAdapter 声明镜像 digest/工具链/离线策略/已知限制), run_differential/generate_counterexamples 已改经适配器执行 (行为逐参数保持), 矩阵 docs/architecture/EXECUTION_COMPATIBILITY.md; Gradle/Node/Python/Go = 规划 (detect 抛 AdapterNotImplemented) | 保持: 每季度重跑兼容矩阵; 阶段4 逐步实现其余适配器并实测后改"已支持" |
| 11 | 跨租户/路径穿越/Webhook 重放/注入/沙箱边界安全测试 | 部分: 路径穿越 (capsule/replay), 注入 (24 矩阵), 沙箱 (15), webhook 验签有 | 补跨租户+重放测试 (阶段1 出口) |
| 12 | 金案例扩展计划拆成案例表 (expected evidence 先行) | 部分: 100 案例 (P6_CASES 数据表 + ground-truth 含 evidence) | 200 案例路线表 (阶段4) |
| 13 | httpx/Starlette TestClient 弃用警告处理 | ✗ (1 警告仍在) | 本轮: 处理并记录 (见 §D) |
| 14 | 数据保留/删除/导出/备份恢复操作手册 + 文档演练 | 部分: RUNBOOK 有备份章节 | 补删除/导出/保留策略 (阶段5) |
| 15 | 代码/文档持续区分 已实现/本地验证/需真实基础设施/规划中 | 部分: 各报告有实测标注惯例 | 制度化: LEVEL_ASSESSMENT + STACK_INVENTORY 已立, 每轮更新 |

## B. §12 八阶段现状映射

| 阶段 | 现状 | 差距 |
|---|---|---|
| 0 基线冻结 | 部分 (门禁全绿/文档多) | 依赖锁定 (uv/requirements lock), 事件清单, 数据字典 |
| 1 身份多租户 | 部分 (CP tenant/user 实体+REST) | OIDC/SAML, RBAC 权限矩阵, Python 侧 tenant scope, 邀请/Token 管理 |
| 2 完整工作流前端 | 部分 (9 页验证控制台) | Agent 工作台 ~20 路由 (W31 车道在途: 任务向导/计划审阅/SSE 工具流/审批/结构化 Diff); 其余: 向导/批量/通知中心/移动端/错误边界 |
| 3 集成与策略 | 部分 (GitHub App webhook/checks/评论/fix) | GitLab/Gerrit, Policy DSL, 豁免流, 分支保护建议 |
| 4 验证深度生态 | 部分 (mvn+沙箱+变异+状态快照) | Gradle/Node/Python/Go 适配器, 状态机测试, 反例最小化, +100 案例 |
| 5 证书合规私有化 | 部分 (Ed25519+血缘+密钥策略) | KMS/HSM, 撤销, 对象加密, 私有 Provider/镜像, 恢复演练 |
| 6 计费运营 | ✗ (成本账本仅内存) | Plan/Subscription/Ledger/Invoice 全套 |
| 7 SpecCraft 生产闭环 | 大幅推进: Schema+工具注册表+规则摄取+stale 保护 ✅ (W33, R 车道 102 测试+236 回归); 门禁组合+并行只读子代理 (W34 在途); 变更预览/人工批准 (W31 在途); Job 持久化/租约 (W30 在途) | craft→verify 强制闭环 (accept) — 等 W34 门禁组合完成后接线; 账单化 (阶段6) |
| 8 平台生态 | 部分 (MCP 服务端) | 插件市场, MCP 客户端, 通知连接器, 行业规则包 |

## C. §15 发布验收清单映射

代码构建: ✅ 大部分 (ruff/mypy/bandit/frontend build 全绿; OpenAPI diff 门禁 ✅ W28 实测: 基线生成 0 → 无变更 0 → 篡改 1 → --allow 豁免 0; 依赖锁定未做; 迁移前向/回滚测试未做)。
功能证据: ✅ 大部分 (契约审批/Job 全态/Finding 反查/Capsule 重放/证书验证; UNVERIFIED 政策已固化)。
安全治理: ✅ 大部分 (fail-closed/验签/限流/路径校验/脱敏/沙箱 12 项/审计)。
运营商业: 部分 (SLO 面板+告警; 套餐/账本/恢复演练未做)。

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
8. 在途车道: W30 Job 持久化/租约 (storage/agent_jobs.py) · W31 Agent 工作台 20 路由 ·
   W32 评测集 50+20+10+10 · W34 门禁组合+并行只读子代理 — 完成后回填本表。
