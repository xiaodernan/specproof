## 这个目录是什么

运维/交付/验收面的文档。唯一的权威来源是**门**（tests/unit、Security、CI workflow）——
本文档只导航，不复述数字。

## 十分钟路线

1. `RUNBOOK.md` §1（组件与端口）+ §2（起停）+ §4（健康与观测）——
   单机部署起点，2026-11-10 补齐边缘网关（specproof-edge，8080/8090）。
2. `OBSERVABILITY.md` §5（SL0 告警表）+ §6（§14 各指标的接线状态，含未 pin 阈值的登记）。
3. `DRILLS.md` §6（待基础设施/需开发清单——**这份清单是故意写在最显眼处**：
   它列出每个「还没做」以及它在哪、被谁钉住、为什么是暂缓）。
4. `DEEP_OPTIMIZATION_PLAN.md`（经 1399 节连载的优化账本；
   最新结果、实测读数、诚实边界都在这里；已不适合从头读，请按节号/日期查）。

## 按角色分

| 你想知道 | 读 | 它有没有门钉住 |
|---|---|---|
| 部署怎么部署 | `RUNBOOK.md`（+ `LOCAL_EXPERIENCE.md` 本地轻量） | `tests/unit/test_runbook_claims_hold.py` |
| 出故障了/停机了 | `RUNBOOK.md` §2、§6（备份与恢复）、`DATA_LIFECYCLE.md` | 迁移/回滚门见 `tests/unit/` |
| 监控/告警为啥报 | `OBSERVABILITY.md` §5（规则↔§5 表↔阈值三处同钉）、§4（验证清单） | `test_alert_table_matches_the_deployed_rules.py`、`test_alert_rules_bind_their_own_threshold_table.py` |
| 评估产品能不能用 | `ACCEPTANCE_CHECKLIST.md`、`PILOT_RUNBOOK.md`、`TECHNICAL_CAPABILITIES_HISTORY.md` | 评测门（golden cases，CI `eval-golden-cases`） |
| 客户端/MCP 接线 | `MCP_GUIDE.md`、`GITHUB_APP_SETUP.md` | MCP 门见 `tests/unit/test_mcp_server.py` 等 |
| 威胁模型与测试 | `THREAT_TESTING.md`、`MIDDLEWARE.md` | `tests/security/` |
| 前端 | `FRONTEND.md` | 前端门（apps/web，vitest） |
| 为什么某个决定这么做 | `DEEP_OPTIMIZATION_PLAN.md`（按节号查：#1 起，当前 #1576）、`DRILLS.md` §5（FIX 台账） | 账本门（`tests/unit/test_ledger_*`） |

## 诚实边界

- 本索引 2026-11-10 写入；各文档内容谁都会漂——**机器判定以门为准**（每个条目右侧的
  门名就是一把尺子：它红了就是文档/代码不一致了）。
- `DEEP_OPTIMIZATION_PLAN.md` 是 append-only 的：某节说过的话**不会被静默改写**；
  后面的节写「订正」。要看现状请读清单最新节，不要倒过来读。
- `DRILLS.md` §6 是全宇宙最诚实的一页：它把"无法做"与"故意不做"分开标注；
  其中 ⏳ 的是真缺口（待基础设施），✅/更正是都已落地——每一行都有它钉的门。
