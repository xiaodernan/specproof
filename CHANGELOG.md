# CHANGELOG.md — SpecProof 变更日志

格式约定：按日期列 **可归因的变更**；每条附"证据"行——命令、输出、结论，而非感知描述。本项目**尚无签名的版本标签**（tag），因此未发布 dists 无法引用；所有内容以 git 历史与 `docs/operations/DEEP_OPTIMIZATION_PLAN.md`（数字化账本，每个 `## #NNN` 对应一笔真实工作）为准：`git log --follow docs/operations/DEEP_OPTIMIZATION_PLAN.md` 或上面的账本。

## 2026-11-15（六次登记） · 滚轮反转 + 压力测试车间 + /health 探针并行化

本条目覆盖 `a504661` → `b0bb993`（ledger `#1750` → `#1755`）。

### 新增 / 修复
- **滚轮方向默认“反转开启”**（#1752）：拥有者明示“往下滑就往下看”——顶栏 ⇅ 默认 ON，可单键回退至浏览器标准轴；`specproof_invert_scroll=0` 显式关闭。
- **UI 快捷键中文串全部入 i18n 表**（#1750）：`ui/shortcuts.ts` 数据结构支持 zh/en，`ShortcutHelp.tsx` 全部 key 化；UiKit 与测试消费侧同步修正。
- **压力测试车间**（#1755）：隔离实例 127.0.0.1:8123（uvicorn，**零触碰线上 MySQL/Redis**），`.local/*-scratch.sqlite3` 拷贝；
  120 并发 × 2 轮，360/360 ok，err 0.00%，p50≈666 ms p99≈973 ms；scratch 已清理。
- **前门压力**（#1751/#1753）：`scripts/stress_smoke.py`——72→150 并发两轮，素面静态服务触顶到 150 并发时大量超时（BUDGET-BLOWN）；朴素开发服务器≠生产 SLA，如实不外推。
- **`/health` 探针并行化**：MySQL/Redis 原串行，死后 29.18 s 才 200；现同 pool 并行（实测仍 ~27 s —— Redis store 内禀超时不改）；degraded 语义不变。

### 验证状态
- Spring Cloud 全服务本机亲跑：gateway **81/81** · discovery-server **1/1** · config-server **1/1** · control-plane **51/51**。
- `vitest` **497/497**；`tsc --noEmit` 0 错误；`vite build` ✅ in 509 ms；progress-event 双向门 4/4；ledger 四件套 45/45 ×4。
- 全量 `pytest tests/unit` 仍未跑完；E2E 未跑；"134/134" 只代表本机一次的观察，不构成可用性背书。
- `#/drill`/新卷未过浏览器目验；CommandPalette ~30 个 `loc` 双语标签保持、不偏到误译；Agent 控制台 ~240 行 CJK 仍是中文原生（账目 #1748/#1750 在案）。

## 2026-11-15（五次登记） · 四服务铁证大一统 + UI 运输层 / 详情页全面双语

本条目覆盖 `1f83434` → `5e22587`（ledger `#1746` → `#1748`）。

### 新增 / 修复
- **四个 Spring Cloud 服务本机全部亲跑绿**：gateway **81/81** · discovery-server **1/1**（Eureka 自签启动）· config-server **1/1**（native）· control-plane **51/51**（H2 + 本机 Redis 6379 + RabbitMQ 5672）= **134/134**；Eureka 复制器 offline noise 如实注明；`services/README.md` 四节实测证据就位。
- **UI 运输层（`api.ts`）五个中文错误串进 i18n 表**（#1747）：`api.unreachable` / `requestFailed` / `streamUnavailable` / `streamDropped` / `aiStreamFailed`；`NETWORK_UNREACHABLE` 冻结 const → **`networkUnreachableMessage()` 现取**，修掉 frozen-at-import 的 en-only 缺陷；FindingDetail/api.net.test 29/29。
- **`FindingDetail.tsx` 全页双语化**（#1748）：50 个用户面中文字面量 → `fd.*` i18n（zh 逐字、en 手译）；`FindingDetail.test.tsx` 26/26 保持全绿；详情页**无面向用户的原生中文字面量**。
- `services/README.md` §3 已更新为四服务实测证据；**不外推到任何承诺**：这是一次本机的观察不是可用性背书。

### 验证状态
- `vitest` **497/497**；`tsc --noEmit` 0 错误；`vite build` ✅ in 519ms；progress-event 双向门 4/4；FindingDetail 26/26；ledger 四件套 45/45；
- Spring Cloud 四服务 **134/134 本机亲跑**（含 Redis/RabbitMQ live）；全量 `pytest tests/unit` 仍未跑完；
- 缓存命中率仍然是观测量（#1723），从来不是健康指标；`#/drill`/新卷未过浏览器目验；
- 仍有未译残余：Agent 控制台约 240 行 CJK、ui-kit 剩余 props、Explorer/Usage 少量字面量——这些就是下一条账目，不遮不掩。

## 2026-11-15（四次登记） · 微服务铁证 mvn 81/81 + jobStatus 双语

本条目覆盖 `1ff1c11`（ledger `#1745`）。

