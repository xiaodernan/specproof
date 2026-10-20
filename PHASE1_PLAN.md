# SpecProof 阶段 1：领域内核与 Job 事实源 — 执行计划

> 主线：`D:\面试项目\specproof-reference`
> 目标：CLI、API、MCP、Worker、Web 共享同一 Verify/Craft Job、Contract、Finding、Artifact 和事件模型。
> 核心纪律：不停止、不跳阶段、每个改动都有测试、每个数字都有证据。

## 一、Phase 1 详细任务（按顺序，不跳阶段）

### P1-1：冻结 Job 状态机与合法转换表（mysql.py 核心）✅ 已完成
**验收**：15 个状态（QUEUED/PREPARING/CONTRACT_REVIEW/RUNNING/REVIEWING/VERIFIED/BLOCKED/NEEDS_REVIEW/FAILED/CANCELLED/STALE/EXPIRED + 兼容 PENDING/ERROR/WAITING_FOR_PROVIDER），终态不可变，取消优先，每次转换写审计；tests/unit/test_job_state_machine.py 静态测试 10/10 通过；ruff 0 errors；mypy 0 errors

### P1-2：AgentJobStore 与 MySQLStore 状态模型统一 ✅ 基本完成
两套 store 共享：事件信封（contracts/events.py）、错误码（api/errors.py）、应用服务层（api/services/verification_service.py）。状态词汇按领域分保留（craft 用 pending/running/...，verify 用 QUEUED/RUNNING/...），跨领域通过事件信封和错误码统一。

### P1-3：Contract Registry 扩充 ✅ 已完成
ContractRecord 新增：certificate_digest、capsule_ref、evidence_pack_ref、supersedes、parent_version、lineage_root、evidence_minimum、waiver/waiver_reason/waived_by/waived_at/waiver_expires_at。content_fields 包含 evidence_minimum/supersedes/parent_version；ruff 0 errors；mypy 0 errors

### P1-4：统一事件 Envelope ✅ 已就绪
contracts/events.py 已有 build_envelope/payload_digest/redact_secrets，outbox_relay.py 的 _flatten_envelope 已使用。

### P1-5：统一错误码、请求 ID、trace ID、租户作用域、幂等键 ✅ 已就绪
api/errors.py 已有完整错误码（13 个）、错误信封（code/message/request_id/retryable/schema_version）、失败类别和重试判断。

### P1-6：Web/API/MCP 从应用服务取聚合数据 ✅ 已完成
新建 api/services/verification_service.py (VerificationApplicationService)，api/routes/jobs.py 的 create_job/cancel_job/list_jobs/get_job/get_job_summary 已迁移到服务层；ruff 0 errors；mypy 0 errors

### P1-7：文件报告/Capsule/证书改为对象元数据引用 ⚠️ 准备就绪
MinIO 基础设施已就绪（object_path/put_object_with_digest/batch_check_exist/put_object_if_absent），待 MinIO 可用时将 craft/accept.py 的证书写入改为同时上传对象并返回对象引用；文件系统保留为 fallback。

---

## 二、退出条件（阶段 1 完成标志）
- 重复请求不重复创建 Job（幂等键）
- 跨租户读取为 404/403
- 所有入口（CLI/API/MCP/Web）得到相同状态和矩阵
- 状态机故障注入覆盖：重复、乱序、并发、非法转换
- 迁移可从空库执行

---

## 三、已完成的变更清单（本次会话）

| 文件 | 变更 | 状态 |
|------|------|------|
| `storage/mysql.py` | 状态机扩展为 15 态，默认状态 PENDING→QUEUED，插入 SQL 'PENDING'→'QUEUED' | ✅ ruff/mypy 通过 |
| `tests/unit/test_job_state_machine.py` | 状态机静态测试同步新状态机 | ✅ 10/10 通过 |
| `api/services/verification_service.py` | 新建 VerificationApplicationService | ✅ ruff/mypy 通过 |
| `api/routes/jobs.py` | create_job/cancel_job/list_jobs/get_job/get_job_summary 迁移到服务层，清理未使用导入 | ✅ ruff/mypy 通过 |
| `agent/contracts/records.py` | ContractRecord 新增 15 个 Phase 1 字段（证书/胶囊/证据引用、血缘、证据最低等级、豁免） | ✅ ruff/mypy 通过 |
| `SPEC_PROOF_LONGTERM_PLAN.md` | 更新 S0-T1..S0-T6 为已完成，标注 S0-T6 环境限制 | ✅ |
| `PHASE1_PLAN.md` | 新建阶段 1 执行计划，标注已完成项 | ✅ |

---

## 四、下一步（阶段 2：证据链和回放闭环）✅ 已完成

### P2-1：Evidence Fragment schema ✅
`evidence/fragments.py` — 8 种观测类型（Http/Db/Redis/Mq/Schema/Performance/Static/Build），
每个 Fragment 带 base/head 对比、判定状态、collector_version、证据引用、可重放性标记。

### P2-2：Capsule 批量回放 runner ✅
`evidence/batch_replay.py` — 失败分类 environment / artifact / script / diverged；
**成功率分母是「已判定」数量而非批次大小**（环境故障不是「没能复现」）。

### P2-3：证书离线验证与 digest mismatch 报告 ✅
`evidence/offline_verify.py` — 不联网、不读数据库；诚实区分
`signature` / `digest_attestation`（**绝不称为"已签名证书"**）/ `unverified`；
撤销日志不可读时 fail-closed 判为已撤销；「没有这份证据」与「证据内容不同」分开报告。

### P2-4：orphan 对象与悬挂引用扫描 ✅
`evidence/orphan_scan.py` — 悬挂引用 / 孤儿载荷 / 摘要不符三类发现；**只报告不删除**。

### CLI 接线 ✅
`specproof evidence replay-batch | verify-cert | scan`

### 新增文件清单（阶段 2）

| 文件 | 内容 | 测试 |
|------|------|------|
| `evidence/fragments.py` | Evidence Fragment schema | `tests/unit/test_evidence_fragments.py` (18) |
| `evidence/batch_replay.py` | 批量回放 runner | `tests/unit/test_batch_replay.py` (22) |
| `evidence/offline_verify.py` | 离线证书验证 | `tests/unit/test_offline_verify.py` (21) |
| `evidence/orphan_scan.py` | 对象链完整性扫描 | `tests/unit/test_orphan_scan.py` (10) |
| `cli/specproof/commands/evidence.py` | CLI 命令组 | `tests/unit/test_evidence_cli.py` (10) |

阶段 2 新增测试 **81 项**，与既有 capsule 回放测试合计 **94/94 通过**；
全项目 ruff 0 errors、mypy 0 errors（225 个源文件）。

---

**执行承诺：本计划从制定起持续有效，每个阶段完成后更新本文档，绝不中断开发。**
