# SpecProof 运维手册 (Runbook)

面向单机生产部署 (Ubuntu LTS, 8 核 / 16-32 GB RAM, 200 GB SSD, 无 GPU)。
对齐 PRODUCTION_SPEC 第 14/17 节。

## 1. 组件与端口

| 组件 | 端口 | 职责 |
|---|---|---|
| FastAPI Agent Runtime (api) | 8000 | 建单/查询/SSE/仪表/指标/webhook(Python) |
| Worker | — | RabbitMQ 消费, LangGraph 执行, 状态迁移 |
| Outbox Relay (Python) | — | outbox 表 -> RabbitMQ |
| Spring Boot Control Plane | 8081 | 租户/用户/审计视图 + GitHub webhook(CP) + CP outbox 中继 |
| MySQL | 3306 | 业务事实源 (10 态状态机 + 审计 + 迁移记录) |
| Redis | 6379 | 租约/幂等/限流/进度 Stream (全 TTL) |
| RabbitMQ | 5672/15672 | 可靠任务管道 (Confirm + Manual Ack + DLQ) |
| MongoDB | 27017 | checkpoint / 复杂分析工件 |
| Elasticsearch | 9200 | 仓库符号检索 (诚实降级) |
| MinIO | 9000/9001 | 报告/胶囊/证书对象存储 |

## 2. 启动与停止

    # 基础设施 (六容器, 健康检查等待)
    docker compose -f compose.phase0.yml up -d --wait

    # 应用服务 (api + worker; SPECPROOF_API_KEY 必填否则 fail-closed)
    export SPECPROOF_API_KEY='<强随机值>'
    docker compose -f compose.phase0.yml -f compose.production.yml up -d

    # Control Plane (另开, 共享同一 MySQL)
    cd services/control-plane && ./mvnw spring-boot:run

