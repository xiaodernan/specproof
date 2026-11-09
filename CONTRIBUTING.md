# CONTRIBUTING.md — 参与 SpecProof

这份指南给任何想参与代码、文档、测试或演练的人。它不假设你在 GitHub 上有提交权；它假设你愿意按证据说话。

## 先读这几份（按序）

1. `README.md` — 产品是什么、怎么跑起来。
2. `docs/operations/PRODUCT_ROADMAP.md` — 现在的优先级和完成事实（每条都有 `[x]`/`[~]`/`[ ]`，附证据）。
3. `docs/operations/DEEP_OPTIMIZATION_PLAN.md` — 数字化记账（ledger），每个 `## #NNN` 对应一笔真实工作。本仓不接受"我觉得完成了"而没有账本/行号证据的提交。
4. `docs/architecture/ARCHITECTURE.md` — 架构与信任边界。

## 环境

- Python 3.12+、Node.js 18+、Docker Desktop（可选，全栈模式需要；轻模式 `pwsh scripts/start_local_light.ps1` 不需要 Docker）。
- GitHub 远端请**不要用 HTTPS + OAuth 令牌**推送涉及 `.github/workflows/*.yml` 的改动——令牌缺 `workflow` scope 会被 GitHub 拒收。改用 SSH：`git@github.com:xiaodernan/specproof.git`。

## 分支与 worktree 纪律

- `origin/master` 是唯一的发布主线；所有改动以 fast-forward 形式进入。
- 多分支开发的收尾要求是收敛：合并进 master 后删除临时分支/ worktree，不留并轨悬空物。
- 不改写已并入的历史（history rewrite 不允许）以"让门变绿"；修复必须是新提交。

## 本地开发循环

```
python --version          # 3.12+
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

- 快速内循环：`.venv/Scripts/python -m pytest tests/unit -m "not integration and not slow" -q`（约 3 分钟）。
- **推送前必须补跑**：`pytest tests/unit tests/security tests/fault`（CI 合并门裸跑；`slow` 标记的 275 例也在）。
- MySQL 后端测试**不要与系统共享 specproof_test**——新机器上建 `specproof_test2` 并改向：
  ```
  $env:SPECPROOF_TEST_MYSQL_DATABASE="specproof_test2"   # 任何 ^specproof_test[A-Za-z0-9_]*$ 都行
  ```
  产品 schema（`specproof_phase0`）等于禁区：隔离协议会挡住，参数不要绕过。
- 后端改动后：`ruff check <changed files>` + `mypy <changed files>`。
- 前端改动后：`cd apps/web && npm run typecheck`（tsc）+ `npm run test -- src/<affected>.test.tsx`（vitest）；全量 `npm run test`。

## 改动的硬性约束

- **不许弱化门**：`tests/*/…gate*`、`conftest.py`、`test_recorded_ledger_sections_do_not_vanish.py`、`security_scanner` 相关都是权力层——遇到它们的红，改产品，不改门。例外：权力层自己逻辑有误才修权力层（且必须先在账本上写明原因）。
- **不许伪造证据**：账本/文档中的 "通过""实测"必须来自真实命令的输出；数字不能抄、不能凑。
- **`.env.example` 与代码默认值字节对齐**：任何新环境变量，三段一起：代码里的 DEFAULT_*、`.env.example` 的注释与值、负责它的 gate。三者不一致＝封回到上一个不一致状态即为回归。
- **不增加未经判别的信任扩声**：新增 claim 之前，先问现场有没有判据；没有判据的 claim 不许写进主干。
- **Refactoring 不删门**：纯格式化提交除外已经明证。

## 提交与账本

- 提交信息遵循现网风格：`feat|fix|docs|style(area): 简述`（中文简述+括号日期）；正文说明里**写明实测**（命令 + 输出数字 + 结论）。
- 非平凡改动必须有 docs/operations/PRODUCT_ROADMAP.md 的订正 + （通常还有）`docs/operations/DEEP_OPTIMIZATION_PLAN.md` 的新 `## #NNN` 节（追加，不重写）；ledger 的 fence 门保障旧节不会消失。
- 提交后 push 走 SSH（见上）。push 会进 master；CI（如果有）会跑全量门。

## 证据标准

任何能让产品在"无人看着"的状态下接手业务的提交，都必须附**可复现的证据**：命令、输出、结论。"我改的、应该没问题"不构成证据。评判争议按"代码不会骗人，数据会骗人"处理。

## 上游之外的执行纪律

- 真实执行不受信仓库的测试是红线，前置限制只能由环境变量显式解除（如 Python lane 的 `SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1`）；在宿主上跑不受信代码 = 红线，不例外。
- `DEEPSEEK_API_KEY`/模型密钥不进仓库；`.local/llm.json`、`.env` 已被 git 忽略；别复制进去。
- 有些工作阻塞等外部事实（pilot 签名、生产停机窗、provider 生产凭证等）：
  遇到时**如实标 ⏳ 阻塞 + 等谁 + 缺什么**，不代领决策。
