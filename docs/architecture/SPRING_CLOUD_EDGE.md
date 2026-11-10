# Spring Cloud 已接入元素（2026-11-10 实测）

本文列出仓库里已经落地的 Spring Cloud / Spring Boot 引用元素（以 pom.xml /
application.yml / Java 测试 / 看板 / 告警作为证据），不吹未落地的。本页只描述
存在的，不在这里规划未来的。任何「已实现」旁边的测试门指向一个真跑的 Java JUnit。

> 2026-11-11 增补（#1603）：元素表里**唯一一处跨语言接缝**是 W190 事件总线。Spring Cloud 侧此前只有一个订阅者（`GatewayMqEventConsumer`），Python 侧只把事件写进日志 —— 即「没有生产者的订阅者」。#1603 补上生产侧并把 exchange / 六键 / 默认关 / 两侧接线写进跨语言门。本页所有「已接入」条目都要求一个真跑的 JUnit 或 pytest，故本行同时指向 `mvn -o -B test` 的 51 例与 Python 的 22 例，而不是只指向一份声明。

> 2026-11-11 增补（#1599）：`opentelemetry-spring-boot-starter` 2.33.1 仅在 BOM
> 对齐下可启动（`opentelemetry-instrumentation-bom` 2.33.1 与
> `opentelemetry-instrumentation-bom-alpha` 2.33.1-alpha 两套同时钉住；漏掉其一时
> SDK 启用即报 `EventLoggerProvider` / `ComponentLoader` 找不到）。实测过程见 #1599。

## 两大服务（Spring Boot 3.4.3 + Spring Cloud 2024.0.1）

| 模块 | 作用 | 关键依赖 | Spring Cloud 元素 |
|---|---|---|---|
| `services/control-plane` | 业务读外观：租户/用户/作业状态/webhook/audit | spring-boot-starter-web,-data-jpa,-amqp,-actuator,-validation,micrometer-registry-prometheus | （无——控制面自己就是被边缘代理的 Spring Boot service；自身的 metrics 通过 actuator+prometheus 暴露） |
| `services/gateway` | 边缘路由：决定哪个平面回答哪个路径 | spring-cloud-starter-gateway, resilience4j-circuitbreaker + resilience4j-ratelimiter（2.2.0）+ resilience4j-micrometer, micrometer-registry-prometheus, spring-boot-starter-actuator, spring-boot-starter-aop | SCG + Resilience4j 断路器 + Resilience4j 限流器 + 池/网关/路由指标 + /actuator/gateway/routes |

## 边缘的 Spring Cloud 元素（本仓唯一 SCG service）

