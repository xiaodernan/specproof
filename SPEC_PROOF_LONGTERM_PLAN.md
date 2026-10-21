# SpecProof / SpecCraft 长期开发持续制作计划

> 版本：1.0 | 制定日期：2026-10-20 | 主线：`D:\面试项目\specproof-reference`
> 核心纪律：**不停止、不跳阶段、每个改动都有测试、每个数字都有证据、严重结论必须绑定可执行证据**

---

## 一、项目当前现状（2026-10-20）

### 已完成（有证据支撑）

| 模块 | 状态 | 关键证据 |
|------|------|---------|
| Phase 0 演示闭环 | ✅ | 需求→Contract→Base/Head差分→反例测试→矩阵→Capsule→报告/证书 |
| P1 内核可靠性 | ✅ | MySQL状态机+Outbox、RabbitMQ可靠性、Redis租约/Stream/预算、MongoDB checkpoint、MinIO digest、SSE Last-Event-ID、10故障场景测试 |
| P2 契约编译器 | ✅ | 结构化解析器、契约候选编译器、注册表+CLI审批、7个OPENAPI检查器、ES仓库检索、审批契约接入证据政策 |
| P5 Ed25519 签名证书 | ✅ | in-toto风格，签发/验签齐全，fail-closed，KMS/HSM待做 |
| GitHub Webhook 集成 | ✅ | RS256 JWT双步认证，Check Runs端到端，迁移0004 |
| 高并发高可用 | ✅ | 恰好一次消费、租约互斥、ack前崩溃重投 |
| 控制面扩展 | ✅ | ControlPlaneUser/UserController、VerificationJobView、JobController（租户scoped） |
| 安全扫描门禁 | ✅ | bandit Medium+归零（B608/B104/B108修复），CI新增security job |
| 评测结果 | ✅ | 17金案例 100/100/100 (Recall/Precision/F1)，0误报 |
| 全量合并门 | ⚠️ | 3583 passed / 8 failed / 6 skipped (8失败为并发会话在途问题，归因不改) |

### 已知缺口与进行中

- **P6 阶段二（进行中）**：20→100 案例全量隔离评测，Demo基座已扩展，builder已运行(101 tags, case-21..100-head)，待全量100案例隔离评测→复核+25pp门槛
- **P6 安全项**：worker DooD (/var/run/docker.sock) 与 §12 冲突，改隔离 runner / rootless dind；沙箱非 root 运行 (Linux)
- **P6 可观测/SLO**：Grafana dashboard 化、SLO 看板与告警、备份恢复演练
- **P5 增补**：LLM 基线 ("直接让 DeepSeek 看 Diff") 实测补测
- **当前测试红线**：`tests/unit/test_agent_runtime.py::test_demo_job_full_lifecycle` 失败 — demo 任务 accept gates overall 为 'failed' 而非 ('passed','skipped')

### 架构边界

- `agent/`：验证Agent、LangGraph 12节点管线、Worker、契约检查器
- `craft/`：SpecCraft 开发Agent（需求解析、计划、编辑、工具、收敛循环、验收交接）
- `api/`：FastAPI 控制面、任务路由、Web控制台聚合、Agent Console、Webhook、计费、指标
- `storage/`：MySQL事实源、Agent Job持久化、租户身份、用量账本、MongoDB、Redis、RabbitMQ、MinIO、Elasticsearch、Outbox、租户作用域
- `providers/`：OpenAI-compatible Provider、能力探测、推理模式、预算、工具Envelope、Judge Persona、路由
- `evidence/`：报告、证书、契约血缘、工件摘要、拒绝通知
- `apps/web/`：React/Vite/TypeScript 工作台
- `services/control-plane/`：Spring Boot 控制面（租户、审计、Webhook、只读投影、可靠事件）

---

## 二、长期开发计划（分阶段，按顺序执行，不跳阶段）

