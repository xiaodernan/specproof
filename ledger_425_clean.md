## #425 静机器评测准备：全量单测、集成、DEEP、无并发 case-100

**背景**：全量评测 `#424` 完成（87/87 cases PASS），当前队列进入「产品/令牌决策」阶段。下一阶段需要在安静机器上验证底层质量保证体系。

**本批目标**：在安静环境下验证：
1. **全量单测**：在无并发、低负载环境下跑完整单测套件，验证 634+ 个测试的健壮性
2. **集成测试**：运行 integration 套件，特别是不需要 MySQL 的测试（`SPECPROOF_TEST_MYSQL_DATABASE` 未设置时）
3. **DEEP 评测**：运行 DEEP 相关测试，验证深度验证能力
4. ** uncontended case-100**：无并发情况下的个案验证，确保单案例执行的可控性

**当前队列状态**（产品/令牌决策，不替代做）：

| 项目 | 状态 | 备注 |
|---|---|---|
| 严重度漂移方向 | 待产品决策 | 池子按证据写期望 / 工具按合同写定级（#418 只摆事实） |
| 「first-try 判不了」口径 | 待产品决策 | 悲观 vs 排除口径 |
| measured wording | 待产品决策 | 「跑过」 vs 「量到」 |
| CI 夜间作业令牌 | 已知限制 | OAuth token 缺少 `workflow` scope，SSH push 可行（#422） |
| MQ surface | 待观测 | 作为「not observed」记录 |

**已完成的证据记录**：

- `#424`：87/87 eval complete, 86.5% severity agreement, 7 drifts all DB-state-driven
- `#423`：页面说明数字来自哪个池子（case_set: mode, excluded holdout, manifest absent）
- `#422`：工作范围诊断修正：HTTPS+OAuth 缺少 workflow scope，SSH push 有效
- `#421`：CI 现在上传 sidecar 文件同 HTML，evidence  travel with page
- `#420`：diagnose_eval_sidecar.py 事后无重运行即可诊断

**下一步**（等待安静机器）：

1. **全量单测**：在安静机器上跑 `tests/unit`，确保无 MySQL 时全绿
2. **集成测试**：运行不需要 MySQL 的 integration tests
3. **DEEP 评测**：运行深度验证测试
4. **case-100 个案验证**：无并发运行 single case，记录输出
5. **记录结果**：再次在 ledger 中追加 ## #NNN 章节，记录 quiet machine 下的测试结果

**质量门**（将在 quiet machine 下验证）：
- `ruff` + `mypy` 全绿
- 单测 634+ passed（不含 MySQL-backed 的 18 文件）
- ledger fence：无重复头，U+FFRD 计数保持不变

**证据文件**：
- `docs/operations/DEEP_OPTIMIZATION_PLAN.md`：当前已至 #424
- `reports/full-eval/eval-report.results.json` / `.jsonl` / `.html`：87 cases, all PASS
- `scripts/diagnose_eval_sidecar.py`：就位，等待 quiet machine 复用