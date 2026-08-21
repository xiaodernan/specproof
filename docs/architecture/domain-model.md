# 领域模型 (DOMAIN MODEL) — 冻结与演进

依据: docs/工业化商业化终极开发指南.md §3/§7/§14-1。本文冻结当前领域对象,
并声明向商业多租户演进的路径 (指南 §7.1 核心关系表为目标态)。

## 1. 当前已冻结对象 (已实现, 以代码为准)

| 领域 | 对象 | 位置 | 备注 |
|---|---|---|---|
| 验证 | VerificationJob (10 态状态机) | storage/mysql.py + agent/worker.py | CREATED/QUEUED/DISPATCHED/RUNNING/WAITING_FOR_PROVIDER/SUCCEEDED/BLOCKED/FAILED/CANCELLED/STALE |
| 验证 | JobStage/JobSummary | storage/mysql.py (0003_job_summary) | 阶段与摘要持久化 |
| 规格 | Specification (spec_digest) | agent/contracts/parser.py | 需求文本→结构化 |
| 契约 | Contract/ContractApproval (PROPOSED/APPROVED/REJECTED/REVOKED) | agent/contracts/registry.py | 审批 + 审计 + spec_digest 版本隔离 |
| 证据 | Finding/EvidenceDigest | evidence/ + agent/state.py | 证据政策 (静态封顶 MAJOR, BLOCKER 六条件) |
| 证据 | MergeCertificate/RejectionNotice + Lineage DAG | evidence/certificate.py + lineage.py | Ed25519 + 契约血缘 |
| 证据 | BugCapsule (manifest digest) | evidence/ + capsules/ | 可重放, PK 校验 |
| 执行 | SandboxResult (mode: docker/local_fallback/local) | sandbox/runner.py | 非 root/断网/ro/限额 |
| 任务 | OutboxEvent/InboxEvent | storage/ + CP OutboxEvent | 事务 Outbox + 幂等 |
| 身份 | Tenant/ControlPlaneUser/WebhookDelivery | services/control-plane/ | CP 侧, 迁移 0001-0004 |
| Agent | TaskSpec/Plan/Step/TaskMemory | craft/ | SpecCraft 规划/记忆 |
| 检索 | 符号块/repo 隔离索引 | storage/elasticsearch.py + retrieval/ | BM25+向量+图谱 |
| 评测 | GoldenCase (spec/ground-truth/scenario) | golden-cases/ + split.json | holdout 锁定 |

## 2. 目标态 (指南 §7.1, 阶段 1/6 落地)

organizations, users, memberships, roles, permissions, service_accounts,
api_tokens, sso_connections, repositories, repository_connections,
repository_policies, specifications, specification_versions, contracts,
contract_approvals, verification_jobs, verification_job_stages,
job_status_transitions, findings, finding_events, finding_waivers,
evidence_artifacts, capsules, certificates, certificate_keys, replays,
provider_configs, model_usage, usage_ledger, plans, subscriptions,
invoices, notifications, audit_events, outbox_events, inbox_events。

迁移原则:
- 每表 tenant scope + (tenant_id, created_at)/(tenant_id, status) 复合索引;
- 外部可见 ID 用不可猜测 ULID/UUID, 不暴露自增 ID;
- usage_ledger 不可变, 只允许追加冲正;
- job_status_transitions 每次迁移 CAS 记录 from/to/actor/reason/trace_id;
- 事实源 MySQL, 工件 MongoDB, 短期状态 Redis (全 TTL), 大对象 MinIO。

## 3. 事件 Envelope (统一契约, 指南 §3.4)

{event_id(ulid), event_type(verification.job.created.v1), occurred_at,
tenant_id, actor_id, trace_id, aggregate_type, aggregate_id, schema_version,
idempotency_key, payload, payload_digest(sha256:...)} — 消费者记 inbox,
失败分 可重试/人工/永久拒绝; 明文密钥/私钥/完整源码/未脱敏请求禁止入事件。

## 4. 领域边界规则 (评审红线, 指南 §13)

- 跨域只经接口/事件; 前端不得知晓表名; Worker 不得改租户账单;
- 不绕过状态机 (禁止直接 UPDATE 状态); 不丢 tenant scope;
- 不可信文本一律数据段; 不把静态证据升 BLOCKER;
- Redis 不当事实源; 重试不得重复副作用; 不留无法清理的对象。
