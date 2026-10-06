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
| BLOCKER/MAJOR Precision>=90% | 无指标 (需按 Finding 判定聚合) | ❌ 未接线 (依赖应用层产出) |
| Capsule Replay>=95% | 无指标 | ❌ 未接线 |
| 无证据严重评论=0 | 无指标 | ❌ 未接线 (由证据门禁保证, 不可观测) |
| PR 归因准确率>=90% | 无指标 | ❌ 未接线 |

§8.10 指标清单中未接线的: Finding Precision、Tool Timeout、
Redis 命中、Base/Head 沙箱失败 (sandbox/ 代码无指标注册,
属 sandbox 子代理职责)、Certificate 签发率。已收口的: ES 延迟
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

已接线指标名（2026-09-25 与代码逐条对账的结果）：本项目**没有静态指标注册表**，名字只在第一次上报时才出现在 /metrics 上，所以这份清单的唯一合法来源是上报点，不是本文件。本节此前写着"全部真实注册"却漏掉了 worker 生命周期整侧与 outbox relay 的 8 个名字，因此改成可复现的对账方法：取 `incr(` / `set_gauge(` / `observe_duration(` 三个上报函数的全仓调用点（`api/auth.py:91` 与 `storage/redis.py:112` 的 `client.incr(...)` 是 Redis 计数命令，不是指标，已排除），再把常量名解析成字面量。生产侧上报模块有五个（#168 起 providers 加入，外加 render_text 自己）：

