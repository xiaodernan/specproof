# 服务面归属：边缘网关与两个平面的路由表

> 这一节回答一个问题：**一条 HTTP 路径由哪个平面回答？**
> 答案只写在一处 —— `services/gateway/src/main/resources/application.yml` 的路由表；
> `tests/unit/test_gateway_route_table_covers_every_plane_route.py` 每次运行都把两个平面的
> 路由普查重新推一遍，再拿它去对账。

## 为什么需要边缘

SpecProof 有两个 HTTP 平面：

| 平面 | 技术 | 路由数（实测） | 角色 |
|---|---|---|---|
| **control-plane**（`services/control-plane`） | Spring Boot 3.4.3 + JPA + AMQP | **9** | 租户、用户、只读作业门面、GitHub webhook —— 业务的唯一事实源 |
| **agent-runtime**（`api/`） | Python + FastAPI | **61** | Web UI 用的产品 API（作业、账务、管理台、代理控制台） |

**实测出的重叠只有一条**：`GET /health` —— 两个平面各有一份，且**载荷不同**：

- agent runtime 的 `/health`（`api/server.py`）：就绪探针，报告**真正卡住作业执行**的那些存储；
- control-plane 的 `/health`（`HealthController.java`）：`{"service": "specproof-control-plane", "status": "ok"}`。

⇒ **同一个路径、两个不同的事实**。这就是必须有一张归属表的理由：不是「谁先部署谁回答」，
而是「谁拥有这个路径」要写在文件里。

**还有一处不是重叠、但比重叠更容易骗人**：agent runtime 的作业子资源挂在
control-plane 的作业条目路径**下面**：

```
/api/v1/jobs/{id}          ← control-plane 的作业条目
/api/v1/jobs/{id}/stages   ← agent runtime 的（还有 matrix/findings/certificate/capsule/feedback）
```

⇒ 一张「按前缀把 `/api/v1/jobs` 交给控制面」的网关规则会**吞掉**另一个平面的 7 条路由。
⇒ 本项目的路径匹配语义是 Spring 的 **PathPattern**：`{var}` 恰好匹配**一段**，`**` 匹配其余。
这正是路由表里 `/api/v1/jobs/{id}` 与 `/api/v1/jobs/{id}/stages` 互不干扰的原因。

## 路由表

`services/gateway/src/main/resources/application.yml` —— 边缘只有 6 条路由：

| # | id | 平面 | 谓词 |
|---|---|---|---|
| 1 | `control-plane-jobs` | control-plane | `Path=/api/v1/jobs,/api/v1/jobs/{id}` + `Method=GET` |
| 2 | `control-plane-tenants` | control-plane | `Path=/api/v1/tenants` + `Method=GET,POST` |
| 3 | `control-plane-tenant-item` | control-plane | `Path=/api/v1/tenants/{id}` + `Method=GET` |
| 4 | `control-plane-tenant-users` | control-plane | `Path=/api/v1/tenants/{tenantId}/users` + `Method=GET,POST` |
| 5 | `control-plane-github-webhook` | control-plane | `Path=/api/v1/webhooks/github` + `Method=POST` |
| 6 | `agent-runtime-default` | agent-runtime | `Path=/**`（兜底，**必须排最后**） |

兜底排在最后，是因为**列表顺序就是匹配顺序**。它指向 agent runtime，于是
**今天由 agent runtime 回答的每一条路径，今天仍然由它回答**（含 `GET /health`）——
边缘没有改任何客户端可见的行为。

每条路由的 `metadata.plane` 写明它属于哪个平面，`uri` 必须点名该平面的上游变量
（`SPECPROOF_CONTROL_PLANE_URL` / `SPECPROOF_AGENT_RUNTIME_URL`）：
**复制粘贴把控制面的路由指到 agent runtime 的上游上，是红的。**

### 唯一一条「不在边缘上」的路由

```yaml
specproof:
  gateway:
    internal-only:
      - plane: control-plane
        method: GET
        path: /health
        reason: >-
          控制面的探针是集群内部事实（compose healthcheck 与负载均衡直接问服务）；
          边缘上的 GET /health 是 agent runtime 的就绪探针，从边缘存在之前就是它
          在回答。两份载荷是两个事实，所以不能让其中一个替另一个回答。
```

