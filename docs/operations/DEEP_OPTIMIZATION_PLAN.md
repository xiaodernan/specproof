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

**当时定下的下一批（第 1 项已在下面「#126 第三批」一节落地，其余项以文末的「下一批」为准）**：
1. `--collect-only` 的子进程不该要求活着的 MySQL（**量过、已复现、这一轮没落地**，草稿在 `.scratch/m126c-wip/`：`conftest.py.fixed` + 见证文件）：
   - 本机复现拿到与 CI 同一条 refusal，不用等 CI：`MYSQL_DATABASE=specproof_test MYSQL_HOST=127.0.0.1 MYSQL_PORT=3399 pytest -o addopts= tests/unit/test_baseline.py --collect-only` ⇒ `exit=1`，正文 `MySQL test isolation check failed: test schema 'specproof_test' is not usable: OperationalError(2003, ... [WinError 10061])`（CI 那条是同一件事的 `[Errno 111]` 面）。机制：`enforce_test_database()` 决定 redirected 时会把 `os.environ["MYSQL_DATABASE"]` 写回（conftest:213），所以子进程天生在 `dedicated` 这一支——也正是唯一会调 `prepare_test_schema()` 的一支。
   - 改法（4 行）：`_apply_mysql_isolation(config)`，`config.getoption("--collect-only")` 为真时跳过 `prepare_test_schema()`，`blocked` 的 fail-closed 判决保留（那条讲的是配置不是连通性）。
   - 第一次跑就把**整个 session 打死**：改了签名忘了调用点 ⇒ `TypeError: _apply_mysql_isolation() missing 1 required positional argument: 'config'`，INTERNALERROR、0 条收集。教训：conftest 的 `pytest_configure` 是装载期守卫，每个子进程都 inherit，改它的第一步必须是**先跑一条 collect-only 再看 exit code**，不是先写见证。
   - **没落地的原因是一条成本的实测**：把两条用例和邻居一起跑 = **759.60s / 4 failed, 1 passed**，而且红的方式里有一条不是我的用例：`test_slow_marker_tagging.py::test_known_slow_module_is_tagged_slow` 报 `subprocess.TimeoutExpired: ... 'tests/unit/test_agent_runtime.py' '-m' 'slow' '--collect-only' timed out after 180 seconds` ⇒ 在被我自己那几个子进程压着的 Windows 机器上，`test_agent_runtime.py` 的纯收集就要 >180s，这是既有 #53 门自身的时间脆弱性，与本修复无关。同时我新文件里的「真跑仍被拒」对照用例是成本大头（拒连 ⇒ 三次重试迁移 + 5s/10s 睡，单个 child 实测 100–190s）。我那两条自己的用例为什么红，日志只留下了末段，**我没读到原因，所以不写它绿**。
   - 下一轮的做法（已按这次实测省钱）：不要再 spawn「真跑」对照（那条 100s+ 就是它）；collect-only 的豁免用一个极小模块的 `--co` child + 一条 in-process 分支测试（喂一个 `getoption` 桩）来钉，整个文件目标 <30s；并且单独处理 `test_slow_marker_tagging.py` 的 180s 预算——要么换掉它探测的重模块，要么把预算按实测抬起来，不许靠 retry 蒙。

### 2026-09-29：`--collect-only` 不再要活着的 MySQL（#126 第三批，上一条的第 1 项已落地）

按上一轮定下的省钱做法做完了，成本目标也达成了：**新文件 4 例全绿 8.33s**（上一轮那批是 759.60s），差别全在「不再 spawn 真跑对照」这一条决定上。

- 生产改动：`tests/conftest.py` 的 `_apply_mysql_isolation(config)` 只在 `--collect-only` 时跳过 `prepare_test_schema()`；隔离判决本身照做（redirect 仍写回 `os.environ`，这条很重要——豁免如果连判决一起跳，孙子进程就会看到未隔离的环境），`blocked` 仍以 `ExitCode.USAGE_ERROR` 结束 session。
- **一个必须先量的细节**：`Config.getoption(name, default=...)` 对不认识的选项名**静默返回 default**（实测 pytest 9.1.1：`PROBE_KEYS ['collectonly', ...]`，`--collect-only` 与 `--co` 都解析成 True，`collect_only` 是 `MISSING`）。⇒ 拼错选项名不会报错，只会让豁免永远不生效，看起来像「修了但 CI 还红」。所以代码里用 dest 名 `collectonly`，而**桩必须不像 pytest 那样宽容**：见证文件的 `_Config` 只认实测过的那三种拼写，其它名字 raise，否则我的桩会把「问了一个没人回答的问题」也测成绿。
- 见证（新文件 `tests/unit/test_collect_only_needs_no_db.py`，4 例）：三条 in-process 分支例（collect-only 只走判决不走迁移／真跑两步都走／`blocked` 在只做收集时仍结束 session 且 rc=USAGE_ERROR）+ 一条**真 child** 例（带 `MYSQL_DATABASE=specproof_test MYSQL_HOST=127.0.0.1 MYSQL_PORT=3399` 的 `--collect-only` 子进程必须 exit 0 且正文不含那句 refusal）。child 例是承重的那条：in-process 例喂的是我自己的 `getoption` 桩，量不出选项名拼写对不对；只有真 child 会。
- 两平面实测：修复后 `4 passed in 8.33s`（child 7.83s）；旧平面（`git worktree` 指 `1225b76` 再拷入新文件）`4 failed in 53.91s`，事前预测的形状 4/4 命中——3 条 in-process 例红在 `TypeError: _apply_mysql_isolation() takes 0 positional arguments but 1 was given`（我预测的是 `missing 1 required positional argument`：**TypeError 这个形状中了，具体措辞没中**，因为旧签名根本没有参数），child 例红在 refusal 断言并原样印出 CI 那句正文（`Exit: MySQL test isolation check failed: ... OperationalError(2003, ...)`）。
- 一处自我否证：我按「冷跑 43s」把本文件加进了 `SLOW_TEST_MODULES`，随后的重测是 **9s（热）/ 43s（刚改完代码的那次）**，文件里 child 也只有 7.83s ⇒ 8.33s 不属于「支配 wall-clock」，那条 slow 登记已撤回。教训：成本要用被登记的那个跑法量（在 suite 里），不能用一次性手敲命令的冷启动。
- 已有门抓到的两条红（都不是我预测的，且都属「新测试自己也是一个站点」这一类）：
  1. `test_mysql_isolation_contract.py::test_the_contract_runs_before_any_test_writes` 把「守卫接在 hook 上」钉成子串 `"_apply_mysql_isolation()"` ⇒ 我加参数就红。已改成从 `pytest_configure` 的 AST 取那个 Call 节点：必须恰好一处，且实参必须是 `config`。新的钉法比旧的强——子串说不出「守卫现在依赖 config」这个真约束，也会在无害的重排格式上假红。
  2. `test_subprocess_text_encoding.py::test_the_rest_of_the_repo_cannot_grow_the_debt` 报 **55 unpinned child captures (ceiling 54)**，多出来的那一条是 `.scratch/m126c-wip/test_collect_only_needs_no_db.py:49`——**我自己上一轮留下的未跟踪草稿**。这条普查走的是工作树而不是 git，所以它会把任何未跟踪 scratch 算进仓库债务；CI（全新 clone）永远复现不出这个数。草稿已被落地文件取代，删掉后回到 54。**口径**：本地量到的 debt 计数若含未跟踪文件，就不是可归因的仓库数字，要按 git 平面重推，不能靠抬 ceiling 蒙过去。
- 定向门：`ruff check` 三个改动文件 0 错；`tests/unit/test_mysql_isolation_contract.py + test_collect_only_needs_no_db.py + test_subprocess_text_encoding.py` = **29 passed in 19.80s**；这一批的 affected-area 跑里 `test_slow_marker_tagging.py` 两条也是绿的（child 没再撞那句 refusal）。

**当时定下的下一批（第 2 项已在下面「#126 第四批」一节落地，其余项以文末的「下一批」为准）**：
1. `test_slow_marker_tagging.py` 的 180s 预算：上一轮在被我自己 spawn 的子进程压着的机器上，`tests/unit/test_agent_runtime.py` 的**纯收集**就 >180s ⇒ 这条门有时间脆弱性。要做的是先量（无并发时单跑那条 child 一次，记下真实耗时），再决定是换探测目标（用一个小的重模块等价物）还是按实测抬预算；不许靠 retry 蒙。
2. 同一文件里那条诊断的口径要修：assert 消息打印的 `MYSQL_DATABASE` 是从**子进程自己的环境**读的，而 conftest 在 redirected 分支会改写它 ⇒ 「runner 给的」和「conftest 自己写的」分不清。做法：`enforce_test_database()` 改写前先留一份继承值（模块级变量或 `SPECPROOF_INHERITED_MYSQL_DATABASE`），诊断与 refusal 消息都报两个值。
3. `test_craft_loop_jobs.py::test_supervisor_cancel_wins_over_leased_worker` 的 `STUCK` vs `CANCELLED`：先问「谁写这个状态、按什么顺序」，再决定是竞态还是判据；不许用 retry 蒙。
4. CI 还有两个 job 红着：`tests-with-infra`（`docker compose up -d --wait`，minio unauthorized）、`eval-golden-cases`（exit 126 / Maven cache 播种）。
5. 本轮新增的一条口径：`gh run view --log-failed` 只能拿到**末段**，要按用例取正文就得 `--job <databaseId>`；自己 spawn 的子进程日志要写进被挂载的目录（`.scratch/`），否则会像这次一样只剩 tail 而丢掉失败原因。

### 2026-09-29：一句 refusal 必须说得出「这个库是谁定的」（#126 第四批，上一条的第 2 项已落地）

上一批的表格里写着：CI 的 `--collect-only` 红打印了 `MYSQL_DATABASE='specproof_test'`，而 `ci.yml` 根本没有这个变量 ⇒ **读环境本身分不清**「runner 给的」和「我上面那个 conftest 改写的」。这一批把那句问话变成那句回答。

- 生产改动（三处，都在 `tests/conftest.py`）：`enforce_test_database()` 的 redirect 分支在改写 `MYSQL_DATABASE` 的同时写下 `SPECPROOF_MYSQL_DATABASE_REWRITTEN_FROM=<被替换掉的那个值>`；`_apply_mysql_isolation()` 在**任何改写之前**记下 `(MYSQL_DATABASE, 那个变量)` 到 `MYSQL_DATABASE_HANDED_TO`；`mysql_database_provenance()` 把这一对念成一句人话，句尾要么写 `(no ancestor conftest rewrote it)`，要么写 `(an ancestor conftest rewrote it from 'specproof_phase0')`。这句话现在出现在两处人都会读的地方：结束 session 的那条 `pytest.exit` refusal，以及 `test_slow_marker_tagging.py` 的 assert 消息（那条消息原来只是把两个环境变量抄出来，抄的还是被改写后的值）。
- 见证：新文件 `tests/unit/test_isolation_provenance.py`，5 例，全部走真守卫或真判决函数（`_apply_mysql_isolation` / `enforce_test_database`），**没有一例是自己手填那条记录再念出来的**——否则测的就不是生产在哪里读它。全绿：单跑 `5 passed in 1.60s`（冷跑 5.12s）。
- 两条变异臂，跑之前先把「哪几条该红、红成什么形状」写死：
  - A 臂：删掉 redirect 分支写 marker 那一行 ⇒ 预测**只有** `test_the_process_that_rewrites_the_schema_leaves_the_trail_it_handed_over` 红。实到 `1 failed, 4 passed`，红消息自己说清了断的是什么（`... got None`）。
  - B 臂：把守卫入口的采集换成 `(None, None)` ⇒ 预测 3 红（dedicated 名 / 子进程继承 / refusal 带话），且「未设置环境」那例与「不经过守卫」的那例（A 臂那条，直接调 `enforce_test_database`）应保持绿。实到 `3 failed, 2 passed`，红的三条名字与预测逐条一致。
  - 两臂都从 `.scratch/conftest.py.bak126e` 原样还原并 `sha256` 对过（`2afee7cd…` 两行相同），还原后再跑一次未变异对照 = `5 passed`。
- 一处自己抓到的见证缺陷：A 臂第一版是 `os.environ[marker] == ...`，那样删掉写入会变成 **KeyError**（红但没有主张）。改成 `.get()` 并在消息里带上实际读到的值，红才说得出「断的是这条trail」。承接本仓库已有的口径：断言要能自己说话。
- **本轮故意没跑满的一条**：`test_slow_marker_tagging.py` 改了消息，它会 spawn 两条 `--collect-only` 子进程，而此刻 `3ad9310` 的全量 lane 正在独立 worktree 里跑（13%）。并发跑它既会把 lane 的 wall-clock 灌水，又会亲手复现上一条第 1 项记的那次 >180s 脆弱性 ⇒ 只跑了不 spawn 子进程的两步：`--collect-only` 该文件 = `2 tests collected in 1.64s`（证明新的 `import tests.conftest` 与消息路径在装载期不炸），以及直接把消息念出来 = `MYSQL_DATABASE='specproof_test' as this process was handed it (an ancestor conftest rewrote it from 'specproof_phase0')`。两条子进程仍未在无并发平面上重跑，记在下一批第 1 项。`ruff check` 四个改动文件 0 错。

**下一批（可直接接手，按顺序）**：
1. 先补两条没量的：① `test_slow_marker_tagging.py` 在无并发平面上单跑（改了消息之后必须重跑）；② `3ad9310` 与这一批 commit 的全量 lane 数字（lane 在 `/tmp/sp-gate126d.log`，读汇总行，不许引成别的 commit 的数）。
2. `test_slow_marker_tagging.py` 的 180s 预算：先量无并发时 `tests/unit/test_agent_runtime.py` 纯收集的真实耗时，再决定换探测目标还是按实测抬预算；不许靠 retry 蒙。
3. `test_craft_loop_jobs.py::test_supervisor_cancel_wins_over_leased_worker` 的 `STUCK` vs `CANCELLED`：先问「谁写这个状态、按什么顺序」，再决定是竞态还是判据；不许用 retry 蒙。
4. CI 还有两个 job 红着：`tests-with-infra`（`docker compose up -d --wait`，minio unauthorized）、`eval-golden-cases`（exit 126 / Maven cache 播种）。
5. 口径沿用：`gh run view --log-failed` 只能拿到末段，按用例取正文要 `--job <databaseId>`；自己 spawn 的子进程日志写进被挂载的目录；本地量到的 debt/provenance 计数若含未跟踪文件就不是可归因的仓库数字。
### 2026-09-29：一个叫 `query` 的参数不是「SQL 文本」的证据（#127）

起因是一条**假阴性**：`#125` 那轮的探针 P2 把 `storage/mysql.py::search_jobs` 变异成
`f"...{where} AND id = '{query}'"`（把一个本该走绑定参数的值改成拼进 SQL 文本），而当时的判据
因为参数**名叫 `query`**（在 `_EXECUTOR_PARAMS` 里）就把它当常量 ⇒ 注入形状被放行。这一批把口子补上，
规则写成一句可判的话：**按名字不是证据，按位置才是**。

