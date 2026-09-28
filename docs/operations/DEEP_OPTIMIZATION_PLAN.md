# SpecProof 第二轮深度优化实施计划

状态：实施中。日期：2026-09-18。承接 PRODUCT_REFRESH_2026-09-18.md；保留既有代码和实测记录。

目标：让产品更易理解、结论有证据、任务可靠恢复、请求可控，并用定向测试和真实运行证明改进。仅把本轮明确发现、能够在当前仓库验证的缺口标为完成；外部客户试点或模型本身正确率不通过宣传性百分比代替验证。

| 工作包 | 发现的问题 / 实现范围 | 验收条件 | 状态 |
|---|---|---|---|
| P1 验收准确性 | Worker、HTML、证书分别判定；PASS 未强制检查证据和契约覆盖；需统一判定规则 | 空覆盖、缺证据、缺契约行、失败、重复冲突不被判为通过；正例仍通过；有针对性案例评测 | 待实施 |
| P2 任务持久化架构 | 事件、审批、diff 元数据存在内存，重启丢失，事件缓冲无界 | 配置持久化时重启可读；单调序号和有界分页；租户授权先于读取；运行中取消和失败诚实显示 | 待实施 |
| P3 模型请求与用量 | 配置字段混合可能套用错误协议；重复 probe；reasoning 计量可能重复；诊断没有按模型区分 | 协议、显式配置优先级、token 计数准确，配置异常有明确错误，取消/超时有界 | 待实施 |
| P4 前端视觉与体验 | 二级页面仍有技术术语、旧布局、搜索请求过密、空态和失败状态不一致 | 规则/覆盖/评测/服务状态统一视觉，中文说明和下一步、键盘与手机可用，后台不重复拉取 | 待实施 |
| P5 真实结果与恢复 | 进度、计划和报告形状仍有适配缝隙，启动依赖多 | API/页面/任务形状一致，启动自检，缺环境不伪造成功；关键链路真实 smoke | 待实施 |
| P6 文档与交付 | 现有报告是历史清单，没有对应验收状态 | 本文逐项记录实现、检查和未覆盖边界；当前用户可直接启动使用 | 待实施 |

执行顺序：并行实施 P1/P2/P4；主任务实施 P3 与跨模块集成；随后 P5 定向验证，最后更新 P6。

验证策略：只跑改动对应测试。构建只在前端批次完成或修复编译问题时运行；不做无变化的全量回归。真实模型沿用用户指定的 gpt-6-astra / max / Responses，凭据仅从现有服务端配置读取，不输出或提交密钥。

## 商业可用性边界

本轮优先完成可审阅的证据、准确状态、重启恢复、合理性能和使用说明。支付通道、实际收费、客户准确率、生产容量与 SLA 需要独立产品决策和部署验证；不把代码模块存在视为这些目标已完成。

## 实施记录

以下由实施和检查结果补全。
### 2026-09-28：反馈身份、词表与结构性债务（#117 / #121 / #115b / #118 / #122）

以下每一行的数字都来自本机当轮的门输出或运行自己印出的页脚，不引用未读过的运行。

