# Aider polyglot benchmark 评测计划 (SpecCraft llm harness)

> 目标: 给 SpecCraft 第二个**工业级 agentic-coding 基准** — Aider 的 polyglot
> benchmark (Aider-AI/polyglot-benchmark, Exercism 练习抽取, 225 题 × 6 语言) —
> 用真实 craft 循环跑 repo 编辑任务, 按任务语言跑测试判分, 每一环失败都显式
> 标注, 绝不虚构。

## 1. 这个 harness 测量什么 (以及不测量什么)

| 测量对象 | 说明 |
|---|---|
| ✅ craft 管道的**真实 agentic 编辑能力** (llm 模式) | 真实调用 `craft/loop.py` (plan → execute → verify), plan/diagnose/edit 全部走 `craft.llm.LLMClient` (LLM_API_KEY/LLM_BASE_URL/LLM_MODEL 构建), **无 fix_registry** |
| ✅ 任务级测试判分 | 每个任务: 干净工作区 (排除 .meta 参考解) → PROMPT.md (任务描述) → craft plan/edit → 按语言执行测试 (python=pytest / javascript=npm test) → passed/failed |
| ✅ 防作弊 | 测试文件与 package.json 在 craft 前后**逐字节比对**, 被修改/新增测试类文件 → 判定无效 (unresolved) |
| ❌ **不**是官方 aider 口径 | 官方口径在 aider 仓库的 benchmark harness (docker + 每语言完整工具链 + aider 自身 agent); 本 harness 只实现 pytest/npm test 两个 runner, 不声称与官方数字可比 |

判定口径 (唯一产生 resolved 的路径):

1. craft 循环跑完且产生至少一个编辑;
2. 任务测试/配置文件与初始状态一致 (防作弊比对);
3. 按任务语言执行的测试全部通过。

任何一步不满足 → `status=unresolved` + 非空 `reason` + 失败阶段
(setup/craft/deps/tests)。reason 为空**当且仅当** resolved — 这条不变量由
`tests/unit/test_bench_aider.py` 直接断言。

craft 的终态 (DONE/FAILED/STUCK) 始终记录, 但**不**作为 resolved 的充分条件:
craft 内部的 `test_green` 判据是 pytest 口径, 对 javascript 任务无意义;
resolved 以 harness 按任务语言执行的测试为准, craft 非 DONE 时会在记录 note
里如实注明。

## 2. 组件

| 文件 | 作用 |
|---|---|
| `scripts/bench_aider.py` | 评测 CLI (`--tasks` / `--offline` / `--benchmark-dir` / `--cache-dir` / `--languages` / `--output` / `--md-output` / `--no-venv` / `--deps-timeout` / `--fetch-timeout` / `--exec-timeout` / `--max-iterations` / `--work-root` / `--keep-work`) |
| `scripts/aider_sample/` | 离线捆绑样例 (镜像真实目录结构 <lang>/exercises/practice/<slug>/): 2 个 python toy 练习 (真实 bug) + 1 个 go 练习 (runner 未支持), 无网络无 Docker |
| `tests/unit/test_bench_aider.py` | 离线端到端测试 (假客户端注入): 1 resolved + 2 诚实 unresolved + env 缺失诚实退出 + schema/扫描/防作弊/下载回退断言 — 无网络无 LLM |
| `docs/eval/aider-results.json` + `.md` | 结果产物 (JSON 全量记录 + md 汇总表); `docs/eval/aider-logs/` 为逐任务日志 |
| `docs/eval/AIDER_PLAN.md` | 本计划 |

## 3. 怎么跑

### 3.1 离线样例 (默认验证路径, 无网络无 Docker)

```powershell
python scripts/bench_aider.py --offline --no-venv --output docs/eval/aider-results.json
```

需要 LLM_* 环境变量非空 (缺了会先诚实退出); 无真实网关时 plan 阶段诚实降级为
规则计划 (llm_fallback_reason 记录), 样例任务全部 unresolved (no edit produced
/ runner 未支持) — 这是机制验证, 不是能力数字。

### 3.2 真实运行 (自动下载 + 真实 LLM)

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
$env:LLM_BASE_URL = "https://api.deepseek.com"   # 按实际网关配置
$env:LLM_API_KEY = "<你的密钥>"                   # 只从环境读取, 绝不落盘
$env:LLM_MODEL = "deepseek-v4-pro"

python scripts/bench_aider.py --tasks 3 --output docs/eval/aider-results.json
```

- **基准获取**: 无 `--benchmark-dir` 时自动从
  `https://codeload.github.com/Aider-AI/polyglot-benchmark/zip/refs/heads/main`
  下载并解压到 `--cache-dir` (默认系统临时目录, 缓存命中复用; zip 提取带
  zip-slip 防护)。下载失败 → 清晰报错 + 回退方案 (`--benchmark-dir` 指向手动
  下载的解压目录, 或 `--offline`)。
