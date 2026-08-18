# Go/No-Go 15 门槛测量 (PRODUCTION_SPEC §20)

总览: **PASS 6/15 · PARTIAL 3/15 · PENDING 6/15** (2026-08, 基于现有仓库实测证据; 未实测的门槛一律标 PENDING, 不编造数字)

状态约定: PASS = 有真实测量/测试证据且达标; PARTIAL = 有部分或间接证据, 未达可宣称达标的程度; PENDING = 无测量, 需按"缺口与下一步"补齐后才能判定。

| # | 门槛 (≥ 指标) | 状态 | 证据引用 | 测量命令 | 缺口与下一步 |
|---|---|---|---|---|---|
| 1 | 已发布 BLOCKER/MAJOR Precision ≥ 90% | PASS | docs/eval/eval-report.results.json (precision=100.0, false_positives=0/20); docs/eval/eval-report.html; docs/eval/baseline-report.md (20 案例同口径) | python -m cli.specproof.main eval --cases golden-cases --repo . --no-llm | 证据域 = golden-cases 20 例评测集; 生产流量口径的 Precision 需等 #12 试点后重测 |
| 2 | 语义回归 Recall ≥ 80% | PASS | docs/eval/eval-report.results.json (recall=100.0, detected=12/12); docs/eval/baseline-report.md | 同上 (eval 全量, 2026-08-18 第十轮审计后实测) | 同上, 生产口径需试点 |
| 3 | PR 归因准确率 ≥ 90% | PARTIAL | agent/nodes/review_court.py (六条件之 3_attribution_to_head, attributed_contract 归因); agent/nodes/run_differential.py (REGRESSION 归因 + DB 状态取证); docs/eval/eval-report.results.json (负样本 0 误报, 仅间接证据) | python -m pytest tests/unit -q --tb=short | 无独立归因准确率指标: 需构造"Base 与 Head 各自都有失败"的用例集, 量化错归因/漏归因比例, 目标 ≥ 90% |
| 4 | Capsule Replay 成功率 ≥ 95% | PENDING | capsules/capsule-*.zip + 每胶囊 run.sh/run.ps1 (真实回放脚本); cli/specproof/commands/replay.py; tests/integration/test_phase_acceptance.py::test_capsule_replay_roundtrip (当前无 zip 时显式 skip, 不伪造通过) | python -m cli.specproof.main replay <capsule.zip> 逐胶囊执行 | 需要: 对全部现有 capsule zip 批量回放并统计成功率的脚本/测试 (尚不存在); 现状仅验证了格式与脚本存在 |
| 5 | 无证据的严重评论 = 0 | PARTIAL | agent/nodes/review_court.py (BLOCKER 六条件 + _has_real_execution_evidence 要求真实 base/head exit code); agent/nodes/run_static_checks.py (_STATIC_CONFIDENCE_CEILING=0.85, 静态封顶 MAJOR); capsules/capsule-COURT-AUTH-01/finding.json (blocker_check 6/6 逐条记录); docs/eval/eval-report.results.json (0 误报) | python -m pytest tests/unit tests/security -q --tb=short | 机制在代码中强制, 但缺少专门测试断言"任何无执行证据的 Finding 都不可能以 BLOCKER 发布"; 需补一条 court 单元测试锁定该不变式 |
| 6 | FAST 小 PR p95 ≤ 8 分钟 | PENDING | — (grep 全库无 timing/p95 基准脚本) | 无现成命令 | 需要: FAST 路径计时基准脚本 (记录 intake→publish_report 墙钟时间, 首次镜像拉取/依赖下载计入并标注), N≥20 个小 PR 测 p95; 当前无任何计时数据 |
| 7 | 重复 Webhook 不产生重复 Job | PASS | tests/unit/test_webhook_endpoint.py::test_duplicate_delivery_idempotent (same-delivery 二次投递 → duplicate_delivery, 仅 1 个 Job); tests/unit/test_github_webhook.py (签名 fail-closed) | python -m pytest tests/unit/test_webhook_endpoint.py tests/unit/test_github_webhook.py -q | 无 (单元层已证; 生产层 X-GitHub-Delivery 去重随 #12 试点复核) |
| 8 | MQ 重投不产生重复 Finding | PASS | tests/unit/test_rabbitmq_reliability.py (make_idempotency_check / QueuePolicy DLQ 退避); tests/unit/test_concurrency_ha.py (N 次投递恰好处理一次); storage/rabbitmq.py (_get_death_count 重投识别); tests/integration/test_outbox_crash_recovery.py (需真实 MySQL+RabbitMQ, 不可用则 skip) | python -m pytest tests/unit/test_rabbitmq_reliability.py tests/unit/test_concurrency_ha.py -q | 集成层证据以 skip 形式存在: 需在真实 broker 上跑一遍 test_outbox_crash_recovery 并记录结果 |
| 9 | Worker Kill 后任务可恢复 | PASS | tests/unit/test_checkpoint_recovery.py (checkpoint 模型/父链/恢复逻辑); tests/integration/test_worker_crash_mid_graph.py (节点 7 崩溃 → 节点 6 checkpoint 恢复, DB 依赖部分 skip); tests/integration/test_outbox_crash_recovery.py (Outbox 崩溃恢复, 需 MySQL) | python -m pytest tests/unit/test_checkpoint_recovery.py tests/integration/test_worker_crash_mid_graph.py -q | 真实 kill -9 进程级演练未做: 试点环境补一次真进程击杀恢复演练 |
| 10 | Key/Token 泄露测试全部通过 | PASS | tests/security/test_no_key_leak.py (canary 自检 + sk- 模式全库扫描); tests/security/test_no_secrets.py; agent/security_scanner.py; providers/redaction.py | python -m pytest tests/security -q | 无 |
| 11 | 第三方模型网关故障时 Job 不丢失 | PENDING | agent/nodes/compile_contracts.py / generate_counterexamples.py / review_court.py (LLM 不可用时 rule-based 回退); storage/mysql.py (Transactional Outbox + 状态机); tests/fault/test_all_scenarios.py (Scenario 5 仅逻辑级: 500/429/超时/空响应) | python -m pytest tests/fault -q (逻辑级) | 无端到端故障注入测试: 需要"Job 运行中拔掉网关 (断网/401) → Job 仍到达终态且不丢"的集成测试; 现状只有逻辑级断言, 不能宣称 PASS |
| 12 | 3 个真实仓库连续试点 2 周 | PENDING | — (无试点记录) | 无 | 需要: 选定 3 个真实 Spring Boot 仓库 + GitHub App 安装 + 连续 2 周运行, 记录 Job/Webhook/Check Run 日志; 完全未开始 |
| 13 | 用户对高等级 Finding 接受率 ≥ 70% | PENDING | — (无用户数据) | 无 | 需要: 试点仓库用户对每个 BLOCKER/MAJOR 做 accept/reject 反馈并统计; 依赖 #12 先启动 |
| 14 | 语义回归发现率比"直接让 DeepSeek 看 Diff"基线高 ≥ 25pp | PARTIAL | docs/eval/baseline-report.md (deterministic diff-reader 基线 Recall 58.3% vs SpecProof 100.0%, +41.7pp PASS); docs/eval/baseline-report.json; cli/specproof/commands/baseline.py (--mode diff-reader|llm, LLM 基线已实现); tests/unit/test_baseline.py (31 例全绿) | python -m cli.specproof.main baseline --cases golden-cases --repo . --mode diff-reader; LLM 基线: 同命令 --mode llm (需 LLM_API_KEY) | 规格要求的 LLM 基线未实测 (本环境无 Key): 配置 LLM_API_KEY 后运行 --mode llm 重测, 覆盖写 LLM 基线报告后按 +25pp 判定; 无 Key 时命令打印 "LLM baseline unavailable" 并退出码 2, 绝不编造 |
| 15 | 平均验证成本在用户配置预算内 | PENDING | storage/redis.py (LLM token budget consume/超支拒绝, 逻辑级); tests/unit/test_redis_stream.py (budget 逻辑测试) | python -m pytest tests/unit/test_redis_stream.py -q (逻辑级) | 无端到端成本测量: 需按 Job 统计 token 用量 + 沙箱/DB 资源成本, 与用户预算参数对比; 现仅预算机制存在, 未经真实账单验证 |

## 结论

- 6 条 PASS 全部来自可复现的仓库证据 (评测侧车、单元/安全测试), 无编造数字。
- 3 条 PARTIAL (#3/#5/#14) 有机制或间接证据, 但缺独立量化指标。
- 6 条 PENDING 中: #4/#6/#11 缺测量工具或故障注入测试 (可在仓库内补); #12/#13/#15 依赖真实试点仓库、真实用户与真实账单, 无法在仓库内完成。
- 任一门槛未达 PASS 前, 不宣称 PRODUCTION_SPEC §3 的商业优势评分成立 (§20: "任何一项失败: 不宣称达到商业优势 9.0")。