- 改动（`tests/unit/test_sql_text_static.py`）：`forwarding` 从「所有参数名的集合」变成
  `Mapping[str, bool]`——参数只有在**被整个作为第一条实参**交给执行器时才算「转发」（责任上移到调用者），
  否则它是数据。判定这一点的 `_bare_parameter()` 只认三种形状：裸名、两侧同名的三元式、
  `.replace(...)` 链；`'SELECT ' + statement` 这种拼进更大表达式的不算。
- 见证（同文件新增 3 例）：① 只把数据插进被执行文本的参数必须被拒（P2 的形状）；
  ② 整参转发必须被放行（义务落在调用者）；③ 转发边界（`.replace` 算、`+` 不算）。
  两平面读数：新判据 **3/3 绿**；旧判据 **2/3 红**（`old RED … got {'cur': False, 'query': True}`、
  `old RED … forwarding said True`）。第③例在旧判据下也绿——它钉的是**边界**而不是缺陷修复，
  如实记，不当成两平面。
- 真实注入臂（不是内存里的字符串，是真改文件）：把上面那种注入写进 `storage/mysql.py`
  （锚点命中 **1**，改后 `ast.parse` 通过）⇒
  - 新判据：**1 finding**，原文点名该行；
  - 旧判据：**0 findings**（漏掉这一行）；
  - 真门跑：`1 failed, 11 passed in 35.28s`，红的正是 `test_no_sql_text_reaches_an_executor_without_proof`。
  - 按字节还原：`shaMatch=True / sha=e6d4efad8122d310 / mutationStillPresent=False`，还原后 `12 passed in 38.94s`。
- 定向门：`ruff check tests/unit/test_sql_text_static.py` **All checks passed**（顺带清掉接手的草稿里
  `F821`（`Mapping` 没 import，全靠 `from __future__ import annotations` 才没在运行期炸）、`SIM102`、`C420` 三条；
  这是"被改的测试自己也是一个站点"的又一例）。`mypy` 配置 `exclude = ["tests/", ...]`，直跑该文件的
  2 条报错都在排除面内且是既有报错，不计入本批。
- **诚实边界**：这一批**没有**扩大对现存代码的判定范围——在未变异的仓库上，新旧判据产出同一份 findings
  （`storage/migrations.py` 那条已登记的）。它买下的是**将来**同类注入不再被参数名骗过；本文件不把它写成
  "修好了一个正在发生的漏洞"。

**这一支的下一步（与并行的 #126 那一支互不重叠）**：接 `#122` 的手写 `<table>` 债务名册——一处一个单位，
迁移到 `ui/Table` 并同步删名册行（名册门翻红是它在尽职）。前端三门前置：`tsc`／`vitest`／`vite build`。
### 2026-09-29：#122 第一处——反馈台账走共享表格（5 处 → 4 处）

- 站点：`pages/FindingDetail.tsx` 的反馈台账表（原 212 行）。名册当初就是为这个形状写的「长理由撑破表」——
  `table.data` 没有溢出容器，评审人粘一整段不换行的理由会把整页撑宽；`ui/Table` 的
  `.ui-table-wrap { overflow: auto }` 把它关在面板里滚动。
- 迁移：`<Table rows={data.rows} rowKey={(r) => r.id} columns=[评审人/判定/对应风险/理由/时间] />`，
  五列既有文案与 `mono` 观感保留；空态仍走页面自己那句「还没有人提交过反馈…」
  （`ui/Table` 的默认空态会换掉这句诚实话术，所以不交给它）。
- 量到的名册变化：`hand_rolled_table_sites()` **5 → 4**（FindingDetail 从 2 处降到 1 处，文件仍在册——还剩一处 kv 表）。
- 见证（`src/pages/FindingDetail.test.tsx` 新增 1 例，理由用 300 个不换行的「证」字）：
  `cell.closest(".ui-table-wrap")` 必须非空、`cell.closest("table.data")` 必须为空。
  两平面：新平面 **1 passed**；旧平面（`git checkout HEAD -- src/pages/FindingDetail.tsx`，测试文件不动）
  **1 failed**，红在事前预测的那一行 `FindingDetail.test.tsx:482: expect(cell.closest(".ui-table-wrap")).toBeTruthy() → null`；
  按备份还原后 diff 为 `32 insertions / 17 deletions`，与迁移本身一致。
- 定向门：`vitest run src/pages/FindingDetail.test.tsx` **25 passed**；`tsc --noEmit` **exit 0**；
  `pytest tests/unit/test_hand_written_table_ledger.py` **8 passed**（名册没有说谎）。
- **诚实边界**：这一条的见证是**结构级**的（谁渲染在哪个容器里），不是**布局级**的。jsdom 没有排版引擎，
  「长理由不再撑宽页面」这句话必须由真浏览器量；在量到之前，本文件不把它写成已证实的视觉结论。

**这一支的下一步（按顺序，仍与并行的 #126 支互不重叠）**：
1. #122 第二处：`pages/FindingDetail.tsx` 的「证据来源」kv 表 → `kv()` 行，迁完把该文件从名册删掉。
2. #122 第三、四处：`agent/pages/AgentEventLog.tsx`、`agent/pages/AgentPlanReview.tsx` 的事件/计划表。
3. #122 第五处：`pages/Dashboard.tsx`；迁完名册为空，届时 `test_the_scan_actually_read_something`
   那条「一处都没有 = 扫描瞎了」的断言必须重做（空名册是**目标**，不是故障），否则门会用一条假红挡住收尾。
4. 真浏览器量「长理由不再撑宽页面」：走 `tests/e2e`（真 SPA + 真 fixture 后端）而不是 jsdom。

### 2026-09-29：没跑成的检查不许判代码（#126 第五批，CI 那族轮转红的真因）

`tests-no-infra` 在 `3ad9310` 上是 **9 failed / 3301 passed / 27 skipped in 477.78s**，其中 7 条是 craft 循环：5 条 `assert 'STUCK' == 'DONE'`、2 条 `IndexError: pop from empty list`。关键是**红的名单在两次 CI 之间会换**（`36463431113` 是另外四条 STUCK）——同一份代码上会换名单的红是环境掷硬币，不是回归。名单换到哪个测试，取决于那一次 `docker info` 探针答没答上来。

- 机制（读源码得到的，不是猜的）：`Executor` 默认 `mode=None` → `SPECPROOF_SANDBOX` 缺省 `auto` → `run_sandboxed` 先 `_docker_available()`；**daemon 在、镜像不在**时走 `_run_docker` 返回 `sandbox image unavailable`，auto 这一支再 `_run_local(local_cmd, ..., "local_fallback")` 兜底，并把降级写在 `result.error` 上。而 craft 传下去的命令带的是**容器内路径**，在宿主机上必然跑不起来 ⇒ `exit_code != 0` **且** `error` 非空。`_check_criteria` 过去只看 `exit_code`，于是把「没跑成」当成「检查失败」，同一签名攒满 3 次就答 `STUCK`——一个关于用户代码的结论，实际坏的是执行面。探针超时那一次 auto 直接跳过 docker，宿主机跑干净，同一个测试就绿。**这就是轮转。**
- 本机量到的两条对照证据：① CI 只在 Linux 有 docker 的平面上红；② 我在 Windows 上按接缝注入同一个结果，旧平面原样复现 CI 那句 —— `result='STUCK' reason="同类错误连续 3 次, 判定 stuck (签名: s3|python: can't open file '/work/test_calc.py')"`：**签名里就是一个容器路径**，这是「判的是没跑成的命令」最直接的自证。
- 生产改动（`craft/loop.py`）：`compile` 与 `test_green` 这两处会执行命令的判据，遇到 `error` 非空且 `exit_code != 0` 时改走**已有的** W114 `unverifiable` 出口（`_sandbox_unverifiable_evidence`），理由是那句出口本来就写着「不进入修复循环, 不计入连续同类失败」；不新增判决种类，只把没产出的结论接进对的出口。`grep` 类判据不执行任何东西，因此不在范围内。
- 见证（`tests/unit/test_sandbox_degradation_is_not_a_code_verdict.py`，5 例，接缝打在 `craft.executor.run_sandboxed`）：①降级+非零 ⇒ `FAILED` 且 `unverifiable`、reason 里带上那句降级原文、**没有**「同类错误连续」、`iterations == 0`；②真失败（exit 1、`error=""`）⇒ 仍是 `STUCK` 且 `iterations == 3`（防我把豁免扩宽到吞掉真红）；③降级但 exit 0 ⇒ 仍然 `DONE`（触发条件是「没有结论」，不是「有任何降级字样」）；④走**真** `run_sandboxed`：只假 docker 的两个探针，量出兜底结果确实同时带着 `local_fallback`、非零退出与那句 degradation——没有这条，豁免可能是在管一个没人能造出来的形状；⑤AST 钉住两个调用点（`compile`/`test_green`），不许靠子串。
- 两平面：新平面 **5 passed in 9.23s**；旧平面（`git worktree` 指 `3f2237b` + 拷入新测试）**2 failed / 3 passed in 35.17s**，红的正是事前点名的两条（例①在第一个断言、例⑤在「found 0 call site(s)」），三条对照例在旧平面本就应当绿——它们的职责是证明豁免没扩宽。
- 一次自己的错，记下来防止复发：第一版编辑把 `if criteria.type == "test_green":` 那行连同上下文一起删掉了，`test_green` 分支变成 compile 分支 return 之后的死代码，于是两个行为例**全绿在错误的地方**（4 步全 green）。抓到它的是我自己那句「exactly one step may end the run, got [...green...]"——**断言「有且只有一个失败步」比断言结果字符串更能揭穿分支被绕过**。修法不是加断言深度而是把分支补回来，并用一个记录 command 的桩先量清 plan 的 4 个步骤各自跑什么（s1 grep / s2 compile / s3+s4 test_green，命令是 `<venv python> -m pytest -q`）。
- 全量 lane 数字补档（可归因，跑在 `3ad9310` 的干净 worktree，与 CI 同一套 `tests/unit tests/security tests/fault`）：**3329 passed, 6 skipped, 2 deselected in 3568.11s**，本机满载冷跑；CI 上同一 commit 是 9 failed / 3301 passed，差的就是本批解释掉的那 7 条 + 2 条 `test_slow_marker_tagging`（已在 #126 d 修掉，CI 已确认它们不再红）。
- 定向门：`ruff check craft/loop.py tests/unit/test_sandbox_degradation_is_not_a_code_verdict.py` 0 错；`mypy craft/loop.py` Success。**受影响面（`test_craft_loop.py`/`test_craft_verify.py`/`test_edit_test_guard.py`/`test_swebench_v10_fixes.py`）这一批没读到结果**——它在后台跑了 20 分钟仍未出汇总（本机同时压着全量 lane），所以本文件不写它的数字；下一批的第一条就是把它读完。

**下一批（可直接接手，按顺序）**：
1. 先读 `/tmp/reg126f.xml`（或重跑那四个受影响文件）并把数字补进上一条；若里面有红，第一嫌疑是本批的豁免把「命令超时」也算成没产出结论——先量再决定，不许靠 retry 蒙。
2. 让 CI 能自己说清是哪一面：`tests-no-infra` 里 craft 例失败时，断言消息应带上 `mode`（`docker`/`local_fallback`/`local`）。做法是把 `_result_dict(result)` 里的 mode 抄进失败诊断，而不是等人再翻一遍 `--log-failed`。
3. 真正的止血项：`auto` 在「有 daemon、无镜像」时不该悄悄换平面跑同一条命令——容器路径在宿主机上没有意义。要么在这种情形下直接判 unverifiable（本批已让判决诚实），要么让 craft 显式传 `local_command`；先量有多少生产调用点在 auto 下命中这一支。
4. `test_slow_marker_tagging.py` 的 180s 预算仍没按实测处理；`tests-with-infra`（minio unauthorized）与 `eval-golden-cases`（Maven cache 播种 exit 126）两个 job 还红着。
5. #122 前端那支由并行会话推进（`55b37d3` FindingDetail 已迁、AgentEventLog 正在改），本支不要碰 `apps/web` 与 `test_hand_written_table_ledger.py`。
### 2026-09-29：#122 第二处——证据面板走 kv 行，`pages/FindingDetail.tsx` 退出名册

- 站点：同文件的「证据来源」两列表（原 318 行）。它不是数据网格而是三对 label/value，所以迁到页面里已经在用的
  `kv()`（`.kv-value { word-break: break-all }`）：长路径会断开，而不是把 `<td>` 撑宽。
- 名册：`HAND_WRITTEN_TABLE_DEBT` 删掉该文件，并把文件头的「84e02e8 时 5 处 / 4 文件」改成同时记下付清的这两处与
  剩下的 3 处 / 3 文件；`hand_rolled_table_sites()` 实测 **4 处 → 3 处**。名册门从 **8 例变 7 例**（参数化跟着文件数走，
  这不是掉了断言，是名册真的少了一行）。
- 见证（同文件新增 1 例）：`container.querySelector("table.data")` 必须为空 + `证据方式` 恰好出现 2 次
  （基本信息面板与证据面板各一次）。
- 两平面：新平面 **2 passed**；旧平面（`git checkout HEAD -- apps/web/src/pages/FindingDetail.tsx`，只回退证据面板、
  保留上一批的共享表格）**1 failed**，红在事前预测的那一行：`expect(container.querySelector("table.data")).toBeNull()`
  → `expected <table class="data">…(1)</table> to be null`。
- 一处必须记下的**假红**：同一批的第一次旧平面跑里，反馈台账那条红成「1 秒内没等到那一行」——这台机器此刻被
  并行的全量门压着，`findByText` 的 1s 默认等待到期时 React 还没 flush，于是红成了「容器不对」的形状。
  把等待放宽到 5s 后新平面两例全绿，且耗时为 **3366ms / 1252ms**——也就是说那一行在负载下真的要 3 秒多才出现。
  ⇒ 判据一字未动，只把被负载压到不成立的默认等待改掉；这不是「用重试蒙绿」，是本仓库自己那条
  「时间脆弱性要先量再改」的口径。
- 定向门：`vitest run src/pages/FindingDetail.test.tsx -t "共享表格"` **2 passed**；
  `pytest tests/unit/test_hand_written_table_ledger.py` **7 passed**；`tsc --noEmit` **exit 0**。
- **诚实边界**同上一条：判据是结构级的；「长理由不再撑宽页面」的布局级结论仍待真浏览器量。
### 2026-09-29：#122 第三处——事件日志走共享表格（3 处 → 2 处）

- 站点：`agent/pages/AgentEventLog.tsx:43` 的事件日志表。它比反馈台账更暴露：**内容列是服务器原样 JSON**，
  一个长值就能把页面撑宽，而 `table.data` 没有容器能兜住它。
- 迁移：四列（序号/类型/时间/内容）→ `ui/Table`；`mono`、`title=`、以及内容列的 `word-break: break-all`
  原样保留在**单元格内部**（`ui/Table` 只给 `td` 提供对齐类，样式留在 `render` 里）。
- 名册：该文件退出名册，`hand_rolled_table_sites()` 实测 **3 处 → 2 处 / 2 文件**；名册门由 **7 例变 6 例**。
- 见证（`src/agent/__tests__/AgentEventLog.test.tsx` 新增 1 例）：喂一条 `{ blob: "x"*300 }` 事件之后，
  那一格必须在 `.ui-table-wrap` 里、且不在 `table.data` 里。