| 元素 | 落点 | 验证门 |
|---|---|---|
| Spring Cloud Gateway 路由表（6 条 routes，顺序即匹配序） | `services/gateway/src/main/resources/application.yml` | `tests/unit/test_gateway_route_table_covers_every_plane_route.py`（7 条腿，R1-R7） |
| `opentelemetry-spring-boot-starter`（OTLP gRPC 导出到同网 `otel-collector:4317`；默认禁用 `OTEL_SDK_DISABLED=true`，由 compose 观测 profile 打开；`application.yml` 的 `otel` 段钉 service name + `parentbased_always_on` sampler） | pom + application.yml `otel:` block + compose.observability.yml specproof-edge env | `GatewayApplicationTests`（`OTEL_SDK_DISABLED=false OTEL_TRACES_EXPORTER=logging mvn -B test -Dtest=GatewayApplicationTests` = 7/7 绿；`mvn -o -B test` 全 28 绿——codec 也实测过） |
| Resilience4j 断路器（catch-all 派发 503 `upstream_unavailable` 体 `request_id` 兜底 + state 写 Java logger/warn） | `services/gateway/.../EdgeCircuitBreakerGatewayFilterFactory.java` | `GatewayApplicationTests`（6 腿含 breaker）+ `EdgeCircuitBreakerGatewayFilterFactoryTest` + `GatewayUpstreamTimeoutTests`（真 hang 住上游，1 秒后 503） |
| Resilience4j 断路器（5 条 control-plane 路由各自挂 `EdgeCircuitBreaker=specproof-control-plane`，实例名独立，挂起不占线程到 httpclient 30s 超时） | `services/gateway/src/main/resources/application.yml`（5 条 control-plane 路由的 filters） | `GatewayApplicationTests.everyControlPlaneRouteCarriesItsOwnBreaker`（5 条路由逐条 name/args 断言 + 实例双注册） |
| SCG Retry 过滤器（4 条只读 control-plane 路由挂 `Retry`：`retries: 2, statuses: INTERNAL_SERVER_ERROR, methods: GET, backoff(firstBackoff=100ms, factor=2, maxBackoff=500ms)`；webhook POST 显式不挂——重试会复制上游 webhook 副作用；GET-only：POST 路由靠断路器和上游语义，不重试） | `services/gateway/src/main/resources/application.yml` | `GatewayApplicationTests.everyGettableControlPlaneRouteCarriesTheRetryFilter`（4 条重试路由逐条 name/args 断言；`control-plane-github-webhook` 断言不含 Retry；count=32 Java 网关测试） |
| Resilience4j RateLimiter（catch-all 入向令牌桶 50/s，空桶本地应答 429 `rate_limited` 体 `request_id` + `Retry-After` 头；edge 不做认证故无 principal 可分钥，全局桶是诚实控制；计数器 `specproof_gateway_rate_limited_total` + 标签维度 `limiter`；gauge `resilience4j_ratelimiter_available_permissions` / `resilience4j_ratelimiter_waiting_threads`） | `services/gateway/.../EdgeRateLimiterGatewayFilterFactory.java`（pom 加 resilience4j-ratelimiter 2.2.0 + application.yml catch-all 挂 filter） | `EdgeRateLimiterGatewayFilterFactoryTest`（3 腿：放行、空桶 429+request_id+Retry-After、micrometer 计数 + 可用许可 gauge）+ `GatewayPrometheusEndpointTests`（含上项两系列名） |
| `EdgeRequestIdGlobalFilter`（trace/span 传播 + 503 体含 request_id） | `services/gateway/.../EdgeRequestIdGlobalFilter.java` | `EdgeRequestIdGlobalFilterTest` + `tests/unit/test_edge_request_id_matches_the_agent_runtime.py`（Python 腿：逐字比对头名/ID 形状） |
| `EdgeSecurityHeadersGlobalFilter`（防御性响应头：`X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY` / `Referrer-Policy: no-referrer` / `Cross-Origin-Opener-Policy: same-origin` / `Strict-Transport-Security: max-age=31536000; includeSubDomains` / `Permissions-Policy: geolocation=(),camera=(),microphone=(),payment=()` / `X-Permitted-Cross-Domain-Policies: none`；全局过滤器，覆盖边缘自身错误响应（503/502）；`specproof.gateway.security-headers.enabled`（默认 true）可关；刻意不加 CSP（catch-all 同时服务 SPA）与 CORP same-origin（会断 SPA 跨源资源）） | `services/gateway/.../filter/EdgeSecurityHeadersGlobalFilter.java` | `EdgeSecurityHeadersGlobalFilterTest`（3 腿：全头集存在、关闭时不出头、默认启用）+ `mvn -o -B test` 全 47 绿（含 #1601 3 例） |
| `EdgeRequestSizeGlobalFilter`（入向请求体尺寸上限：声明体 > `specproof.gateway.request-size.max-bytes`（默认 10 MiB）即 413 短路、不触上游；未知尺寸（chunked 无 Content-Length）不拦截——边缘不消费即弃；`specproof.gateway.request-size.enabled` 可关） | `services/gateway/.../filter/EdgeRequestSizeGlobalFilter.java` | `EdgeRequestSizeGlobalFilterTest`（5 腿：超帽 413 且链不调用、帽内放行、未知尺寸放行、关闭时放行、默认 10MiB 启用）+ `mvn -o -B test` 全 47 绿（含本号 5 例） |
| `GatewayMqEventConsumer`（**事件驱动微服务 #1603**：边缘订阅 W190 六事件 RabbitMQ 观测总线 `specproof.observability.events`（topic 交换机），六路由键 `published`/`publish_confirm_timeout`/`consumed`/`duplicate_acked`/`retry_scheduled`/`dead_lettered` 逐个绑定到 `q.gateway.mq-events`；每事件 `MeterRegistry.counter("specproof.gateway.mq.event", "event", name)` 累加；**默认关** `specproof.gateway.mq-events.enabled=false`——关时 bean 不创建、不连 broker、集群照常起；开启需交换机与六路由键就位否则容器绑定失败 fail-loud；malformed JSON 计 `event=malformed`、缺/非字符串 `event` 计 `event=unknown`，不实造；Python 侧对应 `storage/rabbitmq.py` 的 `RabbitMQBusSink`/`CompositeEventSink`/`declare_events_bus`，把 W190 事件真正发到该总线，是两边唯一事件驱动接缝） | `services/gateway/.../mq/GatewayMqEventConsumer.java` + `application.yml`（`specproof.gateway.mq-events: {enabled:false, exchange: specproof.observability.events, queue: q.gateway.mq-events}`）+ `pom.xml`（`spring-boot-starter-amqp`，新增、未引 Stream binder） | `GatewayMqEventConsumerTest`（8 腿：按名字计数、各事件独立累加、六事件全覆盖、缺名字=unknown、非字符串=unknown、null=unknown、exchange/queue 暴露、KNOWN_EVENTS 恰六）+ `mvn -o -B test` 全 47 绿（含本号 8 例）+ Python 侧 `tests/unit/test_rabbitmq_bus_sink.py`（7 腿：按名转发、缺名=unknown、非字符串=unknown、注入 publisher、composite fan-out、wiring 入 client 无递归、declare_events_bus 拓扑） |
| `GatewayProperties`（**配置外置 #1604**：把边缘所有可调旋钮——`request-size.enabled`/`max-bytes`、`security-headers.enabled`、`mq-events.enabled`/`exchange`/`queue`——从散落的 `@Value` 字符串收拢到单个 `@ConfigurationProperties(prefix="specproof.gateway")` bean，三个 filter 改注入该 bean 而非各自读 `@Value`；无新依赖，默认与旧 `@Value` 字面量完全一致——纯 Spring Boot 微服务"配置外置"惯用法，operator 改一处即全局调参，且可被 config-server / env 统一覆盖） | `services/gateway/.../config/GatewayProperties.java` + `GatewayConfig.java`（`@EnableConfigurationProperties`）+ `EdgeRequestSizeGlobalFilter`/`EdgeSecurityHeadersGlobalFilter`/`GatewayMqEventConsumer` 改注入该 bean（保留直构造器供测试，**45 个既有网关测试零改动仍绿**） | `GatewayPropertiesBindingTest`（2 腿：绑定默认+`@TestPropertySource` 覆盖 `max-bytes=2048`/`security-headers=false` 生效、`mq-events` 默认关且 `exchange`/`queue` 默认就位）+ `mvn -o -B test` 全 47 绿（含本号 2 例） |
| **W190 六事件 RabbitMQ 总线（事件驱动微服务接缝）**：Python `storage/rabbitmq.py` 的六个可靠投递事件（`published` / `publish_confirm_timeout` / `consumed` / `duplicate_acked` / `retry_scheduled` / `dead_lettered`）经 `SPECPROOF_MQ_EVENTS_ENABLED=1` 由 `storage/rabbitmq.py::RabbitMQBusSink`（唯一发布实现, 经 `observability/mq_events.py::GuardedBusSink` 守卫） 发到 durable topic exchange `specproof.observability.events`（routing key == 事件名）；边缘 `@RabbitListener` 绑 durable queue `q.gateway.mq-events` 到同样六个键，按 `event` 标签累计 `specproof.gateway.mq.event`。两侧**默认关**：Python 关时仍装原来的 no-op sink（字节级 legacy），Java `@ConditionalOnProperty(havingValue="true")` 关时不建 listener container、不连 broker。词汇唯一拥有者 = `observability/event_vocabulary.py`；`storage/rabbitmq.py` 的 `MQ_EVENTS`/`EXCHANGE_EVENTS`/`QUEUE_GATEWAY_MQ_EVENTS` 只是别名 | `observability/event_vocabulary.py` + `observability/mq_events.py` + `storage/rabbitmq.py` + `services/gateway/src/main/java/dev/specproof/gateway/mq/`（pom 加 `spring-boot-starter-amqp`，版本由 Boot 3.4.3 父管） | `tests/unit/test_w190_event_bus_producer.py`（16 例）+ `tests/unit/test_w190_event_bus_has_both_sides.py`（6 例，跨语言四处对账）+ `GatewayMqEventBindingTest`（4 例，反射读真注解）+ `GatewayMqEventConsumerTest`（8 例）；`mvn -o -B test` 全 **51** 绿（#1602 时 37 → #1603 消费侧 +8=45 → #1604 配置外置 +2=47 → #1605 绑定门 +4=51） |
| Micrometer 池/网关/路由计量 + `/actuator/prometheus`（JSON） | `application.yml`（`management.prometheus.metrics.export.enabled: true` + `percentiles-histogram.spring.cloud.gateway.requests: true`） | `GatewayPoolMetricsTests`（远程端点抓数 + x3 面板）+ `GatewayMetricsTests`（4 路定时器矩阵）+ `GatewayPrometheusEndpointTests`（/actuator/prometheus 不是 catch-all 应答） |
| `/actuator/gateway/routes`（SCG 自有 actuator 路由表）、`/actuator/health`、ring buffer | 出场默认 loopback，compose 观测网变更为可被 Prometheus 抓取 | `GatewayActuatorRoutesTests`（5 腿：route 表恰好 6 条、catch-all 最后、edge 端口 404、管理端口 200） |
| Spring Cloud Gateway 的 `spring.cloud.gateway.metrics.enabled: true`（路由 Timer 按 routeId） | `application.yml` | `GatewayMetricsTests`（2 腿） |

