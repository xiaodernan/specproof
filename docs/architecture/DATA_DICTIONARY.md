# 数据字典 (DATA_DICTIONARY) — SpecProof 全存储字段级说明

> 口径与出处: 本文逐字段登记 SpecProof 的全部持久化状态。MySQL 表结构以
> `infra/mysql/migrations/0001_init.sql` 至 `0012_finding_feedback_idempotency.sql` 十二个版本化迁移为准,
> 并与代码内幂等 DDL (`storage/identity.py` / `storage/billing.py` / `storage/agent_jobs.py` /
> `storage/object_metadata.py` / `storage/migrations.py`) 逐表核对; MongoDB/MinIO/ES/Redis/RabbitMQ
> 以对应 `storage/*` 适配器为准。
>
> **"版本化迁移为准"这句话以前是不成立的** (2026-09-26 实测纠正): 本节一度写到 0008 为止,
> 而 `agent_jobs` 当时只有代码 DDL —— 结果是 `ensure_tables()` 建出来的新库比线上产品库少一张表
> (17 vs 18)。迁移 0011 把它纳入了版本化体系; 代码 DDL 从"唯一来源"降级为"已存在安装上的
> 自愈路径", 同一张表现在有两份描述, 由 `tests/unit/test_agent_jobs_migration_parity.py`
> 逐列锁定 (列名/类型/顺序不一致即红)。
>保留/清理操作 (retention ops) 不在本文展开, 见
> `docs/operations/DATA_LIFECYCLE.md` (2026-08-19 已演练)。本文只登记**事实**:
> 每张表/集合/桶/索引/键族的 字段、类型、租户作用域、TTL/保留、写入方。

- 租户作用域标记: `T=tenant_id 列` (行级租户); `J=经 job_id 关联` (无独立租户列);
  `R=repo 维度` (按仓库隔离, 无租户); `—=无`。
- 保留标记: 无内建 TTL 的条目写 “永久(无自动清理)”, 运维清理手段见 DATA_LIFECYCLE。

---

## 1. MySQL — 数据库 `specproof_phase0` (compose 服务 mysql:8.4)

共 18 张表 (2026-09-26 于 `specproof_phase0` 与 `specproof_test` 双双实测):
17 张来自版本化迁移 0001-0012 (0012 只给 `finding_feedback` 加唯一约束, 不建新表), 1 张
(`schema_migrations`) 由 `storage/migrations.py` 的代码 DDL 建。
本文 §1.18 / §1.19 两张对象元数据表**不在这 18 张里** —— 它们只在显式选择 MySQL 对象元数据后端时
由 `ensure_schema()` 现建, 默认后端是 SQLite (见 §1.18 的口径说明)。
时间戳约定: 迁移 0001-0004/0006/0008/0009 用 MySQL TIMESTAMP; 0005/0007 与 0011 的 `agent_jobs`
用 epoch 秒 DOUBLE/REAL (`agent_jobs` 走的是 `storage/identity.py` / `storage/billing.py` 那条
可移植时间戳约定, 不是 TIMESTAMP —— 这正是 0011 必须与代码 DDL 逐列对齐的原因之一)。

### 1.1 verification_jobs — 验证任务 (业务事实源)

来源: `0001_init.sql` (+ `0002` 状态枚举, `0003` summary, `0004` github_check_json, `0005` tenant_id)

| 列 | 类型 | 说明 |
|---|---|---|
| id | CHAR(36) PK | UUID |
| repo_path | VARCHAR(512) NOT NULL | 仓库路径/URL |
| base_ref / head_ref | VARCHAR(255) NOT NULL | Base/Head 引用 (branch/tag/sha) |
| spec_path | VARCHAR(1024) NOT NULL | 需求文件路径 (webhook 建单时为空, worker 从仓库 constitution 补) |
| status | ENUM (0002 后 10 态): PENDING, QUEUED, RUNNING, WAITING_FOR_PROVIDER, VERIFIED, BLOCKED, STALE, FAILED, CANCELLED, ERROR | 状态机白名单见 `docs/architecture/STATE_MACHINES.md` |
| depth | VARCHAR(16) DEFAULT 'FAST' | API 当前只接受 FAST |
| retry_count / max_retries | INT DEFAULT 0 / 3 | 预留 (当前无生产重试调用点, 重试在 RabbitMQ 传输层) |
| stale_replaced_by | CHAR(36) NULL | 取代本 Job 的新 Job id |
| last_error | TEXT NULL | 终态错误/原因 (统一错误分类 JSON) |
| worker_id | CHAR(36) NULL | 认领 worker |
| summary | JSON NULL (0003) | 管线结果摘要 (verdict/matrix/findings/capsules)。matrix 部分自 2026-09-23 起**同时含计数与逐条行**: `matrix_passed/failed/unverified` + `matrix_rows[]`(定形 15 键投影, 含 `attribution`/`base_result`/`head_result`/`next_action`) + `matrix_rows_total`/`matrix_rows_truncated`(行上限 60, 截断如实标注)。**真实任务的逐条结果只有这一条通路** —— `contracts`/`findings` 表的生产写入方仅 `scripts/seed_demo.py` |
| github_check_json | JSON NULL (0004) | GitHub Check Run 簿记; NULL=非 PR 来源 |
| tenant_id | CHAR(36) NULL (0005) | NULL=单租户兼容/旧数据/webhook 来源 |
| created_at / updated_at | TIMESTAMP | |