- 两平面：新平面 `vitest run src/agent/__tests__/AgentEventLog.test.tsx` **4 passed**；旧平面
  （`git checkout HEAD -- apps/web/src/agent/pages/AgentEventLog.tsx`，测试文件不动）**1 failed**，
  红在事前预测的那一行 `AgentEventLog.test.tsx:70: expect(cell.closest(".ui-table-wrap")).toBeTruthy()`
  → `expected null to be truthy`；按备份还原后 diff 为 `42 insertions / 22 deletions`，与迁移一致。
- **这一批顺带处理的一个环境事实**（不是产品缺陷，但会让人误判 e2e「坏了」）：`tests/e2e` 的
  fixture 后端在这台机器上**导入 `api.server` 就要 93.0 秒**（探针逐段计时：env/cert/fakes/seed 全都 <1s，
  时间全在 import），而 `playwright.config.ts` 里那条 webServer 的 `timeout` 是 `90_000` ⇒ 门会以
  「Timed out waiting 90000ms from config.webServer」红掉，看起来像 fixture 起不来。已按实测改成 **240_000**
  并把这行测量写进注释。另一条同样实测出来的前提：fixture 必须用**仓库 venv 的 python**（`PATH` 前置
  `.venv\Scripts`），系统 Python 3.11 下同一句 import 在几分钟内都没有开始监听。

### 2026-09-29：#122 第四处——计划步骤表走共享表格（2 处 → 1 处）

- 站点：`agent/pages/AgentPlanReview.tsx:48` 的计划步骤表（# / 标题 / 摘要 / 状态 / 操作）。
- 为什么它在这五处里最该修：**摘要列是模型自由生成的文本**，而这一页是审批人唯一能看到「它到底打算做什么」的地方。
  一个 300 字符不含空格的摘要会让手写 `<td>` 把面板（进而整页）撑宽——表格本身在 `Panel` 里，没有滚动容器。
- 迁移：五列 → `ui/Table`。`mono` 落在序号格、`muted` 落在摘要格，状态 pill 与「审阅」链接的类名原样留在
  `render` 内；`.ui-table-wrap` 与单元格对齐类由 `ui/Table` 提供。行数、待审文案、审批接口一字未动。
- 名册：该文件退出 `HAND_WRITTEN_TABLE_DEBT`，`hand_rolled_table_sites()` 实测 **2 处 → 1 处 / 1 文件**；
  名册门由 **6 例变 5 例**（参数化跟着文件数走，不是掉了断言）。
- 见证（`src/agent/__tests__/AgentPlanReview.test.tsx` 新增 1 例）：喂一条 `summary = "s"*300` 的步骤，那一格必须在
  `.ui-table-wrap` 里，且全页不得再有 `table.data`。为此给 `stubFetch()` 加了可选的 `Partial<AgentJob>` 覆盖参数。
- 两平面：新平面 `vitest run src/agent/__tests__/AgentPlanReview.test.tsx` **4 passed**；旧平面
  （`git checkout HEAD -- apps/web/src/agent/pages/AgentPlanReview.tsx`，测试文件不动）**1 failed**，红在事前预测的那一行
  `AgentPlanReview.test.tsx:114: expect(cell.closest(".ui-table-wrap")).toBeTruthy()` → `expected null to be truthy`。
  同一时刻名册门在旧平面也是红的（`1 failed, 4 passed`，
  `hand-rolled <table> appeared in ['agent/pages/AgentPlanReview.tsx']`）——这一处有两个互不依赖的红同时指着它。
  按备份还原后 `shaMatch=True`（`sha=0c0c1276f174d617`）、`git diff --numstat` = `52 43`，名册门 **5 passed**，
  `tsc --noEmit` exit 0。
- **诚实边界**：同前三处，判据是结构级（DOM 祖先链 + 类名），不是布局级；`.ui-table-wrap` 真有 `overflow-x: auto`
  这件事至今没有任何测试证明过——见「下一批」第 1 条。
- 顺带量到的一个**环境事实**（与本次改动无关，但会让人误判「测试变慢了」）：本机此刻被并行的全量门压着，单文件
  `vitest` 的分解是 transform 13.4s / collect 39.6s / environment 102.4s / tests 4.9s。看到慢先看这份分解，
  别怀疑新加的断言。

**下一批（按顺序）**：
1. 用真浏览器给「长摘要不再撑宽页面」补布局级证据（`tests/e2e`）；若仍是 chromium 的
   `Runtime.callFunctionOn: session closed`，就如实记为未证明，不许拿 jsdom 的结构断言冒充布局证明。
2. #122 最后一处：`pages/Dashboard.tsx:65`（最近验收表）。它是单行 JSX，且已经包在 `.table-scroll` 里——
   迁之前先量 `table-scroll` 与 `.ui-table-wrap` 的 CSS 差别，别把已有的滚动能力换成没有的。
3. 名册清空后 `test_the_scan_actually_read_something` 会自相矛盾（空名册是目标，但断言 `sites` 非空）；
   付清最后一处时把它改成「名册允许为空，但扫描必须真的读过 ≥1 个 tsx 文件」。

### 2026-09-29：#122 收尾——名册不再是「不许有」，而是「每一处都要交代清楚」

- 量到的前情：`pages/Dashboard.tsx:65`（最近验收表）与前四处**不是同一类**。它已经包在
  `<div className="table-scroll">` 里，而 `.table-scroll { overflow-x: auto; }`（`styles/product.css:175`）；
  更要紧的是托着它的网格轨道是 `.dashboard-bottom { grid-template-columns: minmax(0, 2.1fr) minmax(250px, 1fr); }`
  （同文件 141 行）——**`minmax(0, …)` 才是真正买到滚动的那个半句**：写成 `2.1fr` 时轨道 min-content 宽度由最宽的
  单元格决定，溢出容器再全也照样把页面撑宽。也就是说 #122 想消灭的失效模式在这一处**本来就不会发生**。
- 所以这一处**不迁移**，改成「登记 + 复查」：放进新的 `CONTAINED_HAND_ROLLED_TABLES`，把三条事实（包裹类名
  `table-scroll`、`overflow-x: auto` 规则、可缩到 0 的网格轨道）一并登记，由
  `test_contained_hand_rolled_tables_are_still_contained` 逐条重量。不迁的理由也要记诚实：迁到 `ui/Table` 会顺带把
  这张表的字号（11px→13px）、内边距、边框、阴影、sticky 表头全换掉——那是没人要求的外观重做，不在 #122 的诉求里。
- 门换了性质：`HAND_WRITTEN_TABLE_DEBT` 现在是**空集**（这是本线程的目标，不是失败），
  `test_every_hand_rolled_table_is_accounted_for` 要求「扫到的每一处都必须有名有姓地交代」；
  原来那条 `test_the_scan_actually_read_something` 断的是 `sum(sites.values()) >= len(DEBT)`，名册为空时自相矛盾
  （空名册是目标却被判红），已改成**断言扫描自身读了多少 .tsx**（实测 75，下限 40）——它现在证明「扫描没坏」，
  而不是「名册还没清空」。
- 证据（三条事实各自单独判红，每轮按备份还原且 `shaMatch=True`）：
  - 删掉 `.table-scroll { overflow-x: auto; }` → **1 failed, 4 passed**，红在
    「`.table-scroll { overflow-x: auto; }` is gone from styles/product.css…」；
  - 把 `minmax(0, 2.1fr)` 改成 `2.1fr` → **1 failed, 4 passed**，红在「without a grid track that may shrink to 0 …」；
  - 在 `pages/Health.tsx` 末尾加一行含 `<table` 的注释（模拟新的手写表格）→ **1 failed, 4 passed**，红在
    `test_every_hand_rolled_table_is_accounted_for`。
  全部还原后 `pytest tests/unit/test_hand_written_table_ledger.py` **5 passed**。
- 顺带量到的另一件事：`table.data` 这套样式现在只剩**一个生产者**（就是 Dashboard 那一处，另有 3 条「不得出现
  `table.data`」的断言和 Matrix 那条全文档检查）。也就是说 `table.data` 已经接近可以随 Dashboard 一起收掉的死样式——
  见「下一批」第 2 条。
- **诚实边界（这条比前四处更要紧）**：以上全是**源码级**证据——三条事实都是「CSS 里确实写着这条规则」，不是
  「浏览器里真的这么排版」。`minmax(0, …)` 配 `overflow-x: auto` 在真实布局下究竟兜不兜得住，至今没有任何测试
  观察过；这是本线程唯一还没兑现的那类证据。

**下一批（按顺序）**：
1. 真浏览器布局证据（`tests/e2e`）：长摘要不再撑宽页面。已有未提交草稿（fixture 的 feedback 端点 + `longtext.spec.ts`），
   上次红在 chromium 的 `Runtime.callFunctionOn: … session closed`；要么跑通并记下数字，要么如实记为未证明。
2. `table.data` 只剩 Dashboard 一个生产者；等它（或它的样式）收掉时，把 `base.css:1402-1411` 与
   `product.css:176-177` 这七行一并处理，并确认那 3 条「不得出现 table.data」的断言的判据随之更新，而不是悄悄失效。
3. #122 之外：`docs/operations/PRODUCT_ROADMAP.md` §28.4 里那些还红着的 CI job（`tests-with-infra` 的 minio
   unauthorized、`eval-golden-cases` 的 Maven cache exit 126）仍是没被处理的止血项。

---

### 2026-09-29：终态裁决必须说得出是哪条检查决定的（#126 g）

**先更正上一条（#126 f）的过度声称。** 那一节写的是「auto 降级 = 这条轮转红族的机制」，
把 `result.error` 非空那一支收掉了，CI 从 `9 failed, 3301 passed` 降到
`5 failed, 3317 passed, 27 skipped in 510.10s`（run 36473165360 / job 109100204345，`61e4a85`）——
**但剩下的 5 条不走 `error` 那一支**，所以 f 只解释了这一族的一部分，不是全部。
上一条把这个结论当成整族的解释，是过度声称，在此改口。

**这一批把「轮转」量成了表**（同一条 `python -m pytest tests/unit tests/security tests/fault -q`，
逐条读四次 run 的 `--log-failed`，只读名字与断言行）：

| run | job | `tests-no-infra` 红名 |
| --- | --- | --- |
| 36459987681 | 109055858874 | `test_craft_llm`、`test_craft_loop`、`test_craft_memory`、`test_slow_marker_tagging` ×2 |
| 36463431113 | 109067450482 | `test_agent_runtime`、`test_craft_llm`、`test_craft_loop_metrics`、`test_craft_verify`、`test_slow_marker_tagging` ×2 |
| 36467013322 | 109079522865 | `test_bench_mutation`、`test_swebench_llm_fixes`、`test_swebench_v10_fixes`、`test_swebench_v11_fixes` |
| 36473165360 | 109100204345 | `test_craft_llm`、`test_craft_loop_jobs`、`test_craft_loop_metrics`、`test_craft_verify`、`test_kind_threading` |

两件事从表里读出来，而不是从推断里读出来：
1. `test_slow_marker_tagging` 那两三条在 f 之后**消失了**——它是 #126 e 的 collect-only 豁免收掉的，
   机制另有一条（子进程继承父 conftest 改写后的 `MYSQL_DATABASE`，落到 `dedicated` 那一支，
   被迫去连一个不存在的库；本机复现记在上一条之前的段落里）。它和 craft 族是**两个不同的机制**，
   以前被我混在「轮转」这一个词里。
2. 剩下的红全都读作 `assert 'STUCK' == 'DONE'`（或 `IndexError: pop from empty list`——
   剧本回复被多出来的重诊断轮次掏空），且**名字集合在换**；`exec_mode` 全是 `"local"`，
   所以 docker/降级那条解释对这一族**不成立**。CI 里这些测试的 captured stdout 只有四条
   `craft llm call`，一行证据都没有。

**为什么没有证据**：`craft/loop.py` 过去整个文件没有 logger；而 `_check_criteria` 明明造出了
富证据（`check` / `exit_code` / `mode` / `output_tail`），STUCK 那一支却只把
`同类错误连续 3 次 (签名: …)` 塞进 `state.evidence`，把这条结论**由哪条检查、在哪个执行面、
以什么退出码**决定的一手证据丢掉了。报告的读者（Web 控制台）和日志的读者（worker、CI）
于是同时看不见。

**这一批落的东西**：`CraftLoop._record_terminal_check(step, state, verdict, reason, evidence)`
把那份证据合进终态 step 的 `evidence`（多出的键：`check/exit_code/mode/output_tail/terminal_verdict`），
并渲染成一行 `LOGGER.warning`——同一个 dict 喂两个读者，杜绝「日志和报告各抄一份、抄歪了」。
接在**两个**非绿终态上：3× 签名的 STUCK（在 `_run_step` 里）与 W114 的 unverifiable
（`_fail_unverifiable`）。刻意**不**接在「编辑提案重复 3 次」那一支：那里没有检查，硬套一行
「由这条检查决定」就是撒谎。`observability/logging.py` 的 formatter 只渲染
ts/level/logger/message，所以事实必须写在 message 里——这条前提也被一个案例钉住。

**数字（都从输出里读的）**：
- 新增 `tests/unit/test_terminal_verdict_names_its_check.py` 7 例：`7 passed in 66.26s`（本机 win32 / Python 3.12.13 / pytest 9.1.1）。
- 变异臂（把 helper 体首行前插 `return`，call site 原样留着）：`4 failed, 3 passed in 64.28s`，
  红的正是事前点名的 4 条行为案例，绿的正是「绿步骤不该有终态行」「AST 接线门」「formatter 前提」——
  接线门在这种臂下**故意不动**，它量的是接线不是效果。
- 我这次用 `.scratch/arm126g.py` 把对照跑在包装进程里，**对照那一腿崩了**
  （exit `3221227274`，没有汇总行），所以 7/7 这个数字来自随后单独直跑的对照，不来自那次包装跑；
  臂腿跑完 `restored sha … match=True`（字节级还原，锚点唯一性先断言）。
- 兄弟文件 `tests/unit/test_sandbox_degradation_is_not_a_code_verdict.py` 与本批新文件同跑：
  `11 passed`（那 5 例是本改动最直接的下游读者，它们对 stuck 的 `reason` 只做子串断言，
  所以新增键是纯加法——已经这样读过一次，不是推测）。
- `ruff check craft/loop.py tests/unit/test_terminal_verdict_names_its_check.py` → All checks passed；
  `mypy craft/loop.py` → Success。

**没做到的事，写清楚**：上一条「下一批」第 1 条要求先读完受影响面四文件
（`test_craft_loop.py` / `test_craft_verify.py` / `test_edit_test_guard.py` / `test_swebench_v10_fixes.py`，62 例）。
本机这一次跑到 `tests\unit\test_craft_loop.py` 的第 5 个点就停了：这台机器同时在跑别的会话的全量腿，
一条 craft 用例要 1–3 分钟，按这个速度四文件要一小时以上，我把它停了以免它和我后面的验证互抢 CPU。
**所以本文件仍然没有这四文件的可归因数字**；本批的验证范围就是上面那两条（新文件 + 兄弟文件）。
这一批没有回答「craft 族为什么在 CI 里失败」——它造的是回答这问题所必需的那件东西。