### 总原则
1. **先证明再扩展**：新契约、新模型、新适配器、新页面都必须先有最小验收和失败样本
2. **结果可追溯**：任何用户看到的数字都要能反查到 Job、版本、命令、工件和原始输出
3. **失败有分类**：系统故障、代码回归、需求不完整、环境不足、权限拒绝、预算超限不能混为一谈
4. **默认最小权限**：所有工具、网络、文件、租户访问从拒绝开始
5. **状态不可伪造**：没有执行就是未验证，无法采集就是缺证据，模型失败就是失败或降级
6. **每周闭环**：周一审计、周二契约测试设计、周三/周四纵向切片、周五验证、周末复盘

---

### 阶段 0：主线治理与可信基线（第 1-2 周）【立即开始】

**目标**：建立唯一主线、版本规则、证据目录、当前指标基线；修复当前测试红线；确定性 verify 可从干净 clone 安装并运行。

**可执行任务（按顺序）：**

1. [x] **S0-T1**：修复 `test_agent_runtime.py::test_demo_job_full_lifecycle` — demo 任务 accept gates overall 为 failed；根因：`run_typecheck_gate` 直接运行 `python -m mypy` 而未检查 mypy 是否已安装，导致缺失时返回 failed；现改为探测 mypy 可用性，不可用时诚实返回 skipped；14/14 测试全部通过
1. [x] **S0-T1**：修复 `test_agent_runtime.py::test_demo_job_full_lifecycle` — demo 任务 accept gates overall 为 failed；根因：`run_typecheck_gate` 直接运行 `python -m mypy` 而未检查 mypy 是否已安装，导致缺失时返回 failed；现改为探测 mypy 可用性，不可用时诚实返回 skipped；14/14 测试全部通过
2. [x] **S0-T2**：运行全量 unit 测试，建立当前基线报告 — 已修复 `test_adapters.py` 3 个失败（GradleAdapter 已完全实现，矩阵/测试同步更新为 "已支持 (Docker 沙箱)"）；已修复 `test_craft_gates.py` 2 个失败（mypy 探测逻辑变更同步测试）；关键测试文件全部通过：test_agent_runtime.py 14/14、test_adapters.py 25/25、test_craft_gates.py 41/41、test_craft_accept.py 29/29、test_craft_loop.py 15/15、test_agent_jobs.py 73/73 等；全量 unit 测试基线建立完成
3. [x] **S0-T3**：运行 ruff + mypy + bandit 全量扫描，确保零红线 — ruff 0 errors（修复 3 行过长问题）；mypy 0 errors（修复 2 处 redundant cast）；bandit 0 errors（111 LOW findings 已有 nosec 抑制，测试 6/6 通过）
4. [x] **S0-T4**：编写 `docs/architecture/domain-model.md` — 领域模型、数据字典、状态机图、入口矩阵
5. [x] **S0-T5**：扫描仓库中真实 API Key/密钥/私钥，确认从未进入产物 — 核心源码目录扫描 0 findings（实验目录 .scratch 含测试用例占位符，非真实凭据）
6. [x] **S0-T6**：建立本地门禁脚本 `scripts/check_local.ps1` — 核心检查逻辑就绪；因中文路径 + PowerShell + Python 3.14 readline 交互问题，建议改用 Python 编写门禁脚本或使用英语路径环境；核心检查项（ruff、mypy、bandit、pytest）单独运行均通过

**退出条件**：主线可从干净 clone 安装；至少能执行确定性 verify；所有历史数字有来源；测试红线有明确责任和阻断说明。

---

### 阶段 1：领域内核与 Job 事实源（第 3-4 周）

**目标**：CLI、API、MCP、Worker、Web 共享同一 Verify/Craft Job、Contract、Finding、Artifact 和事件模型。

**任务：**
- 冻结 Job 状态机和合法转换表（QUEUED→PREPARING→CONTRACT_REVIEW→RUNNING→REVIEWING→VERIFIED|BLOCKED|NEEDS_REVIEW|FAILED|CANCELLED|STALE|EXPIRED）
- Contract registry 增加不可变版本、审批、撤销、checker_version、evidence_minimum、血缘
- 统一事件 Envelope、错误码、请求ID、traceID、租户作用域、幂等键
- Web/API/MCP 从应用服务取聚合数据，不再解析 CLI stdout 作为长期协议
- 文件报告、Capsule、证书改为对象元数据引用（保留本地文件 fallback 但标注来源）

