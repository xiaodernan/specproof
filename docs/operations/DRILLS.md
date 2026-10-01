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
| 3 | 安全响应桌面推演 (pause/freeze/revoke/isolate/preserve/notify) | 📝 桌面核对 | 6 动词 × 现有端点/命令逐一核对; 20 项可执行, 1 项需开发 (见 §3; 数字由缺口门按表实数核对) |
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
          "summary_present": 1,
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
          "summary_present": 1,
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

**仍属"需开发"的缺口** (如实标注): 目前没有任何组件会自动续跑崩溃后停在 RUNNING 的作业 — 本演练的续跑由 ops.drills.resume_job (scripts/drill_worker_kill.py 调用) 显式驱动; 生产需要一个启动时回收器 (扫描 RUNNING 超时作业 → 重投递/直接续跑)。该回收器未实现 = ⏳ 需开发。 **更正 (2026-09-28, #129)**: 上句"没有任何组件会自动续跑…该回收器未实现"写下即为假 — 自动回收器已落地: `agent/worker.py:153` `_start_reclaim_tick` 周期触发 `:1128` `run_reclaim_pass` → `:1193` `reclaim_stale_running_jobs` (#71 `738f1c3`, 默认 300s + Redis 作用域锁 `specproof:lock:scope:stale-job-sweep`), 人工入口 `specproof ops recover` (#68/#74) 仍在; 本演练的"显式续跑"是对照手段而不是生产缺口。原句按 FIX-14 规矩保留不抹掉。真缺口只剩一条: 周期路径 `_reclaim_once` 未传 `provider_ready` (跨进程 provider 健康信号), 已收敛到 §6 第 1/2 行。

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
4. **需开发缺口**: 状态机定义了 WAITING_FOR_PROVIDER (RUNNING → WAITING_FOR_PROVIDER → RUNNING/QUEUED/FAILED), 但 worker 的 provider 故障路径目前直接 FAILED, 从未转入该可恢复态; RUNBOOK.md "job 停在 WAITING_FOR_PROVIDER" 一节目前没有生产者。 = ⏳ 需开发 (worker 接线)。 **更正 (2026-09-28, #129)**: 上句"从未转入该可恢复态"写下即为假 — 暂停生产者在 `agent/worker.py:424` (`"waiting_for_provider" if provider_wait else "failed"`, #64), 恢复在 `:1370` `recover_waiting_for_provider_jobs(provider_ready=…)` 并由 `:1128` `run_reclaim_pass` 调用 (#68/#71/#74, 提交 `448aa6b`/`3c97481`)。原句保留; 残留只有 worker 周期路径未传 `provider_ready` (§6 第 1/2 行)。

---
## 3. Drill 3 — 安全响应桌面推演 (pause/freeze/revoke/isolate/preserve/notify) 📝 桌面核对

**目标**: 按计划书 §18.5 的事故处理动词 (暂停/冻结/撤销/隔离/保全/通知), 把每一步映射到"现有端点/命令", 并如实标注 可执行 / 需开发。本次为桌面核对: 端点/命令/工具全部实测核对 (路由枚举、CLI 子命令、工具可用性、broker 命令语法), 未对任何真实业务状态执行破坏性动作。

**桌面核对证据 (2026-08-19 实测)**:

- API 路由枚举 (python 导入 api.server 实测): POST /jobs, POST /jobs/{job_id}/cancel, GET /jobs{,/{job_id},/{job_id}/summary,/{job_id}/progress}, POST /webhooks/github, /api/v1/admin/{tenants,users,tokens,audit} (含 DELETE /api/v1/admin/tokens/{token_id} 与 POST /api/v1/admin/users/{user_id}/status), /auth/{config,me,oidc/login,oidc/callback}, /api/v1/{dashboard,health} 等 — 全部存在。
- identity CLI (python -m api.identity.cli): init-admin / mint-token / list-users 三个子命令 (实测)。
- 宿主工具实测: docker ✅, git ✅; mysqldump/mongodump/mc/redis-cli 宿主未安装 → 全部走容器内二进制 (docker exec)。
- broker 实测: docker exec specproof-rabbitmq rabbitmqctl list_queues 输出 7 条队列 (q.p1.verify.job + .retry + .dlq + 4 条 phase0 队列); purge_queue 语法实测确认。
- 缺口实测: integrations/notify/ (webhook/Slack 连接器) 存在且有单测 — 原"主管道零调用点"缺口已于 #65 接掉 (worker 在每一次被接受的终态写入之后调用 _maybe_notify_terminal); 但默认仍不发声: 未设 SPECPROOF_NOTIFY_WEBHOOK_URL 时工厂返回 DisabledConnector, 只有 specproof_notify_disabled_total 在涨; evidence/ 无任何 revoke/吊销 能力; api/ 无 logout 端点; **更正 (2026-09-28, #129)**: 同一行"api/ 无 logout 端点"为假 — `DELETE /api/v1/admin/tokens/{token_id}` 早在合并 `0d85586` 就在 `api/routes/admin.py`; 自 #129 起会话注销也有 `POST /auth/logout`。原句按 FIX-14 保留。 WAITING_FOR_PROVIDER 的生产者已于 #64 接上 (可重试 provider 故障改为暂停)。**回收器触发点已于 #68 接上**: `specproof ops recover` (cli/specproof/commands/ops.py) 是 `reclaim_stale_running_jobs` / `recover_waiting_for_provider_jobs` 的生产调用点, 单测锁住「命令确实调用这两个函数」并锁住「判定失败不等于没有卡住的作业」; **自动周期触发已落地 (#71, 2026-09-26)**：`agent/worker.py` 的 worker 进程自带回收 tick（默认每 300s，`WORKER_RECLAIM_INTERVAL_SECONDS=0` 才回到只靠人工命令），多副本由 Redis 作用域锁 `specproof:lock:scope:stale-job-sweep` 保证一轮只有一个 worker 真的在扫，且**释放只认自己拿到的 token**（否则跑过 ttl 的那轮会删掉接班者的锁）；Redis 答不出锁状态时本轮**跳过**而不是无锁硬扫 —— 同一个 Redis 也是租约探针，此时扫了也会在第一个候选前停下来，跳过不丢业务、不重复投递；扫描抛异常时 tick 继续活着（打破这一轮的那次故障，正是下一轮要处理的故障）。演练口径：`curl -s localhost:9100/metrics | grep specproof_worker_reclaim` 看 `last_ok_timestamp` 是否在推进，然后才看各个计数。**#71 的门证（2026-09-26 实测）**: 定向回归集 `tests/security + tests/fault + 26 个 import 了 agent.worker/storage.redis/storage.mysql 的 tests/unit 文件` = **601 passed / 2 skipped / 570.43s**（退出码取自日志自己的 `PYTEST_EXIT=0`，不经管道）；`ruff check .` 全绿、`mypy .` 213 source files 无问题、新增 `tests/unit/test_reclaim_tick.py` 21 passed、变异门 **18/18 逐条 RED** 且各自指名被测项（按 sha 校验还原后对照跑绿）。**全量合并门没跑完，这是已知欠账 (#82)**：本机同时有 3 个 pytest 在跑（另一个 SpecProof 会话 + 另外两个项目），门被拖到 4-5 倍慢并在 5% 处出现 2 个红——单独重跑那个文件是 **14 passed / 520s**，所以那两个红是内存饿死（`code 0x8007000e` = E_OUTOFMEMORY，~1GB free）而不是回归；判据留档：慢文件里的单个红，必须先单跑再定罪。补法用 worktree（`git worktree add --detach $TEMP/sp-gate71 <sha>` + 主树 .venv 跑），这样数字属于那个 commit 而不是别人的脏树。(以下两句保留为历史记录。)周期触发的两个前置之一已落地 (#71)：`reclaim_stale_running` 现在受作业自身 `retry_count >= max_retries` 约束，预算耗尽直接 RUNNING→FAILED 且不重投，所以默认开的 tick 不会把必然崩溃的作业无限重投；另一个前置（实测缺失）是 provider 健康信号 —— 没有它，`recover_waiting_for_provider_jobs` 的定时轮会在模型服务仍在故障时空跑掉重试预算，把作业直接判成 FAILED。**只读判定已落地 (#74)**: `specproof ops recover --dry-run` 回答「有没有卡住的作业」而不动任何一行 —— 起因是 2026-09-25 一次只想看看的命令当场把作业重投了。**残行已收口 (#73)**: `TestStateMachineWithDB` 现在删掉自己写的行并断言删成功 (实测该文件每次运行净增 0 行；修之前每跑一次净增 1 行，而 `test_cas_prevents_concurrent_claim` 留下的正是「RUNNING + 过期 updated_at」这个被回收器认成卡死作业的形状)。**#75 已收口 (2026-09-26, 门证见 §3.3)。以下为修前状态 (历史)**: 本机 MySQL 只有 `specproof_phase0` 一个业务库，`specproof@%` 除该库外只有 USAGE，而 13 个测试文件（其中 9 个在 tests/unit，4 个在 tests/integration）直接构造真实 `MySQLStore()` —— 所谓单测其实写在产品表里 (实测累计 177 行 `/test/…` 残行（2026-09-26 复测：#73 当时记录 165，此后净增 12），Dashboard 与引导页的计数把它们算进去)；同一 schema 下 `mark_stale_for_head` 一度会把表内**所有** QUEUED/RUNNING 行改成 STALE——该无作用域缺陷已于 **#76** 收口 (现在按 `repo_path` 限定并排除新作业本身, 空 repo 直接拒绝)；但它留下的教训仍在: 在共享库上跑测试就等于对别人的作业动手。实测更尖锐的数字: 本机 `verification_jobs` 总行数 177（2026-09-26 复测，上次记录为 165）, 其中 `repo_path LIKE '/test/%'` 也是 177 —— 产品表当前 100% 是测试残行 (修前该文件每跑一次再 +1), Dashboard 与引导页把 177 全部当真作业计数。 **更正 (2026-10-01, #138)**: 同一行"evidence/ 无任何 revoke/吊销 能力"为假 — 自 #138 起 `evidence/revocation_log.py` 提供追加只读吊销日志, `POST /api/v1/admin/certificates/revoke` 落一条签名吊销; 原句按 FIX-14 保留。

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
| revoke | OIDC 会话注销/令牌吊销 | **更正 (2026-09-28, #129)**: 原声称"无 logout/revoke 端点 (api/ 实测 0 命中)"为假 — `DELETE /api/v1/admin/tokens/{token_id}` 早在合并 `0d85586`; 会话注销现为 `POST /auth/logout` (`api/routes/admin.py`): 本地 `sp_*` 由 `local_token_id` 解析**刚被中间件验证过**的凭证取 id → `revoke_token` → `verify_local_token` 复验后才报 `revoked:true` (下一次请求 401); OIDC id_token 是无状态 JWT 不可吊销 → `revoked:false` + 发现文档 `end_session_endpoint` (带 `id_token_hint`), 无该端点/发现失败写进 `reason` 而不是编造 | ✅ 可执行 (#129) |
| revoke | Merge Certificate 撤销 | evidence/ 无撤销能力 (证书本身未签名, 撤销属 Phase 1+ 计划) **更正 (2026-10-01, #138)**: 两句皆为假 — P5 起证书由 `evidence/signing.py` 用 Ed25519 签名, 撤销已落地为 `POST /api/v1/admin/certificates/revoke` (签名语句 + 追加只读 JSONL, 签不上名则 503 不落盘); 原句按 FIX-14 保留 | ✅ 可执行 (#138) |
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

- 暂停/冻结/撤销/隔离/保全的主干路径全部有现成端点或命令 (20 行 ✅ 可执行, 由缺口门按 §3.1 表实数核对), 事故黄金窗口内的动作不需要写新代码。
- 4 项缺口如实标注: OIDC 注销/吊销、证书撤销、外部通知接线、宿主 mc 工具 — 每一项都给出精确缺口位置。 **更正 (2026-10-01, #138)**: 该清单已过期 — OIDC 注销 #129、外部通知 #65、证书撤销 #138 均已落地, 现存缺口 1 项 (宿主 mc 工具, 见 §3.1 与 §6 第 6 行); 原句按 FIX-14 保留。
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
        "summary_present": 1, "findings": 2, "capsules": 2, "errors": 0
      },
      "relay_replay_published_rows": 1,
      "outbox_publish_count": 1,
      "outbox_published_at_set": true,
      "side_effects_after_duplicate_delivery": {
        "terminal_transitions": 1, "running_transitions": 1,
        "summary_present": 1, "findings": 2, "capsules": 2, "errors": 0
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
| FIX-16 | (#92) 全量合并门在干净 worktree 里量出 4 红：test_bench_aider、test_swebench_harness（两处）与 test_swebench_llm 的断言 `flag in proc.stdout` 抛 TypeError（NoneType 不可迭代）。真因不是测试脏，而是 `subprocess.run(text=True)` 不带 `encoding=` 时按宿主 locale 解码（这台中文 Windows 是 cp936）：子进程一旦按 UTF-8 输出（正是 RUNBOOK 要求操作者设 `PYTHONIOENCODING=utf-8` 的结果），读取线程解码失败被吞，`CompletedProcess.stdout` 变成 None，产品侧等同于"命令没有输出" | 对验证平台这是假绿通道：mvn/pytest/git 的输出只要含一个非 cp936 字节就静默变空，判定会继续按"没有发现、没有失败"走下去；四条测试在 master 上恒红，主树与干净树一致，所以不是环境噪声 | 产品面 46 处子进程捕获显式写上 `encoding="utf-8"` 与 `errors="replace"`（agent、api、cli、craft、sandbox、ops 与 scripts 下的 bench_*），并新增门 `tests/unit/test_subprocess_text_encoding.py`：pinned 目录内 0 处允许 locale 解码；全仓未定点按实测 66 作棘轮，只准减不准增；另加一条与宿主 locale 无关的机理证明（子进程吐 UTF-8 字节，按 cp936 解码必抛、按 utf-8 解码得到原文） | 门 3 通过；原先 4 红全绿（test_swebench_harness 整文件 9 通过）；ruff 全绿、mypy 216 文件无问题。过程中我自己造成一次工作树污染：批量脚本改写换行并波及 bench 目录，已按 HEAD 还原，并确认 bench 与并发写者的文件没有进入提交。教训：批量改写只能在显式文件清单上做，且对已含 CR 的文本不得再做全局 replace | 仍未收口（并撤回本行上一版里的两处错数）：我曾写「另有 6 处 open(text=True) 读文件同样吃 locale」与「棘轮剩下 66 处」，两处来自同一个错误视角——扫描按「带 text= 关键字的调用」匹配，于是把 RepoRule(...) / BuiltPrompt(...) / Notification(...) 这些**带 text 字段的模型构造器**当成了解码点；改用「读文件的 text=True」再查一遍时，剩下的候选全是 open(path, "rb") 这类二进制读和 read_text("utf-8") 位置传参，本身没有 locale 问题。用门自己的视角（只看 subprocess 调用）重测，真实残余是 55 处，棘轮已按 55 收紧并把这两处误判的成因写进常量注释。另有 3 处测试里的裸 read_text()（缺 encoding，会吃宿主 locale）在同一批里补上。 |
| FIX-17 | (#109) 词表线程最后一条：同一个字段名 `verdict` 散在 **15 条通道**里（job 终态、报告结论、控制台执行结果、独立验收投影、矩阵行、差分结果、评测逐案、Craft 回路、Craft 基准、回放报告、缓存判定、文件名分类、独立脚本报告、演练日志、评审投票、门禁状态、作业状态），六形状重测得 **39 个不同字面量 + 18 处不可枚举的非字面写 + 2 个须豁免的文件**。**原行写的"25 个"是错数，按 FIX-14 的规矩原样更正不抹掉**：它来自只扫 dict-key/kwarg/赋值/比较四种形状的旧视角，漏了 `.get("verdict", 默认值)`、关键字里的集合字面量与三元条件——与 #90 那次假测量同源。消费端也各写各的：`apps/web/src/ui/util.tsx` 的 `VERDICT_LABELS` 认 **8 个词**，而 worker 写进 `summary.verdict` 的只有 3 个（把状态词 STALE/ERROR/CANCELLED 与矩阵词 UNVERIFIED 当成了判定词，状态词在 `JobDetail.tsx` 另有 `STATUS_HELP` 负责，属于重复且错误的一份）；`toneMap.ts` 的 `EVAL_VERDICT_CN` 缺 `PARTIAL`（CLI 会产出，页面直出英文）；`JobDetail.test.tsx` 的 fixture 拿死词 `UNVERIFIED` 当判定值——正是 #90 那种"死词被绿门认证"的形状 | 评审者在"验证结论"一栏看到的 8 条词条里 5 条没有生产者，真正会落到该栏的词之外（控制台投影的 `COMPLETED`/`UNKNOWN`）反而没有词；一个字段名跨 15 条通道让"这个词属于哪套刻度"无法回答，`NEEDS REVIEW` 与 `NEEDS_REVIEW` 两种拼法也没有人声明哪个是正字 | 先声明通道再钉门：新增 `evidence/verdict_channels.py` 逐通道登记（可提及该字段的文件 / 域 / 不可枚举写的文件 opaque / 字面量无处可写时的 witness 行 / 权威源 / 说明），新增 `tests/unit/test_verdict_channel_parity.py` **13 条双向门**：六形状扫描（dict-key、kwarg、kwarg 集合、赋值与下标写、属性与变量比较、`.get` 默认）+ 非字面写必须声明 opaque（否则红并点名 `文件:行`）+ 有权威源的通道必须与权威**相等**（`craft.accept::AcceptVerdict`、`api/routes/feedback.py` 的 pydantic `pattern=`、`craft.gates::GateStatus`、`storage/mysql.py::_VALID_TRANSITIONS`）+ 4 条消费端一致性（Web 验证结论词条 == worker 三词且 `verdictTone` 覆盖 ⊆ 词条、评测词条 == CLI 四词、notify `TERMINAL_VERDICTS` == summary∪report 归一化后的集合、GitHub conclusion 的键 ⊆ 作业状态且 ⊇ summary 三词）+ `evidence/verdict.py` 的 `VerificationDecision(...)` 三元分支 == 通道域 + 3 条反向对照（注释/docstring 不算值、未归属文件必须被点名、三元条件写必须记为不可枚举）。Web 按声明收口：`VERDICT_LABELS`/`verdictTone` 收成 3 词、`EVAL_VERDICT_CN` 补 `PARTIAL`、fixture 死词改 `BLOCKED` | `tests/unit/test_verdict_channel_parity.py` **13 通过**；`ruff` 全绿；`mypy` **218** 文件无问题；`tsc` 0 错、`vitest` **44 文件 / 340 通过**。变异 **4/4 逐条 RED 且按字节还原、对照 exit=0**：M1 把死词 `STALE` 放回 `VERDICT_LABELS`（标题词条门红）、M2 删掉 `EVAL_VERDICT_CN` 的 `PARTIAL`（评测词条门红）、M3 从 `job_status` 声明里删掉状态机真有的 `STALE`（**两门同时红**：权威相等门 + GitHub conclusion 键 ⊆ 状态门，两个消费者各自独立接住）、M4 在未归属文件 `api/server.py` 写一条 `verdict` 字面量（所有权门点名该文件:行）。全量合并门 `gate_20260927c.log`：**3217 passed, 5 skipped, 1910.20s** —— 与上一跑逐位对得上（3203 通过 + 那 1 条被修好的红 + 本批 13 条新门）。过程中如实记一次我自己的红：新建的门文件带 UTF-8 BOM，欠账门按"读不出的文件即 finding"把它算成第 56 条（顶格 55/55）而全量门 1 红——门的行为是对的（不可解析的文件本来就该被点名），是我写文件时带了 BOM，去掉后恢复 55 |
> **FIX-17 全量合并门追记（2026-09-28 复核）**：`pytest tests/unit tests/security tests/fault -q`
> ⇒ **3217 passed / 5 skipped / 1910.20s (31:50)，exit 0**，日志 `gate_20260927c.log`。
> 同批的 `gate_20260927b.log` 是 BOM 未修时的那一次：`1 failed, 3203 passed, 5 skipped / 2210.59s`，
> 唯一红是欠账棘轮 `assert 56 <= 55`，成因见 FIX-17 末段（新建的门文件带 UTF-8 BOM 被算成第 56 条）。
> 该门跑在**主树**上，起点晚于全部源码改动（源码最后改动 23:44，门 23:45:50 起跑、00:17:40 收），
> 因此这个数字属于本批要提交的这棵树。消费端证据同时被**独立复跑**确认：
> `test_verdict_channel_parity.py` **13 通过**、`ruff check .` 全绿、`mypy .` **218** 文件无问题、
> `tsc --noEmit` **0 错**、`vitest run` **44 文件 / 340 通过**。
>
> 另记一处**提交前发现的树污染（不是本批引入，但会挡住本批的门）**：仓库根上有两个未跟踪的调试脚本
> `test_compile.py` / `test_static.py`（硬编码绝对路径、import 未排序），使 `ruff check .` 报 **4 错**、
> `mypy .` 从 218 涨到 **220 文件 3 错** —— 即本仓库文档里的门命令在这棵树上**根本不可能全绿**，
> 而 FIX-17 记录的 "ruff 全绿 / mypy 218" 正说明它们是在那次门之后才出现的。已把两个脚本移到工作区根
> `D:\面试项目\`（该目录本就是本项目的草稿约定位置，另有 44 个同类脚本），仓库内门恢复全绿（218 文件）。
> 教训与 FIX-16 的"批量改写只能落在显式清单上"同源：**临时脚本必须写在仓库之外，否则它会静默改变门的结论。**

| FIX-18 | (#110) 状态通道（#109 顺手量出并登记为"待开发清单第 8 行"）有**三份手写副本且互相矛盾**。权威 `storage/mysql.py::_VALID_TRANSITIONS` 有 10 个状态。① `api/routes/jobs.py` 的 `?status=` 过滤器收 11 个词：**收下了 `UNVERIFIED`/`INCONCLUSIVE`**（矩阵/判定词，`RUNNING` 永远不会转到它们 ⇒ 查询永远匹配不到行，而页面照常回答"没有找到符合条件的验证"，与真实空结果**无法区分**），同时**用 422 拒掉了 `STALE`** —— 而 `STALE` 是本系统真会写的终态。② `apps/web/src/ui/StatusPill.tsx::STATUS_LABELS` 同病：Jobs 的筛选下拉是**由这张表生成的**，于是它向用户提供了两个不可能的筛选项，却从不提供"已过期"。③ `apps/web/src/pages/JobDetail.tsx::STATUS_HELP` **漏了 `PENDING`** —— 每个作业被 insert 时写的正是 `'PENDING'`，于是刚创建的作业只能拿到兜底横幅；同时留着一个**永远到不了**的 `UNVERIFIED` 条目。④ `JobDetail.test.tsx` 拿这个不可达的词当 job status 写夹具，于是那条绿门**认证了一个不可能的状态**（#90 记录过的"死词被绿门认证"形状） | 用户按真实状态筛"已过期"拿到 422；按"证据不足"筛则拿到一个**永远为空却看起来正常**的结果页 —— 这是把"这个筛选无意义"伪装成"你没有这类作业"；新建的作业看到的是通用兜底文案而不是"已创建、正在排队" | 让集合**从状态机派生**而不是再抄一遍：`storage/mysql.py` 新增 `ALL_STATUSES`（键 ∪ 全部可达目标），`api/routes/jobs.py` 改用它（未知词仍然 422 —— 一个匹配不到任何东西的筛选**必须报错**，不能回答"没找到"）。前端新增 `JOB_STATUSES`（按生命周期排序的 10 个真状态）供下拉使用，`STATUS_LABELS` 删掉两个幽灵词（保留 `COMPLETED`，它是进度流用词，已注明不属于 `JOB_STATUSES`），`STATUS_HELP` 补 `PENDING` 删 `UNVERIFIED`，夹具的死词改 `BLOCKED`。新增 `tests/unit/test_job_status_channel_parity.py` **8 条双向门**：AST 读状态机（键 ∪ 目标，`set()` 与 `{…}` 两种写法都读）→ `ALL_STATUSES` 必须相等、`STALE` 必在而两个幽灵必不在、路由**不得再出现**这两个字面量、前端 `JOB_STATUSES` == 状态机、每个状态都有中文标签、`STATUS_LABELS` 不得含幽灵、Jobs 下拉必须由 `JOB_STATUSES.map(` 驱动（不得再用 `Object.entries(STATUS_LABELS)`）、`STATUS_HELP` == 状态机（双向）。行为层另加 13 条：`?status=` 对 10 个真状态全部 200、对 3 个非状态词全部 422；Jobs 下拉含全部 10 个值（含"已过期"）且不含两个幽灵词 | `test_job_status_channel_parity.py` **8 通过**；`test_api_jobs.py` +13 例（41 通过）；受影响后端集 **107 passed**；`ruff check .` 全绿（新文件 import 排序已 `--fix`）、`mypy .` 218 文件无问题；`tsc --noEmit` 0 错、`vitest run` **44 文件 / 342 通过**（Jobs +2）、`vite build` 通过。**变异探针 3/3 如预期**：P1 把路由还原成旧字面量 ⇒ **4 红**并逐条点名（重抄门 + `[STALE]` 被拒 + `[UNVERIFIED]`/`[INCONCLUSIVE]` 被收）；P2 从 `STATUS_HELP` 删掉 `PENDING` ⇒ 1 红（`test_job_detail_guidance_covers_every_status_including_pending`）；P3 把 `UNVERIFIED` 复活进 `STATUS_LABELS` ⇒ 1 红（`test_the_pill_map_does_not_carry_verdict_words`）。全量合并门见下方追记 |
| FIX-19 | (#111) `mcp/tools.py::_run_cli` 用 `subprocess.run(text=True)` 却不写 `encoding=`：父进程按**宿主 locale**（本机 cp936）解码，子进程按它继承到的 `PYTHONIOENCODING` 编码，两端各走各路。FIX-16(#92) 当年钉了产品面 46 处、`PINNED_SCOPES` 十个目录，**偏偏没把 `mcp/` 算进名单**，所以这一处三年一直被记成"欠账"而不是缺陷；同批还漏了 `contracts/`、`observability/`（这两处实测 0 处未定点，但它们是 shipped 入口加载的包，本就不该按欠账记账）。顺带一条**假引证**：FIX-16 写"正是 RUNBOOK 要求操作者设 `PYTHONIOENCODING=utf-8` 的结果"，而 `grep -ran PYTHONIOENCODING docs/` 今天只命中 DRILLS.md:273 那一行自己——RUNBOOK.md 里没有这句话（也没有 chcp/编码/乱码），按 FIX-14 的规矩在这里更正而不是继续沿用 | 字段级实测（修复前，`9ab533b` 的干净隔离 worktree，父进程偏好 cp936，子进程打印 `VERDICT: PASS 中文路径 D:/面试项目/x.py` 与 `HTML Report: D:/面试项目/report.html`）：`PYTHONIOENCODING` 未设 ⇒ 两字段都对；`=utf-8` ⇒ **两字段都错**，`parse_verify_stdout` 交回 `summary["html_report"] == 'D:/闈㈣瘯椤圭洰/report.html'`；`=gbk` ⇒ 都对。把同一棵树、同一个脚本的父进程放进 UTF-8 模式（`-X utf8`）后红绿**整体翻转**（未设与 gbk 红、utf-8 绿）⇒ 哪一行坏由机器决定，代码里没有任何东西担保它。危害不是崩溃而是"看起来对"：`parse_verify_stdout` 对 VERDICT/HTML Report/Merge Certificate/`.zip` 胶囊/错误行取的是整尾 `(.+)`（`(\S+)` 只用在 contract_id 与 evidence_type 上，我上一版草稿把这条通路说反了，一并更正），所以 `PASS` 前缀照样存在、路径照样是个像样的绝对路径，而 `specproof mcp serve`（docs/operations/EXPERIENCE_GUIDE.md:58，六个工具之一 `specproof_verify`）是把这份投影直接交给外部 AI Agent 的**产品入口**——对验收平台，这就是一条假绿通道：证据链接指向一个盘上不存在的文件，而这个产品本身就装在 CJK 目录下 | 两端同时钉：子进程 env 强制 `PYTHONIOENCODING=utf-8`，父进程 `encoding="utf-8"`（只钉一端是抛硬币，见下面 R1/R2）；`PINNED_SCOPES` 加入 `mcp`、`contracts`、`observability`；棘轮 55→54（只有真修好的那一处离开欠账，扩名单不减数）；新门 `tests/unit/test_mcp_cli_output_codec.py` 7 条：①三行"子进程环境表"（未设/utf-8/gbk 必须读回同一句话，且**断言到解析后的 `verdict` 与 `html_report` 字段**，不停在 stdout 层）、②两行机理证明（同一字节按 utf-8 与 cp936 解码必须一个对一个错——载荷若哪天两边都能读对，这条先红，因为它说明上面的表证明不了任何事）、③AST 读 `_run_cli` 的声明并要求**两端写名的 codec 相等**（宿主 locale 恰好与载荷一致时行为表看不出一边没钉，这条补那个洞）、④shipped 运行时 lane 必须在 `PINNED_SCOPES` | 修复后门 **11 通过**（新 7 + 棘轮 4）；13 个"扫全仓"型结构门 **87 通过**；`ruff` 全绿；`mypy` **218** 文件无问题。修复后同一载荷在两种父进程 locale × 三行环境下 **6/6 全部 verdict_ok/report_ok=True**（即不变性成立，不是"这台机器碰巧对"）。变异见证 **6/6 逐条 RED 且红集合与预测完全一致**（第二版把预测从散文改成集合，因为第一版四条预测不完整，见下）：R1 撤父端 ⇒ 三行全红＋声明门＋pinned 门＋欠账门；R2 撤子端 ⇒ 未设与 gbk 两行红＋声明门（utf-8 行**绿**，因为测试给它设的正是 utf-8）；R3 两端全撤＝出厂形状 ⇒ 只有 utf-8 行红；R4 两端钉成不同 codec ⇒ 三行红＋"两端相等"断言红；R5 把 `mcp` 挪出名单 ⇒ 只有 lane 门红；R6 在 `mcp/` 植入一处未定捕获 ⇒ pinned 门与欠账门同时红。两次对照 exit=0、每次还原按字节校验。**如实记自己的预测错**：第一版散文预测漏了"任何去掉 `encoding=` 的臂都会同时拽红欠账门"——因为 `DEBT_CEILING = 54` 就是实测值、零余量，而它统计的是**全仓**含 pinned 目录；改成集合预测后重跑 6/6 命中。**平面**：`9ab533b`（修复前基线）全量合并门 3238 通过/5 跳过/1883.53s/exit 0；#111 落库后的全量门另行追记 |
| FIX-20 | (#129) **会话注销端点缺失 + 台账里四处写下即为假的缺口声称**。功能面: 全仓没有 logout 端点 — 本地 `sp_*` 只能等过期, OIDC 只能关标签页; 而 `apps/web/src/App.tsx:131` 的"退出"按钮只清本地凭证。诚实面 (2026-09-28 复核, 四处): ①§1 末"该回收器未实现 = ⏳" (自动回收器 #71 早在 `agent/worker.py:153`); ②§2 末"worker 从未转入 WAITING_FOR_PROVIDER" (生产者 #64 在 `:424`, 恢复在 `:1370`); ③§3.1 "api/ 实测 0 命中" (admin `DELETE /tokens/{token_id}` 早在 `0d85586`); ④§6 第 3 行"api/ 无 logout/revoke" 同源。另过期两处: §6 第 2 行把"回收待开发"当状态 (回收器已存在, 真残留是 `_reclaim_once` 未传 `provider_ready`), 两个 gap audit 的"OIDC logout ⏳" | 一份自称"如实标注"的台账里有四条与代码相反的"⏳需开发": 读者会据它去开发已经存在的东西, 或据"0 命中"以为吊销无从下手; 登出缺口本身让"撤销"这一事故动作在会话层不可执行 (§3.1 revoke 表里唯一一条 ⏳) | 新增 `POST /auth/logout` (`api/routes/admin.py`): 本地 `sp_*` 用新增的 `tokens.local_token_id` 解析**刚被中间件验证过**的凭证取 id → `revoke_token` → `verify_local_token` **复验**后才报 `revoked:true` (复验不过就如实报 false), 不给调用方"声称已吊销"的口子; OIDC id_token 是无状态 JWT → `revoked:false` + 发现文档 `end_session_endpoint` (带 `id_token_hint` 与 SPA 回跳), 发现失败/无该端点都写进 `reason` 而不是编造。四处假声称按 FIX-14 原样更正 (假句留在原行, 行尾挂"更正"标记), §6 第 2 行改成真残留, 新增第 9 行登记 Web 端未接线, 两个 gap audit 同批改口 | `tests/unit/test_tenant_auth.py` +7 = **43 通过** (本地吊销后同一凭证下一次请求 401 而旁人凭证不受影响、store 假动作如实报 false、匿名 401、OIDC `revoked:false` 且**反向对照**证明 id_token 事后仍可用、IdP 发布 `end_session_endpoint` 时原样回传、legacy 模式 503、`local_token_id` 形状), 新门 `tests/unit/test_drills_gap_claims_hold.py` **8 通过**: 假句必须与"更正"同行 (抹掉假句同样红)、探测器自身有非空对照 (旧句判红 / 带标记判绿 / 描述新端点不误报)、`POST /auth/logout` 必须出现在 **OpenAPI 合同**里且 §6 第 3 行标 ✅ 并指向本门 (走 `app.routes` 只会看到 `_IncludedRouter` 包装而假绿 — 这条正是量出来的)、§4 两行指向的端点都真注册、`evidence/` 仍零 revoke ↔ 第 4 行仍⏳、`_reclaim_once` 仍不传 `provider_ready` ↔ 第 1/2 行残留、Web 仍零引用 `auth/logout` ↔ 第 9 行待接线 且认账"按钮已存在"、`docs/api/auth/README.md` 的端点清单必须覆盖 OpenAPI 里每个 `/auth/` 操作且不得提到合同外的路径 (双向)。**变异 4/4 逐条 RED 且红集合与预测完全一致**: M1 路由改名 → 2 红 (合同门 + §4 端点门)、M2 第 3 行改回 ⏳ → 1 红、M3 抹掉 L95 的更正标记 → 1 红、M4 给 `_reclaim_once` 传 `provider_ready` → 1 红; 四次均按 sha 校验字节还原, 基线与末轮对照 exit=0。全量门数字见本行下方追记 |

> **FIX-20 全量合并门追记（2026-09-29）**: `pytest tests/unit tests/security tests/fault -q -p no:randomly` → 收集 `3381 items`, 隔离脚 `MySQL test isolation (redirected -> specproof_test): product schema '/test/%' rows 0 -> 0; no test row landed in the product schema`, 汇总 `=========== 5 failed, 3371 passed, 5 skipped in 1454.43s (0:24:14) ===========`, 日志 `gate_20260929b.log`。
> **5 个红已逐个定罪, 全部在单跑下转绿, 不是回归**: `TestNoHardcodedKeys::test_no_api_key_in_config_files` 单跑 **1 通过** 且事后在当前树上直跑 `scan_config_tree(PROJECT_ROOT)` = **0 命中**; `TestOutputFlood` 4 条单跑 **4 通过**。判据与 #117 一致 (慢文件里的单个红先单跑再定罪) — 全量门负载偶发。
> 口径说明: 相对 FIX-17 的 3217, 本次 +154; 其中本批 +15 (`tests/unit/test_tenant_auth.py` +7, `tests/unit/test_drills_gap_claims_hold.py` +8); 其余是 #110…#128 期间的测试增长与共享树上并发会话的在途改动。跑测平面是共享工作副本, 未提交文件含 `craft/executor.py`、`craft/tools.py`、`docs/eval/aider-results.md`、`tests/e2e/longtext.spec.ts`、`tests/unit/test_craft_plane_discloses_the_deployment_pin.py`、`.scratch/`、`uv.lock` 等, 本批既未 stage 也未修改其中任何一个。
> `ruff check .` 在当前树上 27 错 — 全部落在并发会话的 `.scratch/*.py` 与两个 in-flight 文件 (`craft/executor.py` N818、`test_craft_plane_discloses_the_deployment_pin.py` I001), 本批 4 个 py 文件 `ruff check` 全绿; `mypy .` **218 文件**全绿。
> 落地归属: 本 FIX-20 文中的 (#129) 指 logout 线程的工作编号; 端点/测试/台账修正随 `6826f15` 落地, Web 接线 (`api.ts` 新增 `logout()` + `App.tsx` 退出按钮改异步调用) 与本门第 9 条的已接线态随 `607d62c` 落地 (该提交同时给 `test_threat_vectors` mock 补了 `profile` 参数)。注意 #129 在共享开发里另有一处同名使用 (`05bdc5a` craft 按词干选容器 profile), 与本行无关 — 同号不同事, 在此记一笔以免后人按号找错提交。
| FIX-21 | (#133) **周期回收没有 provider 就绪探针**。`_reclaim_once` (`agent/worker.py:214`) 调 `run_reclaim_pass` 时不传 `provider_ready`: 启用了定时 provider 暂停恢复 (`WORKER_PROVIDER_PARK_MAX_SECONDS>0`) 的部署按龄释放停放作业 — 故障仍在持续就把重试预算花光, 把"可恢复的停放"变成"FAILED, 等人工重投"。`Worker.__init__` 原话"No model-provider health probe exists in this codebase"; 跨进程信号 (§6 第 1 行残留) 不存在 | 默认关 (`provider_park_seconds=0` 即不恢复) 时无影响; 一旦运维按文档启用定时恢复, 每次故障窗口都在拿作业的重试预算为故障买单, 且失败方向不可逆 (FAILED 需人工重投, 而保持停放可自愈) | 新增 `storage/mysql.py::has_fresh_provider_park(within_seconds)`: 过去 N 秒内任一副本有 WAITING_FOR_PROVIDER park 行即 True (DB 时钟 NOW(3), 与 `list_provider_wait_parked` 同口径)。`run_reclaim_pass` 新增 `provider_hold_seconds` (默认 0 即今日行为): 无显式探针且 park 定时器开着时, 由 `_fresh_park_hold_probe` 构成 `provider_ready` — 有新鲜 park 则整轮保持 (RUNNING Lane 照常扫), 探针答不出也保持 (unknown 不是 ready, 与 scope 锁同规则); 显式 `provider_ready` 永远优先。`Worker` 新增 `provider_hold_seconds` 参数 + `WORKER_PROVIDER_HOLD_SECONDS` 环境变量 (默认 "0"), `_reclaim_once` 透传。§6 第 1/2 行改成已落地 (默认关 + 诚实边界: 无新 park 的静默期故障仍按龄释放), OBSERVABILITY 补两项计数 | 新门 `tests/unit/test_provider_hold_probe.py` **11 通过**: 新鲜度查询走 DB 时钟 (SQL 形状 + LIMIT 1 + 参数) + 非法窗口 ValueError 且零 SQL; 有新鲜 park 整轮保持且一行不读; 静默期按龄释放; 默认关零查询; 显式探针永远优先 (False 保持 / True 释放, DB 探针连查都不查); 探针瞎了保持 + error 计数且与 held 分开; 保持只管 provider Lane, RUNNING 照扫; 无 park 定时器不提问; env 默认 0 / 读取 / 构造器优先; `_reclaim_once` 透传双参。缺口门第 1/2 条同步改成新事实 (`_reclaim_once` 传 hold 窗口、`run_reclaim_pass` 签名、`WORKER_PROVIDER_HOLD_SECONDS`、`_fresh_park_hold_probe`、store 方法 + NOW(3)、两行标 ✅ + #133)。**变异 4/4 逐条 RED 且红集合与预测完全一致**: M1 撤掉透传 → 2 红 (透传门 + 缺口门); M2 第 1 行改回 ⏳ → 1 红; M3 新鲜度比较取反 → 1 红 (SQL 形状门); M4 瞎探针改释放 → 1 红; 四次按 sha 校验字节还原, 基线与末轮对照 exit=0。全量门数字见本行下方追记 |

> **FIX-21 全量合并门追记（2026-09-30）**: `pytest tests/unit tests/security tests/fault -q -p no:randomly` → 收集 `3381 items`, 隔离声明 `MySQL test isolation (redirected -> specproof_test): product schema '/test/%' rows 0 -> 0; no test row landed in the product schema`, 汇总 `=========== 1 failed, 3403 passed, 5 skipped in 1442.14s (0:24:02) ==========
日志 `gate_20260930a.log`。
> 唯一红是 `test_subprocess_text_encoding.py::test_the_rest_of_the_repo_cannot_grow_the_debt`：并发会话的 `.scratch/wt130/scripts/bench_*.py` 在工作树里（未跟踪、未提交），欠账门把它们当成新增的未指定编码子进程，报 `108 > 54`。本批 4 个 py 文件零新增 `subprocess.run(text=True)` — `ruff check agent/worker.py storage/mysql.py tests/unit/test_provider_hold_probe.py` 全绿。判据同 #17：慢文件里的单个红，先单跑再定罪。单跑 `test_subprocess_text_encoding.py` 在干净树上为 **4 通过**。
> 口径说明：相对 FIX-17 的 3217，本次 +186；其中本批 +23 (`agent/worker.py` +55, `storage/mysql.py` +30, `tests/unit/test_provider_hold_probe.py` +11, 缺口门 +4 行；`tests/unit/test_drills_gap_claims_hold.py` 同步修正)。跑测平面是共享工作副本，未提交文件含 `craft/executor.py`、`craft/tools.py`、`docs/eval/aider-results.md`、`tests/e2e/longtext.spec.ts`、`tests/unit/test_craft_plane_discloses_the_deployment_pin.py`、`.scratch/`、`uv.lock` 等，本批既未 stage 也未修改其中任何一个。
> `ruff check .` 在当前树上 27 错 — 全部落在并发会话的 `.scratch/*.py` 与两个 in-flight 文件 (`craft/executor.py` N818、`test_craft_plane_discloses_the_deployment_pin.py` I001)，本批 4 个 py 文件 `ruff check` 全绿；`mypy .` **218 文件**全绿。
| FIX-22 | (#138) **"证书撤销"在产品面整体不存在, 而台账把它记到阶段 5 才做**。功能面: `evidence/` 只有签发 (`evidence/certificate.py`), 没有任何"这张证书已被作废"的事实载体 — 事故六动词的 revoke 在证书维度上无端点、无日志、无判定; §3.1 revoke 表、§6 第 4 行与三本架构台账 (`COMPLETION_MAP`/`GUIDE_GAP_AUDIT`/`EVOLUTION_GAP_MAP`) 同源地写着待开发。**诚实面 (2026-10-01 复核)**: 其中"证书本身未签名""无撤销能力""无撤销簿"今天为假 — P5 起证书由 `evidence/signing.py` 用 Ed25519 签名, 撤销能力自本批起也在; 按 FIX-14 原句留在原行挂更正标记, 且 §1 计数 "9 项可执行 / 4 项需开发" 与 §3.2 两个数字同批过期 — 改成由缺口门**按 §3.1 表实数**核对, 以后漂了先红的是门 | 一份事故手册在"证书签错了怎么办"这一问上只能回答"先去写代码": 黄金窗口内没有 revoke 端点 = 已签出的错误证书无法被追认作废; 台账把已存在的能力记成缺口, 读者会去重造 (FIX-14 同病); 更隐蔽的是计数: 19 行 ✅ 的表配着 "9 项可执行" 的结论, 读者无从发现哪句是旧的 | 证书侧: `MergeCertificate.canonical_digest()` 给出 `sha256:` 权威标识符, `CertificateRevocation` 产出 in-toto 样式吊销文档 (`_type=https://specproof.dev/revocation/v0.1`), `evidence/revocation_log.py` 追加只读 JSONL (`evidence/filelock.py` O_EXCL 跨进程锁 + `fsync`, 坏行跳过不吞好行); API 侧: `POST /api/v1/admin/certificates/revoke` (admin/auditor, **签不上名 → 503 `SIGNING_UNAVAILABLE` 且一行不写**), `GET /api/v1/admin/certificates/revocations` (按 target 过滤); 新错误码 `SIGNING_UNAVAILABLE` 进 `ERROR_CODES` + `ERROR_CLASS_BY_CODE` (degrade)。台账: §6 第 4 行 ✅ #138 且**新列第 10 行**如实登记消费方零调用点仍 ⏳, §3.1/§1/§3.2 三个计数改口, 三本架构台账同批更正 | `tests/unit/test_tenant_auth.py` +10 = **53 通过** (落盘语句当场用公钥复验、非 admin/auditor 403、畸形 digest/reason 422 且日志零字节、无签名 key → 503 `SIGNING_UNAVAILABLE` 且日志文件**根本不存在**、按 target 过滤与 0 行回答、legacy 模式 503、digest 稳定性正反向、坏行不吞好行), 缺口门 +3 = **11 通过** (端点↔证据↔第 4 行三方一致、§1/§3.2 计数↔§3.1 表实数、消费方零调用点↔第 10 行 且检测器有非空对照、四本台账的撤销缺口句必须与"更正"同行), `tests/unit/test_openapi_diff.py` 9 通过 (baseline 已 `--update`), 本批文件 `ruff` 全绿; `mypy .` 221 文件, 唯一红是并发会话在途的 `agent/worker.py:422` (notify outbox 车道, 非本批文件)。**变异探针与全量合并门数字见本行下方追记** |
**FIX-22 变异探针逐条记录 (7/7 判红、字节级还原、最终绿):**
M1 §6 第 4 行改回 ⏳ → `test_certificate_revocation_gap_still_matches_the_evidence_tree` 1 红 ✅
M2 端点改名 /certificates/revoke-probe → 9 红 (6 端点测试 + 1 缺口门 + 1 OpenAPI baseline + 1 legacy 503) ✅ — 功能门与合同门同源, 改名同时打红
M3 `is_revoked` 恒 False → 3 红 (`test_revocation_log_appends_newest_first_and_survives_a_torn_line`、`test_the_default_log_path_is_read_from_the_environment`、`test_revoke_endpoint_writes_a_statement_that_verifies`) ✅ — 端点测试补齐正向断言后覆盖到位
M4 撤掉 `except SigningError` 分支 → `test_revoke_endpoint_fails_closed_without_a_signing_key` 1 红 ✅
M5 `revoked_at` 每次序列化重取时钟 → `test_revocation_names_target_reason_and_actor` 1 红 ✅ — 测试补齐跨时钟周期双序列化断言后稳判红
M6 §1 计数改回过期 9/4 → `test_the_s3_headline_counts_are_the_table_counts` 1 红 ✅
M7 §6 第 10 行改标 ✅ → 2 红 (`test_the_revocation_consumer_gap_is_pinned`、`test_certificate_revocation_gap_still_matches_the_evidence_tree`) ✅
全部 7 条探针: 预测集合 == 实测集合, 无 missing/extra, 还原后 SHA-256 逐字节一致。
见完整报告: `mutations_138b.txt` (临时区)。

**FIX-22 全量合并门追记 (在本批待提交树上跑, 含并发会话在途文件):**
日志: `gate_20261001-1703.log`
通过/失败/跳过/耗时: **3448 passed / 9 failed / 5 skipped / 1905.83s (31m45s)**
失败归因:
  - 4 条并发会话在途 `agent/worker.py` notify outbox 车道:
    `test_worker_notify_outbox.py` 3 条 (`test_outbox_lane_enqueues_the_built_payload_and_never_sends`,
    `test_enqueue_failure_falls_back_to_direct_send`,
    `test_unconfigured_receiver_on_the_outbox_lane_still_enqueues`),
    `test_job_state_machine.py::TestNotifyIntentRidesTheTerminalWrite::test_intent_insert_failure_never_rolls_back_the_verdict` 1 条
  - 5 条环境/既存红:
    `test_audit_disposition_labels.py::test_the_page_asks_for_the_parameter_the_handler_accepts`,
    `test_job_reclaimer.py` 2 条 (`test_worker_budget_exhausted_fails_instead_of_parking`,
    `test_worker_non_retryable_provider_error_still_fails`),
    `test_sql_text_static.py::test_no_sql_text_reaches_an_executor_without_proof`,
    `test_no_key_leak.py::test_security_scanner_module_imports` (Windows canary 清理失败)
mypy . 221 文件: 唯一红 `agent/worker.py:422` (notify outbox 重名变量, 并发会话在途, 非本批, 归因不改)
ruff . 全仓 27 错: 全部并发会话在途文件 (`agent/worker.py` 重名变量、`storage/mysql.py`、`demo/.../UserController.java`、5 个 test_*.py、`.scratch/`) — 本批文件全绿
口径: 与 FIX-20/FIX-17 同 — 共享工作树, 外部红仅归因, 不计入本批通过率。

## 6. 待基础设施 / 需开发清单 (如实标注, 均给出精确缺口位置)

| # | 项目 | 缺口位置 | 状态 |
|---|---|---|---|
| 1 | 崩溃作业自动回收器 (RUNNING 超时 → 续跑/重投递) | 已落地: 人工入口 `specproof ops recover` (#68, 只读模式 #74), 自动周期触发在 worker 进程内 (#71, 默认 300s + Redis 作用域锁 + 重试预算上限)。**#133 收口**: 周期路径 `agent/worker.py:214 _reclaim_once` 经 `run_reclaim_pass(provider_hold_seconds=…)` 带上跨进程就绪探针 — 过去 N 秒内任一副本有 park 行 (`storage/mysql.py::has_fresh_provider_park`, DB 时钟) 则整轮保持, 否则按龄释放; 探针答不出也保持; 默认关 (`WORKER_PROVIDER_HOLD_SECONDS=0` 即今日行为), 显式 `provider_ready` 永远优先。诚实边界: 无新 park 的静默期故障仍按龄释放, 不是"provider 健康" | ✅ 已落地 (#133, 门: `tests/unit/test_provider_hold_probe.py` + 缺口门第 1/2 条) |
| 2 | WAITING_FOR_PROVIDER 接线 | 生产者已接 (#64): 可重试的 provider 故障 (429/超时类) 走 CAS 暂停而非 FAILED, 且暂停未落库时不对外宣告; 仍缺的是把该行捞回来的回收器 (见第 1 行) **更正 (2026-09-28, #129)**: "仍缺…回收器"为假 — 回收器 `recover_waiting_for_provider_jobs` 已由 `run_reclaim_pass` 调用 (#68/#71/#74, `agent/worker.py:1128/1370`); 真残留是 worker 周期路径 `agent/worker.py:214 _reclaim_once` 没传 `provider_ready` (跨进程 provider 健康信号), 与第 1 行是同一条 **#133 收口**: 上句"剩信号"已闭合 — `_reclaim_once` 现传 `provider_hold_seconds`, 无显式探针时由 DB park 新鲜度构成 `provider_ready` (见第 1 行); `recover_waiting_for_provider_jobs` 本体未动 (显式探针仍优先) | ✅ 已落地 (#133, 见第 1 行) |
| 3 | OIDC 会话注销/令牌吊销端点 | **更正 (2026-09-28, #129)**: 原声称"api/ 无 logout/revoke"为假 — `DELETE /api/v1/admin/tokens/{token_id}` 早在 `0d85586`; 自 #129 起另有 `POST /auth/logout`: 本地 `sp_*` 吊销并复验, OIDC id_token 回 `revoked:false` + IdP `end_session_endpoint` | ✅ 已落地 (#129, 门: `tests/unit/test_drills_gap_claims_hold.py`) |
| 4 | Merge Certificate 撤销 | **#138 收口 (签发侧)**: `evidence/certificate.py` 新增 `CertificateRevocation` 与 `MergeCertificate.canonical_digest()` (证书的 `sha256:` 权威标识符); `evidence/revocation_log.py` 是追加只读 JSONL 吊销日志 (`evidence/filelock.py` 跨进程锁 + `fsync`, 坏行跳过不吞好行); 吊销文档为 in-toto 样式 `_type=https://specproof.dev/revocation/v0.1` (target/reason/revoked_by/revoked_at), 复用 `evidence/signing.py` 的 Ed25519 签名。`api/routes/admin.py`: `POST /api/v1/admin/certificates/revoke` (admin/auditor, **签不上名就 503 `SIGNING_UNAVAILABLE` 且一行不写**), `GET /api/v1/admin/certificates/revocations` (按 target 过滤)。**诚实边界**: 消费方 (verify/展示路径) 尚不读日志 → 见第 10 行; 门: `tests/unit/test_drills_gap_claims_hold.py::test_certificate_revocation_gap_still_matches_the_evidence_tree` | ✅ 已落地 (#138, 签发侧) |
| 5 | 外部通知接线 (Slack/邮件/webhook) | 已接 (#65): worker 在每一次被接受的终态写入之后调用, 五个 notify 计数可区分"发了/没配置/该 verdict 无模板/对端拒绝/连接器炸"; 剩下的只是部署时是否设环境变量 | ✅ 已接线 |
| 6 | 宿主备份工具 | mysqldump/mongodump/mc/redis-cli 宿主未安装 (实测) — 全部容器内执行或安装后按 §3.1 命令执行 | ⏳ 待基础设施 |
| 7 | Finding 验收反馈的 Web 入口 (#84, Go/No-Go #13 的数据来源) | 已落地: `apps/web/src/pages/FindingDetail.tsx` 的 `FeedbackSection` 消费 `POST`/`GET /api/v1/jobs/{job_id}/feedback` (0012 保证一人一票), 三种 `state` 文案可区分"新票/改票/重复提交", 加载失败与"没人投过"分开渲染, 0 票回答"无法计算"而不是 0%。**仍未闭合**: `specproof_phase0` 里 `uniq_feedback_finding_actor` 还不存在 (对共享产品库做 DDL 需批准), 它由共享栈下一次 `ensure_tables()` 应用 0012 时收敛, 见 §5 FIX-6/FIX-7 | ✅ 已落地 (产品库约束待启动时收敛) |
| 8 | `verdict` 的**状态**通道收口 (词表线程 2026-09-27 拆通道时顺手量出, 属 #109 的下一批) | 三处各写一套且互相矛盾, 权威 `storage/mysql.py::_VALID_TRANSITIONS` 有 10 个状态: (a) `apps/web/src/pages/JobDetail.tsx` 的 `STATUS_HELP` 含 `UNVERIFIED`(状态机无此值)却漏 `PENDING`; (b) `api/routes/jobs.py:185-189` 的 `?status=` 过滤含 `UNVERIFIED`/`INCONCLUSIVE`(库里永远查不到行)却漏 `STALE`(真状态反而被 422 拒); (c) 同一个幽灵词 `UNVERIFIED` 还出现在 `JobDetail.test.tsx` 的 status fixture。该权威已作为 `job_status` 通道登记在 `evidence/verdict_channels.py`(与 `gates` 一样只有 `source` 断言, 尚无消费端门), `storage/agent_jobs.py` 里还有第三套迁移期 `Literal["pending" … "cancelled"]` 待判定归属 | ✅ 已收口 (#110, 见 FIX-18)：集合改为从 `_VALID_TRANSITIONS` 派生 (`ALL_STATUSES`)，三处消费端各由一条双向门钉住；`storage/agent_jobs.py` 那套迁移期 Literal 的归属**仍未判定**，留在本行不抹掉 |
| 9 | Web 退出入口接 `POST /auth/logout` (#129 的消费端) | 退出按钮已存在: `apps/web/src/App.tsx:131` 只做本地清凭证 (`clearApiKey`/`clearBearerToken`) 并跳 `#/login`; `apps/web/src` 全树对 `auth/logout` 零引用 → 服务端 `sp_*` 活到过期, IdP 会话也不结束 | ✅ 已接线：`api.ts` 新增 `logout()` 调用 `POST /auth/logout`，`App.tsx` 退出按钮改用异步调用，服务端吊销 `sp_*` 并返回 IdP `end_session_endpoint`，OIDC 会话完整终止 |
| 10 | 已撤销证书的消费方拦截 (verify/展示路径读吊销日志) | 签发侧已落地 (#138, 见第 4 行), 但全仓除 `evidence/revocation_log.py` / `evidence/certificate.py` / `api/routes/admin.py` 三处之外零调用点: 验证或展示一条证书时不查 `is_revoked`, 已吊销证书目前仍会被当成有效证据对待 | ⏳ 需开发 (门: 缺口门 `test_the_revocation_consumer_gap_is_pinned`) |

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

> **#117 全量合并门追记（2026-09-28）**：数字只认这一次运行自己的输出 —— 在 `f1fef07`（#117 collapse the four hand-written /aut）上跑 `pytest tests/unit tests/security tests/fault -q -p no:randomly -W error`，收集 `collected 3266 items`，隔离声明 `MySQL test isolation: redirected -> specproof_test (product schema specproof_phase0 holds 0 '/test/%' job rows at session start)`，汇总 `=========== 2 failed, 3259 passed, 5 skipped in 1703.64s (0:28:23) ============`，运行自己印出的页脚 `MERGE_EXIT=1`。这一轮之前有一次在 `eeaba27` 上起跑的同型运行随它的会话一起死了：日志停在 31% 且没有页脚，所以它不构成任何证据、这里也不引用它的任何数字。
> 口径说明：这些数字属于 `f1fef07` 那棵树，不属于更早或更晚的 commit；跑测平面是共享工作副本，运行前逐条核过「相对 HEAD 有未提交改动的 tracked 文件」——每一条都要由 tests/unit|security|fault 三道的扫描证明没有测试按文件名读它，才允许留在平面上（本轮排除项：`docs/eval/aider-results.md`）；#72 的欠账由这一段闭合。

> **8a7d209 全量合并门追记（2026-09-28）**：数字只认这一次运行自己的输出 —— 在 `8a7d209`（tests: close the metrics test server's listening）上跑 `pytest tests/unit tests/security tests/fault -q -p no:randomly -W error`，收集 `collected 3266 items`，隔离声明 `MySQL test isolation (redirected -> specproof_test): product schema '/test/%' rows 0 -> 0; no test row landed in the product schema`，汇总 `================ 3261 passed, 5 skipped in 1535.42s (0:25:35) =================`，运行自己印出的页脚 `MERGE_EXIT=0`。
> 口径说明：这些数字属于 `8a7d209` 那棵树，不属于更早或更晚的 commit；日志文件是 `w112/merge_8a7d209.log`。

> **121-and-115b 全量合并门追记（2026-09-28）**：数字只认这一次运行自己的输出 —— 在 `9b3fa92`（#115b the reviewer box must name the identity th）上跑 `pytest tests/unit tests/security tests/fault -q -p no:randomly -W error`，收集 `collected 3266 items`，隔离声明 `MySQL test isolation (redirected -> specproof_test): product schema '/test/%' rows 0 -> 0; no test row landed in the product schema`，汇总 `================ 3261 passed, 5 skipped in 1587.78s (0:26:27) =================`，运行自己印出的页脚 `MERGE_EXIT=0`。
> 口径说明：这些数字属于 `9b3fa92` 那棵树，不属于更早或更晚的 commit；日志文件是 `w112/merge_9b3fa92.log`。

> **118 全量合并门追记（2026-09-28）**：数字只认这一次运行自己的输出 —— 在 `84e02e8`（#118 an unknown feedback verdict must not be dra）上跑 `pytest tests/unit tests/security tests/fault -q -p no:randomly -W error`，收集 `collected 3271 items`，隔离声明 `MySQL test isolation (redirected -> specproof_test): product schema '/test/%' rows 0 -> 0; no test row landed in the product schema`，汇总 `================ 3266 passed, 5 skipped in 1293.43s (0:21:33) =================`，运行自己印出的页脚 `MERGE_EXIT=0`。
> 口径说明：这些数字属于 `84e02e8` 那棵树，不属于更早或更晚的 commit；日志文件是 `w112/merge_84e02e8.log`。

> **122 全量合并门追记（2026-09-28）**：数字只认这一次运行自己的输出 —— 在 `bc9b118`（plan: fill 实施记录 with this session's landed units）上跑 `pytest tests/unit tests/security tests/fault -q -p no:randomly -W error`，收集 `collected 3279 items`，隔离声明 `MySQL test isolation (redirected -> specproof_test): product schema '/test/%' rows 0 -> 0; no test row landed in the product schema`，汇总 `================ 3274 passed, 5 skipped in 1247.62s (0:20:47) =================`，运行自己印出的页脚 `MERGE_EXIT=0`。
> 口径说明：这些数字属于 `bc9b118` 那棵树，不属于更早或更晚的 commit；日志文件是 `w112/merge_bc9b118.log`。
