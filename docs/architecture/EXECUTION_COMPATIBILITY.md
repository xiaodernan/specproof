# 执行适配器兼容矩阵 (Execution Compatibility Matrix)

> 依据: docs/工业化商业化终极开发指南.md §4.5 (执行沙箱插件接口) + §14 任务 10
> 实现: experiments/adapters.py (协议 + registry + JavaMavenAdapter + PythonAdapter)
> + experiments/minimize.py (反例最小化)
> 状态词汇 (指南任务 15): 已实现 / 本地验证 / 需真实基础设施 / 规划中;
> Python 行使用 "已支持 (local-first)" (宿主执行、无容器、首次装依赖可能需网络) — 本表全部如实标注。

## 不支持"任意项目"

SpecProof **不宣称支持任意项目**。管线对每个仓库先执行适配器 `detect()`
(Java/Maven 规则: `pom.xml` + `src/main/java`; Python 规则: `pyproject.toml`
| `requirements.txt` | `pytest.ini`), 命中失败时注册表按注册顺序落到下一个
适配器; 全部未命中则抛出 `AdapterNotImplemented` 并终止执行 (fail-closed,
绝不带病执行)。只有下表标注为 **已支持 (实测)** 或 **已支持 (local-first)**
的组合是本产品的承诺范围; 其余组合一律视为**规划 (planned)** — 其
`detect()` 显式抛 `AdapterNotImplemented`, 不会静默假装可用。市场/销售材料
只允许引用本表。

## 兼容矩阵

| 语言 | 构建工具 | 测试框架 | 支持状态 | 镜像 (digest) | 工具链版本 | 离线策略 | 已知限制 |
|---|---|---|---|---|---|---|---|
| Java | Maven | JUnit 5 + Surefire | **已支持 (实测)** | maven:3.9-eclipse-temurin-21<br>sha256:c07f7ccfb8ca6c9fa29ee523f00afa7d2ca6132c92f8652c4aebb5ee3491f502 | Maven 3.9.9 (wrapper 3.3.2) / Eclipse Temurin JDK 21 | mvn -o + --network none, 依赖只从预置卷 specproof-maven-cache-1000 解析 (RUNBOOK §5, scripts/seed_sandbox_cache.ps1); local 回退走仓库 Maven wrapper + 宿主 ~/.m2 | 缓存卷未预置则离线失败 (fail-closed); local 回退需宿主 JDK 21; 确定性测试模板仅支持 demo 仓库 (com.specproof.demo); 输出按尾部 256000 字符截断; digest 为 2026-08-18 本机验证值, 预拉/seed 时须复核 |
| Java | Gradle | JUnit 5 (Gradle Test) | 规划 (planned) | — | 待定 | 待定 (离线缓存策略随实现声明) | detect 抛 AdapterNotImplemented; 无执行器 |
| JavaScript/TypeScript | npm | Jest | 规划 (planned) | — | 待定 | 待定 (离线缓存策略随实现声明) | detect 抛 AdapterNotImplemented; 无执行器 |
| Python | pip | pytest | **已支持 (local-first)** | — (无容器, 宿主执行) | CPython 3.12 (宿主, 随执行机声明) / venv + pip / pytest | 复用项目 .venv; 缺失时 `python -m venv .venv` (离线安全) + `pip install -r requirements.txt` (首次安装可能需网络, 失败如实抛 PythonEnvironmentError) | local-first 无容器沙箱; 首次装依赖可能需网络; 复用 .venv 时跳过安装; 仅支持 pytest (goal=run_test); exotic Python 项目 detect 抛 AdapterNotImplemented; 输出按尾部 256000 字符截断; SPECPROOF_KEEP_VENV 时保留 .venv, 否则 cleanup 移除 |
| Go | go build | go test | 规划 (planned) | — | 待定 | 待定 (离线缓存策略随实现声明) | detect 抛 AdapterNotImplemented; 无执行器 |

## 协议与执行模型 (指南 §4.5)

