# CHANGELOG.md — SpecProof 变更日志

格式约定：按日期列 **可归因的变更**；每条附"证据"行——命令、输出、结论，而非感知描述。本项目**尚无签名的版本标签**（tag），因此未发布 dists 无法引用；所有内容以 git 历史与 `docs/operations/DEEP_OPTIMIZATION_PLAN.md`（数字化账本，每个 `## #NNN` 对应一笔真实工作）为准：`git log --follow docs/operations/DEEP_OPTIMIZATION_PLAN.md` 或上面的账本。

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
- 全量 `pytest tests/unit tests/security tests/fault`：6476/8（pre-fix）→ 9cfd865 全绿（修复后的回归基线）；MySQL 隔离双库 `specproof_test2`：`pytest … -m slow` 相关 16/22 census 文件实跑。
- 前端：`tsc --noEmit` 干净；`vitest` JobDetail 31/31。
- `ruff` 全绿；`mypy` 直接变更文件零告警。