### 修复 / 新增
- **`services/gateway` 实跑 `mvn -o test`**：`Tests run: 81, Failures: 0, Errors: 0, Skipped: 0 — BUILD SUCCESS`（02:03 min，Netty 真启动，ephemeral ports 60732/49299，`RedisTokenBucketRateLimiterTest` 5/5）。`services/README.md` 已更新为以上数字与可见缺口（`missingServices=[api, control-plane]` — 非致命警告，如实留档）。
- **jobStatus 16 个 gloss 入 i18n 表**（`StatusPill.tsx`）：en/zh 双向对称，`test_progress_event_labels` 双向门 4/4 绿；TS2353 拦住的 en 侧 key 前缀不匹配也如实划掉了。

### 验证状态
- `vitest` 497/497；`tsc --noEmit` 0 错误；`vite build` ✅ in 496ms；progress-event 双向门 4/4；ledger 四件套 45/45；
- **gateway 81/81 只代表 gateway 模块**，三个其余模块未重跑——不外推；全量 `pytest tests/unit` 仍未跑完。

## 2026-11-15（三次登记） · CI 守承诺 + 双语 LLM 实测 + 卷十七 / 第九卷

本条目覆盖 `2c149c0` → `dcea0bd`（ledger `#1740` → `#1743`）。

### 新增
- **`.github/workflows/demo-doctor.yml`**：第一机 6.1《IDE/CI 集成》欠条的台阶——master push/PR 触发，fetch-depth: 0 保 `base`/`head-v1` tag refs，零 Docker、零网络、零 LLM。
- **`scripts/llm_locale_consistency.py`**：双语一致性探针（观测型，不作 gate）；wkapi gpt-6-sol 实测同题同答 `BLOCKER`（zh 4749/cached 3981, en 4727/cached None）。
- **世界书卷十七《两种语言的验收》**（中英双文）；仓库共 17 卷，EN 对应。
- **`/epic` 第九卷**；九卷中英对齐。

### 验证状态
- `vitest` 497/497；`tsc --noEmit` 0 错误；`vite build` ✅；ledger 四件套 45/45；guide gate 6/6；
- 全量 `pytest tests/unit` 未跑完；#/drill 未浏览器目验；CI 工作流尚未经过真实 runner 见红/见绿——三次登记一如既往不粉饰。

## 2026-11-15（二次登记） · 世界书卷十六 + /epic 第八卷

本条目覆盖 `c7626b5` → `4a8a346`（ledger `#1735` → `#1736`）。

### 新增
- **世界书卷十六《十二把铁秤（The Twelve Iron Scales）》**：从「它声称双语」到「toggle 一按就换脸」的完整档案；16.4 如实记下「键与译文写反」事故（tsc+眼检双重咬出，未删测试）；世界书 48.5KB（中文）/ 47.7KB（英文）。
- **`/epic` 第八卷**：「十二把铁秤」进史诗（中英对齐，锚点 #1730–#1734）；手册更新为八卷口径。

### 验证状态
- `vitest` 497/497；`tsc --noEmit` 0 错误；`vite build` ✅；
- 世界书/指南账本四件套 45/45（ledger #1735/#1736）；
- 全量 `pytest tests/unit` 未跑完；#/drill 未浏览器目验——二次登记同样不背书。

## 2026-11-15 · 验收快问 + 世界书卷十五 + UI 词表全量双语

本条目覆盖 `765d00a` → `bda2092` 八个提交（ledger `#1726` → `#1733`，全部附实测命令）。

### 新增
- **`#/drill` 验收快问**：12 道速测，每题锚真实文件/链接/账本（base_pass_head_fail 语义、wkapi 4224 常量、UNVERIFIED 判词、账本 append-only、BLOCKER 不可人为 override……）；暗金印章封印梯（见习→正式→骑士→铁证），键盘 1-4/Enter，`specproof_drill_v1` 持久化最高分；`bda2092`。
- **`demo doctor`**：`scripts/demo_doctor.py` 一条命令自检演示仓（标签解析/差异范围/需求族/工作树），零 Docker·零网络·零 LLM；`--json` 机读报告；`--strict-clean` 强制脏树转红；`bd0668a`。

### 修复
- **指南幽灵路由**：`USER_GUIDE.md` / `USER_GUIDE_EN.md` §3 曾列 `/mcp`、`/admin/identity`、`/readme`——应用从不挂载这三页；已改为真实路由（`/agent`、`/identity`、`/login`）并新增 `tests/unit/test_guide_route_catalog.py`（6 项断言锁死两边）；`765d00a`。
- **App 外壳整段中文**：skip-link、会话区退出/连接、工作空间选择器、顶栏搜索/主题钮、页脚、404 回落 → 26 个 i18n 词条 + 独立 NotFoundPage；`765d00a`。
- **UI 词表层中英脱节**：`toneMap.ts` / `errorHints.ts` / `stages.ts` / `preflight.ts` 的 gloss 全部随 locale 解析（78 + 51 词条）；Python 三门改读 i18n 表；`785c3cc`、`3f7ce44`。
- **`verdict_channel_parity` 基线红**：`api/ai_summary.py` 写入 `verdict` 字段却不被任何通道声明——如实登记为 `job_summary` 通道搬运工（owner + opaque），门真绿；`785c3cc`。