| 单位 | commit | 兑现了什么 | 证据 |
| --- | --- | --- | --- |
| #117 | `f1fef07` | 四份手抄 `/auth/me` 访问 body 收进 `ui/useRoleAccess.ts` 一处，页面只留自己的角色集合 | 五臂见证 5/5 按事前预测精确翻红（第一轮 W3 预测 2 红实到 3 红，整树回滚后重新按「谁读这个值 + 执行顺序」预测才对） |
| #72 | `97c647b` | 第一次跑到自己页脚的全量合并门入档，数字原样记录 | `2 failed, 3259 passed, 5 skipped in 1703.64s`、`MERGE_EXIT=1` |
| 门的卫生 | `8a7d209` | metrics 测试补 `server_close()`：`-W error` 下未关闭的监听 socket 会把全量门判死 | 改前即上面那两条红；改后单文件 6 passed，随后全量门 `3261 passed / 5 skipped / MERGE_EXIT=0`（`11a93be` 入档） |
| #121 | `cb55acd` | 投票在 `/auth/me` 回答之前提交时不再用渲染期快照当 `created_by`——那会把一个真人计成两个人 | `tsc` 0、`vitest` 0（45 文件 / 353 用例）、`vite build` 0、访问形状门 10 passed；反向臂（submit 回到 `who`）恰好命中预测的两个读者 |
| #115b | `9b3fa92` | 评审人框、它的说明文字、以及「我当前这一票」的台账查找，三者统一读被记下来的那个身份 | 同上三门 0；`9b3fa92` 的全量门 `3266 passed / 5 skipped / 1293.43s / MERGE_EXIT=0`（`f5963e4` 入档） |
| #118 | `84e02e8` | 二值三元式不再替未知判定编造含义（任何非 `accept` 都被画成「打回」）；`accept/reject` 词表由声明处推导 | `tsc` 0、`vitest` 0、新门 `test_feedback_verdict_parity.py` 与严重度门 11 passed |
| #122 | `9c76a94` | 手写 `<table>` 的 5 站点／4 文件收成「债务名册」：新增被拒，删掉一处却不同步名册也被拒 | 未变异 8 passed；植入一个临时页面恰好 1 红并点名该文件；撤除后 13 passed |
| #119 | `84224c9` | `/auth/me` 每次挂载只问一次：读同一凭证的读者共享**在途**的那一次请求（原先侧栏切换器 + 页面角色门各问一次） | 改前实测 2 读者 = **2 次请求**，改后 = **1 次**；`tsc` 0 错、`vitest` 46 文件 **365 passed**、`vite build` ok；`test_access_role_parity.py` **11 passed**（+1 条由源码推导读者与凭证读法的条款）；探针 3/3 各自按预测判红并按字节还原 |

这一轮读到的三条产品事实（不是风格问题）：

1. `acceptance_rate` 的「人」由请求体自报的 `created_by` 决定，而提交发生在渲染期身份的快照上；
   `/auth/me` 已在同一页面被读过，却没人把它用于记录。#121 修的就是这个错计。
2. 同一句「你当前的一票」的查找键与被写入的键曾经是两套值，登录用户看不到自己那一票（#115b）。
3. 词表由三个主人各写一份（存储 ENUM、`api.ts` 联合、渲染标签），没有门把它们绑在一起；
   今天量得三者相等，所以这条门是**预防性**的，本文件不把它写成正在发生的错误。

### 仍欠的工作（按可直接接手的顺序）

1. `9c76a94` 之后的全量合并门**还没跑**（这条计划的数字只覆盖到 `9b3fa92`）。
   跑法：`pytest tests/unit tests/security tests/fault -q -p no:randomly -W error` 写入
   `w112/merge_<sha>.log`，再用 `w112/record_merge_run.py <log> <unit>` 入档——该脚本缺页脚即拒写，
   且必须在下一个提交之前运行（它按 `git rev-parse HEAD` 取归属）。
2. #122 名册里的 5 个站点逐个迁到 `ui/Table`，一处一个单位；每迁掉一处都要同步删名册一行
   （门因此翻红是它在尽职，不是缺陷）。「长理由撑破表」这一条**必须先在浏览器里实测**，
   在测到之前本计划不声称它成立。
3. ✅ **已完成（`84224c9`）**：#119 —— `/auth/me` 的 8 个读取点还在（4 个经 `useRoleAccess`，
   另有 `App.tsx`、`identity/TenantSwitcher.tsx`、`pages/Login.tsx`、`api.ts`），但它们现在
   **共享在途的那一次请求**：`api.ts::getAuthMe` 以凭证为键复用尚未落地的读；落地的答案**不保留**，
   所以下一次挂载照旧重读（服务端撤销角色会在下一次导航生效，而不是被缓存冻结一整个会话）。
   ⚠️ 原计划写的「显式失效入口」在实现时换成了**把凭证本身当键**：登录 / 切换租户 / 退出 /
   OIDC 回调每一种换凭证都是不同的键，于是「忘了调用失效」这个失败模式不存在。
   门谓词按计划改为由源码重新推导（见 `tests/unit/test_access_role_parity.py` 的
   `test_auth_me_is_read_through_one_shared_call`），不是手写豁免名单。
