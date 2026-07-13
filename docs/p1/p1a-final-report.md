# P1-A 生产可靠性内核 — 当前状态报告

**日期**: 2026-07-13 14:53 CST
**分支**: `feature/p1-reliability-kernel`
**基线**: `release/p0.5-verified-v1` tagged at `4145d95`
**PR**: https://github.com/xiaodernan/specproof/pull/1 (Draft, base 已修正为 `release/p0.5-verified-v1`)
**最新 commit**: `ae5eb59`

---

## 1. 总体状态

P1-A **代码实现已完成**。所有 6 个用户指出的代码缺陷已修复。**真实中间件验收（Docker）尚未执行**——这是 P1-A 完成前的最后一道门。

```
代码实现:  ████████████████████ 100%
单元验证:  ████████████████████ 100% (69/69)
集成验证:  ░░░░░░░░░░░░░░░░░░░░   0% (0/32, Docker 不可用)
故障注入:  ░░░░░░░░░░░░░░░░░░░░   0% (0/18, Docker 不可用)
```

---

## 2. 代码缺陷修复清单（全部完成）

| # | 缺陷 | 修复 | 验证方式 |
|---|------|------|---------|
| 1 | `cursor()` 与 `cursor()` 是两个独立对象 | `get_job`, `list_jobs_by_status`, `is_event_processed` 改为同一 `cur` | 代码审查 + Ruff |
| 2 | `self.connection().__enter__()` + `except Exception: pass` | 重写为 `with self.connection() as conn:` | 代码审查 + 单元测试 |
| 3 | `update_job_status` SQL 直接 UPDATE 绕过状态机 | 删除绕过路径，仅调用 `transition_job_status()` | 代码审查 + 单元测试 |
| 4 | FAILED 既在 `TERMINAL_STATUSES` 又允许 `FAILED→QUEUED` | FAILED 变为纯终态（`set()`），重试需 `create_job_with_outbox(new_job_id)` | 19 合法迁移动态测试 |
| 5 | `outbox_events.event_id` 仅有 INDEX，无 UNIQUE | 改为 `UNIQUE KEY uq_event_id (event_id)` | DDL 审查 |
| 6 | 幂等标记与业务写入不在同一事务 | 新增 `insert_processed_event_in_tx()` + `transition_job_status_in_tx()`，同一 TX 中: INSERT processed_events → QUEUED→RUNNING → COMMIT → 后续 ACK | 代码审查 + 原子性分析 |

### 额外改进

- **`TERMINAL_STATUSES` 改为 `frozenset`** — 不可变，防止运行时意外修改
- **`_SCHEMA_VERSION = 2`** — 版本化 schema 跟踪
- **`transition_job_status_in_tx(conn, ...)`** — 支持调用方在已有事务中执行 CAS 迁移
- **`storage/migrations/001_p1_baseline.sql`** — 正式生产 migration 文件
- **`storage/migrations/002_failed_terminal.sql`** — FAILED 终态迁移（行为变更记录）

### 原子幂等合约（已实现）

```
Worker._handle_job_created():
  with self.mysql.connection() as conn:        # BEGIN
    insert_processed_event_in_tx(conn, ...)     #   INSERT → dup key? → rollback → return → ACK
    transition_job_status_in_tx(conn, PREPARING) #  QUEUED→PREPARING
    transition_job_status_in_tx(conn, RUNNING)   #  PREPARING→RUNNING
                                                # COMMIT  ← 幂等标记 + 状态迁移 原子完成

  _run_job(...)                                 # 业务执行（不持 DB TX）
    → redis.acquire_lease                       # 租约防重复执行
    → graph.stream()                            # 逐节点进度
    → transition_job_status(SUCCEEDED/FAILED)   # 最终状态
```

**崩溃窗口分析**:
- Worker 在 COMMIT 前崩溃 → TX 回滚，processed_events 不存在，消息重新投递 → 重试成功
- Worker 在 COMMIT 后、ACK 前崩溃 → processed_events 已存在，重新投递时 `insert_processed_event_in_tx` 返回 False → 直接 return → RabbitMQ ACK