### 世界书
- **卷十五《未完的路》**：六块空地逐条写「做完长什么样」+ 可考锚点；15.4 史官欠条如实入册（全量 pytest 未跑完也记）；`caefe2c`。
- `/epic` 新增第七卷「未完的路」（中英七卷对齐）；`7807bbf`。
- 世界书 43.2KB（中文）/ 41.9KB（英文）——portfolio-sync 下次自动带新尺寸；`ed35467` 两笔欠条已划掉。

### 验证状态
- `vitest` **497/497 绿**；`tsc --noEmit` 0 错误；`vite build` ✅（Drill chunk 18.66 KB 懒加载）；
- Python 词表 parity 系列全绿（含 #1730 偿清的基线红 verdict_channel_parity）；
- 账本四件套 45/45（本链路每个提交入账前均跑）；
- 全量 `pytest tests/unit` **未**跑（本机内存上限），不声称全绿；
- `#/drill` 未经浏览器目验（build + 单测 + route gate 背书）。

## 2026-11-09 — 初始公开主干汇总

本项汇总了 2026-07-08 至 2026-11-09 的长期落地（见账本 `#1`–`#1541`）。以下是本次集中收尾的代表性变更；历史逐笔记录以 git log 为准，本文件仅列大版本轮廓，不重复抄账本正文。

### 新增
- `specproof ops rollback-migrations` — 回滚数据库迁移（`infra/mysql/migrations/down/*.sql` 从文档变为显式操作；live 限制 `specproof_test*`，`--dry-run` 只读；`c5dc614`）。
- `specproof doctor` — pipeline 内联 preflight 的 CLI 入口（`53043ef`）。
- `specproof mcp tools [--json]` + `docs/operations/MCP_GUIDE.md` — MCP 目录的自助核对与接线指南（`4ebf9a2`）。
- 证据出口审计：certificate/capsule 下载写入 `audit_logs`（`certificate_read` / `capsule_download`，`0def8c8`）。
- §3.1 节点级产物引用：worker 仅对工件节点发 `completed` 帧，随 SSE/stages 折叠为 `artifact_refs`，JobDetail 渲染 chip（`117606e`）。
- §4.2 反例复现：胶囊清单新增 `counterexample_reproduction`；replay CLI 透传（`f0d64c8`, `3a5cd62`）。
- notify-relay 端口 leg、MCP codec、failed_at 契约、Gradle digest 实钉、notify-relay/billing/invoice-cron 观测态分 manifest 钉住等（`#1528` 起累计多批）。

### 修复
- 2026-11-09 后台全量套件（`_fullgate4`, HEAD=1c39946）暴露 **10 例门红**：账本 `#1536` 的一条 CI 通道口令行因 reason/directive 分行而成为 malformed directive（3 例）+ 测量登记表随 `d4232e3`/`c04448b` 行号漂移（7 例：payload census ×4 / FakeResult exit_code / matrix_diff `COMPLIANT` / JobDetail 行）。闭账`9cfd865`，全量绿。
- payload 行号在多次合并中系统性后移——私有门与所有 consumer-可见性登记表从此前向 +1/+N 重新实钉。
- specproof `--to` 演练 gate 红口径统一：full gate 必须在退出码 0 完成后才能记账。

### 安全
- 生产 guard 存在且接通（`storage/config_guard.py` + 对账门）；沙箱"断网 + 非 root + 只读工作区"红线顺应；audit SECURITY.md 随本批新增补充。
- `specproof-nosec` 审计门通过（排除项必须逐行批注）。

### 验证（本次会话内可复现）
- 全量 `pytest tests/unit tests/security tests/fault`：6476/8（pre-fix）→ 9cfd865 未到 finish（停在 80 % — `test_sql_text_static` 停在新 rollback_migrations.py 的 executor 读点；c5dc614 新增、未被全量门覆盖过）；`fd6f450` 登记 SQL 常量门 18/18 绿；`fafb8be`（fd6f450 全量回归 10 例逐条归因后）即 master 的 `_fullgate_v3.txt`：**6528 passed / 10 skipped / 3 warnings（1:10:23）**，数字归属该轮。
- MySQL 隔离双库：本次后续记录跑在 `specproof_test2`（单独实例），产品库 `/test/%` 行差 = 0（会话头尾隔离协议 0 -> 0）。
- 前端：`tsc --noEmit` 干净；`vitest` JobDetail 31/31。
- `ruff` 全绿；`mypy` 直接变更文件零告警。
- 演练：DATA_LIFECYCLE §6.5（rollback-migrations dry-run 三票据，本机实跑）；§6.6（2026-11-09 12:01 MySQL 全量 dump→restore 逐表比对 report，specproof_test2 → `specproof_restore_drill`，已 drop scratch；2026-11-09 12:02 Mongo 250 篇 dump→drop→restore→digest 校验均 passes；产品库 `specproof_phase0` 当次未触碰）
