# Aider polyglot benchmark — SpecCraft llm harness 结果

- 生成时间: 2026-08-19T13:22:15+00:00
- 基准: Aider-AI/polyglot-benchmark (source: offline-sample)
- LLM: fake-model @ http://127.0.0.1:9 (key 不记录)
- 判定: resolved 仅当 craft 产生编辑 + 任务测试/配置文件未被修改 + 按语言执行的测试全部通过 (见 docs/eval/AIDER_PLAN.md)

## 汇总

- total=3 resolved=1 unresolved=2 pass_rate=33.3%
- 说明: harness 口径: resolved 仅当 craft 产生编辑 + 任务测试/配置文件未被修改 + 按任务语言执行的测试全部通过; 失败阶段如实记录, 绝不伪造 通过 (见 docs/eval/AIDER_PLAN.md)

## 任务明细

| task_id | language | runner | status | stage | reason (前 160 字) |
|---|---|---|---|---|---|
| python/toycalc-double | python | pytest | resolved | tests |  |
| python/toycalc-multiply | python | pytest | unresolved | craft | no edit produced: craft 未产生任何编辑 (终态 STUCK); 未运行测试, 未声称 resolved |
| go/toycalc-sum | go | unsupported-go | unresolved | tests | runner 未支持: 语言 go 的测试执行本 harness 未实现 (仅支持 pytest/npm test); 未运行 craft, 未声称 resolved |

## 诚实性说明

- 这是 harness 口径, 非官方 aider 口径 (官方口径在 aider 仓库的 benchmark harness + 完整语言工具链; 见 AIDER_PLAN.md)
- 每个非 resolved 记录都携带真实阶段 (setup/craft/deps/tests) 与原因; 绝不伪造通过。
