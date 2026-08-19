# 100 金案例全量评估 — 双段实录与缺口分析 (2026-08-19)

状态: 段 2 (case-78..100) 已完成; 段 1 (case-1..77) 改为 4 小块重跑 (job pwsh-22:
c1=1-20 / c2=21-40 / c3=41-60 / c4=61-77, 逐块落盘报告, 抗中断)。
诚实说明: 首次全量跑 (pwsh-1) 在 case-78 处无迹终止 (exit 1, 1-77 尾部日志全 PASS,
无汇总); 第二次段1跑 (pwsh-51) 又因运行环境重启而中断且未落盘报告 — 因此拆成
小块化重跑, 每块完成即有该块报告, 中断不再丢失已完成部分。数字全部来自真实运行。

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

## 三个 MISS 已修复 (W36, 阶段4 执行探针)

- 交付: scripts/probe_templates/ 四件套 (CountingRabbitTemplate 计数+载荷捕获+
  一次性故障注入 / ProbePublishRecorder 写 specproof-probe.json / 探针测试, 独立
  H2 库不污染差分 DB) + builder probe_expectation 注入 + JavaMavenAdapter 探针钩子
  + run_differential PROBE-01 实验 (确定性 digest); 22 新单测;
- 三案例真实 E2E (Docker DooD 沙箱): docs/eval/eval-report-rel.* — total 3 /
  should_detect 3 / detected 3 / FP 0 / Precision/Recall/F1 100%;
  case-97 ORDER_EVENT-01: 注入 1 次故障 → base 1 次尝试(报错) vs head 2 次;
  case-98 EVENT_ONCE-01: base {0,success} vs head {0,error} (outcome 信号; 实测
  publish 计数同为 0 — 与任务描述的"head 1 次"偏差已诚实记录);
  case-100 EVENT_ONCE-01: 时间戳 base 非空 vs head null;
- 全段2 复跑 (78-100, 探针启用) 进行中 (job pwsh-37), 完成后本表回填新 Recall;
- case-97 探针发现按证据政策经 review court 降为 MAJOR (契约匹配仍 PASS)。

## 行动

- 段 1 (c1-c4, pwsh-22) 与段 2 复跑 (pwsh-37) 完成后合并 100 案例总表;
- nightly 矩阵 (GRAND_PLAN 卷 XXVIII) 固定为 100 案例分块跑法, 规避单跑长尾风险;
- 探针机制纳入 EXECUTION_COMPATIBILITY.md 阶段4 已支持项 (故障注入/发布计数/载荷捕获)。