- 数据库迁移在应用启动时自动执行 (infra/mysql/migrations/*.sql,
  schema_migrations 记录版本; 当前 0001-0004)。
- 生产必须 SPECPROOF_ENV=production — config_guard 拒绝默认口令
  (specproof_pass / replace_me) fail-fast。

## 3. 关键环境变量与 fail-closed 行为

| 变量 | 未配置时的行为 |
|---|---|
| SPECPROOF_API_KEY | /jobs 全部 503 (绝不裸奔) |
| GITHUB_WEBHOOK_SECRET | POST /webhooks/github 与 CP 端点 503 |
| SPECPROOF_SIGNING_KEY | 证书/拒绝通知不签名并明确提示 (不伪造) |
| GITHUB_APP_ID / _PRIVATE_KEY / _INSTALLATION_ID | Check Run 发布跳过 + 日志告警; 半配置抛错响亮告警 |
| LLM_API_KEY | 管线确定性降级 (与 --no-llm 同效果) |
| SPECPROOF_SANDBOX | auto: 有 Docker 用 docker, 否则 local_fallback (结果标注 mode) |
| SPECPROOF_PUBLIC_URL | Check Run details_url 链接 (可选) |

## 4. 健康与观测

- GET /health: {status: ok|degraded, redis: bool}
- GET /metrics (Prometheus): jobs_completed_total, jobs_<verdict>_total,
  jobs_processing_seconds, outbox_pending, http_requests_total 等。
- CP: GET /health (8081), actuator health/metrics。
- 日志: JSON 结构 (job_id/trace_id), worker 内每个消息都带 job_id。
- OTel: OTLP exporter (init_tracing, 服务名 specproof-api/specproof-worker)。

## 5. 日常运维

- 备份: mysqldump specproof_phase0 每日; MinIO bucket 同步到冷存储;
  MongoDB 至少保留 checkpoint 集合。
- 磁盘: 定时清理 workspace (--keep-worktrees 只在调试用);
  ES 索引按保留策略滚动。
- 沙箱镜像: 预拉 maven:3.9-eclipse-temurin-21; 拉取失败有进程级缓存
  (一次只付一次超时代价)。Docker Hub 不可达时置
  SPECPROOF_SANDBOX=local 并确认 JDK21 在宿主机可用。
- **沙箱 Maven 缓存卷必须预置 (关键)**。沙箱容器一律 --network none,
  任何依赖都只能来自命名卷 specproof-maven-cache。空卷会让差分执行
  以 "Unknown host repo.maven.apache.org" 静默失败 (Base/Head 双 1 ->
  AMBIGUOUS -> 执行级案例全部漏检)。预置方法:
  宿主机先完整跑过一次 mvnw (缓存齐全) 后执行
  `scripts/seed_sandbox_cache.ps1` (或 Linux 等价命令: 把
  ~/.m2/repository 拷入该卷 /root/.m2/repository), 并用
  `docker run --rm --network none -v specproof-maven-cache:/root/.m2
  -v <demo>:/work -w /work maven:3.9-eclipse-temurin-21 mvn -q -o test-compile`
  冒烟确认。依赖变更后需重新预置。

## 6. 故障手册

| 症状 | 判断 | 处置 |
|---|---|---|
| 建单后一直 QUEUED | outbox_pending 高 / relay 退避 | 查 RabbitMQ; 恢复后 relay 自动续发 (at-least-once) |
| job 停在 WAITING_FOR_PROVIDER | LLM 网关不可用 | 修网关后转 QUEUED 重试, 或人工 FAILED; job 不丢失 |
| MySQL 不可达 | API 503 | 恢复数据库; Outbox 保证已提交任务不丢 |
| ES 不可达 | 检索节点诚实降级 (retrieval_note) | 修复后自然恢复, 不影响判定正确性 |
| worker 崩溃 | lease TTL 到期 | 其他 worker 接管; Mongo checkpoint 从崩溃节点续跑 |
| 重复 webhook | 幂等: Python 内存 delivery 键 + CP delivery_id 唯一索引 | 无需人工处理 |
| BLOCKED job | 有 confirmed finding / unverified | 打开 dashboard job 页 -> capsule replay 复核 |
| Check Run 未更新 | GitHub App 未配置或网络失败 | 看 worker 日志 (best-effort, 不影响验收) |

## 7. 安全与密钥轮换

- 密钥只从环境变量 / Docker Secret 读取; 仓库中只有 .env.example 占位符。
- 轮换 GITHUB_WEBHOOK_SECRET: 改 secret -> 重启 api 与 CP -> GitHub App
  端同步更新 (期间 webhook 401, 不丢事件 — GitHub 会重投, 幂等兜底)。
- 轮换 SPECPROOF_SIGNING_KEY: 新证书用新公钥验证; 旧证书仍可用旧公钥
  离线验证 (in-toto 风格, 签名键与验证键分离)。
- 轮换 GitHub App 私钥: GitHub 支持多密钥共存, 新密钥激活后再删旧。
- 生产模式默认口令 fail-fast 是最后防线, 上线前必须换掉全部默认口令。

## 8. SLO 对照 (PRODUCTION_SPEC 第 14 节)

- FAST p95 <= 8 分钟 / DEEP p95 <= 25 分钟 / webhook 响应 p95 <= 1 秒;
- Job 不丢: Outbox + 幂等 + checkpoint + lease;
- 高等级 Finding 必须有证据, capsule 可重放 (replay 命令见 capsule README)。

## 9. 部署后冒烟清单

1. GET /health 返回 ok; GET /metrics 含 outbox_pending。
2. POST /jobs 创建一个 FAST job -> 观察 QUEUED->RUNNING->终态。
3. 带 --publish-check 跑一次 RELEASE -> 日志显示 Check Run 发布或明确跳过原因。
4. 重复投递同一 webhook delivery -> duplicate_delivery, 不产生第二个 job。
5. 用 docker 沙箱跑一个验证, 确认 --network none 生效 (报告 environment 段)。
