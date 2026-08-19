# SWE-bench-Lite 评测计划 (SpecCraft deterministic + LLM harness)

> 目标: 给 SpecCraft 一个**最小且诚实**的 SWE-bench-Lite 评测口径 — 能报出一个
> resolved-rate 数字, 但数字的每一步都有记录、每一步失败都显式标注, 绝不虚构。

## 1. 这个 harness 测量什么 (以及不测量什么)

| 测量对象 | 说明 |
|---|---|
| ✅ craft 管道的**机制** (确定性模式) | 真实调用 `craft/loop.py` (plan → execute → verify), 修复只来自**显式注入**的 fix 规则 (`fix_registry` / `--fix-module`), 与 M1 设计一致: 没有注入规则就诚实失败 |
| ✅ craft 管道的**机制** (LLM 模式) | `--mode llm`: 从 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL 构建真实 `craft.llm.LLMClient`, **无 fix_registry** 跑 plan/diagnose/edit — 模型真实尝试修复, 失败同样诚实 unresolved |
| ✅ SWE-bench-Lite 判定流程 | checkout base_commit → craft 修复 → 应用 `test_patch` → 逐条重放 FAIL_TO_PASS / PASS_TO_PASS → resolved 判定 |
| ❌ **不**是官方 SWE-bench 口径 | 官方评测需要逐实例 Docker 镜像 + install 脚本 + 官方 log-parser; 本 harness 用 `python -m pytest` 直接重放测试节点, 不声称与官方数字可比 |

确定性模式判定口径 (唯一产生 resolved 的路径):

1. `fix_registry` 中存在该 `instance_id` 的注入规则 (默认只有捆绑样例的
   `specproof__toycalc-double-1`; 真实实例默认无规则);
2. craft 循环终态 `DONE` (每一步都有 checkpoint/report 证据);
3. `test_patch` 成功应用 (git apply, 失败有 stderr 记录);
4. 全部 FAIL_TO_PASS 通过 **且** 全部 PASS_TO_PASS 通过。

LLM 模式判定口径: 同上, 仅第 1 步换成 "craft 循环无注入规则、由真实客户端
驱动 plan/diagnose/edit"; 任何阶段 (setup/craft/test_patch/deps/tests) 失败都
落成 unresolved + 非空 reason。

任何一步不满足 → `status=unresolved` + 非空 `reason`。reason 为空**当且仅当**
resolved — 这条不变量由 `tests/unit/test_swebench_harness.py` 与
`tests/unit/test_swebench_llm.py` 直接断言。

## 2. 组件

| 文件 | 作用 |
|---|---|
| `scripts/bench_swebench.py` | 评测 CLI (`--tasks` / `--dataset` / `--output` / `--mode deterministic\|llm` / `--instances-file` / `--no-venv` / `--deps-timeout` / `--offline` / `--repo-dir` / `--fix-module`) |
| `scripts/fetch_swebench_lite.ps1` | 从 HF datasets-server rows API 下载 SWE-bench-Lite 实例 JSON (带进度; 失败 → 清晰报错 + 复制捆绑样例作为回退) |
| `scripts/swebench_sample/` | 离线捆绑样例: 2 个 toy 实例 (真实 bug + FAIL_TO_PASS), 无需网络/Docker |
| `scripts/swebench_subset/python_subset.json` | 精选 10 例纯 Python 子集 (instance_id 数组, 选取标准见 §3.3 与同目录 README) |
| `tests/unit/test_swebench_harness.py` | 离线端到端测试: 1 resolved + 1 诚实 unresolved + schema 断言 |
| `tests/unit/test_swebench_llm.py` | LLM 模式离线测试 (假客户端): resolved / 诚实 unresolved / env 缺失诚实退出 / 子集 schema 校验 — 无网络无 LLM |
| `docs/eval/swebench-results.json` | 实测结果产物 (样例运行) |

## 3. 怎么跑

### 3.1 离线样例 (默认验证路径, 无网络无 Docker)

```powershell
python scripts/bench_swebench.py --offline --output docs/eval/swebench-results.json
```

