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
| `tests/unit/test_swebench_llm_fixes.py` | 首跑缺口回归 (§8): 编辑提案 JSON 信封修复/自检/稳定错误码、run_test 非静默输出、venv 显式错误与 --no-venv 回退 — 全离线假客户端 |
| `docs/eval/swebench-results.json` | 实测结果产物 (样例运行) |
| `docs/eval/swebench-llm-results.json` | 首次真实 LLM 运行实测产物 (honest 0%, 缺口见 §8) |

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

## 8. 首跑缺口与修复 (2026-08-19)

### 8.1 首跑成绩: 诚实的 0%

第一次真实 LLM 运行 (`docs/eval/swebench-llm-results.json`, 2 实例,
deepseek-v4-pro 经 fagougou 网关) 结果为 **resolved_rate 0.0%**:

| instance | 终态 | 失败点 |
|---|---|---|
| pallets__flask-4045 | FAILED | s4 (test): `LLM 编辑提案非法 … 模型输出缺少 edits 数组` — 模型回复无法解析为预期的 JSON 编辑提案 |
| pallets__flask-4992 | STUCK | s5 (verify): `同类错误连续 3 次 (签名: s5|<no-exec-output>)` — grep 类判据本就不跑命令, 签名用误导性的占位符; 同时 pytest 步骤因 venv 未就位死于 `No module named 'flask'` |

这是 harness 诚实的原始记录, 不修饰、不回填。两个缺口都在 craft/harness 层,
而不是"模型不够聪明":

### 8.2 缺口 1 — 编辑提案 JSON 信封 (pallets__flask-4045)

根因有三层:

1. **互相打架的输出契约**: diagnose 提示词在系统前缀里带着 JSON Action
   Envelope (`{"action": ..., "params": ...}`) 作为尾块, 而真正的输出契约
   (`{"diagnosis", "edits"}`) 埋在数据段 — 模型按信封回答, 解析器自然报
   "缺少 edits 数组" 并立即 FAILED, 没有任何修复机会;
2. **json_object 模式没有被提示词支撑**: 网关只有提示词含 "json" 字样才
   兑现 `response_format=json_object` (docs/design/GRAND_PLAN_V2.md), 而
   契约块在数据段, 系统前缀里没有权威的 JSON 契约;
3. **无修复回合**: 解析失败一步致死, 没有 "再给我一次, 按这个格式" 的
   确定性修复指令。

修复 (craft/loop.py + providers/toolcheck.py + craft/llm.py):

- 新的系统前缀契约块 `_EDIT_PROPOSAL_OUTPUT_BLOCK`: 整个回复必须是**一个
  JSON 对象**, 明确点名 `diagnosis` + `edits` 两个顶层键, 内联紧凑示例;
  diagnose 调用不再追加 JSON Action Envelope 尾块 (`include_envelope=False`);
- `EditProposalSelfCheck` (ToolCallSelfCheck 同款状态机): 非法/无法解析的
  提案**只触发一次**确定性修复指令 (带错误码 + 格式示例, 附模型原输出尾部
  片段); 第二次仍非法则携带稳定错误码 `[LLM_PROPOSAL_INVALID]` 按 M1 语义
  FAILED — 绝不执行非法提案, 也绝不静默吞掉;
- `extract_json_object` 容错强化: 剥离围栏 (前后), 提取文本中
  **第一个平衡的 JSON 值** (对象或数组), 字符串内的花括号不干扰扫描;
- json_object 模式: diagnose 调用始终请求 `response_format={"type":
  "json_object"}` (provider 按能力探测 `json_output` 决定是否真发 — 探测
  通过时网关会兑现, 提示词现在也满足 "含 json" 的前置条件)。

### 8.3 缺口 2 — verify 无输出 / venv 静默 (pallets__flask-4992)

根因:

1. **`<no-exec-output>` 是误导性签名**: grep/read 类判据本来就不执行命令,
   失败签名用占位符 `<no-exec-output>` 而不是真实失败原因 (断言值未命中);
2. **执行层把错误吞成空结果**: `sandbox/runner._run_local` 在启动失败/超时
   时返回空 stdout/stderr, 只把错误放进 `error` 字段, 而下游 (Executor →
   tools.run_test → loop 证据) 全部丢弃该字段 → 工具结果、checkpoint
   `log_tail`、诊断提示词全是空的;