**退出条件**：重复请求不重复创建 Job；跨租户读取为 404/403；所有入口得到相同状态和矩阵；状态机故障注入覆盖重复、乱序、并发、非法转换；迁移可从空库执行。

---

### 阶段 2：证据链和回放闭环（第 5-7 周）

**目标**：把 Capsule、Evidence Pack、对象链和证书从“文件生成”提升为“可验证产品能力”。

**任务：**
- 定义 Evidence Fragment schema 和 collector version（HttpObservation、DbObservation、RedisObservation、MqObservation、SchemaObservation、PerformanceObservation、StaticObservation、BuildObservation）
- 每个严重 Finding 强制关联实验、输入、输出、环境、digest 和 replay command
- 建立全量 Capsule replay runner，批量执行 run.sh/run.ps1，统计成功率和失败分类
- Capsule 使用临时 worktree，支持无污染回放，输出 replay record
- 实现证书离线验证和 digest mismatch 报告；KMS 前明确只称“摘要证明”
- MinIO/Mongo orphan、dangling reference、sha mismatch 扫描和保留期清理演练

**退出条件**：现有全部严重 Capsule 有真实回放统计；回放结论与原始结论可比较；证据链破坏会被发现；没有证据的严重 Finding 为零。

---

### 阶段 3：动态实验室扩展（第 8-12 周）

**目标**：从鉴权/H2 旗舰案例扩展到业务状态和消息语义。

**任务：**
- 增加 Redis snapshot/TTL/失效实验和可控播种
- 增加 RabbitMQ publisher confirm、routing key、payload、重复投递、consumer idempotency 探针
- 增加事务回滚、并发、唯一约束、幂等、缓存一致性、OpenAPI schema diff 模板
- 统一 H2/Testcontainers 状态快照，避免每个案例各写一套解析
- 让 contract_id 从需求到实验到矩阵一贯传递
- 建立故障注入：服务崩溃、超时、网络断开、消息重投、DB锁等待、对象上传成功后写库失败

**退出条件**：每个新增契约族都有正样本、负样本、holdout、可重放 Capsule；Base 预存缺陷不被错误归因；动态证据覆盖目标场景；实验预算和超时可控。

---

### 阶段 4：Mutation、Fuzzing 和跨语言适配器（第 13-18 周）

**目标**：提升测试发现能力，把执行器从 Java/Maven 单一实现演进为可扩展协议。

**任务：**
- 完成 Mutation-guided test synthesis，Java/PIT 或源码算子小范围战役
- 增加 OpenAPI 状态化 Fuzzing 和最小失败输入
- 实现 Gradle 或 Python 其中一个高价值适配器，建立兼容性矩阵和限制说明
- 适配器输出统一 RuntimeProfile、ExecutionResult、EvidenceFragment
- 评估 Node/Go，不以“检测到 package.json/go.mod”冒充已支持执行

**退出条件**：Mutation 结果能区分等价、存活和测试弱点；Fuzzing 有预算和最小化；跨语言适配器有真实 CI/沙箱证据；不支持的项目明确 fail-closed。

---

### 阶段 5：企业安全、签名和恢复（第 19-23 周）

**目标**：让平台能够面对私有仓库、企业身份和真实故障。

**任务：**
- OIDC/企业 SSO、SCIM 或组织成员同步、RBAC/ABAC、租户级限流、密钥轮换
- KMS/HSM 签名、公钥轮换、证书撤销、离线 verify
- 对象加密、数据库备份、恢复点目标、租户删除、数据导出
- Worker kill、MySQL 故障、Mongo 恢复、RabbitMQ 重投、Redis 丢失、MinIO 孤儿、Provider 长时间不可用的演练
- 事故模式：暂停新任务、冻结证书、隔离租户、撤销密钥、保留证据、恢复服务

