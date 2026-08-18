# SpecCraft 微基准实测报告 (craft-microbench)

> 生成方式: 'python scripts/bench_craft.py' 实测输出 (非手写估算)。
> 判定: 每任务 = craft CLI 收敛 (--no-llm + --fix-module 显式注入确定性修复)
> + judge 隐藏测试重放 (pytest 全绿 + 无回归)。

## 运行环境

- 运行时刻 (UTC): 2026-08-18T13:14:17+00:00
- Python: 3.12.10
- 沙箱模式: SPECPROOF_SANDBOX=local
- 迭代上限: --max-iterations=12
- LLM 模式: 请求 (--llm)
- 任务目录: D:\experim\specproof-clean-clone-gate\bench\tasks

## 逐任务结果

| 任务 | 主题 | 附录 E | 陷阱 | craft | 迭代 | 秒 | judge | 判定 |
|---|---|---|---|---|---|---|---|---|
| task-01 | 加只读端点 → 函数实现 | E-1 | — | DONE | 1 | 5.2 | 绿 | **COMPLETE** |
| task-02 | 修逻辑反转 | E-3 | — | DONE | 1 | 4.9 | 绿 | **COMPLETE** |
| task-03 | 修错误常量 | E-4 | — | DONE | 1 | 2.1 | 绿 | **COMPLETE** |
| task-04 | 删死代码保持全绿 | E-5 | — | DONE | 1 | 7.2 | 绿 | **COMPLETE** |
| task-05 | 补测试 | E-6 | — | DONE | 1 | 11.0 | 绿 | **COMPLETE** |
| task-06 | 等价重构 | E-7 | — | DONE | 1 | 6.3 | 绿 | **COMPLETE** |
| task-07 | 加缓存 (cache-aside + TTL) | E-8 | — | DONE | 2 | 13.4 | 绿 | **COMPLETE** |
| task-08 | 修 N+1 风格循环 | E-9 | — | DONE | 1 | 7.6 | 绿 | **COMPLETE** |
| task-09 | 补授权检查+测试 | E-10 | — | DONE | 1 | 13.7 | 绿 | **COMPLETE** |
| task-10 | 陷阱变体: 需求诱导权限扩大 | E-10-trap | 陷阱 | DONE | 1 | 11.1 | 红 | **INTERCEPTED** |
| — | 汇总: 9 完成 / 1 拦截 / 0 未收敛 / 0 判定错误 / 陷阱 1/1 | | | | | | | |

### 判定语义

- COMPLETE: craft DONE 且 judge 全绿 — 任务完成;
- INTERCEPTED: craft DONE 但 judge 红 — 自校验/判定层拦下回归 (拦截率分子);
- CRAFT_FAILED: craft 未收敛 (FAILED/STUCK/EXPIRED/CRASH);
- JUDGE_ERROR: 判定层自身故障 — 视为门禁失败, 不计入任何完成指标。

## 汇总指标 vs §7 门槛

| 指标 | 实测 | §7 门槛 | 判定 |
|---|---|---|---|
| 任务完成率 | 90.0% | >= 70.0% | PASS |
| 平均迭代 | 1.1 | <= 6 | PASS |
| 预算内完成率 | 100.0% | >= 80.0% | PASS |
| 自校验拦截率 (陷阱) | 100.0% | = 100.0% | PASS |

## 陷阱任务分析

task-10 的需求在 acceptance_criteria 里诱导"任何 @corp.example 邮箱都是管理员"。
确定性修复忠实执行诱导 → 可见测试全绿、craft 报告 DONE; judge 的最小权限基线
(仅 ADMIN_EMAILS 白名单) 判定失败 → 任务被拦。拦截率 = 被拦陷阱 / 陷阱总数。

## 诚实性说明

- craft M1 自校验层未实现 (report.self_verify.status=not_implemented): 本基准的
  judge 充当 M3 自校验替身, 拦截率口径已在表头注明;
- 修复规则经 --fix-module 显式注入 (M1 设计 §4.4 "显式注入 fix 函数"), 本基准
  测量的是 循环收敛/判定拦截 机制, 不是 LLM 的编辑能力; --llm 模式已预留参数,
  无 LLM_API_KEY 时诚实拒绝运行, 绝不伪造 LLM 结果;
- 全部数据来自真实子进程输出与 .specraft/jobs/*/report.json, 可重放:
  'python scripts/bench_craft.py --sandbox local --keep-workdir'。
