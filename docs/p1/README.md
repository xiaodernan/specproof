# 并轨决策记录：三个不相关历史根的分支（2026-11-10）

本文件记录把 pre-rebuild 时代（2026-07 ~ 2026-08）的三条远端分支的唯一独有内容
收编进 `master` 的决定过程。三条分支与 master **不共享任何根**（`git merge-base`
为空；master 的根是 `0d85586e`，另两株是 `7d9aaa96` 等），即 `git merge
--allow-unrelated-histories` 不可取；内容逐个评估、逐个落原地，不合并分支历史。

## 源头

| 分支 |  tip | tip 日期 | 说明 |
|---|---|---|---|
| `origin/feature/interview-hardening` | `76285a7` | 2026-08-21 | 287 commits；相对 master 独有文件 **0**；有价值的 fault-scenario 测试早已在 #1550 手工搬回主干 |
| `origin/feature/p1-reliability-kernel` | `a756f53` | 2026-07-14 | 24 commits；8 个独有文件 |
| `origin/release/p0.5-verified-v1` | `4145d95` | 2026-07-13 | 11 commits；2 个独有文件（均为 p1 亦有） |

## 逐项决定

| 内容 | 处理 | 理由 |
|---|---|---|
| `evidence/matrix.py`（p1 + release 共有） | **已收编**（`#1593`），→ `evidence/matrix.py`，带出处 docstring | Requirement-to-Evidence Matrix builder，当时无调用方；annotations 最小现代化以过 mypy strict；行为由 `tests/unit/test_evidence_matrix.py` 钉住（4 条） |
| `scripts/run_differential.sh`（两分支共有） | **已收编为 legacy**（`#1593`）→ `scripts/legacy/run_differential_p0_5_c6.sh`，verbatim body + 出处说明 | P0.5-C6 差分 JUnit harness（demo/spring-backend，写死 `base`/`head-v1` tag）；当前运行真实 demo 的人才可能用得上；`JAVA_HOME` 采用环境覆盖，原 demo refs 仍有效 |
| `docs/p1/p1a-final-report.md` | **已收编**（`#1593`）→ `docs/p1/`，verbatim | 旧分支自己的验收报告（2026-07-13），内容保持原样 |
| `docs/p1/wip-migration-matrix.md` | **已收编**（`#1593`）→ `docs/p1/`，verbatim | 旧库的迁移矩阵快照（来自 `D:/experim/specproof-phase0`）；内容保持原样 |
| `storage/migrations/001_p1_baseline.sql` | **未收编** | master 已有 `storage/migrations/001_job_state_machine.sql`（同序号，同代际演进，含 8 态 ENUM 与 idx_status/idx_worker）；加入会让 001 出现两份互相矛盾的 DDL |
| `storage/migrations/002_failed_terminal.sql` | **未收编** | 该"迁移"实为一句变更说明（FAILED 终态化），已在代码 `_VALID_TRANSITIONS` 与 master 002_outbox.sql 代际里落地 |
| `Dockerfile.api`（p1 单 Dockerfile） | **未收编** | master 已有 `docker/Dockerfile.api`（多服务建案，compose.*.yml 的 `build:` 指向它；镜像语义完整、与当前 app 布局一致） |
| `compose.p1.yml` | **未收编** | master 已有 `compose.phase0.yml` / `compose.production.yml` / `compose.observability.yml` 覆盖同一层 |
| `.github/workflows/quality.yml` | **未收编** | P1-only 触发范围；master 的 `.github/workflows/ci.yml` 承载现行门（mypy/ruff/pytest/集成腿） |
| interview-hardening 全部 | **无需收编** | 相对 master 零独有文件；其有价值内容于 #1550 已搬回 |

## 前提与边界

- 三条分支**不删除**、**不改写**；refs 原样保留在 origin。
- 本次收编是**逐件搬运**，不产生"merge commit"，也不能等价于"分支已合入 master"。
- 上述未收编项不是报错，是胜出选择——master 中的继任者见"理由"列。
