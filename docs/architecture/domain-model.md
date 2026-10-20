# SpecProof 领域模型文档

> 版本：1.0 | 制定日期：2026-10-20 | 主线：`D:\面试项目\specproof-reference`

本文档定义 SpecProof 平台的核心领域模型、数据字典、状态机和入口矩阵。

---

## 一、核心领域对象

### 1.1 领域对象概览

| 领域对象 | 存储位置 | 职责 | 关键状态 |
|---------|---------|------|---------|
| **Tenant** | MySQL (`tenants`) | 租户/组织边界、配额、计费 | active/suspended/deleted |
| **User** | MySQL (`users`) | 用户身份、角色、API Key | active/inactive |
| **VerifyJob** | MySQL (`verify_jobs`) | 验证作业事实源 | QUEUED→...→VERIFIED\|BLOCKED\|FAILED |
| **CraftJob** | MySQL (`agent_jobs`) | 开发 Agent 作业事实源 | QUEUED→...→DONE\|FAILED\|CANCELLED |
| **Contract** | MySQL (`contracts`) | 可执行需求约束 | DRAFT→APPROVED\|REJECTED\|REVOKED |
| **Finding** | MySQL (`findings`) | 验证发现/证据 | OPEN\|CONFIRMED\|WAIVED |
| **EvidencePack** | MongoDB + MinIO | 实验工件、状态快照、digest | - |
| **Capsule** | MinIO | 可重放的完整证据包 | - |
| **Certificate** | MinIO + MySQL | Ed25519 签名的合并证书 | VERIFIED\|REVOKED |

### 1.2 核心关系图

```
Tenant (1) ───< (N) User
Tenant (1) ───< (N) VerifyJob
Tenant (1) ───< (N) CraftJob
Tenant (1) ───< (N) Contract
VerifyJob (1) ───< (N) Finding
VerifyJob (1) ─── (1) Capsule
VerifyJob (1) ─── (1) Certificate
CraftJob (1) ──> (1) VerifyJob (handoff)
Contract (1) ───< (N) Finding (via contract_id)
```

---

## 二、VerifyJob 状态机

### 2.1 状态定义

| 状态 | 含义 | 终态? | 可取消? |
|------|------|-------|---------|
| `QUEUED` | 已入队，等待 Worker | 否 | 是 |
| `PREPARING` | 准备 Base/Head worktree、环境 | 否 | 是 |
| `CONTRACT_REVIEW` | 等待 Contract 人工审批 | 否 | 是 |
| `RUNNING` | 执行静态/动态/差分实验 | 否 | 是 |
| `REVIEWING` | Review Court 裁决中 | 否 | 否 |
| `VERIFIED` | 全部必需 Contract PASS，签发证书 | **是** | 否 |
| `BLOCKED` | 存在 BLOCKER/MAJOR Finding，拒绝合并 | **是** | 否 |
| `NEEDS_REVIEW` | 证据不足，需人工判断 | **是** | 否 |
| `FAILED` | 系统/管线错误，无法完成验证 | **是** | 否 |
| `CANCELLED` | 用户/管理员主动取消 | **是** | 否 |
| `STALE` | Head 已被新 Job 替代 | **是** | 否 |
| `EXPIRED` | 超过保留期/执行期限 | **是** | 否 |

### 2.2 合法状态转换表

| 当前状态 | 允许转换到 | 触发条件 |
|---------|-----------|---------|
| QUEUED | PREPARING, CANCELLED | Worker 拾起 / 用户取消 |
| PREPARING | CONTRACT_REVIEW, FAILED, CANCELLED | 准备完成 / 准备失败 / 取消 |
| CONTRACT_REVIEW | RUNNING, CANCELLED, NEEDS_REVIEW | 审批通过 / 取消 / 无可用 Contract |
| RUNNING | REVIEWING, FAILED, CANCELLED | 实验完成 / 管线错误 / 取消 |
| REVIEWING | VERIFIED, BLOCKED, NEEDS_REVIEW, FAILED | 裁决完成 / 裁决失败 |
| 任意非终态 | STALE | 新 Job 覆盖同一 Head |
| 任意非终态 | EXPIRED | 超过 max_execution_time |

