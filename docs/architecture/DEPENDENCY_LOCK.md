# 依赖锁定说明 (DEPENDENCY_LOCK) — Python / Node / JDK·Maven / Docker Compose

> 采集日期: 2026-08-19 · 分支: feature/interview-hardening · 来源: `pyproject.toml`、
> `apps/web/package-lock.json`、`ide/vscode/package-lock.json`、
> `demo/spring-backend/pom.xml` + `demo/spring-backend/.mvn/wrapper/maven-wrapper.properties`、
> `compose.phase0.yml` / `compose.production.yml` / `compose.observability.yml`。

## 0. 诚实总声明 (先读这一段)

- **Python 侧没有提交任何 lock 文件或 pip freeze 快照**。`pyproject.toml` 用
  `>=` 下限锁定直接依赖 (见 §1), 传递依赖与解析结果未被冻结。
- 因此**完整锁定审计**必须在干净虚拟环境中执行一遍安装并导出快照 (§1.3 命令),
  本文档记录的是“仓库里实际写死的版本”, 不是“审计后证明可复现的版本”。
- Node 侧有 `package-lock.json` (lockfileVersion 3), `npm ci` 可按锁文件精确安装 —
  但 `package.json` 里是 `^` 范围, 锁文件是事实上的锁定点。
- JDK/Maven 侧由 Maven Wrapper 自包含: Maven 版本与 zip 的 sha256 写死在
  `maven-wrapper.properties`, JDK 21 写死在 `pom.xml` (`<java.version>21</java.version>`);
  Maven 依赖本身无显式版本 (Spring Boot BOM 管理)。
- Docker Compose 侧镜像 tag 全部写死 (无 `latest`), 见 §4。

---

## 1. Python (`pyproject.toml`)

- 包名/版本: `specproof 0.1.0` · `requires-python = ">=3.12"` (本仓库实测运行环境 Python 3.12.10,
  见 `docs/eval/mutation-results.md` 运行环境节)。

### 1.1 运行时直接依赖 (24 项, `>=` 下限锁定)

| 包 | 锁定下限 | 备注 |
|---|---|---|
| click | >=8.1.7 | CLI |
| langgraph | >=0.4.0 | 12 节点管线 |
| langgraph-checkpoint | >=2.0.0 | checkpointer 接口 |
| openai | >=1.50.0 | Provider 客户端 |
| httpx | >=0.28.0 | HTTP |
| jinja2 | >=3.1.4 | 模板 |
| pydantic | >=2.10.0 | schema |
| pymysql | >=1.1.1 | MySQL |
| pymongo | >=4.10.0 | MongoDB |
| elasticsearch | >=8.16,<9 | **双端约束**: 客户端主版本必须匹配服务端 (compose 钉 ES 8.16.4) — 9.x 客户端会发 8.x 拒绝的头 |
| redis | >=5.2.0 | Redis |
| pika | >=1.3.2 | RabbitMQ |
| minio | >=7.2.10 | MinIO |
| pyyaml | >=6.0.2 | |
| GitPython | >=3.1.43 | 仓库操作 |
| docker | >=7.1.0 | 沙箱 |
| rich | >=13.9.0 | 终端输出 |
| python-dotenv | >=1.0.1 | 环境变量 |
| tenacity | >=9.0.0 | 重试 |
| cryptography | >=42.0.0 | Ed25519 Merge Certificate (P5) |
| bcrypt | >=4.0.0 | 本地 token secret 哈希 |
| PyJWT[crypto] | >=2.10.0 | OIDC RS256 JWKS |
| defusedxml | >=0.7.1 | surefire XML 安全解析 (工作区内容为不可信 PR 材料) |

### 1.2 开发/可选依赖

- dev (10 项): pytest>=8.3.0, pytest-asyncio>=0.24.0, pytest-cov>=6.0.0, pytest-mock>=3.14.0,
  testcontainers>=4.7.0, ruff>=0.8.0, mypy>=1.13.0, bandit>=1.8.0, responses>=0.25.0,
  httpx2>=0.1.0 (fastapi.testclient 弃用警告 backport)。
