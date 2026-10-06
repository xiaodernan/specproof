# SpecProof 可观测栈 (P6) — 运维手册

对应 PRODUCTION_SPEC §8.10 (OpenTelemetry / Prometheus / Grafana)、§14 (SLO 与生产质量)、
§17 (单机生产部署 Observability Profile)。本栈自托管、零外部 SaaS。

## 1. 组成与数据流

| 服务 | 镜像 | 端口 | 职责 |
|---|---|---|---|
| otel-collector | otel/opentelemetry-collector-contrib:0.123.0 | 4317 (OTLP gRPC) / 4318 (OTLP HTTP) / 8889 (prom exporter) | 接收 api/worker 的 OTLP 数据; 指标经内嵌 prometheus exporter 暴露, Trace 走 debug exporter (无外部后端) |
| prometheus | prom/prometheus:v3.3.1 | 9090 | 15s 抓取: api:8000/metrics、worker:9100/metrics、outbox-relay:9101/metrics、otel-collector:8889、自身; 规则 alerts-slo.yml |
| grafana | grafana/grafana:11.6.1 | 3000 | provisioning 自动接 Prometheus 数据源 + SLO 看板 (uid: specproof-slo) |

数据流: api / worker / outbox-relay (进程内 registry, observability/metrics.py)
→ 各进程 /metrics (api 用 FastAPI 端点; worker/relay 用 observability/metrics_http.py 的 stdlib 端点)
→ Prometheus 抓取 → Grafana 看板 + SLO 告警。

worker/relay 的 /metrics 绑定地址 (observability/metrics_http.py): 环境变量
METRICS_BIND_HOST 可覆盖; 默认容器内 0.0.0.0 (Prometheus 同 compose 网络跨容器抓取,
端口不发布到宿主机)、本机运行 127.0.0.1。

Trace 链路 (§8.10: Webhook → Outbox → RabbitMQ → Worker → LLM → Tools → GitHub):
代码插桩已就绪 (observability/tracing.py, OTLP HTTP exporter)。api 默认端点
http://localhost:4318/v1/traces 在容器内指向自身, 生产组合中需把应用栈 compose 的
OTEL_EXPORTER_OTLP_ENDPOINT 设为 http://otel-collector:4318 — 该项属应用栈
compose 改动, 本可观测栈已就绪 (见 §6 待接线清单)。

## 2. 启动

```powershell
# 仅观测栈 (与已运行的 phase0 基础设施栈并存, 共用 specproof-phase0 网络):
docker compose -f compose.phase0.yml -f compose.observability.yml up -d otel-collector prometheus grafana

# 生产三文件组合 (api + worker + 观测栈同项目同网络, api:8000/worker:9100 服务名直达):
docker compose -f compose.phase0.yml -f compose.production.yml -f compose.observability.yml up -d
```

镜像站说明: 网络无法直连 Docker Hub 的主机, 先经镜像站拉取并 retag 为标准 tag
(compose 文件内保持标准 tag, 本地已有同名镜像时 up 不再联网拉取):

```powershell
docker pull docker.m.daocloud.io/prom/prometheus:v3.3.1
docker tag  docker.m.daocloud.io/prom/prometheus:v3.3.1 prom/prometheus:v3.3.1
docker pull docker.m.daocloud.io/grafana/grafana:11.6.1
docker tag  docker.m.daocloud.io/grafana/grafana:11.6.1 grafana/grafana:11.6.1
docker pull docker.m.daocloud.io/otel/opentelemetry-collector-contrib:0.123.0
docker tag  docker.m.daocloud.io/otel/opentelemetry-collector-contrib:0.123.0 otel/opentelemetry-collector-contrib:0.123.0
```

端口冲突: 4317/4318/8889/9090/3000 均可经环境变量覆盖
(OTEL_OTLP_GRPC_PORT / OTEL_OTLP_HTTP_PORT / OTEL_PROM_EXPORTER_PORT /
PROMETHEUS_PORT / GRAFANA_PORT)。本次实测主机上这些端口全部空闲, 未发生冲突,
使用默认端口 (实测记录见 §7)。

## 3. 访问与凭据

- Grafana: http://localhost:3000 — 匿名只读 (Viewer) 已开启; 管理登录
  admin / specproof_admin (由 GF_SECURITY_ADMIN_PASSWORD, 即环境变量
  GRAFANA_ADMIN_PASSWORD 默认 specproof_admin 提供)。
  **生产必须更换该口令** (并在三文件组合部署时显式设置 GRAFANA_ADMIN_PASSWORD)。
- Prometheus: http://localhost:9090 (无认证 — 单机部署, 生产加反向代理/TLS 保护)。
- 看板: "SpecProof SLO" (provisioning 自动加载, 无需导入)。

## 4. 验证清单 (全部实测通过, 输出见 §7)