## Grafana 看板上对应的 Spring Cloud 面板（本仓 60 面板）

| 面板 | 对应元素 | 编号 |
|---|---|---|
| 断路器状态 stat | resilience4j circuitbreaker state gauge | 53 |
| Edge 路由归属表（markdown） | application.yml 路由表 | 54 |
| 断路器状态历史 timeseries | resilience4j per-state gauge | 55 |
| Edge 上游连接池 timeseries | reactor.netty.connection.provider.* | 56 |
| Edge 各路由请求速率 timeseries | spring.cloud.gateway.requests | 57 |
| Edge 各路由 p95 延迟 timeseries | histogram_quantile on spring_cloud_gateway_requests_seconds_bucket | 58 |
| Edge RateLimiter 丢弃速率 timeseries | rate(specproof_gateway_rate_limited_total[5m]) | 59 |
| Edge RateLimiter 可用许可证 timeseries | resilience4j_ratelimiter_available_permissions{name="specproof-edge-public"} | 60 |

## 告警（22 条 SLO 规则里与 Spring Cloud 相关的）

| 告警 | 守什么 |
|---|---|
| SpecproofEdgeGatewayDown | `up{job="specproof-edge"} == 0`（探针点名 resilience4j + reactor_netty 两个受守家族） |
| SpecproofEdgeCircuitBreakerOpen | `resilience4j_circuitbreaker_state{name="specproof-edge",state="open"} > 0` |
| SpecproofEdgePoolSaturated | `reactor_netty_connection_provider_pending_connections{name="proxy"} > 0` |
| SpecproofEdgeRateLimiterShedding | `rate(specproof_gateway_rate_limited_total[5m]) > 1` 持续 10m——EDGE_RL_SHED_THRESHOLD=1，调用方需降频信号 #1589/#1591 |

