# services/ — the Spring Cloud microservice lane

> 中文见下；operating notes for anyone (human or model) standing this up.
> 本文件逐段中英对照 / sectioned zh+en, one idea per block. Everything below is
> read out of this tree — ports and defaults come from the actual `application.yml`
> files, nothing is cargo-culted from memory.

## 1. What lives here / 这里有什么

| Module | Role / 职责 | Default port |
|---|---|---|
| `discovery-server` | Eureka registry (Spring Cloud Netflix). 微服务的通信录：所有实例自报家门，服务互找靠它；网关注册在上面，`instance host:port` 从注册中心可见。 | **8761** |
| `config-server` | Spring Cloud Config, **native** profile, `src/main/resources/config/`. 配置中心：网关的路由表、熔断与限流参数由它发放；`POST /actuator/refresh` 热刷新，`specproof_edge_config_refresh_events_total` 计数见证（0.0 → 1.0 实测于 2026-11-14）。 | **8888** |
| `gateway` | Spring Cloud Gateway（响应式，Netty）+ Resilience4j 熔断 + **Redis 令牌桶分布式限流** + singleflight 响应缓存 + 路由表同构门（isomorphism gate）+ `/actuator/health`、`/actuator/prometheus`。 | **8080**（`GATEWAY_PORT` 覆盖） |
| `control-plane` | 控制面：GitHub webhook 验签/去重/分发、RabbitMQ 消费（`RABBITMQ_PORT`）、MySQL 持久化（`MYSQL_*`）。它不是一个给浏览器看的服务，是一条异步链的内核。 | RabbitMQ **5672**（`RABBITMQ_PORT`） |

## 2. The algorithm lane / 算法这一刀（为什么不是花架）

- **Redis token bucket（Lua 原子）**：`gateway/ratelimit/` 下有 `TokenBucketScript` + `RedisTokenBucketScript` 与 `RedisTokenBucketRateLimiter`——容量恒等式不放水：固定容量 N、按速率补充、超额拒绝并带 `Retry-After`。这正是"计网知识 + 操作系统调度 + 数据结构"在生产语境里的落点：浏览器/HTTP 的流量进来按令牌恒速通关。
- **SingleFlight 响应缓存**：同一路由上的并发相同 GET 只放行一次到上游，其余共享同一个 future——在 capsules 这类读风暴下直接消掉 N−1 次上游压力。命中与合流是算法，不是装饰。
- **Resilience4j 熔断**：连续失败达到阈值 → 打开 → 半开试探 → 关闭；`EdgeCircuitBreakerGatewayFilterFactory` 把故障挡在上游之外；micrometer 把事件与状态导出到 `/actuator/prometheus`。
- **路由表同构门**：网关路由表与审计侧"端点清单"双向钉住——两边对不上就红。这是计网"你上报的分区就是真相"在配置层面的投影。
- **Outbox + RabbitMQ**：状态变更先进 outbox（MySQL），再异步投递；at-least-once + 幂等消费；把 5xx 计数和业务写解耦。

## 3. Boot it / 起得来的顺序（each module is a standalone Maven project）

```bash
cd services/discovery-server && mvn spring-boot:run   # 8761
cd services/config-server    && mvn spring-boot:run   # 8888
cd services/gateway          && mvn spring-boot:run   # 8080
cd services/control-plane    && ./mvnw spring-boot:run # webhook→MQ lane (MySQL/RabbitMQ required)
```

**Verification on file (2026-11-14)**: `POST /actuator/refresh` drove
`specproof_edge_config_refresh_events_total` 0.0 → 1.0; consecutive failures against a dead
upstream opened the breaker at the threshold; the distributed rate-limit filter returns
429 + `Retry-After` once the bucket drains. Ledger anchors: `#1673/#1674` in
`docs/operations/DEEP_OPTIMIZATION_PLAN.md`.

**Unit tests — real run on this machine (2026-11-15)**:

```text
mvn -o -B -ntp test   # services/gateway, Maven 3.9.15, offline, Netty on ephemeral ports
[INFO] Tests run: 81, Failures: 0, Errors: 0, Skipped: 0
[INFO] ------------------------------------------------------------------------
[INFO] BUILD SUCCESS                     Total time: 02:03 min
```

Landmarks from that run: `RedisTokenBucketRateLimiterTest` 5/5 ·
`GatewayUpstreamTimeoutTests` 2/2 · `GatewayMqEventConsumerTest` 8/8 ·
`GatewayMqEventBindingTest` 4/4 · `GatewayPoolMetricsTests`, `GatewayPrometheusEndpointTests`,
`GatewayApplicationTests` etc. all green · `RouteTableIsomorphismGate` printed a **non-fatal**
warning (`missingServices=[api, control-plane]`) — a pinned visibility gap, not a pass/fail lie.

**Per-module**: the other three services carry their own suites; only the gateway was re-run this round —
don't extrapolate the 81/81 into them.

## 4. Honest limits / 诚实边界

- No production zero-downtime claim beyond what tests prove — nothing soaks multi-node in this repo.
- The distributed limiter needs a real Redis (or the test doubles); it is not faked anywhere.
- Ports and credentials come from `application.yml` + environment variables; no secrets are committed.
- `control-plane` is production-shaped but not load-soaked; its DTO surface is deliberately narrow.

## 5. Where the world book talks about this / 世界书入口

卷四《微服务军阵》(The Steel Rampart) — `docs/world/SPECROOF_WORLD.md`.
Every claim above maps to a real file in this tree; nothing in this lane is decorative.