**下一批（按顺序）**：
1. 看 CI 在 `61e4a85`+本批 这一 run 的 `tests-no-infra` 日志：现在每条 STUCK 都会留下一行
   `craft 步骤 sN 的终态 STUCK 由这条检查决定: check=… exit_code=… mode=… | output_tail=…`，
   直接读它点名哪条检查、哪个面、什么输出——不再靠猜。
2. 如果那一行显示 `check='test_green'` 且 tail 是真测试失败，就顺着 tail 查编辑器/锚点在这一族 fixture 上
   是否根本没落上（`fix_registry` 的 no-op 剧本会伪装成「改了」，所以我这条臂里的 `fix_double` 故意不做编辑：
   它证明的是**日志与报告一致**，不是修复路径正确）。
3. `mode=auto` 静默把容器路径拿到宿主机重跑这条仍然开着：量清生产调用点有几处会走到，再决定是钉死
   还是要求显式授权降级。
4. #53 的 180s collect-only 预算、`tests-with-infra`（minio unauthorized）、`eval-golden-cases`
   （Maven cache 播种 exit 126）仍未处理。
5. 别碰 `apps/web/**` 与 `tests/unit/test_hand_written_table_ledger.py`（并发的 #122 会话拥有它们）。

### 2026-09-29：#122 的布局级证据——真浏览器里量到的不是「撑宽」，而是「够不到」

- 这是本线程唯一还没兑现的那类证据（前四处的判据都是结构级）。真浏览器跑 `tests/e2e/longtext.spec.ts`：
  风险详情页 + fixture 里一条 305 字符不换行的理由。
- **先说被推翻的前提**：#122 的叙述是「长理由把页面撑宽」。实测（1280 视口，chromium headless）**不成立**：
  `.panel { overflow: hidden }`（`styles/base.css:1369`）会先把溢出裁掉，而壳层真正的滚动容器是
  `.content { overflow-y: auto }`（`base.css:1363`，按规范 overflow-x 计算成 auto），所以
  `documentElement.scrollWidth` 恒等于视口宽。第一次我把对照臂写成「注入旧 markup 后 documentWidth 必须 > 视口」，
  对照臂红了：`{"documentWidth":1280,"viewportWidth":1280}`——**对照臂自己证明那条断言什么都测不到**。
  这是本批最有价值的一次红，也说明对照臂不是装饰。
- 换成能区分两种世界的判据：**可达性**——从出问题的单元格往上走，最近的裁剪祖先是谁、它的 computed `overflow-x`
  是 `auto` 还是 `hidden`。前者意味着有滚动条够得到整条理由，后者意味着直接截断。
  - 真臂（现状，走 `ui/Table`）：clipper = `div.ui-table-wrap`，`overflow-x: auto`，clientWidth **936** /
    scrollWidth **2821**（单元格实测 **2539.6px** 宽）；`.content` 的 scrollWidth ≤ clientWidth + 1，页面本身不横滚。
  - 对照臂（同浏览器 / 同 CSS / 同一串字符，只在同一个 `.panel-body` 里注入旧的手写 `<table class="data">`）：
    clipper = `.panel`，`overflow-x: hidden`，表格比面板宽却**没有可滚动的祖先**。
  两臂在同一个 `page.evaluate` 里量，对照表量完即 `remove()`，不污染后续用例。
- 对照臂是「在场证据」，但「真臂自己能不能红」还得单独证：把 `.ui-table-wrap` 的 `overflow: auto` 改成 `hidden`
  （只动 CSS，不动 TSX）重跑 → **1 failed**，红在事前预测的那一行
  `expect(real.clipper?.overflowX).toBe("auto")` → received `"hidden"`，失败消息里带着实测
  `clientWidth 936 / scrollWidth 2821`。按备份还原后 `shaMatch=True`（`sha=800625bebfa27d29`、`git diff` 无输出）；
  绿色那次就是这份还原后的文件：**1 passed (2.5m)**，用例本体 28.0s。
- 途中修掉三个**环境级**问题（每一个都会伪装成产品缺陷）：
  1. `api.routes.feedback` 是 fixture **唯一没被打桩**的 store 模块：GET `/api/v1/jobs/{id}/feedback` 会去连真 MySQL，
     页面上「验收反馈」永远停在 `加载中 LOADING…`（第一轮 e2e 就是这样红的）。已把该模块的 `MySQLStore` 一起 patch，
     并补上 `insert_feedback`（旧件只有 list/stats，POST 会 503）——返回 `created/replaced/unchanged` 与真 store 对齐。
  2. `loginWithToken` 的 `page.goto("/")` 用默认 `load` 等待：并行全量门压着时，光是 Vite 首次按需编译就超过 60s 用例
     预算，红成「导航超时」，看起来像应用没起来。改成 `domcontentloaded`——紧接着的断言本身就是显式可见性等待，壳层又
     要等 `/auth/me` 才出现，没有跳过任何东西。
  3. `playwright.config.ts` 每用例预算 60s → **120s**，理由同上一批 webServer 的 240s：本机实测成本高于预算时，红的
     是环境不是代码；真挂起仍然会红。
- **诚实边界**：本次判据是**布局级**（真浏览器 computed style + clientWidth/scrollWidth），强于前四处的结构级；但它只覆盖
  「风险详情页的验收反馈表 + 一条 305 字符理由」这一个站点。Dashboard 那处的 `minmax(0, …)` 结论**仍是源码级推断**，
  没有被浏览器量过。

**下一批（按顺序）**：
1. 用同一套 e2e 手法把 Dashboard 的 `minmax(0, …)` 变成布局级：注入超长仓库名，量 `.table-scroll` 的
   clientWidth/scrollWidth 与 `.content` 的横滚；顺带确认 `.panel{overflow:hidden}` 是否已经把它的溢出裁掉
   ——若是，Dashboard 的「已被容纳」也要按可达性重写，而不是照抄一条 overflow 规则。
2. `table.data` 只剩 Dashboard 一个生产者；`base.css:1402-1411` + `product.css:176-177` 这七行样式等它一起收。
3. 本批改过 `helpers.ts` 与配置后，其余 e2e 场景（wizard/detail/permissions/degradation）还没跟跑过；按「不全量回归」
   的口径，在下一次改动它们之前单独跑一遍确认没被 240s/120s/domcontentloaded 影响到。

### 2026-09-29：部署钉的 docker 从不覆盖「改代码」这条路，所以先把「未生效」说出来（#128）

**编号更正（先说，免得后来人按错号找）**：本里程碑的提交 `f2a6cb7` 写的是 `#127`，但 `#127` 已被 `a31c192` 那一节（「一个叫 `query` 的参数不是「SQL 文本」的证据」）占用并已推送。已推送的提交信息不改写；**本条是权威编号：后续一律引用 `#128`**（`THREAT_TESTING.md` §1 与门文件的 docstring 已同步改掉）。撞号这件事没有任何门能发现——仓库里没有「里程碑编号唯一」这本账（见文末下一批第 3 项）。

**量到的事实（逐条读自源码/日志，不是推测）**：

- `compose.production.yml` 的 worker 钉了 `SPECPROOF_SANDBOX=docker`；`tests/fault/test_malicious_build.py::TestProductionPinsDockerMode` 断言的**只是这个 YAML 字符串等于 `docker`**。
- `docs/operations/THREAT_TESTING.md` §1 把这条钉列为它自己钉住的缺口「显式 local 模式无隔离」的**缓解事实**。
- 但产品里真正改代码的那条路径——`api/agent_runtime.py` 构造 `CraftLoop`——传的是字面量 `exec_mode="local"`，而 `Executor` 的读取规则是 `mode or getenv(SANDBOX_MODE_ENV, "auto")`：显式 `mode=` 让 env 永远读不到 ⇒ **这条缓解对该路径从未生效**，而唯一的门只证明 YAML 里那个字符。
- 不能直接把钉 honour 掉：`run_sandboxed` 的 profile 默认来自 `_profile_from_env()`——无参数、无条件返回 `MAVEN_PROFILE`，且 **craft 那条路径**没有任何 `run_sandboxed` 调用点传 `profile=`（门只扫 `craft/executor.py`，所以它证的就是这句话的范围）。⚠️我上一版在这里写「全仓库没有任何调用点传 `profile=`」是**越过门所证的过度声称**：`experiments/adapters.py:906` 确实以 `mode="docker", profile=PYTHON_PROFILE` 调用——那是差分/实验路径，说明「按语言选 profile」这件事在仓库里已经有可抄的先例，#129 不必发明它。pytest/npm test 进 java 镜像会以**错误的理由**失败。所以本批做的是**披露**：`craft_plane_decision()` 返回 `(plane, note)`，note 点名「未生效的缓解 + 它的前置条件」；`agent_runtime` 用它取代硬编码的 `local` 并 `logger.warning`（已验证 `observability/logging.py::JsonFormatter` 只渲染 ts/level/logger/message ⇒ 事实必须写在 message 正文里，否则日志里等于没说）。

**门与见证**：新门 `tests/unit/test_craft_plane_discloses_the_deployment_pin.py` 7 例 = `7 passed in 62.22s`；受影响面（`test_agent_runtime` + `test_runbook_claims_hold` + `test_malicious_build`）= `32 passed in 236.09s`，exit 0；`ruff` 三个改动文件 All checks passed；`mypy craft/executor.py api/agent_runtime.py` = Success（2 files）。四臂**全部按事前预测红**：

| 臂 | 红数 | 红的案例（逐字） |
|---|---|---|
| control（未变异） | 0 | — |
| `arm_runtime`（把 `exec_mode` 写回字面量） | 1 | `test_the_runtime_asks_instead_of_inventing_a_plane` |
| `arm_env_name`（改旋钮名） | 1 | `test_the_pin_reader_reads_the_env_the_deployment_sets` |
| `arm_no_note`（note 置空） | 2 | `test_a_pinned_sandbox_is_disclosed_as_not_in_effect`、`test_the_disclosure_survives_the_json_formatter` |
| `arm_profile_kw`（给调用点加 `profile=`） | 1 | `test_the_note_blames_a_prerequisite_that_really_holds` |

⇒ 4/4 捕获，每条红都命中它 aimed 的那一条款。

- **我自己脚本的测量缺陷（记录，不隐瞒）**：`arm127.py` 四条腿全报 RESTORE FAILED（sha 不符）。查因而非直接重试：HEAD blob 与工作树文件都 CR=0、`core.autocrlf=true`、`git diff --stat` 只有预期的 +36/−2 ⇒ 是 `write_text(..., newline="")` 把工作树的 CRLF 抹平成 LF，我的字节校验比 git 还严。内容未坏；还原证明要按 git 平面重做，不能用我自己的字节口径。

**#126 h 的机制已定，LF/CRLF 假设被否证**：CI run 36480857832 汇总行 `5 failed, 3322 passed, 27 skipped in 488.82s`，且红成员在多次 run 之间轮转（`5 failed/3317`、`4 failed/3311`、更早一次 9 红）——所以「哪五条红」不是线索，「红为什么存在」才是。#126 g 落地的终态日志在 CI 上确实生效，逐字为 `check='test_green' exit_code=1 mode='local'`，配的是真实断言失败正文 ⇒ 幸存的 craft 红是**「编辑从未落地」**，不是执行面或超时的假象。另用 `.scratch/test_lf_probe.py` 把同一 fixture 分别按 LF 与 CRLF 各跑一遍：两面都收敛 `DONE`、`llm_calls: 1` ⇒ **换行符假设否证**。仍未解释的形状是 `IndexError: pop from empty list`：脚本化 stub provider 被询问的次数比测试脚本案数多一次，下一站按 `_llm_fix` 的无响应分支插桩（任务 #112）。

**下一批（按顺序，不并行跳）**：

1. `Executor` 按命令词干选 profile（mvn→MAVEN / pytest·python→PYTHON / npm→NODE）；只有做完这一步才允许 craft 这条路尊重钉值，并且同一条门要把 note 从「未生效」翻转成「已生效」——翻转本身就是新证据。
2. `agent/repo_safety.py` 的两个 arming 旋钮（`SPECPROOF_EXEC_MODE`、`SPECPROOF_ALLOWED_ROOT`）**全仓库无人设置**：`DEFAULT_EXEC_MODE = "local"` ⇒ 它自己的 fail-closed sandbox 分支是死代码，`execution_mode_signal` 在生产里以「local mode: host filesystem access allowed」通过。这是 fail-open，与 #128 同族但不是同一件事，必须单独量、单独落。
3. 里程碑编号没有登记处：本轮的 `#127` 撞号只能靠人肉 `git log` 发现。要么加一本「编号唯一」的账（种群读 git log 的号集合，两端都钉），要么换成别的锚；现在这类引用是无人核对的。
4. 仍然欠着的止血项：`tests-with-infra`（`docker compose up -d --wait`，minio unauthorized）、`eval-golden-cases`（Maven cache 播种 exit 126）、`test_slow_marker_tagging` 的 180s 预算还没按实测处理。

**落地后补记（属于上面「门与见证」，因为它是提交之后才量到的）**：本批的见证驱动器 `.scratch/arm127.py` 第 129 行是 `text=True` 而不写 `encoding=`，被 #111 那条普查门算进仓库债务，于是 `test_the_rest_of_the_repo_cannot_grow_the_debt` 报 **55 unpinned child captures (ceiling 54)**，offender 逐字 `.scratch/arm127.py:129`。普查走的是工作树而不是 git，所以未跟踪的 scratch 也算数，CI（全新 clone）永远复现不出这个数。**没有抬 ceiling**：给那一行补 `encoding="utf-8"` 后重跑 = `11 passed in 32.63s`（4 条普查 + 7 条本批门）。口径与 `#126 d` 同源——本地量到的 debt 计数含未跟踪文件时就不是可归因的仓库数字；但这一次不必删证据，**把驱动器本身写成守规矩的形状更好**：它跑的正是 #111 立的规则，自己不该成为 offender。

## #130 — repo_safety 的两个 arming 旋钮只有单测会设（披露落地，判定不变）

**测到的事实（逐条亲验，不抄上一批的结论）**：

- `compose.production.yml` 的 worker 钉 `SPECPROOF_SANDBOX: docker`，`tests/fault/test_malicious_build.py::TestProductionPinsDockerMode` 钉的正是这个 YAML 值。
- `agent/repo_safety.py` 管的就是这条交接：`repo_under_allowed_root` 拒「仓库落在 allowed root 之外」，`execution_mode_signal` 在 sandbox 模式没有 root 时 fail closed。两者只由 `SPECPROOF_EXEC_MODE` / `SPECPROOF_ALLOWED_ROOT` 武装，而** shipped 部署一个都不设**：全仓库唯一设置点是 `tests/unit/test_repo_safety.py:419,422` 的两处 `monkeypatch.setenv` ⇒ 在那个「承诺隔离」的平面上，模块自己回答「local mode: host filesystem access allowed」，fail-closed 分支是死代码。攻击者能命名宿主机上任意一个 git 仓库（不是它自己的），`git worktree add` 就把那个仓库的内容检出来放进将被挂进容器的 workspace —— 跨租约读这条通道此刻没有任何校验挡住。
- 这条「未武装」的事实**早就写在 `report.warnings` 里**，而 `SafetyReport.warnings` 在产品侧没有任何读者：两个 prepare 节点只读 `ok` 与 `fail_reason` ⇒ 守卫的自我披露被丢弃。