预期: 2 个实例, 1 resolved (`specproof__toycalc-double-1`) +
1 unresolved (`specproof__toycalc-multiply-1`, reason=no fix produced),
resolved_rate 50.0%。这也正是 `docs/eval/swebench-results.json` 里提交的实测记录。

### 3.2 真实 SWE-bench-Lite 运行 (文档化的手工步骤)

真实运行在当前仓库仍是**人工步骤** (官方口径尤其如此), 但 harness 已把能自动的
部分自动化:

1. **数据集**: `scripts/fetch_swebench_lite.ps1` 下载 test/dev split JSON
   (需网络或代理; 失败时脚本会说明并把样例复制到目标路径)。
2. **逐实例仓库**: SWE-bench-Lite 的 `repo` 字段是 `owner/name` (如
   `django/django`)。harness 按优先级取仓库: 本地 `--repo-dir/<slug>`
   checkout → 自动 `git clone https://github.com/<owner/name>.git`
   (走 HTTPS_PROXY/HTTP_PROXY 代理)。克隆得到的是完整历史, 随后
   `git worktree add --detach <base_commit>`; 任何失败 (浅克隆缺 commit
   等) 都诚实记录 `worktree 创建失败`。
3. **Docker 镜像**: 官方 SWE-bench 的 install/test 依赖逐实例镜像; 本 harness
   **刻意不实现**官方 docker 环境 — 它直接 `python -m pytest` 重放测试, 因此
   只适合 Python 实例且不声称官方口径。要官方数字, 需另建 docker 化的评测
   步骤 (见 §3.4)。

```powershell
.\scripts\fetch_swebench_lite.ps1 -Split test -OutFile .\swebench-lite-test.json
python scripts/bench_swebench.py --dataset .\swebench-lite-test.json --tasks 10 \
    --repo-dir D:\swebench-repos --output docs/eval/swebench-results.json
```

预期 (当前确定性模式): 全部 `unresolved`, reason=`no fix produced` —
**这是正确且诚实的结果**: 确定性模式没有任何针对真实实例的注入修复, resolved
数必然是 0。要得到非零 resolved 率, 必须为具体实例显式注入规则:

```powershell
python scripts/bench_swebench.py --dataset .\swebench-lite-test.json --tasks 10 \
    --repo-dir D:\swebench-repos --fix-module .\my-swebench-fixes.py
```

`--fix-module` 指向导出 `FIX_REGISTRY: {instance_id: {step_key: fix_fn}}` 的
Python 模块 (`fix_fn(editor, step, diagnosis) -> list[str]`, 与
`craft/loop.py` 的 `FixFunction` 同签名)。注入即声明: resolved 只说明"注入的
确定性修复 + 管道收敛 + 隐藏测试全绿", 不代表模型智能。

### 3.3 LLM 模式 (真实客户端, 真实尝试)

LLM 模式用 `craft/llm.py` 的 `LLMClient` 从环境变量构建客户端
(`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`), craft 循环**不使用
fix_registry**: plan / diagnose / edit 全部走真实客户端。任何环境缺失在
任何实例工作**之前**诚实退出:

```
LLM mode requires LLM_API_KEY/LLM_BASE_URL/LLM_MODEL env vars
```

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
$env:LLM_BASE_URL = "https://api.deepseek.com"   # 按实际网关配置
$env:LLM_API_KEY = "<你的密钥>"                   # 只从环境读取, 绝不落盘
$env:LLM_MODEL = "deepseek-v4-pro"

python scripts/bench_swebench.py --mode llm \
    --dataset princeton-nlp/SWE-bench_Lite \
    --instances-file scripts/swebench_subset/python_subset.json \
    --repo-dir D:\swebench-repos \
    --output docs/eval/swebench-results.json
