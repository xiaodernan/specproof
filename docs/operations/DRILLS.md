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
- 缺口实测: integrations/notify/ (webhook/Slack 连接器) 存在且有单测 — 原"主管道零调用点"缺口已于 #65 接掉 (worker 在每一次被接受的终态写入之后调用 _maybe_notify_terminal); 但默认仍不发声: 未设 SPECPROOF_NOTIFY_WEBHOOK_URL 时工厂返回 DisabledConnector, 只有 specproof_notify_disabled_total 在涨; evidence/ 无任何 revoke/吊销 能力; api/ 无 logout 端点; WAITING_FOR_PROVIDER 的生产者已于 #64 接上 (可重试 provider 故障改为暂停)。**回收器触发点已于 #68 接上**: `specproof ops recover` (cli/specproof/commands/ops.py) 是 `reclaim_stale_running_jobs` / `recover_waiting_for_provider_jobs` 的生产调用点, 单测锁住「命令确实调用这两个函数」并锁住「判定失败不等于没有卡住的作业」; **自动周期触发已落地 (#71, 2026-09-26)**：`agent/worker.py` 的 worker 进程自带回收 tick（默认每 300s，`WORKER_RECLAIM_INTERVAL_SECONDS=0` 才回到只靠人工命令），多副本由 Redis 作用域锁 `specproof:lock:scope:stale-job-sweep` 保证一轮只有一个 worker 真的在扫，且**释放只认自己拿到的 token**（否则跑过 ttl 的那轮会删掉接班者的锁）；Redis 答不出锁状态时本轮**跳过**而不是无锁硬扫 —— 同一个 Redis 也是租约探针，此时扫了也会在第一个候选前停下来，跳过不丢业务、不重复投递；扫描抛异常时 tick 继续活着（打破这一轮的那次故障，正是下一轮要处理的故障）。演练口径：`curl -s localhost:9100/metrics | grep specproof_worker_reclaim` 看 `last_ok_timestamp` 是否在推进，然后才看各个计数。**#71 的门证（2026-09-26 实测）**: 定向回归集 `tests/security + tests/fault + 26 个 import 了 agent.worker/storage.redis/storage.mysql 的 tests/unit 文件` = **601 passed / 2 skipped / 570.43s**（退出码取自日志自己的 `PYTEST_EXIT=0`，不经管道）；`ruff check .` 全绿、`mypy .` 213 source files 无问题、新增 `tests/unit/test_reclaim_tick.py` 21 passed、变异门 **18/18 逐条 RED** 且各自指名被测项（按 sha 校验还原后对照跑绿）。**全量合并门没跑完，这是已知欠账 (#82)**：本机同时有 3 个 pytest 在跑（另一个 SpecProof 会话 + 另外两个项目），门被拖到 4-5 倍慢并在 5% 处出现 2 个红——单独重跑那个文件是 **14 passed / 520s**，所以那两个红是内存饿死（`code 0x8007000e` = E_OUTOFMEMORY，~1GB free）而不是回归；判据留档：慢文件里的单个红，必须先单跑再定罪。补法用 worktree（`git worktree add --detach $TEMP/sp-gate71 <sha>` + 主树 .venv 跑），这样数字属于那个 commit 而不是别人的脏树。(以下两句保留为历史记录。)周期触发的两个前置之一已落地 (#71)：`reclaim_stale_running` 现在受作业自身 `retry_count >= max_retries` 约束，预算耗尽直接 RUNNING→FAILED 且不重投，所以默认开的 tick 不会把必然崩溃的作业无限重投；另一个前置（实测缺失）是 provider 健康信号 —— 没有它，`recover_waiting_for_provider_jobs` 的定时轮会在模型服务仍在故障时空跑掉重试预算，把作业直接判成 FAILED。**只读判定已落地 (#74)**: `specproof ops recover --dry-run` 回答「有没有卡住的作业」而不动任何一行 —— 起因是 2026-09-25 一次只想看看的命令当场把作业重投了。**残行已收口 (#73)**: `TestStateMachineWithDB` 现在删掉自己写的行并断言删成功 (实测该文件每次运行净增 0 行；修之前每跑一次净增 1 行，而 `test_cas_prevents_concurrent_claim` 留下的正是「RUNNING + 过期 updated_at」这个被回收器认成卡死作业的形状)。**#75 已收口 (2026-09-26, 门证见 §3.3)。以下为修前状态 (历史)**: 本机 MySQL 只有 `specproof_phase0` 一个业务库，`specproof@%` 除该库外只有 USAGE，而 13 个测试文件（其中 9 个在 tests/unit，4 个在 tests/integration）直接构造真实 `MySQLStore()` —— 所谓单测其实写在产品表里 (实测累计 177 行 `/test/…` 残行（2026-09-26 复测：#73 当时记录 165，此后净增 12），Dashboard 与引导页的计数把它们算进去)；同一 schema 下 `mark_stale_for_head` 一度会把表内**所有** QUEUED/RUNNING 行改成 STALE——该无作用域缺陷已于 **#76** 收口 (现在按 `repo_path` 限定并排除新作业本身, 空 repo 直接拒绝)；但它留下的教训仍在: 在共享库上跑测试就等于对别人的作业动手。实测更尖锐的数字: 本机 `verification_jobs` 总行数 177（2026-09-26 复测，上次记录为 165）, 其中 `repo_path LIKE '/test/%'` 也是 177 —— 产品表当前 100% 是测试残行 (修前该文件每跑一次再 +1), Dashboard 与引导页把 177 全部当真作业计数。

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
| notify | 外部通知 (Slack/邮件/webhook) | worker 终态写入成功后自动发 (agent/worker.py::_maybe_notify_terminal, #65): 设 SPECPROOF_NOTIFY_WEBHOOK_URL (+_SECRET, 可选 _KIND=slack|generic|feishu) 后重启 worker; 未设=不发, 只涨 specproof_notify_disabled_total | ✅ 可执行 (需先配置环境变量) |

### 3.2 推演结论

- 暂停/冻结/撤销/隔离/保全的主干路径全部有现成端点或命令 (9 行 ✅ 可执行), 事故黄金窗口内的动作不需要写新代码。
- 4 项缺口如实标注: OIDC 注销/吊销、证书撤销、外部通知接线、宿主 mc 工具 — 每一项都给出精确缺口位置。
- 与 §18.5 的映射: "暂停新任务和证书签发" = pause/freeze 行; "隔离受影响租户或执行器" = isolate 行; "保留日志和对象版本" = preserve 行; "撤销外部集成" = revoke 行; "通知客户" = notify 行 (需开发接线); "影响评估和回归测试" = preserve + audit + 重跑本手册 Drill 1/2/4。

### 3.3 #75 测试库隔离契约 —— 所谓"单测"不再写产品库 (2026-09-26 实测)

- **修前的实测形状**: 产品库 `specproof_phase0.verification_jobs` 共 177 行, 其中 `repo_path LIKE '/test/%'` 也是 177 行 —— 产品表 100% 是测试残行; 而 `specproof@%` 除该库外只有 USAGE, 所以测试**没有别的库可写**, "绿色门"的一直是"产品库又多了几百行"。
- **落地**: `tests/conftest.py` 在 `pytest_configure` (任何测试构造真实 `MySQLStore()` 之前) 判四种状态 —— dedicated / redirected / unreachable / blocked。**blocked 直接 `pytest.exit(returncode=4)` 并指名补救脚本, 不退化成 skip**: 跳过会让绿色门继续建立在产品库上, 而"没隔离"和"没跑"必须不是一回事。
- **`scripts/create_test_database.ps1`**: 只 CREATE + GRANT 名字匹配 `^specproof_test[A-Za-z0-9_]*$` 的库, 目标等于产品库名直接拒绝; root 密码只从 `MYSQL_ROOT_PASSWORD` 环境变量读, 经 `-e MYSQL_PWD` 进容器 (绝不写进命令行参数 —— 那会出现在别人的进程列表里)。本机实测: `specproof_test` 17 张表, 产品库 18 张 —— 差的正是 #80 登记的 `agent_jobs`, 该脚本会把这种不等量打印成 WARNING 而不是静默。
- **门证 (全部实测)**:
  - 契约单测 `tests/unit/test_mysql_isolation_contract.py` = **21 passed / 20.60s**, 全程不连任何库 (它测的是判定本身)。
  - 13 个真实构造 `MySQLStore()` 的文件 (9 个 tests/unit + 4 个 tests/integration) 在新重定向下 = **201 passed / 1 failed / 1017.45s**; 会话头 `MySQL test isolation: redirected -> specproof_test (product schema specproof_phase0 holds 177 '/test/%' job rows at session start)`, 会话尾 `177 -> 177; no test row landed in the product schema` ⇒ **202 个测试对产品表的净写入 = 0 行**, 这是这条契约存在的唯一理由。
  - 那 1 个红 (`test_full_lifecycle_pending_to_verified`) 的 traceback 指向 `storage/mysql.py:200` 的 `conn.rollback()` 抛 `InterfaceError: (0, '')`。按 §3 既有判据 (慢文件里的单个红必须先单跑再定罪) 单跑该文件 = **9 passed / 157.37s, PYTEST_EXIT=0**, 同一对隔离头/尾仍报 `177 -> 177`; MySQL 容器侧 `OOMKilled=false / RestartCount=0 / Uptime=109482s / Aborted_clients=16` ⇒ 服务端没死, 是客户端 socket 先没 (本机同时有多个 pytest 抢内存)。所以它是偶发丢连接, **不是** #75 回归 —— 但它顺带暴露了 #83: 真因被 `rollback()` 自己的失败顶掉了, 报错永远指向错误的一层。
  - 变异门: 6 个各破坏一条隔离判据的 mutant (K1 只决定不应用 / K2 恒判 dedicated / K3 读不到残行数就当 0 / K4 允许测试库沿用产品库名 / K5 对当前任何库都做迁移 / K6 行被搬走后仍报 clean) = **6/6 逐条 RED** 且各自指名被测测试; 按 sha 校验还原 (`31cc49514a`) 后复跑 21 passed, `ruff check .` 全绿。
- **文档缺口一并补上**: `MYSQL_DATABASE` 这个"决定你正在往哪个库写"的变量此前在任何 .md 里都**没有出现过一次** (实测 grep 0 命中), 现已进 RUNBOOK §3 的 fail-closed 表。

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
| FIX-4 | (#83) 5 个 store 的 `connection()` 逐字节相同, 形态是 `except Exception: conn.rollback(); raise` + `finally: conn.close()` — 连接被丢时 rollback/close 自己会抛 `InterfaceError: (0, '')`, 于是**每一个"连接丢了"的报错都写成"回滚坏了"**, 调查方向被指向错误的一层 (实测触发: #75 门里 `test_full_lifecycle_pending_to_verified` 的红, traceback 停在 `storage/mysql.py:200`; 单跑该文件 9 passed, 容器 `OOMKilled=false/Aborted_clients=16` ⇒ 真因是偶发丢连接) | 所有 MySQL 侧故障的报错都指不到真因; `finally` 里抛错还会把原异常整个丢弃 | 合并成唯一的 `storage/unit_of_work.py::unit_of_work(connect)`: 归还动作失败只记 WARNING (文案明说"调用方看到的那个才是真因"), 绝不再顶替原异常; 5 个 store 全部改为消费它, 不留第二份实现 | `tests/unit/test_unit_of_work.py` 27 通过 (含 5 个 store 各自的行为契约 + "storage 里不许再出现局部 rollback" 的单一来源门); 变异门 M1 归还再抛 / M2 静默吞掉 / M3 close 裸奔 / M4 干净路径不 commit / M5 某个 store 退回本地实现 = **5/5 逐条 RED** 且各自指名测试; ruff + mypy 全绿 |
| FIX-5 | (#80) `agent_jobs` 只有代码 DDL (`storage/agent_jobs.py` 的 `CREATE TABLE IF NOT EXISTS`), 而 `storage/migrations.py` 自称"schema 变更绝不 ad-hoc CREATE IF NOT EXISTS" —— 两句同时为真, 实测后果是 `ensure_tables()` 建出来的全新库比线上产品库**少一张表** (17 vs 18)。同一周 `docs/architecture/DATA_DICTIONARY.md` 还把它登记成"代码 DDL 表", 并宣称迁移范围止于 0008 (0009/0010 早已落地 ⇒ `finding_feedback` 存在于两个真实 schema 却在文档里没有任何条目), 还宣称共 19 张表并把两张只在显式 MySQL 后端下才现建的 `object_metadata`/`object_contracts` 算进默认部署 | 新装库与线上库结构不一致; 文档把"事实来源"指向一份不存在的表清单, 读者按文档核对必然对不上 | 补版本化迁移 `0011_agent_jobs.sql` (+ `down/0011_agent_jobs.sql`), 代码 DDL 降级为"已存在安装上的自愈路径"; 文档改口径 (18 张 = 17 迁移 + `schema_migrations`, 对象元数据两张单列为条件表), 新增 §1.20 登记 `finding_feedback` 并如实标注"Web 无入口" | 迁移侧: `tests/unit/test_agent_jobs_migration_parity.py` 5 通过 (逐列/顺序/类型锁 + 本仓语句拆分器只出一条 + down 镜像 + `ensure_tables()` 真建表); 文档侧: `tests/unit/test_data_dictionary_covers_migrations.py` 5 通过 (每条迁移建的表必须有 §1 条目、"至 `00NN_….sql`"必须等于最新迁移、1.17/1.18 的归属、文档表数 == 实测表数); 变异门 3/3 + 5/5 逐条 RED 且各自指名测试; 实测闭合: `specproof_test` 17 → **18**, 与 `specproof_phase0` 的 18 一致 |
| FIX-6 | (#84) `MigrationRunner.apply_pending` 的 docstring 与 0012 的迁移头注释都写着"一条迁移一个事务, 失败则表原样未动"。**MySQL 对 DDL 隐式提交**, 这句话不成立。实测: 本机并发把 `read_timeout=15s` 拖爆, 0012 的第二条语句 (`ADD UNIQUE KEY`) 已在线上的表里落下, 而 `schema_migrations` 没有第 12 版 —— 于是**下一次 `ensure_tables()` 永久停在 1061 duplicate key name**, 迁移器自己造出一个不可恢复的半应用状态 | 半条 DDL 落库后产品库再也无法自愈; 任何超时/崩溃都让下一次启动直接红 | 承认隐式提交: 只把 {1050 表已存在, 1060 列已存在, 1061 索引名已存在} 当作"该语句已经应用过"跳过并记 WARNING (带迁移号与语句头), 其余错误 (含 1062/1064/1146) 照旧在记录版本前中止; 0012 头注释改为"两步都写成可收敛" (去重语句重跑是 no-op, 加索引语句由白名单容忍), 版本行仍只在全部语句走通后写 | `tests/unit/test_migrations.py` 两侧各钉: 3 个白名单 errno 参数化 → 记版本 + 断言"1061 … 0002" 出现在日志; 3 个非白名单 errno → 抛错且**不**记版本; 变异门 M6 把 1062 放进群 / M7 清空白名单 → 各自 RED (见 `D:\面试项目\new84\witness84.log`) |
| FIX-7 | (#84) 验收反馈的两条读路径 (`MySQLStore.list_feedback` / `feedback_stats`) 按位置取列 (`row[0]`), 而本 store 的连接是 `cursorclass=DictCursor` (`storage/mysql.py:188`) —— 实测**任何真实调用都抛 `KeyError: 0`**。同里程碑另两处: 每次 POST 造新 uuid 且无唯一约束 ⇒ 同一人双击"接受"在分子里留两行; Web 上没有任何 accept/reject 入口 ⇒ Go/No-Go #13 的 `acceptance_rate` 只能靠手工 curl 产生, 两个真实 schema 该表 0 行 | 产品上"接受率"这个指标从来没被真正算出来过 (读一次崩一次), 而计数一旦能读又会因人手重复而虚高; 试点用户没有地方表达自己的判断 | 读路径改为按列名取 (`COUNT(*) AS n`); 新增迁移 `0012_finding_feedback_idempotency.sql` (先按 `(finding_id, created_by)` 留最新一行去重, 再 `ADD UNIQUE KEY uniq_feedback_finding_actor`), `insert_feedback` 改 `INSERT ... AS new ON DUPLICATE KEY UPDATE` 并回 `{"state": created|replaced|unchanged, "id": 库里真实行 id}`; 路由原样回显 `state`; 前端在 FindingDetail 挂 `FeedbackSection` (评审人标识 + 接受/打回 + 理由必填规则 + 三种 state 不同文案 + 加载失败≠空账本 + 只有四个可记录 severity 才开按钮) | 后端: `tests/unit/{test_migrations,test_feedback_api,test_feedback_store_read}.py` **27 通过** (含真连 `specproof_test`: 同一人三次 POST 塌成一票、两个人两票、50.0%、以及 finally 清探针行), 隔离契约尾行 `177 -> 177`, 变异门 **7/7 逐条 RED 且各自指名测试** (`witness84.log`, 对照 `27 passed`); `ruff` 全绿 + `mypy` 214 文件无问题。前端: `tsc` 0 错、`vitest run src/pages/FindingDetail.test.tsx` **15 通过**、全量 **43 文件 / 317 通过**、`vite build` 成功, 前端变异门 **7/7 RED 且各自指名** (`witness84fe.log`, 对照 15/15 绿 + 按字节还原)。**未闭合 (如实)**: `specproof_phase0` 至今**没有**这个唯一键 —— 对共享产品库做 DDL 属需批准操作, 未擅自执行; 它会在共享栈下一次 `ensure_tables()` 启动时由 0012 自己收敛 (FIX-6 正是为这一步能重跑而修)。
| FIX-8 | (#81) 严重度词表在四处各写一份且互不一致 (实测): `apps/web/src/ui/toneMap.ts` 认 `INFO` —— 而 `findings.severity` 与 `finding_feedback.severity` 是同一个四值 ENUM (`0001`/`0009`), 全仓没有任何生产者能写出 INFO; 同一个文件**没有** `NEEDS_CONFIRMATION` 的语气/提示/排序位, 于是这一条合法风险在页面上渲染成"未知 UNKNOWN", 与一个拼错值长得一模一样; `pages/JobDetail.tsx` 另有一份私有 `SEVERITY_RANK` (含 CRITICAL/HIGH/MEDIUM/LOW 四个哪一列都存不下的值) 且恰好漏掉 NEEDS_CONFIRMATION, 而它上面的注释自称"the canonical enum values are normalized into a rank"; 检查器真正会写的 `NONE`(registry.py:565, java_source.py:443) 与 `ERROR`(generate_counterexamples.py:1130) 同样渲染成"未知" | 评审者看得到"未知"却看不出是数据坏了还是检查器崩了 —— 最该行动的那一行 (崩溃/无检查器) 与一个错别字共用同一句话; 同时"一人一票"入口 (FIX-7) 只能在前端自己抄的那份白名单上判断可投性, 抄错就等于允许投一条存不进去的票 | 词表收敛到 `toneMap.ts` 的 `SEVERITIES` 一处 (每值带 rank/cls/label/storeable/hint), `severityPill`/`SEVERITY_HINT`/`severityRank`/`SEVERITY_STOREABLE` 全部由它派生; 删掉 INFO 与 JobDetail 的私有 rank 表; NONE/ERROR 给出"不构成风险判定/反例编译失败"的明确措辞并标为不可投票 | `tests/unit/test_severity_vocabulary_parity.py` **6 通过**, 两端都从源码取 (不手抄): MySQL ENUM (整文件正则, 后写的 ALTER 覆盖 CREATE)、`api/routes/feedback.py` 的 `pattern=`、`toneMap.ts` 的 `SEVERITIES` 条目、以及 AST 扫出的验收形状 finding (`severity` 且带 `contract_id/evidence_type/...` 之一) —— 断言可存值 ⊆ 有词、有词 ⊆ 可存 ∪ 产出、HTTP 接受集 == 列允许集、`apps/web` 除 `toneMap.ts` 外不得再有第二份词表; 门本身两侧都被证过: 变异 **6/6 逐条 RED 且各自指名测试** (W1 复活 INFO / W2-W3 NEEDS_CONFIRMATION 改标记或删词 / W4 pattern 放宽到 INFO / W5 页面重新私有化 / W6 流水线新写一个没人命名的 `FATAL`; `witness81.log`, 对照 exit=0 且 FAILED=none), 前端一侧另有 **3/3 RED** (`witness81fe.mjs`, 对照 29/29 绿); 全部还原按字节校验。#84 的前端见证在重构后重跑仍 **7/7** (`witness84fe-rerun.log`), 说明收敛没有把上一次的证据跑丢 |
| FIX-9 | (#87) `findings.evidence_type` 是 VARCHAR(64)，没有 ENUM 可当权威值集，于是两端各写一套： Web 的 `EVIDENCE_CN` 认识 6 个词，其中 `runtime_test`/`static`/`differential`/`review` **没有任何生产者**（`FindingDetail`/`JobDetail` 的单测还拿 `runtime_test` 当fixture，于是这条死词被一道绿门长期认证为“产品支持的证据类型”）；反过来流水线真正写出的 `java_source_diff` / `constitution_check` / `checker_failed` / `probe_differential` / `base_pass_head_fail` / `differential_execution` 一个词都没有，直接以英文原文出现在“证据方式”一栏；`unknown` 也确实会被写（`create_capsule.py:185`、`inline_comments.py:132`），连 PR 行内评论都会带上它 | 评审者在最关心的“这条结论是怎么来的”一栏读到的是没人翻译过的内部代号；同时词表里 4/6 是装饰，维护者按它理解产品会以为平台支持四种不存在的证据 | 先把域声明出来：`agent/evidence_kinds.py::EVIDENCE_KINDS`（9 值，含 `unknown`，理由写在模块 docstring 里）；`EVIDENCE_CN` 重写为“每个 kind 一句诚实说明”（静态类一律注明“没有执行任何代码”、`checker_failed` 必须写成“没有跑出结果…不等于没有问题”、`self_test_diff` 继续不声称沙箱/宿主），标签仍保留原 token；fixture 从 `runtime_test` 改成真正会被产出的 `java_source_diff` | `tests/unit/test_evidence_vocabulary_parity.py` 5 通过，三个方向都钉（生产者字面量 ⊆ 声明；声明值必须有生产者；Web 键 == 声明）+ 一条“崩溃不得被说成干净”的语义门。扫描覆盖 dict-key / kwarg / assign / compare / `.get(field, default)` 五种形状（后者是 `review_court.py:175` 唯一能发现 `static_analysis` 的地方），且只认 `.get("evidence_type", …)` 以免把键名自己当成值；声明用 AST 读 `Final[frozenset]`（AnnAssign，只探 Assign 会“找不到声明”而假红）。变异 **5/5 逐条 RED 且各自指名**：E1 删掉 `unknown` 的词、E2 生产者改写一个未声明的 kind、E3 声明删掉仍在生产的 kind、E4 把 `checker_failed` 译成“检查已完成（未发现问题）”、E5 标签丢掉 canonical token（`witness87.log`，pytest 与 vitest 两条对照都先跑绿，还原按字节校验）。本轮全量：定向 11 通过（含 #81 门）、隔离尾行 `177 -> 177`、tsc 0 错、vitest 43 文件 / 321 通过、vite build 成功、ruff 全绿、mypy **215** 文件无问题 |
| FIX-10 | (#86) 独立验收投影（accept.json）的严重程度在控制台只能靠读 JSON 得到：`AgentResult` 把 `accept.findings` 整个 `JSON.stringify` 成一个 <pre>，既没有中文也没有语气（更正当初登记缺口时的说法：信息**在**页面上，只是要评审者自己解析对象）。更麻烦的是这套刻度不是验收平台那条 ENUM：密钥扫描器报 CRITICAL/HIGH/MEDIUM/LOW（`agent/security_scanner.py::_SECRET_PATTERNS`），craft 自己的发现缺省写 BLOCKER/MAJOR（`craft/accept.py:319`、`craft/verify.py:68`），而**只有 CRITICAL 与 HIGH 被计入阻断**（`craft/verify.py:39`、`craft/gates.py:364`） | 一条“扫到已泄漏凭证”与一条“信息性发现”在页面上长得一样，评审者必须自己解析 JSON 才知道哪条会挡住合并；两套刻度若被混用还会把不阻断的级别涂成红色 | 新增 `craft/severity.py` 声明 `ACCEPT_FINDING_SEVERITIES`(6) 与 `BLOCKING_ACCEPT_SEVERITIES`(2)；`apps/web` 新增 `ACCEPT_SEVERITY_CN`/`acceptSeverityLabel`/`acceptSeverityTone`/`ACCEPT_SEVERITY_BLOCKING`（MEDIUM/LOW 的措辞必须自带“不阻断”，未识别的值**原样显示**而不是大写成平台的样子）；`AgentResult` 的验收发现改为逐条列表（严重度徽章 + 类型 + 文件:行 + 描述），完整投影仍在下方 raw 折叠里 | `tests/unit/test_accept_severity_parity.py` 4 通过，四个方向都钉（声明 == 扫描器表 ∪ craft 字面量、Web 键 == 声明、阻断集 == craft 代码里的比较集 == 前端 ACCEPT_SEVERITY_BLOCKING、MEDIUM/LOW 措辞含“不阻断”）；扫描器一侧读 `_SECRET_PATTERNS` 每行第 3 元，craft 一侧读 dict-key/kwarg/参数缺省，并把 `str(x or "MAJOR")` 这类嵌套形状也展开（否则 MAJOR 会被判成“声明了但没人写”）。变异 **5/5 逐条 RED 且各自指名**：V1 前端删掉 LOW 的词、V2 扫描器改报一个未声明的 SEVERE、V3 前端把 MEDIUM 涂成阻断、V4 措辞删掉“不阻断”、V5 控制台把所有发现涂成中性（`witness86.log`，pytest 与 vitest 两条对照先跑绿，按字节还原） |
| FIX-11 | (#79) `storage/config_guard.py` 会在 `SPECPROOF_ENV=production` 时拒绝出厂默认口令，`api/server.py:152` 也无条件调用它——但 **没有任何入口把这个变量设成 production**（实测：compose.phase0/production/observability 三个文件与 start_local(.light).ps1 全无 `SPECPROOF_ENV`），于是这道安全门在真实部署里恒为 no-op；`compose.production.yml` 还把每个凭据写成 `${X:-specproof_pass}`，忘记设就是静悄悄使用出厂口令；同时 `docs/operations/RUNBOOK.md` 第 2 节明确写着“生产必须 SPECPROOF_ENV=production — config_guard 拒绝默认口令”（该文件另一处还停留在“当前 0001-0004”，而迁移已到 0012），也就是说文档在替一条不可达的路径背书 | 一个看似有 fail-closed 的生产部署，实际会用 `specproof/specproof_pass@specproof_phase0` 这套出厂组合起起来；越靠后的运维越会相信文档那句“已被守卫拦住” | compose.production.yml 的 api/worker/outbox-relay 显式 `SPECPROOF_ENV: production`，应用服务用到的凭据全部改为 `${X:?set X}`（沿用同文件里 SPECPROOF_API_KEY 已有的必填写法），start_local(.light).ps1 显式设 `dev`；把 MYSQL_USER 也纳入守卫清单（账号名本身就是产品库凭据的一半）；RUNBOOK §2 重写为可核对的事实 | 新增 `tests/unit/test_production_guard_reachability.py` 7 通过：`api/server.py` 确实调用守卫、每个应用服务都声明环境、compose 写的那个值真的让 `is_production()` 为真、受守卫检查的凭据没有一个还留着 `:-` 兜底、守卫清单与部署清单双向对账、以及一条端到端（拿 compose 的值 + 默认口令真的抛 ProductionConfigError）；`test_config_guard.py` 里那份手抄的变量清单改成读守卫自己的 `_DEFAULT_CREDENTIALS`（它漏掉 MYSQL_USER 就是同一类漂移）。变异 **6/6 逐条 RED 且各自指名**（G1 撤掉环境声明、G2 把值拼成 prod、G3 恢复一个 `:-` 兜底、G4 守卫不再查 MYSQL_USER、G5 守卫多查一个没人提供的变量、G6 本机脚本自称 production；对照 `exit=0 且 FAILED=none`，六次改动后均按字节还原）。**运维须知**：本改动会让漏设凭据的 `docker compose up` 直接失败并点名变量——这是有意的 fail-fast，上线前请按 RUNBOOK §2 的清单补齐；本轮没有重启或改动任何正在运行的共享栈。 |
| FIX-12 | (#88) #79 暴露的不是一个变量，而是一类无人核对的文档承诺：`docs/operations/RUNBOOK.md` §2 写着“生产必须 SPECPROOF_ENV=production — config_guard 拒绝默认口令 fail-fast”，而没有任何入口设置它；同一节还写着“当前 0001-0004”（实际 0012）。`DATA_DICTIONARY.md` 从 #80 起有 `tests/unit/test_data_dictionary_covers_migrations.py` 钉住“文档里的迁移范围必须等于最新迁移”，RUNBOOK 没有同型门——所以运维手册是唯一一份“写错也没人知道”的交付物 | 一句承诺可以让所有后来者（包括代理）停止核对：文档说“已拦住”，人就以为拦住了，而真实部署用出厂凭据起来；过期的迁移范围会让人按不存在的表结构排查 | 新增 `tests/unit/test_runbook_claims_hold.py` 3 通过，三条都只核对文档自己说出口的东西：迁移范围 == `infra/mysql/migrations/` 最新号；每一条“生产必须 VAR=值”必须真被某个 compose/启动脚本设置；RUNBOOK 抄的那份凭据清单必须等于 compose `${X:?}` 实际要求的集合（只认 `_PASSWORD`/`_USER`/`SPECPROOF_API_KEY` 这类凭据名，免得把散文中提到 `RUNBOOK` 也算成清单条目）。RUNBOOK 里新增一句说明这句话本身是被检查的 | 变异 **3/3 RED 且各自指名** + **1 条反向对照必须绿**：R1 把范围改回 0001-0004、R2 从文档清单里删掉一个 compose 确实要求的凭据、R3 新写一条没人接线的“生产必须 SPECPROOF_AUDIT_LAKE=enabled”（正是 #79 的形状）、R4 加一句**不是**义务的 `VAR=值` 说明文字，必须仍然全绿——否则这条门其实是“全文匹配”的伪装。`witness88.log` / `witness88-rerun.log` 两次都 4/4 as predicted（对照 exit=0，按字节还原）|
| FIX-13 | (#89) 全新检出的仓库在 master 上是红的：`tests/unit/test_bench_craft.py` 有两条测试断言 `bench/<suite>/task-*/fixture/.specraft/jobs/<id>/{checkpoint,plan,memory}.json` 必须落盘，而 `.gitignore` 有一条无差别的 `.specraft/` 规则 ⇒ 这 30 个文件只存在于“跑过生成器的那棵树”里。实测方法本身就是发现过程：为了做 #82 而 `git worktree add --detach $TEMP/sp-gate82-f5dacaf HEAD`，在该树里跑这个文件 = **2 failed / 35 passed**，同一份代码在主树里 37/37 绿 | `docs/architecture` 里写的“fresh clone 可复现”不成立；CI/干净环境（以及任何用 worktree 取可归因门数字的人）看到的是一条与产品无关的红；#82 想借 worktree 量一次全量门也因此一开始就不可行 | 让断言落在**能被追踪的东西**上：种子文件由 `scripts/bench_gen_tasks.py::build_suite()` 生成，测试改为 (a) 生成器必须产出这 30 个路径、(b) 内容满足恢复契约（`workspace == SCRATCH_PLACEHOLDER`、`last_green_step == "s2"`、`plan.json` 过 `craft.planner.Plan.from_dict(...).steps`）、(c) 盘上真有就必须逐字节一致，盘上没有则必须仍然满足“`.gitignore` 确实忽略了 `.specraft/`”这个前提；免检数只允许 0（跑过生成器的树）或 30（干净 clone），半有半无直接红 | 主树 37 通过、把同一个文件复制进那棵没有任何 `.specraft` 的 worktree 也是 37 通过（两条路径各测一次，才算“双向”）；`ruff` 全绿。剩下的同类风险如实记下：这条规则只覆盖 bench 的种子，其它依赖本地未追踪状态的测试如果有同类问题，只有干净 worktree 全量跑能暴露——那正是接下来 #82 要做的事 |
| FIX-14 | (#90) 我自己写进本文档的一条“实测”是假的。FIX-12 与旧的“已知未收口”行称 `checker_type` “生产侧实测只有 http/sql/redis/openapi/rabbitmq/tests 六种，而 Web 词表多出一个 `constitution` 没有生产者”，又说 `attribution` “在验收侧扫不到任何字面量产出点”。两句都来自一个只读 dict 字面量的扫描：`agent/contracts/compiler.py::family_id_for` 是按 `if checker_type == "constitution"` 分支的（值在模型里，只是不由 dict 写出），`tests` 来自 `agent/nodes/compile_contracts.py:102`；`attribution` 的 `none`/`unknown` 由 `agent/matrix_policy.py::_merged_attribution` 以常量与分支写出。假测量的来源不是乱猜，而是扫描形状不全 | 一条印在缺陷台账里的假“实测”比一句空话更危险：下一个读它的人会以为已经查过，从而不去补门；而 #81/#87 整套做法恰恰依赖“扫得到所有形状”这个前提 | 补齐四种形状（dict-key / kwarg / 赋值 / 与字段名的比较）+ 读 `_TYPE_RULES` 表首元素，固化成门：`tests/unit/test_checker_type_parity.py` 断言 `_TYPE_RULES ⊆ 可产出集` 且 `Web 词表 == 可产出集`（双向）。结论是这个词表本来就一致（7 值 == 7 词，含 `constitution` 与 `tests`），于是把口头结论换成了一条会红的门 | `tests/unit/test_checker_type_parity.py` 2 通过（纯文本、不碰库，可与后台全量门并行）；`ruff` 全绿。下面那行把先前两句假测量原样更正并写明原因，不悄悄抹掉 |
| FIX-15 | (#91) `attribution`（矩阵页"差异归因"一栏）在 #90 重测时被证明两端一致，但"一致"当时只是我手工扫出来的口头结论，和 #90 里那条被证明是假的口头结论同一种东西；而这个词表的值分散在三处：`agent/nodes/build_matrix.py::_ATTRIBUTION_BY_VERDICT`（verdict→归因表）、`agent/matrix_policy.py::_merged_attribution` 的 `return`（none/unknown/head）、以及 build_matrix 里直接以 `attribution` 为键写下的字面量。只读 dict 键的扫描会把 `unknown` 当成没有主人的词表项——这正是 #90 那次误判的形状 | 归因是评审者判断"这条是这次改动引入的还是改前就有"的唯一依据；任何一处新加值都会以英文原文出现在矩阵页上，而 `head`/`base` 的措辞若被写重，页面就会把两种相反的结论说成同一件事 | 把结论换成门：`tests/unit/test_attribution_parity.py` 读三种生产者形状（表值 / 名字含 attribution 的函数的 return / dict 键字面量），断言 ①探针真的读到五个值（防止扫描形状退化后"看起来全绿"）、②Web `MATRIX_ATTRIBUTION_CN` 的键 == 产出集（双向）、③`head` 与 `base` 的中文措辞不得相同 | 门 3 通过（纯文本，可与后台全量门并行）；变异 **4/4 如预期**：A1 词表删掉 `unknown`、A2 把 UNEXPECTED_FIX 归因改成一个没人翻译的词、A3 让 head 与 base 用同一句中文、**A4 反向对照**（只在 docstring 里出现的 `attribution = "phantom"` 必须不算成值，否则门其实是全文匹配）；对照 exit=0，按字节还原。ruff 全绿。至此词表四条里三条已入门（severity/evidence_type/checker_type/attribution 共四条），只剩评测 `verdict` 需要先拆通道 |
| FIX-16 | (#92) 全量合并门在干净 worktree 里量出 4 红：test_bench_aider、test_swebench_harness（两处）与 test_swebench_llm 的断言 `flag in proc.stdout` 抛 TypeError（NoneType 不可迭代）。真因不是测试脏，而是 `subprocess.run(text=True)` 不带 `encoding=` 时按宿主 locale 解码（这台中文 Windows 是 cp936）：子进程一旦按 UTF-8 输出（正是 RUNBOOK 要求操作者设 `PYTHONIOENCODING=utf-8` 的结果），读取线程解码失败被吞，`CompletedProcess.stdout` 变成 None，产品侧等同于"命令没有输出" | 对验证平台这是假绿通道：mvn/pytest/git 的输出只要含一个非 cp936 字节就静默变空，判定会继续按"没有发现、没有失败"走下去；四条测试在 master 上恒红，主树与干净树一致，所以不是环境噪声 | 产品面 46 处子进程捕获显式写上 `encoding="utf-8"` 与 `errors="replace"`（agent、api、cli、craft、sandbox、ops 与 scripts 下的 bench_*），并新增门 `tests/unit/test_subprocess_text_encoding.py`：pinned 目录内 0 处允许 locale 解码；全仓未定点按实测 66 作棘轮，只准减不准增；另加一条与宿主 locale 无关的机理证明（子进程吐 UTF-8 字节，按 cp936 解码必抛、按 utf-8 解码得到原文） | 门 3 通过；原先 4 红全绿（test_swebench_harness 整文件 9 通过）；ruff 全绿、mypy 216 文件无问题。过程中我自己造成一次工作树污染：批量脚本改写换行并波及 bench 目录，已按 HEAD 还原，并确认 bench 与并发写者的文件没有进入提交。教训：批量改写只能在显式文件清单上做，且对已含 CR 的文本不得再做全局 replace | 仍未收口：另有 6 处 `open(text=True)` 读文件同样吃 locale（agent/contracts/parser.py、craft/rules.py、integrations/notify/templates.py、providers/prompt_templates.py），以及棘轮里剩下的 66 处子进程捕获 |
| 已知未收口 (如实) | 词表线程还剩一处：评测 `verdict`。同一个字段名在 job 终态、门禁、评测逐案、Craft 回路四条通道里复用，按四种形状扫出的字面量有 25 个不同值混在一起（PASS/FAIL/REGRESSION/AMBIGUOUS/COMPLETED/CANCELLED/green/stuck/template/…），值与散文词分不开——必须先把通道拆开（每个通道各自声明域），才谈得上像 #87/#90/#91 那样双向钉门。另：`attribution` 已于 #91 入门，`checker_type` 已于 #90 入门（那两条先前写在本文档里的"实测"是假测量，已在 FIX-14 原样更正，未抹掉） | 评测页仍可能出现无词的值或直出英文；一个字段名跨四条通道也让"这个词属于哪套刻度"无法回答 | 先定 `verdict` 的通道归属并逐通道声明域，再补门 | ⏳ 需开发 |
## 6. 待基础设施 / 需开发清单 (如实标注, 均给出精确缺口位置)

| # | 项目 | 缺口位置 | 状态 |
|---|---|---|---|
| 1 | 崩溃作业自动回收器 (RUNNING 超时 → 续跑/重投递) | 已落地: 人工入口 `specproof ops recover` (#68, 只读模式 #74), 自动周期触发在 worker 进程内 (#71, 默认 300s + Redis 作用域锁 + 重试预算上限)。仍缺的是跨进程 provider 健康信号, 所以 provider 暂停分支的定时恢复仍默认关 | ✅ 已落地 (剩 provider 信号) |
| 2 | WAITING_FOR_PROVIDER 接线 | 生产者已接 (#64): 可重试的 provider 故障 (429/超时类) 走 CAS 暂停而非 FAILED, 且暂停未落库时不对外宣告; 仍缺的是把该行捞回来的回收器 (见第 1 行) | 🟡 生产者已接, 回收待开发 |
| 3 | OIDC 会话注销/令牌吊销端点 | api/ 无 logout/revoke | ⏳ 需开发 |
| 4 | Merge Certificate 撤销 | evidence/ 无撤销能力 (签名本身亦未实现, Phase 1+) | ⏳ 需开发 |
| 5 | 外部通知接线 (Slack/邮件/webhook) | 已接 (#65): worker 在每一次被接受的终态写入之后调用, 五个 notify 计数可区分"发了/没配置/该 verdict 无模板/对端拒绝/连接器炸"; 剩下的只是部署时是否设环境变量 | ✅ 已接线 |
| 6 | 宿主备份工具 | mysqldump/mongodump/mc/redis-cli 宿主未安装 (实测) — 全部容器内执行或安装后按 §3.1 命令执行 | ⏳ 待基础设施 |
| 7 | Finding 验收反馈的 Web 入口 (#84, Go/No-Go #13 的数据来源) | 已落地: `apps/web/src/pages/FindingDetail.tsx` 的 `FeedbackSection` 消费 `POST`/`GET /api/v1/jobs/{job_id}/feedback` (0012 保证一人一票), 三种 `state` 文案可区分"新票/改票/重复提交", 加载失败与"没人投过"分开渲染, 0 票回答"无法计算"而不是 0%。**仍未闭合**: `specproof_phase0` 里 `uniq_feedback_finding_actor` 还不存在 (对共享产品库做 DDL 需批准), 它由共享栈下一次 `ensure_tables()` 应用 0012 时收敛, 见 §5 FIX-6/FIX-7 | ✅ 已落地 (产品库约束待启动时收敛) |

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