- `observability/metrics.py::render_text` 无条件输出：specproof_up。
- `api/server.py` 中间件：specproof_http_requests_total、specproof_http_requests_failed_total、specproof_http_responses_5xx_total；#162 起按路径计时 specproof_webhook_github_handling_seconds (直方图, 亚秒桶梯度 0.05..2.5s——默认梯度首格 60s, 对 §14 的 1s 分位数无分辨率)。
- `providers/budget.py`（#168 起，craft 车道 LLM 计量）：specproof_llm_calls_total、specproof_llm_tokens_prompt_total、specproof_llm_tokens_completion_total、specproof_llm_tokens_reasoning_total、specproof_llm_prompt_cache_hit_tokens_total、specproof_llm_prompt_cache_miss_tokens_total（六个计数每次 TokenBudget.record 调用按用量累加；hit/miss 是 prompt 的不相交子集分区，不是额外 token）、specproof_llm_charge_units_total（按 cost_weights 加权的消耗单位，部署相对量纲非货币）、specproof_llm_budget_remaining_units（仪表，进程级最后写入，并发 run 相互覆盖——记账看计数器）、specproof_llm_budget_exceeded_total（check/record 超限 raise 次数；在涨说明有 run 死于预算耗尽）。诚实边界：agent 验证管线各节点直连 provider.chat，不经过 budget，其 token 不在这组名字里。
- `agent/worker.py`：specproof_jobs_completed_total、specproof_jobs_processing_seconds (仪表)、specproof_jobs_duration_seconds_<depth> (直方图族, #161 起按 depth 拆名, 见拼接族)、specproof_worker_lease_renews_total、specproof_worker_lease_renew_seconds (直方图)、specproof_worker_cancelled_at_checkpoint_total、specproof_worker_lease_lost_total、specproof_worker_provider_wait_total、specproof_worker_terminal_cas_lost_total、specproof_worker_cancel_checkpoint_unconfirmed_total、specproof_worker_lease_lost_unconfirmed_total（#66 起：停止帧无法对行核实时的静默计数）、specproof_worker_exception_failures_total（异常失败轮次，读法见下）、specproof_worker_reclaim_lease_probe_unknown_total（#68 起：回收轮里 Redis 答不出租约的次数；每一次都意味着本轮**停止**抢回而不是继续猜测，非 0 时先看 Redis，不要读成「有作业卡死」）、specproof_worker_reclaim_retry_budget_exhausted_total（#71 起：回收器把过期 RUNNING 判成 FAILED 的个数，判据是作业自身 `retry_count >= max_retries`；这个数在涨说明有作业每次都把 worker 打挂，**必须人工处理**，它不会再自己回来）；**#71 起（worker 周期回收 tick）**新增四个计数与一个仪表。先说后者，因为它是唯一能回答「扫描还活着吗」的那个：specproof_worker_reclaim_last_ok_timestamp_seconds（仪表：上一轮完整跑完的时间戳，区分「扫了、这轮确实没有卡住的作业」与「tick 早就死了」——前者是健康，后者是所有卡死作业的总开关）；specproof_worker_reclaim_lock_held_total（锁被别的 worker 持有，本轮什么都没做——多副本下这是「只有一个 worker 在扫」的正常证据，不是故障）、specproof_worker_reclaim_lock_unknown_total（Redis 答不出锁状态，本轮直接跳过；非 0 时先查 Redis，**绝不能**读成「没有卡死作业」）、specproof_worker_reclaim_pass_error_total（扫描抛异常、tick 继续活着的次数，持续上涨要查，因为它意味着每轮都没有人在回收）、specproof_worker_reclaim_provider_wait_deferred_total（因为没有 provider 健康探针而**不**自动放行停放作业的次数；这个数在涨是默认行为，不是故障）；#65 起外加对外通知的三个定名计数 specproof_notify_skipped_total、specproof_notify_error_total 与拼接族 specproof_notify_<status>_total（见下一段）。 #133 补两项: `specproof_worker_reclaim_provider_wait_held_total`(新鲜度保持整轮——过去 N 秒内有 park 行) 与 `specproof_worker_reclaim_provider_probe_error_total`(探针答不出也保持, 与 held 分开计数); 上句"因为没有探针"只在 `WORKER_PROVIDER_HOLD_SECONDS=0` 默认时成立, 启用后保持由本两项计数。#163 补两个恢复时钟直方图: `specproof_worker_reclaim_recovery_lag_seconds`(每个被收回作业的死亡→收回等待 = now - updated_at - ttl, updated_at 正是 CAS 自身判过期的心跳戳; 梯度 30..1200s 按 tick 周期 300s 定) 与 `specproof_worker_reclaim_pass_seconds`(_reclaim_once 成功路径的单轮扫描端到端耗时, perf_counter 计时, 梯度 0.05..30s; 抛异常的 pass 不观测——那是 pass_error 计数的故事)。
- `storage/outbox_relay.py`：仪表 specproof_outbox_pending、specproof_outbox_oldest_age_seconds、specproof_outbox_failure_rate、specproof_outbox_retry_count、specproof_outbox_dead_letters、specproof_outbox_last_success_ts；计数 specproof_outbox_published_total、specproof_outbox_publish_failed_total、specproof_outbox_dead_lettered_total（常量定义在该文件 36-44 行）。
- `api/routes/jobs.py`（#164 起）：`_progress_stream` 对 **live** SSE 投递 observe specproof_dashboard_progress_delivery_lag_seconds（进度事件从 xadd_progress 的 `at` 戳写入到端点发出的驻留；梯度 0.05..5s, §14 的 2s 上界在梯度内才有分辨率）。重放（Last-Event-ID 断线补发）刻意不观测——重放的驻留测的是导致重连的断档, 不是看板延迟; `at` 解析失败照发不测。
- `storage/elasticsearch.py`（#169 起）：`_timed_es` 包住每个 ES client 往返, 拼接族 specproof_es_request_seconds_<op>（op ∈ search / index / bulk / delete_by_query / count / ping / indices, 词表派生自 self.client.<op> 调用点, 对账门钉死; indices 合并 exists/create/delete 管理往返）。直方图梯度 0.005..30s——毫秒级 ping 到秒级 bulk(refresh) 全程有分辨率, 顶格对齐 client 的 request_timeout=30, 超时请求也落有限桶（分位数不落 +Inf）。计时含失败请求（finally 语义）: 一次超时的 search 记完时长照常抛错, 延迟序列不因故障缺样本。
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
