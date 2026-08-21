# SpecProof 故障演练与安全响应手册 (DRILLS)

> 依据: W67 "双演练" 交付 (worker-kill 恢复 + 安全响应); 计划书 §18.5 事故处理 (暂停/隔离/保留/撤销/通知/影响评估); 工业化指南 §15.4 (发布前至少一次恢复演练 + 一次安全响应演练); 主计划 §14.2 outbox 治理。
> 与 DATA_LIFECYCLE.md 的关系: 本文执行"故障恢复"与"安全响应"两类演练; DATA_LIFECYCLE 负责数据保留/删除/导出/备份恢复。备份/恢复命令两文一致, 冲突以本文为准并同步修改 DATA_LIFECYCLE。
> 演练日期: 2026-08-19 (工作树 feature/interview-hardening, 单写者车道)。

状态标注约定 (与 DATA_LIFECYCLE.md 相同制度):

- ✅ 已演练 — 今日在真实基础设施上执行, 真实输出记录在本文 (输出为执行时的原样 JSON)。
- 📝 桌面核对 — 未对生产状态动手, 但逐条对照源码/迁移/实测命令语法与可用性, 输出记录在本文。
- ⏳ 待基础设施/需开发 — 需要未实现的自动化或未接线的能力, 给出精确命令或缺口说明。

演练环境 (2026-08-19 实测): Windows 主机, Docker Desktop 运行中 — specproof-mysql (8.4, healthy), specproof-rabbitmq (4.0-management, healthy), specproof-redis (7.4, healthy), specproof-mongodb (7.0, healthy), specproof-minio, specproof-elasticsearch (8.16.4) 全部 Up/healthy; Python 3.12.10; worker/relay 以宿主进程方式运行 (与 start_local.ps1 相同形态)。LLM 凭据一律不注入 (确定性档)。

## 0. 演练结论速览

| # | 演练 | 状态 | 结果 |
|---|---|---|---|
| 1 | Worker 中途被杀 → 断点恢复 → 单终态 + 无重复副作用 | ✅ 已演练 | **PASS** — 恢复后 BLOCKED 与对照完全一致; 终态转移恰 1 次; 副作用计数与对照逐项相同 |
| 2 | Provider 不可达端点 → 诚实降级 | ✅ 已演练 | **PASS** — 3 次尝试全部如实暴露 (timeout 分类), 熔断打开; 作业级 LLM 编译失败记入 degrade_reasons, 规则结果保留 |
| 3 | 安全响应桌面推演 (pause/freeze/revoke/isolate/preserve/notify) | 📝 桌面核对 | 6 动词 × 现有端点/命令逐一核对; 9 项可执行, 4 项需开发 (见 §3) |
| 4 | Outbox Relay 崩溃窗口 → 重启重放 → 幂等去重 | ✅ 已演练 | **PASS** — 同一事件投递 2 次, 作业恰执行 1 次; 重放前后副作用计数逐项相同; 队列清空 |

演练期间发现并修复 3 个真实缺陷 (详见 §5): MySQL 迁移拆分器注释分号缺陷、providers/toolcheck.py 中途编辑遗留的语法损坏、**MongoDBSaver 未持久化 pending writes 且 get_tuple 忽略 checkpoint_id — 断点续跑实际不工作** (修复后由探针与 Drill 1 双重验证)。

---

## 1. Drill 1 — Worker 中途被杀, 断点恢复, 单终态 + 无重复副作用 ✅ 已演练

**目标**: 确定性作业跑到中途时强杀 worker (taskkill /F /T), 租约过期后续跑, 断言 (a) 恰一个终态转移, (b) 与未中断对照作业的副作用计数逐项相同 (无重复副作用), (c) 判定与对照一致。

**机制复用**: MySQL 10 态状态机 + outbox 事务 (storage/mysql.py); RabbitMQ 手动 Ack + Redis SETNX 幂等键 (storage/rabbitmq.py); Redis 租约 30s TTL (storage/redis.py); LangGraph checkpointer (agent/mongo_saver.py, thread_id == job_id); 确定性作业 = ops/drills.AUTH_FIXTURE_* (auth 回归 fixture, 无 pom.xml → 差分节点诚实降级 NON_REPRODUCIBLE, 静态检查产出确定性 finding)。

**执行命令** (可重跑):

    python scripts/drill_worker_kill.py