- **python 任务**: 共享 venv + pytest (`--no-venv` 跳过, 离线/测试路径)。
- **javascript 任务**: `npm install` (继承 HTTPS_PROXY) + `npm test`;
  npm 缺失/安装失败 → 诚实 `deps unavailable`。
- 每个任务都在 `--work-root` 下全量重拷贝干净工作区, **绝不修改基准仓库**。

### 3.3 官方全量 225 题 (文档化的人工步骤, 保持不变)

官方口径仍是人工步骤: aider 仓库的 benchmark harness + 逐语言工具链
(docker 化)。本 harness 的 pytest/npm 口径与其**不可比**; 任何数字必须标注
"harness 口径, 非官方口径"。

## 4. 子集选取标准 (--tasks / --languages)

1. **runner 支持优先级排序**: python (pytest) > javascript (npm test) >
   go/java/rust/cpp (本 harness 未实现, 诚实 unresolved, 默认排最后不选中)。
2. `--tasks N` (默认 3) 取该顺序的前 N 个任务; `--languages python,javascript`
   过滤语言 (未知语言名 → HarnessError)。
3. 练习目录判定: python 要有 `<slug>_test.py` (排除 test_*.py 辅助文件),
   javascript 要有 `*.spec.js` + package.json; 描述取 `.docs/instructions.md`。
4. 任务条目经 `_validate_task` 严格 schema 校验 (task_id/language/runner/
   test_file/source_dir/description), 非法条目落成 `<invalid-N>` unresolved
   记录而非静默跳过。

## 5. 结果 schema 与诚实性约定

`docs/eval/aider-results.json` 顶层: `schema_version` / `harness` /
`generated_at` / `benchmark` (name/url/source/语言计数/选取 note) / `run`
(超时/迭代预算/venv 状态) / `llm` (model + 去敏感 base_url 摘要, key 永不记录) /
`tasks` / `summary` (total/resolved/unresolved/resolved_rate_pct + note)。

每条任务记录: `task_id` / `language` / `runner` / `test_file` /
`description_head` / `prompt` (PROMPT.md 路径) / `craft` (终态/mode/编辑/
迭代/秒/report 路径/llm_usage/llm_fallback_reason) / `deps` (venv 或 npm
install 结果) / `test_run` (runner/command/outcome=passed|failed|error/
输出尾部/秒) / `logs` (tests.log 路径) / `stage` / `reason`。

工程级防伪造: 结果原子写; 每个非 resolved 记录携带真实 stderr 摘录;
harness 自身异常落成 unresolved 而不是崩溃出局; 测试/配置文件防作弊比对;
密钥/凭据绝不进入任何产物 (key_recorded=false)。

## 6. 诚实限制清单 (面试/审查场景直接引用)

1. **非官方口径**: 官方 aider polyglot 数字来自 aider 仓库 benchmark harness;
   本 harness 的数字不可与官方数字比较, 且必须标注 harness 口径。
2. **只有两个 runner**: pytest (python) 与 npm test (javascript) 已实现;
   go/java/rust/cpp 一律诚实 `runner 未支持` unresolved, 绝不假装跑过。
3. **craft 内部判据 ≠ 任务判分**: craft 的 test_green 是 pytest 口径, JS 任务
   craft 终态通常非 DONE; resolved 以按语言执行的测试为准, craft 终态如实记录。
4. **共享 venv ≠ 官方环境**: python 依赖只有 pytest; 练习若有额外依赖,
   测试失败会如实记为 test fail。JS 的 npm install 需要网络/代理。
5. **基准获取需要网络**: 自动 zip 下载走 HTTPS_PROXY/HTTP_PROXY; 失败给出
   `--benchmark-dir` / `--offline` 回退, 绝不静默继续。
6. **密钥只活在环境变量**: LLM_* 缺失/占位符 → 任何任务工作之前 exit 2;
   结果只记录 model 名 + 去敏感 base_url, key_recorded=false
   (tests/security/test_no_key_leak.py 兜底)。
7. **样例证明机制, 不证明性能**: 离线样例的 resolved 来自单元测试注入的假
   客户端, 只证明管线每一环真实可执行、失败路径真实可记录。
8. **真实干跑状态 (本次交付)**: 交付会话里 LLM_API_KEY 未设置 → 真实干跑**未
   执行** (诚实跳过); 由 captain 按 §3.2 单独执行, 结果回填
   `docs/eval/aider-results.json`。

## 7. 门禁与验证

```powershell
python -m ruff check scripts/bench_aider.py tests/unit/test_bench_aider.py scripts/aider_sample
python -m mypy --strict scripts/bench_aider.py
python -m pytest tests/unit/test_bench_aider.py tests/unit/test_swebench_harness.py tests/security/test_no_key_leak.py -q
python scripts/bench_aider.py --offline --no-venv --output docs/eval/aider-results.json
```

样例端到端测试与假客户端测试均无网络、无 Docker、无真实 LLM, 可在任何装有
git + pytest 的环境复现。
