# 更正卷轴 · The Corrections Scroll

> 本仓库里被撤回、被修正、被自己打脸过的每一件事，全部在此。
> 这页本身不是追责书——它是"可审计的错误用处理器"：能查到账本、能查到 commit、
> 能重算出修正后的数。凡我这个仓库声称过的话，凡本书后续引用本卷轴，都不绕过它。
>
> 规矩：① 卷轴只增不删；② 每条更正必挂 commit / ledger anchor；③ 任何想引用本仓库的人，先读这一张。

## 条目

| # | 误判原文（时间） | 实际指陈 | 撤回/修正 | anchor |
|---|---|---|---|---|
| **R01** | chronicle 1,645 节（2026-11-16T13:2xZ，#1845 入册时写错） | 实际 1,644 节 | 同段落内手动更正为 1,644 | DEEP_OPTIMIZATION_PLAN §#1845 |
| **R02** | 世界书双语失衡：「zh 72 / en 73」（#1855 首次入卷时两边数量不一致，中文文件误判为"已存在"跳过 zh，en 追加了 LXVI） | 同一对 zh/en 声称其实同一卷；检测重叠置布太宽（仅用"船期表"），zh 未被写入 | 回滚 en 版本，修检测为含完整标题「卷六十六 ·」，两边都入库 → **73 / 73** | DEEP_OPTIMIZATION_PLAN §#1855 + git show |
| **R03** | CrewCard 里留死数字「commits 2,499 · ledger 1,658 节」（#1858 卡生成器里写死） | 每一笔提交都会 +1（自我指涉），死数永远变成谎 | 全部改为 import 时从 repoStats.json/evidence.json 现场解析 | §#1858 |
| **R04** | ROADMAP-LIVE item 5 声称「疑似 ~1000 个 hash 名 542-byte scratch 残片」（#1860） | 真容：**21 件 git-tracked 文件（591,524 B），全在 docs/eval/swebench-logs/*/craft/backup/ —— SWE-bench 评测的源码快照（craft/backup 机制），内容寻址命名** | audit_scratch_residue.py 落地 + #1865 正式撤回 + ROADMAP-Live 第 5 项重渲染 | §#1860 → 撤回 @ §#1865 · docs/evidence/audit-scratch-residue.json |
| **R05** | `audit_court_lock.py` 首敲输出「verdict: BROKEN · lock c2ebdc0b…」（2026-11-15T18:24Z，#1866） | **这不是 repo 坏了——是我的审计 regex 不认 `kwargs["stream_options"] = {"include_usage": True}` 这一 Python 惯用拼法** | 修正为双拼法兼容（kwargs[…]= 和 JSON 风格的"stream_options":{...} 都校验）；复敲 → **LOCKED · lock 4117d2b0ca5fb23a** | §#1866 · tests/unit/test_court_lock_machine.py |
| **R06** | `build_evidence.py` 排序按文件名逆序取 latest（2026-11-16T17:5xZ，#1852 v1） | 同前缀文件名逆序会选错（`.json` > `-2.json`）——展示了错误 artefact | 排序关键从文件名换为 `started_utc`（ISO 字典序 = 时间序）逆序 | §#1854（衍生："#1852 起文件名乱序导致误选 latest"） |
| **R07** | Archive.tsx 写死 `worldbook: 50` + 文案硬编码「世界书 50 卷·编年 1,625 节」（存在很久；本次修订 #1863） | **此刻全假**：build 链早把它们涨成 81/1,664 等数字 | 全部改为 import lock 的 locked JSON，计数与 build_*.py 实时对账（并新增「史诗卷」KPI tile） | §#1863 |
| **R08** | `audit_unsigned.py` 首次敲出「branch-cleanliness: no-upstream」（2026-11-15，#1863 上线时） | subprocess 没被 import → 异常被 `except` 静默吞 → 返回 "" → 误判为 no-upstream | `import subprocess` 入模块 + 补充 docstring（4 灯）；复敲 → 正确读出 dirty-tree → 提交后转 clean | §#1863 |
| **R09** | 同一轮里 build_roadmap_live.py 入库 ≠ 它是确定性的——「commit 只修输出没跟脚本」（#1865 主提交遗漏生成器） | 出书面 v2 修复并提交 `27d632b`（follow-up）：ROADMAP-LIVE item 5 输出与生成器保持一致 | DEEP_OPTIMIZATION_PLAN 不为此另立节；提交 `27d632b` 直接记账（见 git log） | git show 27d632b |
| **R10** | RageCoach 测试断言 `"Sign & seal"` 期望 approve —— 实际规则在 tour-seal（规则内含 seal 关键词先吃掉） | 规则命名本来就有重叠；测试 expectation 错了不是代码错了 | 测试期望改为 tour-seal；`approve` 规则加空白容错（`批\s*准` 等） | #1846：`apps/web/src/ui/rage.test.ts` |

## 使用约束

1. 本卷轴条目不许删，只许增量 append；
2. 每次 rebuild 后 `python scripts/audit_evidence.py` 可敲比对：worldbook.json · chronicle.json · repoStats.json · engine.json · unsigned.json —— 一旦漂移一字节即报红并写新 R 条入册；
3. 本卷轴登记的≠小声喘息——它是失败的最终落点：我的错每一件，都如实埋着座标等你亲自敲。
