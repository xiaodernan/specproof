# SWE-bench-Lite 评测计划 (SpecCraft deterministic harness)

> 目标: 给 SpecCraft 一个**最小且诚实**的 SWE-bench-Lite 评测口径 — 能报出一个
> resolved-rate 数字, 但数字的每一步都有记录、每一步失败都显式标注, 绝不虚构。

## 1. 这个 harness 测量什么 (以及不测量什么)

| 测量对象 | 说明 |
|---|---|
| ✅ craft 确定性管道的**机制** | 真实调用 `craft/loop.py` (plan → execute → verify), 修复只来自**显式注入**的 fix 规则 (`fix_registry` / `--fix-module`), 与 M1 设计一致: 没有注入规则就诚实失败 |
| ✅ SWE-bench-Lite 判定流程 | checkout base_commit → craft 修复 → 应用 `test_patch` → 逐条重放 FAIL_TO_PASS / PASS_TO_PASS → resolved 判定 |
| ❌ **不**是 LLM agent 能力 | 默认 `--mode deterministic`; 没有 LLM 调用、没有规划模型。LLM agent 模式的 SWE-bench 数字是另一个实验, 本 harness 刻意不做 |
| ❌ **不**是官方 SWE-bench 口径 | 官方评测需要逐实例 Docker 镜像 + install 脚本 + 官方 log-parser; 本 harness 用 `python -m pytest` 直接重放测试节点, 不声称与官方数字可比 |

判定口径 (唯一产生 resolved 的路径):

1. `fix_registry` 中存在该 `instance_id` 的注入规则 (默认只有捆绑样例的
   `specproof__toycalc-double-1`; 真实实例默认无规则);
2. craft 循环终态 `DONE` (每一步都有 checkpoint/report 证据);
3. `test_patch` 成功应用 (git apply, 失败有 stderr 记录);
4. 全部 FAIL_TO_PASS 通过 **且** 全部 PASS_TO_PASS 通过。

任何一步不满足 → `status=unresolved` + 非空 `reason`。reason 为空**当且仅当**
resolved — 这条不变量由 `tests/unit/test_swebench_harness.py` 直接断言。

## 2. 组件

| 文件 | 作用 |
|---|---|
| `scripts/bench_swebench.py` | 评测 CLI (`--tasks` / `--dataset` / `--output` / `--mode deterministic` / `--offline` / `--repo-dir` / `--fix-module`) |
| `scripts/fetch_swebench_lite.ps1` | 从 HF datasets-server rows API 下载 SWE-bench-Lite 实例 JSON (带进度; 失败 → 清晰报错 + 复制捆绑样例作为回退) |
| `scripts/swebench_sample/` | 离线捆绑样例: 2 个 toy 实例 (真实 bug + FAIL_TO_PASS), 无需网络/Docker |
| `tests/unit/test_swebench_harness.py` | 离线端到端测试: 1 resolved + 1 诚实 unresolved + schema 断言 |
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

真实运行在当前仓库是**人工步骤**, 不是一条命令, 因为:

1. **数据集**: `scripts/fetch_swebench_lite.ps1` 下载 test/dev split JSON
   (需网络或代理; 失败时脚本会说明并把样例复制到目标路径)。
2. **逐实例仓库**: SWE-bench-Lite 的 `repo` 字段是 `owner/name` (如
   `django/django`), harness 只从 `--repo-dir/<slug>` 找本地 checkout —
   需要人工把每个仓库**完整克隆**到 `--repo-dir` 下 (浅克隆没有
   `base_commit` 时, harness 会诚实记录 `worktree 创建失败`)。
3. **Docker 镜像**: 官方 SWE-bench 的 install/test 依赖逐实例镜像; 本 harness
   **刻意不实现**官方 docker 环境 — 它直接 `python -m pytest` 重放测试, 因此
   只适合 Python 实例且不声称官方口径。要官方数字, 需另建 docker 化的评测
   步骤 (见 §6 后续)。

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

## 4. 结果 schema 与诚实性约定