4. ✅ **已完成（`0099c96`）**：#120 —— 全量门用时在 1293s–1704s 之间摆动（本机四个数据点：
   1703.64 / 1535.42 / 1587.78 / 1293.43s）。已把「谁需要 MySQL」印进每次 pytest 的输出：
   扫描名册（实测 **16** 个文件，`\b` 锚定使三处 `FakeMySQLStore()` 不入册）+ 本次跑了几个 +
   各自 wall-clock 与会话占比；「空名册」与「一个都没跑」各印不同的话，绝不沉默。
   见 `tests/conftest.py`、`tests/unit/test_mysql_usage_report.py`（7 passed）与 ROADMAP §28。
   ⚠️ census 只回答静态可判定的那一半（谁需要 MySQL）；「是不是负载问题」仍需同机对照运行，
   那是另一个单位——本文件不把它算作已完成。
5. 需要产品决策或授权、因此**故意没做**的：#113 的路由分类错位、服务端强制
   `created_by == principal.user_id`（改的是线上权限语义）、产品库 `specproof_phase0` 中
   822 行无归因审计残留的清理。
6. **CI 复活后暴露的 5 个红 job**（`2fb4612` 之前 CI 文件本身解析失败，所有 job 从未创建过，
   详见 ROADMAP §28.1）：`bandit B608` 7 处 medium（如 `storage/mysql.py:732`）、
   `tests-with-infra` 的 `docker compose … up -d --wait`、`tests-no-infra`、`eval-golden-cases`
   的 Maven cache 播种、`openapi-schema-diff`。`lint-type` 已绿。逐个修，每个都要把运行号与
   job 结论写回本节。

### 2026-09-29：同一份文本在另一套操作系统上被读错（#126 第一批）

`tests-no-infra`（CI run `36436188582`，ubuntu-latest）实测 **10 failed / 3261 passed / 27 skipped**。
这一批修掉其中**两条真正的跨平台缺陷**与**两条平台假设**，剩下 6 条按下面的口径归入下一批。

| 分类 | 站点 | 量到的事实 | 这一批做了什么 |
| --- | --- | --- | --- |
| 生产缺陷（POSIX） | `craft/spec.py` 的 `parse_spec` | Linux 上 `stat()` 对超过 255 字节的**单个路径分量**回 `ENAMETOOLONG`，而 `Path.is_file()` 只吞 ENOENT/ENOTDIR/EBADF/ELOOP ⇒ 一条内联 JSON 任务规格不是「找不到文件」而是**当场崩**；CI 原文 `OSError: [Errno 36] File name too long: '{"id": "task-01", ...}'` | 文件系统探针收进 `_existing_file()` 并吃 `OSError`/`ValueError`；解析顺序不变（真实路径仍优先） |
| 生产缺陷（POSIX） | `mcp/tools.py` 的 `parse_verify_stdout` | `Path(...).name` 只按**运行平台**的分隔符切；Linux 上的 MCP 服务读一份 Windows 报告时，capsule 字段拿到的是整条服务器端路径而不是文件名（CI：`['C:\\tmp\\re...CTION-01.zip']`） | 新增 `_report_basename()`，两种分隔符都切；并加一条 AST 门：解析器里再出现 `Path(...).name` 即红 |
| 测试的平台假设 | `tests/unit/test_repo_safety.py` 的 junction | `cmd.exe` 在 Linux 不存在 ⇒ 抛 `FileNotFoundError` 而不是走那条 `pytest.skip`，skip 分支从未在另一平面上取到值 | 链接构造改为按平台取（Windows junction / POSIX symlink，`agent/repo_safety.py:186` 的 `is_symlink()` 本来就认 POSIX 符号链接）；两种都造不出来才 skip，且 skip 话术点名是哪一种 |
| 测试的诊断缺失 | `tests/unit/test_slow_marker_tagging.py` | 子进程 `pytest` 被会话级 MySQL 隔离检查 `pytest.exit` 掐死；父会话 27 skip、子进程却要求 schema 可用——两者看到的**环境不一致**，而原来的断言话术里连子进程继承了什么环境变量都没印 | 断言话术先印 `exit=` 与子进程继承的 `MYSQL_DATABASE` / `SPECPROOF_TEST_MYSQL_DATABASE`；真因未定，不在这一批编造 |