1. Prometheus: GET http://localhost:9090/-/healthy → 200 "Prometheus Server is Healthy."
2. Grafana: GET http://localhost:3000/api/health → 200 含 "database":"ok"
3. Grafana 数据源: GET http://localhost:3000/api/datasources (Basic admin) → 列表含
   Prometheus (url http://prometheus:9090)。
4. Prometheus 目标: GET http://localhost:9090/api/v1/targets — api/worker/outbox-relay
   未起时 state=down 属正常 (应用栈 up 后自动转 up); phase0 栈未起时 rabbitmq (15692,
   /metrics/per-object) 同样 down 属正常 (#165 起); otel-collector/prometheus 应 up。
5. 告警: http://localhost:9090/alerts 可见 13 条 specproof-slo 规则; 无 Alertmanager
   部署 (§17 profile 未含), 告警在 Prometheus UI 观察, 生产接 Alertmanager 后走通知。

## 5. SLO 告警 (alerts-slo.yml)

阈值集中在规则文件头部 THRESHOLDS 表 (Prometheus 规则文件不支持模板变量, 单一修改点),
逐条注释 PRODUCTION_SPEC §14 出处:

| 告警 | 表达式要点 | for | 阈值变量 | §14 出处 |
|---|---|---|---|---|
| SpecproofApiDown | up{job="api"} == 0 | 1m | — | 可用性 99.5% |
| SpecproofWorkerDown | up{job="worker"} == 0 | 5m | — | Job 不丢失 (消费端) |
| SpecproofOutboxRelayDown | up{job="outbox-relay"} == 0 | 5m | — | Job 不丢失 (投递端) |
| SpecproofOutboxBacklogHigh | specproof_outbox_pending > 50 | 5m | OUTBOX_PENDING_THRESHOLD=50 | Job 不丢失: Outbox + MQ + 幂等 |
| SpecproofApiHigh5xxRate | 5xx 率 > 0.05 | 5m | API_5XX_RATE_THRESHOLD=0.05 | CP 月可用性 99.5% |
| SpecproofWorkerFailureRateHigh | 失败/完成 > 0.30 | 15m | WORKER_FAIL_RATE_THRESHOLD=0.30 | 质量目标 (Precision/Replay 前置健康) |
| SpecproofJobDurationP95FastHigh | FAST job 时长 p95 > 480s | 30m | JOB_P95_FAST_SECONDS=480 | FAST 小 PR p95 <= 8 分钟 |
| SpecproofJobDurationP95DeepHigh | DEEP job 时长 p95 > 1500s | 30m | JOB_P95_DEEP_SECONDS=1500 | DEEP 小 PR p95 <= 25 分钟 (队列仅收 FAST, DEEP armed) |
| SpecproofWebhookDurationP95High | webhook 响应 p95 > 1s | 5m | WEBHOOK_P95_SECONDS=1 | §14 GitHub Webhook 响应 p95 <= 1 秒 (#162 接线, 亚秒桶梯度) |
| SpecproofWorkerReclaimTickStale | time() - 上一轮完整回收扫描时间戳 > 900s (3×默认 tick 300s) | 5m | RECLAIM_TICK_STALE_SECONDS=900 | §14 Worker 崩溃后可恢复 (#163 接线; gauge 是舰队级——任一副本 tick 跑完即刷新, 本告警=没有任何 sweeper 活着; worker 刚启动 gauge 未上报时无序列不触发, 由 up 告警补位) |
| SpecproofDashboardProgressLagHigh | 进度事件写入→SSE 发出驻留 p95 > 2s | 5m | DASHBOARD_PROGRESS_P95_SECONDS=2 | §14 Dashboard 进度延迟 <= 2 秒 (#164 接线; 只测 live 投递, SSE 轮询间隔 0.5s 是下限; 发出→浏览器的网络/前端段无服务端观测点) |
| SpecproofVerifyQueueBacklogHigh | broker ready 深度合计 > 50 | 10m | VERIFY_QUEUE_BACKLOG_THRESHOLD=50 | §14 Job 不丢失 — MQ 侧 (#165 接线; rabbitmq per-object 抓取; 消费端停摆时 broker 深度是唯一还在涨的信号, 与 Outbox 侧积压互不替代) |
| SpecproofVerifyDlqNonEmpty | 任意 *.dlq 死信 > 0 (阈值内联) | 5m | VERIFY_DLQ_THRESHOLD=0 | §14 Job 不丢失 — 死信 (#165 接线; 队列名按 storage/rabbitmq.py 的 dlq_suffix='.dlq' 规则正则匹配, 覆盖全部车道; 死信不会自己消失) |

## 6. SLO 接线状态 (§14 各指标, 诚实标注)

| §14 指标 | 测量方式 | 状态 |
|---|---|---|
| Control Plane 月可用性 99.5% | up{job="api"} + 5xx 率 + down 告警 | ✅ 已接线 (看板 + 告警) |
| Job 不丢失 (Outbox/MQ/幂等) | specproof_outbox_pending 积压 + relay down 告警 | 🟡 指标与告警已接线; relay 服务已进入 compose.production.yml (#161 核实), 起应用栈后本面板即有数据。#165 起 MQ 侧也已接线: broker ready 深度合计告警 (消费端停摆) + *.dlq 非空告警 (死信待人工) + 看板面板 19/20 (rabbitmq per-object 抓取) — 两侧互不替代 |
| Worker 崩溃后可恢复 | SpecproofWorkerReclaimTickStale (tick 停摆) + specproof_worker_reclaim_recovery_lag_seconds (死亡→收回等待, 梯度 30..1200s 按 tick 周期定) + specproof_worker_reclaim_pass_seconds (单轮扫描耗时) 直方图 | ✅ 已接线 (#163: 恢复的两个可测时钟; 收回重投递后的排队等待属 broker 域无上报点, 崩溃作业的 checkpoint 续跑无独立边界不可测) |
| FAST p50<=3min / p95<=8min | specproof_jobs_duration_seconds_fast 直方图 (p50/p95 面板 + p95 告警) | ✅ 已接线 (#161 起按 depth 拆名, FAST 用自己的 480s 阈值) |
| DEEP p50<=10min / p95<=25min | specproof_jobs_duration_seconds_deep 直方图 | 🟡 拆名与 1500s 告警已 armed (#161); 队列入口当前仅收 FAST (POST /jobs 钉 ^FAST$、MCP 同、webhook 硬编码), DEEP 走 CLI 本地执行不入队, 入队前该序列无数据 |
| Webhook 响应 p95<=1s | specproof_webhook_github_handling_seconds 直方图 (api/server.py 中间件按路径测量, 含 4xx/5xx; 亚秒桶梯度 0.05..2.5s) | ✅ 已接线 (#162: 面板 + p95>1s 告警; 默认梯度首格 60s 对 1s 分位数无分辨率, 故用亚秒梯度) |
| Dashboard 进度延迟<=2s | specproof_dashboard_progress_delivery_lag_seconds 直方图 (api/routes/jobs.py SSE 循环对 live 事件测写入→发出驻留; p50/p95 面板 + p95>2s 告警) | ✅ 已接线 (#164: 服务端可测段; SSE 发出→浏览器渲染属网络/前端域无观测点, 诚实边界记录于此) |
| BLOCKER/MAJOR Precision>=90% | specproof_findings_court_*_total 判定族 (Review Court 节点边界) + eval 评测集 ground truth 对账 (evidence/acceptance.py severity_reconciliation: Severity agreement=matched 正例判级一致率, Severe precision=severe call 认可率——漂移到 MINOR 仍在分母, FP 负例入分母; 经 eval --cases 进 CLI/HTML/sidecar) | ✅ 已接线 (#180 线上判定聚合 + #188 离线 ground truth 对账, §14 的 90% 阈值在评测门上仍未 pin——acceptance.default() 同款先例, 由维护者从全量跑数 pin) |
| Capsule Replay>=95% | specproof_capsule_replay_runs_total / specproof_capsule_replay_verdict_<word>_total 四词族 / exec_errors、timeouts (evidence/capsule_replay.py: --run 显式 opt-in, run.sh 在沙箱内执行, verdict 词表 = create_capsule 模板) | ✅ 已接线 (#183: 成功率 = confirmed/runs, <95% 告警 SpecproofCapsuleReplayRateLow; git/依赖离线不可解是真实失败计 exec_errors, 非环境借口) |
| 无证据严重评论=0 | specproof_severe_comments_without_evidence_total 拒发计数 (integrations/inline_comments.py build_review_comments 证据门: BLOCKER/MAJOR 无 evidence_type 在锚定前拒发) | ✅ 已接线 (#182: SLO=计数恒 0, >0 即 critical 告警 SpecproofNoEvidenceSevereComment) |
| PR 归因准确率>=90% | specproof_findings_attribution_compared/kept/rejected_total + findings_attribution_signal_<word>_total 词族 (review_court 节点边界: 双侧同败的归因判定分布——kept=Head 行为差异保留归因, rejected=既有缺陷拒归因, 信号词族携带 WHY) | 🟡 归因判定分布已接线 (#184: kept/compared 可算, 拒归因保护可见); 真准确率需 ground truth 且评测集无 base-已含缺陷探针 (#188 勘察: 100 case 全是 head 引入, 对账在现评测集上不可测), §14 的 90% 阈值不做告警 |

§8.10 指标清单中未接线的: Redis 命中
（#168 判定诚实不接线——storage/redis.py 的 LLM 缓存零调用点）。
已收口的: 无证据严重评论
（#182 接线, integrations/inline_comments.py 的 build_review_comments 证据门:
BLOCKER/MAJOR 且 evidence_type 缺失/unknown/? 的 finding 在锚定之前拒发并计
severe_comments_without_evidence_total——SLO 即计数恒 0, 非零即 critical
告警 SpecproofNoEvidenceSevereComment; 纯函数模块, 计数进进程内注册表,
不碰网络/env）、Capsule Replay 成功率
（#183 接线, evidence/capsule_replay.py: replay --run 显式 opt-in 把 run.sh 送进沙箱
执行, mode="docker" 钉死——无 Docker 是诚实报错, 绝不本地回退跑不可信 capsule 代码;
capsule_replay_runs_total 计每次到达沙箱的执行, capsule_replay_exec_errors_total 计
error 非空, capsule_replay_timeouts_total 用与 #178/#181 同源的 "timed out after"
公共子串, capsule_replay_verdict_<word>_total 四词族——词表 = create_capsule 模板的
REGRESSION CONFIRMED / UNEXPECTED FIX / AMBIGUOUS / COMPLIANT, 对账门 import
VERDICTS 钉死, stdout 首个命中、解析不出不计族; 成功率 = confirmed/runs 的 rate 比,
<95% 告警 SpecproofCapsuleReplayRateLow。host 上唯一执行物是 git clone——
declared execution surface 契约）、Base/Head 沙箱失败
（#181 接线, experiments/adapters.py 的 JavaMavenAdapter.run 咽喉点——产品树里
唯一的 run_sandboxed 调用点, sandbox/ 本体保持无指标不动其所有权边界:
sandbox_runs_total 计每次到达沙箱的运行, sandbox_failures_total 计 error 非空
（沙箱 runner 自己的 "无法跑完" 契约）, sandbox_timeouts_total 用与 #178 同源的
"timed out after" 公共子串判超时——spawn 错误计入失败不冒充超时）、法庭判定聚合
（#180 接线, agent/nodes/review_court.py 的 run_review_court 节点边界:
findings_court_candidates_total 计进入法庭的候选, findings_court_<outcome>_total
计四类判定——confirmed/needs_confirmation/not_attributed/skipped, 词表 = policy 层
封闭的 COURT_OUTCOMES, 对账门 import 钉死; 确认率 = confirmed/candidates 的 rate 比,
是 §14 BLOCKER/MAJOR Precision>=90% 的线上前置——真精度对账已落地 (#188,
evidence/acceptance.py severity_reconciliation: eval --cases 按 ground truth
对账 Severity agreement/Severe precision 两个口径, 结果进 CLI/HTML/sidecar;
线上 90% 阈值仍不做告警——评测门是离线 CI gate, §14 无对应线上序列)、
PR 归因判定分布
（#184 接线, agent/nodes/review_court.py 的 run_review_court 节点边界, policy 层
保持 pure: audit entry 携带 preexisting_check——双侧同败的归因比较结果,
findings_attribution_compared_total 计比较, findings_attribution_kept_total 计
Head 行为差异保留归因, findings_attribution_rejected_total 计既有缺陷拒归因,
findings_attribution_signal_<word>_total 四词族（词表 = policy 层封闭的
HEAD_ONLY_SIGNALS, 对账门 import 钉死）携带 WHY——exit_code_differs /
failure_signature_differs / head_extra_failure_count / head_db_state_differs;
kept/compared 可算, 拒归因保护可见, 真准确率无告警; #188 勘察: 评测集 100 case
全是 head 引入缺陷 (正例 63 全 BLOCKER/MAJOR, 负例 37), 无 base-已含缺陷探针,
归因准确率的 ground truth 对账在现评测集上不可测, 需构造 preexisting case）、
证书签发与拒绝
（#179 接线, evidence/certificate.py: issue_certificate 的 VERIFIED 出口计
specproof_certificates_issued_total、非 VERIFIED 出口计 specproof_certificates_refused_total
——判定词表 VERIFIED/BLOCKED/FAILED 封闭, refused 即 blocked+failed 之和;
build_rejection_notice 计 specproof_rejection_notices_total——调用者实际写出
拒绝单的计数, 与 refused（判定未过）语义分开; 签发率 = issued / (issued+refused)
的 rate 比, §14 无证书阈值故无告警）、工具执行时长与超时
（#178 接线, craft/executor.py 的 Executor.run 咽喉点: _timed_tool 包住每次
run_sandboxed, 拼接族 specproof_tool_run_seconds_<stem> 词表=ALLOWED_COMMANDS
白名单, 对账门 import 该常量钉死; tool_timeouts_total 计沙箱超时——判据是两类
沙箱超时文案的公共子串 "timed out after", spawn 错误不冒充超时; 梯度 0.5..3600s
顶格对齐工具 API 的 timeout 上限, 超时也落有限桶）、ES 延迟
（#169 接线, storage/elasticsearch.py 的 _timed_es 包住每个 client 往返,
拼接族 es_request_seconds_<op> 词表派生自调用点; 梯度 0.005..30s, 顶格
对齐 client request_timeout=30, 超时请求落有限桶分位数不落 +Inf）、
LLM Token 与费用
（#168 接线, providers/budget.py TokenBudget.record 是 craft 车道唯一
计量咽喉点——与 billing listener 同点; 诚实边界: agent 验证管线各节点
直连 provider.chat 尚未过 budget, 不在本面板; charge units 是部署相对
量纲非货币; 无告警, §14 无 token 阈值, 预算强制由进程内 BudgetExceeded
执行, specproof_llm_budget_exceeded_total 可见）、各阶段耗时（#166 接线
看板面板 21 per-stage p50/p95, #167 起定制梯度 0.25..1800s——亚秒级节点
有分辨率, 顶格高于 DEEP 作业级 p95 目标 1500s, 分位数不落 +Inf 桶）、
Queue Depth 与 DLQ（#165 接线, 见 §5 表末两行）。

已接线指标名（2026-09-25 与代码逐条对账的结果）：本项目**没有静态指标注册表**，名字只在第一次上报时才出现在 /metrics 上，所以这份清单的唯一合法来源是上报点，不是本文件。本节此前写着"全部真实注册"却漏掉了 worker 生命周期整侧与 outbox relay 的 8 个名字，因此改成可复现的对账方法：取 `incr(` / `set_gauge(` / `observe_duration(` 三个上报函数的全仓调用点（`api/auth.py:91` 与 `storage/redis.py:112` 的 `client.incr(...)` 是 Redis 计数命令，不是指标，已排除），再把常量名解析成字面量。生产侧上报模块有二十一个（#168 起 providers 加入，含 render_text 自己的条目；按本条清单重数：每个列出文件计一次、重复条目不计——#190 订正了 #184 为已在册的 review_court.py 加第二条目时的 +1（文件数未变）与 #185–#187 三个未同步的新文件；#192 重数再订正：#190 写 17 时漏计了自身新增的 preflight 条目（当时清单实为 18 个文件），本号加入 agent/nodes/compile_contracts.py 后按同一口径为 19；#193 重数：加入 agent/nodes/prepare_base.py 与 agent/nodes/prepare_head.py 两个文件（双生节点词表共享同一概念，仍按文件各计一次），按同一口径为 21）：

- `observability/metrics.py::render_text` 无条件输出：specproof_up。
- `api/server.py` 中间件：specproof_http_requests_total、specproof_http_requests_failed_total、specproof_http_responses_5xx_total；#162 起按路径计时 specproof_webhook_github_handling_seconds (直方图, 亚秒桶梯度 0.05..2.5s——默认梯度首格 60s, 对 §14 的 1s 分位数无分辨率)。
- `providers/budget.py`（#168 起，craft 车道 LLM 计量）：specproof_llm_calls_total、specproof_llm_tokens_prompt_total、specproof_llm_tokens_completion_total、specproof_llm_tokens_reasoning_total、specproof_llm_prompt_cache_hit_tokens_total、specproof_llm_prompt_cache_miss_tokens_total（六个计数每次 TokenBudget.record 调用按用量累加；hit/miss 是 prompt 的不相交子集分区，不是额外 token）、specproof_llm_charge_units_total（按 cost_weights 加权的消耗单位，部署相对量纲非货币）、specproof_llm_budget_remaining_units（仪表，进程级最后写入，并发 run 相互覆盖——记账看计数器）、specproof_llm_budget_exceeded_total（check/record 超限 raise 次数；在涨说明有 run 死于预算耗尽）。诚实边界：agent 验证管线各节点直连 provider.chat，不经过 budget，其 token 不在这组名字里。
- `agent/worker.py`：specproof_jobs_completed_total、specproof_jobs_processing_seconds (仪表)、specproof_jobs_duration_seconds_<depth> (直方图族, #161 起按 depth 拆名, 见拼接族)、specproof_worker_lease_renews_total、specproof_worker_lease_renew_seconds (直方图)、specproof_worker_cancelled_at_checkpoint_total、specproof_worker_lease_lost_total、specproof_worker_provider_wait_total、specproof_worker_terminal_cas_lost_total、specproof_worker_cancel_checkpoint_unconfirmed_total、specproof_worker_lease_lost_unconfirmed_total（#66 起：停止帧无法对行核实时的静默计数）、specproof_worker_exception_failures_total（异常失败轮次，读法见下）、specproof_worker_reclaim_lease_probe_unknown_total（#68 起：回收轮里 Redis 答不出租约的次数；每一次都意味着本轮**停止**抢回而不是继续猜测，非 0 时先看 Redis，不要读成「有作业卡死」）、specproof_worker_reclaim_retry_budget_exhausted_total（#71 起：回收器把过期 RUNNING 判成 FAILED 的个数，判据是作业自身 `retry_count >= max_retries`；这个数在涨说明有作业每次都把 worker 打挂，**必须人工处理**，它不会再自己回来）；**#71 起（worker 周期回收 tick）**新增四个计数与一个仪表。先说后者，因为它是唯一能回答「扫描还活着吗」的那个：specproof_worker_reclaim_last_ok_timestamp_seconds（仪表：上一轮完整跑完的时间戳，区分「扫了、这轮确实没有卡住的作业」与「tick 早就死了」——前者是健康，后者是所有卡死作业的总开关）；specproof_worker_reclaim_lock_held_total（锁被别的 worker 持有，本轮什么都没做——多副本下这是「只有一个 worker 在扫」的正常证据，不是故障）、specproof_worker_reclaim_lock_unknown_total（Redis 答不出锁状态，本轮直接跳过；非 0 时先查 Redis，**绝不能**读成「没有卡死作业」）、specproof_worker_reclaim_pass_error_total（扫描抛异常、tick 继续活着的次数，持续上涨要查，因为它意味着每轮都没有人在回收）、specproof_worker_reclaim_provider_wait_deferred_total（因为没有 provider 健康探针而**不**自动放行停放作业的次数；这个数在涨是默认行为，不是故障）；#65 起外加对外通知的三个定名计数 specproof_notify_skipped_total、specproof_notify_error_total 与拼接族 specproof_notify_<status>_total（见下一段）。 #133 补两项: `specproof_worker_reclaim_provider_wait_held_total`(新鲜度保持整轮——过去 N 秒内有 park 行) 与 `specproof_worker_reclaim_provider_probe_error_total`(探针答不出也保持, 与 held 分开计数); 上句"因为没有探针"只在 `WORKER_PROVIDER_HOLD_SECONDS=0` 默认时成立, 启用后保持由本两项计数。#163 补两个恢复时钟直方图: `specproof_worker_reclaim_recovery_lag_seconds`(每个被收回作业的死亡→收回等待 = now - updated_at - ttl, updated_at 正是 CAS 自身判过期的心跳戳; 梯度 30..1200s 按 tick 周期 300s 定) 与 `specproof_worker_reclaim_pass_seconds`(_reclaim_once 成功路径的单轮扫描端到端耗时, perf_counter 计时, 梯度 0.05..30s; 抛异常的 pass 不观测——那是 pass_error 计数的故事)。
- `storage/outbox_relay.py`：仪表 specproof_outbox_pending、specproof_outbox_oldest_age_seconds、specproof_outbox_failure_rate、specproof_outbox_retry_count、specproof_outbox_dead_letters、specproof_outbox_last_success_ts；计数 specproof_outbox_published_total、specproof_outbox_publish_failed_total、specproof_outbox_dead_lettered_total（常量定义在该文件 36-44 行）。
- `api/routes/jobs.py`（#164 起）：`_progress_stream` 对 **live** SSE 投递 observe specproof_dashboard_progress_delivery_lag_seconds（进度事件从 xadd_progress 的 `at` 戳写入到端点发出的驻留；梯度 0.05..5s, §14 的 2s 上界在梯度内才有分辨率）。重放（Last-Event-ID 断线补发）刻意不观测——重放的驻留测的是导致重连的断档, 不是看板延迟; `at` 解析失败照发不测。
- `storage/elasticsearch.py`（#169 起）：`_timed_es` 包住每个 ES client 往返, 拼接族 specproof_es_request_seconds_<op>（op ∈ search / index / bulk / delete_by_query / count / ping / indices, 词表派生自 self.client.<op> 调用点, 对账门钉死; indices 合并 exists/create/delete 管理往返）。直方图梯度 0.005..30s——毫秒级 ping 到秒级 bulk(refresh) 全程有分辨率, 顶格对齐 client 的 request_timeout=30, 超时请求也落有限桶（分位数不落 +Inf）。计时含失败请求（finally 语义）: 一次超时的 search 记完时长照常抛错, 延迟序列不因故障缺样本。
- `craft/executor.py`（#178 起）：`Executor.run` 咽喉点的 `_timed_tool` 包住每次 run_sandboxed, 拼接族 specproof_tool_run_seconds_<stem>（stem ∈ ALLOWED_COMMANDS 白名单 mvn/gradle/npm/pytest/python/cargo, 对账门 import 该常量钉死; CRAFT_EXTRA_COMMANDS 运行时扩展的词干同样进族, 面板用通配 selector 覆盖）。直方图梯度 0.5..3600s——亚秒往返到 10 分钟默认超时全程有分辨率, 顶格对齐工具 API 的 timeout 上限 (Param max_value=3600), 超时执行也落有限桶（分位数不落 +Inf）。计时含失败执行（finally 语义）。超时另计 specproof_tool_timeouts_total: 判据是两类沙箱超时文案的公共子串 "timed out after", spawn 错误等其他沙箱失败不冒充超时。
- `evidence/certificate.py`（#179 起）：`issue_certificate` 的 VERIFIED 出口 incr specproof_certificates_issued_total、非 VERIFIED 出口 incr specproof_certificates_refused_total（refused 即 BLOCKED+FAILED 之和, 判定词表封闭）；`build_rejection_notice` incr specproof_rejection_notices_total——实际写出拒绝单的计数, 与「判定未过」语义分开（调用者可拒绝而不写单）。签发率 = issued 与 refused 两条 rate 的比值, §14 无证书阈值故无告警。
- `agent/nodes/review_court.py`（#180 起）：`run_review_court` 节点边界的判定聚合——findings_court_candidates_total（进入法庭的候选数）与 findings_court_<outcome>_total 四词族（confirmed / needs_confirmation / not_attributed / skipped, 词表 = policy 层封闭的 COURT_OUTCOMES, 对账门 import 该常量钉死）。确认率 = confirmed 与 candidates 两条 rate 的比值, 是 §14 BLOCKER/MAJOR Precision 的线上前置; 真精度需评测集 ground truth（bench_replay 离线）, §14 阈值故无告警。
- `agent/nodes/review_court.py`（#184 起）：run_review_court 节点边界的归因判定分布——audit entry 携带 preexisting_check（policy 层 _preexisting_check 的双侧同败比较结果, policy 保持 pure）: findings_attribution_compared_total / findings_attribution_kept_total / findings_attribution_rejected_total 与 findings_attribution_signal_<word>_total 四词族（exit_code_differs / failure_signature_differs / head_extra_failure_count / head_db_state_differs, 词表 = policy 层封闭的 HEAD_ONLY_SIGNALS, 对账门 import 钉死）。kept = Head 行为差异保留归因（att-08 场景）, rejected = 既有缺陷拒归因（假阳性保护）; kept/compared 是 §6 PR 归因准确率的线上前置, 真准确率需 ground truth, 故无告警。
- `agent/nodes/run_differential.py`（#185 起，#185b 订正）：`run_differential_node` 节点边界的执行计数——differential_runs_total（每次调用，含未执行即返回的尝试）、differential_outcomes_skipped_total（三条未执行路径：workspace 未备好 / 无生成测试 / 注入失败）、differential_errors_total（执行出错：Base/Head 结果 error 非空；#185b 起独立计数，outcomes_ambiguous 保持词表声明的 base_fail+head_fail 义，不吸收基础设施错误）、differential_outcomes_<word>_total 五词族（regression / compliant / ambiguous / unexpected_fix / skipped, 词表 = DIFF_OUTCOMES frozenset, 对账门 import 钉死）。skipped 既可能是诚实降级也可能是能力缺口（需结合 errors rate 判断）；outcomes 是 Phase 2「多语言验证能力」的执行面分布，§2 的多语言能力成熟度阈值不冒充，故无告警。
- `experiments/adapters.py`（#181 起）：`JavaMavenAdapter.run` 咽喉点（产品树里唯一的 run_sandboxed 调用点, Base/Head 差分与 self-test 全部过此点）计 sandbox_runs_total / sandbox_failures_total / sandbox_timeouts_total。failure 判据是沙箱 runner 的 error 非空契约; timeout 判据与 #178 同源（"timed out after" 公共子串）, spawn 错误不冒充超时; sandbox/ 本体保持无指标（所有权边界不动）。§14 无沙箱失败率阈值故无告警。
- `integrations/inline_comments.py`（#182 起）：`build_review_comments` 证据门——BLOCKER/MAJOR 且 evidence_type ∈ {"", "unknown", "?"} 的 finding 在锚定之前拒发（continue）并计 specproof_severe_comments_without_evidence_total。拒绝即策略（与锚定失败的静默丢弃同一诚实族）, §6 "无证据严重评论=0" 的 SLO 就是这条计数恒 0, >0 即 critical 告警 SpecproofNoEvidenceSevereComment。纯函数模块: 计数进进程内注册表, 不引入网络/env。
- `evidence/capsule_replay.py`（#183 起）：`run_capsule_replay`——replay --run 显式 opt-in 后 run.sh 在沙箱内执行（mode="docker" 钉死: 无 Docker 是诚实报错, 绝不本地回退跑不可信代码; host 上唯一执行物是 git clone）。计数: capsule_replay_runs_total（每次到达沙箱的执行, 失败也是运行）、capsule_replay_exec_errors_total（沙箱 error 非空契约）、capsule_replay_timeouts_total（"timed out after" 公共子串, 与 #178/#181 同源）、capsule_replay_verdict_<word>_total 四词族（词表 = create_capsule 模板 REGRESSION CONFIRMED / UNEXPECTED FIX / AMBIGUOUS / COMPLIANT, 对账门 import VERDICTS 钉死; stdout 首个命中, 沙箱跑完且 exit 0 才解析, 解析不出不计族——诚实缺席）。成功率 = confirmed 与 runs 两条 rate 的比值, §14 "Capsule Replay>=95%", <95% 告警 SpecproofCapsuleReplayRateLow。
- `agent/nodes/intake.py`（#186 起）：`intake_node` 节点边界的验证计数——intake_runs_total（每次调用）、intake_repo_missing_total（仓库路径不存在）、intake_spec_missing_total（需求文件不存在）、intake_spec_read_total（成功读取）。两个检查彼此独立：缺仓库不会短路需求读取，一次运行可同时记 repo_missing 与 spec_read（两失败计数亦可同记；#186b 行为测试钉住）。任一记录错误会在 preflight 守卫处中止作业，解释为何作业从未到达后续节点（诚实归因，非静默丢弃）。
- `agent/nodes/publish_report.py`（#187 起）：`publish_report_node` 节点边界的执行计数——publish_report_runs_total（每次调用）、publish_report_success_total（成功生成 HTML + lineage 产物）。两者差值即诚实失败——渲染/写盘失败，或 lineage 构建失败（发生在 HTML 落地之后：报告可能没有血缘文档）；元数据管道故障被 best-effort 吞掉、不动两计数（#187b 行为测试钉住）。
- `agent/nodes/preflight.py`（#190 起）：`preflight_node` 节点边界的执行计数——preflight_runs_total（每次调用）与 preflight_outcomes_<word>_total 五词族（clean / blocked / upstream_errors / disabled / probe_error, 词表 = PREFLIGHT_OUTCOMES frozenset, 对账门 import 钉死）。关键读法：result 的 passed=true 覆盖 clean/probe_error/disabled/upstream_errors 四种情形（仅 blocked 为 false）——「探测没跑」（upstream_errors = intake 已记录错误 / disabled = SPECPROOF_PREFLIGHT 逃生门）与「探测坏了」（probe_error = 运行器抛异常, fail-open 仅一条 warning）只有 outcomes 词表能区分; blocked 的 Preflight: 前缀错误由 graph._abort_on_preflight 提前收口作业, 解释为何作业从未到达后续节点（#190 行为测试逐词钉住）。
- `agent/nodes/compile_contracts.py`（#192 起）：`compile_contracts_node` 节点边界的执行计数——compile_contracts_runs_total（每次调用）与 compile_contracts_outcomes_<word>_total 七词族（empty_input / approved_loaded / rules_sufficient / llm_disabled / llm_unavailable / llm_replaced / llm_degraded, 词表 = COMPILE_OUTCOMES frozenset, 对账门 import 钉死）。关键读法：编译报告单看 accepted_count 无法区分这些结局——llm_replaced 与 rules_sufficient 都可能产出可接受契约，llm_unavailable / llm_disabled / llm_degraded 都「保留规则列表继续」（差别只在 LLM 是否被尝试、为何没有产出），empty_input 与 approved_loaded 则是零编译收口（后者经人工批准优先）。只有 outcomes 词表能看见当轮究竟走了哪条路（#192 行为测试逐词钉住）。
- `agent/nodes/prepare_base.py`（#193 起）：`prepare_base_node` 节点边界的执行计数——prepare_base_runs_total（每次调用）与 prepare_base_outcomes_<word>_total 四词族（prepared / safety_failed / checkout_failed / prepare_error, 词表 = PREPARE_OUTCOMES frozenset, 对账门 import 钉死）。关键读法：三种失败都返回「空 workspace + errors 追加一条」的同一形状，返回值本身分不出是谁拒绝的——safety_failed = 共享仓库安检拒绝（作业载荷/仓库状态层；其 warning 披露见 #130）、checkout_failed = 安检放行后 git worktree add 非零退出（git 层）、prepare_error = git 调用本身抛异常（基础设施层）。twin 不变量：与 prepare_head 词表逐词相同，parity 推导块实测断言两者相等（只改一份副本会被门点名）。
- `agent/nodes/prepare_head.py`（#193 起）：prepare_head_runs_total 与同样的四词族——一次作业挂两个 worktree（base/head），分节点计数才知道是哪一半失败；四词含义与 base 条目完全一致（同一共享安检、同一条 git 命令形状，只有 ref 与状态键不同）。注意 base 失败不短路 head（图里两段都是无条件边，head 照常尝试并各自计数），两者任一失败都在 prepare_head 之后的错误守卫（graph._abort_on_errors）收口作业——与 preflight 条目同款「诚实归因」：作业没走到 collect_diff 的原因，去看是哪个节点的哪个词在涨。
- `storage/notify_relay.py`（#16.6-1，`SPECPROOF_NOTIFY_OUTBOX=1` 时的 webhook 投递车道）：仪表 specproof_notify_outbox_pending、specproof_notify_outbox_oldest_age_seconds、specproof_notify_outbox_retry_count、specproof_notify_outbox_dead_letters、specproof_notify_outbox_last_success_ts；计数 specproof_notify_outbox_delivered_total、specproof_notify_outbox_failed_total、specproof_notify_outbox_dead_lettered_total。入车道侧（K 收口后）由 `storage/mysql.py::transition_job_status_with_notify` 在终态写同事务内上报：specproof_notify_outbox_enqueued_total（意图入库成功）与 specproof_notify_outbox_intent_lost_total（意图入库失败——终态照常落库，通知降级为丢，绝不回滚终态）。

另有一类**第三方指标**不在本对账内：`rabbitmq_*`（RabbitMQ 自带插件 rabbitmq_prometheus 的输出，#165 起 prometheus.yml 的 rabbitmq 抓取任务经 /metrics/per-object 供给；队列级深度 rabbitmq_queue_messages / _ready / _unacked 带 vhost/queue label）。对账门的 specproof_* regex 天然扫不到它们——第三方名的真伪只能靠抓取目标 up 与实际查询验证（#165 已实测 15692 存活、per-queue 序列与 rabbitmqctl 对数一致）。

三个**名字由代码拼接**的族不能列举，看板/告警要用正则匹配：`jobs_<verdict>_total`（verdict 取小写，所以旧清单里的 specproof_jobs_verified_total / _blocked_total / _failed_total 只是它的三个实例）、`worker_stage_duration_seconds_<node>`（graph 节点名拼进指标名，每个节点一条直方图，#167 起定制梯度 0.25..1800s）、`jobs_duration_seconds_<depth>`（#161 起 depth 小写拼进名字：specproof_jobs_duration_seconds_fast / _deep / _release，词表封闭见三个入口的校验）与 `notify_<status>_total`（`SendStatus` 的三个成员小写拼进名字：specproof_notify_sent_total / _disabled_total / _failed_total）。

`notify_*` 一族的读法（#65 接线后的实测语义）：一次终态宣告最多产生一个 notify 计数，五个名字互斥且互补——`skipped` 说"这个 verdict 没有模板，所以什么都没发"（CANCELLED/ERROR/STALE 都是真实终态，不是假设），`sent` 说对端 2xx，`failed` 说对端给了不可重试或重试耗尽的答复，`error` 说连接器自己炸了（工厂构造或 send 抛异常，worker 吞掉以保住已落库的终态），`disabled` 说**根本没有人配置通知**。最后一条是这组计数里唯一会被误读成好消息的：`notify_sent_total` 长期为 0 只说明没发出去，而 `notify_disabled_total` 非 0 才说明"看起来已通、其实一条也没通"——接线与未接线的区别全在这两个名字上，所以部署后先看 disabled 是否在涨。

`notify_outbox_*` 一族的读法（#16.6-1 收口，K 批同事务化后）：worker 不再直接发 webhook，而是把**构建完成的**通知（event_type/title/text/blocks，冻结于构建时刻）随终态写**同事务**持久化到 notify_outbox 表（`transition_job_status_with_notify`），由 `storage/notify_relay.py` 的独立循环送达——端点收下后 `delivered` 才落库，失败按指数退避延期并计入 `attempts`，超过预算进死信（等运营处理）；连接器 DISABLED（没人配置接收端）**立即死信**而不是重试进虚无。`notify_outbox_pending` 长期在涨或 `notify_outbox_dead_letters` 非 0 都说明接收端有问题，先看接收端再看 worker。`intent_lost_total` 非 0 说明 notify_outbox 表写入出过问题——终态不受影响，但那一次宣告丢了，按 job_id 回放或补发。flag 关闭时直发车道原样保留，两套车道不该同时启用。

`specproof_worker_terminal_cas_lost_total` 的语义（#63 起，#64 扩展）：终态写入被拒绝的次数。终态判定与它背后的证据已合并为同一条 UPDATE，被拒时既不落库也不发出任何完成宣告，所以这个计数非 0 就是"有 worker 在替一行不属于它的状态说话"的信号；正常情况下它应当一直是 0。#64 把同一条规则推广到**失败**路径，因此这个计数器现在覆盖三种被拒：VERIFIED/BLOCKED 等成功终态 CAS 被拒、FAILED 落库被拒（含 `InvalidStateTransition`，例如行已是 CANCELLED 时不再允许 FAILED）、以及 429 暂停写入 `WAITING_FOR_PROVIDER` 被拒。三者都不再对外宣告（#65 起，三条对外通道都不发：Redis 进度帧、GitHub Check Run、webhook 通知）。注意 `specproof_worker_provider_wait_total` 只在暂停**落库成功**时才 +1 —— 它说"有多少行真的在等 provider"，不是"有多少次判定想让它等"。

`specproof_worker_exception_failures_total` 的语义（#13.6-4 收口）：**抛异常告终的失败轮次**。verdict 族（`jobs_failed_total` 等）的 incr 点位于"图跑完并成功落终态"之后，所以异常轮次从来不进族——按族算失败率时这些轮次从分子和分母里**同时消失**，失败率被系统性低估。本计数只数"异常路径落 FAILED 成功"的轮次（暂停 WAITING_FOR_PROVIDER 的轮次不算失败、CAS 被拒的轮次已由上面的计数覆盖），是**新增**而非改口径：`jobs_failed_total` 的"图跑完、结论 FAILED"语义原样保留，既有告警查询不受影响；看全量失败要两个名字相加，读法写在 worker.py 的 incr 点注释里。

进度流（Redis stream，前端 `worker_stage_duration_seconds_<node>` 的 node 名与此同源）中有三个值**不是 graph 节点**，而是 worker 自己写的生命周期事件，看板/文案不要把它们当成"某个阶段跑完了"：`lease`（租约续约）、`cancel_checkpoint`（取消检查点）、`terminal`（#64 起，失败/暂停的终结帧；此前这里的 node 位置写的是一次性 job id，等于在阶段列表里插入一个 UUID）。#64 后终结帧的 status 只有 `failed` 与 `waiting_for_provider` 两种，不再出现"429 暂停也报 failed"的假陈述。

`lease` 与 `cancel_checkpoint` 两帧的 status 语义（#66 起，取代本节此前"已知未修的不一致"登记）：两帧都**跟随落库的行**，与 `terminal` 帧同一可信级别。worker 自己的写入成功时，帧说写入的状态（cancel_checkpoint → `cancelled`；lease → `failed`）；CAS 被拒时读回行、说行真实的状态——取消路径被拒是常态（API 的取消 CAS 通常已把行写成 CANCELLED，读回确认后帧仍说 `cancelled`，检查点审计照样记录），租约丢失被拒时行可能已被 reclaimer 改回 QUEUED（帧如实说 `queued`：这是重试，不是死亡）或已被用户取消（`cancelled`）。只有行读不回来或读回的状态两者都对不上时，帧**不发**，改记 specproof_worker_cancel_checkpoint_unconfirmed_total / specproof_worker_lease_lost_unconfirmed_total——静默可观测，不猜测。此前两帧无条件写 `failed`，在"用户取消了作业"与"作业被改回队列待重试"两种场景下都是对行的谎报。

这两个集合的双向对账由 `tests/unit/test_progress_event_labels.py` 守住：worker/graph 生产出来的每个 node/status 字面量都必须在 `apps/web/src/ui/stages.ts` / `StatusPill.tsx` 里有中文注释，反之清单里也不得留死条目。

## 7. 实测记录 (2026-08, Windows + Docker Desktop 29.6.2)

- 端口 4317/4318/8889/9090/3000 实测空闲, 未发生冲突, 全部使用默认端口。
- docker compose -f compose.phase0.yml -f compose.production.yml -f compose.observability.yml config
  校验通过 (需 SPECPROOF_API_KEY 环境变量, 测试值仅存在于进程环境)。
- 三项健康检查 + 数据源 + targets 全部按 §4 实测通过; api/worker/outbox-relay
  目标在应用栈未启动时显示 down 属正常, 经网络别名临时起 api 容器实测
  自动转 up (详见 P6 交付报告)。
- 停止: docker compose -f compose.phase0.yml -f compose.observability.yml down
  (清理观测栈; 数据卷保留, down -v 清空 Prometheus TSDB / Grafana 数据)。

## 8. 已知注意事项

- 生产三文件组合与"仅 phase0 已运行"的同主机并存时, 应用栈会因端口
  3306/6379/5672 冲突无法启动 — 先 docker compose -f compose.phase0.yml down
  再整体拉起三文件组合。
- GF_SECURITY_ADMIN_PASSWORD 默认 specproof_admin 仅用于首次体验, 生产必须更换。
- Trace 无持久后端 (debug exporter), 接 Tempo/Jaeger 时在
  infra/otel/otel-collector.yaml 的 traces pipeline 追加 otlphttp 转发即可。