### 2.3 状态转换不变量

1. **单向流动**：状态只能按表推进，禁止回退（除了 CANCELLED）
2. **终态不可变**：VERIFIED/BLOCKED/NEEDS_REVIEW/FAILED/CANCELLED/STALE/EXPIRED 进入后不可再转换
3. **取消优先**：任何非终态均可被取消，取消操作幂等
4. **审计必记**：每次转换必须写入 `job_audit_log` (job_id, from_state, to_state, actor, reason, at)

---

## 三、CraftJob 状态机

### 3.1 状态定义

| 状态 | 含义 | 终态? |
|------|------|-------|
| `QUEUED` | 已创建，等待规划 | 否 |
| `PLANNING` | 正在生成计划（LLM 或确定性） | 否 |
| `PLAN_READY` | 计划已生成，等待人工批准 | 否 |
| `EXECUTING` | 正在执行工具流 | 否 |
| `SELF_VERIFYING` | 运行五道内部门禁 | 否 |
| `HANDOFF_VERIFY` | 交付 SpecProof 独立验收 | 否 |
| `DONE` | 验收通过，交付完成 | **是** |
| `FAILED` | 执行/验收失败 | **是** |
| `STUCK` | 预算耗尽/连续失败/无法继续 | **是** |
| `CANCELLED` | 用户取消 | **是** |
| `EXPIRED` | 超过保留期 | **是** |

### 3.2 关键转换点

- `PLANNING` → `PLAN_READY`：计划生成完成，**必须**等待人工批准
- `PLAN_READY` → `EXECUTING`：用户点击"批准执行"
- `EXECUTING` → `SELF_VERIFYING`：工具流完成，运行五道门禁
- `SELF_VERIFYING` → `HANDOFF_VERIFY`：内部门禁全部通过（或 skipped 但无 error）
- `HANDOFF_VERIFY` → `DONE`/`FAILED`：取决于 SpecProof VerifyJob 结果

---

## 四、Contract 状态机

### 4.1 状态定义

| 状态 | 含义 |
|------|------|
| `DRAFT` | 候选契约，待审批 |
| `APPROVED` | 已批准，可用于验证 |
| `REJECTED` | 审批拒绝 |
| `REVOKED` | 已撤销，不再使用 |
| `SUPERSEDED` | 被新版本替代 |

### 4.2 版本控制

- 每次修改产生新版本（`version` 自增）
- 旧版本**不可变**，保留用于历史重放
- `spec_digest` 绑定需求文本，需求变更 = 新 Contract 族
- `checker_version` 记录检查器版本，确保可复现

---

## 五、Finding 严重度与生命周期

### 5.1 严重度定义（按 Review Court 政策）

| 严重度 | 定义 | 证据要求 | 可升级为 BLOCKER? |
|--------|------|---------|------------------|
| `BLOCKER` | 真实回归、有 DB/行为证据、Head 归因、Contract 已批准、Capsule 可重放、置信度 ≥ 0.9 | 必须有动态证据 | 是（默认） |
| `MAJOR` | 静态发现、或有证据但不满足 BLOCKER 全条件 | 静态证据可接受 | 否（需动态证据） |
| `MINOR` | 代码风格、文档、非阻塞 finding | 可无动态证据 | 否 |
| `INFO` | 信息性记录 | 无 | 否 |

### 5.2 Finding 状态流转

```
OPEN → CONFIRMED (Review Court 裁决)
     → WAIVED (人工豁免，需审批人、理由、过期时间)
     → REJECTED (误报，需证据)
```

---

## 六、数据字典（核心表）