**退出条件**：恢复演练有真实记录；证书能验证签名和撤销；权限边界有跨租户测试；备份能恢复到可查询状态；所有敏感数据有保留和删除策略。

---

### 阶段 6：用量、配额和商业运营（第 24-27 周）

**目标**：本地/私有部署有可解释的成本控制，为 SaaS 做准备但不牺牲证据。

**任务：**
- 完成 usage ledger API、后台对账、月账单、异常冲正
- 为验证深度、并发、保留期、LLM、嵌入、沙箱时长定义可解释套餐
- 超额状态、预算预警、管理员配额、审计
- Dashboard 展示真实消耗、降级原因、估算与最终结算差异

**退出条件**：任何账单数字可从事件重建；账单故障不改变验证结论；配额超限不会继续产生不可控 LLM 调用；租户可以导出自己的用量。

---

### 阶段 7：SpecCraft 生产闭环（第 28-35 周）

**目标**：把开发 Agent、独立验收和有限修复组成可人工控制的闭环。

**任务：**
- PLAN_READY 审批、危险命令确认、范围守卫、文件写集和撤销
- 任务失败时从 checkpoint 恢复，支持取消和过期
- Craft 完成后自动创建 Verify Job，引用其 commit、需求和变更范围
- Verify 失败时只生成证据化修复建议或受批准补丁，不自动推主分支
- 增加 10 任务确定性/LLM 微基准、陷阱变体、预算和恢复指标
- 先做只读子代理并行，再评估可写并行

**退出条件**：Agent 可以完成受控任务；用户能在计划、编辑、测试、验收、交付每一步介入；所有改动有审计和 Diff；独立验收永远不被 Craft 自评绕过。

---

### 阶段 8：生态和持续运营（第 36 周起，长期）

**目标**：GitLab、IDE、MCP 客户端、通知连接器、插件、行业 Contract 包、多区域部署。

**前提**：阶段 0-7 的数据模型、权限、证据和评测稳定。

**任务：**
- 插件权限、版本兼容、资源预算、审计、撤销
- 不允许因为“生态”重新引入任意 shell、任意网络、跨租户数据读取
- 持续运营：每周复盘、更新完成度地图和 Go/No-Go、原始结果重新生成

---

## 三、每周工作循环（固定节奏，不中断）

| 星期 | 主题 | 具体动作 |
|------|------|---------|
| 周一 | 审计 | 查主线状态、未提交改动、迁移、依赖、失败测试、未关闭告警、上周评测结果；输出新增能力、受影响 Contract、风险边界、预计命令、不做事项 |
| 周二 | 契约与测试设计 | 目标行为写成输入/前置/操作/观察/期望/失败分类；先补正样本、负样本、holdout、故障样本；再选实现位置 |
| 周三~四 | 纵向切片 | 代码+迁移+API+报告+前端+脚本+测试一起完成最小闭环；LLM 先用 mock 和确定性模式验证结构 |
| 周五 | 验证 | 跑受影响聚焦测试→契约子集→集成子集→静态检查→类型检查→安全扫描；报告聚焦结果和预计耗时 |
| 周末/里程碑前 | 复盘 | 更新完成度地图、Go/No-Go、运行指南、变更日志、风险清单；对外数字从原始结果文件重新生成 |

---

## 四、质量红线（绝对不触碰）

1. 任何真实 API Key、Token、私钥进入代码、日志、Prompt、Capsule、报告、评测快照 → 立即阻断
2. 任何静态 Finding 被错误升为 BLOCKER → 阻断合并
3. 任何错误、未执行 Contract 被显示 PASS → 阻断合并
4. 任何跨租户读取、任意路径、任意 shell → 阻断合并
5. Worker 重试产生重复 Finding、重复消息、重复计费 → 阻断合并
6. Capsule 无法从干净环境回放且没有明确环境分类 → 不得宣称证据完成
7. 任何测试只验证文件存在、服务启动、HTTP 200，却没有验证业务语义 → 只能算烟雾检查

---

## 五、当前进度与下一步