**这一批做的是披露，不是武装**：在没有 root 的部署上直接翻成 sandbox 会让每个作业 fail closed（不是修好任何事），而往 `compose.production.yml` 加 root 属于改线上行为，需用户批准。沿用 #128 已接受的做法：先把话说清、把话接上读者。

**落地内容**：
1. 平面钉值的真值收进一层：`sandbox/runner.py` 现在拥有 `SANDBOX_MODE_ENV`、`ISOLATION_PLANES`、`deployment_plane_pin()`（`sandbox` 只依赖 stdlib 与 `sandbox.cache_verify`，agent/craft 都已在它之上；`agent → craft` 才是循环，因为 craft 懒导 agent）。`craft/executor.py` 删掉自己的同名常量与 `sandbox_pin_from_deployment()`/`IMAGE_REQUIRED_MODES`，`craft/gates.py` 改调 helper。
2. `agent/repo_safety.py::safety_plane_truth()` 返回 `(mode, note)`：note 只在「钉了承诺隔离的平面、而本层没进 sandbox」时出现，正文点名 `SPECPROOF_SANDBOX` 的钉值、`SPECPROOF_EXEC_MODE`、`SPECPROOF_ALLOWED_ROOT` 与 `repo_under_allowed_root`。`check_repo_safety` 把它塞进 `warnings`，判定一字不改。
3. `prepare_base` / `prepare_head` 逐条 `logger.warning` 出 `report.warnings`（带 job_id）——这条披露唯一的可达读者。`JsonFormatter` 只渲染 ts/level/logger/message，所以事实全在 message 正文。

**门与见证**：新门 `tests/unit/test_repo_safety_discloses_the_unarmed_containment.py` 9 例（含逐字点的 compose 矛盾、按声明而非行号键的普查、`warnings` 读者普查、两个节点的实机日志腿）。测量面 = `.scratch/wt130`（HEAD 平面 + 我这 8 个文件覆盖上去；`agent.repo_safety.__file__` 已探针确认解析到该平面，不是仓库根）：control 63 例 0 红（新门 9 + `test_craft_plane_discloses_the_deployment_pin` 12 + `test_repo_safety` 42）；`ruff` 8 个改动文件 All checks passed；`mypy` 6 个产品模块 Success（6 files）。六臂全部按事前预测红、零存活：

| 臂 | 含义 | 红数 | 红的案例 |
|---|---|---|---|
| A | `safety_plane_truth` 永不产出 note | 4 | `_a_pinned_container_plane_...`、`_the_note_rides_the_report_...`、节点腿 `[base]` `[head]` |
| B | prepare_base 不再读 `report.warnings` | 2 | `_every_module_that_asks_for_a_safety_report_reads_its_warnings`、节点腿 `[base]` |
| C | 再抄一份平面钉值定义 | 1 | `_the_pin_name_has_exactly_one_definition_in_product_code` |
| D | note 算出来了但没进报告 | 1 | `_the_note_rides_the_report_without_changing_the_verdict` |
| E | 调用点绕过 helper 直接手抄字面量 | 1 | `_the_pin_name_has_exactly_one_definition_in_product_code` |
| F | note 点名错的检查 | 1 | `_a_pinned_container_plane_...` |

臂 E 是 `literals` 那条款式的**非空证**（臂 C 只证 `definitions`）：普查里「没有杂散拼写」如果没被敲过一次，就等于没测。还原校验按整体字节比对：`restore byte-identical: True`。

## #132 — CI 的红名单不是信号：旋转量化 + 唯一稳定红的归因（只测量，未改代码）

实测的三个运行（workflow `specproof-ci`，job `tests-no-infra / Unit + security + fault tests`）：

- `36608818914` @ 7b06dab（#130）= 7 failed / 3361 passed / 27 skipped in 495.98s
- `36604571352` @ 5d07632（#131）= 6 failed / 3353 passed / 27 skipped in 492.10s
- `36604556204` @ 5d07632（同一 commit 的第二次运行）= 6 条真红

**同一份代码的两次运行只共享 1 条红名。** 5d07632 的两轮并集是 11 个不同名字，交集只有
`tests/unit/test_craft_loop.py::test_loop_converges_done_with_injected_fix`。其余各红 5 条
（`test_no_llm_no_network_no_docker` / `test_offline_sample_kill_rate_and_records` /
`test_judge_persona_applied_to_the_diagnose_prompt` 对
`test_two_concurrent_jobs_do_not_interfere` / `test_cache_miss_fills_the_cache_and_reports_zero_hits` /
`test_kind_threading::test_loop_diagnosis_passes_diagnose_kind` /
`test_swebench_v10_fixes::test_genuinely_different_proposal_gets_a_new_iteration` /
`test_verify_criterion_anchor::test_deterministic_no_llm_path_report_shape_unchanged`）。
⇒ 拿"这次比上次多一条红"当回归证据是错的；#130 推上去后那条 +1 落在旋转带里，
红名单里没有 `test_repo_safety_discloses_the_unarmed_containment`，也没有
`test_craft_plane_discloses_the_deployment_pin`。

旋转带全部落在同一个机制上：deterministic craft 循环 + 真跑 `python -m pytest -q` 的
`test_green` 检查。每条 STUCK 红都由同一行披露决定
（`check='test_green' exit_code=1 mode='local'`，签名 `s3|E  assert 2.0 == 8`），
`IndexError: pop from empty list` 的两条是夹具里预置的 fix 列表被多消耗的一轮取空。

**唯一 3/3 稳定红的那条被归因了**：`05bdc5a`、`d96f494`、`3f99ed4`、`5fdc0ef` 四次运行里
`test_loop_converges_done_with_injected_fix` 都不在红名单；从 5d07632 的两轮到 7b06dab 一直红。
5d07632 是纯测试 commit（`+114/-0`，`craft/executor.py` 零 diff），产品代码来自它父级
`6826f15`（"Add profile selection per command stem in executor" + `_requested_stem`），
而 6826f15 自己没有 CI 运行 ⇒ 红的出现点 = 6826f15 的产品改动第一次进 CI。与 #130 无关。

否证记录（两条曾经的说法都不许再写）：

1. LF/CRLF：前一轮已否证。
2. 同长度、同秒的编辑被 `__pycache__` 顶掉：本轮直接量过——工作区写
   `def double(x):\n    return x / 2`，跑一遍 `python -m pytest -q`（rc=1，生成 pyc），
   再原地改成 `return x * 2`（字节数不变，均为 34，同一秒内），重跑 = **rc=0 / 1 passed**。
   ⇒ 陈旧字节码不背这个锅。

本地平面的对照（`.scratch/wt130` = 5d07632 + #130 九个文件覆盖，与 CI 同一份代码）：
**3212 passed / 5 skipped / 0 failed，PYTEST_RC=0，1670.78s**。含 CI 上 3/3 稳定红的那条。
⇒ #130 没有引入任何本地红，而那 7 条 CI 红里有一条在本地全绿——差异在平面，不在代码。

还缺的证据：CI 日志只证明判定读到的仍是 `2.0`，没有证明工作区里 `calc.py` 的字节。
所以"编辑未落地"目前是推断，不是观察。#132 的做法是让证据自己说话：`test_green` 的
evidence 带上被检查文件的字节摘要，红一次就能区分"没写进去"和"写进去了但检查读的是别处"。
在这条证据到位前不改 `craft/executor.py`。

## #134 — 旋转的 CI 红集合：等长同秒的修复，下一跳检查根本看不见

实测（origin 上三个连续 run，同一个 tests-no-infra 作业）：

- `36613910190`＝6 failed / 3362 passed / 27 skipped / 469.07s，六条红全是同一形状
  `assert 'STUCK' == 'DONE'`（test_craft_memory、test_craft_verify、test_kind_threading、
  test_swebench_llm_fixes 等）；
- `36634530368`＝3 failed / 3368 passed / 27 skipped / 501.94s，`36638027066`＝2 failed /
  3369 passed / 27 skipped / 519.26s；两次的红名字与上一次几乎不相交。
  （名单里那条 `FAILED test_calc.py::test_double` 不是红，它是 STUCK 披露回显的夹具输出；
  上面三个数字取的是 runner 自己的汇总行，不是 grep 出来的条数。）

关键读数：那些 STUCK 披露里的子进程始终打印 `assert 2.0 == 8`（即 `x / 2` 还在生效），
而整份日志里 **锚点拒绝 0 次**（grep `apply_edit 被拒` / `old 未命中` 无命中）。
也就是修复确实写进了磁盘，是产品自己的验证读不到它。

机制（`.scratch/g134/probe.py`，无依赖两平面探针，本机 windows/python3.12.13 实测）：
CPython 用「源码 mtime 的整秒 + 字节数」校验 `.pyc`。把时序钉死后
`run1 rc=1 → 等长且同秒的原子替换 → run2 rc=1 "1 failed"`，源码此时已经是修好的字节；
不钉时序则每次跨秒 ⇒ 本机常年全绿。
这解释了「红集合旋转」：它不是 flaky，是一个以时序为谓词的确定性缺陷。

落地 `6c6d6f0`：`Editor._atomic_write` 之后 best-effort 删掉被改模块的
`__pycache__` 条目（三条写路径 apply_edit / write_file / `ast_edit._atomic_write`
都经过这一个入口），不入审计 ⇒ 公布的 diff_stat 不会多出缓存文件。

见证 `tests/unit/test_craft_editor_drops_stale_bytecode.py` 3 例：钉时序的循环必须 DONE；
**对照臂**（把删除动作废掉）必须 STUCK——这条保证第 1 例的红真是机制而非巧合；
以及只删被改模块的缓存、非 .py 的兄弟缓存不动。

订正 #132 的第 2 条否证记录（那句「陈旧字节码不背这个锅」要改成下面这样）：
那一次测量本身是真的（写→跑→等长改→再跑 rc=0），但它没有构造出它所否证的谓词。
本轮同一支探针不钉时序时印的是 `mtime_s 1790785534 -> 1790785539 (same_second=False)`
——编辑跨到了 5 秒之后，pyc 头里的整秒自然对不上，rc=0 是必然的。加上 `os.utime`
把 mtime 钉回源码创建那一秒，`same_second=True`，同一条链 100% 复现 rc=1。
⇒ 正确结论＝「未钉时序的探针没测到同秒情形」，而不是「同秒情形不存在」。
教训：写下「否证」之前要指出是哪一次测量、以及那次测量是否满足了被否证命题的谓词。

还剩一条推断（不是测量）：CI 子进程只要 0.03s，所以修复更容易落进源码创建的那一秒；
本机慢平面每次跨秒，所以常年全绿。这条推断可被直接检验——`6c6d6f0` 推上去以后，
如果 `assert 'STUCK' == 'DONE'` 这一族红不再出现，机制成立；如果仍出现，
说明字节码陈旧不是（全部）原因，要另找。届时 #132 的 written_bytes 披露能同时回答
「字节动没动」。

平面门数字（干净 worktree 检出 `6c6d6f0`，tests/unit + tests/security + tests/fault，
由本脚本从 junit 读出、不许手抄）：tests=3423 / failures=0 /
errors=0 / skipped=7，用时 1135.443s。

## #135 — 快环为两个「每条案例起一个真 child」的见证白等；登记口径改成从合入门的 junit 求和

本轮把 `tests/unit/test_craft_terminal_discloses_written_bytes.py`（#132 的终态披露）
与 `tests/unit/test_craft_editor_drops_stale_bytecode.py`（#134 的字节码缓存）登进
`tests/conftest.py::SLOW_TEST_MODULES`，登记之后这张表有 **23** 个名字（登记之前 21）。

成本不来自我手敲的命令，来自合入门自己那本 junit 里 per-case `time` 的按模块求和
（平面 `6c6d6f0`，`tests/unit+security+fault`，**3423 例 / 3416 passed / 0 failed-error / 7 skipped / 1135.443s**）：

- `test_craft_terminal_discloses_written_bytes` ＝ **40.05s**（3 例）
- `test_craft_editor_drops_stale_bytecode` ＝ **23.62s**（3 例：10.059 + 13.532 + 0.032，只有第 3 例不起 child）
- 两条合计 **63.68s**；`-m 'not integration and not slow'` 的收集量从 **3423** 降到 **3137**（−286 例），
  其中这两个文件各自贡献 **3 + 3 例**（逐文件探针印的是 `no tests collected (3 deselected)`，
  rc=5）——块级 −286 里其余是既有 slow 集合，所以「快环变小」这句话只能靠逐文件探针站住，不能靠块级数字。

订正（原句留着）：我草稿里写的是「~33s 与 ~56s」，那是**一次性冷启动手敲命令**的读数，
正是 #132 记过并被撤回的那种测量。改成上表这两个在 suite 里的求和之后，`tests/conftest.py`
的注释也跟着写实测值——注释里的数字同样是一个声明，它也要有出处。

登记的是这两条，不是「所有慢的」：同一本 junit 里 `test_repo_safety` 是 **53.57s**，
排第 7，比若干已登记的模块更慢，但**故意不登记**——它是 #130/#131 那套 containment
守卫自己的覆盖面，把守卫请出快环是反向收益。这条留在文档里，而不是留在 frozenset 里。

CI 覆盖不受影响是读出来的，不是推的：`.github/workflows/ci.yml:71` 的 tests-no-infra 作业
不带 `-m`，所以 `slow` 只重排本地快环的便利，不减合并门（`pytest_collection_modifyitems`
docstring 里同一条声明由 `tests/unit/test_slow_marker_tagging.py` 双向钉着）。

双向见证（跑在改完的那个平面）：既有门 `test_slow_marker_tagging.py` **2 通过**；
两个文件各自 `-m slow --collect-only` 收 **3 例**、`-m 'not integration and not slow' --collect-only`
收 **0 例（3 deselected，rc=5）**——正向证明它被标上了，反向证明快环真的把它请出去了。

那 7 条 skip 逐个有名。它们与共享副本记 5 条的差**不在代码里，在平面的产物与特权上**：
`apps/web/dist` 在主工作副本＝True，在本轮那条腿的干净 worktree
＝False，于是 `test_web_api.py` 的两条只在干净平面上被跳过：

- `test_billing.py::test_mysql_backend_scenario` — MYSQL_URL not set — MySQL billing test skipped (skip)
- `test_node_adapter.py::test_node_adapter_runs_real_suite_on_host` — real npm execution is exercised on POSIX CI; skipped when  (skip)
- `test_node_adapter.py::test_node_adapter_runs_real_suite_in_sandbox` — needs a live Docker daemon; opt in with SPECPROOF_TEST_DOC (skip)
- `test_web_api.py::test_root_serves_spa_when_built` — SPA not built - run npm run build in apps/web (skip)
- `test_web_api.py::test_spa_fallback_does_not_mask_api_404s` — SPA not built - run npm run build in apps/web (skip)
- `test_threat_vectors.py::test_real_symlink_escape_rejected_if_platform_allows` — 平台不允许创建符号链接 (Windows 需开发者模式/管理员): [WinError 1314] 客户端没有所需的 (skip)
- `test_threat_vectors.py::test_real_symlink_inside_root_allowed_if_platform_allows` — 平台不允许创建符号链接 (Windows 需开发者模式/管理员): [WinError 1314] 客户端没有所需的 (skip)