### 6.1 `verify_jobs` 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK, 自增 | 内部 ID |
| job_id | CHAR(36) | UK, NOT NULL | 对外 UUID |
| tenant_id | BIGINT | FK, NOT NULL | 租户 |
| repository | VARCHAR(500) | NOT NULL | 仓库地址/路径 |
| base_sha | CHAR(40) | NOT NULL | Base 提交 |
| head_sha | CHAR(40) | NOT NULL | Head 提交 |
| spec_text | TEXT | NOT NULL | 需求文本 |
| spec_digest | CHAR(64) | NOT NULL | SHA-256(spec_text) |
| contract_version | INT | DEFAULT 0 | 使用的 Contract 版本 |
| policy_version | INT | DEFAULT 1 | 策略版本 |
| depth | VARCHAR(20) | DEFAULT 'FAST' | FAST/DEEP |
| budget_tokens | BIGINT | DEFAULT 0 | Token 预算 |
| status | VARCHAR(30) | NOT NULL | 见状态机 |
| error | TEXT | NULLABLE | 失败原因 |
| worker_id | VARCHAR(100) | NULLABLE | 执行 Worker |
| lease_expires_at | TIMESTAMP | NULLABLE | 租约过期 |
| retry_count | INT | DEFAULT 0 | 重试次数 |
| started_at | TIMESTAMP | NULLABLE | 开始时间 |
| finished_at | TIMESTAMP | NULLABLE | 结束时间 |
| created_at | TIMESTAMP | DEFAULT NOW() | 创建时间 |
| updated_at | TIMESTAMP | DEFAULT NOW() | 更新时间 |

### 6.2 `contracts` 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK | 内部 ID |
| contract_id | VARCHAR(100) | UK | 如 AUTH-01-v3 |
| family | VARCHAR(50) | NOT NULL | AUTH/UNIQUE/TRANSACTION... |
| version | INT | NOT NULL | 版本号 |
| requirement_digest | CHAR(64) | NOT NULL | 需求文本摘要 |
| approval_state | VARCHAR(20) | NOT NULL | DRAFT/APPROVED/REJECTED/REVOKED/SUPERSEDED |
| spec | JSON | NOT NULL | 结构化契约定义 |
| scope | JSON | NOT NULL | 适用仓库/语言/框架/路径 |
| evidence_minimum | VARCHAR(20) | DEFAULT 'DYNAMIC' | STATIC/DYNAMIC/DB_STATE |
| checker_version | VARCHAR(50) | NOT NULL | 检查器版本 |
| approved_by | BIGINT | FK | 审批人 |
| approved_at | TIMESTAMP | NULLABLE | 审批时间 |
| revoked_at | TIMESTAMP | NULLABLE | 撤销时间 |
| supersedes | VARCHAR(100) | NULLABLE | 替代的旧版本 |
| created_at | TIMESTAMP | DEFAULT NOW() | 创建时间 |

### 6.3 `findings` 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | BIGINT | PK | 内部 ID |
| job_id | CHAR(36) | FK, NOT NULL | 关联 VerifyJob |
| contract_id | VARCHAR(100) | FK, NOT NULL | 关联 Contract |
| severity | VARCHAR(20) | NOT NULL | BLOCKER/MAJOR/MINOR/INFO |
| confidence | DECIMAL(3,2) | DEFAULT 0.0 | 置信度 0.0-1.0 |
| status | VARCHAR(20) | DEFAULT 'OPEN' | OPEN/CONFIRMED/WAIVED/REJECTED |
| attribution | VARCHAR(20) | NOT NULL | HEAD/BASE/AMBIGUOUS |
| evidence_pack_ref | VARCHAR(200) | NULLABLE | MongoDB/MinIO 引用 |
| capsule_ref | VARCHAR(200) | NULLABLE | Capsule 对象引用 |
| waiver_reason | TEXT | NULLABLE | 豁免理由 |
| waived_by | BIGINT | FK | 豁免人 |
| waived_at | TIMESTAMP | NULLABLE | 豁免时间 |
| created_at | TIMESTAMP | DEFAULT NOW() | 创建时间 |

---

## 七、事件 Envelope 契约

所有异步事件（RabbitMQ、Outbox、SSE、Webhook）统一使用：