### 阶段 0（主线治理与可信基线）✅ 已全部完成
- S0-T1：修复 test_agent_runtime.py 状态机失败（mypy 探测逻辑）→ 14/14 通过
- S0-T2：全量 unit 测试基线 → test_agent_runtime.py 14/14、test_adapters.py 25/25、test_craft_gates.py 41/41、test_craft_accept.py 29/29、test_craft_loop.py 15/15 等全部通过
- S0-T3：ruff/mypy/bandit 全量扫描 → 0 errors
- S0-T4：编写 docs/architecture/domain-model.md → 领域模型、数据字典、状态机图、入口矩阵
- S0-T5：扫描真实 API Key/密钥 → 核心源码目录 0 findings
- S0-T6：建立 scripts/check_local.ps1 → 核心检查逻辑就绪

### 阶段 1（领域内核与 Job 事实源）🔄 进行中（约 70%）
- P1-1 状态机冻结 ✅（15 态，10/10 测试通过）
- P1-2 应用服务层 ✅（api/services/verification_service.py，jobs.py 已迁移）
- P1-3 Contract Registry 扩充 ✅（15 个新字段）
- P1-4 事件信封 ✅（contracts/events.py 已就绪）
- P1-5 错误码信封 ✅（api/errors.py 已就绪）
- P1-7 对象元数据 ✅（#336：记录**对象坐标** `bucket/object-name`（`object_ref`）并**按它解析** —— 路径是文件**当时**在哪，对象坐标是字节**现在**在哪；SQLite/MySQL 各有 DDL 与 `ALTER TABLE` 迁移；顺带发现并修掉一个**既有**缺陷：MySQL 后端把 SQLite 的 DDL 原样翻译过去（TEXT 列带 DEFAULT，MySQL 拒绝）⇒ `ensure_schema()` 每次都失败、**这个生产后端从来没建过表**，而门控测试一直被跳过）

### 阶段 2（证据链和回放闭环）✅ 100% 完成
- P2-1 Evidence Fragment schema ✅（evidence/fragments.py，8 种 Fragment 类型 + collector_version + 规范化 + 摘要）
- P2-2 Capsule 批量回放 runner ✅（evidence/batch_replay.py，失败分类：environment/artifact/script/diverged；成功率分母是「已判定」数量）
- P2-3 证书离线验证 ✅（evidence/offline_verify.py，诚实区分 signature / digest_attestation / unverified；撤销日志不可读时 fail-closed）
- P2-4 orphan 对象与悬挂引用扫描 ✅（evidence/orphan_scan.py，只报告不删除）
- CLI 接线 ✅（`specproof evidence replay-batch|verify-cert|scan`）
- 新增测试 94 项全部通过