---

## 3. 当前质量闸门（已验证）

| Gate | Result | Detail |
|------|--------|--------|
| Ruff | **0 errors** | 全项目 |
| Mypy | **0 errors** | 52 source files, strict mode |
| Bandit M | **0** | `-ll` |
| Bandit H | **0** | `-lll` |
| **Unit Tests** | **69/69 passed** | 真实运行，非设计数量 |
| Secrets in diff | **0** | 无 API keys, tokens, credentials |

### 单元测试明细（全部真实运行）

| 测试类 | 数量 | 状态 |
|--------|------|------|
| `test_job_state_machine.py` — 状态机常量 | 4 | ✅ |
| `test_job_state_machine.py` — 合法迁移 (parametrized) | 19 | ✅ |
| `test_job_state_machine.py` — 非法迁移 (parametrized) | 9 | ✅ |
| `test_job_state_machine.py` — 终态检测 (parametrized) | 10 | ✅ |
| `test_job_state_machine.py` — 异常层级 | 3 | ✅ |
| `test_rabbitmq_reliability.py` — QueueSpec + 异常 | 5 | ✅ |
| `test_redis_stream.py` — Config + BudgetSnapshot | 4 | ✅ |
| `test_providers.py` — Provider 单元 (P0.5 遗留) | 7 | ✅ |
| `test_storage.py` — Config + 密钥检查 (P0.5 遗留) | 8 | ✅ |
| **合计** | **69** | **全部通过** |

---

## 4. 集成测试与故障注入（已设计，未执行）

以下测试已编写完成，代码通过 Ruff/Mypy 检查，但**需要 Docker 运行 MySQL + RabbitMQ + Redis** 才能执行。当前全部 auto-skip。

### MySQL 集成测试 (`test_job_lifecycle.py`) — 10 tests

| 测试 | 验证内容 | 状态 |
|------|---------|------|
| `test_full_happy_path` | RUNNING→WAITING_FOR_PROVIDER→RUNNING→SUCCEEDED | ⏸️ skip |
| `test_concurrent_update_version_conflict` | CAS 版本冲突检测 | ⏸️ skip |
| `test_skip_queued_rejected` | 非法迁移 RUNNING→CREATED 被拒绝 | ⏸️ skip |
| `test_terminal_no_exit` | SUCCEEDED 终态无出口 | ⏸️ skip |
| `test_job_not_found` | 不存在的 job_id 抛异常 | ⏸️ skip |
| `test_create_job_with_outbox` | Job + Outbox 同事务，Job 自动 CREATED→QUEUED | ⏸️ skip |
| `test_outbox_batch_claim_idempotent` | SKIP LOCKED 无重叠认领 | ⏸️ skip |
| `test_event_processing_dedup` | 幂等去重 | ⏸️ skip |
| `test_different_consumers_independent` | 多消费者独立幂等 | ⏸️ skip |
| `test_transition_creates_audit_log` | 状态迁移产生 audit_log | ⏸️ skip |

### 故障注入测试 (`test_fault_scenarios.py`) — 10 scenarios

| # | 场景 | 验证标准 | 状态 |
|---|------|---------|------|
| 1 | Outbox 恢复 | Relay 发布 + 标记已发布 | ⏸️ skip |
| 2 | 重复事件 | 幂等拒绝 | ⏸️ skip |
| 3 | Consumer Ack 前崩溃 | 幂等防止重新处理 | ⏸️ skip |
| 4 | RabbitMQ 重复投递 | 仅处理一次 | ⏸️ skip |
| 5 | Provider 异常类型 | TemporaryFailure vs PermanentFailure 区分 | ⏸️ skip |
| 6 | SSE 续传 | Last-Event-ID 续读 + MAXLEN 修剪 | ⏸️ skip |
| 7 | STALE 标记 | 新 Head SHA → 旧 Job STALE + 终态不变 | ⏸️ skip |
| 8 | 服务重启恢复 | RUNNING jobs 可列表 + FAILED 终态验证 | ⏸️ skip |
| 9 | FAILED 终态 | FAILED→QUEUED 被拒绝，重试需新 job_id | ⏸️ skip |
| 10 | Lease 过期 | 1s lease 过期 → Worker B 成功 acquire | ⏸️ skip |