索引: idx_status, idx_worker, idx_jobs_tenant。
- **写入方**: `api/routes/jobs.py` POST /jobs 与 `api/routes/webhooks.py` (GitHub PR) 经
  `storage/mysql.py` `create_job_with_outbox` (Job 行 + Outbox 行同一事务, 事务内 PENDING→QUEUED);
  `agent/worker.py` 状态转换 (RUNNING/终态); `api/routes/jobs.py` POST /jobs/{id}/cancel (CANCELLED)。
- **租户作用域**: T (读取端仓库层过滤, 越权读取返回 404 + attempted_tenant 审计)。
- **TTL/保留**: 永久; 无自动清理 (收缩规则见 DATA_LIFECYCLE §2.1)。

### 1.2 findings — Finding 明细 (来源 0001)

| 列 | 类型 | 说明 |
|---|---|---|
| id | CHAR(36) PK | |
| job_id | CHAR(36) FK → verification_jobs ON DELETE CASCADE | |
| contract_id | VARCHAR(128) | |
| severity | ENUM(BLOCKER, MAJOR, MINOR, NEEDS_CONFIRMATION) | BLOCKER 需六条件 (court) |
| confidence | FLOAT | |
| evidence_type | VARCHAR(64) | 证据类型 |
| impact_path | JSON NULL | |
| capsule_path | VARCHAR(1024) NULL | Bug Capsule zip 路径 |
| created_at | TIMESTAMP | |

- **写入方**: `storage/mysql.py` `insert_finding`; 当前生产调用点仅 `scripts/seed_demo.py` (演示种子) —
  正式管线的 findings 以 summary JSON (`verification_jobs.summary`) 与 capsule 落盘为准, 本表为演示/历史口径。
- **租户作用域**: J (经 job_id)。**TTL/保留**: 永久, 无自动清理。

### 1.3 contracts — 单 Job 契约执行结果 (来源 0001)

| 列 | 类型 | 说明 |
|---|---|---|
| id | CHAR(36) PK | |
| job_id | CHAR(36) FK CASCADE | |
| contract_id_str | VARCHAR(128) | |
| requirement_text / expected_behavior | TEXT | |
| checker_type | VARCHAR(64) | checker 家族名 |
| result | ENUM(PASS, FAIL, UNVERIFIED) DEFAULT UNVERIFIED | 合并规则 FAIL>PASS>UNVERIFIED |
| evidence_ref | VARCHAR(1024) NULL | |

- **写入方**: `storage/mysql.py` `insert_contract`; 当前生产调用点仅 `scripts/seed_demo.py`。
- **租户作用域**: J。**TTL/保留**: 永久。

### 1.4 provider_capabilities — Provider 能力探测 (来源 0001)

| 列 | 类型 | 说明 |
|---|---|---|
| id | INT AUTO PK | |
| base_url | VARCHAR(1024) | |
| model | VARCHAR(128) | |
| capabilities | JSON | 探测出的能力清单 |
| probed_at | TIMESTAMP | |

- **写入方**: `storage/mysql.py` `upsert_provider_capability` (按 base_url/model 更新);
  **当前无生产调用点** — 探测结果现行缓存于 Redis `specproof:capability:*` (TTL 86400)。
- **租户作用域**: —。**TTL/保留**: 可重建; 无自动清理 (DATA_LIFECYCLE 建议 30 天滚动)。

### 1.5 contract_registry — 契约注册表 (追加式版本化; 来源 0001 + 0006)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(128) | 复合主键 (id, version) 之一 |
| repo_path | VARCHAR(512) | |
| requirement_ref | VARCHAR(64) | |
| requirement / expected_behavior | TEXT | |
| checker_type | VARCHAR(64) | |
| source | VARCHAR(32) DEFAULT 'spec' | |
| checker_version | VARCHAR(64) DEFAULT '' (0006) | 产出该版本的 checker 实现版本 |
| version | INT (0006) | 复合主键 (id, version) — SQL 层保证只 INSERT 不原地改 |
| status | ENUM(PROPOSED, APPROVED, REJECTED, REVOKED) DEFAULT PROPOSED | 模型不得直接置 APPROVED (调用层强制) |
| spec_digest | VARCHAR(64) DEFAULT '' | |
| created_at / updated_at | TIMESTAMP | |

索引: idx_repo, idx_status, idx_contract_registry_id。
- **写入方**: `agent/contracts/storage.py` (插入新版本; approve/reject/revoke 为 UPDATE 状态,
  非 CAS 状态机 — 审批权限由调用层控制)。读取方: `api/routes/web.py` GET /api/v1/contracts、`mcp/tools.py`。
