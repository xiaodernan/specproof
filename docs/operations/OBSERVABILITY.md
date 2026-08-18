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
   未起时 state=down 属正常 (应用栈 up 后自动转 up); otel-collector/prometheus 应 up。
5. 告警: http://localhost:9090/alerts 可见 7 条 specproof-slo 规则; 无 Alertmanager
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
| SpecproofJobDurationP95High | job 时长 p95 > 480s | 30m | JOB_P95_FAST_SECONDS=480 | FAST 小 PR p95 <= 8 分钟 |

## 6. SLO 接线状态 (§14 各指标, 诚实标注)

| §14 指标 | 测量方式 | 状态 |
|---|---|---|
| Control Plane 月可用性 99.5% | up{job="api"} + 5xx 率 + down 告警 | ✅ 已接线 (看板 + 告警) |
| Job 不丢失 (Outbox/MQ/幂等) | specproof_outbox_pending 积压 + relay down 告警 | 🟡 指标与告警已接线; relay 服务尚未进入 compose.production.yml, 部署前该面板无数据 |
| Worker 崩溃后可恢复 | up{job="worker"} down 告警; 恢复语义在应用层 (checkpoint/lease) | 🟡 崩溃检测已接线; 恢复时长指标未接线 |
| FAST p50<=3min / p95<=8min | specproof_jobs_duration_seconds 直方图 (p50/p95 面板 + p95 告警) | ✅ 已接线 (P6 新增直方图); 无 depth 标签, FAST/DEEP 暂时合并统计, 告警用 FAST 480s 上界 |
| DEEP p50<=10min / p95<=25min | 同上 | 🟡 待给指标加 depth 标签后按 DEEP 1500s 分别告警 |
| Webhook 响应 p95<=1s | 无指标 | ❌ 未接线 (api 无 webhook 处理耗时直方图) |
| Dashboard 进度延迟<=2s | 无指标 | ❌ 未接线 |
| BLOCKER/MAJOR Precision>=90% | 无指标 (需按 Finding 判定聚合) | ❌ 未接线 (依赖应用层产出) |
| Capsule Replay>=95% | 无指标 | ❌ 未接线 |
| 无证据严重评论=0 | 无指标 | ❌ 未接线 (由证据门禁保证, 不可观测) |
| PR 归因准确率>=90% | 无指标 | ❌ 未接线 |

§8.10 指标清单中未接线的: 各阶段耗时 (仅总时长直方图)、Finding Precision、
LLM Token 与费用、Tool Timeout、Queue Depth (需 rabbitmq_prometheus 插件, 属 phase0
infra 栈改动)、DLQ、ES 延迟、Redis 命中、Base/Head 沙箱失败 (sandbox/ 代码无指标注册,
属 sandbox 子代理职责)、Certificate 签发率。

已接线指标名 (全部真实注册, 与看板/告警一致):
specproof_up、specproof_http_requests_total、specproof_http_requests_failed_total、
specproof_http_responses_5xx_total (api/server.py 中间件)、
specproof_jobs_completed_total、specproof_jobs_verified_total、
specproof_jobs_blocked_total、specproof_jobs_failed_total、
specproof_jobs_processing_seconds (agent/worker.py)、
specproof_jobs_duration_seconds 直方图 (P6 新增, agent/worker.py)、
specproof_outbox_pending (storage/outbox_relay.py)。

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