**真实输出** (2026-08-19 执行, 原样):

    {
      "drill": "worker_kill_recovery",
      "fixture": {"repo_path": "D:/UserData/HUAWEI/Temp/specproof-drill-wk-fixture-ovr53v_m",
                  "base_ref": "base", "head_ref": "head-v1", "padding_files": 40},
      "kill_job": {
        "job_id": "drill-wk-1787145074",
        "worker_pid": 2672,
        "checkpoints_before_kill": 6,
        "worker_killed": true,
        "killed_at_checkpoints": 6,
        "stuck_running_after_kill": true,
        "lease_owner_after_kill": "worker-2672-1787145095",
        "lease_available_after_ttl": true,
        "resume_seconds": 9.09,
        "verdict": "BLOCKED",
        "terminal_status": "BLOCKED",
        "side_effects": {
          "terminal_transitions": 1,
          "running_transitions": 1,
          "summary_writes": 1,
          "findings": 2,
          "capsules": 2,
          "errors": 0
        },
        "checkpoints_after_resume": 24
      },
      "control_job": {
        "job_id": "drill-wk-ctl-1787145139",
        "verdict": "BLOCKED",
        "side_effects": {
          "terminal_transitions": 1,
          "running_transitions": 1,
          "summary_writes": 1,
          "findings": 2,
          "capsules": 2,
          "errors": 0
        }
      },
      "assertions": {
        "same_verdict_as_control": true,
        "identical_side_effect_counts": true,
        "exactly_one_terminal_transition": true,
        "checkpoints_advanced_after_resume": true
      },
      "passed": true,
      "verdict": "PASS — killed worker resumed via checkpoints; one terminal state; no duplicate side effects"
    }

**演练发现与记录**:

1. 强杀后消息未 Ack → 重回队列; 但重投递被 Redis 幂等键 (specproof:idempotent:outbox-{id}) 直接丢弃并 Ack — **重投递绝不重跑作业** (与 Drill 4 同一机制, 两次演练互相印证)。
2. 强杀后作业停在 RUNNING, 租约 30s TTL 到期 (lease_available_after_ttl=true) 后续跑 — 恢复被租约天然串行化, 旧 worker 不可能再写业务结果。
3. **修复前该演练真实失败过一次**: 续跑只重放了输入状态并在第 1 个节点后停止, 最终状态为空矩阵 → 判定映射为 VERIFIED (假通过)。根因 = MongoDBSaver 两个缺陷 (见 §5 FIX-3): put_writes 未持久化到独立集合、get_tuple 忽略 checkpoint_id 恒返最新文档。修复后用探针与 Drill 1 双重验证, 续跑从被杀的检查点继续跑完剩余 9 个节点 (checkpoints 6 → 24)。
4. 演练未发现重复副作用: 恢复路径跳过了已完成节点 (LangGraph 版本跳过), findings/capsules/summary/终态审计与对照完全一致。

**仍属"需开发"的缺口** (如实标注): 目前没有任何组件会自动续跑崩溃后停在 RUNNING 的作业 — 本演练的续跑由 ops.drills.resume_job (scripts/drill_worker_kill.py 调用) 显式驱动; 生产需要一个启动时回收器 (扫描 RUNNING 超时作业 → 重投递/直接续跑)。该回收器未实现 = ⏳ 需开发。

---
## 2. Drill 2 — Provider 不可达端点, 作业诚实降级 ✅ 已演练