**声明必须为真**：控制面自己的 `/health` 不会被任何路由送回控制面；哪天有人给它加了一条
指向控制面的路由，这条声明就变成假话，门会红。**路由不许凭空消失**：既没有被表覆盖、
也没有声明，就红。

## 门守住什么

`tests/unit/test_gateway_route_table_covers_every_plane_route.py`（7 条腿）：

| 规则 | 关掉的是什么失败 |
|---|---|
| **R1 归属唯一** | 平面自己的路由没有被送回给它自己（路径的含义随部署顺序变） |
| **R2 声明为真** | 「不在边缘上」写成了一句假话；或没有理由；或路由已经不存在了 |
| **R3 兜底在后** | 兜底在中间 ⇒ 把它之后的路由全遮住 |
| **R4 无死路由** | 一条谁都不服务的路由（拼错的路径 ⇒ 404） |
| **R5 不越界** | 一条路由吞掉另一个平面的路由 |
| **R6 平面写明** | 路由 id 重复；平面未知；uri 与所声明的平面不是同一个上游变量 |
| **R7 探针不空** | 普查自己塌了（读不懂控制器/路由器的注解） |

两个普查都是**现推**的：control-plane 从 Spring MVC 注解读，agent-runtime 从 FastAPI
装饰器**用 AST** 读（不是逐行正则 —— 正则分不清 `@router.get("/x")` 和注释里提到它）。

## 本地跑起来看

```powershell
cd services\gateway
mvn -B -DskipTests package          # Boot 3.4.3 + Spring Cloud 2024.0.1（gateway 4.2.1）
$env:GATEWAY_PORT=18080             # 边缘端口（默认 8080）
$env:GATEWAY_MANAGEMENT_PORT=18090  # 管理端口（默认 8090，绑 127.0.0.1）
java -jar target\gateway-0.1.0.jar
```

管理端点**单独占一个端口且绑在回环地址上**：边缘端口上挂 actuator 会把上游拓扑
（路由表里有每个平面的内部 URL）发布给公网。

运行时自己的读数（`/actuator/gateway/routes`，本机实测 HTTP 200）：

```json
{ "route_id": "control-plane-jobs",
  "uri": "http://control-plane:8081",
  "metadata": { "plane": "control-plane" },
  "predicate": "(Paths: [/api/v1/jobs, /api/v1/jobs/{id}], match trailing slash: true && Methods: [GET])" }
```

⇒ **运行时读到的谓词与门建模的谓词逐字一致**：`{var}` 是一段，`Methods` 是显式的，
兜底的 `Paths: [/**]` 排在最后。

## 请求 id：边缘自己也是一个平面（#1558）

agent runtime 早就在读 `X-Request-ID`、没有就自己生成一个 16 位十六进制 id
（`api/middleware.py::RequestIDMiddleware`）。但**边缘自己回的错**原来不带 id：
503（断路器）、502（上游连不上）落到运维手里时，没有一个值可以引用，也没法拿它去
上游日志里搜。

所以边缘也用同一套语言：

- `EdgeRequestIdGlobalFilter`（`GlobalFilter`，order = HIGHEST_PRECEDENCE + 10）：
  **进来带了就原样带走**（调用方在用它对账自己的日志，边缘不改写别人的 id）；
  **没带就现生成一个**（16 位小写十六进制，与 agent runtime 的 `uuid4().hex[:16]`
  同一个形状）；id 写进请求头**转发给上游**，也回显在响应头上——包括边缘自己出的错。
- 断路器的 503 体里带 `request_id`：`{"error":"upstream_unavailable",
  "edge":"circuit-open","state":"open","request_id":"…"}`。

**两个平面的头名与 id 形状必须一致**，否则运维读到的 id 和上游日志里的 id 不是同一个。
`tests/unit/test_edge_request_id_matches_the_agent_runtime.py`（3 条腿）逐字比对两侧的
声明：header 名、id 长度、以及「进来的 id 不改写」这条语义——Java 侧单方面改名或改长度，
这道门立刻红。