3. **venv 与 craft 循环脱节**: craft 循环的 pytest 用系统 python
   (`exec_mode=local`), 共享 venv (含 pytest) 只给最后的 FAIL_TO_PASS 重放
   用; 实例依赖要到 craft DONE 之后才装 → flask 实例的 craft 测试步骤必然
   死于 `No module named 'flask'`; venv 创建失败则整批实例直接
   "deps unavailable", 没有回退。

修复 (sandbox/runner.py + craft/executor.py + craft/tools.py +
craft/loop.py + scripts/bench_swebench.py):

- **永不静默空输出**: 超时保留已产出部分输出; 启动失败 (OSError) 生成
  `could not start command …` 显式错误; Executor 与 tools.run_test 在输出
  为空时把 sandbox 错误注入 `output_tail`/`[exec error]`; loop 的
  test_green/compile 证据增加 `stderr_tail` 与 `error` 字段 (非空才加,
  确定性路径字节不变);
- **真实失败签名**: `_error_signature` 在无命令输出的步骤上用证据里的真实
  原因 (如 `断言值 'tomllib' 未出现在 …`) 代替 `<no-exec-output>` 占位符;
- **venv 显式校验**: `_prepare_venv` 创建/复用后都跑 `pytest --version`
  验证; pytest 缺失/损坏 → 显式错误而不是"已就绪"的假象;
- **自动 --no-venv 回退**: venv 创建/校验失败时 main() 自动回退到当前解释
  器直接跑 pytest (不安装依赖), 原始失败原因保留在 `run.venv.error` 与
  每实例 `deps.venv_error`/note 字段 — 绝不静默, 绝不崩溃出局;
- **venv 前置 + 接线**: 实例依赖在 craft **之前**装进共享 venv,
  `Executor`/`CraftLoop` 新增可选 `python` 解释器覆盖 (llm 模式传入 venv
  python), craft 循环自己的 compile/pytest 步骤与 FAIL_TO_PASS 重放共用
  同一解释器; 依赖安装失败记为 `deps.install_error` 并**不阻断** craft —
  测试步骤会把真实 stderr/退出码摊在报告里。确定性模式不传 python,
  行为与之前逐字节一致。

### 8.4 回归测试与门禁

新回归文件 `tests/unit/test_swebench_llm_fixes.py` (全部离线假客户端/
monkeypatch, 无网络、无 Docker、无真实 LLM):

- (a) 代码围栏 JSON → 解析并应用; 首 JSON 值提取;
- (b) 非 JSON → 恰好一次修复指令; 第二次失败携带 `[LLM_PROPOSAL_INVALID]`;
  `edits` 缺失 → 修复后收敛; 自检状态机/修复指令纯函数;
- (c) diagnose 请求 json_object + 提示词含 JSON/edits 且无 Action Envelope;
  provider 仅在能力 `json_output` 时发送 response_format (录制式假 SDK);
- (d) run_test 携带 stderr + exit code; 启动失败非静默; Executor 错误注入;
  venv python 覆盖;
- (e) venv 创建失败显式报错; `--no-venv` 回退保留原因; pytest 缺失显式报错;
  重放启动失败为逐测试显式 error。

门禁: ruff (改动文件) + mypy --strict (改动模块) + pytest 上述四个测试文件
+ craft sweep 全绿。诚实性不变式不变: reason 非空当且仅当 unresolved,
resolved 只来自 craft DONE + test_patch + FAIL_TO_PASS/PASS_TO_PASS 全过。

### 8.5 复跑实录 v2 (2026-08-19): 编辑提案已流通, 新缺口=测试文件误改

修复落地后真实复跑 (docs/eval/swebench-llm-results-v2.json, 同 2 实例、
同网关): 编辑提案 JSON 信封修复生效 — 模型输出的提案已能被解析并进入
apply/verify 循环; 但两个实例都在 verify 步以真实签名诚实 STUCK:

| instance | 终态 | 真实签名 (v2) |
|---|---|---|
| pallets__flask-4045 | STUCK | s3: 断言值 'pytest.raises(ValueError)' 未出现在 tests/test_blueprints.py |
| pallets__flask-4992 | STUCK | s4: 断言值 'tomllib' 未出现在 tests/test_config.py |

解读 (诚实): 模型学会了"补断言"策略 — 但它改的是测试文件, 而隐藏
FAIL_TO_PASS 测试由 harness 的 test_patch 应用, craft 的职责是只改源码
让隐藏测试通过。签名从 <no-exec-output> 升级为真实断言值/文件清单,
可定位性大幅提升, resolved 率仍为诚实的 0%。