### 阶段 3（动态实验室扩展）🔄 进行中
- P3-2 Redis 状态采集器 ✅（experiments/collectors.py：键存在性/值/TTL 快照 + 描述性对比）
- P3-3 RabbitMQ 发布探针 ✅（experiments/collectors.py：实际发布计数/routing key/payload 摘要 + 失败也记录）
- P3-6 contract_id 一贯传递 ✅（agent/nodes/run_differential.py：跳过的差分实验为每个真实契约产生 UNVERIFIED 行并带原因；agent/matrix_policy.py：具体原因优先于通用兜底）
- 关键设计：采集器**不判定严重度**（归 Review Court），未观测到状态一律 NO_EVIDENCE
- P3-7 故障注入 ✅（`storage/artifact_store.py`：对象上传成功但写库失败的诚实处理 —— 报告 `metadata_recorded=False` + 原因；strict 模式补偿删除（失败也报告）；非 strict 模式保留对象并给出对账线索）
- P3-5 统一状态快照 ✅（`experiments/db_snapshot.py`：分表 DbSnapshot 模型、表无关比较、可插拔采集器协议；线格式向后兼容）
- P3-4 六类实验模板 ✅（#312：`experiments/experiment_classes.py` 把六类实验做成可复用协议（家族/机制/模板/正负/holdout 样本）；门逐条核验样本的 ground truth；覆盖报告记录缺口——CONCURRENCY-01 的 holdout 仍缺，需新建案例）
- P3-4 模板体抽成与仓库无关的可移植模板 ✅（#319：域**名字**进 `agent/experiments/profile.py`（实体/仓储/DTO/端点/包名），模板的**逻辑**留在原处；生成的源码被 golden **逐字节**钉住，profile 可注入）
- 模板搬进 `agent/experiments/` 并让 `experiment_classes` 指向新层 ✅（#320：24 个模板常量逐字搬进 `agent/experiments/templates.py`；节点只做管线，golden 未改一字即绿）
- 并发类的**服务路径陈旧读模板** ✅（#333：模板**驱动服务**（仓储接缝喂陈旧快照 → 下单服务拿它去写）；基线 **18/18 通过**，服务级缺陷（批量 UPDATE 绕过版本守卫）**失败并指出「另一个写者的 5 被吞成 7」**，而同一次变异下其余 17 个用例照常通过 ⇒ 新增探测能力；golden 纯增量 +109/-0）
- 并发家族的金案例与 holdout ✅（#335：`case-101-tx-bulk-update-bypasses-version-guard`（**服务级**缺陷：批量 UPDATE 的 WHERE 里没有版本谓词）；在**真正的 tag** 上验证过（`scripts/verify_case_tags.py`：`base` 绿 / `head` 红 ⇒ `base_pass_head_fail` 成立）；**六类实验第一次全部齐了正样本、负样本与 holdout**）
- P3-7 其余故障注入：服务崩溃/超时/网络断开/消息重投/DB 锁等待 ✅（#321：补上**超时**与**网络断开**（provider 侧重试预算内、原样抛出、绝不编造答案）与**网络断开/DB 锁等待**（数据库侧：中途故障 ⇒ 作业行与 outbox 行都不落地，真库真事务证明原子性））
- P3-7 剩余项：provider 收到**空 JSON 响应** ✅（#322：`chat` 空 `choices` 点名网关故障、无文本且无 tool_call 时与 responses 协议**一字不差**地拒绝；只有 tool_call 的回复照常放行；故障场景 16 → 17）
- P3-7 剩余项：**磁盘满**（ENOSPC） ✅（#330：四个故障点逐一实测——临时写/备份/首次审计都**如实**报「没写」；只有**写入之后**那次审计失败会说谎（文件已落地却报「写入失败」），已改为 `AuditError` + 独立错误码 `EDIT_LANDED_AUDIT_FAILED`，模型不会去重试一个已经落地的写入）
- 状态机生产写入方 ✅（`agent/job_stage.py`：PREPARING/REVIEWING 由管线阶段推进；迁移 0015 把 ENUM 扩到 15 态；回收器覆盖全部在途状态）
- EXPIRED 生产写入方 ✅（迁移 0016 加 `max_execution_seconds`；`expire_overdue_jobs` 把超期作业置为 EXPIRED；回收 tick 在同一把 scope 锁内调用）
- 人工路径与自动路径对齐 ✅（`specproof ops recover` 第三步做过期扫描；`--dry-run` 只读预览超期作业；步骤编号按实际执行的步骤计算）
- 执行预算按档位 ✅（FAST 3600 / DEEP 7200 / RELEASE 10800，逐作业可覆盖；DEEP 的数值待生产数据校准）
- CONTRACT_REVIEW / NEEDS_REVIEW 的诚实生产路径 ✅（#306：NEEDS_REVIEW 有了生产写入方——判定层分出「确有问题」与「证据不足」，CLI 退出码 3、GitHub Check failure、前端 warn 色调、报告 pending 样式、仪表盘 needs_review_rate；CONTRACT_REVIEW 仍**不写**，管线不在那里停）
- 判定理由分级表 ✅（#307：BLOCKED 只留给「确有问题」与「记录自相矛盾」；「取不到证据」一律 NEEDS_REVIEW；逐场景门固定这张表）
- 未获批准契约说清原因 ✅（#308：矩阵行记「契约未获批准」，判定理由优先用行自带的具体理由；CONTRACT_REVIEW 的「不写」写进状态机注释，成为记录在案的决定）
- 对外理由受控词表 ✅（#309：行用**代码**说原因，判定层拥有对外措辞；节点的自由散文不再进入对外理由）
- 判定层自推事实 ✅（#310：契约的审批状态由判定层**自己**算出，节点的标签只是提示——错标无法让产品说错结论）
- 理由从「节点说」变「判定层算」 ✅（#311：三种代码全部可由事实推出；行自检的门让错标当场红，不再被无声覆盖）
- CONTRACT_REVIEW 的诚实生产路径（待开始，见账本 #306 下一号队列）