## 事件与不变量

- 边缘不做认证——认证留给两个上游（agent runtime 的 API key、control-plane 的 JWT）
- catch-all 必须排最后（`agent-runtime-default`）——路由顺序由门钉死
- `/actuator/*` 不在 edge 端口答（否则 edge 会泄露路由表 + 上游 URL）；管理端口单独监听 + loopback
- 两个 planes 都不会"没人知道"：Prometheus scrapes 边缘 management 端口 `specproof-edge:8090`
- Spring Cloud Gateway 的 DiscoverClient/注册中心：**未接入**（单机部署，没必要，
  避免过早微服务化；那个决策已写在 ADR-018）
- 限流器只护公开产品面（catch-all），不分钥（边缘无认证）；control-plane 路由不限流——
  它们是内部外观，放大了反而是 false sense of security；要限就全环，理由写在 ADR-019
- 入向 429 与上游故障 503 是两种信号：429 = 调用方需降频、503 = 上游不可用；
  看板/告警若要区分，用 `specproof_gateway_rate_limited_total` 与 `resilience4j_circuitbreaker_state`

## 当前 Spring Cloud 仍是 0.1 单边

- **控制面没有 Spring Cloud 元素**：它是被边缘代理的内部服务，自身 metrics 通过
  actuator + micrometer-prometheus 对外（`#1585`），不是 SCG。
