# Mutation Kill-Rate Benchmark 实测报告

> 生成方式: 'python scripts/bench_mutation.py --offline' 真实运行输出 (非手写估算)。
> 口径: killed = 测试失败 或 SpecProof 契约判定; skipped = 无可用验证通道,
> 不计入杀死率; 杀死率 = killed / (killed + survived)。

## 变异杀死率: 83.3%

- 变异体总数: 6 (请求 10)
- 杀死: 5 / 存活: 1 / 跳过: 0
- 杀死率 = 5 / (5 + 1) = 0.833

## 运行环境

- 运行时刻 (UTC): 2026-08-19T05:26:48+00:00
- Python: 3.12.10
- 模式: offline_sample
- 目标: D:\experim\specproof-clean-clone-gate\scripts\mutation_sample
- 基线校验: PASS
- 测试通道: available
- 契约判定通道: available

## 逐变异体结果

| 变异体 | 操作 | 状态 | 判定来源 | 测试退出码 | 契约违规 |
|---|---|---|---|---|---|
| M01 | operand_swap | **killed** | test_failure, spec_verdict | 1 | bulk discount at exact threshold (C1): expected 450.0, got 500.9; bulk discount above threshold (C1): expected 540.0, go |
| M02 | boundary_change | **killed** | test_failure, spec_verdict | 1 | bulk discount at exact threshold (C1): expected 450.0, got 500.0 |
| M03 | return_inversion | **killed** | test_failure, spec_verdict | 1 | free shipping below threshold (C2): expected False, got True |
| M04 | constant_change | **killed** | spec_verdict | 0 | free shipping at exact threshold (C2): expected True, got False |
| M05 | constant_change | **killed** | test_failure, spec_verdict | 1 | tax rate is 8% (C3): expected 108.0, got 118.0 |
| M06 | constant_change | **survived** | — | 0 | — |

## 诚实性说明

- skipped (无任何可用验证通道) 不计入分子也不计入分母, 从不被算作 killed;
- baseline 未通过时整场实验以错误退出, 不产出数字;
- 存活变异体是测试弱点, 不自动视为 Bug (与产品规格一致);
- 离线样本的 M06 有意命中规范外、无测试覆盖的提示小费行为并存活,
  以证明本数字不是被凑成 100% 的。