```json
{
  "event_id": "uuid-v4",
  "event_type": "verify.job.started",
  "schema_version": "1",
  "tenant_id": 123,
  "aggregate_id": "job-uuid",
  "aggregate_type": "VerifyJob",
  "occurred_at": "2026-10-20T10:00:00Z",
  "trace_id": "trace-uuid",
  "producer": "worker-1",
  "payload_digest": "sha256:...",
  "idempotency_key": "job-uuid:started",
  "payload": { ... }
}
```

### 7.1 核心事件类型

| 事件类型 | 触发时机 | Payload 关键字段 |
|---------|---------|-----------------|
| `verify.job.queued` | Job 创建入队 | job_id, repository, base_sha, head_sha |
| `verify.job.started` | Worker 开始执行 | job_id, worker_id |
| `verify.job.contract_review` | 进入审批等待 | job_id, contract_ids[] |
| `verify.job.running` | 进入实验执行 | job_id, stage |
| `verify.job.reviewing` | 进入 Review Court | job_id |
| `verify.job.verified` | 终态 VERIFIED | job_id, certificate_ref |
| `verify.job.blocked` | 终态 BLOCKED | job_id, findings[] |
| `verify.job.failed` | 终态 FAILED | job_id, error |
| `verify.job.cancelled` | 终态 CANCELLED | job_id, reason |
| `craft.job.created` | CraftJob 创建 | job_id, repo_path |
| `craft.job.plan_ready` | 计划待批准 | job_id, plan_json |
| `craft.job.approved` | 用户批准计划 | job_id |
| `craft.job.handoff_verify` | 交付验收 | job_id, verify_job_id |
| `craft.job.done` | 终态 DONE | job_id |
| `craft.job.failed` | 终态 FAILED | job_id, error |

---

## 八、入口矩阵（五大入口统一调用应用服务）

| 入口 | 验证创建 | 查询状态 | 取消 | 进度流 | 矩阵/证据 | 证书/回放 |
|------|---------|---------|------|--------|----------|----------|
| **CLI** | `specproof verify` | `specproof status <id>` | `specproof cancel <id>` | 无 | JSON 输出 | `specproof accept` |
| **FastAPI** | `POST /jobs` | `GET /jobs/{id}` | `POST /jobs/{id}/cancel` | `GET /jobs/{id}/events` (SSE) | `GET /jobs/{id}/matrix` | `GET /jobs/{id}/certificate` |
| **MCP** | `tools/verify` | `tools/verify_status` | `tools/cancel_job` | 资源订阅 | `tools/get_matrix` | `tools/replay_info` |
| **GitHub App** | Webhook → `POST /jobs` | Check Run 状态 | 无 | Check Run 进度 | Check Run 评论 | Check Run 证书链接 |
| **Web** | 向导式表单 | Dashboard 列表/详情 | 详情页取消按钮 | 实时时间线 | 矩阵页/证据页 | 证书页/回放按钮 |

**统一规则**：所有入口必须调用同一 `VerificationApplicationService`，共享：
- 相同的 Job 创建逻辑（幂等键、输入摘要、Outbox 写入）
- 相同的状态机、权限矩阵、错误码
- 相同的聚合 DTO 返回结构

---

## 九、权限矩阵（RBAC）

| 角色 | VerifyJob 创建 | VerifyJob 读取 | VerifyJob 取消 | CraftJob 创建 | CraftJob 批准 | Contract 审批 | 证书下载 | 管理员操作 |
|------|---------------|---------------|---------------|--------------|-------------|-------------|---------|-----------|
| Viewer | ✅ | ✅ (自己) | ❌ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Member | ✅ | ✅ (租户) | ✅ (自己) | ✅ | ❌ | ❌ | ✅ | ❌ |
| Reviewer | ✅ | ✅ (租户) | ✅ (租户) | ✅ | ✅ | ❌ | ✅ | ❌ |
| Admin | ✅ | ✅ (租户) | ✅ (租户) | ✅ | ✅ | ✅ | ✅ | ❌ |
| Owner | ✅ | ✅ (租户) | ✅ (租户) | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 十、错误码规范

