# 100 金案例全量评估 — 双段实录与缺口分析 (2026-08-19)

状态: 段 2 (case-78..100) 已完成; 段 1 (case-1..77) 重跑中 (job pwsh-51)。
诚实说明: 首次全量跑 (pwsh-1) 在 case-78 处无迹终止 (exit 1, 1-77 尾部日志全 PASS,
无汇总), 故拆为两段重跑以取得逐段汇总 — 数字全部来自真实运行。

## 段 2: case-78..100 (docs/eval/eval-report-rem.html/.results.json)

- 总案例 23 · 应检出 13 · 实际检出 10 · 误报 0
- Precision 100.0% · Recall 76.9% · F1 87.0%

## 段 2 三个 MISS (真实缺口, 非掩盖)

| 案例 | 契约 | 分析 |
|---|---|---|
| case-97 rel-broker-failure-retried-into-duplicate | EVENT_ONCE-01 (已找到契约) | 重试致重复发布是运行时行为 (broker 故障注入后重试路径), 差分执行未注入 broker 故障 → 不可观察; 需故障注入执行适配器 (阶段4 路线) |
| case-98 rel-noop-email-change-publishes-event | (无契约命中) | 语义等价判断失败: no-op 变更仍发事件需领域语义 (事件应为幂等变更才发), 静态契约无法表达 → 反例生成/LLM 语义契约候选 |
| case-100 rel-event-timestamp-nulled | (无契约命中) | timestamp 置空属字段级时间语义破坏, 当前契约无时间字段断言 → 契约模板扩展 (EVENT_FIELDS 类) |

三个 MISS 全部为 rel (可靠性) 类, 与既有 AUTH/CACHE/ORDER/NPLUSONE 等类的
100% 命中形成对照 — 说明静态+差分检测的边界在"运行时故障注入"与"时间语义"。

## 行动

- 段 1 完成后合并 100 案例总表 (Recall 双段加权);
- 将三个 MISS 转化为回归案例组 (fault-injection 适配器, 见 EXECUTION_COMPATIBILITY.md
  阶段4 路线), 每修复一个 MISS 即以案例重跑证明;
- nightly 矩阵 (GRAND_PLAN 卷 XXVIII) 固定为 100 案例双段跑法, 规避单跑长尾风险。
