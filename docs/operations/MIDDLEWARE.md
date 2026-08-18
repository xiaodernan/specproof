# SpecProof 中间件与拦截链盘点 (J 轮, 2026-08-18)

对应 AGENT_STATE_OF_ART.md §6「中间件完整性」的补齐项落地: Request-ID 传播 +
JSON 请求体大小限制 + 本盘点文档。全链路每一环都列出职责 / 配置 / 验证方式;
验证命令均为实测口径, 禁止把「配置了」当作「生效了」。

## 1. 请求处理顺序 (FastAPI, 最外 → 最内)

```
RequestID  →  PayloadLimit  →  request_metrics  →  OTel tracing (若启用)  →  CORS
   →  路由依赖: auth (fail-closed) → rate limit (fail-open)  →  处理器  →  SSE / 静态文件
```

- 注册位置: api/server.py (add_middleware 是前插, 后注册者先执行: RequestID 注册在最后 = 最外层)。
- RequestID 最外: 任何一层 (含 413 / 401 / 503) 的响应都带 X-Request-ID。
- PayloadLimit 在 auth 之前: 超大 JSON 请求体在鉴权前即被 413 拒绝 (不消耗应用逻辑)。
- SSE (GET /jobs/{id}/progress) 是 GET 流式响应: PayloadLimit 只作用于
  POST/PUT/PATCH + application/json, 永不触碰流; 两个新中间件均为纯 ASGI
  (非 BaseHTTPMiddleware), 不缓冲流式响应。

## 2. FastAPI 侧中间件盘点

| # | 中间件 | 位置 | 职责 | 配置 | 验证方式 |
|---|---|---|---|---|---|
| 1 | RequestID | api/middleware.py | 读取 X-Request-ID, 缺失则生成 uuid4().hex[:16]; 回显响应头; 写入 request.state.request_id 与 observability request_id_var (所有结构化日志行带 request_id 字段) | 无必填; 客户端可自带 X-Request-ID | curl -s -D - -H "X-Request-ID: smoke-1" -H "X-API-Key: $key" http://localhost:8000/api/v1/health → 响应头 X-Request-ID: smoke-1; 不带该头时回显 16 位 hex; 日志 JSON 含 "request_id" |
| 2 | PayloadLimit | api/middleware.py | JSON 请求体上限, 超限 413 (在 auth/路由之前); 只作用于 /api/、/jobs、/webhooks 的 POST/PUT/PATCH + application/json | SPECPROOF_MAX_JSON_BYTES (默认 10485760 = 10 MiB, 每请求读取可热调) | 超大 JSON POST /jobs → 413 + detail 含字节数; 小体 → 正常路径 |
| 3 | CORS | api/server.py (CORSMiddleware) | 跨域白名单; 生产禁用 "*" | SPECPROOF_CORS_ORIGINS (逗号分隔, 默认 localhost:3000,localhost:8000) | 带白名单 Origin 请求 → access-control-allow-origin 回显; 非白名单源无该头 |
| 4 | auth | api/auth.py:require_api_key (路由依赖) | API Key 校验, fail-closed: 未配置 key 时拒绝服务 (503), 绝不开后门; 常量时间比较; SSE 场景允许 query 传 key | SPECPROOF_API_KEY | 无 key → 401; 未配置 SPECPROOF_API_KEY → 503 (生产默认凭据由 storage/config_guard 阻止启动); 错误 key → 401 |
| 5 | rate limit | api/auth.py:enforce_rate_limit (路由依赖) | 每 key 固定窗口限流 (Redis 计数器); 防滥用而非安全边界: Redis 不可用时放行并记日志 (fail-open, 可用性优先) | SPECPROOF_RATE_LIMIT_PER_MIN (默认 60) | 60 次/分钟内第 61 次同 key 请求 → 429; 停掉 Redis 后请求仍 200 (日志记 warning) |
| 6 | metrics | api/server.py:request_metrics + GET /metrics | 每请求计数 (总数/失败/5xx), Prometheus 文本暴露 | 无 (Prometheus 抓取 :8000/metrics) | curl -s http://localhost:8000/metrics → specproof_http_requests_total 递增 |
| 7 | tracing | observability/middleware.py:add_trace_middleware | OpenTelemetry 自动插桩 (FastAPI), 未装/未启用时 NoOp | SPECPROOF_OTEL_ENABLED=1 | 启用后 OTLP HTTP 导出到 otel-collector:4318; trace 链路 Webhook→Outbox→RabbitMQ→Worker→LLM→Tools→GitHub (见 OBSERVABILITY.md) |
| 8 | logging | observability/logging.py (JsonFormatter) | 结构化 JSON 每行一条; job_id / trace_id / request_id 由 contextvar 注入 | 无 | 任意 API 请求 → stdout 的 JSON 行含 "request_id" (J 轮新增字段) |
| 9 | SSE 例外 | api/routes/jobs.py:job_progress | text/event-stream 实时进度 + Last-Event-ID 续传; 明确不受 PayloadLimit 影响 (GET 无体) | 无 | curl -N -H "X-API-Key: $key" http://localhost:8000/jobs/<id>/progress → id:/event:/data: 帧; 断线重连带 Last-Event-ID 从断点续 |