- **租户作用域**: R (按 repo_path, 无 tenant 列)。**TTL/保留**: 永久, 追加式不可原地改。

### 1.6 contract_approvals — 契约审批流水 (来源 0001 + 0006)

| 列 | 类型 | 说明 |
|---|---|---|
| id | BIGINT AUTO PK | |
| contract_id | VARCHAR(128) | 复合 FK (contract_id, contract_version) 之一 |
| contract_version | INT DEFAULT 1 (0006) | FK → contract_registry(id, version) ON DELETE CASCADE |
| action | ENUM(APPROVE, REJECT, REVOKE) | |
| approved_by | VARCHAR(128) | |
| reason | VARCHAR(1024) DEFAULT '' | |
| created_at | TIMESTAMP | |

- **写入方**: `agent/contracts/storage.py`。**租户作用域**: — (经 contract 关联)。
- **TTL/保留**: 永久。

### 1.7 outbox — 事务性发件箱 (来源 0001 + 0008)

| 列 | 类型 | 说明 |
|---|---|---|
| id | BIGINT AUTO PK | |
| aggregate_id | CHAR(36) | job_id |
| aggregate_type | VARCHAR(64) DEFAULT 'verification_job' | |
| tenant_id | VARCHAR(36) NULL (0008) | 行级租户 (relay 统计/清理) |
| event_type | VARCHAR(64) | 如 JobCreated |
| payload | JSON | 事件载荷 |
| payload_digest | VARCHAR(80) NULL (0008) | payload JSON 的 sha256 |
| routing_key | VARCHAR(128) | 如 q.p1.verify.job |
| created_at | TIMESTAMP(3) | |
| published_at | TIMESTAMP(3) NULL | 发布成功时间 |
| retry_count | INT DEFAULT 0 | 失败次数 |
| publish_count | INT DEFAULT 0 (0008) | 总发布尝试 (成功+失败) |
| last_error | VARCHAR(1000) NULL (0008) | 最近失败 (截断) |
| next_retry_at | TIMESTAMP(3) NULL (0008) | 逐行重试延迟; relay 只取 NULL 或已到期行 |
| dead_lettered_at | TIMESTAMP(3) NULL (0008) | DLQ 状态; 不再自动重试, 等运维重放 |

索引: idx_published(published_at, id), idx_aggregate, idx_outbox_tenant, idx_outbox_dead。
- **写入方**: `storage/mysql.py` `create_job_with_outbox` (与 Job 同事务, at-least-once 根基);
  `storage/outbox_relay.py` (published / failed+next_retry_at / dead-letter; SELECT ... FOR UPDATE SKIP LOCKED 认领)。
- **租户作用域**: T (tenant_id)。**TTL/保留**: 未发布行永久; 已发布行无自动清理 (DATA_LIFECYCLE: >7 天可删)。

### 1.8 audit_logs — 审计日志 (来源 0002 + 0005)

| 列 | 类型 | 说明 |
|---|---|---|
| id | BIGINT AUTO PK | |
| job_id | CHAR(36) NULL | |
| actor | VARCHAR(128) | 操作者 (worker/api/system/user) |
| action | VARCHAR(64) | job_status_transition / job_cancelled / job_cancelled_at_checkpoint / tenant_isolation_blocked 等 |
| from_status / to_status | VARCHAR(32) NULL | 状态转换前后 |
| detail | VARCHAR(1024) DEFAULT '' | |
| attempted_tenant | VARCHAR(128) NULL (0005) | 越权读取被拒时记录的对方租户 |
| created_at | TIMESTAMP | |

索引: idx_job, idx_created。
- **写入方**: `storage/mysql.py` `record_audit` (best-effort, 永不阻断业务; 状态转换/取消/租户隔离拒绝)。
- **租户作用域**: attempted_tenant 审计列; 审计员可跨租户读 (`api/routes/admin.py` GET /audit)。
- **TTL/保留**: 永久, 不清理。

### 1.9 tenants — 租户 (来源 0005; `storage/identity.py` ensure_schema 同布局)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | |
| name | VARCHAR(255) | |
| plan_id | VARCHAR(64) DEFAULT 'free' | |
| status | VARCHAR(32) DEFAULT 'active' | |
| created_at | DOUBLE (epoch 秒) | |

- **写入方**: `api/identity/store.py` (MySqlIdentityStore) + `api/routes/admin.py` GET/POST /tenants (admin)。
- **租户作用域**: 本体即租户维度。**TTL/保留**: 与租户生命周期一致。

### 1.10 users — 用户 (来源 0005)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | |
| tenant_id | VARCHAR(36) | UNIQUE(tenant_id, email) 之一 |
| email | VARCHAR(255) | |
| oidc_sub | VARCHAR(255) NULL | UNIQUE (OIDC subject) |
| role | VARCHAR(32) DEFAULT 'viewer' | viewer/operator/admin/auditor (RBAC §2 矩阵) |
| status | VARCHAR(32) DEFAULT 'active' | |
| created_at | DOUBLE | |