- otel (6 项, 全部 >=1.28.0 或 >=0.49b0): opentelemetry-api / sdk / exporter-otlp-proto-http +
  instrumentation-fastapi / pika / pymongo / redis / pymysql。

### 1.3 锁定快照与干净环境审计命令 (本文档记录的诚实缺口)

仓库当前**没有** `requirements*.txt` / `constraints*.txt` / `poetry.lock` / `uv.lock`。
要生成快照或做完整锁定审计:

```bash
# 1) 生成当前环境快照 (记录用, 不替代锁文件)
python -m pip freeze --all > constraints-freeze-YYYYMMDD.txt

# 2) 干净环境锁定审计 (推荐在 CI 或一次性目录执行)
python -m venv .venv-audit
.venv-audit\Scripts\pip install -e ".[dev,otel]"      # Windows PowerShell
.venv-audit\Scripts\pip freeze --all > freeze-audit.txt
```

审计结论只有从第 2 步的干净安装输出才能得出 — 本仓库尚未提交该输出, 因此
“全量依赖可复现性” 目前是**未验证**状态, 不在任何验收数字内。

---

## 2. Node

### 2.1 apps/web — 仪表盘 SPA (`apps/web/package.json` + `package-lock.json`, lockfileVersion 3)

- 名称/版本: `specproof-web 0.1.0` (React 18 + Vite 5 + TypeScript, 无外部 UI 运行时依赖)。

| 依赖 | 声明范围 | 说明 |
|---|---|---|
| react / react-dom | ^18.3.1 | 仅有的两个运行时依赖 |
| @playwright/test | ^1.62.1 | e2e |
| @testing-library/dom | ^10.4.1 | |
| @testing-library/react | ^16.3.2 | |
| @types/react / @types/react-dom | ^18.3.12 / ^18.3.1 | |
| @vitejs/plugin-react | ^4.3.4 | |
| jsdom | ^25.0.1 | |
| typescript | ^5.6.3 | |
| vite | ^5.4.11 | |
| vitest | ^2.1.9 | |

- 锁定事实: `apps/web/package-lock.json` 精确记录了全部传递依赖的 version/resolved/integrity —
  安装请用 `npm ci` (按锁文件), 不用 `npm install`。校验树: `npm ls --all`。

### 2.2 ide/vscode — Agent Console 扩展 (`ide/vscode/package.json` + `package-lock.json`, lockfileVersion 3)

- 名称/版本: `specproof-agent-console 0.1.0` · `engines.vscode: ^1.95.0`。

| 依赖 | 声明范围 |
|---|---|
| @types/node | ^22.10.1 |
| @types/vscode | ^1.95.0 |
| typescript | ^5.6.3 |
| vitest | ^2.1.9 |

- 锁定事实同上: `npm ci` 按 `ide/vscode/package-lock.json` 精确安装。

---

## 3. JDK / Maven (`demo/spring-backend` 演示项目, 自包含构建)

- **Maven Wrapper** (`demo/spring-backend/mvnw` + `.mvn/wrapper/maven-wrapper.properties`):
  - Maven 发行版: **3.9.9** — `distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip`
  - zip sha256 已钉死: `distributionSha256Sum=4ec3f26fb1a692473aea0235c300bd20f0f9fe741947c82c1234cefd76ac3a3c`
  - wrapper jar: maven-wrapper 3.3.2。
- **JDK**: **21** — `pom.xml` `<java.version>21</java.version>`; 本机实测环境 Amazon Corretto
  jdk21.0.11_10 (`docs/eval/replay-results.md` 环境节)。无需系统 Maven, mvnw 自动下载。