**目标**: provider 指向不可达端点 (http://127.0.0.1:1/v1) 时, (a) provider 层如实暴露失败并熔断, 绝不造假输出、绝不悬挂; (b) 作业级 LLM 编译失败记入 compile_report.degrade_reasons, 确定性规则结果绝不因 LLM 失败被丢弃。

**执行命令** (可重跑, 零基础设施依赖):

    python scripts/drill_provider_outage.py

**真实输出** (2026-08-19 执行, 原样; 密钥为脚本内置的明显假值 drill-dummy-key-unreachable-endpoint, 指向不可达端点, 会话外不落盘):

    {
      "drill": "provider_outage",
      "base_url": "http://127.0.0.1:1/v1",
      "env_guard": {"LLM_API_KEY": "", "LLM_BASE_URL": "", "LLM_MODEL": ""},
      "provider_level": {
        "attempts": 3,
        "elapsed_seconds": 16.062,
        "failure_surfaced": true,
        "result_produced": false,
        "exception_class": "APITimeoutError",
        "exception_message": "Request timed out.",
        "final_decision_reason": "timeout",
        "final_decision_retryable": true,
        "breaker_state": "open",
        "breaker_total_failures": 3
      },
      "job_level": {
        "contracts_produced": 1,
        "errors_recorded": [],
        "compile_report": {
          "llm_used": false,
          "candidate_count": 1,
          "accepted_count": 1,
          "degrade_reasons": ["LLM call failed: Error code: 502"],
          "schema_errors": [],
          "parser_rule_version": "1.0.0",
          "requirement_digest": "facaae00fa921f72"
        }
      },
      "wall_seconds": 36.922,
      "passed": true,
      "verdict": "PASS — provider outage degraded honestly"
    }

**演练发现与记录**:

1. provider 层: 3 次尝试全部以 APITimeoutError 如实暴露 (SDK 对不可达端点报 Request timed out), classify_retry 分类为 timeout/retryable, CircuitBreaker 3 连败后打开 (breaker_state=open) — 无伪造结果 (result_produced=false), 全程有界 (16.1s)。
2. 作业级: compile_contracts 节点走真实 LLM 增强路径, 调用失败记入 compile_report.degrade_reasons ("LLM call failed: Error code: 502"); 规则解析的 1 个契约被保留 (contracts_produced=1, accepted_count=1, llm_used=false) — 诚实降级, 错误绝不吞掉。
3. OpenAICompatibleProvider 对 "replace_me" 占位密钥 fail-closed (构造即拒绝) — 演练因此使用明显假值, 这正是密钥纪律的代码级证据。
4. **需开发缺口**: 状态机定义了 WAITING_FOR_PROVIDER (RUNNING → WAITING_FOR_PROVIDER → RUNNING/QUEUED/FAILED), 但 worker 的 provider 故障路径目前直接 FAILED, 从未转入该可恢复态; RUNBOOK.md "job 停在 WAITING_FOR_PROVIDER" 一节目前没有生产者。 = ⏳ 需开发 (worker 接线)。

---
## 3. Drill 3 — 安全响应桌面推演 (pause/freeze/revoke/isolate/preserve/notify) 📝 桌面核对

**目标**: 按计划书 §18.5 的事故处理动词 (暂停/冻结/撤销/隔离/保全/通知), 把每一步映射到"现有端点/命令", 并如实标注 可执行 / 需开发。本次为桌面核对: 端点/命令/工具全部实测核对 (路由枚举、CLI 子命令、工具可用性、broker 命令语法), 未对任何真实业务状态执行破坏性动作。

**桌面核对证据 (2026-08-19 实测)**:

- API 路由枚举 (python 导入 api.server 实测): POST /jobs, POST /jobs/{job_id}/cancel, GET /jobs{,/{job_id},/{job_id}/summary,/{job_id}/progress}, POST /webhooks/github, /api/v1/admin/{tenants,users,tokens,audit} (含 DELETE /api/v1/admin/tokens/{token_id} 与 POST /api/v1/admin/users/{user_id}/status), /auth/{config,me,oidc/login,oidc/callback}, /api/v1/{dashboard,health} 等 — 全部存在。
- identity CLI (python -m api.identity.cli): init-admin / mint-token / list-users 三个子命令 (实测)。
- 宿主工具实测: docker ✅, git ✅; mysqldump/mongodump/mc/redis-cli 宿主未安装 → 全部走容器内二进制 (docker exec)。
- broker 实测: docker exec specproof-rabbitmq rabbitmqctl list_queues 输出 7 条队列 (q.p1.verify.job + .retry + .dlq + 4 条 phase0 队列); purge_queue 语法实测确认。
- 缺口实测: integrations/notify/ (webhook/Slack 连接器) 存在且有单测, 但主管道零调用点; evidence/ 无任何 revoke/吊销 能力; api/ 无 logout 端点; worker 无启动回收器; WAITING_FOR_PROVIDER 无生产者。

### 3.1 六动词映射矩阵

| 动词 | 事故响应动作 | 现有端点/命令 (出处) | 状态 |
|---|---|---|---|
| pause 暂停 | 停掉验证管道 (worker/relay), 新作业停止执行 | taskkill /F /T /PID <worker-pid>; 或 pwsh scripts/stop_local.ps1 (停全部, 保留数据卷) | ✅ 可执行 |
| pause | 单作业暂停/作废 (CAS) | POST /jobs/{job_id}/cancel — 从 QUEUED/RUNNING/WAITING_FOR_PROVIDER/FAILED CAS 转 CANCELLED, 终态不可变, 写审计 job_cancelled (api/routes/jobs.py) | ✅ 可执行 |
| freeze 冻结 | 冻结业务事实库 (取证一致性) | docker exec specproof-mysql mysql -u<user> -p<pass> -e "FLUSH TABLES WITH READ LOCK" (解除: UNLOCK TABLES; 容器重启即失效 — 保全窗口内必须完成 dump) | ✅ 可执行 |
| freeze | 冻结证书签发 | 证书只在 VERIFIED 终态签发 → 暂停 worker 即冻结签发; 队列保留 (RabbitMQ durable) | ✅ 可执行 |
| revoke 撤销 | 撤销租户/用户 API Token | DELETE /api/v1/admin/tokens/{token_id} (identity store revoke_token, 秒级生效) | ✅ 可执行 |
| revoke | 停用用户/降权 | POST /api/v1/admin/users/{user_id}/status {"status":"disabled"}; POST /api/v1/admin/users/{user_id}/role | ✅ 可执行 |
| revoke | 轮换网关/演示密钥 | 修改 SPECPROOF_API_KEY 环境变量并重启 api 进程 (密钥只进环境变量, 绝不落盘) | ✅ 可执行 |
| revoke | OIDC 会话注销/令牌吊销 | 无 logout/revoke 端点 (api/ 实测 0 命中) | ⏳ 需开发 |
| revoke | Merge Certificate 撤销 | evidence/ 无撤销能力 (证书本身未签名, 撤销属 Phase 1+ 计划) | ⏳ 需开发 |
| isolate 隔离 | 隔离受影响租户的作业 | 逐作业 POST /jobs/{id}/cancel + 该租户 token 全部 DELETE (上两行) | ✅ 可执行 |
| isolate | 清空管道队列 (防止污染扩散) | docker exec specproof-rabbitmq rabbitmqctl purge_queue q.p1.verify.job (语法实测) | ✅ 可执行 |
| isolate | 强占卡死作业的租约 (让恢复串行化) | 租约键 = specproof:lease:job:{job_id} (storage/redis.py): docker exec specproof-redis redis-cli DEL specproof:lease:job:<job_id> | ✅ 可执行 |
| isolate | 网络级隔离单服务 | docker compose -f compose.phase0.yml stop <mysql|rabbitmq|redis|mongodb|minio|elasticsearch> | ✅ 可执行 |
| preserve 保全 | MySQL 全量快照 (业务事实源) | docker compose -f compose.phase0.yml exec -T mysql mysqldump -u root -p"<root>" --single-transaction --routines --triggers specproof_phase0 > backup-<ts>.sql (DATA_LIFECYCLE §5 同款) | ✅ 可执行 |
| preserve | Mongo 断点/产物快照 | docker compose -f compose.phase0.yml exec -T mongodb mongodump --db specproof_phase0 --archive --gzip > mongo-<ts>.archive.gz | ✅ 可执行 |
| preserve | 作业进度流导出 (Redis) | 流键 = specproof:stream:job:{job_id}: docker exec specproof-redis redis-cli XRANGE specproof:stream:job:<job_id> - + | ✅ 可执行 |
| preserve | 日志保全 | 拷贝 .local/worker.log, .local/outbox.log, .local/api.log; docker logs specproof-<svc> > svc.log | ✅ 可执行 |
| preserve | MinIO 对象保全 | 宿主无 mc 二进制 (实测) → docker run --rm --network specproof-phase0_default minio/mc ... 或宿主机安装 mc 后 mc mirror (DATA_LIFECYCLE §5) | ⏳ 待基础设施 (宿主 mc 未安装) |
| notify 通知 | 系统内审计/进度通知 | audit_logs (每次状态转移落库, /api/v1/admin/audit 可读), SSE 进度流 (GET /jobs/{id}/progress) | ✅ 可执行 |
| notify | GitHub 侧状态回写 | worker 终态回写 Check Run + Inline Findings (integrations/github_checks.py, github_check_json 存在时) | ✅ 可执行 |
| notify | 外部通知 (Slack/邮件/webhook) | integrations/notify/ 连接器已实现且有单测, 但主管道零调用点 (实测) | ⏳ 需开发 (接线) |

### 3.2 推演结论

- 暂停/冻结/撤销/隔离/保全的主干路径全部有现成端点或命令 (9 行 ✅ 可执行), 事故黄金窗口内的动作不需要写新代码。
- 4 项缺口如实标注: OIDC 注销/吊销、证书撤销、外部通知接线、宿主 mc 工具 — 每一项都给出精确缺口位置。
- 与 §18.5 的映射: "暂停新任务和证书签发" = pause/freeze 行; "隔离受影响租户或执行器" = isolate 行; "保留日志和对象版本" = preserve 行; "撤销外部集成" = revoke 行; "通知客户" = notify 行 (需开发接线); "影响评估和回归测试" = preserve + audit + 重跑本手册 Drill 1/2/4。

---
## 4. Drill 4 — Outbox Relay 崩溃窗口: 重启重放, 幂等防重 ✅ 已演练

**目标**: 复现 relay 的崩溃窗口 (broker 已确认、UPDATE published_at 未执行 — 即 relay 在 publish 与 mark 之间被强杀留下的状态), 重启后的 relay 重放同一事件, 验证幂等键防止重复处理: 同一作业恰好执行一次。

**机制复用**: outbox 事务 (create_job_with_outbox); relay 只在 broker confirm 之后 mark published (storage/outbox_relay.py drain_pending); 消费者侧 Redis SETNX 幂等键 (make_idempotency_check); 真实 worker 进程 (python -m agent.worker) + 真实队列。

**执行命令** (可重跑):

    python scripts/drill_outbox_crash.py

**真实输出** (2026-08-19 执行, 原样):

    {
      "drill": "outbox_crash_window",
      "job_id": "drill-ob-1787142041",
      "outbox_row_id": 151,
      "event_id": "outbox-151",
      "row_still_pending_after_publish": true,
      "worker_pid": 19688,
      "terminal_status": "BLOCKED",
      "idempotency_key_after_first_delivery": true,
      "side_effects_after_first_delivery": {
        "terminal_transitions": 1, "running_transitions": 1,
        "summary_writes": 1, "findings": 2, "capsules": 2, "errors": 0
      },
      "relay_replay_published_rows": 1,
      "outbox_publish_count": 1,
      "outbox_published_at_set": true,
      "side_effects_after_duplicate_delivery": {
        "terminal_transitions": 1, "running_transitions": 1,
        "summary_writes": 1, "findings": 2, "capsules": 2, "errors": 0
      },
      "queue_messages_remaining": 0,
      "terminal_transitions": 1,
      "passed": true,
      "verdict": "PASS — crash-window replay deduplicated, job executed exactly once"
    }

**演练发现与记录**:

1. 崩溃窗口状态被真实复现: 手动 publish 后不 mark, outbox 行仍处于 pending (row_still_pending_after_publish=true) — 这正是 broker confirm 与 UPDATE 之间强杀留下的状态。
2. 真实 worker 消费第 1 次投递, 作业跑到 BLOCKED 终态, 幂等键 specproof:idempotent:outbox-151 已存在。
3. 重启的 relay (drain_pending) 重放同一行: publish_count=1 (relay 视角的首次发布尝试), published_at 落库 — 之后该行不再出现在 pending 集。
4. 第 2 次投递到达 worker 后被幂等键丢弃并 Ack: 重放前后副作用计数逐项相同 (终态转移 1、summary 1、findings 2、capsules 2), 队列余量 0 — **同一事件投递 2 次, 作业恰好执行 1 次**。
5. 语义澄清 (写入手册): publish_count 统计的是 relay 的发布尝试次数, 不是 broker 投递次数 — 崩溃窗口的第 1 次投递绕过 relay 计数器, 因此重放后 publish_count=1 而实际投递 2 次; 防重的证据链是幂等键 + 副作用计数 + 队列余量, 而不是 publish_count。
6. 演练前必须跑通 schema 迁移: 首跑因 outbox 缺 0008 治理列失败 (payload_digest 不存在), 由 storage/migrations.py 的 ensure_tables 应用 0008 后通过 — 过程中又暴露并修复了迁移拆分器的注释分号缺陷 (见 §5 FIX-1)。

---
## 5. 演练期间发现并修复的缺陷 (如实记录)

| # | 缺陷 | 影响 | 修复 | 验证 |
|---|---|---|---|---|
| FIX-1 | storage/migrations.py _split_statements 先按 ";" 切分再删注释行 — 注释行内含分号时, 分号后的注释文字泄漏成假语句 (0008 的 "-- ...deferral; the relay only claims rows" 实测让 0008 应用失败) | 含分号注释的迁移无法应用 | 先删注释行再按 ";" 切分, 并保留行内 "-- " 尾部注释处理 | tests/unit/test_migrations.py 4 通过; 0008 在演练库真实应用成功 |
| FIX-2 | providers/toolcheck.py 存在另一车道中途编辑遗留的语法损坏 (字符串字面量内裸换行, py_compile 失败) — 演练的桌面核对导入 api.server 时暴露 | 全仓 ruff/任何导入 craft/api 的代码全部失败 | 仅修复字符串字面量语法 (合并裸换行为 \n 转义) + 2 处 ruff 行宽/尾换行 | py_compile 通过; 全仓 ruff 通过; mypy strict 通过 |
| FIX-3 | agent/mongo_saver.py 断点续跑两个缺陷: (a) put_writes 把 pending writes 塞进 checkpoint 文档子字段, 而 get_tuple 从不读取 → 待执行任务丢失; (b) get_tuple 忽略 config.checkpoint_id, 恒返回最新 checkpoint → 续跑永远找不到被杀超步的 pending 任务。**实测后果: 强杀后续跑从输入状态重放并在首个节点后停止, 空矩阵被判定映射为 VERIFIED (假通过)** | 崩溃恢复机制 (P1.6 的核心承诺) 实际不工作 | (a) pending writes 写入独立 checkpoint_writes 集合, 按 (thread_id, checkpoint_ns, checkpoint_id, task_id) 键控; (b) get_tuple 尊重显式 checkpoint_id; (c) get_tuple 以 (task_id, channel, value) 三元组挂载 pending_writes; (d) delete_thread 同步清理两集合 | 探针: 断点后续跑从第 4 个节点继续并跑完全部 15 个节点 (见 §1); Drill 1 真实强杀演练 PASS; tests/integration/test_worker_crash_mid_graph.py 11 通过 (含按新契约更新的 2 个 fake) |

## 6. 待基础设施 / 需开发清单 (如实标注, 均给出精确缺口位置)

| # | 项目 | 缺口位置 | 状态 |
|---|---|---|---|
| 1 | 崩溃作业自动回收器 (RUNNING 超时 → 续跑/重投递) | 无任何组件调用 resume 路径; ops.drills.resume_job 是本演练的显式驱动 | ⏳ 需开发 |
| 2 | WAITING_FOR_PROVIDER 接线 | worker 的 provider 故障直接 FAILED; 状态机与 RUNBOOK 已有该态但无生产者 | ⏳ 需开发 |
| 3 | OIDC 会话注销/令牌吊销端点 | api/ 无 logout/revoke | ⏳ 需开发 |
| 4 | Merge Certificate 撤销 | evidence/ 无撤销能力 (签名本身亦未实现, Phase 1+) | ⏳ 需开发 |
| 5 | 外部通知接线 (Slack/邮件/webhook) | integrations/notify/ 连接器已有单测, 主管道零调用点 | ⏳ 需开发 |
| 6 | 宿主备份工具 | mysqldump/mongodump/mc/redis-cli 宿主未安装 (实测) — 全部容器内执行或安装后按 §3.1 命令执行 | ⏳ 待基础设施 |

## 7. 演练支撑物 (本次交付)

| 文件 | 作用 |
|---|---|
| ops/drills.py | 演练辅助库 (纯编排): 轮询等待、副作用台账、崩溃窗口发布、显式续跑 resume_job、诚实降级报告、确定性 fixture 构建; 一切效果经由调用方注入的真实客户端 |
| scripts/drill_worker_kill.py | Drill 1 驱动 (真实强杀 + 续跑 + 对照 + 断言) |
| scripts/drill_provider_outage.py | Drill 2 驱动 (provider 层 + 作业级降级) |
| scripts/drill_outbox_crash.py | Drill 4 驱动 (崩溃窗口重建 + 重放 + 幂等断言) |
| tests/unit/test_drill_helpers.py | 22 个纯 fake 单测 (零基础设施、零真实睡眠) 覆盖全部辅助库 |

**演练验证门禁** (2026-08-19 全绿):

    python -m ruff check .                                    # All checks passed
    python -m mypy --strict ops/drills.py tests/unit/test_drill_helpers.py scripts/drill_worker_kill.py scripts/drill_provider_outage.py scripts/drill_outbox_crash.py   # 5 files, no issues
    python -m pytest tests/unit/test_drill_helpers.py tests/security/test_no_key_leak.py -q   # 全部通过 (含 no-key-leak 全仓扫描)
    python -m pytest tests/unit/test_migrations.py tests/integration/test_worker_crash_mid_graph.py -q   # 修复相关回归 15 通过