```python
class ExecutionAdapter(Protocol):
    def detect(self, repo: RepositorySnapshot) -> RuntimeProfile: ...
    def prepare(self, request: ExecutionRequest) -> PreparedExecution: ...
    def run(self, prepared: PreparedExecution) -> ExecutionResult: ...
    def collect(self, prepared: PreparedExecution) -> EvidenceFragment: ...
    def cleanup(self, prepared: PreparedExecution) -> None: ...
```

- `detect` 只读判定, 返回 RuntimeProfile (language/build_tool/test_runner/known_limits)。
- `prepare` 产出 PreparedExecution: 沙箱内命令 (容器 /work 布局) + local 回退命令 +
  **镜像 digest / 工具链版本 / 离线依赖策略** 声明 + 超时。
- `run` 复用 sandbox.run_sandboxed 语义 (非 root / 断网 / 只读 workspace / 缓存卷 /
  local 回退并记录 mode), 结果进 ExecutionResult (exit/stdout_tail/stderr_tail/
  mode/沙箱资源记录); 输出按 §4.5 输出长度限制截断尾部。
- `collect` 产出 EvidenceFragment: surefire 报告引用 + exit 证据 (exit_code / mode /
  沙箱资源 / 测试摘要) — 证据链进入 guide §4.7 血缘。
- Python/pytest 为 local-first: `prepare` 复用/创建项目 `.venv` 并按需安装
  requirements.txt (pip 失败如实抛 `PythonEnvironmentError`, 分类
  venv_create/pip_install), `run` 在宿主直接执行 `python -m pytest -q`
  (无容器 — 矩阵已如实标注), 输出同样按尾部 256000 字符截断; `collect` 提供
  pytest 短摘要 (passed/failed/skipped); `cleanup` 在未设置
  SPECPROOF_KEEP_VENV 时移除 .venv。
- `cleanup` 只声明清理边界 (可丢弃 worktree 由管线回收, 容器 --rm 自清, local 模式
  target/ 为 build-cache 复用而保留), 适配器不得删除 workspace/target。

## 接线现状 (Q 车道)

- agent/nodes/run_differential.py 的 `_run_generated_test` 与
  agent/nodes/generate_counterexamples.py 的 `_compile_test` 已改为经
  registry.get → prepare → run 调用; Maven 命令形状与参数 (离线 -o /
  -Dtest= 注入 / -Dmaven.main.skip=true 复用标志 / 超时 900s·600s) 与改造前
  逐参数一致, 既有差分行为为回归红线。
- 新增语言: 实现 ExecutionAdapter 五方法 → 在 registry 注册顺序中声明 → 更新本表 →
  用真实项目实测后把状态从"规划"改为"已支持"。每季度重跑兼容矩阵 (指南 §13)。
- Python 适配器已注册 (registry 顺序: Java/Maven → Java/Gradle 规划 → Node 规划 →
  Python → Go 规划); experiments/minimize.py 提供 ddmin 反例最小化
  (步骤列表/集合/子串三种 fixture 缩减 + 迭代日志 + 预算停止 +
  unchanged-result 证明, runner 由调用方注入)。

## 验证记录

- 单元: tests/unit/test_adapters.py (detect 规则 / registry 顺序 / prepare 命令形状 /
  run 经 sandbox (mock) / collect 摘要 / 未实现适配器 / 矩阵内容断言);
  tests/unit/test_python_adapter.py (detect / venv 复用与创建 / venv_create·
  pip_install 失败分类 / run 经假 runner / pytest 摘要与尾部截断 / collect /
  SPECPROOF_KEEP_VENV cleanup / 矩阵行); tests/unit/test_minimize.py (ddmin
  列表收缩 / 集合与子串缩减 / 迭代日志 / 预算停止 / unchanged-result 证明,
  假 runner 注入, 全程无网络)。
- 实测: PythonAdapter 本机端到端冒烟 (2026-08-19, 系统临时目录的临时 pytest 项目,
  真实 venv 创建 + pip 安装 + pytest -q 执行): detect→prepare→run→collect→cleanup
  全链路通过, 1 passed/1 failed 摘要解析正确 (exit 1), cleanup 后 .venv 已移除;
  探针目录已清理, 不进入仓库。
- 门禁: ruff + mypy strict + bandit 全绿; tests/unit 全量 + tests/integration/
  test_differential.py (真实 Docker 沙箱差分) 全绿。