见证（`tests/unit/test_platform_independent_reading.py`，11 格）：Linux 的失败没法靠「换台机器跑」在 Windows 上复现，所以在**故障进来的那道缝**上装它——把 `Path.is_file` 换成对超长分量抛 `ENAMETOOLONG` 的实现。夹具会回报它拒绝过哪些名字，依赖它的每一格都断言这个回报非空；不装这一句，JSON 那格会在旧代码上照样绿（我第一次就踩了这个坑：夹具声明了却忘了请求它）。

- 修好的平面：**11 passed**；旧平面（`git worktree` 取 `3d5212e`，把这份测试复制进去）：**3 failed**，红的正是事前点名的三格（两格 `OSError ... File name too long`、一格 `Path(...).name at line(s) [75]`），其余 8 格在旧平面照绿。
- ⚠️Windows 路径那一格在 Windows 上**旧代码也是绿的**——这台机器切得开反斜杠。它只有在 Linux CI 上才会翻红，所以那条 AST 门才是跨平台都能守的那一道；本文件不把它写成「本地已复现」。
- 受影响面定向跑：`test_repo_safety / test_mcp_server / test_bench_craft / test_slow_marker_tagging / test_craft_spec / test_craft_schemas / tests/security/test_injection_matrix` = **188 passed**；`ruff check` 五个改动文件 0 错；`mypy craft/spec.py mcp/tools.py` Success。

**上一节留给下一批的那句话已被实测否证**（写在这里而不是删掉，因为它替读者编过一次含义）：`test_craft_stream`、`test_craft_loop_metrics` 并不是「Linux 上多做一次模型调用／编辑没落地」。在 python:3.12-slim 容器（Python 3.12.14，`-p no:randomly`）里单跑这三条 = **1 failed, 2 passed**，红的只有 `tests/fault/test_output_flood`；CI `36456722364` 上这两条也随第一批一起转绿。⇒ 它们的红来自 CI 的**随机顺序 + 环境**，不是平台性质；本项目的判断口径是「先在新平面复现，再判」，这一条复现不了，所以不改生产代码。

### 2026-09-29：超时留下的半截输出被当成「没输出」（#126 第二批）

CI `36456722364`（= `11ef7a9`）`tests-no-infra`：**4 failed / 3293 passed / 27 skipped，602.57s**（承接上一批的 10 failed / 3261 passed）；`security`、`lint-type`、`openapi-schema-diff` 三个 job 在同一个 run 上 success ⇒ 上一批的六条修复由 CI 确认，不是我自己推的。

剩下 4 条里第一条是**真的生产缺陷**，两条是**测试自己的前置**，一条是新出现的**顺序相关**：

| 红 | 判据 | 这一批做的 |
| --- | --- | --- |
| `tests/fault/test_output_flood.py::test_timeout_flood_preserves_bounded_partial_output`（`assert False is True`，快照里 `SandboxResult(exit_code=-1, stdout='', stderr='', error='execution timed out after 3s', truncated=False)`） | 容器探针：`subprocess.run(text=True, timeout=...)` 在 POSIX 超时路径抛出的 `exc.stdout` 类型实测是 **bytes**（Windows 会重跑 `communicate()` 拿到 str）。`sandbox/runner.py` 两处按 `isinstance(..., str)` 读 ⇒ Linux 上被超时杀掉的活儿**一条输出都不留**。docker 分支是生产默认模式 ⇒ 常见路径也在丢证据 | 加 `sandbox.runner.timed_out_partial()`：bytes 按 **UTF-8 + errors="replace"** 解，str 原样，None → 空串；两个分支改走它。普查又找到第三处同样的写法：`scripts/bench_swebench.py`（超时测试的 output_tail 在 Linux 上会退化成 `<timeout after Ns>`，评测行没有证据），一并改 |
| `test_slow_marker_tagging.py` 两条（`exit=1`，子进程正文：`MySQL test isolation check failed: test schema 'specproof_test' is not usable: OperationalError(2003, "Can't connect to MySQL server on 'localhost' ([Errno 111] Connection refused)")`） | 上一批加的诊断把这轮的**原因印出来了**，不再靠猜：子进程是 `--collect-only`，只做收集却被 `conftest._apply_mysql_isolation → prepare_test_schema` 要求一个活着的 MySQL；而 `ci.yml` 里根本没有 `MYSQL_DATABASE`/mysql service，所以那句 `MYSQL_DATABASE='specproof_test'` 是**父进程 conftest 自己改写过 env**（`enforce_test_database()` 决定 redirected 时写回 `os.environ`）之后被子进程继承的 ⇒ 我的诊断读的是改写后的值，分不清「CI 给的」和「conftest 自己写的」，这条口径要在下一批修 | 尚未修，见下面「下一批」 |
| `test_craft_loop_jobs.py::test_supervisor_cancel_wins_over_leased_worker`（`assert 'STUCK' == 'CANCELLED'`） | 这一轮新出现的红，上一条 run 的 10 条里没有它 ⇒ 顺序/时序相关，不能按「平台缺陷」记账 | 尚未修，见下面「下一批」 |