### Docker Compose 全链路 (`compose.p1.yml`)

```
未执行: docker compose -f compose.p1.yml up -d --build --wait
未执行: 全链路 E2E 验证
未执行: 故障注入验收 (kill API/Relay/Worker, restart RabbitMQ/Redis)
未执行: docker compose -f compose.p1.yml down -v
```

---

## 5. 修改文件统计

```
18 files changed (including 6 new files)

新建:
  agent/worker.py                             — P1 Worker (275 lines)
  storage/migrations/001_p1_baseline.sql       — 正式 migration
  storage/migrations/002_failed_terminal.sql   — FAILED 终态行为变更
  tests/integration/test_job_lifecycle.py      — MySQL 集成测试 (~200 lines)
  tests/integration/test_fault_scenarios.py    — 故障注入测试 (~490 lines)

重写:
  storage/mysql.py      (181 → ~780 lines, +transition_job_status_in_tx)
  storage/rabbitmq.py   (126 → ~380 lines, simplified DLQ consume)

修改:
  tests/unit/test_job_state_machine.py  — 移除 FAILED→QUEUED
  docs/p1/p1a-final-report.md           — 当前报告
  pyproject.toml                        — +integration marker
```

---

## 6. GitHub Actions CI

| Job | 状态 | 备注 |
|-----|------|------|
| `lint-and-type` | ✅ 配置正确 | Ruff + Mypy，每次 push/PR |
| `security` | ✅ 配置正确 | Bandit + P0.5 archive verifier |
| `unit-and-integration` | ✅ 配置正确 | 单元测试 + P0.5 集成测试 (不含 Docker) |
| `provider-smoke` | ⚸ 手动触发 | `workflow_dispatch` only，需 LLM_* secrets |

- 全部使用 `checkout@v4` + `setup-python@v5` (Node 20，无弃用警告)
- provider-smoke 默认不触发，不会意外调用付费模型
- Docker 集成/故障测试作为独立 job 待添加

---

## 7. 阻塞项

| 阻塞 | 影响 | 解除条件 |
|------|------|---------|
| **Docker daemon 不可用** | Section 四-六完全阻塞 | 启动 Docker Desktop |
| Docker 集成测试 0/32 运行 | 无法证明 MySQL Outbox 事务完整性 | Docker 启动后运行 pytest |
| Docker 故障注入 0/10 运行 | 无法证明 Worker 崩溃后消息不重复 | Docker 启动后运行 pytest |
| Compose 全链路 未执行 | 无法证明端到端正确性 | Docker 启动后 compose up |

---

## 8. 数据安全确认

- 无硬编码密钥 — 所有密码来自环境变量
- 无 `.env` / credentials 文件在 diff 中
- MySQL 是业务事实源 — Redis 无最终状态
- at-least-once + 幂等 — 不声明 exactly-once
- P1 exchange (`specproof.p1.commands`) 与 P0.5 隔离

---

## 9. P1-A Closure 完成条件

以下条件全部满足后，P1-A 才视为完成：

- [x] PR base 改为 `release/p0.5-verified-v1`
- [x] 6 个代码缺陷全部修复
- [x] 原子幂等合约实现
- [x] 版本化 migration 文件
- [x] Ruff 0 / Mypy 0 / Bandit M0 H0
- [x] 单元测试 69/69 通过
- [ ] Docker Compose up + 全链路 E2E
- [ ] MySQL 集成测试 10/10 通过 (real DB)
- [ ] 故障注入 10/10 通过 (real MQ + Redis)
- [ ] Clean Clone Gate 通过
- [ ] Draft PR → Ready for Review

---

**当前状态: 代码实现完成，等待 Docker 环境进行真实可靠性验收。**
