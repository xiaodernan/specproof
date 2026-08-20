# Go/No-Go #15 成本测量 (仓库内半程) — 真实按 Job 用量折算

> 目的: 门槛 #15 "平均验证成本在用户配置预算内" 中仓库内可测的一半 —
> 按 Job 聚合**真实** LLM token 用量并折算成本, 对照每作业已记录的 token 预算。
> 测量工具: `scripts/bench_cost.py` (ruff / mypy strict / 15 离线测试全绿)。
> 数据源: 真实运行的 craft report.json (`LLMClient.stats_report` + budget 台账), 无一数字编造。

## 价格口径 (诚实声明)

- 示例默认价 = **DeepSeek deepseek-chat 公开价** (USD / 1M tokens):
  prompt cache-hit $0.07 · cache-miss $0.27 · completion $1.10 · reasoning 按 completion 价 $1.10。
- 这是**换算口径示例**, 不是 llm-api.fagougou.com 的真实账单;
  reasoning 定价按 DeepSeek 惯例并入输出价。
- 真实账单对账 + 沙箱/DB/ES 资源成本计入之前, **#15 保持 PENDING**。

## 实测快照 (2026-08-20 18:45 UTC, docs/eval/cost-results.json)

| Job | 终态 | 调用 | tokens (prompt+completion+reasoning) | 成本估算 | token 预算 | 预算内 |
|---|---|---|---|---|---|---|
| swebench-pallets__flask-4045 | STUCK | 5 | 52,735 (10186+21664+20885) | **$0.048197** | 56,815 / 500,000 | ✅ |
| swebench-pallets__flask-4992 | STUCK | 7 | 133,401 (32800+50977+49624) | **$0.116650** | 153,299 / 500,000 | ✅ |
| swebench-specproof__toycalc-double-1 | DONE (确定性离线样本) | 0 | 0 | $0.000000 | 无 LLM 预算记录 | — |

汇总: jobs=3, total **$0.164847**, mean **$0.054949 / job**, total_tokens=186,136,
total_seconds=1,466.7; token 预算内 = **2/2** (有预算记录的两例均未超 500,000 上限);
每作业 $1.00 示例货币预算下 **3/3 预算内**。

解读: 两个真实网关实例的平均单作业 LLM 成本在 **$0.05–0.12 量级** (示例价格表),
token 预算使用率 11.4% (4045) / 30.7% (4992), 与每作业 500k token 预算的余量巨大。
若用户配置预算 ≥ $0.12/job, 当前用量在预算内 (示例价格口径)。

## 快照时点数据源说明 (诚实)

- 4045 的 report.json 在快照时点 (calls=5 / 4 迭代 / 256.6s) 为 v12 在途重跑的新报告 —
  harness 每次运行覆写 `docs/eval/swebench-logs/<instance>/craft/report.json`,
  v11 的 4045 报告 (calls=7 / 87,377.6 tokens) 已被覆盖; 4992 的 report (calls=7 / 153,298.6)
  与 v11 数字一致, 说明 v12 尚未覆写该实例。
- toycalc-double-1 为确定性离线样本 (0 LLM 调用), 证明脚本对零用量作业安全 (成本 $0)。
- **v12 终态报告产出后重跑刷新** (见下), 最终数字以重测为准。

## 刷新命令

```powershell
python scripts/bench_cost.py --per-job-budget-usd 1.0
# 结果: docs/eval/cost-results.json (schema_version 1, rows + aggregate)
```

## 剩余缺口 (门槛 #15 仍 PENDING 的原因, 诚实列出)

1. **真实账单对账**: 网关月度账单 vs 台账逐月核对, 尚未发生 (需真实付费账号)。
2. **非 LLM 资源成本**: 沙箱 (Maven/容器)、MySQL/Mongo/ES/Redis/MinIO 资源成本未计入。
3. **口径验证**: 示例价格表 ≠ 网关真实价格; 需以网关官方价目替换后复测。
