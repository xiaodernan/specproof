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

    # 应用服务 (api + worker + outbox-relay + sandbox DooD 守护进程; SPECPROOF_API_KEY 必填否则 fail-closed)
    export SPECPROOF_API_KEY='<强随机值>'
    # 首次启动前必须先预置沙箱卷 (scripts/seed_sandbox_cache.ps1, §5),
    # 并把 maven 沙箱镜像预拉进 DooD 守护进程 (§5)。
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
- **沙箱 Maven 缓存卷必须预置 (关键)**。沙箱容器一律 --network none
  且以非 root (--user 1000:1000) 运行, 任何依赖都只能来自命名卷
  specproof-maven-cache-1000 (容器内挂 /home/maven/.m2, 也是 runner 的
  默认缓存卷)。卷名由 SPECPROOF_SANDBOX_M2_VOLUME 控制; 旧卷名
  specproof-maven-cache (root 布局, 供长时全量评测等旧部署继续使用,
  需显式设置该变量才会挂载) — 不要删除或 prune 旧卷。空卷会让差分
  执行以 "Unknown host repo.maven.apache.org"
  静默失败 (Base/Head 双 1 -> AMBIGUOUS -> 执行级案例全部漏检)。预置
  方法: 宿主机先完整跑过一次 mvnw (缓存齐全) 后执行
  `scripts/seed_sandbox_cache.ps1` (该脚本只动 -1000 卷)。脚本:
  (a) 把 ~/.m2/repository 拷入卷内 /home/maven/.m2/repository 并 chown
  1000:1000; (b) 联网跑一次 demo 的 mvnw 把 Wrapper 发行版
  (apache-maven-3.9.9) 拉入卷内 /home/maven/.m2/wrapper/dists;
  (c) 在 base tag 的干净 worktree 上冒烟确认离线编译:
  `docker run --rm --network none --user 1000:1000 -e
  MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven"
  -v specproof-maven-cache-1000:/home/maven/.m2 -v <副本>:/work:ro
  -v <副本>/target:/work/target -w /work
  maven:3.9-eclipse-temurin-21 mvn -q -o test-compile`。
  依赖变更或 Wrapper 版本变更后需重新预置。

- **沙箱容器非 root / 只读源码**。sandbox/runner.py 固定
  `--user 1000:1000`、`--pids-limit 256` (SPECPROOF_SANDBOX_PIDS 可调)。
  workspace 以 `:ro` 挂载 /work, 仅 /work/target 是可写子挂载 (Maven
  输出)。注: workspace 是每次运行新建的可丢弃 worktree 副本, 非仓库
  本体。maven 镜像内没有 maven 用户, MAVEN_USER_HOME 需指向
  /home/maven/.m2 (Wrapper 把该值当 ~/.m2 本身用), Maven 本地仓库则靠
  MAVEN_OPTS=-Duser.home=/home/maven 钉住 (mvn 3.9.9 忽略
  MAVEN_USER_HOME 环境变量, JDK21 的 user.home 来自 /etc/passwd, 均已
  实测)。

- **DooD: 生产不挂宿主机 docker.sock (§12)**。compose.production.yml
  的 worker 通过 DOCKER_HOST=tcp://sandbox:2375 使用专用
  docker:dind 守护进程 (sandbox 服务, privileged, TLS 关闭, 端口
  2375 为实测值: TLS 关闭时 dind 绑 2375, 2376 是 TLS 端口)。这是
  Docker-in-Docker 而非 socket 透传, 与 §12 不冲突; 但 TCP 无认证仅限
  compose 内网使用, 不要向宿主机发布该端口。rootless 变体
  (docker:27-dind-rootless) 已实测不可用 (dockerd 启动即失败:
  "error setting up default driver: chmod /home/rootless/.local/
  share/docker/volumes: operation not permitted", 且 rootless 的
  subordinate-uid 重映射会破坏共享卷上的文件属主), 故采用 docker:dind。
  运维要点: (a) 卷桥接 — specproof-maven-cache-1000 挂在 dind 的卷存储路径
  /var/lib/docker/volumes/specproof-maven-cache-1000/_data, 使沙箱容器内的
  `-v specproof-maven-cache-1000:/home/maven/.m2` 命中预置缓存 (worker 侧
  已通过 SPECPROOF_SANDBOX_M2_VOLUME=specproof-maven-cache-1000 指定);
  (b) specproof-workspaces 卷由 worker(uid 1000)与 sandbox 共享,
  worker 的 TMPDIR=/workspaces 让 worktree 路径在 dind 侧同名可见;
  (c) 首次起 sandbox 后把沙箱镜像预拉进 dind:
  `docker compose -f compose.phase0.yml -f compose.production.yml exec
  sandbox docker pull maven:3.9-eclipse-temurin-21`;
  (d) dind 首跑会 chown 卷存储目录, 之后重跑 seed 脚本可恢复 1000 属主。

- **Outbox Relay 是生产必需组件**。compose.production.yml 的
  outbox-relay 服务 (复用 worker 镜像, `python -m storage.outbox_relay`)
  把 MySQL outbox 表行中继到 RabbitMQ — 没有它 webhook 建单会一直
  QUEUED。它暴露 :9101 (OUTBOX_RELAY_METRICS_PORT, Prometheus 抓取
  outbox-relay:9101/metrics)。api/worker 的 OTEL 链路经
  OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 汇入观测栈
  (compose.observability.yml)。

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

- 沙箱加固 (§12): 沙箱容器以 --user 1000:1000 非 root 运行, 带
  --pids-limit/--network none/--cap-drop ALL/no-new-privileges;
  源码只读挂载, 仅 target 可写; worker 与 sandbox 之间没有任何
  /var/run/docker.sock 挂载 (DooD 走 tcp://sandbox:2375, 见 §5)。
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
5. 用 docker 沙箱跑一个验证, 确认 --network none 生效 (报告 environment 段),
   并确认容器非 root 运行 (`docker inspect` 的 .Config.User 为 "1000:1000")。