## 3. CP 侧 (Spring Boot 对端) 拦截链

| 环节 | 实现 | 职责 | 配置 | 验证方式 |
|---|---|---|---|---|
| webhook 验签 | integrations/github.py:verify_signature | X-Hub-Signature-256 = HMAC-SHA256(payload, webhook_secret), 常量时间比较, 配置错误/签名缺失一律 fail-closed (401/503, 绝不静默放行) | GITHUB_WEBHOOK_SECRET | 用 sign_payload 生成合法签名 → 202 accepted; 篡改 body / 错误签名 → 401 (tests/unit/test_github_webhook.py) |
| 审计 | api/routes/jobs.py:store.record_audit (MySQL audit 表) | 关键动作 (如 job_cancelled: actor/from_status/to_status) 落库可追溯 | 无 (随 MySQL 可用性) | 取消任务后查 audit 表存在 job_cancelled 行 |
| outbox | storage/mysql.py:create_job_with_outbox | 任务行 + outbox 事件在**同一事务**提交 (at-least-once 投递, 消费者幂等); API 崩溃不丢事件 | 无 | POST /jobs → 202 且 outbox 表同事务可见; relay 重投不双跑 (test_outbox.py / test_api_jobs.py) |
| delivery 幂等 | api/routes/webhooks.py:_delivery_key | X-GitHub-Delivery+event 哈希去重, GitHub 重投不重复入队 | 无 | 同一 delivery 重投 → {"action": "duplicate_delivery"} |

## 4. 配置项速查

| 变量 | 默认 | 作用 |
|---|---|---|
| SPECPROOF_API_KEY | (无) | API Key; 未配置 = 全部任务操作 503 |
| SPECPROOF_RATE_LIMIT_PER_MIN | 60 | 每 key 每分钟限流 |
| SPECPROOF_MAX_JSON_BYTES | 10485760 (10 MiB) | JSON 请求体上限, 超限 413 |
| SPECPROOF_CORS_ORIGINS | localhost:3000,localhost:8000 | CORS 白名单 |
| SPECPROOF_OTEL_ENABLED | (空) | 置 1 开启 OTel tracing |
| GITHUB_WEBHOOK_SECRET | (无) | webhook 验签共享密钥 |

## 5. 响应缓存策略 (明确记录)

有意**不引入服务端响应缓存**: 证据产物 (报告/证书/capsule) 是流水线的真实状态,
任一时刻都可能被新一轮验证覆盖; SSE 进度流本质实时; 仪表盘聚合读 MySQL 实时行。
缓存会违反诚实降级契约 (可能把陈旧数据当当前事实)。SSE 响应显式
Cache-Control: no-cache; 静态资源 (SPA/dashboard) 由前端构建层处理指纹缓存,
不在 API 层决策。若未来需要加速读路径, 策略应落在显式产物版本号 (job_id +
证书 digest) 上, 而不是中间件透明缓存。

## 6. 验证清单 (全部实测)

powershell:
# Request-ID 透传 + 回显 (响应头逐字回显)
curl.exe -s -D - -H "X-Request-ID: smoke-1" -H "X-API-Key: $env:SPECPROOF_API_KEY" http://localhost:8000/api/v1/health
# 未带 → 生成 16 位 hex; 日志 JSON 行含 "request_id"
# Payload 超限 → 413 (auth 之前): 构造 >10MB JSON POST /jobs
# SSE 流不被 payload 中间件拦截
curl.exe -N -H "X-API-Key: $env:SPECPROOF_API_KEY" http://localhost:8000/jobs/<job_id>/progress

自动化覆盖: tests/unit/test_middleware.py (15 用例: request-id 生成/透传/唯一/
413 上回显/结构化日志字段/contextvar 复位; payload 超限 413 先于 auth/放行/
非 JSON 豁免/非 api 路径豁免/GET 豁免; SSE 流式完整断言)。