```

LLM 模式的每个实例流程: checkout (本地 checkout 或 github 克隆, 见 §3.2) →
craft (真实 plan/diagnose/edit, 计划调用失败会诚实降级为规则计划并记录
`llm_fallback_reason`) → `test_patch` → **deps** (共享 venv, 见下) → 逐条
FAIL_TO_PASS / PASS_TO_PASS。resolved 仅当 craft `DONE` + test_patch 应用成功
+ 全部目标测试通过 — 与确定性模式同一把尺子。

**venv 与依赖 (deps 阶段)**: 每次运行在 `--work-root` 下建一个共享 venv 并
安装 pytest; 每个实例按首个存在的安装配置尝试平凡安装 (pyproject.toml →
setup.py → setup.cfg 走 `pip install .`, requirements.txt 走 `pip install -r`)。
安装超时/失败 → 诚实 `unresolved (deps unavailable)`, 绝不假装环境可用。
`--no-venv` 跳过全部 venv/依赖逻辑 (离线样例与单元测试路径)。诚实声明:
共享 venv ≠ 官方逐实例 Docker 环境, 依赖漂移 (如 werkzeug 3.x vs flask 2.3)
导致的失败会如实记录, 不会被掩盖。密钥与 base_url 凭据绝不写入结果 JSON
(base_url 只记录 scheme+host+port 摘要)。

**精选子集 (scripts/swebench_subset/python_subset.json)**: 10 例 SWE-bench-Lite
test split 实例, 选取标准 (详见同目录 README):

1. 纯 Python 小仓库 (flask / pylint / sphinx), 无编译型依赖;
2. `pip install .` 依赖平凡 (纯 wheel, 无需系统库/DB/容器);
3. FAIL_TO_PASS 是纯单元测试 — 不碰网络/DB/Docker, plain pytest 可直接重放;
4. PASS_TO_PASS 列表短 (≤ 54 条), 逐节点重放快;
5. 排除 astropy / matplotlib / scikit-learn / pandas / xarray / seaborn /
   django 等重依赖实例。

组成: pallets/flask × 3 (4045, 4992, 5063), pylint-dev/pylint × 4
(5859, 6506, 7228, 7993), sphinx-doc/sphinx × 3 (7975, 8721, 11445)。
`--instances-file` 是严格的 instance_id 数组 (schema 非法 / 重复 / 数据集里
找不到的 id → HarnessError), 与 `--dataset` 联用; 与 HF id 联用时 harness
会拉取完整 split 再按 id 过滤。

### 3.4 官方全量 300 例 (文档化的手工步骤, 保持不变)

官方口径仍是人工步骤: 逐实例 Docker 镜像 + install 脚本 + 官方 log-parser,
按 SWE-bench 官方评测流程执行, 本 harness 的 venv+pytest 口径与其**不可比**。
LLM 模式出的任何数字必须标注 "harness 口径, 非官方口径"。

## 4. 结果 schema 与诚实性约定

`docs/eval/swebench-results.json` 顶层: `schema_version` / `mode` /
`dataset` (含 `subset` 信息) / `run` (超时、迭代预算、可用 fix 规则清单、
venv 状态) / `llm` (llm 模式: model + 去敏感 base_url 摘要, key 永不记录) /
`instances` / `summary` (total/resolved/unresolved/resolved_rate_pct + note)。

每条实例记录:

- `status`: `resolved` | `unresolved`; `resolved`: bool;
- `reason`: **非空当且仅当 unresolved** (clone 失败 / worktree 失败 /
  no fix produced / craft 未收敛+步骤原因 / test_patch 应用失败 /
  deps unavailable / FAIL_TO_PASS 未通过 / PASS_TO_PASS 回归 /
  schema invalid / harness 内部错误);
- `stage`: 失败发生的阶段 (setup/craft/test_patch/deps/tests);
- `checkout`: 方法 (worktree/copy) + 来源 + base_commit;
- `craft`: 终态/模式 (deterministic|llm)/编辑清单/迭代数/秒数 +
  `report.json` 路径 (llm 模式附 `llm_usage` 与 `llm_fallback_reason`;
  craft 未运行时为 null);
- `llm` (llm 模式): client 类型 + model + 去敏感 base_url 摘要 + key_recorded=false;
- `deps` (llm 模式): venv 解释器 + 安装标记 + 安装结果 (失败即 deps unavailable);
- `fail_to_pass` / `pass_to_pass`: 逐测试节点 outcome + 输出尾部
  (SWE-bench 数据集的嵌套 bundle 列表 `[[a::t, b::t]]` 会被展平 — bundle 语义
  是"全部节点必须通过", 展平不改变判定);
- `logs`: 测试日志路径 (完整输出在 `swebench-logs/<instance>/tests.log`)。

工程级防伪造措施: 结果文件用原子写; 每个非 resolved 记录必然携带真实
stderr/报告摘录; harness 自身异常也落成 unresolved 记录而不是崩溃出局;
`--tasks N` 只是取数据集顺序前 N 个 (不是官方 300 例选取口径, 已在结果
JSON 的 dataset.note 注明); llm 模式的密钥/凭据绝不进入任何产物。

## 5. 诚实限制清单 (面试/审查场景直接引用)

1. **两种模式都诚实, 但口径不同**: 确定性模式的 resolved-rate 衡量
   "注入修复规则 + 循环收敛 + 判定流程" 的机制; LLM 模式衡量
   "真实客户端 (plan/diagnose/edit) + 循环收敛 + 判定流程"。二者都不是官方
   SWE-bench 口径, 数字之间不可直接比较。
2. **LLM 模式的密钥只活在环境变量里**: `LLM_API_KEY` 缺失/占位符 → 任何实例
   工作之前诚实退出; 结果 JSON 只记录 model 名与去敏感 base_url 摘要,
   key_recorded=false (由 tests/security/test_no_key_leak.py 兜底)。
3. **共享 venv ≠ 官方 Docker**: llm 模式 deps 阶段是共享 venv + 平凡 pip 安装,
   失败即 honest `deps unavailable`; 依赖漂移导致的失败如实记录, 不掩盖。
4. **样例是简化**: 基座套件里放了一条观察性失败测试 (真实 SWE-bench 的
   FAIL_TO_PASS 测试在 test_patch 之后才出现, 基座是绿的) — 否则确定性循环的
   `test_green` 判据无从观察 bug。此简化已在样例 README 与记录中注明。
5. **真实实例默认 unresolved (确定性模式)**: `SAMPLE_FIX_REGISTRY` 只按样例
   instance_id 键控; 真实 id 永远匹配不到 → "no fix produced" → craft 阶段
   SKIPPED 且 resolved=false。这是特性, 不是缺陷。
6. **需要 Docker 的是官方口径**: 官方 SWE-bench-Lite resolved-rate 需要逐实例
   Docker 镜像与安装脚本; 本仓库没有实现, 所以任何真实数字都必须标注为
   "harness 口径, 非官方口径", 且官方全量运行是文档化的人工步骤 (§3.4)。
7. **样例证明机制, 不证明性能**: 50% 样例 resolved-rate 只证明 harness 管线
   每一环真实可执行、失败路径真实可记录; 10 例子集是自测口径, 不代表
   官方 300 例分布。

## 6. 门禁与验证

```powershell
python -m ruff check scripts/bench_swebench.py scripts/swebench_subset tests/unit/test_swebench_harness.py tests/unit/test_swebench_llm.py
python -m mypy --strict --follow-imports=silent scripts/bench_swebench.py tests/unit/test_swebench_llm.py
python -m pytest tests/unit/test_swebench_llm.py tests/unit/test_swebench_harness.py tests/security/test_no_key_leak.py -q
python scripts/bench_swebench.py --offline --output docs/eval/swebench-results.json
```

mypy 说明: `--follow-imports=silent` 只为目标文件报错 (craft/ast_edit.py 与
craft/structured_diff.py 在 HEAD 上已有 13 个历史 strict 错误, 不属于本交付);
目标文件本身仍在 strict 模式下被完整检查。

样例端到端测试与 LLM 模式测试 (假客户端) 均无网络、无 Docker、无真实 LLM,
可在任何装有 git + pytest 的环境复现。

## 7. 后续路线 (不在本次交付范围)

- 官方 docker 环境: 逐实例镜像 + install + 官方 log-parser;
- 官方 300 例 (test split) 全量运行 + resolved-rate 表 (LLM 模式已在 harness
  内, 但官方口径仍是文档化的人工步骤)。