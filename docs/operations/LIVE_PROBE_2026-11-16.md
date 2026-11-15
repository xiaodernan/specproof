# 实测纪要 · 2026-11-16 · 单机真实验收车道（Live Probe）

> 本文是一次**亲手跑过的实验**的完整记录，不是设想、不是演示数据。
> 与 OBSERVABILITY.md 的关系：那份是设计图与操作手册；本文是 2026-11-16 的一次真实开机记录。
> 本文不修改 OBSERVABILITY.md 的任何承诺；它只在上面加注一个现场。

## 1. 环境指纹（全部实敲）

| 项 | 值 |
|---|---|
| 操作系统 | Windows 11（PowerShell 7） |
| 宿主机局域网 IP | 192.168.1.5（`Get-NetIPAddress` 实测：vEthernet WSL 192.168.144.1 / 有线 192.168.1.5 / Loopback 127.0.0.1） |
| Docker Desktop | `com.docker.backend.exe` PID 12868，占用 **127.0.0.1:8000**（归属：career-os-ai-service，另一个项目，uvicorn；`server: uvicorn` + `x-request-id` + `traceparent`） |
| 本仓库进程 | `python -m api.server`（`.venv`，PID 13896 首启 → PID 10724 本轮复启），绑 **0.0.0.0:8000** |
| Prometheus | `prom/prometheus:v3.3.1`，容器 `specproof-phase0-prometheus-1`，绑 0.0.0.0:9090 |
| 当日时间戳 | UTC 2026-11-15T16:29Z ≈ 北京时间 2026-11-16T00:29Z |

## 2. 端口 8000 的三分真相

| 地址 | 回答者 | 响应特征 |
|---|---|---|
| `127.0.0.1:8000/health` | career-os-ai-service（PID 12868） | `{"status":"ok","db":true,"llm_provider":"openai_compat","llm_ready":true,"build_sha":"dev"}` |
| `192.168.1.5:8000/health` | **本仓库**（绑 0.0.0.0） | `{"status":"ok","mysql":true,"redis":true,"agent_jobs":true}` |
| `0.0.0.0:8000`（curl） | 不可用 | Windows 不可路由 `0.0.0.0`；netstat 只显示监听 |

## 3. 本仓库服务的实测序列（全部成功）

1. `curl http://192.168.1.5:8000/health` → `{"status":"ok","mysql":true,"redis":true,"agent_jobs":true}`
2. `GET /` → HTTP 200（1490 bytes，`<html lang="zh-CN">`，正是本仓库构建产物的 SPA）
3. `GET /manual` → HTTP 200（1490 bytes，同一 SPA，服务端 fallback 生效）
4. `GET /metrics` → Prometheus text exposition：`specproof_up 142.0`、`specproof_http_requests_total 4`、`specproof_redis_request_seconds_ping` histogram（含 `_sum 0.1038` / `_count 1`，第一次连 Redis 的真耗时）
5. 并发压测 `scripts/stress_smoke.py --target http://192.168.1.5:8000`：
   - 第 1 组：48 并发 × 2 req × 2 轮 — **96/96 ok，0 err，p99 440ms → 175.8ms**
   - 第 2 组（本轮复启后）：24 并发 × 2 — **48/48 ok，0 err，p99 587.0ms**
   - （此前更早一组：72 并发 ×2 轮共 192 req，0 err；`/metrics` 计数器从 4 → ~197 印证）
6. 压测后从 Prometheus 查询 `specproof_http_requests_total{job="local-host-api"}`：counter 从 5 → **55**，48 个新请求全部计入 ✅
7. **Fail-closed 认证实测**（未设 `SPECPROOF_API_KEY`）：
   - `GET /api/v1/llm/usage/summary` → **HTTP 503**，`{"detail":"API key not configured… The API refuses to accept jobs without authentication."}`
   - `GET /api/v1/admin/users` → **HTTP 503**，`{"detail":"Multi-tenant auth is not enabled…"}`
   - `GET /api/v1/health` → **HTTP 503**（同上 fail-closed）
   - 即：**无密钥 = 拒绝服务**，从不「开着门」。

## 4. Prometheus 对账（改前 → 改后）

**改前**（`infra/prometheus/prometheus.yml` 只有生产编排目标）：
10 个 target 中 **2 up**（`prometheus` 自抓、`rabbitmq:15692/metrics/per-object` ✅），**7 down**（`api` / `worker` / `outbox-relay` / `notify-relay` / `invoice-cron` / `otel-collector` / `specproof-edge` — 全部 `lookup … no such host`，因为 phase0 网络里没有它们）。

**改动**（本仓库，随本次提交入库）：新增 `local-host-api` job，注释中写明：
- `host.docker.internal:8000` 在本机指向 127.0.0.1，被 career-os-ai-service 占用（容器内实测返回 404）——**不能用**；
- 宿主网关 172.20.0.1 直连本进程被拒（应用绑 0.0.0.0，不响应容器网关 IP）——**不能用**；
- 故钉死宿主机局域网 IP：**192.168.1.5:8000**；换机器改这一行；完整应用栈里仍走 `api:8000`，本目标不替代它。

**改后**（`docker restart specproof-phase0-prometheus-1`，20 秒后对账）：

| job | scrapeUrl | health |
|---|---|---|
| prometheus | http://localhost:9090/metrics | **up** |
| rabbitmq | http://rabbitmq:15692/metrics/per-object | **up** |
| **local-host-api** | http://192.168.1.5:8000/metrics | **up** |
| api | http://api:8000/metrics | down (预期) |
| worker | http://worker:9100/metrics | down (预期) |
| outbox-relay | http://outbox-relay:9101/metrics | down (预期) |
| notify-relay | http://notify-relay:9102/metrics | down (预期) |
| invoice-cron | http://invoice-cron:9103/metrics | down (预期) |
| otel-collector | http://otel-collector:8889/metrics | down (预期) |
| specproof-edge | http://specproof-edge:8090/actuator/prometheus | down (预期) |

**真实时序证据**（`/api/v1/query`，改后立即抓取）：
- `specproof_up{job="local-host-api"}` = **67.9**（进程 uptime 秒）
- `specproof_http_requests_total{job="local-host-api"}` = **5**（启动自检后）
- 再压一次 48 请求 → 18 秒后复查 = **55**
- `specproof_redis_request_seconds_ping_count` = 1（App 存活后自检 Redis 一次）

## 5. 明确没发生的事（防误读）

- 应用栈（api/worker/outbox-relay…）**一个都没有在 compose 网络里起过**；7 个 down target 是「正确的 down」，不是失败。
- 127.0.0.1:8000 的答案永远是 career-os-ai-service，**不是本仓库**。本仓库的答案在 192.168.1.5:8000（或本机 LAN 下的任意绑定地址）。
- `local-host-api` target **只在本机应用跑起来时才 up**；进程退出后 Prometheus 会将其标为 down 并继续重试 —— 这是设计行为，不是故障。
- 本实验未触碰 OBSERVABILITY.md 的任何部署承诺；Alertmanager 仍为 null receiver；Grafana 仍未证明过 SLO 看板。
- 未配置 `SPECPROOF_API_KEY` → 任何业务端点无法被调用，本次只证明了「存活 + 指标 + 假闭」。