基线口径订正：我给 #134 的预测钉在 3217，那是 `DRILLS.md` FIX-17（2026-09-27，**共享工作副本**平面）
的数字，距本轮三天、中间并发会话已落 `4a58e36`/`c49057c` 两批测试。最近的一条记录是 FIX-21
的 3403 passed（2026-09-30，同样是共享副本）。本轮 3416 相对 3403 是 **+13**＝
#132 的 3 例 + #134 的 3 例 + 并发会话在 `4a58e36`/`c49057c` 里的 provider-hold 与 notify-outbox 测试；
我没有逐文件列举差值，因为那条基线本身就不是我这一路的平面。教训写进方法里：**预测要钉在
「同一个 commit 的上一条腿」，不能钉在文档里最顺手的那个数**——否则一个正确的修复会被用来
解释一个我自己算错的差值。

欠一条：`docs/operations/PRODUCT_ROADMAP.md:333` 仍写「`SLOW_TEST_MODULES` 取 21 个实测模块」，
本轮之后是 23 个。该文件在并发写者清单里，我不改它，在这里登记为欠账，由它的拥有者把
「21」换成读数口径（按合入门 junit 的 per-case 求和登记，而不是按一次 `--durations` 手敲）。

## #136 — 缓存投毒守卫的三段死：没有生产者、半配置会自己拆火、裁决没人读

实测（修复前）：`enforce_cache_integrity` 的唯一调用点在 `sandbox/runner.py` 的
`if cache_dir and cache_manifest is not None:` 之后，而全仓没有任何 shipped 调用方传过这对参数
（`experiments/adapters.py` 四处、`scripts/mutation_bench_lib.py`、`agent/nodes/run_deep_experiments.py`、
`craft/executor.py` 都没传），守卫在生产里从未举过枪；`cache_verify.py` 的模块头写着
"Manifest format (JSON, produced by the seed step)"，而 `seed_sandbox_cache.ps1`、`seed_npm_cache.ps1`、
`seed_pip_wheelhouse.ps1` 三只播种脚本里 `manifest|sha256|Get-FileHash` 0 命中 —— 生产者不存在，
操作者无从造出守卫要吃的那个文件；`SandboxResult.cache_note` 在测试之外 0 个读者。

三段里本轮修掉两段半：

1. 生产者：`build_digest_manifest()`（POSIX 相对键 + 按文件自身字节 sha256；跳符号链接；跳过超过
   `max_entry_bytes` 的条目，因为那正是 `verify_cache_dir` 报 `<oversized>` 而不哈希的形状）+
   `save_digest_manifest()`（临时文件 + replace，不留 `.tmp`）+ `python -m sandbox.cache_verify seed|verify`
   真入口，退出码把裁决写出来：0 通过 / 1 投毒（拒绝执行）/ 2 清单或目录本身不可用 —— 坏掉的校验器永远不报 0。
   空缓存拒写空清单：`{}` 会让之后每一次校验都在 Nothing 上通过。
2. 半配置不再自己拆火：过去只传一对里的一半会穿过那个 `and` 落进"没配置校验"，照常执行 ——
   一个本该武装却静默解除武装的部署，比一个明说的未武装部署更坏。现在它拒执行并点名缺的是哪一半
   （"给了 cache_manifest 却缺 cache_dir"），且断言在零次 spawn 之前成立。
3. 未武装要被读出来（第三段只做了这一半）：挂了缓存卷却没配校验的每一次执行，`cache_note` 写
   `NOT VERIFIED` + 具体挂载点 + 播种命令，与"校验通过"共用同一个字段，于是"没验过"不可能被读成"验过、没问题"。

仍未闭合（如实登记，不是已落地）：没有任何 shipped 调用方武装这对参数，因为真正的武装点在
compose/播种脚本的环境变量上 —— 那属于需要用户批准的那一类改动；字段的产品读者（作业记录/UI）同样待接。

| 门 | 数字 |
|---|---|
| 新门 `tests/unit/test_cache_guard_producer_and_arm.py` | 16 例（生产者 7 / CLI 4 / 武装 5） |
| `tests/fault/test_cache_poisoning.py` | 21 例，其中原 `test_verification_skipped_when_not_requested`（断言 `cache_note == ""`，即把静默当作正确行为）改名成 `test_unarmed_cache_volume_is_disclosed_not_silent` 并改成断言披露 |
| 本轮焦点腿（新门 + fault + `test_sandbox_runner.py` + `test_sandbox_degradation_is_not_a_code_verdict.py`） | 63 passed / 0 failed / 0 errors / 0 skipped / 5.799s，junit 逐例数 63 与 attrs 相等 |
| 变异见证 | 6/6 臂 MATCHED（M1 撤半配置拒 → 2 红；M2 撤披露 → 1 红 unit + 1 红 fault；M3 生产者哈希超大条目 → 1 红；M4 键改成宿主分隔符 → 2 红；M5 CLI 投毒报 0 → 1 红；M6 允许空清单 → 1 红），控制腿修复前后各 37 例全绿，还原按 sha 校验 |
| `ruff check` | 本批 4 个文件全绿 |
| `mypy .` | 221 文件 5 错，全部在并发会话新增的未跟踪 `evidence/filelock.py`（Windows 无 `fcntl`）；本批文件 0 错 |
| 编码欠账棘轮 | 唯一红 `162 > 54` 的名册里只有 `.scratch/wt130/**`（另一会话的 worktree 草稿）：逐路径剥掉 wt130 前缀后为空集 ⇒ 本批 0 新增；新测试里的子进程两端都钉（`text=True` + `encoding="utf-8"`） |

旁证（同一次推送的 CI）：run `36749532101`（master `9deb5f9`）的 `tests-no-infra` 是 success ——
#134 预测可否证的旋转红（六条 `assert 'STUCK' == 'DONE'`）消失；该 run 的三个红作业是既有的
`lint-type`（就是上面那个 `evidence/filelock.py`）、`eval-golden-cases`、`tests-with-infra`。

## #137 DEEP 层的缓存完整性披露：第一个产品读者（已落地）

#136 把守卫本身修诚实了，但同时登记过一句实话：`SandboxResult.cache_note` 在仓库里
**没有任何 shipped 读者**，所以 verdict 到不了作业记录也到不了界面。`experiments/adapters.py`
在并发写者清单上（不许动），因此这条链不能从适配器平面穿；能穿的地方是**本来就握着整个
SandboxResult 的 shipped 调用方** —— `agent/nodes/run_deep_experiments.py` 的每次 Maven 运行
都在消费种子缓存卷，而它原先只把 `exit_code/error/mode` 传出去，note 在这个边界被丢。

落地内容：

- `_run_test_via_sandbox` 的返回多带 `cache_note`；新增纯函数 `_cache_integrity_disclosure`
  按访问顺序保留**每一条不同的**陈述（这是来源披露不是安全等级，不许取平均），全为空时
  返回空串，调用方**只在非空时写键** —— 缺席的披露不能长成 `""`，那会被读成「查过，没问题」。
- 披露取自完整 run 视图（头跑 + 稳定性和重跑）。第一次跑门就抓到真缺陷：`repeat_runs` 是
  投影掉 `cache_note` 的字典，`[head_run, *repeat_runs]` 其实只读到了头跑那一条。
- 读者是持久化的 `deep-report.json`（评审者真会打开的工件），断言直接读回那个文件。

| 门 | 数字 |
|---|---|
| 新门 `tests/unit/test_deep_cache_disclosure.py` | 7 例 / 0 红 / 0.565s（AST 的 `def test_` 数与 junit 逐例数互相对账 = 7） |
| 焦点腿（新门 + `test_verdict_stability.py` + `tests/fault/test_cache_poisoning.py` + `test_cache_guard_producer_and_arm.py`） | 52 passed / 0 failed / 0 errors / 0 skipped / 1.383s |
| 变异见证 `.scratch/g137/mutate_137b.py` | 控制腿 7/7 绿；A1/A3/A4/A5 MATCHED，**A2 事前预测 2 条红、实测 4 条**（多出的两条是同一去重子句的真实后果：那两个夹具把同一条 note 喂给多次运行）⇒ 0 臂存活，记档按实测改写（`bbb161c`），漏预测写在 docstring 里没被抹平 |
| 源码字节 | 每臂之后按 sha256 还原，收尾再与提交前备份核对 `src==committed-bytes: True`；多行臂点先按文件自己的行尾（CRLF）重排，否则每臂都是 BAD PATCH SITE |
| `ruff check` | 本批 3 个文件全绿 |

仍未闭合（如实登记）：

- 没有任何 shipped 调用方**武装** `cache_dir`+`cache_manifest`：这一步要改 `compose.*.yml` 或
  seed 脚本，按约定需用户批准，不擅自动。
- `deep_results` 不入库，Web 界面仍读不到这条披露 —— 下一单位是把它接进作业记录/界面。
- `craft/executor.py:221` 同样丢弃 `cache_note`（`ExecResult` 没有披露字段）。

提交：`6e2aa25`（代码 + 7 例）与 `bbb161c`（见证按实测订正），均已推送。

## #139 DEEP 工件的作业化命名与自报归属（已落地）

量出来的缺陷：state["output_dir"] 对所有作业都是同一个目录（CLI/demo/eval/mcp 一律
传 reports），而 DEEP 节点把变异战役、状态差分、稳定性判决与 #137 的缓存披露统统
写进同一个固定文件名 deep-report.json。两个 DEEP 作业同时在跑，后者直接覆盖前者的
证据；幸存的那份文件又不写着它属于哪个作业——评审者拿到的是一份归属不明的工件。
这不是猜测：写方只有本节点、读方为零，所以覆盖不会以任何报错暴露出来。

落地内容（提交 7d178e8，已推送）：

- 文件名作业化：deep-report-<job_id 前 8 位>.json，形状守卫沿用证书工件那条
  [0-9a-fA-F-]{8,64}（api/routes/web.py 的 _certificate_artifacts）；非 id 形状的 id
  （临时 CLI 跑）保持原名，任意字符串不参与路径拼接。
- 工件自带归属三键：job_id / deep_report_file / deep_report_naming，只拿着文件也
  能知道它描述谁、该按哪个名字被找到。
- 新门 tests/unit/test_deep_report_attribution.py 5 例：两作业各留一份且内容不串
  （就是覆盖回归）、名字由 id 派生、空 id 保原名、../../escape 不进文件名、
  工件自指的文件必须真的存在。

| 门 | 数字 |
|---|---|
| 焦点腿（新门 + #137 新门 + test_verdict_stability.py） | 20 passed / 0 failed / 0 errors / 0 skipped |
| 控制腿分母 | junit 5 例 == AST 数出的 def test_ 5（两条独立来源对账） |
| 变异见证 | 4/4 MATCHED：K1 固定名→3 红、K2 去掉形状守卫→1 红、K3 撤 job_id→1 红、
  K4 撤自指文件名→1 红；每臂之后按 sha256 还原并与见证前备份核对一致 |

事故如实登记（不是代码缺陷，但属于同一批）：git commit 提交的是整个索引，本次提交
把并发会话已经 staged 的 demo/spring-backend/.../UserController.java（0/4，删掉一段
javadoc）一起带进了 7d178e8 并推送。我在提交前的 numstat 里看到了这一行却照抄不误
——打印清单不是校验，能拒绝才算。事后不重写历史、不擅自回滚别人的内容（那是另一个
写者的意图），只做披露与流程订正：以后 staged 集合必须与自己的路径集合相等，不等就
先 git restore --staged <他人路径>（保留其工作副本内容）再提交。
## #140 DEEP 缓存披露的最后一位读者：归档的 HTML 报告

**问题。** #7 的守卫产出 `SandboxResult.cache_note`，#137 把它接进 `deep_results["cache_integrity"]`，
#139 让 sidecar `deep-report-<job8>.json` 能被归因。这三个都是机器工件。评审人真正打开、并且会存进
档案柜几年后再 diff 的那份工件——HTML Verification Report——对 DEEP 跑测时消费的缓存卷一个字都没说：
一条诚实的 `NOT VERIFIED` 与一次干净的缓存在报告里长得一样。`publish_report_node` 已经在渲染
`preflight`（环境披露），DEEP 的披露却在节点边界被丢掉。

**修法。** `evidence/report.py` 加 `_render_deep_evidence(deep, note, safe)`，渲染三种必须互不混淆的情形：
①有披露——原文照抄（分号合并、保持访问顺序，不做平均）；②DEEP 跑了却没有披露——写
`not disclosed by this run`，绝不写 verified；③根本没跑 DEEP（`deep_note` 含 tier 语句）——只说没跑，
不产生任何缓存断言；④调用方完全不带 deep 状态（旧调用点）——整节不渲染，免得把「没传」冒充成「没跑」。
`publish_report_node` 把 `deep_results`/`deep_note` 传进去。

