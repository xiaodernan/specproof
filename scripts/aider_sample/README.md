# scripts/aider_sample — 离线捆绑样例 (offline sample)

bench_aider harness 的离线可测试性来源。运行方式:

    python scripts/bench_aider.py --offline

无需网络、无需 Docker。真实运行需 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL
(见 docs/eval/AIDER_PLAN.md)。

## 布局

镜像真实 polyglot-benchmark 的结构 (<lang>/exercises/practice/<slug>/):

- `repo/python/exercises/practice/toycalc-double/` — `double()` 有真实 bug
  (`value / 2` 应为 `value * 2`), `toycalc_test.py` 基座红;
- `repo/python/exercises/practice/toycalc-multiply/` — `multiply()` 有真实 bug
  (`a + b` 应为 `a * b`);
- `repo/go/exercises/practice/toycalc-sum/` — runner 未支持 (harness 只实现
  pytest/npm test) 的诚实 unresolved 样例;
- 每个练习都有 `.docs/instructions.md` (任务描述) 与 `.meta/example.py`
  (参考解, 只用于证明工作区拷贝会排除 .meta)。

## 单元测试的预期结果 (harness 机制的证明)

| task_id | 预期 | 原因 |
|---|---|---|
| `python/toycalc-double` | **resolved** | 假客户端 (tests/unit/test_bench_aider.py 注入) 产出合法 llm 计划 + 正确的 `toycalc.py` 编辑 → craft DONE → `pytest toycalc_test.py` 通过 → resolved |
| `python/toycalc-multiply` | **unresolved** | 假客户端返回空编辑 → craft STUCK → harness 诚实记录 `no edit produced`, 绝不虚构 resolved |
| `go/toycalc-sum` | **unresolved** | runner=unsupported-go (harness 仅 pytest/npm test) → stage=tests 诚实 unresolved, craft 不运行 |

## 诚实的样例简化

1. 真实 polyglot 练习的任务描述是纯行为描述 (implement X), 测试文件基座红;
   本样例的描述直接点明 bug 位置, 与真实分布不同 — 样例只证明管线机制。
2. `.meta/` 参考解只存在于源树中, 工作区拷贝通过
   `shutil.ignore_patterns(".meta")` 排除 — 判定时模型拿不到答案。
3. 无 git 历史: 工作区重置 = 从源树全量重拷贝 (真实运行同样全量重拷贝,
   绝不修改 --benchmark-dir 下的原始仓库)。