- **写入方**: `api/identity/store.py` + `api/routes/admin.py` (operator=本租户)。
- **租户作用域**: T。**TTL/保留**: 与租户生命周期一致。

### 1.11 api_tokens — API Token (来源 0005)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | |
| user_id | VARCHAR(36) | |
| name | VARCHAR(128) | |
| token_hash | CHAR(64) UNIQUE | 前缀哈希 (查询用) |
| secret_hash | VARCHAR(128) | bcrypt 密文 (本地鉴权) |
| scopes | VARCHAR(1024) DEFAULT '' | |
| expires_at / last_used_at | DOUBLE NULL | |
| created_at | DOUBLE | |

- **写入方**: `api/identity/tokens.py` (mint) + `api/identity/store.py` (show-once / revoke 即时删行)。
- **租户作用域**: 经 user_id → tenant。**TTL/保留**: 撤销即删行; 无自动过期清理。

### 1.12 billing_plans — 计费套餐 (来源 0007; `storage/billing.py` 同布局)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(64) PK | |
| name | VARCHAR(255) | |
| price_monthly | DOUBLE DEFAULT 0 | |
| quotas | JSON | 配额 (如 verify 次数) |
| overage | JSON | 超额单价 |

- **写入方**: `storage/billing.py` (seed/ensure)。**租户作用域**: — (全局目录)。
- **TTL/保留**: 永久。

### 1.13 billing_subscriptions — 订阅 (来源 0007)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | |
| tenant_id | VARCHAR(36) | idx_billing_subs_tenant |
| plan_id | VARCHAR(64) | |
| status | VARCHAR(32) DEFAULT 'active' | |
| period_start / period_end | DOUBLE | |

- **写入方**: `storage/billing.py`。**租户作用域**: T。**TTL/保留**: 永久。

### 1.14 usage_ledger — 用量流水 (来源 0007)

| 列 | 类型 | 说明 |
|---|---|---|
| id | BIGINT AUTO PK | |
| tenant_id | VARCHAR(36) | |
| event_id | VARCHAR(255) UNIQUE | 幂等键 (同一事件只计一次) |
| metric | VARCHAR(32) | 如 job_verify / gate_findings |
| units | DOUBLE | |
| unit_label | VARCHAR(64) DEFAULT '' | |
| happened_at | DOUBLE | |

索引: idx_usage_tenant_time, idx_usage_tenant_metric。
- **写入方**: `storage/billing.py` meter_* — `agent/worker.py` 在管线真正开始时计量
  job_verify、终态时计量 gate_findings (event_id 幂等, best-effort, 未配 SPECPROOF_BILLING_URL 时 no-op)。
- **租户作用域**: T。**TTL/保留**: 永久 (可归档 >13 个月)。

### 1.15 invoices — 发票 (来源 0007)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(36) PK | |
| tenant_id | VARCHAR(36) | UNIQUE(tenant_id, period) 之一 (每租户每月一票) |
| period | VARCHAR(7) | YYYY-MM |
| line_items | JSON | |
| total | DOUBLE | |
| currency | VARCHAR(8) DEFAULT 'USD' | |
| status | VARCHAR(32) DEFAULT 'draft' | draft→issued→paid |

- **写入方**: `storage/billing.py`。**租户作用域**: T。**TTL/保留**: 永久 (对账可重建)。

### 1.16 schema_migrations — 迁移台账 (代码 DDL: `storage/migrations.py`)

| 列 | 类型 | 说明 |
|---|---|---|
| version | INT PK | 迁移编号 |
| name | VARCHAR(255) | 迁移名 |
| applied_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |

- **写入方**: `storage/migrations.py` `MigrationRunner` (每迁移一个连接; **但 MySQL 对 DDL 隐式提交**, 所以含 ALTER 的迁移做不到"要么全成要么全不成" —— 半路断线时约束已建而版本号未记, 重跑会撞 1061。runner 因此只把 1050/1060/1061 三个"已经是这样了"的错误当作可跳过并记 WARNING, 其余错误照旧中止且不记账, 由 `tests/unit/test_migrations.py` 两侧各自钉住)。
- **租户作用域**: —。**TTL/保留**: 永久, 不清理。

### 1.17 agent_jobs — SpecCraft Agent 任务投影 (来源 `0011_agent_jobs.sql`; `storage/agent_jobs.py` 的代码 DDL 是已存在安装上的自愈路径)