- **Python 侧不是 Spring Cloud**：Python agent runtime 与 `observability/`（Python）
  与 Spring 无关，两边靠 `X-Request-ID` 关联。但 #1603 在 Python 侧新增
  `RabbitMQBusSink`/`CompositeEventSink`/`declare_events_bus`（`storage/rabbitmq.py`），
  把 W190 观测事件发到 `specproof.observability.events` topic 总线，边缘的
  `GatewayMqEventConsumer` 订阅——这是两边唯一一个**事件驱动**的接缝（默认关，需两端都
  开启才生效；总线 sink 走 `RabbitMQClient._publish_raw`，转发事件不会自递归）。
- **服务发现**：没有 Eureka/Consul/Nacos——这是设计决定（`#1585` 前身），不是缺陷。

## 如果你要接入

1. **Service Discovery**：加 `spring-cloud-starter-netflix-eureka-client`，
   `application.yml` 的 `spring.cloud.discovery.client.simple-enabled=false`，
   `compose.production.yml` 起 eureka 容器，改 `lb://serviceId` URIs。
2. **配置中心**：目前所有配置都是 `application.yml` + env 变量；
   若要多环境配置统一，`spring-cloud-config-client` + 一个 config server compose
   服务即可（本仓无兴趣此事的优先级）。
3. **Spring Cloud Contract**：本仓没有 CDC 契约——Python agent runtime 和 Java
   control-plane 之间的协议是已定死的 outbox + `verification_jobs` 投影，目前
   没有比这个更值得契约化的。

以上状态基于 master `cf29dda`（+ #1589 限流器、#1590 面板 59/60、#1601 安全头、#1602 请求尺寸、#1603 事件总线消费者）测量；所有数字
（6 routes、60 panels、22 alerts、tags/probe counts、47 Java 网关测试）都有对应的 Java/Python 门现算。
限流器两条面板（59 丢弃速率 rate(5m)、60 可用许可证 gauge）是 timeseries + 单绿色阈值，
不带画数字阈值——`test_dashboard_slo_figures_bind_their_declarations.py` 无需新增声明，
51 passed 实证（docs/dashboards 三门同套）。
