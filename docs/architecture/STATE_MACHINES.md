# 状态机说明 (STATE_MACHINES) — Verify Job 与 Craft Job 冻结定义 × 当前实现映射

> 口径: “冻结定义” = `docs/持续演进终极目标与链路计划.md` §4.3 (Verify) 与 §4.4 (Craft)
> (演进计划, 产品目标态); “当前实现” = 本仓库 `storage/mysql.py` / `storage/agent_jobs.py` /
> `craft/loop.py` / `api/routes/jobs.py` / `api/routes/agent_console.py` /
> `api/agent_runtime.py` / `agent/worker.py` / `agent/job_control.py` 的实际代码,
> 经逐文件核对 (2026-08-19, 分支 feature/interview-hardening)。§2.2 / §2.5 / §3 于
> 2026-08-20 更新 (backlog #5: stale-RUNNING 回收器 + WAITING_FOR_PROVIDER 接线)。
> 每张实现表都标注“白名单允许” 与 “生产代码实际发出” 两个口径 —
> 两者不一致处即诚实边界, 不粉饰。

---

## 1. Verify Job 状态机 — 冻结定义 (演进计划 §4.3)

### 1.1 冻结主链

`QUEUED → PREPARING → CONTRACT_REVIEW → RUNNING → REVIEWING →
VERIFIED | BLOCKED | NEEDS_REVIEW | FAILED | CANCELLED | STALE | EXPIRED`

### 1.2 终态语义 (冻结)

| 终态 | 含义 (冻结原文要求) |
|---|---|
| VERIFIED | 全部契约通过、证据齐全 |
| BLOCKED | 确认存在阻断性回归, 或策略禁止 |
| NEEDS_REVIEW | 发现或契约证据不足, 需要人工判断 |
| FAILED | **只表示系统无法完成验证, 不表示代码一定有问题** |
| CANCELLED | **只能由用户或管理员明确触发** |
| STALE | Head 已被新 Job 替代 |
| EXPIRED | 超过保留或执行期限 |

### 1.3 冻结硬约束

1. 状态转换必须由服务端白名单控制。
2. 每次转换写审计和事件。
3. 终态语义不得挪用 (尤其 FAILED 与 BLOCKED 的区分)。

---

## 2. Verify Job 状态机 — 当前实现映射

### 2.1 实际枚举 (迁移 0002, `infra/mysql/migrations/0002_cancel_audit.sql`)

`verification_jobs.status` 为 10 态 ENUM:
`PENDING, QUEUED, RUNNING, WAITING_FOR_PROVIDER, VERIFIED, BLOCKED, STALE, FAILED, CANCELLED, ERROR`

### 2.2 白名单转移表 (`storage/mysql.py` `_VALID_TRANSITIONS`) × 生产发出方

CAS 实现: `transition_job_status` 执行 `UPDATE ... WHERE id = %s AND status = %s`,
rowcount==1 才算成功; 静态非法转移抛 `InvalidStateTransition`; 成功后写审计行 (P0-A5)。

| 从 → 到 | 白名单 | 生产代码实际发出方 | 说明 |
|---|---|---|---|
| PENDING → QUEUED | ✅ | `storage/mysql.py create_job_with_outbox` (`api/routes/jobs.py` POST /jobs, `api/routes/webhooks.py` GitHub PR) | 与 Outbox 行同一事务内的直接 UPDATE (不走 CAS 校验, 不产生审计行); PENDING 只是事务内瞬态 |
| PENDING → ERROR | ✅ | **无生产调用点** (仅测试) | 白名单预留 |
| QUEUED → RUNNING | ✅ | `agent/worker.py` (lease 获取后, 读当前状态 CAS) + `claim_job` 辅助 | worker_id 一并写入 |
| QUEUED → CANCELLED | ✅ | `api/routes/jobs.py` POST /jobs/{id}/cancel | 仅用户/管理员入口, 符合冻结语义 |
| QUEUED → STALE | ✅ | **无生产调用点** (`mark_stale_for_head` 仅测试调用) | 白名单预留; PR 同 Head 再触发不会把旧 Job 置 STALE |
| QUEUED → ERROR | ✅ | **无生产调用点** | 白名单预留 |
| RUNNING → VERIFIED / BLOCKED / FAILED | ✅ | `agent/worker.py` 终态 (见 §2.4 映射表) | 终态 = 管线**真实结果**, 绝不无条件 VERIFIED |
| RUNNING → CANCELLED | ✅ | API cancel CAS; worker 在阶段边界感知后以 `cancelled_at_checkpoint` 落审计 | worker 不再产生任何副作用 (§14 任务 8) |
| RUNNING → STALE | ✅ | **无生产调用点** | 白名单预留 |
| RUNNING → WAITING_FOR_PROVIDER | ✅ | `agent/worker.py` 异常路径 → `MySQLStore.enter_provider_wait` (2026-08-20 backlog #5) | 可重试 provider 故障 (429/5xx, class=provider+retryable) 且 retry_count<max_retries 时停放; 审计 `job_provider_wait_entered`; 不可重试/预算耗尽仍走 classify_job_error → FAILED |
| RUNNING → ERROR | ✅ | **无生产调用点** (仅测试/演练脚本) | 白名单预留 |
| RUNNING → QUEUED | ❌ (白名单外) | `MySQLStore.reclaim_stale_running` + `agent/worker.py reclaim_stale_running_jobs` (2026-08-20 backlog #5) | 回收器专用 CAS: `status='RUNNING' AND updated_at < NOW(3) - INTERVAL ttl SECOND` + Redis 租约心跳探测 (lease key 存在=存活); 审计 `job_reclaimed_stale_running`; 幂等 (重复调用不产生重复转移); worker_id 清空、retry_count+1 |
| WAITING_FOR_PROVIDER → QUEUED / FAILED | ✅ | `MySQLStore.recover_provider_wait` + `agent/worker.py recover_waiting_for_provider_jobs` (2026-08-20 backlog #5) | 预算内 (retry_count<max_retries) → QUEUED (retry_count+1, 重投递新 event_id); 超限 → FAILED (`provider_wait_retries_exhausted`)。RUNNING / CANCELLED / ERROR 分支仍无生产调用点 |
| FAILED → QUEUED | ✅ | **无生产调用点** (无 retry 端点; retry_count/max_retries 列预留) | 白名单预留 |
| FAILED → CANCELLED | ✅ | `api/routes/jobs.py` POST /jobs/{id}/cancel | FAILED 非终态 (见下) |
| FAILED → ERROR | ✅ | **无生产调用点** | 白名单预留 |
| STALE / VERIFIED / BLOCKED / CANCELLED / ERROR → 任意 | ❌ | — | `TERMINAL_STATUSES = {VERIFIED, BLOCKED, STALE, CANCELLED, ERROR}`; **FAILED 不在终态集合** (可重试/可取消) |

### 2.3 API 取消入口的允许前置状态 (`api/routes/jobs.py`)

`POST /jobs/{job_id}/cancel` 仅接受前置状态 `QUEUED / RUNNING / WAITING_FOR_PROVIDER / FAILED`;
终态 (VERIFIED/BLOCKED/STALE/CANCELLED/ERROR) 返回 409 STATE_CONFLICT — 终态不可变。

### 2.4 Worker 终态判定 (`agent/worker.py _terminal_status_from_state`)

| 管线状态 | 终态 | 理由 |
|---|---|---|
| state.errors 非空 | FAILED | 坏引用/缺 spec/Maven 错误等系统无法完成 |
| confirmed_findings 非空 | BLOCKED | 有确认 Finding, 人类必须看 |
| matrix.unverified > 0 | BLOCKED | 有契约未验证, VERIFIED 绝不伪造 |
| 全部通过且零 Finding | VERIFIED | |

异常路径: 未捕获异常经 `agent/job_control.py classify_job_error` 统一分类
({class: system|repo|provider|policy|unknown, code, retryable, note} JSON 写进 last_error) → FAILED;
例外 (2026-08-20 backlog #5): class=provider 且 retryable (429/5xx) 且 retry_count<max_retries
时 → WAITING_FOR_PROVIDER (`enter_provider_wait`, 审计 `job_provider_wait_entered`),
由 `recover_provider_wait` 恢复 (预算内 → QUEUED, 超限 → FAILED);
取消检查点 (每个执行前后 + LLM 重试前 + 图阶段边界) 命中 → CANCELLED (`cancelled_at_checkpoint`);
租约丢失 → FAILED (`lease_lost`), 停止一切业务写入。

### 2.5 审计与事件口径 (对照冻结约束 2)

| 项目 | 实现 | 差异 |
|---|---|---|
| 状态转换审计 | `transition_job_status` 成功后写 `audit_logs` (job_status_transition) | ✅ 已实现 |
| 取消审计 | job_cancelled (API) / job_cancelled_at_checkpoint (worker) | ✅ 已实现 |
| 回收审计 (RUNNING→QUEUED) | `record_audit(action=job_reclaimed_stale_running)` (backlog #5) | ✅ 已实现 |
| Provider 等待进入审计 | transition 审计 + `record_audit(action=job_provider_wait_entered)` (backlog #5) | ✅ 已实现 |
| 回收转移走白名单 | 回收器专用 CAS UPDATE (同 `mark_stale_for_head` 直写型, 附时间谓词) | ⚠️ 差异 |
| PENDING→QUEUED | 事务内直接 UPDATE, 无审计行 | ⚠️ 差异 |
| mark_stale_for_head | 直接 UPDATE, 无审计行、不走 CAS | ⚠️ 差异 (且无生产调用点) |
| 每转换写事件 | 仅 JobCreated 入 Outbox; 状态转换不产事件 | ⚠️ 差异 (冻结要求每次转换写事件) |

---

## 3. Verify 冻结定义 vs 当前实现 — 差异对照表

| 维度 | 冻结 (§4.3) | 当前实现 | 判定 |
|---|---|---|---|
| 主链状态 | QUEUED → PREPARING → CONTRACT_REVIEW → RUNNING → REVIEWING | PENDING → QUEUED → RUNNING (管线阶段只体现在 Redis 进度流, 不落 MySQL 状态) | ⚠️ 差异: 中间态未实现 |
| 终态集合 | VERIFIED/BLOCKED/NEEDS_REVIEW/FAILED/CANCELLED/STALE/EXPIRED | VERIFIED/BLOCKED/FAILED/CANCELLED/STALE/ERROR (+ 运行态 PENDING/WAITING_FOR_PROVIDER) | ⚠️ 差异 |
| NEEDS_REVIEW | 证据不足 → 人工判断 | 未实现 (unverified>0 现行归 BLOCKED) | ⚠️ 语义差异 |
| EXPIRED | 超保留/执行期限 | 未实现 (列不存在) | ❌ 缺 |
| PREPARING/CONTRACT_REVIEW/REVIEWING | 独立状态 | 未实现 | ❌ 缺 |
| WAITING_FOR_PROVIDER | (冻结无) | 有枚举+白名单; 2026-08-20 已接线: worker 将可重试 provider 故障停放此状态 (enter_provider_wait), recover 路径回 QUEUED (预算内) / FAILED (超限) | ⚠️ 预留 → 已接线 |
| ERROR | (冻结无) | 终态, 无生产写入方 (基础设施错误实际记入 FAILED) | ⚠️ 预留 |
| FAILED 语义 | 系统无法完成验证, ≠ 代码有问题; 冻结下 FAILED 为终态 | FAILED=管线错误终态, **可重试 (→QUEUED)/可取消**, 与 BLOCKED 区分正确 | ✅ 语义主体一致; ⚠️ 终态性不同 |
| CANCELLED 语义 | 仅用户/管理员触发 | 仅 API cancel (worker 检查点只是配合落审计) | ✅ 一致 |
| STALE 语义 | Head 被新 Job 替代 | 语义一致 (stale_replaced_by), 但无生产调用点 | ⚠️ 有语义无触发 |
| 服务端白名单 | 要求 | `_VALID_TRANSITIONS` + CAS | ✅ 一致 |
| 每次转换审计 | 要求 | 见 §2.5 (两处直写无审计) | ⚠️ 基本一致 |
| 每次转换事件 | 要求 | 无 (仅 JobCreated) | ❌ 缺 |

---

## 4. Craft Job 状态机 — 冻结定义 (演进计划 §4.4)

### 4.1 冻结主链

`QUEUED → PLANNING → PLAN_READY → EXECUTING → SELF_VERIFYING → HANDOFF_VERIFY →
DONE | FAILED | STUCK | CANCELLED | EXPIRED`

### 4.2 冻结语义与硬约束

| 项 | 要求 |
|---|---|
| PLAN_READY | **真正的人机协同点**: 计划展示目标文件、命令、风险、预计成本、禁止操作、可能触发外部服务的步骤、预计变更规模; **只有计划批准后才允许写入** |
| 工具调用审计 | 每个工具调用写 tool_call、tool_result、输入摘要、输出摘要、资源消耗、决策来源 |
| SELF_VERIFYING → HANDOFF_VERIFY | 自校验通过也只能到 HANDOFF_VERIFY, 由**独立 SpecProof** 创建验证任务 |
| 终态 | DONE / FAILED / STUCK / CANCELLED / EXPIRED |

> 注: `docs/design/SPECCRAFT_PLAN.md` 附录 C 载有早期 10 态转移表
> (`QUEUED → PLANNING → PLAN_READY → EXECUTING → SELF_VERIFYING → DONE|FAILED|STUCK|CANCELLED|EXPIRED`,
> 无 HANDOFF_VERIFY)。以演进计划 §4.4 为准, 附录 C 视为旧版本。

---

## 5. Craft Job 状态机 — 当前实现映射 (三层)

### 5.1 层一: craft/loop.py 本地循环终态 (CLI 事实)

`craft/loop.py` 报告终态 `result ∈ {DONE, FAILED, STUCK, CANCELLED, EXPIRED}` (report.json):

| 终态 | 触发点 (代码) | 说明 |
|---|---|---|
| DONE | `run()` 全部步骤绿 | 唯一“完成”声明 |
| FAILED | 步骤收敛失败 / `_tool_gate` 工具调用超预算 | 另有: 自校验门 failed 且 result==DONE → **DONE 覆盖为 FAILED** (编辑不回滚, report 诚实说明) |
| STUCK | 同类错误连续 3 次 (loop 诊断循环) | 不无限烧预算 |
| CANCELLED | supervisor cancel (store.status==cancelled) 于步骤边界感知 | checkpoint 记录 verdict=cancelled |
| EXPIRED | `_time_gate` 超 deadline (默认 60 分钟) | 超限即停止并诚实交付当前状态 |

### 5.2 层二: storage/agent_jobs.py 持久投影 (5 态, 三后端同语义)

`agent_jobs.status ∈ {pending, running, succeeded, failed, cancelled}`。
转移规则 (`storage/agent_jobs.py`, 每后端同语义, 一致性由单测锁定):

| 操作 | 规则 |
|---|---|
| update_status | 任何**非终态**可转任何非终态 (含 pending→succeeded); 终态只接受同状态 (幂等 no-op), 其他目标抛 InvalidJobTransitionError |
| lease | 授予成功时 pending→running (started_at 写一次); 终态拒绝 |
| renew/release | 仅持有者可续/可释放; 终态无租约 |
| set_plan / set_progress | 终态拒绝 (InvalidJobTransitionError) — cancel 优先于迟到投影 |
| cancel | **唯一无条件覆盖**: 任何状态 → cancelled (含 succeeded/failed), 幂等, 清租约, 写 finished_at — cancel wins |
| attach_accept_result | 仅 succeeded/failed 可挂 accept_json; first-write-wins (终态不可变, 重复为幂等 no-op) |

与 loop 终态的映射 (`craft/loop.py _finish`): `DONE → succeeded`; `FAILED/STUCK/EXPIRED → failed`;
`CANCELLED → store.cancel` (loop 不写终态投影, supervisor 的 cancel 永远优先)。

### 5.3 层三: Web Agent 控制台词汇与端点 (`api/routes/agent_console.py` + `api/agent_runtime.py`)

| console 状态 | store 状态 | 含义 |
|---|---|---|
| PLANNING | pending 无 plan_json | 计划生成中 |
| AWAITING_APPROVAL | pending 有 plan_json | **人机协同点 (近似 PLAN_READY)** |
| EXECUTING | running | loop 执行中 |
| COMPLETED | succeeded | 终态 |
| FAILED | failed | 终态 |
| CANCELLED | cancelled | 终态 |

端点:
- `POST /agent/jobs` (auto_start) → create (pending) → runtime 线程跑真实确定性 CraftLoop
  (无 LLM、无网络; 计划 SSE 事件 + 工具调用 SSE 事件)。
- `POST /agent/jobs/{id}/approve` target=plan: approve→running / reject→failed;
  target=step: 逐步批准, 全部批准→running, 任一拒绝→failed; target=gate: approve→succeeded / reject→failed;
  终态拒绝审批 (409)。
- `POST /agent/jobs/{id}/cancel` → 协作取消标志 + store.cancel (cancel wins); 终态拒绝 (409)。
- `GET /agent/jobs/{id}/events` SSE: plan/progress/tool_call/tool_result/edit/gate 事件流。
- 工具调用审计 (对冻结要求): `api/agent_runtime.py _EventedEditor` 为每次 read_file/apply_edit/
  write_file 发布 tool_call/tool_result/edit 事件; CLI 侧编辑审计落 `.specraft/jobs/{id}/audit.jsonl` 与
  report.audit_trail; 资源消耗在 report.budget_used。输入/输出摘要、决策来源为部分对齐 (见 §6)。

### 5.4 验收闭环 (`craft/accept.py`, `craft/gates.py`)

`craft accept` = 五道门禁摘要 + SpecProof 独立验证 + Merge Certificate (Ed25519)。
`AcceptVerdict ∈ {VERIFIED, BLOCKED, ERROR}`。runtime lane 只挂门禁摘要投影,
**永不声明 VERIFIED** (完整闭包需 git base/head + 签名密钥, 归 `specproof craft accept` CLI)。

---

## 6. Craft 冻结定义 vs 当前实现 — 差异对照表

| 维度 | 冻结 (§4.4) | 当前实现 | 判定 |
|---|---|---|---|
| 主链状态数 | 10 态 | store 5 态 (pending/running/succeeded/failed/cancelled) + loop 本地终态 (DONE/FAILED/STUCK/CANCELLED/EXPIRED) | ⚠️ 差异: 冻结态未全部投影 |
| PLANNING | 独立状态 | pending 无 plan (console PLANNING 标签) | ⚠️ 近似 |
| PLAN_READY | 独立状态 + 批准后才允许写入 | pending 有 plan_json (console AWAITING_APPROVAL) + approve 端点 | ⚠️ 近似; **auto_start 默认绕过批准直接执行** (诚实边界) |
| EXECUTING | 独立状态 | running | ✅ 对应 |
| SELF_VERIFYING | 独立状态 | 无独立状态; 自校验在 `_finish` 内同步跑 (failed→DONE 覆盖 FAILED) | ⚠️ 语义在, 状态不在 |
| HANDOFF_VERIFY | 独立状态, 独立 SpecProof 验证 | 无独立状态; 以 `craft accept` 闭包近似; runtime lane 不声明 VERIFIED | ⚠️ 近似 |
| STUCK / EXPIRED | 独立终态 | loop 报告区分, store 统一投影 failed | ⚠️ 投影合并 |
| CANCELLED | 终态 | store.cancel 无条件覆盖 (cancel wins) | ✅ 一致 |
| 终态不可变 | 是 | 终态只接受同状态; attach_accept_result 为例外 (first-write-wins) | ✅ 一致 |
| 工具调用审计 | tool_call/tool_result/输入摘要/输出摘要/资源消耗/决策来源 | tool_call/tool_result/edit SSE + audit.jsonl + audit_trail + budget_used | ⚠️ 主体实现, 摘要字段部分对齐 |
| 事件 | (演进计划 §4.2: 异步事件带 event_id/trace_id 等信封) | agent_jobs 投影无 Outbox 事件 (M4 未接线) | ❌ 缺 |

---

## 7. 引用文件清单 (实现核对出处, 全部存在)

- 冻结定义: `docs/持续演进终极目标与链路计划.md` §4.3/§4.4; 旧版 Craft 转移表: `docs/design/SPECCRAFT_PLAN.md` 附录 C。
- Verify 实现: `storage/mysql.py` (白名单/CAS/审计), `api/routes/jobs.py` (创建/取消/SSE),
  `agent/worker.py` (终态映射/检查点), `agent/job_control.py` (错误分类/取消检查点),
  `infra/mysql/migrations/0001_init.sql` + `0002_cancel_audit.sql` (枚举)。
- Craft 实现: `craft/loop.py` (终态/门禁), `storage/agent_jobs.py` (5 态投影/租约/cancel/accept),
  `api/routes/agent_console.py` + `api/agent_runtime.py` (控制台词汇/approve/cancel/事件),
  `craft/accept.py` + `craft/gates.py` (验收闭包)。