| 列 | 类型 | 说明 |
|---|---|---|
| id | VARCHAR(255) PK | |
| status | VARCHAR(16) | pending/running/succeeded/failed/cancelled (5 态) |
| spec_text | TEXT | 任务需求原文 |
| spec_digest | CHAR(64) | sha256(spec_text) |
| plan_json | TEXT NULL | 计划 (有值 = console AWAITING_APPROVAL) |
| current_step | VARCHAR(255) NULL | 当前步骤 |
| progress_json | TEXT NULL | 步骤进度投影 |
| lease_owner | VARCHAR(255) NULL | 租约持有者 host:pid:job_id |
| lease_expires_at | DOUBLE NULL | epoch 秒 |
| started_at / finished_at | DOUBLE NULL | 进入 running / 进入终态各写一次 |
| result_json | TEXT NULL | 终态报告 |
| accept_json | TEXT NULL (W35.1) | accept 结果, 仅 succeeded/failed 可挂, first-write-wins |
| error | TEXT NULL | 终态原因 (cancel 覆盖) |
| created_at / updated_at | DOUBLE | |

- **写入方**: `api/routes/agent_console.py` (create/cancel/approve) + `api/agent_runtime.py`
  (runtime 线程跑真实确定性 CraftLoop, loop 内 create/lease/renew/set_plan/set_progress/update_status) +
  `craft/loop.py` (store 接线后); `craft/accept.py` `persist_accept_result` 挂 accept_json。
- **读取方**: `api/routes/agent_console.py::_accept_view` 把该列投影为
  `GET /agent/jobs/{job_id}` 响应的 `accept` 字段 (落地记录见 PRODUCT_ROADMAP §8)。三态可分辨:
  `null` = 尚未挂载, 对象 = 已挂载摘要, `{"attached": true, "malformed": true}` = 已挂载但本端点读不出来
  (解析失败永不渲染成"没有验收记录")。`rolled_back`/`idempotent`/证书路径等键**缺失即不出现**;
  门禁与发现列表各截断到 20 条, 同时给 `total` 与 `truncated`。
- **租户作用域**: — (单租户投影, 无 tenant 列; 诚实边界见 STATE_MACHINES)。
- **TTL/保留**: 永久; 无自动清理。

### 1.18 object_metadata — 对象元数据 (代码 DDL: `storage/object_metadata.py`, §A 任务 7)

> **口径 (2026-09-26 实测补充)**: 本节和 §1.19 描述的是 **MySQL 后端**的表, 而
> `default_object_metadata_store()` 的默认后端是 **SQLite** (`~/.specproof/object-metadata.sqlite3`),
> MySQL 只在显式给出 `MYSQL_URL` 并构造 `MySQLObjectMetadataStore` 时启用, 且表要由
> `ensure_schema()` 现建 —— 因此 `specproof_phase0` / `specproof_test` 两个真实 schema 里
> **都没有这两张表** (已在 §1 表数中排除)。本节列的是 SQLite 方言 (REAL/TEXT),
> MySQL 方言由 `_to_mysql()` 转换。

| 列 | 类型 | 说明 |
|---|---|---|
| object_id | VARCHAR(32) PK | uuid4().hex, 稳定身份 (绝不等于路径) |
| kind | VARCHAR(32) | certificate / capsule / replay_report |
| payload_sha256 | VARCHAR(64) DEFAULT '' | 载荷 sha256 |
| digests_json | TEXT | 摘要集 JSON |
| job_id | VARCHAR(128) DEFAULT '' | 所属验证任务 (未知为 "") |
| contract_ids_json | TEXT DEFAULT '[]' | 关联契约 id 列表 |
| created_at | REAL | epoch 秒 |
| path_hint | TEXT DEFAULT '' | 记录时路径 (仅提示, 解析失败回退旧路径查找) |

- **写入方**: `storage/object_metadata.py` `record_file_object` (证据管线, best-effort 永不阻断产物落盘)。
- **租户作用域**: J。**TTL/保留**: 与 MinIO 对象同生共死 (digest 校验依据)。

### 1.19 object_contracts — 对象×契约关联 (代码 DDL: `storage/object_metadata.py`)

| 列 | 类型 | 说明 |
|---|---|---|
| object_id | VARCHAR(32) | PK (object_id, contract_id) 之一 |
| contract_id | VARCHAR(128) | |

- **写入方**: `storage/object_metadata.py`。**租户作用域**: J。**TTL/保留**: 与 object_metadata 同步。

### 1.20 finding_feedback — Finding 验收反馈 (来源 `0009_finding_feedback.sql` + `0012_finding_feedback_idempotency.sql`; 本文此前漏登记该表)

| 列 | 类型 | 说明 |
|---|---|---|
| id | CHAR(36) PK | UUID |
| job_id | CHAR(36) NOT NULL | 所属验证任务; `idx_feedback_job` |
| tenant_id | VARCHAR(36) NULL | `idx_feedback_tenant` (可空 = 尚未绑定租户的历史写入) |
| finding_id | CHAR(36) NOT NULL | FK -> `findings(id)` ON DELETE CASCADE |
| contract_id | VARCHAR(128) NOT NULL | 被评价的契约 |
| severity | ENUM('BLOCKER','MAJOR','MINOR','NEEDS_CONFIRMATION') | 冗余快照, 便于按级别算接受率 |
| verdict | ENUM('accept','reject') | 唯一取值域 |
| reason | VARCHAR(1000) NULL | reject 的理由 |
| created_by | VARCHAR(128) NOT NULL | 打回人 |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | |

**唯一键 `uniq_feedback_finding_actor (finding_id, created_by)`** —— 由迁移 0012 建立 (先按
`(finding_id, created_by)` 保留最新一行去重, 再加约束)。它是 Go/No-Go #13 的度量契约本身:
一个评审人对一个 finding 只能有一票, 改主意是**覆盖**而不是**加权**。

- **写入方**: `api/routes/feedback.py` (`POST /api/v1/jobs/{job_id}/feedback` ->
  `MySQLStore.insert_feedback`, 该语句是 `INSERT ... AS new ON DUPLICATE KEY UPDATE`, 返回
  `{"state": created|replaced|unchanged, "id": <库中真实行 id>}`; 路由把 `state` 原样回给前端。
  **重述时回显的是库里那一行的 id, 不是调用方新造的 uuid** —— 后者在库里根本不存在)。
- **读取方**: 同路由 `GET /api/v1/jobs/{job_id}/feedback` -> `list_feedback` + `feedback_stats`;
  Go/No-Go #13 的 `acceptance_rate` = accepted/(accepted+rejected), **无反馈的 finding 不计入**
  ("沉默不等于接受"), 分母为 0 时 `acceptance_rate_pct` 为 `null` 而不是 0。
  **2026-09-26 实测的两个缺陷已在同一里程碑修掉并各有一道门**: (a) 这两个读函数原先按位置取列
  (`row[0]`), 而本 store 的连接是 `cursorclass=DictCursor` —— 于是**任何真实调用都抛
  `KeyError: 0`**, 即整条验收反馈读路径在产品数据库上是坏的; (b) 每次 POST 生成新 uuid 且无约束,
  同一个人双击"接受"会在分子里留下两行。