`docs/eval/swebench-results.json` 顶层: `schema_version` / `mode` /
`dataset` / `run` (超时、迭代预算、可用 fix 规则清单) / `instances` /
`summary` (total/resolved/unresolved/resolved_rate_pct + note)。

每条实例记录:

- `status`: `resolved` | `unresolved`; `resolved`: bool;
- `reason`: **非空当且仅当 unresolved** (clone 失败 / worktree 失败 /
  no fix produced / craft 未收敛+步骤原因 / test_patch 应用失败 /
  FAIL_TO_PASS 未通过 / PASS_TO_PASS 回归 / schema invalid / harness 内部错误);
- `stage`: 失败发生的阶段 (setup/craft/test_patch/tests);
- `checkout`: 方法 (worktree/copy) + 来源 + base_commit;
- `craft`: 终态/编辑清单/迭代数/秒数 + `report.json` 路径 (craft 未运行时为 null);
- `fail_to_pass` / `pass_to_pass`: 逐测试节点 outcome + 输出尾部
  (SWE-bench 数据集的嵌套 bundle 列表 `[[a::t, b::t]]` 会被展平 — bundle 语义
  是"全部节点必须通过", 展平不改变判定);
- `logs`: 测试日志路径 (完整输出在 `swebench-logs/<instance>/tests.log`)。

工程级防伪造措施: 结果文件用原子写; 每个非 resolved 记录必然携带真实
stderr/报告摘录; harness 自身异常也落成 unresolved 记录而不是崩溃出局;
`--tasks N` 只是取数据集顺序前 N 个 (不是官方 300 例选取口径, 已在结果
JSON 的 dataset.note 注明)。

## 5. 诚实限制清单 (面试/审查场景直接引用)

1. **确定性模式 ≠ LLM agent 模式**: 本 harness 的 resolved-rate 衡量的是
   "注入修复规则 + 循环收敛 + 判定流程" 的机制, 不是模型编程能力。LLM 模式的
   SWE-bench 评测是独立工作, 需要 `--llm` 式接入与密钥环境, 当前刻意不实现。
2. **样例是简化**: 基座套件里放了一条观察性失败测试 (真实 SWE-bench 的
   FAIL_TO_PASS 测试在 test_patch 之后才出现, 基座是绿的) — 否则确定性循环的
   `test_green` 判据无从观察 bug。此简化已在样例 README 与记录中注明。
3. **真实实例默认 unresolved**: `SAMPLE_FIX_REGISTRY` 只按样例 instance_id
   键控; 真实 id 永远匹配不到 → "no fix produced" → craft 阶段 SKIPPED 且
   resolved=false。这是特性, 不是缺陷。
4. **需要 Docker 的是官方口径**: 官方 SWE-bench-Lite resolved-rate 需要逐实例
   Docker 镜像与安装脚本; 本仓库没有实现, 所以任何真实数字都必须标注为
   "harness 口径, 非官方口径", 且真实运行是文档化的人工步骤。
5. **样例证明机制, 不证明性能**: 50% 样例 resolved-rate 只证明 harness 管线
   每一环真实可执行、失败路径真实可记录。

## 6. 门禁与验证

```powershell
python -m ruff check scripts/bench_swebench.py scripts/swebench_sample tests/unit/test_swebench_harness.py
python -m mypy --strict scripts/bench_swebench.py
python -m pytest tests/unit/test_swebench_harness.py tests/security/test_no_key_leak.py -q
python scripts/bench_swebench.py --offline --output docs/eval/swebench-results.json
```

样例端到端测试无网络、无 Docker, 可在任何装有 git + pytest 的环境复现。

## 7. 后续路线 (不在本次交付范围)

- LLM agent 模式: 用 `craft/llm.py` 的 client 驱动真实 SWE-bench 实例, 按
  官方口径出数字;
- 官方 docker 环境: 逐实例镜像 + install + 官方 log-parser;
- 官方 300 例 (test split) 全量运行 + resolved-rate 表。