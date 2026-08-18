# SpecProof 架构说明

版本: 0.3 (Phase 0 演示 + P1 可靠性内核 + P2 契约编译器)

## 1. 系统分层

```
┌─────────────────────────────────────────────────────────────┐
│ 入口层                                                        │
│  CLI (verify/eval/probe/replay/contract) · FastAPI (jobs/SSE) │
├─────────────────────────────────────────────────────────────┤
│ Agent 层 (LangGraph, 13 节点线性管道 + 错误短路)              │
│  intake → compile_contracts → prepare_base → prepare_head    │
│  → collect_diff → retrieve_repository_context → run_static_  │
│  checks → generate_counterexamples → run_differential        │
│  → review_court → build_matrix → create_capsule              │
│  → publish_report                                            │
├─────────────────────────────────────────────────────────────┤
│ 契约编译器 (P2)                                               │
│  agent/contracts/parser.py      结构化需求解析               │
│  agent/contracts/compiler.py    候选生成 + family 映射       │
│  agent/contracts/registry.py    人工审批注册表 (MySQL)       │
├─────────────────────────────────────────────────────────────┤
│ 能力层                                                        │
│  providers/ (ModelProvider + 10 维能力探测 + 降级)           │
│  agent/checkers/ (7 个确定性 Java 源码契约检查器)            │
│  evidence/ (HTML 报告 + 证书/拒绝通知)                       │
├─────────────────────────────────────────────────────────────┤
│ 可靠性内核 (P1)                                               │
│  MySQL 状态机+Outbox → RabbitMQ (Confirm/DLQ/幂等) → Worker  │
│  (Redis lease + MongoDBSaver checkpoint) → SSE 进度          │
├─────────────────────────────────────────────────────────────┤
│ 基础设施 (compose.phase0.yml)                                 │
│  MySQL · MongoDB · Elasticsearch · Redis · RabbitMQ · MinIO  │
└─────────────────────────────────────────────────────────────┘
```

### P2 契约生命周期

需求文本 → parser → Requirement (验收标准/禁止变更/优先级)
→ compiler → ContractCandidate (PROPOSED)
→ registry.approve (人工) → APPROVED + 审计记录
→ verify --use-approved-contracts → 按 checker 家族映射为可执行契约
→ 检查器执行 → Review Court 条件 1 只认可 approved 契约

## 2. 一条 verify 的完整数据流

1. intake: 读需求文本, 校验 repo/spec 存在; 错误记入 errors。
2. compile_contracts: 正则规则先解析 (auth/unique/token/backward_compat/
   event_once/transaction 六类模板); LLM 配置时富化稀疏结果; 失败记 errors。
3. prepare_base/head: git worktree add --detach 隔离两个版本;
   subprocess 用参数列表 (无 shell 注入); 失败记 errors。
4. 错误守卫: 任一节点记录了错误 → 直接 publish_report, 绝不基于坏输入伪造结果。
5. collect_diff: 逐文件 diff, 提取方法签名变化与 @PreAuthorize/@Transactional
   等注解移除。
6. run_static_checks: 契约检查器注册表对 Base/Head 源码做确定性比对;
   结果按 contract_id 合并 (FAIL > PASS > UNVERIFIED), 静态证据封顶 MAJOR。
7. generate_counterexamples: LLM 生成 JUnit (非思考模式) → schema 校验 →
   mvnw test-compile → 最多 3 次受控修复; 失败退确定性模板 (仅 demo 仓库);
   记录 llm_generated / deterministic_template 来源。
8. run_differential: 同一测试注入 Base 与 Head, 真实 Maven 执行;
   Base 通过+Head 失败 = base_pass_head_fail; 用 SpecProofDbCheck 读文件型
   H2 库做 DB 状态比对 (DB_MUTATED_ON_UNAUTH); 源码级注解差分独立于测试生成
   无条件记录; 证据摘要 sha256 确定性 (无时间戳)。
9. review_court: Prosecutor/Defender/Judge 三审 (LLM) 或规则法庭 (确定性);
   BLOCKER 6 条件硬校验, 不满足自动降 MAJOR; 无法官裁决默认 needs_confirmation。
10. build_matrix: 合并后的 contract_results 逐合约生成矩阵行;
    未跑过实验的合约保持 UNVERIFIED。
11. create_capsule: BLOCKER/MAJOR 各生成 capsule 目录 + zip (manifest/
    requirement/contract/finding/generated-tests/fixtures/run.sh/run.ps1);
    manifest 只含 evidence_digest。
12. publish_report: HTML 报告; CLI 层按 errors/BLOCKER/findings/unverified
    给出 FAILED/BLOCKED/NEEDS REVIEW/VERIFIED, 并写证书或拒绝通知。

## 3. 关键正确性不变量

- 只有真实实验能写 PASS/FAIL; UNVERIFIED 是诚实默认。
- 节点不得整表覆盖 contract_results (LangGraph channel 替换语义), 必须合并。
- 静态分析 ≠ BLOCKER; digest ≠ signature。
- 证据摘要确定性: 相同输入重跑得到相同 sha256。
- 无真实 Key 进入任何产物; capsule zip 内容同样扫描。

## 4. P1 内核的可靠性机制

- 任务不丢: API 建 job 与 outbox 同事务提交; relay SKIP LOCKED 轮询发布;
  Publisher Confirm 确认后才标记 published_at。
- 任务不重: RabbitMQ at-least-once 投递 + Redis 幂等键 + MySQL 状态机 CAS;
  MQ 重投不产生重复 Finding。
- 崩溃恢复: MongoDBSaver 每节点 checkpoint; worker 以 job_id 为 thread_id
  重入即从断点继续; lease 过期可被其他 worker 接管。
- 实时进度: Redis Stream (progress:{job}) + SSE Last-Event-ID 断线续传。
- 诚实终态: VERIFIED/BLOCKED/FAILED 由管线真实结果映射, 不无条件 VERIFIED。

## 5. 存储职责表

| 组件 | 职责 | 不是 |
|---|---|---|
| MySQL | job/contract/finding 事实源, 状态机, outbox | 大对象、检索 |
| MongoDB | agent_checkpoints、evidence_packs、differential_runs | 业务事实源 |
| Redis | lock/lease/budget/rate-limit/Stream 进度 (全 TTL) | 持久业务状态 |
| RabbitMQ | 命令/事件可靠投递, DLQ, 重试 | Pub/Sub 关键任务 |
| MinIO | reports/capsules/patches 大对象 (带 digest) | 结构查询 |
| Elasticsearch | 代码/契约/证据检索 (repo 隔离) | 事实判定 |

## 6. 安全模型

- PR 代码视为不可信输入; 实验在隔离 worktree 执行; 默认不读宿主机环境。
- subprocess 一律参数列表; 不拼接 shell 字符串。
- Prompt 注入防护: 仓库文本是数据, 不改变系统策略; Tool Gateway 独立鉴权 (后续阶段)。
- 密钥仅从环境变量读取; security_scanner + canary 自检 + 产物扫描。