- **租户作用域**: T (有 `tenant_id` 列)。**TTL/保留**: 永久(无自动清理)。
- **产品入口 (2026-09-26 已落地, 工作项 #84)**: `apps/web/src/pages/FindingDetail.tsx` 的
  `FeedbackSection` 是这张表唯一的写入界面 —— 评审人标识存在本机浏览器 (`localStorage`
  `specproof_reviewer`), 它就是"一人一票"键的另一半, 所以页面上如实写明它不是登录账号;
  三种 `state` 各有各的文案 (新票/改票/重复提交不重复计数); 读失败渲染为失败而不是"没人投过";
  0 票时接受率显示"无法计算"。页面只在 `severity ∈ {BLOCKER, MAJOR, MINOR, NEEDS_CONFIRMATION}`
  时才给按钮 —— 本表的 `severity` 与请求模型是同一个 ENUM, 前端词表里多出来的 `INFO`
  (以及检查器为证据族写下的 `NONE`) 存不进任何一行, 允许点击只会换来一个 422。
  **约束本身仍未在产品库落地**: `specproof_phase0` 当前没有 `uniq_feedback_finding_actor`
  (对共享库做 DDL 属需批准操作, 未擅自执行); 它会在共享栈下一次 `ensure_tables()` 启动时由
  0012 收敛 —— 而 FIX-6 (见 `docs/operations/DRILLS.md` §5) 正是为了让那一步能重跑。

---

## 2. MongoDB — 数据库 `specproof_phase0` (compose 服务 mongodb:7.0)

可重建的 checkpoint 与分析文档; 不得成为 Job 终态唯一来源 (演进计划 §4.2)。
集合由 `storage/mongodb.py` `ensure_collections` 创建 (`agent/mongo_saver.py` 构造时调用)。

### 2.1 agent_checkpoints — LangGraph 断点 (崩溃续跑)

| 字段 | 类型 | 说明 |
|---|---|---|
| thread_id | string | = job_id (查找键) |
| checkpoint_id | string | 与 thread_id 组成 unique 索引 |
| parent_checkpoint_id | string? | 父链 |
| checkpoint_ns | string | |
| checkpoint.v / id / ts / channel_values / channel_versions / versions_seen | object | LangGraph Checkpoint 结构 (JsonPlus 序列化) |
| metadata.source / step / writes / parents | object | |
| pending_writes[] | array | 未提交节点输出 |

- **写入方**: `agent/mongo_saver.py` (每节点执行后 upsert; thread_id=job_id)。
- **租户作用域**: J。**TTL/保留**: 无 TTL; job 终态后可删 (DATA_LIFECYCLE §2.2)。

### 2.2 differential_runs — 差分实验产物

- 字段: `job_id`, `contract_id` + 实验载荷 (schema 灵活), `created_at`; 索引 (job_id, contract_id)。
- **写入方**: `storage/mongodb.py` `save_differential_run` (run_differential 节点)。
- **租户作用域**: J。**TTL/保留**: 与 job 同生命周期。

### 2.3 evidence_packs — 证据包 (MinIO sha256 交叉核验链)

- 字段: `job_id`, `contract_id`, `minio_objects[]` ({bucket, object_name}), `created_at`;
  unique 索引 (job_id, contract_id) — upsert (replace_one); created_at 索引。
- **写入方**: `storage/mongodb.py` `save_evidence_pack`; `verify_artifact_chain` 逐对象与 MinIO 存在性/摘要核验。
- **租户作用域**: J。**TTL/保留**: 与 job 同生命周期。

---

## 3. MinIO — 对象存储 (compose 服务 minio: RELEASE.2025-04-08T15-41-24Z)

桶由 `storage/minio.py` `ensure_buckets` 创建; 对象按 job 组织 (路径前缀), 大对象内容
不落 MySQL — MySQL 只存 `object_metadata` 的 digest/大小/类型。无生命周期规则/版本策略内建。

| Bucket | 内容 | 写入方 | 租户 | TTL/保留 |
|---|---|---|---|---|
| specproof-tool-reports | 工具输出报告 | `storage/minio.py` upload/put (证据管线) | J (job 前缀) | 与 job 同生命周期; 无自动清理 |
| specproof-bug-capsules | Bug Capsule zip (可重放证据) | 同上 | J | 证据核心, 租户存在期间永久 |
| specproof-html-reports | HTML 矩阵/报告 | 同上 | J | 与 job 同生命周期 |

治理: `governed_stat` 返回 {bucket, object_name, size_bytes, content_type, sha256};
`get_object` 校验 sha256, 摘要不符即失败 (证据链防篡改)。

---

## 4. Elasticsearch — 检索投影 (compose 服务 elasticsearch:8.16.4)

可删除、可重建的检索投影 (演进计划 §4.2); 单索引全仓库共享。

### 4.1 索引 `specproof-code-phase0`

- settings: number_of_shards=1, number_of_replicas=0。
- mapping (`storage/elasticsearch.py` `ensure_indices`):

| 字段 | 类型 | 说明 |
|---|---|---|
| repo | keyword | 仓库 (隔离维度) |
| tenant_id | keyword | 租户过滤 (查询按 tenant 过滤) |
| source_type | keyword | |
| commit_sha | keyword | 索引快照 commit |
| path | keyword | 文件路径 |
| symbol | keyword | 符号名 |
| language | keyword | python/java 等 |
| content | text | BM25 全文 |
| embedding | dense_vector (HNSW, m=16, ef_construction=100, cosine) | RAG 2.0 向量通道, dims 由配置 |
| start_line / end_line | integer | 符号级行范围 |

- **写入方**: `storage/elasticsearch.py` `index_repository / index_with_embeddings`
  (幂等重索引: delete_repo = 整索引删除+重建; delete_by_query 在 Windows elasticsearch-py 8.19 不可用, 代码已注明)。
- **租户作用域**: R+tenant_id (文档携带 tenant_id, 检索按租户/仓库/commit 过滤)。
- **TTL/保留**: 无 ILM/无 snapshot (诚实边界); 最新快照即可重建。

---

## 5. Redis — 键族总览 (compose 服务 redis:7.4-alpine, maxmemory 256mb allkeys-lru)

原则: **全部键带 TTL, 无永久业务状态** (`storage/redis.py` 注释即产品承诺)。
键前缀 `specproof:*`; 无 tenant 维度 (job_id 内嵌于键)。

| 键族 | 类型/操作 | TTL | 写入方 | 用途 |
|---|---|---|---|---|
| specproof:progress:{job_id} | string (SETEX, JSON) | 600 s | `storage/redis.py` `set_progress` | 进度 (P0.5 兼容, 已弃用) |
| specproof:stream:job:{job_id} | stream (XADD MAXLEN ~1000; `REDIS_STREAM_MAXLEN`/`REDIS_STREAM_TTL_SECONDS` 可配置) | 键 TTL 86400 s | `storage/redis.py` `xadd_progress` (worker 各阶段) | SSE 进度流 (`api/routes/jobs.py` GET /jobs/{id}/progress, Last-Event-ID 续传; 事件载荷带绝对 `sequence` 与保留窗口秩 `seq`) |
| specproof:stream:job:{job_id}:seq | string (INCR, 每事件 +1) | 键 TTL 86400 s (与流同写同过期) | `storage/redis.py` `xadd_progress` | 每作业 SSE 单调序列号计数器 (MAXLEN trim 后仍单调; 供事件载荷 `sequence` 字段) |
| specproof:lease:job:{job_id} | string SET NX EX 30 | 30 s (每阶段续租) | worker acquire/renew; Lua 保证仅持有者可 release | Worker 租约 (防重复处理/失租快速失败) |
| specproof:budget:job:{job_id} | string (DECRBY 消费, 超支回滚) | 7200 s | `storage/redis.py` `init/consume_budget` | LLM token 预算 |
| specproof:lock:scope:{scope} | string SET NX EX ttl，值为持有者 token | 调用方 ttl (回收扫描 120 s) | `storage/redis.py` `acquire_scope_lock` / `release_scope_lock` | 互斥锁（**集群级作业锁**，不是按作业号的锁；释放要求 token 匹配，否则超时的那轮会删掉接班者的锁。唯一读写者是 #71 的周期回收 tick，scope=`stale-job-sweep`；以前的 `specproof:lock:job:{job_id}` 从未被任何代码调用过）|
| specproof:cache:model:{cache_key} | string (SETEX, JSON) | 3600 s (默认) | `storage/redis.py` `cache_llm_response` | LLM 响应语义缓存 |
| specproof:capability:{base_url_hash} | string (SETEX) | 86400 s | `storage/redis.py` `cache_provider_capability` | Provider 能力探测缓存 |
| specproof:idempotent:{event_id} | string SET NX EX 86400 | 86400 s | `storage/rabbitmq.py` `make_idempotency_check` | RabbitMQ 消息幂等 (重复投递丢弃) |

---

## 6. RabbitMQ — 事件传输拓扑 (compose 服务 rabbitmq:4.0-management-alpine)

事件传输, 不是查询数据库 (演进计划 §4.2)。拓扑由 `storage/rabbitmq.py` `ensure_topology`
声明 (worker 启动与 `storage/outbox_relay.py` 各自调用, 幂等)。

| 对象 | 名称 | 说明 |
|---|---|---|
| exchange (P1) | specproof.p1.commands (direct, durable) | 生产命令交换机 |
| queue (P1) | q.p1.verify.job | 验证任务主队列; 手动 ack, prefetch=1, x-dead-letter→.dlq |
| queue (P1) | q.p1.verify.job.retry | 重试队列; per-message TTL (1s/5s/30s, max_retries=3) 到期重回主队列 |
| queue (P1) | q.p1.verify.job.dlq | DLQ: 无 TTL, 永久滞留 (等运维重放; 无自动告警 — 诚实边界) |
| exchange (P0 兼容) | specproof.phase0.commands | 4 条 legacy 队列: q.phase0.contract.compile / static.scan / differential.run / finding.replay (长期空转) |

- **写入方**: Outbox Relay 发布 (publisher confirm); worker 消费 (idempotency_fn=Redis SETNX)。
- **租户作用域**: — (队列无租户维度; 消息载荷含 job_id/event_id)。**保留**: 消费即删; DLQ 永久。

---

## 7. 租户作用域总览 (跨存储对照)

| 存储 | 租户维度 | 实施方式 |
|---|---|---|
| MySQL verification_jobs / outbox / users / billing_* | tenant_id 列 | 写入端从请求作用域盖戳 (`storage/tenant_scope.py`); 读取端仓库层过滤 (auditor 例外); 越权 404 + attempted_tenant 审计 |
| MySQL audit_logs | attempted_tenant | 越权取证 |
| MySQL findings/contracts/object_* | 经 job_id 关联 | 无独立租户列 |
| MySQL contract_registry | repo_path | 仓库级隔离, 无租户列 (诚实边界) |
| MySQL agent_jobs | — | 单租户投影 (诚实边界) |
| MongoDB 三集合 | job_id | 无 tenant 字段 |
| MinIO 三桶 | job 前缀路径 | 无桶级多租户 |
| Elasticsearch | repo + tenant_id 字段 | 查询强制过滤 |
| Redis / RabbitMQ | 键/消息内嵌 job_id | 无租户结构 |

## 8. 事实来源清单 (写入方代码定位)

- MySQL 迁移: `infra/mysql/migrations/0001_init.sql` … `0012_finding_feedback_idempotency.sql` (down 文件在 `infra/mysql/migrations/down/`; 0011 是 2026-09-26 为 `agent_jobs` 补的那一份, 它的缺失曾让全新安装比线上少一张表; 0012 是同日为 `finding_feedback` 加的那份约束)。
- MySQL 业务/状态: `storage/mysql.py`; 迁移执行: `storage/migrations.py`。
- Finding 验收反馈 (Go/No-Go #13): `storage/mysql.py` `insert_feedback`/`feedback_stats` + `api/routes/feedback.py` (Web 侧无入口, 见 §1.20)。
- 租户身份: `storage/identity.py` + `api/identity/store.py` + `api/routes/admin.py`。
- 计费: `storage/billing.py` (计量钩子: `agent/worker.py`)。
- Agent 任务: `storage/agent_jobs.py` + `api/agent_runtime.py` + `api/routes/agent_console.py`。
- 对象元数据: `storage/object_metadata.py`。检索: `storage/elasticsearch.py`。
- 文档/检索引擎: `storage/mongodb.py` + `agent/mongo_saver.py`。
- 对象存储: `storage/minio.py`。缓存/租约/流: `storage/redis.py`。事件: `storage/rabbitmq.py` + `storage/outbox_relay.py`。
- 保留/清理操作: `docs/operations/DATA_LIFECYCLE.md`。