**门（实测）。** 聚焦腿 4 个文件 `29 passed / 0 failed / 0 skipped`（新模块 7 例 + `test_report_preflight`
10 例 + #137 的 7 例 + #139 的 5 例）；`ruff` 三文件全过；`mypy` 两个源文件 `Success: no issues found
in 2 source files`。

**变异见证（预测先写，实测后读）。** 控制腿 7/7 绿，且 `collected == ast_declared`（用例数从测试文件自己的
AST 派生，不是手抄）。6 臂全部 CAUGHT，0 存活、0 未判，还原后按 sha256 与被见证字节逐文件相等：
N1 节点不再转发 deep 关键参数 → 2 红；N2 渲染器丢掉披露行 → 2 红；N3「无披露」被写成 verified → 1 红；
N4 去掉「不是 DEEP 就不渲染」的守卫 → 1 红（第 4 例：旧调用方的静默被冒充成「没跑 DEEP」）；
N5 披露行不过 `safe()` → 1 红；N6 整节从文档里掉出来 → 4 红。

**仍未闭合（不要在下一批里假设它们已闭）。**
- Craft 的 `ExecResult` 仍然丢 `cache_note`：`craft/executor.py` 里 `run_sandboxed` 的返回被投影成
  exit/stdout/mode，注记无处可去。本项目内 `craft.executor` 无仓库外调用点，所以这条要么连着
  Craft 结果工件一起接，要么别单独落（后端半边单独落＝没人读的字段）。
- `deep_results` 依旧不入库、Web 界面读不到 DEEP 的任何结论；给它一条 HTTP 读路径要重生成 OpenAPI
  baseline，而 `scripts/export_openapi.py` 在本窗口是并发写者文件，动不了。
- compose 武装（`SPECPROOF_ALLOWED_ROOT` + `SPECPROOF_EXEC_MODE=sandbox`）仍需用户批准；今天没有任何
  shipped 调用方同时传 `cache_dir` + `cache_manifest`，所以每一份当前报告里的 `NOT VERIFIED` 都是真话。
## #141 Craft 的门禁 note 才是控制台读得到的那条缓存披露

**问题。** `run_sandboxed` 有两条 shipped 调用路径：DEEP 节点（#137/#140 已接）和
`craft/executor.py`。后者把 `SandboxResult` 投影成 `ExecResult` 时只留
exit/stdout/stderr/error/mode——`cache_note` 在投影处消失。Craft 循环每跑一次 `mvn`
都消费播种缓存卷（#129 之后 mvn 走 MAVEN profile），但评审人在 Web 控制台看到的门禁
note 只有 `mode=docker_sandbox`。也就是说「缓存被投毒的构建」与「缓存干净的构建」在产品里
长得一模一样，而这正是 #7 那道守卫想说的话。

**修法。** `ExecResult` 加 `cache_note`（默认空串），`Executor.run()` 原样转发；
`craft/gates.py::_run_commands` 在**通过与失败两条 note**上都追加
`缓存=<沙箱原话>`——只在失败分支带等于「披露只会在已经出事时出现」。GateResult 的
`note` 经 `to_dict()` 进 `api/agent_runtime.py` 的 entry 载荷，所以这条文案就是控制台载荷本身，
不需要新路由、不动 OpenAPI baseline。

**诚实口径。** 空 note＝该 profile 不挂缓存：此时一个字都不写，绝不写「已验证」。
这条由 C4 臂钉死（把空 note 编成「缓存=已验证」必须红）。

**门（实测）。** 聚焦腿 5 个文件 `81 passed / 0 failed`（新模块 5 例 + `test_craft_gates` +
`test_acceptance_gate` + #140 的 7 例 + #7 守卫的产家/武装文件）；`ruff` 三文件过；
`mypy` `Success: no issues found in 2 source files`。

**变异见证（预测先写，实测后读）。** 控制腿 5/5 绿且 `collected == AST 派生的用例数`。
第一轮 5 臂里 3 MATCHED + 2 MISMATCH，两条都在预测侧：
- C2（通过分支丢后缀）实测 2 红而非 1 红：第 5 例（控制台载荷）本来就走通过分支，是同一条线的
  真后果，不是多余红；预测按「案例的名字」而不是按「它踩的分支」写，已订正为 {2,5}。
- C5（`ExecResult` 整个字段没了）实测 4 红而第 4 例仍绿——**这条抓到我自己的洞**：
  `_run_commands` 把执行器异常吞成「执行异常」note，而那条 note 里同样没有「缓存」，
  所以「空 note 不造话」只断言 absence 时分不清「没缓存可披露」与「功能整个没了」。
  第 4 例现在要求 note 里出现 `mode=docker_sandbox`（只有真 `ExecResult` 走到 note 构造才会
  有它），C5 重测＝5 红，5 臂 5/5 MATCHED、0 存活，逐臂 sha256 与被见证字节相等。

**仍未闭合。**
- `craft/loop.py` 的三处 evidence 字典（compile / test_green / `_sandbox_unverifiable_evidence`）
  仍只带 `mode`/`output_tail`，没带 `cache_note`；终态那行日志（#126 g 的
  `_record_terminal_check`）同理。这条不在本批里，因为要先把 loop 的构造成本降下来才测得起。
- `deep_results` 依旧不入库、Web 界面读不到 DEEP 结论；HTTP 读路径要重生成 OpenAPI baseline，
  而 `scripts/export_openapi.py` 仍是并发写者文件。
- compose 武装（`SPECPROOF_ALLOWED_ROOT` + `SPECPROOF_EXEC_MODE=sandbox`）仍需用户批准。

## #142 Craft 循环自己的证据字典现在也带缓存披露

**问题。** #141 把披露接到了门禁 note（控制台那条），但 Craft 循环里更有用的那三份证据被丢在
原地：`_check_criteria` 给 compile / test_green 两个检查建的字典、`_sandbox_unverifiable_evidence`
给「检查根本没得出结论」建的字典，都只转发 `mode`/`output_tail`——`cache_note` 在投影处消失。
于是 #126 g 那行终态日志（「这个终态由这条检查决定」）也说不出口：一次 STUCK 可能是在消费未校验
依赖缓存的容器里得出的，而报告与 worker 日志里都看不见这件事。

**修法。** `ExecResult` 多一个派生属性 `cache_disclosure`（有沙箱原话时返回 `{"cache_note": ...}`，
否则空字典），三处字典各用 `**result.cache_disclosure` 展开，`_record_terminal_check` 的 facts
键位加上 `cache_note`。规则只写一次，所以证据字典与那行日志不可能各说各话。
字典随 `report.json`/作业记录进控制台，日志进 worker 输出——两个读者同一份事实。

**诚实口径。** 空 note＝该 profile 不挂依赖缓存（`sandbox/runner.py` 对挂了缓存卷的 profile
连「调用方没播种」都要写一句原话），所以「没有这个键」=「没东西可披露」，绝不是「缓存已验证」。
每条 absence 断言同时钉住 `mode`，这样「看不见键」不能是「什么都没读」的别名（#141 的 C5 教训）。

**门（实测）。** 新模块 6 例、整套聚焦腿 56 passed / 0 failed；
`ruff` 三文件过；`mypy` `Success: no issues found in 2 source files`。
这批改完 loop 的构造成本疑虑就消失了：把检查脚本化在沙箱接缝之后，新模块 6 例
实测 3.95s（整套聚焦腿 104.92s），
所以 #141 记档里「要先降成本才测得起」那句已被测量否证——按测量走，不登记进 `SLOW_TEST_MODULES`。

**变异见证（预测先写在测试模块 docstring，实测后读）。** 控制腿 collected=6 且等于 AST 派生的
`def test_` 数；6 臂 6/6 MATCHED、0 未判、逐臂 sha256 还原后被见证平面
byte-identical。红集合按「案例踩哪条分支」预测而不是按名字，所以第一轮就全中：
L1 compile 字典→1 红；L2 test_green 字典→2 红（终态那例走的正是这条检查）；
L3 unverifiable 字典→1 红；L4 空 note 也写键→2 红（两条 absence 例）；
L5 facts 键位丢了它→1 红（只红日志那半）；L6 整个机制没了→4 红，两条 absence 例照旧绿＝它们是对照。

**仍未闭合。**
- `deep_results` 依旧不入库、Web 界面读不到 DEEP 结论；HTTP 读路径要重生成 OpenAPI baseline，
  而 `scripts/export_openapi.py` 仍是并发写者文件。
- compose 武装（`SPECPROOF_ALLOWED_ROOT` + `SPECPROOF_EXEC_MODE=sandbox`）仍需用户批准；
  今天没有任何 shipped 调用方同时传 `cache_dir` + `cache_manifest`，所以每份报告里的
  `NOT VERIFIED` 都是真话。
- 本弧的全量合并门数字仍未在干净平面重跑（这批只取聚焦腿）。

## #143 诊断提示词第一次说出「这段失败是哪一面跑出来的」

**问题。** `_diagnose_context` 一直只引用 `failure_output`，从不说明这段输出出自哪个执行面。
于是当「为什么这条判据还在失败」的诚实答案是「这一轮消费了未校验的依赖缓存」时，提案循环
里没有任何一句话能把这件事告诉模型——它只能回到源码去改，而 #7 那道守卫想让人看见的正是
「STUCK 可能是在缓存没校验的容器里得出的」。#140/#141/#142 把报告、控制台与终态日志这四个
读者接上了，剩下的读者是模型自己。

**修法。** 新增一个 context 变量 `execution_plane`：`mode=…` + 依赖缓存那一行原话（值直接来自
#142 的 `ExecResult.cache_disclosure`，规则仍只写一次）；`result is None`（只读/断言型判据）
时明说「本步骤没有执行任何命令，因此不存在执行面」。接缝是实测出来的而不是假设的：
`providers/prompt_templates.py::assemble` 泛型渲染 variable dict 的**每一个**键
（`sections = [f"[{key}]\n{value}" for key, value in sorted(variable_data.items())]`），
所以一个新键天然进模型——不动模板、不新增路由、不重生成 OpenAPI baseline（后两条在今天
是硬约束：`scripts/export_openapi.py` 是并发写者文件）。

**诚实口径。** 空 note 写成「该 profile 未挂载依赖缓存卷（无内容可披露，这不等于缓存已验证）」，
绝不写成「已验证」；没跑命令的判据不许冒充有执行面。每条 absence 断言同时钉住 `mode`，
这样「看不见缓存」不能是「什么都没读」的别名。副作用要说清：新增键改变了每份 diagnose 提示词
的字节，`cache_key(_prompt_digest(built.text), …)` 那层语义缓存因此会失效一次——这是正确行为
（提示词确实变了），不是回归。

**门（实测）。** 新模块 5 例 `5 passed in 2.79s`；影响面腿 10 个文件
（`test_craft_loop*`、`test_craft_memory`、`test_craft_verify`、`test_terminal_verdict_names_its_check`、
`test_providers_dsv4`、`tests/security/test_injection_matrix`）**142 passed / 0 failed，267.74s**；
`ruff` 两文件 `All checks passed!`；`mypy` `Success: no issues found in 2 source files`。

**变异见证（预测先写在测试模块 docstring，实测后读）。** 控制腿 collected=5 且等于 AST 派生的
`def test_` 数；5 臂 5/5 MATCHED、0 未判、逐臂 sha256 还原后被见证平面 byte-identical。
红集合按「案例踩哪条分支」预测：
- M1 从 context 里删掉这个键 → 4 红（案例 1 渲染整份提示词，2/3/4 直接取那个键），案例 5 照旧绿＝
  它两次构建的差别本来就在 `failure_diagnosis`，这条对照说明 M1 没伤到缓存不变量。
- M2 空 note 分支编造「依赖缓存: 已验证」→ 案例 3 红。
- M3 没跑命令的分支返回一个执行面形状的块 → 案例 4 红。
- M4 `assemble` 把变量段折进稳定前缀 → 案例 5 红（每轮都变的诊断再也不能共享前缀）。这条线
  仓库里本来就有守卫（`verify_variables_after_prefix`，被 `test_providers_dsv4`、
  `test_injection_matrix`、`test_craft_memory` 三处断言），所以 M4 是双保险：新例把它从
  **诊断读者**这一侧也钉住了。
- M5 执行面块丢掉 `mode` 行 → 3 红（案例 1/2/3 都钉着平面），案例 4/5 绿——因为那条分支本来就
  没有平面可报。第一轮就全中，没有一条预测需要订正。

**仍未闭合。**
- `deep_results` 依旧不入库、Web 界面读不到 DEEP 结论；HTTP 读路径要重生成 OpenAPI baseline，
  而 `scripts/export_openapi.py` 仍是并发写者文件。
- compose 武装（`SPECPROOF_ALLOWED_ROOT` + `SPECPROOF_EXEC_MODE=sandbox`）仍需用户批准；
  今天没有任何 shipped 调用方同时传 `cache_dir` + `cache_manifest`，所以每份报告与每条提示词里的
  `NOT VERIFIED` 都还是真话。
- 本弧（#140/#141/#142/#143）的全量合并门数字仍未在干净平面重跑；这批只取影响面腿。

## #144 待办配方（实测范围，不是猜测）：envelope 自检那条提示词也带着执行面，却没有证人

**实测到的现状。** `craft/loop.py` 里只有两处 `assemble(... "diagnose" ...)`：
`:1755`（普通提案腿）与 `:2124`（W44 自检腿，`include_envelope=True`，它把
`_diagnose_context` 的字典 `dict(context)` 复制一份再加 `self_check_repair`）。
`_diagnose_context` 只有一个 `return`，因此 #143 的 `execution_plane` 现在**两条腿都带**——
这是读代码确认的结构性事实，不是新增行为。

**欠的证人。** #143 的 5 例全部走 `envelope_mode=False`。也就是说「自检腿也向模型披露执行面」
今天只成立在结构上：将来谁给 envelope 腿单独拼一份 sections（很自然的优化动机是「自检只带
JSON 契约，别拖 2000 行源码」），执行面就会从自检提示词里消失，而 5 例照旧全绿。

**下一号的配方（成本已量过，够便宜）。** 在 `tests/unit/test_diagnose_prompt_names_the_plane.py`
追加一例：`context(loop, result, envelope_mode=True)` → `assemble(base, "diagnose", sections,
include_envelope=True)` 的 `built.text` 里同时出现 `[execution_plane]`、`CACHE_UNARMED` 原话与
JSON Action Envelope 块；再补一臂 M6＝自检腿改成自己拼 sections（丢掉这个键），预测恰 1 红。
控制腿 collected 仍要等于 AST 派生的 `def test_` 数。整例在沙箱接缝之后不需要真跑命令，
所以成本与现有 5 例同级（`5 passed in 2.79s`）。

**为什么现在不落。** 本批只剩记档的回合预算；一个没有见证的新例不如一条写清范围与预测的配方。
按测量走，不按名字走。

## #144 落地：自检提示词的执行面披露现在有证人，而它先抓到我自己的三条假预测

**做了什么（只动测试）。** `tests/unit/test_diagnose_prompt_names_the_plane.py` 加第 6 例：
不再从外面拼提示词，而是把 W44 自检腿 `_llm_fix_envelope` 真的驱动起来——第一份信封故意版本号
不合法，逼出那条重试（`[self_check_repair]` 因此也进提示词），再用 recording client 收下两条
真正发给模型的文本。生产代码字节没动（见证逐臂 sha256 还原后平面 byte-identical）。

**实测门。** 模块 6 例 `6 passed in 3.43s`；信封机构腿 4 个文件
（`test_craft_loop_metrics`/`test_toolcheck`/`test_craft_tools`/`test_craft_verify`）
`89 passed / 0 failed, 112.66s`；#143 那条 10 文件影响面腿 `142 passed / 0 failed, 267.74s`
仍成立（生产未变）。

**预测订正（先记错的那半，不是事后改数字）。** 第一轮 7 臂见证 **拒收**（exit 1，3 臂未判），
三条都在预测侧，全部按实测订正而不是把断言改松：
- M1（context 丢键）预测 4 红，实测 5 红——多出来的是新例：自检腿 `sections = dict(context)`
  复制的正是同一个字典，所以「删键」这条线在两条腿上都有后果。
- M5（执行面块丢 `mode` 行）预测 3 红，实测 4 红，同一原因（新例也钉 `mode=`）。
- **M7 存活**（预测 1 红，实测 0 红）——这条抓到的是我自己的假钉子：我原本断言信封块的
  「首行出现在提示词里」，而 envelope 模式的 context 自己就引用了那段契约文字，于是
  `include_envelope=False` 也照样绿。钉子改成**位置**断言（信封块必须是提示词的结尾），
  重跑后 M7 恰 1 红。教训与 #141 的 C5 同一型：一条 absence/presence 断言如果不绑定
  「只有被测机制才会产生的那个形状」，它就是零证据。
订正后端到端：控制腿 collected=6 且等于 AST 派生 `def test_` 数，M1–M7 **7/7 MATCHED、
0 未判**，逐臂 sha256 还原后平面 byte-identical。

**§#144 配方里那句「两处 assemble 都带披露」现在有了证人**：结构性事实（单 return + dict 复制）
不再只是读代码得到的保证，M6 一臂（自检腿自己拼 sections 丢掉这个键）会立刻红。

**仍未闭合。** `deep_results` 入库与 Web 读路径（并发写者文件 + OpenAPI 重导）、compose 武装
（要用户批准）、以及本弧 #140–#144 的干净平面全量合并门数字。

## #145 待办配方（本轮实测）：step 证据里的缓存披露在前端一个读者都没有

**实测到的现状（三条，都是这一轮量出来的）。**
1. `cache_note` 在 `apps/web/src` 全库 **0 命中**——#142 把它写进三处 evidence 字典之后，
   没有任何前端组件读它。
2. 门禁 note 那条路**是**通的：`apps/web/src/agent/pages/AgentGates.tsx` 里有 `note` 读者
   （#141 的设计前提，仍然成立）。所以「控制台读得到缓存披露」这句话只对**门禁 note**成立，
   不能推广到 step 证据。
3. `output_tail` / `written_bytes` / `exit_code` 在 `src/agent` 下 **0 命中**。也就是说
   evidence 面板要么是通用 JSON 直出（那 `cache_note` 会被动露出，但会是裸英文键名，需要词表），
   要么压根没渲染（那是 #58/#59 那一类「证据落库却看不见」的缺陷）。**这两种情况的修法不同**，
   所以 #145 的第一步不是写组件而是走这一条：从 `api/agent_runtime.py` 的 entry 载荷形状
   找到渲染点，判定落在哪个分支。

**下一号的顺序（别跳）。** 先量渲染点（读代码 + 一个真实作业载荷）→ 再决定是「补词表 + Term」
还是「补面板」→ 才写测试。若走词表分支，注意 #81/#87 那类「值有词」对账门会点名新键，
先查 `tests/` 里的枚举门是否覆盖 evidence 键名，避免把门改成迎合实现。

**平面归属（本轮确认）。** `apps/web` 目前干净（只有一个未跟踪的 vite timestamp 文件），
`AgentEventLog.tsx` 与其测试仍是并发写者文件；前端三门禁（tsc / vitest / vite build）都要走。

**本轮同时欠着的一次测量。** #140–#144 这条弧的干净平面全量合并门正在
`.scratch/plane144`（`git archive HEAD` 冻结平面，PYTHONPATH 已钉，`craft.loop.__file__`
实测落在平面内）后台跑，产物 `.scratch/plane144_gate.xml` / `.scratch/plane144_gate.log`
（末行 `GATE_EXIT=`）。**没有读到汇总行之前，任何地方都不许引用这个弧的「全量门已过」。**

## #146 本弧欠的那次干净平面全量门：数字到手，而它顺手抓到一条用户看得见的地雷

**跑法（可归因的关键）。** `git archive HEAD` 冻结到 `.scratch/plane144`（平面＝`4ce4b58`，
我的弧最后一次生产改动），CI 的单测腿原样：`pytest tests/unit tests/security tests/fault -q`，
**PYTHONPATH 钉在平面根**，并实测 `craft.loop.__file__` 落在
`.scratch/plane144/craft/loop.py`——不钉这一条，venv 的 editable-install `.pth` 会把
「干净平面」偷偷换成带着并发写者脏文件的工作副本，数字就成了假证据。

**数字（读的是 junit，不是退出码）。** `tests=3488 / failures=1 / errors=0 / skipped=30`，
`time=3966.769s`，`GATE_EXIT=1`。历史那个「约 45 分钟」的口径在这个平面是 66 分钟：
冻结平面没有共享缓存、机器上还有别的会话在跑——所以耗时照实记，不拿来当基线。
**#140/#141/#142/#143/#144 这条弧至此才有可归因的全量门数字**，且这 1 条红不在弧里：
弧动的文件是 `craft/`、`providers/`、`sandbox/` 与两个 `test_diagnose*`/`test_craft*` 文件。

**那条红是确定的、可复现的，而且是一句真话。**
`tests/unit/test_audit_disposition_labels.py::test_the_page_asks_for_the_parameter_the_handler_accepts`
在冻结平面上单独重跑 `1 failed in 1.34s`，断言原文就是结论：
`AssertionError: the page never sends target — the filter is cosmetic`。
也就是说审计页那个按作业检索的筛选器**不把参数发出去**——用户填了、按了，结果集没被过滤。
归属审计那条 lane（该测试文件最近三次提交是 #112/#107/#97），不是本弧引入的回归。

**为什么这条比任何性能数字都重要。** 这正是「不好用」最坏的形状：控件看起来在工作。
下一条（候选 #147）就是把它真的接上——页面把 `target` 发出去，并让那条门从
「正则扫页面源码」升级成「真的把参数带到请求上」。先量归属再动手，别把别人的红当自己的修。

**#145 的分支判断也量完了（修正上一轮的配方）。** 上一轮写「evidence 面板要么通用 JSON
直出，要么根本没渲染」——实测落在**前者**：`AgentResult.tsx:129` 有
`<details>查看完整执行记录</details>` 里 `JSON.stringify(result, null, 2)`，
所以 `cache_note` 会露出，但是以**裸英文键名、折叠在原始 JSON 里**的形式；
`AgentEventLog.tsx:79` 同样 `JSON.stringify(ev.data)`（那是并发写者文件，别碰）。
结论：#145 不是「补面板」，而是把这条披露从原始 dump 里提出来放到有中文标签的位置，
并按 #81/#87 那道「值有词」门的方式配词表——先查枚举门是否覆盖 evidence 键名。

## 更正 #146：那条红不是「筛选器不发参数」，是我把 #96 的门读错了——#138 撞了它的探针

#146 记的是「审计页的 job 筛选器是装饰性的，它从不把参数发到请求上」。这句话**错了**，
在把 junit 的那一条红归因之后我按落库字节重量了三处，结论反转：

- `apps/web/src/pages/Audit.tsx:142-144` 实打实地拼了请求：
  `"/api/v1/admin/audit?limit=" + … + (jobFilter ? "&job_id=" + encodeURIComponent(jobFilter) : "")`。
  `grep -c "target="` 在该文件是 **0**，而 `job_id=` 就在请求串里。筛选器不是装饰。
- 那条门（`tests/unit/test_audit_disposition_labels.py:245` `test_the_page_asks_for_the_parameter_the_handler_accepts`）
  从 `api/routes/admin.py` **整本文件**里取第一个匹配
  `^\s+(\w+): str \| None = Query(default=None, pattern=` 的名字。当前第一个匹配是
  **:686** 的 `target`，它属于 `@admin_router.get("/certificates/revocations")`（:683），
  不是 `@admin_router.get("/audit")`（:721，参数在 :725 是 `job_id`）。
  所以门把「另一个路由的参数名」当成审计处理器的名字去页面里找，找不到就判死。
- 引入时间可归因：`git log -S` 指向 **9e1abd8（#138 证书撤销）**——它把带 `pattern=` 的
  可选查询参数写在 `/audit` **之前**，从此第一个匹配换了人。#138 的提交里全量门已经
  报到 3448/9/5，这条属于其中被归因为「既存」的那批。

也就是说：这是**一条误响的证人**（witness clause 没有绑定它宣称的那个处理器），不是用户
看见的地雷。同一文件里 `_HANDLER_ROLES_RE`（:38-40）已经示范了正确写法——先锚
`@admin_router.get("/audit")` 再向后取。

下一条（重定范围后的 #147）＝修这条门，别改产品代码：

1. 探针改成从 `@admin_router.get("/audit")` 的签名里取参数名（DOTALL、和 roles 那条同一个
   锚形状），并且**先自证取到的这个名字属于 /audit**——断言派生名 == 该签名里
   `Query(default=None, pattern=` 的那个，而不是硬写 `job_id`（硬写就又变成手抄后端）。
2. 页面的断言保持「把派生名带到请求串上」的形状（`&{name}=`），因为 :144 就是这个形状。
3. 变异臂预测（先写后跑）：
   - A1 把 :725 的 `job_id` 改名 ⇒ 门**红**（证明它跟着处理器走）。
   - A2 把 Audit.tsx:144 的 `job_id=` 改掉 ⇒ 门**红**（证明它跟着请求走）。
   - A3 在 admin.py 更靠前的位置再插一个带 `pattern=` 的可选参数路由（复刻 #138 的撞法）
     ⇒ 门必须**绿**（这才是这条门真正的用途；旧写法在这里必红，即误响本体）。
4. 顺带：#146 里「地雷」的说法作废，`Audit.tsx` 的 job 筛选器工作正常；真正的欠账还是
   #145（`cache_note` 在前端没有读者）。

## #147 修那条误响的门：探针不再拿整本文件里的第一个 `pattern=`，而是绑到 `/audit` 自己的签名上

**改动只在测试里，产品代码一字未动。** `test_the_page_asks_for_the_parameter_the_handler_accepts`
原来的探针是 `re.search(r"(?m)^\s+(\w+): str \| None = Query\(default=None, pattern=", 整本 admin.py)`，
取的是**全文第一个**匹配。#138（证书撤销）把 `/certificates/revocations` 的 `target` 写在 `/audit`
**之前**，从此探针读的是别人的参数名，门便永久红在 `the page never sends target — the filter is
cosmetic` —— 一句真话，说的却是一个**工作正常**的页面（#146 的"地雷"判断据此作废）。

**改法（新增 `_audit_handler_block()` 助手）。** 锚 `@admin_router.get("/audit")`，在**下一个
`@admin_router.` 装饰之前**截断，得到 `/audit` 处理器自己那一段；参数名只从这一段里派生。形状与
同文件早已在用的 `_HANDLER_ROLES_RE` 一致（先锚路由，再向后取）。

**自证（不是硬写 `job_id`）。** 派生名必须在该段里以 `{name}={name}` 的形式出现——即处理器把它
**按同名关键字转发**给存储（`audit_trail(limit=limit, job_id=job_id)`）。两边都由派生名生成，所以
改名后依然为真、而删掉转发则为假：它证明的是"探针读的是真正参与过滤的那个参数"，而不是"这段里
恰好有个声明"。

**三臂变异（预测先写在 #147 定义里，再跑；每臂按字节还原并校验 sha）。**

| 臂 | 变异 | 预测 | 实测 |
|---|---|---|---|
| A1 | 把 `/audit` 的参数改名（声明 + 转发 + 响应键三处） | 门**红**（证明它跟着处理器走） | **RED (exit=1)** ✅ 如预测 |
| A2 | 把 `Audit.tsx` 的 `&job_id=` 改成 `&jobId=` | 门**红**（证明它跟着请求走） | **RED (exit=1)** ✅ 如预测 |
| A3 | 在 `/audit` **之前**再插一个带 `pattern=` 的可选参数路由（复刻 #138 的撞法） | 门必须**绿** | **GREEN (exit=0)** ✅ 如预测 |

A3 的绿正是这条门真正的用途：**旧写法在 A3 场景下必红**，而那个红就是误响本体——它已经以
baseline 的形式被测到了（修复前同一条断言报 `the page never sends target`）。A1/A2 则保证修完
之后这条门没有退化成"永远绿"：它仍然两侧都咬得住。

**门证。** `ruff check tests/unit/test_audit_disposition_labels.py` 全绿；
`test_audit_disposition_labels.py` **28 passed**（修复前 1 failed / 27 passed）；
连带 `test_audit_action_parity.py` + `test_web_api.py` 共 **100 passed**。
变异脚本落在仓库外 `D:/面试项目/_arm147.py`（三臂各自还原并校验 sha 后才进下一臂）。

**仍未做。** 本弧（#140–#147）的可归因干净平面全量门还没跑——见下一条。

## #145 落地：缓存披露从原始 JSON dump 里提出来，放到有中文标签的面板上——先量再动手，量的结果改写了任务本身

**先量，任务的前提被改写了一半。** #145 的配方写「step 证据里的缓存披露在前端**一个读者都没有**」。实测：
`craft/gates.py:189` 早就把 `缓存={result.cache_note}` 拼进**门禁 note**，而
`apps/web/src/agent/pages/AgentResult.tsx` 的「检查结果」面板会渲染 `gate.note` —— 所以对**跑命令且通过**
的门，披露是有读者的。真正没有读者的是**另一条路径**：`craft/loop.py:1184` 写进 step evidence 的
`cache_note`，它只出现在 `result.steps[].evidence` 里，而前端 `AgentJobResult` **根本没有 `steps` 字段**
（只有 `plan.steps`），于是它只能靠 `<details>查看完整执行记录</details>` 里的
`JSON.stringify(result, null, 2)` 露出——**裸英文键名、折叠在原始 dump 里**。这就是"诚实的披露没人找得到"。

**枚举门那一问的答案（量到的，不是猜的）。** 配方说"先查枚举门是否覆盖 evidence 键名"。实测
`CacheCheck.verdict` 的三个值（`use` | `fail` | `rebuild`，`sandbox/cache_verify.py:67`）
**从不进入任何载荷**：`SandboxResult`（`sandbox/runner.py:335`）与 `ExecResult`
（`craft/executor.py:108`）都只有 `cache_note: str`。所以给这三个词配中文表会是**死代码**而不是披露——
本批**不加**词表，并把这条判断写进门文件的 docstring，将来真透出了要一起改。

**改动。**
- `apps/web/src/api.ts`：新增 `AgentJobStep`（`id/kind/status/iterations/evidence`）与
  `evidence.cache_note`，并给 `AgentJobResult` 补 `steps?: AgentJobStep[]`。此前该字段**没有类型**，
  这正是它只能待在 dump 里的原因。
- `apps/web/src/agent/pages/AgentResult.tsx`：从 `result.steps[].evidence.cache_note` 取出披露，
  **去重**（同一条 note 每个跑过命令的 step 都会记一次；页面陈述事实，不陈述重复了几次），
  渲染到新的「依赖缓存完整性」面板。**没有 note 就不渲染该面板**——"没挂缓存"必须保持沉默，
  不能变成一句让人安心的"已验证"。

**见证门（`tests/unit/test_cache_disclosure_has_a_reader.py`，4 例）——把读者的键绑到生产者的键上。**
① `craft/loop.py` 的证据投影列表里仍有 `cache_note`；② `sandbox/runner.py` 与 `craft/executor.py`
仍在该字段上有生产者；③ 页面的 `evidence?.<key>` **派生集合必须等于** `{"cache_note"}` 且
⊆ 循环写的键集（**两边都由源码派生，没有一边硬写另一边**）；④ 标签是中文的、且面板是
`cacheNotes.length > 0` 条件渲染的。

**三臂变异（预测先写后跑，各臂按字节还原并校验 sha）。**

| 臂 | 变异 | 预测 | 实测 |
|---|---|---|---|
| M1 | 生产者把证据键改名 `cache_note` → `cacheNote` | 红 | **RED**，点名 `test_the_producer_still_writes_the_cache_key` + `test_the_page_reads_the_key_the_loop_writes` ✅ |
| M2 | 页面改读 `evidence?.cacheNote` | 红 | **RED**，点名 `test_the_page_reads_the_key_the_loop_writes` ✅ |
| M3 | 把中文标签去掉（披露退回只剩原始 JSON） | 红 | **RED**，点名 `test_the_label_is_chinese_and_the_panel_is_conditional` ✅ |

**门证。** `ruff` 全绿；新门 4 passed，连带 `test_craft_cache_disclosure.py` +
`test_craft_loop_cache_disclosure.py` 共 **15 passed**；前端 `tsc --noEmit` 0 错、
`vitest run` **46 文件 / 372 通过**（`AgentResult.test.tsx` +3：披露出得来、多步同一条只陈述一次、
没有缓存时保持沉默）、`vite build` 通过。变异脚本落在仓库外 `D:/面试项目/_arm145.py`。

**仍未做。** 本弧的可归因干净平面全量门仍在跑（见下一条）。
