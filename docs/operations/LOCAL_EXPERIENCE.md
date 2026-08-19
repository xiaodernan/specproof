# SpecProof 本地体验一键启动指南 (LOCAL EXPERIENCE)

> 面向: 面试演示 / 试用客户 / 自己验证产品。一条命令把"基础设施 + 后端 + 前端 + 演示数据"全部拉起来,
> 打开浏览器就是一场可点击的完整演示, 而不是一个空列表。

## 0. 这条命令是什么

```powershell
pwsh scripts\start_local.ps1
```

它会按顺序完成五件事 (全程幂等, 可反复执行):

1. **基础设施** — `docker compose -f compose.phase0.yml up -d` 并等待健康检查
   (MySQL / MongoDB / Elasticsearch / Redis / RabbitMQ / MinIO; MySQL 必须就绪, 其余降级放行);
2. **后端** — 启动 FastAPI (`python -m uvicorn api.server:app`, `127.0.0.1:8000`,
   后台运行, 日志 `.local\api.log`); 已运行时跳过;
3. **演示数据** — `python scripts\seed_demo.py` 幂等播种 (详见 §6 播种设计);
4. **前端** — `npm run dev` (Vite, `localhost:5173`, 日志 `.local\web.log`; 首次自动执行 `npm install`);
   已运行时跳过;
5. **打印入口** — Web URL、API 文档 URL、演示登录密钥、停止命令与"先点什么"。

> 顺序说明: 任务书里播种在 API 之前, 实际执行时我们把 **API 先拉起来再播种** ——
> 因为【演示】Agent 任务的标题与事件只存在于 API 进程里, 必须走真实的
> `POST /agent/jobs` 才能让演示任务带上标题; 这是有意为之, 已在代码注释与 §6 中记录。

停止: `pwsh scripts\stop_local.ps1` (停前后端进程树 + `compose down`, **数据卷保留**)。

## 1. 前提条件

| 依赖 | 版本要求 | 检查方式 |
|---|---|---|
| Docker Desktop | 4.x (Windows 用 WSL2 后端), 内存建议 ≥ 8GB | `docker info` |
| Node.js + npm | Node ≥ 18 (推荐 20/22), npm ≥ 9 | `node --version` |
| Python | **3.12** (`pyproject.toml` 要求 `>=3.12`) | `python --version` |
| Python 依赖 | `python -m pip install -e ".[dev]"` (一次性) | 脚本会自检并提示 |

前端依赖不用手装: `start_local.ps1` 检测到 `apps/web/node_modules` 不存在时会自动 `npm install`。

**端口占用清单** (这些端口必须空闲, 或允许 compose/脚本改变端口):

- 3306 MySQL、27017 MongoDB、9200 Elasticsearch、6379 Redis、5672 RabbitMQ、
  9000/9001 MinIO (compose 端口);
- 8000 FastAPI、5173 Vite (脚本启动, 端口被占时脚本会跳过并提示)。

⚠️ 本机如果已经装了原生 MySQL/ES/Redis 等并占用了上述端口, 请先停掉它们或改端口
(见 §8 故障排查)。

## 2. 启动

```powershell
cd <repo 根目录>          # 也可在任意目录执行, 脚本按自身位置解析路径
pwsh scripts\start_local.ps1
```

**预期输出** (首次拉镜像需要几分钟; 已启动过的环境十几秒内就绪):