下一修复 (W112): craft 编辑路径加测试文件守卫 — 任何指向 tests/**、
test_*.py、*_test.py 的提案条目按 CODE_TEST_FILE_FORBIDDEN 拒绝并携
"只改源码、绝不新建/修改测试文件"的修复指令重试一次; diagnose 提示词
加一行同义约束。修完再复跑同 2 实例。

### 8.6 后续复跑实录 v3-v9 (逐轮消障, 全部诚实 0%)

| 轮 | 实例终态 | 该轮清除的障碍 / 暴露的新层 |
|---|---|---|
| v3 | 4045 apply_edit 锚点未命中; 4992 verify 目标=测试文件 | 守卫生效 (测试文件误改消失) |
| v4 | 4045 判据退化 ('.'); 4992 锚点仍未命中 | verify 目标守卫生效 |
| v5 | 4045 依赖漂移 (werkzeug 3.x 移除 url_quote); 4992 判据重建生效 | 判据重建 (W114) |
| v6 | 4045 目标路径后缀 (flask/blueprints.py vs src/...); 4992 understand 判据 | 钉版本 (W140) + understand 重建 |
| v7 | 两实例直达 TEST 步, werkzeug ImportError 复现 | 后缀解析 (W143) + 钉版本生效证明 |
| v8 | 同 v7 (ImportError) | venv 复用钉应用 (W147) |
| v9 | 4045 craft 测试步收集整库 (test_cli.py 收集错误, 旧提交需特定 pytest); 4992 预算 12 次诚实超限 | 实探修正钉 werkzeug<3.0 (3.0.6 已移除 url_quote, 2.3.8 存在); ImportError 消失 |
| v10 | 4045 通过整库收集障碍直达 s5 (APITimeoutError 网关瞬时超时); 4992 [LLM_PROPOSAL_REPEATED] 第 2 迭代同提案即终止 | --continue-on-collection-errors + spec/diagnosis 测试文件限定 + 重复提案守卫 (W156) |
| v11 | 4045 超时重试生效推进到 s3, 两实例均在模型层重复提案上以 M1 语义 STUCK | 瞬时超时 2 次退避重试 + 多样化指令 (W163); harness 层障碍全部清完, 剩余为模型能力层 |
| v12 | 4045 同 v11: s3 [LLM_PROPOSAL_REPEATED], craft 0 次编辑应用 (4 迭代); 4992 推进到 s6 仍 [LLM_PROPOSAL_REPEATED] (提案与第 1 迭代即全同), craft 0 次编辑应用 (4 迭代) | 网关 /v1/models 仅 deepseek-v4-flash + deepseek-v4-pro 两档 (无更强档), 以最强档 deepseek-v4-pro 重测; craft/providers 全库无 temperature/seed 采样旋钮 (0 命中), 未改代码; 提案多样性未改善, 剩余确认为模型能力层 |

十二轮每轮清一类障碍 (信封→venv→测试文件误改→编辑锚点→判据退化→依赖漂移→venv 复用→后缀路径→测试收集→重复提案→瞬时超时), resolved 率始终诚实 0%; 官方 Docker 口径数字待 §3.4 手工步骤。v12 实测: 网关 /v1/models 只暴露 deepseek-v4-flash 与 deepseek-v4-pro, 不存在比 v11 所用 deepseek-v4-pro 更强的档位, 故 v12 以最强档重测同 2 实例; craft/llm.py 与 providers/ 全库无 temperature/seed/top_p 采样旋钮 (0 命中), 唯一生成侧 env 旋钮 LLM_THINKING_MODE 只是思考开关而非采样多样性、且网关恒返 reasoning_content, 加采样旋钮需改动允许清单之外的 craft/llm.py 或 providers/, 故未改任何代码 (scripts/bench_swebench.py 未动, 无需跑门禁)。结果: 4045 与 v11 同为 s3 [LLM_PROPOSAL_REPEATED]; 4992 从 v11 的 s5 推进到 s6 但签名不变、且重复提案与第 1 次迭代即全同 (v11 为第 2 次); 两实例 craft 均 0 次编辑应用 (v11 各至少 1 次), 全程 0 次瞬时超时 — 多样化指令 (W163) 未带来提案多样性, resolved 率诚实 0%, 剩余障碍确认为模型能力层。v13 方向: 换官方 Docker 口径 (§3.4 手工步骤) 或引入网关外的更强模型档位 (当前网关无 gpt-tier/deepseek-reasoner)。