| Code | HTTP | 含义 | 可重试? |
|------|------|------|--------|
| `INVALID_ARGUMENT` | 400 | 请求参数非法 | 否 |
| `UNAUTHENTICATED` | 401 | 未登录/Token 失效 | 否 |
| `PERMISSION_DENIED` | 403 | 无权限（跨租户/角色不足） | 否 |
| `NOT_FOUND` | 404 | 资源不存在 | 否 |
| `STATE_CONFLICT` | 409 | 状态冲突（如重复取消、非终态强制完成） | 否 |
| `DEPENDENCY_DEGRADED` | 503 | 依赖降级（ES 不可用、Provider 不可用） | **是** |
| `EXECUTION_FAILED` | 500 | Worker/沙箱执行失败 | 视情况 |
| `RATE_LIMITED` | 429 | 限流 | **是** (Retry-After) |
| `BUDGET_EXCEEDED` | 402 | 预算耗尽 | 否 (需充值) |

---

## 十一、存储分层职责

| 存储 | 职责 | 数据类型 | 保留策略 |
|------|------|---------|---------|
| **MySQL** | 事实源：Job、Contract、Finding、User、Tenant、Audit、Outbox、Billing | 结构化、强一致 | 永久（法律要求） |
| **MongoDB** | Checkpoint、EvidencePack、复杂分析文档 | 文档、可重建 | 90 天（可配置） |
| **MinIO** | Capsule、Certificate、大工件、日志 | Blob、不可变 | Capsule/Cert: 1 年；日志: 30 天 |
| **Redis** | 幂等键、租约、进度 Stream、预算计数器 | 临时、TTL | TTL 自动过期 |
| **RabbitMQ** | 事件传输（不作为查询 DB） | 消息 | 消费确认后删除，DLQ 保留 7 天 |
| **Elasticsearch** | 全文/语义检索投影 | 可删除、可重建 | 同步 MySQL，随源数据更新 |

---

## 十二、迁移版本对照

| 版本 | 迁移文件 | 关键变更 | 兼容性 |
|------|---------|---------|--------|
| 0001 | `0001_initial_schema.py` | 初始 Schema | - |
| 0002 | `0002_add_contracts.py` | Contract 表、版本控制 | 向前兼容 |
| 0003 | `0003_add_findings.py` | Finding 表、严重度 | 向前兼容 |
| 0004 | `0004_github_app.py` | GitHub App 安装、Check Run | 向前兼容 |
| 0005 | `0005_billing.py` | 用量账本、发票 | 向前兼容 |
| 0006 | `0006_craft_jobs.py` | Agent Job 表、状态机 | 向前兼容 |
| 0007 | `0007_evidence_pack.py` | EvidencePack 引用字段 | 向前兼容 |
| 0008 | `0008_capsule_replay.py` | ReplayRecord 表 | 向前兼容 |

> **迁移原则**：新增列先允许 NULL → 回填 → 加约束；枚举变更先让旧 Worker 能读取；删除字段经历至少一个发布周期。

---

## 十三、Go/No-Go 指标基线

| 指标 | 目标 | 当前基线 (2026-10-20) | 测量方式 |
|------|------|---------------------|---------|
| BLOCKER/MAJOR Precision | ≥ 90% | 100% (17/17) | Golden cases eval |
| 语义回归 Recall | ≥ 80% | 100% (17/17) | Golden cases eval |
| PR 归因准确率 | ≥ 90% | 100% (旗舰案例) | Base/Head 差分 |
| Capsule Replay 成功率 | ≥ 95% | 待全量测量 | `specproof craft accept --replay` |
| 无证据严重 Finding | 0 | 0 (政策强制) | Review Court 裁决 |
| FAST 小 PR p95 | ≤ 8 分钟 | 待测量 | 端到端计时 |
| vs LLM 基线 Recall 提升 | ≥ +25pp | 待补测 | Baseline 对照实测 |

---

*文档版本控制：每次架构变更必须同步更新本文档、OpenAPI Spec、数据字典、评测记录。*