- **pom.xml 直接钉版本** (`demo/spring-backend/pom.xml`):
  - parent: spring-boot-starter-parent **3.4.3** (BOM 管理其余 Spring 依赖, 无显式版本)
  - testcontainers **1.20.4** (test) · springdoc-openapi-starter-webmvc-ui **2.7.0**
  - mysql-connector-j / h2: BOM 管理 (h2 为 test scope)
- 演示项目的 docker-compose: `demo/spring-backend/docker-compose.yml` (演示仓库自带, 与主栈无关)。

---

## 4. Docker Compose 服务镜像版本 (全部 tag 写死, 无 latest)

### 4.1 基础设施栈 (`compose.phase0.yml`)

| 服务 | 镜像 | 备注 |
|---|---|---|
| mysql | mysql:8.4 | 库 specproof_phase0 |
| mongodb | mongo:7.0 | |
| elasticsearch | docker.elastic.co/elasticsearch/elasticsearch:8.16.4 | 与 Python 客户端 >=8.16,<9 匹配 |
| redis | redis:7.4-alpine | maxmemory 256mb + allkeys-lru |
| rabbitmq | rabbitmq:4.0-management-alpine | 15672 管理台 |
| minio | minio/minio:RELEASE.2025-04-08T15-41-24Z | 9000/9001 |

### 4.2 应用栈 (`compose.production.yml`, 叠加 phase0 使用)

| 服务 | 镜像/构建 | 备注 |
|---|---|---|
| api | build `docker/Dockerfile.api` | SPECPROOF_API_KEY 必填 (fail-closed) |
| worker | build `docker/Dockerfile.worker` | uid 1000; DOCKER_HOST=tcp://sandbox:2375 |
| outbox-relay | 同 Dockerfile.worker | `python -m storage.outbox_relay`, 指标 :9101 |
| sandbox | docker:27-dind (privileged) | DooD 专用守护, 无宿主机 socket 挂载 (§12) |

### 4.3 观测栈 (`compose.observability.yml`)

| 服务 | 镜像 |
|---|---|
| otel-collector | otel/opentelemetry-collector-contrib:0.123.0 |
| prometheus | prom/prometheus:v3.3.1 (TSDB retention 15d) |
| grafana | grafana/grafana:11.6.1 |

---

## 5. 锁定状态矩阵 (一页速查)

| 生态 | 直接依赖锁定方式 | 传递依赖 | 判定 |
|---|---|---|---|
| Python | `>=` 下限 (pyproject) | 未锁定, 无 freeze 快照 | ⚠️ 部分锁定 — 完整审计需 §1.3 干净 venv |
| Node (apps/web, ide/vscode) | `^` 范围 + package-lock.json | 锁文件精确锁定 (npm ci) | ✅ 锁定 |
| JDK | 21 (pom) | — | ✅ 写死 |
| Maven | 3.9.9 + zip sha256 (wrapper) | 依赖由 Spring Boot 3.4.3 BOM 管理 (非逐条钉版) | ✅ 工具链锁定; ⚠️ 依赖集随 BOM |
| Docker Compose | 镜像 tag 全部写死 | 镜像内层未审计 | ✅ 顶层锁定; ⚠️ 镜像内部未锁定 |

## 6. 已知缺口 (诚实记录, 不掩饰)

1. Python 无 lock/freeze 快照 — 完整锁定审计 (干净 venv + freeze) 未执行, 见 §1.3。
2. `pyproject.toml` 的 `>=` 下限不阻止未来破坏性主版本 (除 elasticsearch 的 <9 外无上限)。
3. Maven 依赖 (mysql-connector-j 等) 由 Spring Boot BOM 3.4.3 管理, 未逐条钉版。
4. Compose 镜像内部 (操作系统/运行时) 未做内容级审计; `docker:27-dind` 为 privileged (DooD 隔离在 compose 层说明, 见 `compose.production.yml` 注释与 `docs/operations/RUNBOOK.md`)。
5. 演示仓库 `demo/spring-backend/docker-compose.yml` 的镜像版本未纳入本文审计范围。
