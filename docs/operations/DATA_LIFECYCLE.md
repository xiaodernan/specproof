# SpecProof 数据生命周期操作手册 (DATA_LIFECYCLE)

> 依据: 工业化商业化终极开发指南 §14 任务 14 (数据保留/删除/导出/备份恢复 + 一次不依赖 Docker 的文档演练) · §15.3 (数据删除、备份恢复有可执行手册) · §15.4 (发布前恢复演练)。
> 与 RUNBOOK.md 的关系: 本文把 RUNBOOK §5 (备份)、§6 (故障)、§9 (冒烟) 的数据操作细化为可执行的保留/删除/导出/备份恢复手册; 两文数字如有冲突, 以本文为准并同步修改 RUNBOOK。
> 审计/演练日期: 2026-08-19 (工作树 feature/interview-hardening)。
> 2026-08-20 补充 (backlog #10 ES 投影删除清理): storage/elasticsearch.py 新增 delete_projection(tenant_id=/job_id=) 与 count_projection_docs(tenant_id=/job_id=) (逐文档删除, 幂等, 索引/文档不存在返回 0); §1/§2.4/§3.4/§3.6/§7 的 ES 条目同步更新。

状态标注约定 (本仓库任务 15 制度):

- ✅ 已实现 — 代码/迁移中有对应实现, 出处可查。
- 📝 已演练 (无 Docker) — 今日完成文档级桌面演练: 逐条对照源码/迁移/compose 走查, 命令语法与对象名核对, 宿主机工具可用性实测; 未对真实存储执行。
- ⏳ 待基础设施 — 需要真实 MySQL/MongoDB/MinIO/ES/Redis/RabbitMQ 实例才能执行, 或需要尚未实现的自动化 (cron/快照/版本控制)。

## 1. 数据类与存放位置总览

| 存储 (compose 服务) | 数据类 | 位置/集合/索引/键 | 租户维度 | 事实来源 (代码) |
|---|---|---|---|---|
| MySQL specproof-mysql (3306, 库 specproof_phase0) | 验证任务、Outbox、审计、Finding、Contract、能力探测、租户/用户/Token、Agent 任务、对象元数据、计费 | 表: verification_jobs / outbox / audit_logs / findings / contracts / provider_capabilities / tenants / users / api_tokens / agent_jobs / object_metadata / object_contracts / billing_plans / billing_subscriptions / usage_ledger / invoices / schema_migrations | verification_jobs.tenant_id, users.tenant_id, billing_subscriptions/usage_ledger/invoices.tenant_id, audit_logs.attempted_tenant; contracts/findings 经 job 关联 | storage/mysql.py, storage/identity.py, storage/agent_jobs.py, storage/object_metadata.py, storage/billing.py, infra/mysql/migrations 0001-0007 |
| MongoDB specproof-mongodb (27017, 库 specproof_phase0) | Agent 断点、差分运行产物、证据包 | 集合: agent_checkpoints / differential_runs / evidence_packs (job_id 索引) | job_id 关联 | storage/mongodb.py |
| MinIO specproof-minio (9000/9001) | 工具报告、Bug 胶囊、HTML 报告 | Bucket: specproof-tool-reports / specproof-bug-capsules / specproof-html-reports (对象按 job 组织) | job_id 路径前缀 | storage/minio.py |
| Elasticsearch specproof-elasticsearch (9200) | 仓库符号/代码检索索引 (BM25+向量) | 单索引 specproof-code-phase0 (按 repo 字段隔离) | repo (主隔离键) + tenant_id 打标 (W84); job_id 为可选打标 (backlog #10, 写入侧传参才存在) | storage/elasticsearch.py |
| Redis specproof-redis (6379) | 进度/流/租约/预算/锁/缓存/幂等键 — 全部带 TTL, 无永久业务状态 | 键前缀见 §2.5 | job_id 键内嵌 (无 tenant 列) | storage/redis.py |
| RabbitMQ specproof-rabbitmq (5672) | 任务管道 | 队列 q.p1.verify.job (+ .dlq/.retry 后缀) + 4 条 phase0 兼容队列 (q.phase0.contract.compile / static.scan / differential.run / finding.replay) | 无 (队列无租户维度) | storage/rabbitmq.py |

## 2. 保留策略矩阵 (retention matrix)

### 2.1 MySQL (业务事实源, 默认永久)

| 数据类 | 保留策略 | 清理手段 | 状态 |
|---|---|---|---|
| verification_jobs (10 态状态机, 含 tenant_id) | 永久 — 验收证据与审计主体 | 无自动化归档; 如需收缩: 仅清理终态 (VERIFIED/BLOCKED/FAILED/ERROR/STALE) 且 > 180 天, 关联 findings/object_metadata 一并归档 | ⏳ 待基础设施 (无自动化) |
| outbox | 未发布行永久保留 (at-least-once 的根基); 已发布行 > 7 天可删 | DELETE FROM outbox WHERE published_at IS NOT NULL AND published_at < NOW() - INTERVAL 7 DAY | ⏳ 待基础设施 (无自动化) |
| audit_logs | 永久 (合规与跨租户取证; attempted_tenant 审计在此) | 不清理 | ✅ 已实现 (写入) |
| findings / contracts | 永久; contracts 为追加式 (id,version) 不可就地改 | 不清理 | ✅ 已实现 (写入) |
| provider_capabilities | 可重建 (lazy probe 重跑即重建); 30 天滚动足够 | DELETE FROM provider_capabilities WHERE updated_at < NOW() - INTERVAL 30 DAY | ⏳ 待基础设施 |
| tenants / users / api_tokens | 与租户生命周期一致; 撤销 token 即时删行 | 见 §3 租户删除 | ✅ 已实现 (revoke_token) |
| agent_jobs (含 accept_json/plan_json/progress_json) | 永久; 可选 180 天归档 (终态) | 无自动化 | ⏳ 待基础设施 |
| object_metadata / object_contracts | 与 MinIO 对象同生共死 (digest 校验依据) | 随 job/租户删除 (见 §3) | ✅ 已实现 (写入) |
| billing_plans / billing_subscriptions / usage_ledger / invoices | 永久 (发票对账 total=Σline_items 需可重建); usage_ledger 可归档 > 13 个月 | 无自动化 | ⏳ 待基础设施 |
| schema_migrations | 永久 | 不清理 | ✅ 已实现 |

### 2.2 MongoDB

| 集合 | 保留策略 | 清理手段 | 状态 |
|---|---|---|---|
| agent_checkpoints | 短期 — 仅用于崩溃续跑; job 终态后可清理 | deleteMany({job_id: ...}) | 📝 已演练 (命令级, 未执行) |
| differential_runs | 与 job 同生命周期 (证据) | deleteMany({job_id: ...}) | 📝 已演练 (命令级) |
| evidence_packs | 与 job 同生命周期 (MinIO sha256 交叉核验链) | deleteMany({job_id: ...}) | 📝 已演练 (命令级) |

### 2.3 MinIO (对象存储)

| Bucket | 保留策略 | 清理手段 | 状态 |
|---|---|---|---|
| specproof-tool-reports / specproof-bug-capsules / specproof-html-reports | 与 job 同生命周期; 证书/胶囊属证据核心, 租户存在期间永久 | mc rm --recursive --force <bucket>/<job 前缀> | 📝 已演练 (命令级, 未执行) |

### 2.4 Elasticsearch

| 索引 | 保留策略 | 清理手段 | 状态 |
|---|---|---|---|
| specproof-code-phase0 (单索引, 全仓库共享) | 可重建数据 (从仓库符号重索引); 保留最新快照即可 | delete_repo = 整索引删除+重建; 代码级清理 delete_projection(tenant_id=/job_id=) = 搜索+逐文档 bulk delete (避开 delete_by_query 的 Windows 原生崩溃), 幂等; count_projection_docs 供核对; 无 ILM/无 snapshot | ✅ 已实现 (delete_repo / delete_projection / count_projection_docs); ⏳ 待基础设施 (ILM/snapshot/滚动) |

### 2.5 Redis (全 TTL, 无永久业务状态; maxmemory 256mb + allkeys-lru 兜底, compose 事实)

| 键族 | TTL | 数据类 |
|---|---|---|
| specproof:progress:<job_id> | 600 s | 进度 (P0.5 兼容) |
| specproof:stream:job:<job_id> | 86400 s | SSE 进度流 (MAXLEN 1000) |
| specproof:lease:job:<job_id> | 30 s | Worker 租约 |
| specproof:budget:job:<job_id> | 7200 s | LLM token 预算 |
| specproof:lock:job:<job_id> | 300 s | 互斥锁 |
| specproof:cache:model:<key> | 3600 s | LLM 语义缓存 |
| specproof:capability:<base_url_hash> | 86400 s | Provider 能力探测缓存 |
| specproof:idempotent:<event_id> | 86400 s | 事件幂等键 |

### 2.6 RabbitMQ

| 队列 | 保留策略 | 状态 |
|---|---|---|
| q.p1.verify.job / q.p1.verify.job.retry / q.p1.verify.job.dlq | 主/重试队列消息消费即删; DLQ 无 TTL 永久滞留 | ⏳ 待基础设施 (DLQ 巡查/告警无自动化) |
| 4 条 q.phase0.* 兼容队列 | 同上, 长期空转 | ✅ 已实现 (拓扑声明) |

## 3. 租户删除传播顺序 (MySQL → MongoDB → MinIO → ES → Redis + 孤儿扫描)

> 顺序理由: MySQL 是事实源, 先删才能让下游派生数据 (Mongo 证据包、MinIO 对象) 失去"主"; 检索索引 (ES) 是派生物, 次之; Redis 无租户语义且全部 TTL, 最后清 + 自然过期兜底。整个过程没有事务可以跨五个存储, 因此每一步都带校验计数, 失败即停、可重入 (每步幂等)。

### 3.0 前置 (冻结与取证)

```sql
-- 1) 冻结租户 (状态机允许值 active/suspended, 见 storage/identity.py)
UPDATE tenants SET status = 'suspended' WHERE id = '<tenant_id>';
-- 2) 取证: 记录将被删除的全部 job_id (后续步骤的删除键)
--    (导出任务见 §4, 先于删除执行)
-- 3) 撤销全部 token
DELETE FROM api_tokens WHERE user_id IN (SELECT id FROM users WHERE tenant_id = '<tenant_id>');
```

### 3.1 MySQL (单事务, 先子后父)

```sql
START TRANSACTION;
-- 计费账本
DELETE FROM usage_ledger   WHERE tenant_id = '<tenant_id>';
DELETE FROM invoices       WHERE tenant_id = '<tenant_id>';
DELETE FROM billing_subscriptions WHERE tenant_id = '<tenant_id>';
-- 对象元数据 (与 MinIO 对象同删)
DELETE FROM object_contracts WHERE object_id IN (SELECT object_id FROM object_metadata WHERE job_id IN (SELECT id FROM verification_jobs WHERE tenant_id = '<tenant_id>'));
DELETE FROM object_metadata  WHERE job_id IN (SELECT id FROM verification_jobs WHERE tenant_id = '<tenant_id>');
-- 验证域
DELETE FROM findings            WHERE job_id IN (SELECT id FROM verification_jobs WHERE tenant_id = '<tenant_id>');
DELETE FROM outbox              WHERE aggregate_id IN (SELECT id FROM verification_jobs WHERE tenant_id = '<tenant_id>');
DELETE FROM agent_jobs          WHERE job_id IN (SELECT id FROM verification_jobs WHERE tenant_id = '<tenant_id>');
DELETE FROM verification_jobs   WHERE tenant_id = '<tenant_id>';
-- 身份域
DELETE FROM users   WHERE tenant_id = '<tenant_id>';
DELETE FROM tenants WHERE id = '<tenant_id>';
COMMIT;
```

审计取舍 (如实记录): audit_logs 与 contracts 不在删除之列 — audit_logs 保留 attempted_tenant 取证历史, contracts 为追加式契约账本。若未来签署 GDPR 类"彻底删除"条款, 需为 audit_logs 增加按租户脱敏/删除的迁移, 当前**不**提供该路径, 这是有意取舍, 非疏漏。

### 3.2 MongoDB (按取证 job_id 清单, 三集合同删)

```js
db.agent_checkpoints.deleteMany({ job_id: { $in: [ /* 3.0 取证的 job_id 清单 */ ] } });
db.differential_runs.deleteMany({ job_id: { $in: [ /* 同上 */ ] } });
db.evidence_packs.deleteMany({ job_id: { $in: [ /* 同上 */ ] } });
```

### 3.3 MinIO (按 job 前缀)

```powershell
mc rm --recursive --force local/specproof-tool-reports/<job_id>/
mc rm --recursive --force local/specproof-bug-capsules/<job_id>/
mc rm --recursive --force local/specproof-html-reports/<job_id>/
# 逐个 job_id 重复; 完成后 bucket 级计数核对 (见 3.6)
```

### 3.4 Elasticsearch (tenant_id / job_id 维度)

ES 文档按 repo 隔离, 并携带 tenant_id 字段 (W84 打标); job_id 为 backlog #10 新增的**可选**打标 — 写入侧 (retrieve_repository_context 节点 / 脚本) 不传参时该字段不存在, 此时按 job_id 清理只会命中 0 条 (幂等, 不报错)。索引全仓库共享。

代码级清理 (storage/elasticsearch.py, 无需 curl): 对 §3.0 取证的每个 job_id 执行 `delete_projection(job_id=...)` 逐文档删除该 job 的投影; 租户级收尾执行 `delete_projection(tenant_id=...)` (默认租户一并命中无 tenant 打标的遗留文档)。两函数均为"搜索 + 逐文档 bulk delete", 刻意避开 delete_by_query (Windows elasticsearch-py 8.19 原生崩溃的工程事实, 与 delete_repo 注释一致), 且幂等: 索引/文档不存在返回 0, 不报错; 重复调用返回 0。完成后用 `count_projection_docs` 核对 (§3.6)。

```powershell
# 备选 (需 ES 可用): 按 repo 条件删除
curl.exe -u elastic:<密码> -X POST "http://localhost:9200/specproof-code-phase0/_delete_by_query?refresh=true" -H "Content-Type: application/json" -d '{"query":{"term":{"repo":"<repo>"}}}'
```

注意 (如实标注): index_repository / index_with_embeddings 内部仍调用 delete_repo = 整索引删除+重建 (重索引幂等性), 该路径在多租户下会连带清掉其他租户的文档 — 本车道 (backlog #10) 未改写入侧, 属既有行为, 仍记录在此。

### 3.5 Redis (显式清理 + TTL 兜底)

```powershell
# 对 3.0 取证的每个 job_id: 删除其全部键族 (见 §2.5)
redis-cli -a <密码> --scan --pattern "specproof:*<job_id>*" | ForEach-Object { redis-cli -a <密码> DEL $_ }
# 兜底: 全部键带 TTL (最长 86400s), 即使漏删 24 小时内自然过期; 无 tenant 列是当前事实, 不伪装成精确删除
```

### 3.6 孤儿扫描 (orphan scan — 删除完成后必须全零)

| 存储 | 校验 | 期望 |
|---|---|---|
| MySQL | SELECT COUNT(*) FROM verification_jobs WHERE tenant_id='<id>'; users/usage_ledger/invoices/object_metadata/agent_jobs 同类计数 | 全 0 |
| MongoDB | 三集合 countDocuments 按 job_id 清单计数 | 全 0 |
| MinIO | mc ls --recursive 三 bucket | 无该租户 job 前缀对象 |
| ES | count_projection_docs(tenant_id=/job_id=) (或 count (repo term)) | 计数全 0 |
| Redis | SCAN specproof:* 对照 §2.5 键族 | 无该租户 job 键 |

扫描结果 (每项计数) 写入 audit 记录, 与 3.0 取证清单一起归档 — 这是"删除可证明"的唯一依据。

### 3.7 不参与传播的组件 (如实标注)

RabbitMQ 队列没有租户维度: 在途消息消费到已删除 job 时 worker 按"job 不存在"自然失败进入 DLQ, 由 DLQ 巡查人工清理 (见 §2.6)。因此传播顺序不含 RabbitMQ, 但 DLQ 清理是租户删除的收尾义务之一。

## 4. 导出范围 (export scope)

租户数据导出 (删除前取证/迁移/合规), 含与不含:

**包含**: MySQL 中 verification_jobs / agent_jobs / findings / contracts / object_metadata / usage_ledger / invoices / audit_logs 的该租户行; MinIO 三 bucket 中该租户 job 对象; MongoDB differential_runs / evidence_packs。

**不包含**: Redis (纯缓存/租约, TTL 后即无); Elasticsearch (可从仓库重新索引, 导出无意义); RabbitMQ 消息 (源在 outbox); api_tokens 不导出明文 (库中仅存 hash, 导出行含 hash 属可接受); 密钥/口令类环境变量一律不导出。

```powershell
# MySQL: 逐表 --where 过滤导出 (宿主机无 mysqldump → docker compose exec, 见 §6.1-6)
docker compose -f compose.phase0.yml exec -T mysql mysqldump -u root -p"<root>" specproof_phase0 verification_jobs --where="tenant_id='<id>'" > tenant-jobs.sql
# MinIO: 镜像到归档目录
mc mirror --overwrite local/specproof-bug-capsules/<job_id>/ <导出目录>/bug-capsules/<job_id>/
# MongoDB: 按查询过滤导出
docker compose -f compose.phase0.yml exec -T mongodb mongodump --db specproof_phase0 --collection evidence_packs --query '{"job_id": {"$in": ["<job_id>"]}}' --archive > tenant-evidence.archive
```

导出物按证据链要求附 sha256 清单, 与 capsule/report 的 digest 交叉核验 (object_metadata.payload_sha256)。

## 5. 备份与恢复 (per store, 细化 RUNBOOK §5)

> RUNBOOK §5 基线: "mysqldump specproof_phase0 每日; MinIO bucket 同步到冷存储; MongoDB 至少保留 checkpoint 集合"。本文补上恢复步骤与验证。
> 宿主机现状 (2026-08-19 实测 Get-Command): mysqldump/mysql/mongodump/mongorestore/mc/rclone/redis-cli **均未安装**, docker 可用 → 所有命令以 docker compose exec 形式给出; 备选: 安装各原生客户端后用同参数直连。

| 存储 | 备份 (每日) | 恢复 | 验证 | 状态 |
|---|---|---|---|---|
| MySQL | docker compose -f compose.phase0.yml exec -T mysql mysqldump -u root -p"<root>" --single-transaction --routines --triggers specproof_phase0 > backup-YYYYMMDD.sql (再 gzip) | gunzip -c backup.sql.gz 后 docker compose exec -T mysql mysql -u root -p"<root>" specproof_phase0 < backup.sql | 表计数对比 (verification_jobs/outbox 行数) + schema_migrations 版本一致 | 📝 已演练 (命令级); ⏳ 待基础设施 (执行 + 每日 cron + binlog PITR) |
| MongoDB | docker compose -f compose.phase0.yml exec -T mongodb mongodump --db specproof_phase0 --archive --gzip > mongo-YYYYMMDD.archive.gz | docker compose exec -T mongodb mongorestore --archive --gzip --drop < mongo.archive.gz | 三集合 countDocuments 对比 | 📝 已演练 (命令级); ⏳ 待基础设施 (执行) |
| MinIO | mc mirror --overwrite local/specproof-tool-reports <冷存储>/... (三 bucket; RUNBOOK §5) | mc mirror --overwrite <冷存储>/<bucket> local/<bucket> | mc stat 抽查 + payload_sha256 与 object_metadata 核对 | 📝 已演练 (命令级); ⏳ 待基础设施 (执行 + 版本控制) |
| Elasticsearch | 策略=可重建 (从仓库重索引), 不做每日全量备份; 快照 API 为可选增强 | 重索引 (index_repository) 或 snapshot restore | count_repo_docs 对比 | 📝 已演练 (重建路径是代码事实); ⏳ 待基础设施 (snapshot 仓库) |
| Redis | **不备份** (全 TTL 缓存, 与 RUNBOOK §5 一致); 恢复=进程重启后自然重建 | — | — | ✅ 策略已定 |
| RabbitMQ | **不备份** (消息源在 MySQL outbox; DLQ 人工); 恢复=重启 + outbox_relay 补发 | — | — | ✅ 策略已定 |

备份保留: 每日 30 天滚动 + 每月 1 份归档 (12 个月)。恢复演练 (含 §15.4 的"发布前恢复演练") 必须在真实基础设施上执行 — 见 §6, 当前 ⏳。

## 6. 演练记录 (honest drill record, 2026-08-19)

### 6.1 📝 已演练 (无 Docker / 文档级)

| # | 步骤 | 演练内容与证据 |
|---|---|---|
| 1 | 数据类盘点 | 逐文件读 storage/mysql.py, identity.py, agent_jobs.py, object_metadata.py, billing.py, mongodb.py, minio.py, elasticsearch.py, redis.py, rabbitmq.py + infra/mysql/migrations 0001-0007 → §1/§2 全部条目出自代码事实, 无凭记忆条目 |
| 2 | 保留矩阵交叉核对 | TTL/索引/唯一键/状态机值与代码逐条对照 (如 Redis 八类键 TTL、contracts (id,version) 追加式、DLQ 无 TTL) |
| 3 | 租户删除顺序桌面走查 | §3 五库顺序 + 每步校验 + 孤儿扫描全零标准, 按 3.0→3.6 逐步推演两遍 (含失败停/可重入检查); 未对真实库执行 |
| 4 | 导出范围界定 | §4 含/不含清单逐项对照代码 (api_tokens 仅 hash、Redis/ES 排除理由) |
| 5 | 备份/恢复命令编排 | §5 六存储命令逐一写出并核对容器名/库名/bucket 名 (specproof-mysql 等, 见 compose.phase0.yml) |
| 6 | 宿主机工具可用性探测 | Get-Command 实测: mysqldump/mysql/mongodump/mongorestore/mc/rclone/redis-cli 缺失; docker 可用 (C:\Program Files\Docker\Docker\resources\bin\docker.exe) → 命令改 docker compose exec 形式并注明备选 |
| 7 | compose 校验 | docker compose -f compose.phase0.yml config --services exit 0 — 服务名 (mysql/mongodb/elasticsearch/redis/rabbitmq/minio) 与卷名 (mysql-data 等 6 卷) 与 §5 命令对齐 |
| 8 | Webhook 重放防护回归 (任务 11 侧证据) | tests/security/test_webhook_replay.py 13 用例本日 pytest 实测全绿 (重放矩阵: 重复 delivery 单效应/旧签名重放不重复/无效签名 401/时间戳超窗 401/缺头 401·400) |

### 6.2 ⏳ 待基础设施 (如实标注, 未执行不记为已演练)

| # | 步骤 | 阻塞条件 |
|---|---|---|
| 9 | MySQL 每日 mysqldump 实际执行 + 30 天滚动 | 需运行中的 MySQL (specproof-mysql) + 计划任务 |
| 10 | MongoDB mongodump / MinIO mc mirror 实际执行 | 需运行中的 MongoDB/MinIO + mc 客户端 |
| 11 | 备份恢复演练 (§15.4 发布前恢复演练) | 需完整基础设施 + 隔离恢复目标库 |
| 12 | 租户真实删除执行 + 孤儿扫描全零 | 需多租户数据 (含跨租户 job) + 五存储在线 |
| 13 | ES snapshot/ILM、Redis/RabbitMQ DLQ 巡查 cron | 需 ES 插件仓库 + 告警通道 |
| 14 | workspace 清理与 ES 索引滚动自动化 (RUNBOOK §5) | 需部署环境的实际磁盘/索引增长观测 |

### 6.3 演练结论

任务 14 要求的"一次不依赖 Docker 的文档演练"= §6.1 的 8 项, 今日完成, 证据为源码对照 + Get-Command 实测 + compose config exit 0。**执行级演练 (备份/恢复/删除的真实运行) 全部为 ⏳ 待基础设施** — 本机无运行中的 MySQL/Mongo/MinIO/ES/Redis 实例且原生客户端缺失, 不把"写出了命令"伪装成"跑通了恢复"。基础设施就位后, 按 §6.2 逐项执行并把本节升级为真实执行记录 (附命令输出摘录)。

## 7. 已知缺口 (honest gaps, 与 §6.2 对应)

- 无任何保留/清理自动化 (cron 或应用内回收器) — 全部靠手册。
- 租户删除无 API/脚本封装, 依赖 §3 手工步骤; 跨五库无分布式事务, 靠"校验-停止-重入"纪律。
- ES 单索引无 ILM; delete_by_query 在 Windows 崩溃 → 清理改走 delete_projection 的逐文档删除 (backlog #10), 但 job 终态/租户删除仍无自动化接线 (需写入侧传 job_id + 调用方接线), 且 index_repository 内部整索引重建在多租户下成本随 repo 数线性增长。
- audit_logs 无按租户删除路径 (有意取舍, §3.1)。
- Webhook 重放防护的去重集为进程内存 (重启即失), 签名时间戳窗口为可选加固 (GitHub 原生不发送), 未签名重放的残余风险由 tests/security/test_webhook_replay.py 中 test_unsigned_replay_with_new_delivery_documented_limitation 如实钉住。