## 上游可见性：超时、池、与网关自己的指标（#1568 / #1570 / #1571 / #1572）

边缘原来是「只会拒绝」的存在——断路器管失败、不管排队；而**排队**（连接池耗尽、
调用方全挂在 `response-timeout` 前的等待里）同样把请求拖死，只是看起来不像失败。
这几号补上了那一半：

- **超时**（#1568）：`spring.cloud.gateway.httpclient.connect-timeout=5000`、
  `response-timeout=30s`——SCG 对 response-timeout **没有默认值**（未设 = 等死）。
  `GatewayUpstreamTimeoutTests.java` 用睡 10 秒的 JDK `HttpServer` 上游证明：
  告警体 `{"error":"upstream_unavailable","edge":"circuit-open","state":"closed",…,
  "request_id":"…"}` 在 9 秒内回，而 30 秒才来的回包什么都证明不了。
  response-timeout 约束的是**第一个响应字节**，**不**切 SSE 长连接。
- **连接池指标**（#1570）：`httpclient.pool.metrics=true`（SCG 默认 false）⇒
  `reactor.netty.connection.provider.{total,active,idle,max,pending}.connections`
  进 Prometheus（management 端口早被抓）。**连 connect 池满了都看得见**——
  "agent runtime 慢"和"边缘池满了在排队"在这里分得开。
- **池满告警**（#1571）：`SpecproofEdgePoolSaturated`（`reactor_netty_…_pending_connections
  {name="proxy"} > 0`，for 2m）——pending 持续 = 上游在排队而非拒绝；与
  `SpecproofEdgeCircuitBreakerOpen`（拒绝）和 `SpecproofEdgeGatewayDown`（抓不到）
  三者各守各的失效形状；EdgeGatewayDown 的 annotation 点名了这两个受守家族
  （被抓断 = 两个家族同时沉默，不点名读者看不见）。
- **路由自己的 metrics**（#1572）：`spring.cloud.gateway.metrics.enabled=true`
  （默认 false）⇒ `spring.cloud.gateway.requests`（CumulativeTimer，tag：routeId /
  outcome / routeUri …）与 `spring.cloud.gateway.routes.count`（gauge，== 6）。
  每条路由怎么结束，不用翻日志。

面板：Grafana「Edge 上游连接池（reactor-netty）」(56) 与「Edge 各路由请求速率
（SCG metrics）」(57)——未经 Grafana 渲染实测，面板只有 PromQL 字面合法的证明。

## 这个单元故意不做的事

- **不注册服务中心**（Eureka）：一个边缘 + 两个上游不是集群；本项目自己的商业计划
  「风险 7」明确反对在还没挣到的时候把产品拆成十几个部署单元 ⇒ 路由表就是
  「谁回答什么」的全部故事，而且它是一个人能读完的文件。
- **不改写路径**（无 `RewritePath`）：边缘路径与服务路径一旦不同，就多出第二份
  「这条路径本来是什么」的事实，而那正是最容易烂掉的东西。
- **不给边缘加认证**：边缘只做路由，两个平面各自认证（agent runtime 的路由挂着
  `require_api_key`）；网关依赖树里只有 `spring-security-crypto`，没有 security 自动配置
  ⇒ 被代理的请求不会被边缘拦下。

## 诚实边界

1. 门是**静态**的：它读文件、按 PathPattern 语义模拟匹配；它**不启动** JVM。
   运行时由 actuator 单独核对（见上），两条读数目前一致。
2. 运行时对**尾斜杠**更宽松（`match trailing slash: true`），门的模型不认尾斜杠；
   两个平面的路由普查里本来就没有带尾斜杠的路径，所以当前无差 ⇒ 哪天出现带尾斜杠的
   路由，门的模型要跟一步。
3. 门只覆盖**这两个平面**。agent runtime 内部自己路由的顺序（它把 SPA 兜底注册在最后、
   并对保留前缀回 404）**不归**这张表管 —— 边缘不拆它。
4. CI **没有 Java 腿** ⇒ 这道门必须是纯 Python、离线可跑的，它就是；Maven 构建与
   actuator 读数是**本机**实测，不在 CI 里。