```text
==> 预检: 检查本机工具链
    [ok] docker / python / node / npm 均可用
==> 检查 Docker Desktop
    [ok] Docker 可用
==> 启动基础设施容器 (compose.phase0.yml)
==> 等待容器健康检查 (首次需拉取镜像, 可能需要几分钟)
    [ok] MySQL (specproof-mysql) 已就绪
    [ok] Elasticsearch (specproof-elasticsearch) 已就绪
    [ok] Redis (specproof-redis) 已就绪
    [ok] MongoDB (specproof-mongodb) 已就绪
    [ok] RabbitMQ (specproof-rabbitmq) 已就绪
    [ok] MinIO (specproof-minio) 已就绪
==> 配置 API 环境变量 (演示密钥, 仅本机演示用)
    [ok] Agent 任务存储: MySQL (与 API 相同)
==> 启动 FastAPI (uvicorn api.server:app -> http://127.0.0.1:8000)
    [..] API 启动中 (日志: .localapi.log) ...
    [ok] API 就绪: http://127.0.0.1:8000/health
==> 播种演示数据 (幂等, 可重复执行)
[seed] 验证任务(演示历史): 新建 3, 已存在 0 (存储: MySQL — 与 API 相同)
[seed] Agent 任务: <uuid> 【演示】修复 double 函数 — created via POST /agent/jobs — 状态: AWAITING_APPROVAL
==> 启动前端 (Vite dev server -> http://localhost:5173)
    [..] Vite 启动中 (日志: .localweb.log) ...
==> 全部就绪

  Web 前端   : http://localhost:5173           <- 从这里开始
  API 文档   : http://127.0.0.1:8000/docs
  登录密钥   : specproof-local-demo-key   (登录页选择 X-API-Key)
  日志       : .localapi.log / .localweb.log
  停止       : pwsh scriptsstop_local.ps1
````

再次执行 `start_local.ps1` 时: 容器/进程均"已在运行 → 跳过",
种子输出变为 `新建 0, 已存在 3`, Agent 任务显示 `already exists` —— 不会产生任何重复数据。

## 3. 打开什么

| 入口 | URL | 说明 |
|---|---|---|
| **Web 前端** | http://localhost:5173 | Vite dev server, 代理 `/api`、`/agent`、`/jobs` 等到 8000 |
| **API 文档** | http://127.0.0.1:8000/docs | Swagger UI, 全部端点 (需要 X-API-Key 的端点会标出) |
| 健康检查 | http://127.0.0.1:8000/health | `{"status":"ok","redis":true}` |
| 依赖健康 | http://127.0.0.1:8000/api/v1/health | 6 个依赖的逐项延迟 (Web 内"健康"页) |

**登录**: 打开 Web 后出现登录页, 选择 **X-API-Key** 模式, 粘贴:

```text
specproof-local-demo-key
```

密钥只在 sessionStorage 中, 随每次请求以 `X-API-Key` 头发送; 后端 fail-closed,
密钥错误时所有数据接口 401/拒绝 (SSE 用 `?key=` 查询参数, 与旧 dashboard 一致)。
这只是一个**本机演示密钥** (脚本硬编码、仅用于本地体验), 生产部署必须配置自己的 `SPECPROOF_API_KEY`。

## 4. 点击之旅

### 4.1 验证流: 新建验证 → 矩阵 → 证书

1. **总览 Dashboard** — 登录后落在总览页: 任务总数、按状态分布 (VERIFIED ×2 / BLOCKED ×1)、
   24 小时时间线、最近任务列表 —— 全部来自 MySQL 真实聚合。
   全新环境: 总数就是 3 (三条演示任务); 已有历史数据的开发机: 总数更多,
   3 条【演示】任务按创建时间排在**最近任务列表顶部**。
2. **任务列表 Jobs** — 侧栏"任务": 3 条【演示】任务 (`demo/spring-backend` `base → head-v1` 等)。
   新建验证: 页面内提交 `repo_path / base_ref / head_ref / spec_path`
   (`POST /jobs` 202 → QUEUED)。见 §7 已知限制: 一键启动不含 worker, 新任务会停在 QUEUED,
   演示流建议直接点预置任务。
3. **任务详情 JobDetail** — 点进 **【演示】AUTH 越权回归** (BLOCKED):
   - *概览*: 状态/引用/提交时间;
   - *阶段 Stages*: 从 Redis 流回放的 7 个阶段 (intake → compile_contracts → run_differential →
     review_court → build_matrix → create_capsule → publish_report, 全部 completed);
   - *Findings*: 1 条 **BLOCKER** AUTH-01 (runtime_diff, confidence 0.97) ——
     "head-v1 移除 @PreAuthorize, 匿名调用 200 vs 基线 401, H2 取证邮箱被改写";
   - *证书 Certificate*: 拒绝通知 (Rejection Notice) —— 只有全部契约 PASS 才会发 Merge Certificate,
     拦截任务永远是拒绝通知, 这正是产品的诚实契约。
   - Findings 行可下载 **Bug Capsule** zip (种子生成的演示胶囊, 内容自述"未经过真实差分执行")。
4. **需求矩阵 Matrix** — 侧栏"需求矩阵": 选择 AUTH 越权回归, 看到 AUTH-01 FAIL / AUTH-02 PASS
   的需求-证据矩阵; 换一条 VERIFIED 任务 (【演示】邮箱变更事件追踪) 看全 PASS 矩阵。
5. **证书** — 打开一条 VERIFIED 任务的详情 → 证书页: 真正的 Merge Certificate
   (subject/commit_sha/requirements_digest/evidence_digests/toolchain, 由 `evidence.certificate`
   真实构建器生成, 未签名 —— 见 §7)。
6. 顺路可看: **契约中心 Contracts**、**评测 Eval** (读仓库内持久化评测报告)、**健康 Health**
   (6 依赖逐项延迟, 全部绿色)。

### 4.2 Agent 流: 新建任务 → 计划 → 工具流 → 门禁 → accept

1. **Agent 总览** — 侧栏"Agent": 已有 1 条 **【演示】修复 double 函数**, 状态
   **等待计划审批 AWAITING_APPROVAL** —— 这是种子留下的"进行中"任务, 计划已就绪, 等你审批。
2. **计划 Plan** — 点进任务 → 计划页: 4 步计划
   (定位实现 → 修复符号判断 → 补边界测试 → 回归验证), 逐条 **approve**;
   全部批准后任务进入 **执行中 EXECUTING** (状态机: PLANNING → AWAITING_APPROVAL → EXECUTING)。
3. **门禁 Gates** — 门禁页: 写备注 → **通过门禁 Approve gate** → 任务 **COMPLETED**;
   拒绝则 FAILED。每一步决定都会留下审批记录 (审批 Approval 页可见)。
4. **新建任务** — Agent 总览"新建任务"向导 4 步 (仓库 → 需求 → 门禁 → 提交) →
   `POST /agent/jobs` → 跳转到新任务详情, 事件流里出现 "Job created"。
   ⚠️ 一键启动不含 Agent 执行 worker, 新任务的计划不会自动生成 (见 §7)。
5. **工具流/事件/编辑/Diff** — 任务详情里的工具流 (SSE)、事件日志、编辑记录、结构化 Diff
   都来自 API 进程内的事件日志; 种子任务只有创建事件与你的审批事件 —— 这是诚实的,
   不是缺页 (原因见 §7)。

### 4.3 登录 / 租户

- **默认 (单租户 legacy 模式)**: `SPECPROOF_AUTH_ENABLED` 未设置, 登录页只需 X-API-Key;
  侧栏"身份"入口按 legacy 规则显示, 管理端点返回 503 (行为与旧部署逐字节一致)。
- **可选: 打开多租户身份 (工业化阶段 1)**: 启动前设置环境变量再启动 API:

  ```powershell
  $env:SPECPROOF_AUTH_ENABLED = "true"
  $env:SPECPROOF_IDENTITY_URL = "sqlite:specproof_identity.db"   # 或 mysql://user:pass@host/db
  $env:SPECPROOF_TOKEN_HMAC_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
  python -m api.identity.cli init-admin admin@example.com        # 创建 default 租户 + admin
  python -m api.identity.cli mint-token <user_id>                # 生成 show-once sp_* token
  ```

  然后用 `sp_` token 登录 Web: 侧栏出现"身份"页 (租户/用户/Token/RBAC 审计),
  TenantSwitcher 可切换已保存的 token。没有 HMAC key 时 mint 拒绝执行 —— 没有默认密钥, fail-closed。

## 5. 预期视觉 (验收清单)

- [ ] 总览: 3 条【演示】任务 (全新环境即总数 3; 有历史数据的机器上排最近任务顶部),
  状态徽标 VERIFIED/BLOCKED, 时间线非空, 失败率/拦截率非 N/A
- [ ] 任务列表: 每条演示任务显示 repo 与 `base → head` 引用
- [ ] AUTH 任务: 阶段时间线 7 节点全绿; Findings 1 条 BLOCKER; 证书页=拒绝通知; 胶囊可下载
- [ ] 需求矩阵: FAIL/PASS 着色行
- [ ] Agent: 演示任务可审批计划 → EXECUTING → 门禁通过 → COMPLETED, 审批记录可查
- [ ] 健康页: mysql/mongodb/elasticsearch/redis/rabbitmq/minio 六项全部 ok + 延迟
- [ ] API 文档 `/docs` 可打开, 401/422 信封格式可见

## 6. 播种设计 (seed_demo.py 为什么这么写)

任务书要求"用 API 读取的同一个存储, 优先 MySQL, 并在读代码后决定播种途径"。读完
`api/routes/jobs.py`、`agent_console.py`、`storage/mysql.py`、`storage/agent_jobs.py` 后的决定:

| 数据 | 途径 | 原因 |
|---|---|---|
| 3 条终态验证任务 (+contracts/findings/summary/Redis 阶段流/证书/胶囊) | **直写 API 读取的同一个 MySQL 存储** | `POST /jobs` 只会创建 QUEUED 任务 + outbox 事件; **没有任何 API 能把历史任务置为终态或写矩阵** —— 伪造一个端点或假装任务跑过都不诚实, 直写存储是唯一诚实路径。写入用的是 `storage.mysql` 自身的方法与列纪律 (`insert_job/insert_contract/insert_finding/save_job_summary`, 迁移先 `ensure_tables()`) |
| 1 条 Agent 任务 | **先 `POST /agent/jobs` (真实 API), 计划再经同一个 durable store 附上** | Agent 任务的标题/事件存在 API 进程里, 只有走真实 POST 标题才显示; 而"设置计划"没有 API 端点, 所以计划通过 `SPECPROOF_AGENT_JOBS_URL` 选择的同一个存储 (MySQL 优先, SQLite 回退) 附加 —— 与 API 完全一致的 fail-closed 选择逻辑 |
| 证书/拒绝通知 | `evidence.certificate` 的 `issue_certificate` / `build_rejection_notice` | 与 CLI verify 流程完全相同的构建器; VERIFIED 全 PASS 才签发, BLOCKED 只发拒绝通知 |
| 建表 (schema) | 种子先按版本化迁移建表 (`infra/mysql/migrations/*.sql` + `schema_migrations` 记账, 与 `storage.migrations.MigrationRunner` 完全相同的文件与记账表) | API 启动时不做迁移; 而原 runner 的分句会把 0005/0006 注释里的分号切成非法 SQL (全新库上实测 1064 报错), 种子内置了"先去注释行、再按分号分句"的安全分句器, 修复后 0001→0006 全部应用成功 (实测) |
| 胶囊 zip | 真实 zip 文件 (`capsules/`), 内容自述为演示产物 | API 会校验 zip magic bytes; 没有真实管道执行, 就不伪装成真实证据 |

**幂等键**: 验证任务用固定 `uuid5(NAMESPACE_URL, "specproof-demo:<key>")` 作为 job/finding/contract id;
Agent 任务用 `sha256(spec_text)` 在 durable store 中匹配; 证书/胶囊/阶段流都按"存在即跳过"。
所以重复执行 `seed_demo.py` 或整个 `start_local.ps1` 都不会产生重复。

**回退**: MySQL 未就绪时验证任务部分降级为警告并跳过 (不假装成功 —— API 本身此时也返回 503);
Agent 任务存储回退到 SQLite `.local\specproof_agent_jobs.db`。种子数据里没有任何密钥/密码,
单元测试逐 payload 断言 secret 形状内容为零。

## 7. 已知限制 (诚实的边界)

1. **一键启动不含 worker 与 outbox relay**。这是任务书明确的进程范围 (API + 前端)。
   后果: 新建的验证任务会停在 QUEUED, 不会进入真实管道; 要跑真实验证请用 CLI
   (`python -m cli.specproof.main verify ...`) 或另行启动 `python -m agent.worker` + relay。
2. **Agent 任务没有执行 worker**: 计划由种子提供; 用户新建的 Agent 任务停在 PLANNING,
   工具流为空。审批→执行→门禁的状态机流转是真实的 (真实 API 端点), 执行动作本身没有
   worker 去做 —— 这是产品当前的车道边界, 不是演示造假。
3. **演示数据是"真实格式的演示内容"**: 矩阵/证书/胶囊的格式与真实管道完全一致,
   但未经过真实差分执行; 所有内容带【演示】标记, 胶囊自述"未经过真实差分执行"。
4. **证书未签名**: 种子证书只有 SHA-256 digest, 没有 Ed25519 签名
   (签名需要配置密钥, 计划 Phase 1+; 与产品现状一致)。
5. **Agent 控制台的事件/审批/标题是 API 进程内存态** (产品设计): API 重启后,
   种子任务的事件数归零 (durable 计划/结果仍在)。这是控制台的车道现状。
6. **compose 文件在仓库根目录** (`compose.phase0.yml`), 不是 `infra/` —— 脚本与文档都按实际位置引用。
7. **演示密钥是脚本内置的本机演示值**, 不是生产安全边界; 生产必须自配 `SPECPROOF_API_KEY`。
8. **端口变化**: compose 的端口可用环境变量 (如 `MYSQL_PORT`) 覆盖, 但 storage 的默认值
   对齐 compose 默认端口; 改动后需同步设置 `MYSQL_*`/`REDIS_*` 等环境变量。

## 8. 故障排查

| 现象 | 原因与处理 |
|---|---|
| `Docker 不可用` | Docker Desktop 未启动 → 启动后重跑 (脚本会从上一步继续, 不重复播种) |
| `docker compose up 失败` | 端口被占 (3306/9200/6379/5672/9000/27017): 本机原生 MySQL/ES/Redis? 停掉或改 `MYSQL_PORT` 等 env 后重跑 |
| 首次启动很慢 | 首次拉取 6 个镜像 (ES 约 1GB): 属正常; 之后秒级。ES 健康检查有 60s start_period, 耐心等脚本输出 |
| `API 在 90 秒内未就绪` | 看 `.local\api.log`; 常见: 未执行 `pip install -e ".[dev]"` (缺 fastapi/uvicorn), 或 MySQL 未健康 |
| `端口 8000/5173 已被其他进程占用` | 脚本会跳过并警告; 用 `stop_local.ps1` 只停自己 PID 记录的进程, 不会误杀他人进程 —— 手动处理占用者后重跑 |
| `缺少 docker/python/node/npm` | 装好后加入 PATH, 重跑 |
| `npm install 失败` | 网络/代理问题; 删除 `apps/web/node_modules` 后重跑 |
| 前端打开但数据 401 | 登录页密钥不对; 重新粘贴 `specproof-local-demo-key` (或浏览器 devtools 看 `X-API-Key` 头) |
| 种子警告 MySQL 未就绪 | `docker ps` 查 `specproof-mysql` 健康; 数据卷损坏时 `down -v` 重置 |
| 想彻底清空演示数据 | `docker compose -f compose.phase0.yml down -v` + 删除 `.local\specproof_agent_jobs.db` 与 `reports/merge-certificate-*.json`、`capsules/capsule-*.zip` |

## 9. 交付物清单

| 文件 | 说明 |
|---|---|
| `scripts/start_local.ps1` | 一键启动 (幂等), 日志 `.local/api.log` / `.local/web.log` |
| `scripts/stop_local.ps1` | 停前后端进程树 + `compose down` (数据卷保留) |
| `scripts/seed_demo.py` | 幂等演示播种 (3 验证任务 + 1 Agent 任务; MySQL 优先 / SQLite 回退; ruff + mypy --strict 全绿) |
| `tests/unit/test_seed_demo.py` | 播种幂等性 (SQLite 回退跑两遍 → 相同数量、零重复) + 无密钥断言 |
| `docs/operations/LOCAL_EXPERIENCE.md` | 本文档 |
| `.local/.gitignore` | 运行时目录 (日志/PID/回退库) 永不入库 |