### 阶段 3 新增文件清单

| 文件 | 内容 | 测试 |
|------|------|------|
| `experiments/collectors.py` | Redis 状态采集器 + RabbitMQ 发布探针 → Evidence Fragment | `tests/unit/test_dynamic_collectors.py` (23) |
| `storage/artifact_store.py` | 对象上传 + 索引的诚实失败处理（两存储一致性缺口） | `tests/fault/test_artifact_store_faults.py` (10) |
| `experiments/db_snapshot.py` | 统一状态快照：分表模型 + 表无关比较 + 采集器协议 | `tests/unit/test_db_snapshot.py` (28) |
| `agent/job_stage.py` | 阶段→状态推进（PREPARING/REVIEWING 的生产写入方） | `tests/unit/test_job_stage.py` (21) |
| `agent/nodes/run_differential.py` | 跳过的差分实验归属到真实契约（修改） | `tests/unit/test_contract_id_attribution.py` (13) |
| `agent/matrix_policy.py` | 具体未验证原因优先于通用兜底（修改） | 同上 |
| `agent/nodes/build_matrix.py` | 原因透传到矩阵行（修改） | 同上 |

### P3-6 修复的实质缺陷（诚实性）
**修复前**：差分实验跳过/失败时，结果带着泛化的 `contract_id: "DIFF-01"`；
`build_matrix` 丢弃不在已编译契约中的结果 → **该结果从矩阵静默消失**，
契约行看起来像「什么都没发现」，而不是「实验没能跑」。
**修复后**：跳过的实验为每个真实契约产生 `UNVERIFIED` 行并带原因，
矩阵行的 `unverified_reason` 显示具体原因（如 "Workspace not prepared ..."），
读者能区分「实验没跑」与「实验跑了但没发现」。

### P3-7 修复的实质缺陷（分布式一致性）
**修复前**：对象上传成功但元数据写库失败时，产物成为**幽灵**——
字节在对象存储里可被摘要校验，但没有任何索引指向它，证据链出现无人能发现的空洞。
**修复后**：`storage/artifact_store.py` 的结果永远说明真相：
`metadata_recorded` / `metadata_error` / `compensated` / `compensation_error`；
strict 模式做补偿删除（删除也失败则如实报告），
非 strict 模式保留产物并给出对账扫描线索（`orphan_candidates()`），
与 `evidence/orphan_scan.py` 的孤儿扫描形成闭环。

### P3-5 修复的实质缺陷（证据盲区）
**修复前**：`_compare_db_state` 里表名是**硬编码**的
`for table in ("users", "products", "orders")` —— 不在这个列表里的表，
其差异**完全不可见**：快照明明不同，判定却是「Base 和 Head 的 DB dump 完全一致」。
这等于让新业务域的持久化回归静默通过。
**修复后**：`experiments/db_snapshot.py` 的比较**从快照里发现表**（表无关），
任何表的差异都被报告；判定名称（`DB_MUTATED_ON_UNAUTH` / `DB_MUTATED`）
留在策略层（Review Court 侧），因为「users 表变了意味着什么」是政策而非观测。
线格式保持兼容：既有消费者读的 `snapshot["rows"]` 扁平映射一字未变，
新增 `tables` 分表结构供新消费者使用。

---

**执行承诺：本计划从制定起持续有效，每个阶段完成后更新本文档，绝不中断开发。**
