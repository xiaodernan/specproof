# scripts/swebench_sample — 离线捆绑样例 (offline sample)

Harness 的离线可测试性来源。运行方式:

    python scripts/bench_swebench.py --offline

无需网络、无需 Docker、无需 HuggingFace。

## 布局

- `instances.json` — 2 个 SWE-bench-Lite 风格实例 (`instance_id`, `repo`,
  `base_commit`, `problem_statement`, `test_patch`, `FAIL_TO_PASS`,
  `PASS_TO_PASS`)。`repo` 是相对本目录的路径。
- `repos/toycalc-double/` — 迷你 Python 仓库, `double()` 有真实 bug
  (`x / 2` 应为 `x * 2`)。
- `repos/toycalc-multiply/` — 迷你 Python 仓库, `multiply()` 有真实 bug
  (`a + b` 应为 `a * b`)。

## 两个实例的预期结果 (harness 机制的证明)

| instance_id | 预期 | 原因 |
|---|---|---|
| `specproof__toycalc-double-1` | **resolved** | craft 确定性管道 + 为**该样例实例专门注册**的硬编码 fix (`scripts/bench_swebench.py` 的 `SAMPLE_FIX_REGISTRY`) 修复 `calc.py` → `test_patch` 加入隐藏测试 → FAIL_TO_PASS / PASS_TO_PASS 全绿 |
| `specproof__toycalc-multiply-1` | **unresolved** | 未注册任何 fix 规则 → harness 诚实记录 `no fix produced` (craft 管道 SKIPPED), 绝不虚构 resolved |

## 诚实的样例简化 (与真实 SWE-bench-Lite 的差异)

1. 真实 SWE-bench 的 FAIL_TO_PASS 测试通过 `test_patch` 在修复**之后**才出现,
   基座测试套件是全绿的; 本样例把一条观察性失败测试 (`test_double` /
   `test_multiply`) 放进了基座套件, 这样确定性循环的 `test_green` 判据才能
   观察到 bug 并触发注入的 fix。`test_patch` 仍演示了真实的补丁应用机制。
2. 样例仓库以普通文件分发 (无 git 历史), harness 用直接拷贝 checkout
   (`method=copy`), `base_commit` 仅为标注值; 真实实例走
   `git worktree add --detach <base_commit>`。
3. fix 注册表**只**按样例 `instance_id` 键控 — 真实 SWE-bench 实例 id 永远
   匹配不到, 因此真实运行默认全部 `unresolved (no fix produced)`, 直到通过
   `--fix-module` 显式注入规则。

改动 `instances.json` 后请同步检查 `SAMPLE_FIX_REGISTRY` 与
`tests/unit/test_swebench_harness.py` 的断言。