见证（新文件 `tests/unit/test_timeout_partial_output.py`，9 例）——**两平面都跑过**：

- 修复后：Windows（本机 .venv，`-p no:randomly`）**18 passed**（9 新 + `test_output_flood` 9）；Linux 容器同一组 **18 passed / RC=0**（57.32s）。
- 旧平面（`git worktree` 指 `11ef7a9`，把新测试文件拷进去单跑）：**7 failed / 2 passed**，事前预测逐条命中——4 条行为例（local/docker/flood/cjk）红在断言、2 条 `timed_out_partial` 单元例红在 AttributeError、普查例红在「列出 3 个站点」；绿色的正是预测的两条（kill 前无输出 → `""` 而非 `"None"`；普查下限例）。旧平面红在 **Windows 上一样成立**，因为模拟打在「runner 读到的异常对象」这个故障实际发生的接缝上，不依赖跑它的是什么 OS。
- 普查例自己带下限（`test_the_census_actually_reads_the_files_it_claims_to_guard`）：人口必须含 `sandbox/runner.py`、`scripts/bench_swebench.py`，且「读 partial 的 TimeoutExpired 块」≥ 3 —— 上一批学到的：一个只数到自己看不见的空集合的门，等于没门。
- 定向门：`ruff check` 三个改动文件 0 错（一处 `.encode("utf-8")` 被 UP012 判多余，改成 `.encode()`，断言的口径不变：解码头一段注释写明「runner 必须按 UTF-8 解，不按机器 locale」）；`mypy sandbox/runner.py scripts/bench_swebench.py` Success。

**下一批（可直接接手，按顺序）**：
1. `--collect-only` 的子进程不该要求活着的 MySQL：`conftest._apply_mysql_isolation()` 在纯收集时跳过 `prepare_test_schema()`（收集不写库，`blocked` 的 fail-closed 判决保留）。本地就能复现 CI 的 111 拒连，不用等 CI（本机已实测：`exit=1`，正文是 WinError 10061 拒连，与 CI 的 `[Errno 111]` 同一件事的两个平面）：把 `MYSQL_DATABASE=specproof_test` + `MYSQL_HOST/MYSQL_PORT` 指向一个没人听的端口，跑 `pytest --collect-only tests/unit/test_baseline.py` ⇒ 现在 `exit=1`，修后 `0`/`5`。同时把 `test_slow_marker_tagging.py` 的诊断改准：它必须报**子进程实际看到**的 env（`proc` 的 argv/env），不能报父进程被 conftest 改写后的 `os.environ`。
2. `test_supervisor_cancel_wins_over_leased_worker` 的 `STUCK` vs `CANCELLED`：先问「谁写这个状态、按什么顺序」，再决定是竞态还是判据；不许用 retry 蒙。
3. CI 还有两个 job 红着：`tests-with-infra`（`docker compose up -d --wait`，minio unauthorized）、`eval-golden-cases`（exit 126 / Maven cache 播种）。

