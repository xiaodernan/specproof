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

## #150 RELEASE 档的两道发布门：结论过去只活在一个没人读的文件里，现在进了评审人的报告

**先量，再动手（三条都是实测）。**
- `--depth RELEASE` 是 shipped 的 CLI 选项（`cli/specproof/commands/verify.py:293` 的
  `click.Choice(["FAST","DEEP","RELEASE"])`），而 `run_release_checks` 在图上无条件执行
  （`agent/graph.py:122-123`：`create_capsule → run_release_checks → publish_report`）。
  节点真跑两道门：把生成的反例测试在 HEAD 上重放、逐个胶囊重算 manifest 摘要
  （`agent/nodes/run_release_checks.py:33-84`）。
- 全库普查（排除 `.scratch`）：`release-report.json` 的**读者数 = 0**（只有
  `run_release_checks.py:87` 一处写）；`release_results` / `release_note` 除
  `tests/unit/test_release_checks.py` 外**没有读者**。
- `agent/nodes/publish_report.py` 只转发 `deep`/`deep_note`（#140 那条缝），把发布门整对键丢掉。
  于是：**用户显式请求最高档，两道门的结论在节点边界死掉**；一次"证据复现不出来"的 RELEASE
  作业，归档报告与一次全通过的 RELEASE 作业**一字不差**。

**改动（两处产品代码 + 一条新门）。**
- `evidence/report.py`：新增 `_render_release_gates(release, note, safe)` 与三个小助手
  （`_gate_verdict` / `_capsule_line` / `_detail_of`），`render_verification_report` 多收
  `release` / `release_note` 两个参数，文档体里 `{release_html}` 紧跟 `{deep_html}`。
  门行**按 `gates` 通用迭代**（节点以后新增门会自动出行，不需要改渲染器，也不给渲染器
  一份手抄的门名册）。四条诚实规则，每条都有案例钉住：
  1. 档位未请求（`payload == {}` 且 note 含 `RELEASE`）→ 只带节点自己的原话 +
     「本次没有执行任何发布门: 该档位未请求, "未跑"不等于"已通过"」，**不产生任何门判定字样**；
  2. 调用方根本不带 release 状态 → 整节不渲染（沉默，不是安慰）；
  3. 胶囊集合为空 → 该门 `未判定` + 「没有条目可校验（该门没有获得任何证据）」，
     绝不写"全部相符"（`passed: True` 的载荷也一样，读者的判断权高于节点的自我宣告）；
  4. 门条目里没有 `passed` 键 → `未判定`。裁决词的唯一来源就是那个旗标，缺了就说不判。
- `agent/nodes/publish_report.py`：转发 `release=raw_state.get("release_results", {})` +
  `release_note=str(raw_state.get("release_note", ""))`（与 #140 同形状，空即真空，不编造）。

**新门 `tests/unit/test_release_gates_reach_the_report.py`（10 例）**：渲染端 8 例（含逐条摘要、
极性翻转、打不开的胶囊、敌意路径转义、缺旗标、空集合）+ 真节点端 2 例（跑 shipped
`publish_report_node` 捕获它递给渲染器的 kwargs，钉"有状态要转发"与"无状态转发空"）。

**七臂变异见证（预测先写进门文件 docstring，再跑；`.scratch/g150/mutate_150.py`）——7/7 MATCHED：**

| 臂 | 变异 | 预测红 | 实测 |
|---|---|---|---|
| R1 | 节点不再转发 release 那对键 | 9,10 | 2 红 [9,10] ✅ |
| R2 | "未请求"分支改口说门已通过 | 3 | 1 红 [3] ✅ |
| R3 | 去掉空胶囊集合的分支 | 5 | 1 红 [5] ✅ |
| R4 | 缺 `passed` 的条目按通过渲染 | 8 | 1 红 [8] ✅ |
| R5 | 整节不插入文档 | 1,2,3,5,6,7,8 | 7 红 ✅ |
| R6 | 胶囊路径不转义 | 7 | 1 红 [7] ✅ |
| R7 | 总判定无视 `passed` | 2 | 1 红 [2] ✅ |

控制腿：`collected == AST 里 def test_ 数 == 10`，0 红；每臂还原后整平面 sha 一致。
案例 4 在 R1/R5 下**故意保持绿**（它断言的是"缺席"，缺席不可能让缺席断言失败），所以它必须与
9/10 这对"载体在场"断言配对才有意义——这条判断写进门 docstring，避免后人把它当漏网臂。

**门证。** `ruff` 三个文件全绿；新门 **10 passed**；连带 `test_report_deep_section.py`(7) +
`test_release_checks.py`(3) **20 passed**；受影响大腿 `-k "report or lineage or release or deep or
publish"` **249 passed / 0 failed（145.18s）**；`mypy evidence/report.py agent/nodes/publish_report.py`
`Success: no issues found in 2 source files`（第一轮 1 条 `no-any-return` 已按字节改好后**重跑整张
臂表**，不是只重跑门）。

**下一号（#151 配方，未做）**：报告有了读者，但**对外宣告还没听这道门**——实测 `verify.py` 在
:293 之后没有任何一处读 `release_results`，也就是 RELEASE 门失败既不改变 CLI 退出码、也不拦证书、
也不进 GitHub Check（:614 那条发布路径）。这一号要动的是命令结果与签发路径，属于用户可观察行为
改变，得单独一批、先量三个入口（CLI 退出码 / 证书签发 / Check 注解）再动。

### #151 对外宣告从此听发布门：RELEASE 门失败不再签发证书（`BLOCKED` 走三个出口）

**实测前提（写代码之前量的，不是推断）**：#150 只给了报告一个读者。`release_results` 在全库
仍只有 `publish_report.py` 一处读者，验收宣告路径上没有任何一处读它：`verify.py` 收了
`--depth RELEASE`、跑了 `run_release_checks` 节点，然后**只用契约行**算 verdict，于是
一道门刚失败的活动照样签发 Merge Certificate、照样把 `VERIFIED` 落进作业摘要、照样在
`--publish-check` 上发布成功注解。三个出口读同一个 `verdict` 变量，所以否决权放在共享策略里、
只在那一个调用点接上。

**订正 #126 里我自己写下的口径**：这一号的原始描述说「不改 CLI 退出码」。实测 `verify.py`
**根本没有按 verdict 退出**——全文件只有三处 `SystemExit`（仓库路径缺失、spec 缺失、preflight
未通过），VERIFIED 与 FAILED 一样退 0。退出码不是「漏了发布门」，是「漏了所有裁决」，而它不能
顺手补：`mcp/tools.py` 在子进程返回码非零时抛 `ToolError` 并丢弃已解析的 BLOCKED 摘要
（`specproof_verify` 里那句 `specproof verify exited with code …`），所以补退出码必须同时给
MCP 那条读路径留一个「非零但仍带裁决」的分支。这一条另立 **#153**，不与本号混落。

**落了什么**：
- `evidence/verdict.py`：`RELEASE_GATE_REASON_PREFIX` 常量、`_gate_row()`、`release_gate_veto()`、
  `evaluate_acceptance()`。共享策略的模块文档句本来就自称「jobs / reports / certificates 共用的
  一份 fail-closed 验收口径」，否决权放这里是归位不是新层。
- `cli/specproof/commands/verify.py`：裁决改走 `evaluate_acceptance(..., release=final_state
  .get("release_results"))`；拒绝通知书的理由先取**门自己那句话**，取不到才退回原有的
  findings / errors / `"contracts unverified"` 链；模块文档的诚实契约补一句「被拒的 RELEASE 门
  也构成 BLOCKED」。
- 新门 `tests/unit/test_release_gates_veto_the_verdict.py`（12 例）。

**四条不许互相混淆的口径**（每条有自己的案例）：
1. 门拒绝 ⇒ `VERIFIED` 降为 `BLOCKED`，并且**点名是哪道门**（状态词仍只用本模块既有的三分法，
   不发明第四态）；
2. 已经 `FAILED` / `BLOCKED` 的作业**永不被改写**——否决只会向下，不会替坏消息编一个好口径，
   也不在已失败的理由里追加门话；
3. 没跑这一档（FAST/DEEP，`release_results={}`）**不受影响**：「没有门」不等于「有门拒绝」，
   否则每个普通作业都会莫名其妙丢掉证书；
4. 门记录里**没有 `passed` 旗标**、或**校验了空集合**，都写作 未判定——它有权拒绝一份验收，
   但永远不能用来支持一份验收。

**见证**：`.scratch/g151/mutate_151.py`，控制腿 `collected=12 == AST def test_ 计数`、
0 红；V1–V8 八臂 **8/8 MATCHED**，0 unsettled，还原后两个源文件字节相同。
预测是按**每个案例踩哪条分支**写的（写在门文档里，先于跑见证）：
V1 调用点不再传 `release=` ⇒ {9,12}；V2 否决永不生效 ⇒ {2,3,6,7,8,9,12}；
V3 「没有门可听」的子句被摘掉 ⇒ {4}；V4 通知书不再引用门话 ⇒ {9}；
V5 否决连 `FAILED` 一起改写 ⇒ {5}；V6 空胶囊名册读作 通过 ⇒ {7}；
V7 无旗标的门读作 通过 ⇒ {6}；V8 门名不再排序 ⇒ {8}。
案例 1、10、11 是「不得误拒」对照腿，八臂下都必须绿。

**门数字（只在干净平面读，PYTHONPATH 钉在平面内并断言 `evidence.verdict.__file__` 落在平面里）**：
`git archive HEAD` 冻结为 `.scratch/plane151`。同一组文件在 HEAD（九个文件，本号新增的门还不存在）
= **149 passed / 0 failed / 0 errors / 0 skipped, 94.932s**；把本号三个文件覆盖进去同一条腿
= **161 / 0 / 0 / 0, 101.089s**，即 **+12 例 / +0 红**。脏工作副本同一条腿是 164 例 **1 红**，
红在 `test_verdict_channel_parity`：`accept: witness craft/accept.py:475 does not contain 'ERROR'`
——那是并发会话正在改的 `craft/accept.py`（工作副本脏、HEAD 干净，同一文件在 HEAD 平面上
13/13 绿），归因明确，不属本号。ruff 两个源文件＋门文件干净；mypy `Success: no issues found in
2 source files`。

**下一号**：
- **#152**（本号实测发现，故意没修）：`run_release_checks` 在 `capsules` 为空时写
  `capsule_integrity=[]` 却仍让 `passed=True`，于是「没有条目可校验」在节点里算通过、在报告里算
  未判定，两个口径不一致；本号的否决只在 `passed` 不为真时触发，所以这条空集合路径仍然只在报告
  里露出来。要修的是节点的旗标，不是新增第四种口径。
- **#153**：CLI 按 verdict 退出码 + `mcp/tools.py` 的非零返回码分支（上面已量）。
- 旧的 #151 之前欠的：`deep_results` 入库与 Web 读路径（需 `agent/worker.py`、`storage/mysql.py`、
  OpenAPI 重导，都是并发写者）；compose 武装仍待用户批准。
### #152 「没有条目可校验」在三个地方有三种含义：汇总旗标不再单独作证

**实测前提（写代码之前量的）**：`run_release_checks_node` 起手是
`results = {"gates": {}, "passed": True}`，两道门都**只清除** `passed`、从不因为「什么都没校验」
把它置灰：`capsules` 为空时写出的是 `capsule_integrity=[]` 而 `passed` 仍是 `True`。于是同一次运行
在三个地方读出三种含义——节点：通过；#150 报告的门行：`未判定（没有条目可校验）`；#151 的否决：
只看总旗标，所以**通过**，证书照签。一份什么都没校验的 RELEASE 活动对外宣告 VERIFIED，而它自己
的报告下面那行写着「该门没有获得任何证据」。

**为什么修下游不修节点**：节点的 `passed` 就是它自己的汇总旗标，语义没写错；错的是下游把旗标当作
唯一证据。去改节点的旗标等于再发明第四种口径（#151 记档时预告的就是这一句）。

**落了什么**：
- `evidence/verdict.py::release_gate_veto`：拒绝读**两处**——总旗标不为真，**或**任一门行读作
  未通过/未判定。一行既然不能证明通过，就不能在自己未被判定时无声地放行一份验收。反过来，当
  每行都写着 通过、只有总旗标拒绝时，理由表末尾补一句 `总判定: 未通过（节点汇总旗标拒绝）`，
  读者不会看到「全通过 ⇒ BLOCKED」这种自相矛盾。
- `evidence/report.py::_render_release_gates`：报告标题不再复述旗标。旗标 True 而有门未判定/未通过
  ⇒ `发布门总判定: 未通过（有门未判定或未通过: <门名>）`，门名过 `safe()`（这一节自己的规矩：
  来自运行的字符串只能是文本）；旗标自己拒绝 ⇒ 仍只写 `未通过`，不冒充「有门没判定」。
  于是同一次运行在报告和对外宣告里回答同一套口径。

**四形必须互不混淆**（每形有自己的唯一证人）：
1. 旗标 True 且每行 通过 ⇒ `通过`（报告案例 1／政策案例 1，对照腿）；
2. 旗标 True 而有行 未判定 ⇒ 标题拒绝并点名（报告 5、8／政策 13、14）；
3. 旗标 True 而有行 未通过 ⇒ 标题拒绝（报告 12，政策 V6 同臂下红）；
4. 只有旗标拒绝、每行都 通过 ⇒ 标题 `未通过` 且**不带**「有门未判定」这句话；理由表带 `总判定`
   那一句（报告 11、2／政策 15）。

**见证**：`.scratch/g152/witness_all_152.py`，两张表一次跑完，控制腿
`collected == AST def test_ 计数`（15 与 12）、0 红，20/20 MATCHED，还原后四个源文件字节相同。
预测先写在两个门 docstring 里。政策面 V1–V10 与 #151 同一形状，新增
V9 只让总旗标有权拒绝（#152 之前的口径）⇒ {13,14}、V10 拿掉 `总判定` 那句话 ⇒ {15}。
报告面 R1–R6 是 #150 的原臂（R5 的预测因新增案例从 7 红改为 9 红），R7 **重新指过**：它原来打的
`overall_word = ... if payload.get("passed") ...` 那行已被本次改写删掉，补丁行消失的臂不是臂，
现在打 `flag_passed` ⇒ {2,11}；W1 discard 行扫描 ⇒ {5,8,12}、W2 拒绝不再点名 ⇒ {12}、
W3 只认 未判定 不认 未通过 ⇒ {12}。
第一轮 W1 被自己的标签骗了：写成 `!= "没有这种判定词"`，那句对**每行**都为真，于是它不是「什么都不
扣」而是「逢门就扣」，红在案例 1 而 5/8/12 全绿——预写的预测判的是臂，不是代码；改成
`uncredited = []` 后**整张表重跑**，`evidence/report.py` 一个字节没为臂让路。

**门数字（干净平面，`git archive bed281b` 解到 `.scratch/plane152`，PYTHONPATH 钉在平面内并先印
`evidence.report.__file__` / `evidence.verdict.__file__` 证明确实读的是平面）**：同一组十二个文件
（两本发布门门 + 报告 DEEP 节 + `test_release_checks` + 八本会驱动 `verify` 命令的测试）
HEAD = **170 passed / 0 红 / 0 错 / 0 skip**；把本号改动的两个源文件与两本门覆盖进去 = **175 passed / 0 红 / 0 错 / 0 skip**，
即 **+5 例 / +0 红**（12→15 与 10→12 两次相加）。
ruff 四个文件干净；mypy `evidence/report.py evidence/verdict.py` `Success: no issues found in
2 source files`。

**订正 #151 的口径（本号实测，不是漏网重试）**：#151 那一句「三个出口读同一个 `verdict` 变量」
量的是 `verify` 命令进程。作业路径在**另一个进程**里自己算裁决：`agent/worker.py:314` 用
`_terminal_status_from_state(final_state)` 取 MySQL 终态，`:319` 用 `_state_summary(final_state,
verdict)` 落库，而这两个函数（worker.py:1081 / :1121）调的都是 `evaluate_verification`——全文件
`grep release` 没有任何一处读 `release_results`。也就是说 Web/MySQL 上的 RELEASE 作业既不会因为
发布门拒绝而变 BLOCKED，落库摘要的 `coverage_reason` 也说不清拒绝来自哪里。这一条另立 **#154**，
它需要自己的案例与臂表（改的是持久化终态，属于产品状态机），不与本号混落。

**下一号**：
- **#154**（上面已量，两行调用点已定位）：作业路径听发布门。
- **#153**：CLI 按 verdict 退出码 + `mcp/tools.py` 的非零返回码分支（#151 已量：现在根本不按裁决
  退出，补退出码会先把 BLOCKED 摘要降级成 raw tail）。
- 旧的欠账：`deep_results` 入库与 Web 读路径（`agent/worker.py`、`storage/mysql.py`、OpenAPI 重导
  都是并发写者）；compose 武装仍待用户批准。

### #154 落地：作业路径听发布门——两个调用点接上同一份共享否决，摘要终于说得出拒绝来自哪道门

**实测前提（写代码之前量的）**：#151/#152 之后，`release_results` 在全库仍有且仅有一个读者
（`publish_report.py`）。作业路径自己算裁决：`agent/worker.py` 的 `_terminal_status_from_state`
（:1128，供 :314 的终态写）与 `_state_summary`（:1081，供 :319 的落库摘要）调的都是
`evaluate_verification`——于是一道刚拒绝的 RELEASE 活动照样把 `VERIFIED` 落进 MySQL、照样给
notify 通道发"验证通过"、照样上 Dashboard，而 `coverage_reason` 只会说"契约未验证"，说不出发
布门的名字。CLI 路径同样受害在摘要上：`verify.py:556/:645` 调 `_state_summary(final_state,
verdict)`，内部那份决策从未听说发布门——#151 给 CLI 的裁决接了 veto，持久化摘要的
`coverage_reason` 却还说不出拒绝来自哪。

**落了什么（一个文件的两行调用点，不是新层）**：
- `agent/worker.py`：两个函数改调 `evaluate_acceptance(..., release=state.get("release_results"))`
  ——与 CLI 签证书、报告渲染同一份共享策略。`_terminal_status_from_state` 的 docstring 补第四行
  口径（门拒绝/未判定 → BLOCKED；`release_results` 缺席或空 = "没有门可听"，不是"门通过"）。
- `evidence/verdict_channels.py`：`job_summary` 通道的 note 是散文声称，本号让它继续说真话
  ——`evaluate_verification(...).status` 改为 `evaluate_acceptance(...).status` + veto 一句，
  顺手更正已漂移的 `worker.py:306` 行号引用（终态写现在是 `transition_job_status_with_notify`）。
  parity 门不读 note，这不是门要求的，是它自称"通道声明"就不得过期。
- 新门 `tests/unit/test_release_gates_veto_the_job.py`（7 例），载荷取 `run_release_checks.py`
  写进 state 的真实形状（`gates.reproducibility` 带 passed 旗标的映射、`gates.capsule_integrity`
  摘要行列表），不是手编的抽象 dict。

**七条口径互不混淆**（每条一个证人）：①门拒绝 ⇒ 终态 VERIFIED→BLOCKED 且 `coverage_reason`
点名 `RELEASE 档发布门 reproducibility`；②行无旗标 ⇒ 未判定照样拒绝（哪怕节点总旗标说通过）；
③空名册 ⇒ 未判定照样拒绝（#152 的第二口径在作业路径同形）；④`release_results` 缺席/空/无
gates ⇒ 普通作业裁决分毫不动；⑤veto 永不改写 FAILED/BLOCKED，也不往已阻塞的理由里加门话；
⑥两个读者（终态/摘要）对同一 state 说同一个故事；⑦全行通过+总旗标通过 ⇒ VERIFIED 照常
（不过度拒绝）。否决不擦证据：`matrix_passed` 仍是 1，通过的还是通过的。

**见证**：`.scratch/g154/mutate_154.py`，控制腿 `collected == AST def test_ 计数 == 7`、0 红；
三臂 **3/3 MATCHED**，还原后 worker.py 字节相同（sha 复核）：A1 终态掉 `release=` ⇒ {1,2,3}；
A2 摘要掉 `release=` ⇒ {1,6}；A3 整体绕过（导入+调用一起变回 `evaluate_verification`）⇒ {1,2,3}。
**预写的预测错了一次，按实测改**：A1 原预测含 6——错。案例 6 断言两个读者一致，而 A1 让它们
通过 `verdict` 参数继续一致（错得一致）；它的否决半边由 1-3 钉、摘要半边由 A2 钉。"为什么绿"
写进了门 docstring（#150 案例 4 同族：缺席/参数传递类断言在单边变异下绿是设计，不是漏网）。
**仪器教训两条**：①见证首版的红集解析拿 `" FAILED "`（带前导空格）匹配 `-q` 短摘要——摘要行
以 `FAILED ` 起头，永远匹配不上，**红集恒空冒充全绿**；改为按 `FAILED + ::test_` 形状匹配。
②A3 只变异调用行不变异导入行 ⇒ NameError 七例全错——那红是脚本造的，不是臂的；导入与调用
必须同臂。另记一笔自伤：调试时先 `write_bytes(b'')` 截断了 worker.py，再用
`git checkout --` 还原，把本号未提交的编辑一并抹掉——编辑重放即恢复，但破坏性命令作用于
"含自己未提交工作的工作树"之前必须先看清树里有什么（#139"提交索引吞并他人 staged 路径"的
镜像：这次是 checkout 吞并自己的 unstaged 工作）。

**门数字**：
- 定向腿（工作树）：新门 + 既有五本 verdict/summary/coverage 门 **86 passed**（79+7）；
  `ruff` 三文件干净；`mypy agent/worker.py evidence/verdict_channels.py`
  `Success: no issues found in 2 source files`。
- 受影响宽腿（工作树，`-k "worker or verdict or release or summary or notify or reclaimer"`）：
  **393 passed / 1 failed**——红在 `test_verdict_channel_parity` 的
  `accept: witness craft/accept.py:475 does not contain 'ERROR'`，归属并行会话（其工作副本正在
  改 craft/accept.py，HEAD 上该 witness 13/13 绿；#151 记档已归因同一条）。
- 干净平面对照（`git archive HEAD` → `.scratch/plane154`，PYTHONPATH 钉平面并先印
  `agent.worker.__file__` 证明确实读的是平面）：同一宽腿 HEAD 基线 = **386 passed / 1 failed**；
  覆盖本号三文件 = **393 passed / 1 failed**，即 **+7 例 / +0 红**，且那条红字节级同因——
  `report_verdict: written but never declared: 通过`，这是已落库 #152 在 `report.py` 引入的
  局部变量名（`verdict != "通过"` 的 compare 形状撞进 report_verdict 通道），**#152 当时的
  12 文件定向腿不含 parity 门所以从未见过它**；并行会话工作树里 9 行的 `report.py` diff 正在
  修它（局部变量 `verdict` → `word`）。两条红都有名有姓有归属，本号零贡献、不代抬。

**下一号**：
- **#153**：CLI 按 verdict 退出码 + `mcp/tools.py` 的非零返回码分支（#151 已量：现在根本不按裁决
  退出，补退出码会先把 BLOCKED 摘要降级成 raw tail）。
- 旧的欠账：`deep_results` 入库与 Web 读路径（`agent/worker.py`、`storage/mysql.py`、OpenAPI 重导
  都是并发写者）；compose 武装仍待用户批准。

### #153 落地：退出码是裁决的最后一个出口——0=VERIFIED / 1=BLOCKED / 2=无裁决，MCP 不再把 BLOCKED 摘要降级成 raw tail

**实测前提（写代码之前量的）**：#151 已量得 `verify.py` 全文件只有三处 `SystemExit`（仓库缺失
:385、spec 缺失 :392、preflight 未过 :443，当年都退 1），VERIFIED 与 FAILED 一样退 0——退出码
不是「漏了发布门」，是「漏了所有裁决」。补之前还必须先看下游：`mcp/tools.py::_tool_verify` 在
子进程返回码非零时无条件抛 `ToolError`，把已经解析出来的 BLOCKED 摘要（含 BLOCKER findings）
整个丢弃，调用方只拿到一句 raw tail。所以退出码与 MCP 读路径必须同号落地，不能拆开。

**落了什么（两处产品代码 + 一条新门）**：
- `cli/specproof/commands/verify.py`：`VERDICT_EXIT_CODES = {"VERIFIED": 0, "BLOCKED": 1,
  "FAILED": 2}` + `exit_code_for()`（词表外的词 fail-closed 映射 2——本模块从不写那个词，映射
  到「无裁决」而不是猜）；三处 setup 退出 1→2（注释写明：环境拒绝构建不是对变更的裁决，"1"
  从此永远意味着一个真实裁决在拒绝这次变更）；命令末尾 `raise SystemExit(exit_code_for(verdict))`
  ——打印的 VERDICT 行、证书/通知书、GitHub Check、退出码，四个出口说同一个词。模块 docstring
  的诚实契约补退出码三行。
- `mcp/tools.py`：非零返回码**但有 parsed verdict** ⇒ 返回摘要 + `cli_exit_code`（BLOCKED 是
  工具对"该不该合"这个问题的成功回答，不是工具故障）；非零**且无裁决** ⇒ 照旧 `ToolError`
  （transport/setup 类失败没有摘要可交）；零退出路径一个字节没动。模块文档的 ToolError 条目
  同步改写。
- 新门 `tests/unit/test_verify_exit_codes.py`（9 例）：CliRunner + monkeypatch 假图覆盖完整命令
  尾部（MySQL persist 在 try/except 内被吞、issue_certificate 空契约返回 None、
  `_maybe_sign_document` 的 SigningError 被吞、`_cleanup_worktrees` 无 workspace 键则 no-op），
  MCP 侧 monkeypatch `_run_cli`。

**四条互不混淆的口径**（每条有自己的证人）：
1. VERIFIED ⇒ 0、BLOCKED ⇒ 1、FAILED ⇒ 2（案例 4/5/6）；
2. setup 失败（仓库缺失/spec 缺失/preflight）⇒ 2，不是 1（案例 2/3）——"1"不再有第二种读法；
3. 词表外的词 ⇒ 2（案例 1，fail-closed 映射腿）；
4. MCP：非零+裁决 ⇒ 摘要+`cli_exit_code`（案例 7）；非零+无裁决 ⇒ `ToolError`（案例 8）；
   零退出 ⇒ 行为不变（案例 9）。

**见证**：`.scratch/g153/mutate_153.py`，控制腿 `collected == AST def test_ 计数 == 9`、0 红；
四臂 **4/4 MATCHED**，还原后 verify.py 与 mcp/tools.py 字节相同（sha 复核）：
E1 词表把 BLOCKED/FAILED 也映到 0 ⇒ {1,5,6}；E2 掉尾部 `raise SystemExit(exit_code_for(verdict))`
⇒ {5,6}；E3 MCP 非零分支退回无条件 ToolError ⇒ {7}；E4 仓库缺失 setup 退回 1 ⇒ {2}。
**预测在跑之前修正过一次**：E1/E2 首版预测把案例 4 算进红集（{1,4,5,6}/{4,5,6}）——错。案例 4
是 VERIFIED→0：E1 只动 BLOCKED/FAILED 两个词条，E2 去掉尾部后 CliRunner fall-through 也退 0，
两臂下它都该绿，它是对照腿不是证人。预测判的是"每个案例踩哪条分支"，必须先于跑写对（#154 A1
同族教训：把"为什么绿"写进门 docstring）。

**门数字**：
- 新门 **9 passed**；`ruff` 三文件干净；`mypy cli/specproof/commands/verify.py mcp/tools.py`
  `Success: no issues found in 2 source files`。
- 受影响宽腿（工作树，11 文件：新门 + verify 命令域 + MCP 五本 + `test_release_gates_veto_the_
  verdict`）：**140 passed / 0 红**。
- 干净平面对照（`git archive HEAD` → `.scratch/plane153`，PYTHONPATH 钉平面）：纯 HEAD 基线
  10 文件 = **131 passed / 0 红**；覆盖本号三文件（新门随之进场）11 文件 = **140 passed / 0 红**，
  即 **+9 例 / +0 红**。
- **仪器教训三条**：①默认 `python` 是 3.11，conftest 的版本门直接 rc=4 退出——见证与门必须用
  `.venv`（3.12）跑，`sys.executable` 才指向对的解释器；②PowerShell 管道 `git archive | tar`
  会把二进制流过文本编码、tar 报 damaged archive——改 `git archive -o` 落盘再 `tar -xf` 中转；
  ③平面解包有两个 CJK 文档名失败（tar 路径编码），与门无关，不追。

**下一号**：
- 旧的欠账（本轮没动）：`deep_results` 入库与 Web 读路径（`agent/worker.py`、`storage/mysql.py`、
  OpenAPI 重导都是并发写者，动手前先量归属）；compose 武装仍待用户批准。

### #155 落地：deep_results 入库 + Dashboard 读路径——DEEP 档的证据终于到达摘要通道

**实测前提（写代码之前量的）**：`deep_results`/`deep_note` 只由 `run_deep_experiments_node` 写
（三路返回：FAST ⇒ 空 dict+"DEEP tier not requested"；缺 workspace ⇒ 空 dict+"DEEP skipped…"；
跑完 ⇒ 完整 results+"DEEP experiments completed: …"），此前唯一读者是 `publish_report.py` 的
HTML/deep-report.json；而 `storage/mysql.py::get_job_summary` 对 summary 列整块 JSON 透传、
`api/routes/jobs.py::get_job_summary` 直接 return，端点又是泛型 `dict[str, Any]` 响应——所以本号
零改动面就是 `_state_summary` 一处投影 + 前端一个 Panel，storage/api/OpenAPI 一个字节不用动
（openapi baseline 零 diff 有门作证）。`verdict_stability.classification` 的词表在
`agent/verdict_stability.py`：stable / flaky / no_runs / single_run / contaminated。

**落了什么（一处后端投影 + 一块前端披露）**：
- `agent/worker.py::_state_summary`：加 `deep_results`——**仅非空写**：空 dict 不能冒充
  "跑过且没发现"，缺席即无话可说；加 `deep_note`——**总写**（`str(state.get(...))`，与
  `retrieval_note` 同风格，"DEEP tier not requested" 是对 FAST 作业的诚实回答）。FAILED 路径
  `_failure_summary` 不动：死在半路的作业没有 DEEP 证据可披露。
- `apps/web/src/pages/JobDetail.tsx`：`Summary` 接口加 `deep_note?`/`deep_results?`；
  `DeepResults` 只声明要渲染的键（verdict_stability / cache_integrity / deep_report_file）——节点
  以后加的键在这里被忽略而不是被猜；`DEEP_CLASSIFICATION_LABELS` 走 `DEPTH_LABELS` 同款
  gloss 模式（"中文 · token"，词表外的值原样透传，绝不替后端断言一个它没报告的分类）；
  overview tab"证据与产物"之后加"DEEP 深度验证披露"Panel，**仅当 `deep_results` 非空在场
  才渲染**（前端对空 dict 再防一道）。
- 门：后端新门 `tests/unit/test_worker_summary_deep_disclosure.py` 4 例，预测预写在 docstring
  （FAST 诚实 note 不造结果 / DEEP 原样透传含 classification token / 空 dict 不冒充一次运行 /
  无键状态序列化为 "" 而不是键消失）；前端 `JobDetail.test.tsx` 2 例（DEEP 节渲染含
  gloss+原样 note+报告文件名 / FAST 不渲染披露节）。

**门数字**：
- 新门 **4 passed**；定向三文件（新门+matrix rows+openapi diff）**22 passed**，OpenAPI
  baseline 零 diff；`ruff`/`mypy` 干净；前端全量 **47 文件 379 passed**。
- 宽腿 10 文件（worker summary 域全量交叉引用）**169 passed / 1 红**——红 = parity accept
  witness `craft/accept.py:475`，与 #154 记档同一处、同一归属：craft/accept.py 是并行会话脏
  文件，本号未触碰，不代抬。
- 干净平面：**+180/-1 行、4 文件**（worker.py +11/-1、JobDetail.tsx +45、JobDetail.test.tsx
  +39、新门 85 行）全在本号清单内；9 个并行会话脏文件原样未动。

**仪器教训一条**：全量 pytest 含黄金 eval 慢阶段（实测 >80min 量级），且后台转存让三次全量
互相并发叠加、互相拖慢——本号门证按 #153 先例回归"定向宽腿"口径；全量套件不是逐号纪律。

**下一号**：
- 旧的欠账（本轮没动）：compose 武装仍待用户批准；并发写者归属（storage/api）在 #155 已量清：
  summary 列读路径是纯透传，后续往 summary 加键不需要再动它们。

### #156 落地：compose 武装——fail-closed 沙箱分支结束停役，隔离平面的承诺与管束终于同键

**实测前提（写代码之前量的）**：`sandbox/runner.py` 的 `ISOLATION_PLANES={"docker"}`，而
`compose.production.yml` 的 worker 早已 `SPECPROOF_SANDBOX: docker`——隔离平面的承诺一直在
声明，containment 却因 `SPECPROOF_EXEC_MODE`/`SPECPROOF_ALLOWED_ROOT` 全仓库无人设置而停在
"local mode: host filesystem access allowed"（#130 只落了披露）。管束只由 `agent/repo_safety.py`
的 env 旋钮驱动（该文件是并行会话脏文件，本号一字未动——武装是部署事实，不是代码改动）。
**根只能是 /workspaces**：worker 没有任何宿主仓库 bind mount（只有
`specproof-workspaces:/workspaces`，与 sandbox dind 共享），worktree 全部来自
`tempfile.mkdtemp`（TMPDIR=/workspaces），即 worker 能看见的仓库路径要么在 /workspaces 下
要么不存在；`check_repo_safety` 的读者只有 prepare_base/prepare_head（worker 侧），
api/outbox-relay 从不跑它——只武装 worker 一个服务是对的。`docker/Dockerfile.*` 无预置旋钮。

**落了什么（两处）**：
- `compose.production.yml` worker environment：`SPECPROOF_EXEC_MODE: sandbox` +
  `SPECPROOF_ALLOWED_ROOT: /workspaces`（注释写明两旋钮与卷事实互相锁死：改一处必须重派生
  另一处）。生效后：`repo_under_allowed_root` 对解析到 /workspaces 之外的仓库拒绝（此前
  local 模式只 warning），`execution_mode_signal` 的 sandbox 分支不再停役；仓库缺失/越界的
  作业 fail-closed，这是该检查存在的本意。
- `tests/unit/test_repo_safety_discloses_the_unarmed_containment.py`：部署事实案例按它自己的
  失败消息契约重派生（"worker 若自己武装，披露必须重派生"）——
  `test_the_production_worker_pins_the_plane_but_arms_no_containment` 更名为
  `..._pins_the_plane_and_arms_containment`，断言不再写死字面量：root == worker 的 TMPDIR ==
  specproof-workspaces 卷挂载点，且 worker 无宿主 bind mount（两个让 /workspaces 成为唯一
  合法根的卷事实）；`_worker_env` 助手随之删除。**机制案例一字未动**：钉了平面而不武装的
  部署照样收到披露（monkeypatch 模拟的就是那种部署），#130 的披露语义对它们永续成立。
  模块 docstring 追加 #156 段说明重派生依据。

**门数字**：
- 本域两文件 **51 passed / 0 红**（披露套件 + repo_safety 机制全套）；安全域宽腿
  `-k "safety or deployment_plane or sandbox"` **92 passed / 1 skipped / 0 红**；
  `ruff`/`mypy` 干净。
- 干净平面：**+54/-22、2 文件**（compose +11/-0、测试 +43/-22）全在本号清单内；9 个并行
  会话脏文件原样未动。
- 预测预写：重派生案例在跑之前写好四条断言（plane/sandbox/root==TMPDIR/挂载点+无宿主挂载），
  一次全绿；compose 的 YAML 可解析性由该案例的 `yaml.safe_load` 本身作证。

**欠账清空**：台账长期挂着的"compose 武装待用户批准"至此闭合（用户本窗口批准）。剩余次级
债：`test_craft_loop_jobs` 的 STUCK vs CANCELLED 判据、`test_slow_marker_tagging` 180s 预算、
CI 两个红 job（minio unauthorized / Maven 播种 126，需要 CI 权限与基础设施）。

### #157 落地：slow-marker 探针的 180s 预算按实测收口——地板是引导不是模块，抬预算而不是换目标

**先量（台账挂了很久的"先量无并发真实耗时"）**：探针 child 原命令各跑 3 次、无并发——
慢模块 `test_agent_runtime.py` **6-8s**，快模块 `test_baseline.py` **5-6s**（exit 5 为预期）。
关键事实：**地板是 conftest/session 引导（~5s），模块导入只占 1-3s**——换一个更小的慢集合
模块只能省 ~2s，对"导入树缩小"的期待被实测否掉（这正是台账给的两个选项里必须先量才能选的
原因）。历史 >180s 的红出自**本地自spawn竞争**（同机全量 lane + 自己 spawn 的子进程互相压），
不是探针的固有成本；CI lane 单进程无 xdist（`ci.yml` 实测命令行），CI 的 slow_marker 两连红
另有真因、已在 #126d 修掉且 CI 确认不再红。

**决定与落地**：`tests/unit/test_slow_marker_tagging.py` 的 child 预算 **180s → 600s**（实测
5-8s 带 ⇒ ≥75 倍余量）；探测目标**保持** `test_agent_runtime.py`——最重的模块保持被钉在
slow 集合里，恰是贡献者最需要的那条信号。代价口径写进 docstring：误报超时 = 红 lane + 人工
排查，真挂死只多等几分钟就被点名；docstring 同时记录两次实测数字与"换目标被否"的理由，
防止下一个号再把它当 open question。

**门数字**：本文件 **2 passed**（13.81s，child 真跑）；`ruff` 干净；`mypy` 对本文件 0 错
（`import tests.conftest` 牵出的 6 条 no-untyped-def 全部是 conftest.py 既有欠账，本号未触碰
该文件、不代修）。干净平面：**+14/-3、1 文件**；9 个并行脏文件原样。

**下一号**：次级债只剩 `test_craft_loop_jobs.py::test_supervisor_cancel_wins_over_leased_worker`
的 STUCK vs CANCELLED（先问谁写状态、按什么顺序）；CI 两个红 job（minio unauthorized /
Maven 播种 126）需要 CI 权限与基础设施。

### #158 关账：STUCK vs CANCELLED 判据问题由并行会话收口——本支冲突改动全部回退，零净变更

**判据调查（本支结论，供追溯）**：CI 红 `assert 'STUCK' == 'CANCELLED'` 不可能是 job.status
（JobStatus 词表无 "stuck"），必出自 `report["result"]`——3x 同签名规则在步内返回 STUCK，而
loop 的 cancel 检查只在步骤边界（`craft/loop.py` 步首），步内落地的取消对三个终态出口
（非 green / 门失败 / DONE）不可见。本支据此落过修：`_store_cancelled` 加 `step_ran` 参数 +
终态出口补离场取消检查 + 回归测试（mid-step cancel 击穿 3x-STUCK 判词）。

**撞车与并行契约**：门证跑两次之间发现并行会话在同一测试文件写同题测试，钉的是**相反契约**
——"两个词都诚实"：worker 的 report 保留自己的裁决词（STUCK 是对用户代码的主张，不是作业
生命周期）；store 的取消是终局且永不被 worker 覆盖（`update_status:failed` 被 CAS 拒绝且
留在 spy 记录）；`job_store_note` 披露覆盖。期间还观测到第二个并行写入的 PROBE-X1 探测
（删除 supersession note，与其测试断言 `job_store_note` 相斥），随后被并行会话自行撤掉。
按并发纪律：不代抬、不抢写，本支改动全部回退。

**处置与验证**：`craft/loop.py` 手术恢复原 `_store_cancelled(step)` 签名/docstring、run()
原三终态出口与诊断原文（期间 PROBE-X1 已被并行自行撤销，恢复后该文件 diff 清空）；
`tests/unit/test_craft_loop_jobs.py` 由并行会话自行整体还原到 HEAD（其测试与本支测试均已
不在，原测试尾 4 行断言完好）。回退后 HEAD 状态全文件 **7 passed**（57.83s）。本号**零净
变更、不产生提交**；CI 一次性红（run 36456722364）的归属与"两词都诚实"契约是否重新落测，
由并行 lane 主理。

**纪律更新**：`craft/loop.py` 取消语义与 `tests/unit/test_craft_loop_jobs.py` 列为并发写者
文件，本支不再触碰（加入 9 个并行脏文件的禁碰清单口径）。

**下一号**：CI 两红 job 需 CI 权限（暂不可达）；从台账/ROADMAP 另选题继续推进。

### #159 CI 恢复绿开工：gh 权限已通，四 job 三因量清——#159a 落 mvnw 修复，minio 撤镜与单测三红留配方

**前提变化（先量）**：gh 对本仓库的查询权限已恢复。master CI 自 10-01 21:34 起连续 14 个
run 全 failure；`2fb4612`（ci.yml 第二个提交）自述"workflow 之前根本无法解析，job 从未
启动"——**这批 job 从未绿过，一出生就是红的**，不是回归。

**三因量证（全部拿到原始日志，不是推断）**：
1. **Maven 播种 exit 126**（eval-golden-cases + nightly-eval）：`mvn-entrypoint.sh: exec:
   ./mvnw: Permission denied`。根因：`demo/spring-backend/mvnw` 在 git 里自 create mode 起
   就是 **100644**（Windows 提交丢执行位），非 root 沙箱用户 `./mvnw` exec 必 126。
2. **Start infrastructure 红**（tests-with-infra）：`docker pull quay.io/minio/minio` 返回
   daemon 级 401。三路互证：quay API 匿名查询同 401、Docker Hub 该 tag 404、本地 docker
   pull 同样 401 —— **MinIO 已把社区镜像从公共 registry 整体撤下，任何 tag 不可匿名拉取**。
   而 `tests/integration/test_artifact_recovery.py` 真依赖 minio（21 处 S3/boto 引用），
   服务不能移除，需选型 S3 兼容替代品（SeaweedFS/Garage 等）+ `storage/minio.py` 兼容性
   验证 + healthcheck 改写——**独立号，不与 #159a 混落**。
3. **tests-no-infra 3 红**（3498 passed / 3 failed），配方清单：
   - 编码棘轮 55>54：`scripts/bench_craft.py:786,819,845` + `scripts/bench_replay.py:769,
     1589,1610,1622,1632,1643,1675,1695,1712` 共 **11 处** subprocess 未钉 codec；两脚本
     不在并行脏清单可修；注意测试文件本身是并行脏文件，验证时以 HEAD 版断言（ceiling 54）
     为准，修完应 44 ≤ 54。
   - `test_bench_mutation` kill-rate **6≠5**：M04=killed/spec_verdict/exit0 被计入 killed；
     先本地复现，分清计数 bug 还是期望过期（#126 i 让红自己点名变异体的设计仍在）。
     **【本支复测（同日）】本地 5 passed（37.55s），不复现**——CI 红读数取自 #159c 之前
     的 run，且本测对目标模块内容敏感（并行在途改动可能移过计数）；留待最新 master CI
     run 复核，暂不认领。
   - `test_verdict_channel_parity`：`report_verdict: written but never declared: 通过`——
     查"通过"写入方与 #109 三词词表口径，改写入方或补声明，二选一前先量。

**#159a 落了什么**：`.github/workflows/ci.yml` 两处 `./mvnw -q -v` → `sh mvnw -q -v`（sh
调用不依赖执行位，Windows 贡献者再提交也不会复发），行间注释写明 126 根因。**验证依赖
下次 CI run**（本地无 maven 容器等效验证手段）；minio 替代选型与单测三红按上面配方继续。

### #159c 编码棘轮落地：两 bench 脚本 16 处钉 utf-8，仓库自身未钉 55→39（ceiling 54 不动）

**先量修正配方**：镜头实测（HEAD 版棘轮门口径）未钉不是配方写的 11 处而是 **16 处**——
`bench_craft.py:786,819,845`（3 处多行式）+ `bench_replay.py:769,1555,1589,1610,1622,1632,
1643,1675,1679,1690,1695,1712,1754`（13 处）；配方漏计 `1555`（java -version 探测）、
`1679`（synthetic commit）、`1690`（synthetic tag）、`1754`（capsule run script 执行）四处。

**修法**：全部按仓库惯例钉 `encoding="utf-8"`（`text=True` 保留，仅插一行/一个 kwarg），
零逻辑改动。`bench_replay.py` 修改前 grep 确认零个已钉 subprocess 调用，replace_all 无误伤。

**验证（分清账与环境噪声）**：
- 两脚本镜头归零；全仓计数 532 = `.scratch/` 评估残留副本 **493** + 仓库自身 **39**。
  39 = 55 − 16，ceiling 54 有 15 余量。CI 无 `.scratch/`，将是 39 ≤ 54 绿。
- 本地跑棘轮门 `1 failed, 3 passed`：唯一失败 `test_the_rest_of_the_repo_cannot_grow_the_debt`
  的 offender 前 12 条全是 `.scratch/attr_9708712/` 下旧版副本（行号与修前完全一致），挂因
  是环境残留非本次改动；pinned-scopes / venv 跳过 / 解码机制三门全绿。
- 门证：ruff 两脚本 All checks passed；mypy 两脚本 no issues；py_compile rc=0；
  `bench_craft.py --help` 正常出 usage。tests/ 无 bench 直测文件（grep 无匹配）。
- 棘轮测试文件本身是并行脏文件（并行会话加了 linked-worktree skip，ceiling 仍 54，不冲突），
  本地验证用工作区版镜头计量，台账以"仓库自身 39"为准。


### #150–#157 合并门追记：隔离 worktree 全量 2 failed / 3539 passed——两红全部对上 #159 配方，零新增动作

**量法**：隔离 worktree `.scratch/wt-mergegate-150-157`（HEAD=`1bfe632`=#157 tip；
`master..HEAD` 为空，#150–#157 已全部并入 master；master 与该点仅差 `ci.yml` 与本文件，
门相关 scripts/tests **零差异**），跑 `pytest tests/unit tests/security tests/fault -q`，
**1008.59s**，`GATE_EXIT=1`。

**读数**：**2 failed / 3539 passed / 7 skipped**。两红逐一对号：

1. `test_subprocess_text_encoding::test_the_rest_of_the_repo_cannot_grow_the_debt`
   **55 > 54**——即 #159 配方第 1 条（编码棘轮）。worktree 内跑无嵌套 worktree 倍增
   （印证并行会话 lens fix 的测量口径：这份 55 就是仓库自身的裸数）。
2. `test_verdict_channel_parity::test_a_declared_word_is_written_and_a_written_word_is_declared`
   `report_verdict: written but never declared: 通过`——#157 提交信息已记（#152 落库代码
   引入、并行会话 `evidence/report.py` 9 行 diff 在修），即 #159 配方第 3 条。

两红均有主、均在修/已留配方，**不代抬、零新增动作**；合并门的使命（给 #150–#157 补上
全量读数）完成。worktree 归档后即清理。

**更正（同日，写档后复核）**：本条目初稿曾认领配方第 1 条，复核发现**已被并行 lane 抢先
在 master 落地**——`git log 1bfe632..master` 里的 `34934e8 #159c encoding ratchet: pin
utf-8 on all 16 unpinned bench-script captures`（实际 16 处，配方里数的 11 处是漏数）。
按工作树内容（master+并行在途）用同 lens 复算主树：**39 个违例（≤ 54，棘轮已绿；
其中含并行在途测试自带的 2 处，纯 HEAD 口径只少不多）**；本次门读数 55>54 是
#157 时点（1bfe632）的历史快照，不是 master 现状。教训：隔离 worktree 出数前先
`git log <worktree_head>..master` 确认没有更新的修复落地，否则会把已修的账记成待办。
红 2（`通过`）仍归并行 `evidence/report.py` 在修。**本支零动作收账，认领撤销。**

### #159d mutation kill-rate 6≠5 定案：stale-bytecode 竞态（配方二选一之外的第三种答案），PYTHONDONTWRITEBYTECODE 根除

**CI 红自点名成功**（verdict 表设计兑现）：`M06=killed/test_failure/exit1`，其余 M01–M05
全部符合期望；错误尾巴 `where 118.0 = with_tax(100.0) | tests/test_pricing`。
配方给的二选一（计数 bug vs 期望过期）**都不对**——期望 5/6 是样本设计的真相，计数逻辑
也无辜；红在测量通道本身。

**机制（实验逐字复现，非推断）**：`run_mutation_bench` 全程复用一个 copytree workspace，
目标模块全部变体（v0/v5/v6）**同字节长**（0.08↔0.18、0.15↔0.18）；CPython pyc 校验 =
(mtime 秒, size)。M05 轮 pytest 编译 v5 写 pyc（头=源 mtime 秒）；M05 finally 还原与
M06 写入连续执行——CI 每轮 pytest ≈1s（bench 文件 05:01:43→05:01:54 跑完 7 轮），
M06 源 mtime 与 pyc 头**同秒同 size** 时 pytest 直读 **M05 的字节码**（TAX_RATE=0.18）
→ `with_tax(100)=118` → M06 被诬杀。概率型 flake（同秒命中≈每轮 20%），与"CI 偶红
偶绿"的历史吻合；本地每轮 >1s 必跨秒，永不复现。
spec 通道无辜的旁证：`check_module` 对内存源串 exec，永远基于真实变异源——M06 无
spec_verdict 与"pytest 读到 v5 字节码"完全自洽。

**实验**：临时 workspace 手工重放——v5 跑 pytest 产 pyc（flags=0, hdr_mtime, size=1309）
→ 写 v6 并 `os.utime` 钉到 pyc 头同秒 → pytest 红 `assert 118.0 == 108.0`（与 CI 逐字
同错）；加 `PYTHONDONTWRITEBYTECODE=1` 重放 → **pyc 不再写出**，同秒下 v6 rc=0。

**修法**：`mutation_bench_lib._run_pytest` 注入 `env["PYTHONDONTWRITEBYTECODE"]="1"`
（子进程每轮从真实源重编译，竞态根除；每轮多编译一个 50 行文件，可忽略）。real-repo
pipeline 通道走 Maven/Java，无 CPython pyc 协议，不受影响，未动。

**门证**：`test_bench_mutation.py` 5 passed（47.87s）；ruff/mypy lib 双清。

### #159e parity「通过」量证收账：写入方修复已由并行 lane 在途（report.py 9 行 diff），本支零动作不代抬

**量**：本地跑 `test_verdict_channel_parity.py` = `1 failed, 12 passed`——**CI 的那条
「通过」红本地已不红**：并行脏 diff `evidence/report.py`（9 行在途）正是在修声明侧
（`verdict != "通过"` → `word != "通过"` 改名 + #109 口径注释），属"补声明"路线的
在途施工，归并行，不抢。
本地面板多出的两条 witness 红（`craft/accept.py:475 does not contain 'ERROR'`、
`agent_console.py:455 does not contain 'UNKNOWN'`）与 HEAD 口径不符（CI 37098380151
同测试仅报「通过」一条）：前者是并行脏文件 `craft/accept.py` 在途 diff 的行号漂移；
后者待并行落库后复测再定性。**本支零动作。**

### #159b minio 撤镜定案：换 SeaweedFS 3.80（六调用实证 + 双 compose 落地 + healthcheck 实测 Healthy）

**选型**：Garage 淘汰（强制 RPC 拓扑初始化，compose 化重）；SeaweedFS 胜出——
Docker Hub 匿名可拉（对照：quay.io/minio 实测 401，DockerHub 该镜像 404，本地 pull 同
401）、单容器内嵌 S3（v4 签名）、官方声明 minio 客户端兼容、镜像内自带 busybox nc/wget
（healthcheck 无需加包）。

**兼容实证（storage/minio.py 全部六个调用，真容器逐个跑过）**：bucket_exists /
make_bucket / put_object / stat_object / get_object / list_objects——匿名与身份双模式
全通；错误凭据 S3Error 拒绝；目录挂载 s3.json 身份隔离生效。`test_artifact_recovery.py`
的 21 处 "minio" 勘察为纯 Python 模拟数据，不真连服务——真依赖面只有 minio-py 客户端
与 compose 服务定义。

**落地**：
- `deploy/seaweedfs/s3.json`：phase0 静态默认身份（minioadmin/specproof_pass）。
- `compose.phase0.yml`：minio 服务换 image/command/healthcheck（`nc -z localhost 9000`，
  start_period 40s 吸收 raft 选举——实测容器起到 "Start Seaweed S3 API Server" ≈25s），
  服务名保留 `minio`（MINIO_HOST 与 app env 契约不动）；旧 9001 控制台无对应物，映射删除。
- `compose.production.yml`：minio override 用 entrypoint 从容器 env 现场 printf 生成
  /tmp/s3.json——凭据单一来源（config_guard 拒默认凭据的臂甲不破）；**command 必须同
  覆盖**（compose 列表合并语义：不覆盖则合并后仍指挂载的默认 s3.json，docker compose
  config 实测抓到）。
- `RUNBOOK.md` 端口表更新（MinIO→SeaweedFS(S3)，9001 删除）。

**门证**：`docker compose -f compose.phase0.yml config` rc=0；双文件合并 config rc=0
（REQUIRED 变量补齐后，确认 command 覆盖与 env 注入生效）；本地
`docker compose up -d --wait minio` 全链 **Healthy**（与 CI `up -d --wait` 等效）；
compose 栈冒烟 ensure_buckets/upload/get_object OK。测试容器与卷已清理。

### #160 conftest 类型债收口：6 条 no-untyped-def 清零，顺带把 pytest 9 已除名的 legacy rootdir 换成 rootpath

**背景**：#157/#159 多轮门证反复被 `import tests.conftest` 牵出 6 条 no-untyped-def 挡路
（当时明言"不代修"——本号补上）。conftest.py 不在并行脏清单，零冲突。

**修**：六个 hook/内部函数钉签名——`pytest_configure/_apply_mysql_isolation/
pytest_report_header/collection_modifyitems` 钉 `pytest.Config`，`pytest_sessionfinish`
钉 `pytest.Session, exitstatus: int`，`_connect` 钉 `-> Any`（pymysql 无 stubs）。

**注解牵出的真发现**：`pytest_collection_modifyitems` 一旦入 mypy 视野，`config.rootdir`
报 attr-defined——实测 pytest 9.1.1 的 `Config` **类上已无 rootdir**（实例上是 legacy
`LocalPath` 兼容物），typed 等价物是 `rootpath: Path`。改用 `config.rootpath.resolve()`
并留注释，防下一个注解这行的人再踩。这不是纯类型修饰：legacy 属性随时可能随 py.path
退役而消失，届时标记 hook 会在 collection 期炸掉整个 session。

**门证**：`mypy tests/conftest.py` **0 errors**（6→0）；ruff 干净；
`test_baseline + test_slow_marker_tagging` **33 passed**（后者即标记行为的回归锁——
integration/slow 双标记经 rootpath 路径仍正确）。

### #161 SLO 时长告警按 depth 分档 + 观测栈引用对账门：§14 FAST/DEEP 各用各的阈值，陈旧引用从此红在测试里

**选题量测**：盘点 ROADMAP「P6 可观测/SLO」欠账时，alerts-slo.yml 头注释自认
「jobs_duration_seconds 无 depth 标签, 暂用 FAST 480s 作统一上界」——即 DEEP 的
1500s 门槛（§14: DEEP 小 PR p95 ≤ 25 分钟）从未被单独告警；OBSERVABILITY.md §6
第 97/98 行同样登记着这笔 🟡。顺藤摸到两处陈旧引用：prometheus.yml 注释说 outbox
relay「尚未进入 compose.production.yml」而该服务早在其中（#161 逐行核实）；
OBSERVABILITY.md §6 第 95 行同句过期。这暴露出一类结构性盲区：本项目指标注册表
**没有静态表**（名字只在第一次上报时出现），告警/看板引用死名字没有任何门会红。

**修法（尊重「直方图无标签」的既有设计）**：observability/metrics.py 的手写注册表
注释明言 histograms 无标签是有意为之——所以维度走**名字**而非标签，与既有先例
`worker_stage_duration_seconds_<node>` 同构：worker 终态上报改
`jobs_duration_seconds_<depth>`（depth 小写拼名）。基数安全的前提量过：三个入口的
词表全封闭——POST /jobs 钉 `^(FAST)$`、MCP `_JOB_DEPTH_VALUES=("FAST",)`、webhook
硬编码 FAST；CLI `--depth` 是 `click.Choice(["FAST","DEEP","RELEASE"])` 但 CLI 走
本地执行不入队。词表取并集 {fast, deep, release}，族有界。

**诚实边界（重要）**：队列今天**只收 FAST**，所以 `_deep` 序列与 DEEP 告警上线即
armed 但无数据——这不是假装接线：DEEP 走 CLI 本地执行不过 worker，1500s 告警要等
DEEP 入队那天自动生效。alerts 描述、看板 description、OBSERVABILITY.md §6 三处
都明写这一点，不冒充已测量。

**落地**：`agent/worker.py` 拆名（注释记词表封闭证据）；alerts-slo.yml 一条
SpecproofJobDurationP95High 拆成 `…P95FastHigh`（>480s）与 `…P95DeepHigh`（>1500s），
头注释的「无标签」自白改为分档说明；grafana 面板 12 从 p50/p95+单阈值线扩为
FAST/DEEP 各 p50+p95 四序列 + 480/1500 双阈值线；prometheus.yml 与 OBSERVABILITY.md
三处陈旧更正（§5 告警表拆两行、§6 FAST ✅ / DEEP 🟡armed、上报清单改名 + 拼接族
登记第四族）。

**对账门（本号的结构性产出）**：新增
`tests/unit/test_observability_metric_parity.py`——把 OBSERVABILITY.md 自己登记的
对账方法变成可执行的门：
1. 从 alerts-slo.yml + prometheus.yml（纯文本，注释也算引用面）+ specproof-slo.json
   （全字符串遍历，prose 里的死名字同样误导）提取全部 `specproof_*` 引用，
   剥 `_bucket/_sum/_count` 展开后缀；
2. 从 agent/api/storage/observability 四棵树扫 `incr(/set_gauge(/observe_duration(`
   调用点，字面量与**同文件模块常量**双层解析（outbox_relay/notify_relay 的名字全走
   `METRIC_* = "..."` 常量，单层字面量必漏——OBSERVABILITY.md 第 111 行的方法描述
   就是这么写的）；
3. 每个引用必须落在「已上报 ∪ 拼接族」里，否则红。四个拼接族（verdict/stage/
   depth/notify）各有上报点指针；族词表**不手抄**——notify 族从 `SendStatus`
   枚举派生、depth 族从 CLI `click.Choice` 派生（取最宽入口词表），产品加词时门
   与代码一起动，杜绝清单漂移。散文占位符（如 `..._<depth>`）剥成尾下划线名丢弃。

**门证**：ruff/mypy 双清（新测试 + worker）；`test_observability_metric_parity +
test_metrics_http` **8 passed**（对账门第一轮就验住了本轮全部改名——若 alerts 还指
旧名立即红）；worker 接线回归 `test_worker_consume_pump + test_worker_cancel_points`
**26 passed**；alerts/prometheus YAML 与看板 JSON 解析 OK。

### #162 GitHub Webhook 响应 p95≤1s 接线（§14 最后一个未接线的性能项之一）：亚秒桶梯度 + 中间件按路径计时

**选题量测**：OBSERVABILITY.md §6 第 100 行登记「Webhook 响应 p95<=1s ❌ 无指标」。
量后发现真正的缺口有两层：①无直方图；②即便加了，注册表的全局桶梯度首格是 **60s**
（为 FAST/DEEP 分钟级目标设计），对 1s 分位数毫无分辨率——histogram_quantile 只能
在桶间线性插值，全落进 60s 桶的 p95 读数毫无意义。所以本号必须先给注册表开
per-histogram 桶梯度，否则接线是假的。

**修法**：
- `observability/metrics.py`：`observe_duration` 增加可选 `buckets` 参数，梯度随
  首次上报钉死（后续调用沿用存储梯度——二次传入不匹配梯度会静默污染累计计数，
  首次为准是设计决定，docstring 写明）；`snapshot()` 的 histograms 项新增
  `bounds` 键（counters/gauges 消费方不受影响，实测全仓只读 counters）。
- `api/server.py` 中间件按路径 `/webhooks/github` 计时：**含 4xx/5xx 与异常路径**
  ——GitHub 感受的是响应时延本身，不是只有成功响应的时延；亚秒梯度
  (0.05, 0.1, 0.25, 0.5, 1.0, 2.5)。/metrics 自抓取不经此路径，不自污染。
- alerts-slo.yml 新增 `SpecproofWebhookDurationP95High`（10m 窗口 p95>1, for 5m）；
  看板新增「Webhook 响应时延」面板（p50/p95 + 1s 参考线，id=16，后续面板 y 坐标
  级联 +8）；OBSERVABILITY.md §5 告警表、§6 第 100 行 ❌→✅、上报清单同步。
- 顺手修掉看板面板 14 描述里第三处「outbox-relay 尚未进入应用栈」陈旧声明
  （与 #161 的 prometheus.yml 同款，同因：无对账门时散文里的部署声明随便老去）。

**对账门零改动自证**：新直方图名是字面量上报，#161 的 parity gate 自动纳管——
alerts/看板引用的 `webhook_github_handling_seconds_bucket` 剥后缀即命中字面量，
无需注册任何新拼接族。

**门证**：ruff/mypy 双清（metrics/metrics_api/server 三文件）；`test_metrics_http +
test_webhook_endpoint + test_observability_metric_parity` **18 passed**（含新增三条：
亚秒梯度渲染、梯度首次为准、401 拒绝响应也必须进直方图——§14 语义的回归锁）；
`test_api_errors + test_production_guard_reachability` **22 passed**（server.py 导入期
回归）；YAML/JSON 解析 OK。

## #163：Worker 崩溃恢复的两个可测时钟——死亡到收回有等待，扫描本身有耗时

**背景**：OBSERVABILITY §6 第 98 行「Worker 崩溃后可恢复 🟡 崩溃检测已接线; 恢复时长
指标未接线」。量测恢复路径后发现语义要先拆开：恢复 = 死亡(最后一次心跳 updated_at)
→ 租约过期(+ttl) → 回收 tick 收回(CAS 判回 QUEUED) → 重投递 → 重新 pickup。其中
**过期后到被收回的等待**与**单轮扫描的耗时**是 worker 侧自然计时点；重投递后的排队
等待属 broker 域无上报点，checkpoint 续跑无独立边界不可测——诚实边界写进 §6。
另一缺口：`worker_reclaim_last_ok_timestamp_seconds` 仪表自 #71 起上报却**没有任何
告警**——「进程活着但 tick 死了」是 up 告警抓不到的形态。

**修法**：
- `agent/worker.py`：`reclaim_stale_running_jobs` 对每个收回行 observe
  `worker_reclaim_recovery_lag_seconds` = `now - updated_at - ttl`（updated_at 正是
  CAS 自身判过期的心跳戳，两钟同源；梯度 30..1200s 按默认 tick 周期 300s 定）；
  `_reclaim_once` 成功路径 observe `worker_reclaim_pass_seconds`（perf_counter,
  梯度 0.05..30s；抛异常的 pass 不观测——那是 pass_error 计数的故事，观测半个扫描
  会污染「完整扫描多久」的语义）。时钟假设：DB 会话钟 == worker 进程钟（compose
  双方 UTC），skew 只弯直方图不弯计数——注释写明。
- alerts-slo.yml 新增 `SpecproofWorkerReclaimTickStale`（time() - gauge > 900s =
  3×默认 tick, for 5m）；THRESHOLDS 表加 RECLAIM_TICK_STALE_SECONDS=900；描述写清
  gauge 舰队级语义（任一副本刷新即算活）与启动期无序列不触发（up 告警补位）。
- 看板面板 16 缩半 (w=24→12)，右侧插入面板 17「崩溃恢复」（lag p50/p95 + pass p95
  + tick 滞后序列 + 900s 阈值线）——同排插入零 y 级联。
- OBSERVABILITY.md：§5 告警表、§6 第 98 行 🟡→✅、worker 上报清单补两个直方图名。

**对账门零改动自证**：两个字面量直方图名 + alerts 引用的 gauge 名全部被 #161 的
parity gate 自动纳管追到上报点，无需注册拼接族。

**门证**：ruff/mypy 双清（worker.py）；`test_job_reclaimer +
test_observability_metric_parity` **37 passed**（含新增两条：lag≈45s 按 ttl+45s
死亡行断言 + 区间梯度首格 30s；pass 计时成功观测 + 异常路径零观测）；JSON 解析 OK
（17 面板，p16/p17 同排无重叠）。drills 缺口门 1 红归并行会话 in-flight diff
（craft/accept.py + DRILLS.md 均为禁碰清单脏文件，#159e 同款 witness 红），本支零触碰。

## #164：Dashboard 进度延迟接线——live 投递才叫延迟，重放叫恢复

**背景**：OBSERVABILITY §6 第 103 行最后一处可自包含收口的 ❌「Dashboard 进度延迟
<=2s 无指标」。量测发现时钟天然存在：`RedisStore.xadd_progress` 每条事件自带
`at`（UTC ISO-8601 写入戳），SSE 循环 `sleep(0.5)` 轮询是延迟主导项——驻留
（写入→发出）可测，无需新表新列。语义必须先拆：**live 投递**（写入后经轮询发出）
才是 SLO 说的「延迟」；**重放**（Last-Event-ID 断线补发/首连历史回放）的条目
驻留长达断档时长——测它会在端点干恢复工作的那一刻报告看板坏了。

**修法**：
- `api/routes/jobs.py`：`_progress_stream` else 分支（live）yield 前 observe
  `dashboard_progress_delivery_lag_seconds` = `now(UTC) - fromisoformat(at)`，
  梯度 0.05..5s（§14 的 2s 上界在梯度内才有分辨率）；时钟回拨 clamp 0、
  `at` 解析失败照发不测（观测钩子绝不门控它搭载的载荷）。重放分支零观测。
  首连历史回放同样走重放分支——同语义（那不是延迟，是补课）。
- alerts-slo.yml 新增 `SpecproofDashboardProgressLagHigh`（10m p95>2, for 5m）；
  THRESHOLDS 加 DASHBOARD_PROGRESS_P95_SECONDS=2。
- 看板面板 18「进度事件驻留」（p50/p95 + 2s 参考线，y=46 新排），row 13 与
  面板 14/15 级联 +8。
- OBSERVABILITY.md：§5 告警表、§6 ❌→✅（诚实边界：SSE 发出→浏览器渲染属
  网络/前端域无服务端观测点）、上报模块清单「三个」→「四个」+ jobs.py 条目。
- **对账门零改动自证**：新字面量名自动纳管（第四个上报模块无需登记拼接族）。

**门证插曲（witness 证伪）**：首轮测试 live 断言 KeyError——spy 驱动复现发现
reader 在流启动前 append 的条目走**重放路径**（第一轮 history 已含它），不观测
正是设计行为；测试自身的 two-phase（先吞重放轮再 append live 条目）才是对的
测法。修正后两测变绿，同时坐实「重放不观测」分支被真实测试覆盖。

**门证**：ruff/mypy 双清（jobs.py）；`test_api_governance +
test_observability_metric_parity` **27 passed**（含新增两条：重放零观测 + live
恰一次观测且 sum<2s、坏 `at` 照发不测）；`test_envelope_retryable + test_web_api`
**78 passed**（SSE/共享模块回归）；JSON 解析 OK（18 面板，y=46/54/55 无重叠）。

## #165：Queue Depth / DLQ 接线——「Job 不丢失」的 broker 侧终于可测

**背景**：OBSERVABILITY §8.10 清单把 Queue Depth 标为「需 rabbitmq_prometheus 插件,
属 phase0 infra 栈改动」而搁置。本轮实测推翻两个前提：①插件无需安装——
rabbitmq:4.0-management-alpine 自带 rabbitmq_prometheus 4.0.9 且已启用（容器内
rabbitmq-plugins list -e 实测 E* running，15692 存活）；②队列级序列无需改
compose——观测栈与 phase0 栈共用 specproof-phase0 网络，服务名直达。但默认
/metrics 是聚合渲染（无 per-queue label，队列选择器会匹配空），队列级深度在
/metrics/per-object 渲染——metrics_path 必须钉死后者，否则告警静默失效
（absent series 不触发，配置合法、信号全黑）。DLQ 队列 q.p1.verify.job.dlq
实测存在，命名规则出自 storage/rabbitmq.py 的 dlq_suffix='.dlq' 拼接——告警用
queue=~"q\\..+\\.dlq" 贴合代码规则而非硬编码单队列。

**修法**：
- prometheus.yml 新增 rabbitmq 抓取任务（metrics_path=/metrics/per-object，
  target rabbitmq:15692；注释写明聚合/per-object 两种渲染的坑）。
- alerts-slo.yml 两条 broker 侧告警：SpecproofVerifyQueueBacklogHigh
  （sum(ready)>50 for 10m——消费端停摆时 broker 深度是唯一还在涨的信号，与
  Outbox 侧积压互不替代）与 SpecproofVerifyDlqNonEmpty（*.dlq>0 for 5m——
  死信不会自己消失）；THRESHOLDS 加 VERIFY_QUEUE_BACKLOG_THRESHOLD=50 与
  VERIFY_DLQ_THRESHOLD=0。
- 看板面板 19「MQ 队列深度」（每车道 ready/unacked，x=0,y=63）与面板 20
  「DLQ 死信数(应为 0)」（stat，绿→红@1，x=18,y=63）——挂 row 13
  「积压 (Job 不丢失)」组尾，零 y 级联。
- OBSERVABILITY.md：§4 验证清单（rabbitmq 目标 down 属正常 + 告警数 7→13——
  旧数字在 #161-#164 连续加告警后早已过时）、§5 表 +2 行、§6「Job 不丢失」行补
  MQ 侧、§8.10 清单移除 Queue Depth/DLQ（并修正「各阶段耗时(仅总时长直方图)」
  的过时括注——stage 族早已在代码拼接上报）、已接线指标名节新增第三方指标段
  （rabbitmq_* 不在 specproof_* 对账管辖，靠抓取 up + 实测验证）。
- test_observability_metric_parity.py 新增配对测试：钉住抓取任务/metrics_path/
  端口与两条告警/看板 expr 的共存——revert 任一侧都是静默失明（对账门
  specproof_* regex 天然看不到 rabbitmq_*）。

**门证插曲（PromQL 转义）**：首轮 DLQ expr 写 `queue=~"q\..+\.dlq"`，promtool
抓出 parse error "unknown escape sequence"——PromQL 字符串字面量不认 `\.`，
正则转义必须双写 `\\.`（单引号 YAML 原样透传、JSON 解一层、PromQL 再解一层，
三层各砍一刀）；看板三个 expr 同病（promtool 管不到 Grafana JSON，只能在配对
测试里钉 JSON 解析后的形态）。修正后 promtool SUCCESS 13 rules。

**门证**：promtool check config SUCCESS（13 rules）；ruff/mypy 双清（parity
测试）；test_observability_metric_parity **3 passed**（含新配对测试）；JSON
解析 20 面板（19/20 同排无重叠）；端到端实测：compose 起 prometheus 后
/api/v1/targets 显示 rabbitmq **up**（api/worker 等 down 属应用栈未起），告警
同款 expr 实查：DLQ 序列 q.p1.verify.job.dlq=0（不触发）、sum(ready)=1（与
rabbitmqctl 对数一致）、per-queue 精确查询=1。本号零 Python 生产代码改动
（纯 infra+docs+测试）。

## #166：各阶段耗时面板——stage 直方图族从「上报了但看不见」到接线

**背景**：§8.10 清单里「各阶段耗时」一行括注「仅总时长直方图」是过时陈述——
`worker_stage_duration_seconds_<node>` 早在 #161 前就由 agent/worker.py 在
updates 流的每个 stage 边界 observe（节点名拼进指标名），对账门也有 stage 拼接族
登记；缺的只是看板入口。量先于动的核实：看板 JSON 全文零 worker_stage 引用、
上报点用默认梯度（首格 60s）、面板空载条件=worker 未跑完任一 stage。

**修法**：
- 看板面板 21「各阶段耗时」(x=0,y=71,w=12)：per-stage p50/p95，
  `histogram_quantile(..., sum by (__name__, le) (rate({__name__=~"specproof_worker_
  stage_duration_seconds_[a-z0-9_]+_bucket"}[15m])))`——族名拼接所以查询必须用
  __name__ regex，按 __name__ 分组保留每 stage 一条序列，图例即指标名。
- 诚实边界写进面板描述与 §8.10：默认梯度首格 60s（为分钟级作业时长设计），
  亚秒级阶段的分位数分辨率有限；定制梯度要改 worker 上报点（#162/#164 的
  per-histogram 首用钉死语义），留给下一号。
- §8.10 清单收口：各阶段耗时移入「已收口」并保留分辨率括注；未接线剩
  Finding Precision、LLM Token 费用、Tool Timeout、ES 延迟、Redis 命中、
  Base/Head 沙箱失败、Certificate 签发率。
- test_observability_metric_parity.py 新增 selector 防漂移测试：对账门把
  __name__ regex 里的引用当 prose 占位符丢弃（捕获名以 _ 结尾），selector
  打错字会静默空面板——钉死精确 selector 文本与 0.95/0.50 两个分位数。

**门证**：JSON 解析 21 面板（21 号 x=0,y=71 与 19/20 无重叠）；ruff 清；
`test_observability_metric_parity` **4 passed**（含新 selector 测试）。零
prometheus/alerts 改动（无新告警，promtool 不重跑）。worker 未起无法实测
序列（面板空载条件已如实记录），expr 语法经 parity 测试的精确文本钉死。



## #167：stage 族定制梯度——亚秒阶段的分位数从「不可测」到「有分辨率」

**背景**：#166 面板 21 上线时留下的诚实边界：`worker_stage_duration_seconds_<node>`
族用默认梯度（首格 60s，为分钟级作业时长设计），而 16 个 graph 节点的耗时跨
两个量级——intake/preflight/build_matrix 亚秒级，prepare_base/generate_
counterexamples/run_deep_experiments 分钟级。首格 60s 意味着所有快节点的
整个分布堆进第一个桶，per-stage p50/p95 在 60s 以下完全无分辨率。

**修法**：agent/worker.py 上报点传 `_STAGE_BUCKETS`（0.25..1800s 共 14 桶：
0.25/0.5/1/2/5/10/30/60/120/300/600/900/1200/1800）。梯度设计三点：低密
亚秒段给快节点分辨率；中段 5/10/30/60/120 覆盖秒到分钟级 LLM/构建节点；
顶格 1800s 高于 DEEP 作业级 p95 目标 1500s——单阶段分位数永不落入 +Inf
桶（histogram_quantile 对 +Inf 无插值，会返回 NaN）。首用钉死语义与
#162 webhook / #163 recovery 两个先例一致（metrics.observe_duration 的
per-histogram ladder，first-use-wins）。面板 21 描述、§8.10 两处括注、
对账文档拼接族行同步去掉「分辨率有限」边界。

**门证**：ruff 清；mypy agent/worker.py 清（项目口径 exclude tests/，
最初误把测试文件带进 mypy 范围报出 16 个既有错属范围噪音非本号引入）；
定向 pytest **37 passed**（含新增 test_stage_duration_family_pins_custom_
ladder——断言 bounds[0]==0.25 / bounds[-1]==1800 而非精确 count，对进程级
全局 registry 顺序无关）；端到端 exposition 实测：0.11s 观测落
le="0.25" 首桶、173s 落 le="300" 桶、默认 `_HISTOGRAM_BUCKETS` 首格仍
60s 未受影响；看板 JSON 解析 21 面板、面板 21 描述更新确认。零
alerts/prometheus.yml 改动（无新告警，promtool 不重跑）；worker 未起无法
实测真实序列（#166 已记录的空载条件不变，需下次起应用栈后观察面板）。



## #168：LLM Token 与费用——craft 车道的计量咽喉点接进 /metrics

**背景**：§8.10 清单「LLM Token 与费用」未接线。量先于动的勘察：
providers/budget.py 的 `TokenBudget.record()` 是 craft 车道（craft/llm.py
流式 :345 与非流式 :612 两路）每次 LLM 调用的唯一计量咽喉点——与 billing
listener（`_emit_usage`）同点同 entry；agent 验证管线（generate_counterexamples
等节点）直连 `provider.chat` 不经过 budget——其 token 无计量点，这是诚实
边界不是遗漏修复项（给验证管线加 budget 是行为变更——BudgetExceeded 会在
作业中途 raise——不属观测接线）。storage/redis.py 的 cache_llm_response /
get_cached_llm_response 全仓零调用点，「Redis 命中」没有活观测点（诚实
不接线，接了就是永久为 0 的谎）——同轮勘察否决。

**修法**：record() 落 entry 后上报 7 计数 + 1 仪表：llm_calls_total、
llm_tokens_prompt/_completion/_reasoning_total、llm_prompt_cache_hit/_miss_
tokens_total（hit/miss 是 prompt 的不相交子集分区）、llm_charge_units_total
（cost_weights 加权，部署相对量纲非货币）、llm_budget_remaining_units（
进程级最后写入仪表，并发 run 相互覆盖——记账看计数器，诚实注进文档与
面板描述）；check()/record() 两处超限 raise 前计数 llm_budget_exceeded_
total（在涨=有 run 死于预算耗尽）。parity 门 EMIT_DIRS 增 providers/
（OBSERVABILITY.md 对账方法行同步四改五）；看板面板 22（x=12,y=71 与
面板 21 并排）三 target：prompt/completion tok/s + charge units/s；
无告警（§14 无 token 阈值，预算强制本就由进程内 BudgetExceeded 执行）。
§8.10 未接线清单移出 LLM Token 与费用并入已收口（边界全注）。

**门证**：ruff 清；mypy providers/budget.py 清；定向 pytest **25 passed**
（含新增 test_record_emits_token_and_charge_metrics 与 test_overrun_records_
budget_exceeded_counter——前者钉 7 计数 delta 与 remaining 仪表，后者钉
超限可见性）；端到端 exposition 实测 9 个 specproof_llm_* 序列全部渲染，
数值对账（charge 180+超限 100=280、remaining -90 负值即超限可见、exceeded
1）；看板 JSON 解析 22 面板、面板 22 x=12,y=71 与 21 并排无重叠。craft
未跑时序列不存在（面板空载条件已如实记录）；promtool 不重跑（零 alerts/
prometheus.yml 改动）。






### #152b 我自己给 #152 引入的一条越界词：门行的词不该借 `verdict` 这个名字

**这是订正，不是新功能**：#152（9708712）落地后跑本弧欠的干净平面全量门，读数
**3350 passed / 2 红 / 0 错 / 5 skip**。两条红里：

- `test_subprocess_text_encoding::test_the_rest_of_the_repo_cannot_grow_the_debt` 在
  `bed281b` 与 `9708712` 两个平面上的红集合**逐行相同**（`scripts/bench_craft.py` 3 处 +
  `scripts/bench_replay.py` 9 处，55 > 上限 54），且那一本文件在工作副本里正被另一个会话改着——
  不是我欠的，也不在本号动它。
- `test_verdict_channel_parity::test_a_declared_word_is_written_and_a_written_word_is_declared`
  在 `bed281b` **绿**、在 `9708712` **红**：`report_verdict: written but never declared: 通过`。
  这条是我的。

**落点已经不是我提交的那个 ref**：修复在途期间，并行 lane 在同一支 `master` 上又落了 23 个提交
（#153–#158、#159a–e、#160–#168）。其中 **#159e（3a4f87a）** 明确记了这条红的归属——
「parity『通过』量证收账：写入方修复已由并行 lane 在途（report.py 9 行 diff），本支零动作不代抬」。
也就是说这条红**一直活着**，本号到 `463cdd9` 仍是必要的而不是重复的：腿的 HEAD 平面里
`evidence/report.py` 仍然写着 `(_, verdict, _) in rendered`，本号覆盖进去才消失。
fill 脚本对这两点各有一条 refuse——测到的 ref 与本号要提交的文件若已被别人改动（不同字节），
或那处误命名槽位在 `git rev-parse HEAD` 上已经不存在（别人已修），都拒绝落笔而不是照抄旧数字。

**根因（用探针定位，不是猜）**：`.scratch/g152/probe_parity.py` 把两个平面的扫描命中逐条打印出来，
`bed281b` 上中文词命中 **0 条**，`9708712` 上恰好 1 条——
`evidence/report.py:237 [compare] '通过'`，也就是本号新写的那行
`uncredited = [name for name, (_, verdict, _) in rendered if verdict != "通过"]`。
#109 那本门按**标识符**认频道：比较式一侧的名字是 `verdict`（或属性 `.verdict`）就认定它在说
`report_verdict` 这个字段，于是要求字面量属于该频道声明的刻度
`{VERIFIED, BLOCKED, NEEDS REVIEW}`。我那个元组槽位其实是 `_gate_verdict` 自己 docstring 里的
「verdict word」——门行的判定词，跟报告的 `verdict` 字段是两种东西，却借了同一个名字，
于是报告文件被读成「拿中文词比较报告裁决字段」。

**为什么改名而不是给中文词加一个频道**：频道表描述的是**字段**（`report.json` 的 verdict、
`result_json.verdict`、作业终态……），而这里没有任何字段叫 `verdict` 装着 `通过`；为一次误命名
去登记一个频道，等于把撞名写成规矩。改名同时把这条约束留在原地：`evidence/report.py` 里加了一行
注释说明槽位为什么必须叫 `word`，两本门的 docstring 记了这次实测，而真正的守门人是
`test_verdict_channel_parity` 本身——将来谁把它改回 `verdict`，那本门立刻红，本号不需要再补一条案例
去复述别人的门。

**门数字（两个平面，同一组 13 个文件：#152 的两本发布门门 + `test_verdict_channel_parity` +
#150/#151 的 10 本 + `test_baseline_pool_alignment`）**：**测在落点 ref `463cdd9`**，
不是测在 9708712——因为要落的平面是前者。`463cdd9` = **188 passed / 1 红**；把本号这两个文件
（`evidence/report.py` 与报告门 docstring）覆盖进去 = **188 passed / 0 红**，即 **+0 例 / −1 红**。
改名是行为中性的，所以唯一允许的读数就是红少一条；若案例数变了，本号就是写错了。
同一组腿先在 `9708712` 上跑过一轮（188 collected / 1 红 → 188 passed / 0 红），两个 ref 之间
这 13 本文件只有 `evidence/verdict_channels.py` 动过（+4/−2，全在 `note=` 散文里），
所以两轮读数相同不是巧合，fill 脚本仍按 `463cdd9` 那一轮写进本节。

**见证**：`.scratch/g152/witness_all_152.py` 在**改名后的字节**上整张表重跑（20 臂，
V1–V10 政策面 + R1–R7/W1–W3 报告面），W1 与 W3 的补丁串跟着改名重指
（`(_, word, _) in rendered if word != "通过"` / `if word == "未判定"]`）；
预测表一个字没动，**20 臂全 MATCHED、还原字节相同**。

**这一号欠下的流程账（写给后面的号）**：#152 的干净平面腿只有 12 个文件，全是我自己那两本门加相邻
调用方——**没有一本是全库结构门**。`test_verdict_channel_parity` 按 `SCAN_ROOTS` 走产品目录，
它会读到我的新代码，却不在我的腿里。所以自本号起，凡改 `evidence/**`、`agent/**`、`cli/**` 的号，
腿集合必须至少含一本按全库走的结构门（`test_verdict_channel_parity`、
`test_hand_written_table_ledger`、`test_drills_gap_claims_hold` 之类），否者「+0 红」只覆盖了我
挑的那 12 本。本弧全量门因此从「收尾动作」提前成了「下一号的第一个动作」——它就是这样抓到东西的。

**下一号（订正 #152 结尾的预告）**：#154 与 #153 已被并行 lane 落掉，不是欠账——
`a81dd49`（作业路径：`_terminal_status_from_state`/`_state_summary` 都改调 `evaluate_acceptance`
并传 `release=state.get("release_results")`，HEAD 上 worker.py:1119/:1175 实测）、
`aedfc7f`（CLI 退出码 `VERDICT_EXIT_CODES = {VERIFIED: 0, BLOCKED: 1, FAILED: 2}` + MCP 不再丢弃
BLOCKED 摘要）、`d13f0bd`（#155 `deep_results` 进持久化摘要 + Dashboard 面板）。
本号之后走**全弧欠的那件事**：在落点 ref 的干净平面上跑一次全量合并门，把红逐条归因，
再据读数挑 #169；不自挑一个「听起来对」的号绕过测量。

**顺手量到的一个候选（只记已证的部分）**：`cli/specproof/commands/craft.py:669-673` 手抄了
同一套「裁决→退出码」映射，而不引用 #153 在 verify 那条路上建立的 `exit_code_for`，
两条链的尾巴都是 `sys.exit(2)`；`craft/accept.py:51` 的 `AcceptVerdict` 只有
`{VERIFIED, BLOCKED, ERROR}` 三个词，所以 2 目前**恰好**只由 `ERROR` 走到——
「未知词被静默降级成 ERROR」在今天的字节上不可达，本号不把它写成缺陷（写过的草稿已经删：
原先那句说 `result.verdict` 能拿到 `_verification_summary` 的 `FAILED`，实测 `result.verdict`
来自 `AcceptResult`，而 `FAILED` 只存在于另一个 dict 里，两个载体没有同一个读者被证过）。
剩下的可修事实只有一条：同一个数字 2 在两条命令里挂着两个名字（verify 的 `FAILED` /
craft 的 `ERROR`），而全库没有一本门把「哪些命令按裁决退出、数字各是什么」对账。
这一条要在下一号用臂表证明它有牙齿（把 craft 的链改成引用 `exit_code_for` 会不会红、
把 `ERROR` 从 `AcceptVerdict` 里去掉会不会被 2 静默接住），不在本号动。

### #169 验收原因有五种，页面却只讲其中一种：文案判据换成 payload 能证明的字段

**实测到的缺陷**：`agent/worker.py::_state_summary` 把 `decision.reason` 原样存成
`coverage_reason`，而 `evidence/verdict.py` 里那个串是**一个「；」拼接的多原因列表**——
零检查（`if not rows`）、记录格式/契约标识/汇总不一致、`缺少契约检查结果：…`、
`存在 N 项已确认问题…`、`执行过程有错误…`，再叠上 `release_gate_veto` 的
`RELEASE 档发布门 <name>: <word>`。`api/routes/jobs.py::get_job_summary` 把摘要**不加过滤**
透出去，所以这些都会到浏览器。而 `apps/web/src/pages/JobDetail.tsx:310-311`（以及
`nextAction` 的第三条分支）对**任何一种**原因都渲染同一句话：
「本次没有形成可执行的检查项。请完善验收条件，或接入对应检查器后重新验收。」，
并把下一步指到 `#/guide`。一个四条检查都跑完、只被发布门拒掉的作业，于是被告知
「你根本没形成检查」——评审人按错的方向补验收条件，真正的门结论在同一个页面上方
就写着，却没有被当成下一步的依据。

**为什么用 `matrix_rows_total` 而不是猜原因**：那句文案唯一能被 payload 证明的形式是
「本轮没有形成任何检查行」，而 `agent/worker.py::_matrix_rows_for_summary` 恰好持久化了它
（`matrix_rows_total`，2026-09-23 起随摘要入库）。三种读数必须互不混淆：
`=== 0`（确实没形成检查）、`> 0`（形成了检查，原因在别处）、**缺席**（摘要早于该字段，
属于未知）。缺席当 0 就是本号要修的那个错的翻版，所以判据写成
`typeof s?.matrix_rows_total === "number"`，绝不用 `?? 0`。

**落地内容**：banner 的标题与正文、`degraded` 框的链接、`nextAction` 的第三条分支，
四处都按同一个 `rowsTotal` 分流；小节标题从中性的「本次验收结论未能确认」起，
把「哪一种原因」留给后端原话（`coverage_reason` 逐字仍在框里，#150 的披露不动）。
`Summary` 接口补 `matrix_rows_total?: number`——它是已提交摘要里真实存在的键，
不是我为测试发明的字段。

**门数字（全部走文件，不手抄）**：
新增 4 条 vitest 案例，**先对旧页面跑一次**：3 红 / 20 绿（共 23 例），红的三条正是「把四种原因讲成一种」
的三处断言，绿的正是那句文案**确实成立**的那一条（零检查作业），所以改文不是把话删了了事。
改完同一本文件 23 passed / 0 红；全量 web 套件 47 个文件 383 例：381 passed、2 failed——那 2 条红是并发会话正在改的
`SameRepoCraftPanel.tsx` 与其测试（该测试只 import `../SameRepoCraftPanel` 与 `../../api`，
从不 import `JobDetail`），按案例名与失败原因（`Found multiple elements with the text: /已完成/`）
归因给别人，本号不动。`tsc --noEmit` 零诊断。落地改动 测试文件 +78/-0（纯追加），页面 +13/-3。

**见证（`.scratch/g169/witness169.py`，7 臂）**：7 臂全 CAUGHT（0 存活、0 MISMATCH），还原字节相同。每臂只拆一个子句，
预测的是**案例名**而不是条数——`A1` 只毁正文分流、`A2` 只毁标题分流、`A2b` 把同一
三元式朝反方向掰（只有零检查那条该红，用来证明那条绿案例不是空转）、`A3` 把缺席读成 0、
`A4` 让 `degraded` 链接重新对所有原因指引导页、`A5` 让主下一步按钮同样不分类、
`L1` 把小节标题改回「验收覆盖不足」。`A1` 与 `A2` 预测相同而机制不同，正是标题与正文
各自承重的证据。

**这一号欠下的流程账（写给后面的号）**：一次「拼接串当分类键」在同一条弧上出现第三次
（#109 的标识符撞名、#152b 的门行判定词、本号的多原因共用一句文案）。凡文案要说出
**原因**，判据必须是某个具名字段，不能是对一段散文的正则或存在性检查。

**下一号**：#170 的候选已定位——`JobDetail.tsx` 的 `nextAction` 第一条操作数是
`status === "UNVERIFIED"`，而本文件 `STATUS_HELP` 上方的注释（`storage/mysql.py::ALL_STATUSES`
对账，由 `tests/unit/test_job_status_channel_parity.py` 钉住）明确说 `UNVERIFIED` **不是作业状态**。
先用探针量那本门扫不扫 `nextAction` 里的字面量（扫不到就是门有洞，不是分支没问题），
再决定是删不可达分支还是补门；本号不动它。

## #170 状态词表的「比较位置」从未被任何门看见：删掉一条永远走不到的分支，并把页面手抄的两份集合钉住

**实测起点（先量，不改）**：#110 那本门把作业状态词表钉在三个**声明位置**上 ——
`StatusPill.tsx::JOB_STATUSES`（数组元素）、`STATUS_LABELS` 与 `JobDetail.tsx::STATUS_HELP`
（Record 键）。它没钉**使用位置**。用 `\b\w*[sS]tatus\w* === "大写词"` 扫一遍 `apps/web/src`，
得到的站点里只有一处属于验收作业通道却又不在那三个声明位置：

- `apps/web/src/pages/JobDetail.tsx:286` 的 `nextAction` 三元链里带着
  `status === "UNVERIFIED" || …`。而同一个文件第 268 行写得很清楚
  `const status = (job.status || "").toUpperCase()` —— 这个 `status` 只会是作业行的状态；
  `storage/mysql.py::_VALID_TRANSITIONS` 十个状态里没有 `UNVERIFIED`，`RUNNING` 也到不了它
  （它是矩阵行/裁决词，正是 #110 的 `_NOT_STATUSES` 点名要挡的那两个词之一）。
  也就是说：这条分支**永远走不到**，而它已经在#169 之前一直被误当作用户路径。
  它在 `||` 里，删掉之后行为不变（另一个析取项 `!!s?.coverage_reason && rowsTotal === 0` 才是活的那条）。

扫出来的其余大写比较词**属于另外两套词表**，不是缺陷：`AgentResult.tsx:109` 的
`job.status === "COMPLETED"` 走的是 Craft 控制台的裁决（`api/agent_runtime.py::console_status_label`
把 store 的 `succeeded` 映射成 `COMPLETED`；store 自己那套是小写的
`pending/running/succeeded/failed/cancel`，见 `storage/agent_jobs.py::JOB_STATUSES`），
`Contracts.tsx:70` 走的是契约状态。所以按词的形状建门会一次误伤三套通道 ——
新条款必须绑「左值是不是状态」而不是「词长得像不像枚举」。

**第二处实测到的洞**：`JobDetail.tsx:44-45` 手抄了 `ACTIVE` / `TERMINAL` 两个集合，
而 `TERMINAL.has(currentStatus)` 决定的是关掉进度流、触发工件加载、以及 5 秒轮询是否继续
（第 204/221/233 行）。今天它恰好等于后端的 `TERMINAL_STATUSES`，但**没有任何门钉它**：
后端新增一个终态，这个页面就会对着一件已经结束的作业永远轮询下去。

**改了什么**：
1. `JobDetail.tsx`：删掉 `nextAction` 里那条不可达的 `status === "UNVERIFIED" ||`（+1/−1）。
2. `tests/unit/test_job_status_channel_parity.py`：追加三条条款 + 两个读取器 ——
   `test_job_detail_compares_only_statuses_the_machine_can_hold`（比较位置的每个操作数必须是
   状态机真有的状态，并带一条**下限** `len(sites) >= 3`：扫描解析不到东西时，条款不能算通过）、
   `test_job_detail_keeps_no_ungated_copy_of_the_terminal_set`（页面 TERMINAL == 后端 TERMINAL_STATUSES，
   两个方向分别说清「永远轮询」与「提前停轮」）、
   `test_job_detail_progress_bar_set_covers_in_flight_states`
   （ACTIVE 不含终态、不遗漏任何非终态；唯一例外 `FAILED` 是被点名的那条：它可重试所以仍要轮询，
   但没有在飞进度可画，所以没有进度条）。

**读数（全部来自本次真实输出）**：门在 HEAD 收 **8** 例，加条款后 **11 例 0.91s**（快环，纯文本，不碰数据库）；
`ruff check` All checks passed、`mypy` Success、`npx tsc --noEmit` **0 诊断**；
`vitest src/pages/JobDetail.test.tsx` 删除前后都是 **23 passed**（例数没变，#169 那四条 payload 分流案例仍绿，
证明这一刀确实行为不变）。

**见证：4 臂，全部 MATCHED，还原字节相同**（`.scratch/g170/witness170.py`，预测在跑之前写死）：
- E1 把不可达分支**放回去**（反向控制：门必须在改前的页面上点名它）→ 预测且实测只红
  `compares_only_statuses…`；
- E2 从页面 TERMINAL 抄件里删掉 `STALE` → 只红 `no_ungated_copy_of_the_terminal_set`；
- E3 把终态 `ERROR` 塞进 ACTIVE → 只红 `progress_bar_set_covers_in_flight_states`；
- E4 把门的正则收窄到解析不到任何站点 → 红在下限那条断言上（证明下限是承重的，不是装饰）。

**流程规则（进本弧纪律）**：一本只读**声明位置**的词表门，会在「用这个词的那条分支」腐烂时照样绿。
词表门必须同时钉比较位置，而且钉的是**左值的身份**（它是不是状态），不是词的形状 ——
因为这个产品里至少有三套状态词表（验收作业 / Craft 控制台 / 契约），它们的合法词互相都是对方的死词。

**#171 种子（只登记，未量）**：控制台那套词（`console_status_label` 的六个裁决 +
`api/routes/agent_console.py` 的 `STATUS_LABELS` 与 `_CONSOLE_TO_STORE_STATUS`）在前端有若干手抄比较站点
（`AgentResult.tsx`、`AgentJobDetail.tsx`、`agent/util.ts::agentStatusMeta`），
但**还没量过它们有没有门**；先量再决定是补对账还是删副本。另：`STATUS_LABELS` 这个名字在
后端控制台与前端 `StatusPill.tsx` 各有一份，属同一通道不同词表，量普查时别把两者当同一份。

### #171 矩阵结果词表：`DEGRADED` 是一个没有任何生产者写过的徽章，而四份副本没人对账（已落地）

**量到的事实（HEAD `0932ebe`，全部来自源码而不是记忆）**

- 权威集合只有一处：`agent/matrix_policy.py:31` `_RESULT_PRIORITY = {"FAIL":3,"PASS":2,"UNVERIFIED":1}`；`_merge_verdict` 的每个返回值要么是这张表的键、要么是它自己 `best = "UNVERIFIED"` 的字面默认值。写 `result` 的节点（`run_static_checks.py:158`、`compile_contracts.py:214`、`run_differential.py:615-640`、`checkers/java_source.py:541-568`）也只写这三个词。
- 但把这套词写给读者看的副本有 **四份**，没有一条门比较过它们：
  1. `apps/web/src/ui/toneMap.ts` 的 `resultPill` switch（配色）；
  2. `apps/web/src/pages/Matrix.tsx:9` 的私有 `const RESULT`（中文说明 + 搜索框匹配文本）；
  3. `evidence/report.py:304-308` 的 `result_class`（HTML 报告行样式）；
  4. `agent/nodes/build_matrix.py:248-250` 的三处 `row["result"] == ...`（矩阵页四个 StatCard 的分母）。
- **一个词没有值。** 前端两份都给了 `DEGRADED` 含义（"检查受限" / pill-mute）。全仓 `DEGRADED` 实测：Python 产品代码 0 个生产者（只有 `tests/unit/test_terminal_verdict_names_its_check.py` 里的变量名和文档），它真正属于另一套刻度——`/api/v1/health` 的 `ok/degraded`，而 `toneMap.ts` 里给那套刻度做翻译的 `healthStatusLabel` 早就存在。于是这枚徽章永远不可能出现，同时它把"这一轮跑受限"的说法塞进了结果词表：读者若真遇到异常值，看到的是 未知，而不是一个被产品承诺过的状态。
- **一份词表没有门。** `evidence/verdict_channels.py` 的 `matrix_row` 通道 scale 写的正是那三个词（碰巧对），但它的对账门 `test_verdict_channel_parity.py` 只比较 `Literal`/pydantic `pattern` 那类权威，从不读 `_RESULT_PRIORITY`，所以"对"这件事没有任何东西在守。

**改法**

`resultPill` 的 switch 换成一张表 `RESULT_STATES`（一行一个值：`cls` + `caption`），`DEGRADED` 随之消失；`Matrix.tsx` 删掉自己那份 `RESULT`，改 `import { resultCaption } from "../ui"`。未知值仍走 pill-mute（与旧 `DEGRADED` 同色），只是不再享有中文名——`resultPill` 给 `未知 UNKNOWN`、`resultCaption` 给 `待确认状态`，搜索框现在匹配的是屏幕上真实出现的那句。行为等价性由两侧测试各自钉住：`vitest` 58 例（Matrix 21、toneMap 37）改前改后同一集合绿，其中我为收敛新增 1 例（搜索中文说明）。

**新门（`tests/unit/test_matrix_result_vocabulary_parity.py`，7 例）**

五个来源各读各的源码：`_RESULT_PRIORITY`（正则取字面表）、`_merge_verdict` 的字面默认值（AST）、`RESULT_STATES`（`^export const` 锚定，一行一条）、`report.py` 的 `result_class`（AST，注意它是 `{...}.get(...)`，字面量是调用的接收者而不是赋值右值）、`build_matrix.py` 的比较（AST，含 `>=3` 自检）、`verdict_channels.py` 的 `matrix_row` scale（AST，`frozenset({...})` 要剥一层 Call）。断言分三个方向：每个值有词、每个词有值、每条表项同时带 `cls` 与 `caption`；外加普查 `apps/web/src` 里"在词表位置"写这些词的站点，只允许 `src/ui/` 一份。

**见证：5 臂，全部 MATCHED，还原逐字节相同**

- `A1` 把死词放回去 ⇒ 2 条门红 + 2 条 vitest 红（含矩阵页"两枚 未知"计数）。
- `A2` 让页面重新声明单行 `const RESULT` ⇒ 2 条门红（导入位 + 普查）。**这条臂第一轮 MISMATCH，抓到门自身一个洞**：普查只认行首键，而单行 map（正是 HEAD 上 `Matrix.tsx` 的形状）整个溜过去；改成 `^\s*|[{,]\s*` 后 MATCHED。改完的基线当场被 `sites>=3` 的下限拒了一次（"扫到 0 条"≠"很干净"），说明这类假绿确实有东西在拦。
- `A3` 让一条表项丢掉 `caption` ⇒ 1 条门红 + 3 条 vitest 红。第一轮预测漏了搜索框那例（预测之外的额外红，不是洞），按实测补进预测。
- `A4` 把普查的词表缩成一个不存在的词 ⇒ 门红在自己的下限上（vacuity 控制）。
- `A5` 把 `_merge_verdict` 的默认值改成 `"UNKNOWN"` ⇒ 恰 1 条门红（词表没动，所以只有默认值那条子句看得见）。

**读数**

- `pytest` 本门 7/0 红；连同邻居 `test_verdict_channel_parity.py`、`test_severity_vocabulary_parity.py`、`test_job_status_channel_parity.py`、`test_web_api.py` 共 **80 passed / 1 failed**。那 1 条红不是本单位的：`api/routes/agent_console.py`(+41) 与 `craft/accept.py`(+51) 有并发会话未提交的改动，把 witness 指向的 455/475 两行挪走了；那两个文件在禁改清单里，只登记不碰。
- `npx tsc --noEmit` rc=0；`ruff check` rc=0；`mypy` 门文件 Success。
- 门耗时 <1s（纯文本/AST），不进基线。

**合并门读数（落地前补跑）/ 下一号种子**

- 全量合并 Python 门（本弧落地前补跑，两个平面各一次）：纯 HEAD 平面 collect **3667** 例，同一平面叠加本弧 7 个文件后 collect **3674** 例 ⇒ 差值恰为新门自己的 7 例；WITH 平面 **4 failed / 3644 passed / 26 skipped (1265.87s)**，把这 4 条案例名拿到**不含本弧**的纯 HEAD 平面重跑 ⇒ 红的正是同 4 条名字（同一多重集，非按条数对上），所以本弧是 **+7 collected / +0 红**。平面自证：两条 run 的 log 首行分别是 `rootdir: D:\面试项目\plane171`（WITH）与 `plane171base`（WITHOUT），`agent.__file__` 也在平面内——工作副本里那些并发车道的脏文件没有参与本次测量。那 4 条红不归本弧：`tests/integration/test_differential.py:129`（`'NoneType' object has no attribute 'lower'`）、`tests/integration/test_phase_acceptance.py:109`（`argument of type 'NoneType' is not iterable`）与同文件 `:226`（`AssertionError: Matrix has no rows`）、`tests/unit/test_metrics_http.py:108`（histogram ladder 断言），本弧没有改动它们的任何输入。
- `#172` 种子（已量，未修）：Craft 控制台的**终态集合在前端有五份手抄**——`apps/web/src/agent/components.tsx:13`（`TERMINAL_AGENT_STATUSES`）、`AgentJobDetail.tsx:91`、`AgentResult.tsx:17`、`AgentResult.tsx:110`，以及第五份 `agent/pages/AgentToolStream.tsx:87`（藏在 SSE 尾标的模板串里，`["COMPLETED","FAILED","CANCELLED"].includes(job.status)` 直接写在 JSX 内）。权威是 `api/agent_runtime.py:106 console_status_label`：#69 之后它末尾是 `return str(job.status)`，docstring 明写「unknown status 原样透传，由 UI 自己的 unknown handling 决定怎么显示」（:114-116），而 `test_agent_console_api.py:234` 已把这条透传钉住（`"archived" → "archived"）。**那句话目前没有兑现的证人**：一个超出词表的**已终态**存储状态到了前端，五份副本一律判「非终态」，于是 `AgentResult.tsx:36` 永远显示「任务尚未进入终态，独立验收还不会运行」，`AgentToolStream` 的尾标也永远不带「已结束」——为未知编不出含义是对的，但把未知当成「还在跑」是另一种编造。收法与 #170/#171 同型：一处导出（`src/ui` 或 `src/agent/util.ts`）＋一条词表门（前端集合 == 后端 `_TERMINAL_CONSOLE_STATUSES`，两个方向 + 普查不许有第六份），并为透传 token 补一条「终态但未识别 ⇒ 明确说不认识，而不是说仍在执行」的界面见证。
- 另两处只刻画不修：`apps/web/src/pages/Jobs.tsx:49` 的 `data.total ?? data.jobs?.length ?? 0` 在路由总返回真实 `COUNT`（`storage/mysql.py::search_jobs`）的前提下是潜在回退而非当前缺陷，但 `api.ts` 把 `total?: number` 声明成可选，等于允许未来某个调用点把窗口长度当总数；`tests/e2e/longtext.spec.ts` 用 "证据不足" 作为矩阵行文案锚点，本弧已确认它仍成立（`UNVERIFIED` 的中文说明未变）。

### #172 Craft 控制台的运行阶段：五份「终态」手抄，加上 #69 那句「由 UI 自己的 unknown handling 决定」一直没有证人（已落地）

**量到的事实（HEAD `d33fb73`，全部来自源码而不是记忆）**

- 映射权威只有一处：`api/agent_runtime.py:106 console_status_label`。它的六个返回词是 `PLANNING / AWAITING_APPROVAL / EXECUTING / COMPLETED / FAILED / CANCELLED`（`pending` 行的两个词藏在同一个条件返回里），末尾 #69 留下的 `return str(job.status)` 把词表外的存储状态**原样透传**，docstring 明写「由 UI 自己的 unknown handling 决定怎么显示」；`tests/unit/test_agent_console_api.py:234` 与 `:249` 已把这条透传钉在 API 层（`"archived" → "archived"`）。
- 服务端强制只认一份集合：`api/routes/agent_console.py:111 _TERMINAL_CONSOLE_STATUSES`。取消走 `_require_cancellable`（`:675` 定义，`:677` 判 `status in _TERMINAL_CONSOLE_STATUSES` 抛 409），审批走 `:869` 同一句。同一行的 `:110 _CANCELLABLE_STATUSES` 在 HEAD **全仓只有它自己的声明这一处**（`git grep`），是死声明。
- 前端把「终态」手抄了**五份**：`apps/web/src/agent/components.tsx:13`（`TERMINAL_AGENT_STATUSES`，停轮询）、`pages/AgentJobDetail.tsx:91`（禁取消按钮）、`pages/AgentResult.tsx:17`（验收面板）、`pages/AgentResult.tsx:110`（结果面板）、`pages/AgentToolStream.tsx:87`（SSE 尾标，藏在模板串里）。`git grep` 实测 `tests/` 里没有任何东西读过这些名字或那两个后端 frozenset ⇒ 五份副本与后端之间**零对账**。

**这个缺陷读者看到什么**

一个词表外的**已终态**存储状态到了前端（旧行、旧写入者），五份副本一律判「非终态」：验收面板永远显示「任务尚未进入终态，独立验收还不会运行」，结果面板永远「任务还在处理中」，SSE 尾标永远不带「已结束」，轮询永不停止。#69 在后端删掉的是「替未知编一个含义」（把未知报成 `CANCELLED`），前端却用 `!terminal` 这个二值判断把同一件事**反着**编了一遍：把未知当成「还在跑」。承诺过的「UI 自己的 unknown handling」在 UI 里根本不存在。

**改法**

- 一处导出（`apps/web/src/agent/util.ts`）：`AGENT_ACTIVE_STATUSES` / `AGENT_TERMINAL_STATUSES` / `agentRunPhase() → "active" | "terminal" | "unknown"` / `isAgentTerminal()` / `agentUnknownNotice()`。
- 四个站点全部改成调用导出（`components.tsx` 删掉自己那份 `new Set`）。**收敛处行为等价**：集合一字未动，变的只是「谁拥有它」。
- 真正改行为的只有第三支：`AgentResult` 的两个面板与 `AgentToolStream` 的尾标对 `unknown` 明确说「这一轮上报的状态不在本页词表里 / 无法判断它是仍在执行还是已经结束」，既不按「仍在执行」也不按「已终态」；尾标加 `状态未识别 unrecognized`，轮询继续（未识别不等于结束），但页面上没有任何一句替它编含义。
- 走过的一段弯路值得记：我先写了 `isAgentCancellable` 并在注释里断言「API 会拒这种状态」。读了 `_require_cancellable` 与数过 `_CANCELLABLE_STATUSES` 的调用点之后发现**恰恰相反**——服务端只拒「在终态集合里」的，未知状态它照收。那个 helper 是给一条不存在的规则做见证，已删；`util.ts` 的注释按实测改成「活跃集合镜像的是那份死声明，本门钉的是词表而不是它的行为」。

**新门（`tests/unit/test_agent_console_terminal_vocabulary_parity.py`，8 例）**

五个来源各读各的源码：两个后端 frozenset（AST，两个都要解析到否则拒）、`console_status_label` 的**返回**字面量（只读 `Return`，且剥 `IfExp`——不剥就少读一个词，因为 `pending` 行一次返回两个词）、`util.ts` 的两条 `export const` 数组、`AGENT_STATUS_META` 的键、以及页面里的**比较位置**（`job.status === "TOKEN"`）。断言四个方向：终态集合双向 ==、活跃集合 == 声明、两后端集合互斥且覆盖映射、透传与「不认识」分支同生共死（透传没了就要求删分支，分支没了就红），外加每个映射词恰一个 UI 词、第六份手抄普查、比较词必须出自词表。三条下限（两个 frozenset 都到、`util_sites>=2`、比较站点 `total>=3`）：「扫到 0 条」绝不能绿着过。

一处口径是实测逼出来的收窄：`\bstatus\s*[!=]==` 把 `gate.status === "passed"`、`line.status === "added"`、`step.status === "approved"` 也算成 offender（5 条假红），那是三套本通道不拥有的词表；锚定成 `job\.status` 之后只剩真实站点，正则在注释与断言话术里都写明了为什么只算这一个字段。

**见证：8 臂，全部 MATCHED，控制位改前改后都绿**

预测先写、每臂开头还原 pristine **字节**（工作副本是 CRLF，按行尾翻译锚点；按文本重写会把一行臂变成整文件 diff）：

- `A1` 前端终态集合丢 `FAILED` ⇒ 恰 2 红（下限 + 终态双向）。
- `A2` `components.tsx` 重新声明第六份 ⇒ 恰 1 红（普查）。
- `A3` 把 `return str(job.status)` 折成 `return "CANCELLED"` ⇒ 恰 1 红（透传/分支同生）——这正是 #69 删掉的那个含义，如今有东西守着它回来。
- `A4` 给 `AGENT_STATUS_META` 加一条没有生产者的 `PAUSED` ⇒ 恰 2 红（下限 + 每词有值）。
- `A5` 把一处 `job.status === "EXECUTING"` 改成 `"ARCHIVED"` ⇒ 恰 1 红（比较位置）。
- `A6` 把两处 `agentUnknownNotice(job.status)` 换成裸字符串 ⇒ 恰 1 红（同一条 clause 的另一半：读者消失）。
- `A7` 前端活跃集合丢 `AWAITING_APPROVAL` ⇒ 恰 2 红（下限 + 活跃双向）。
- `A8` 给 `_TERMINAL_CONSOLE_STATUSES` 塞进 `PLANNING`（`api/routes/agent_console.py` 在并发车道的禁改清单里，所以这一臂在 `git archive HEAD` 的**冻结平面** `D:\面试项目\plane172` 上做）⇒ `FF.F....` 恰 3 红（下限 + 终态双向 + 互斥），活跃集合与其余四例照绿；还原后平面 `8 passed`，还原字节与 HEAD blob 在 LF 归一后 sha 相同。

八个案例名各自被至少一臂杀到，没有一条断言是「写了但没人敲过」。

**读数**

- `pytest` 本门 **8 passed / 0 红**；`mypy` Success、`ruff` All checks passed。门文件第一轮 mypy 报 `ast.Return.value` 可能是 `None`，按类型收窄成 `node.value is not None`（语义不变：裸 `return` 本来就贡献零个词），改完**七臂当场全部重跑**，仍 7/7 MATCHED。
- `npx vitest run src/agent` **12 files / 92 passed**：本弧开始时同一集合是 86，+6 = `util.test.ts` 4 + `AgentResult.test.tsx` 1 + `AgentToolStream.test.tsx` 1。新增的三例都是「未知」方向：结果页两个面板同时承认词表外（`findAllByText(/不在本页词表里/)` 恰 2）、不许出现「还在处理中 / 尚未进入终态」、流面板尾标说 `状态未识别` 且不说 `已结束`。
- `npx tsc --noEmit` rc=0（0 行输出）。
- Web 全量 `npx vitest run --reporter=basic`：**47 files / 392 tests：390 passed / 2 failed**，两条红都在 `src/pages/__tests__/SameRepoCraftPanel.test.tsx`（并发车道的 §30.2 repo_path 活）。这次没有靠「看着不像我」下结论，而是在**一个不含我任何文件的平面**上做了归因：`plane172base`（纯 `git archive HEAD`，临时挂一个 node_modules junction 让 vitest 能解析）里该文件 **5 passed**；只把那两个脏文件（`pages/SameRepoCraftPanel.tsx` 与它的测试）覆盖进同一平面 ⇒ **同样的 2 条案例名红**，报错正是 `Found multiple elements with the text: /已完成/`——他们删掉了客户端 `normalizeRepoPath` 过滤、把 mock 返回的每一行都渲染出来，于是两枚「已完成 Completed」药丸撞了 `getByText`。本弧没碰这两个文件，`agentStatusMeta` 的 COMPLETED 文案一字未改（门里那条「每个映射词恰一个 UI 词」钉的就是它）。测量完把平面里的两个文件按 HEAD 还原（逐文件 sha 与 `git show HEAD:` 一致）并拆掉 junction，确认原 `node_modules` 未被链接操作伤到。
- 平面自检：`rootdir: D:\面试项目\plane172`，本门在平面上 8 passed（平面是 `git archive HEAD` + 只叠加本弧 9 个文件，并发车道的脏文件没有参与测量）。
- 合并门读数（两趟都在 `git archive HEAD` 平面族上做，逐名归因由 `.scratch/g172/attr172.py` 计算，不靠心算）：WITH **collected 3402 / 3397 passed / 5 skipped / 0 red / rc=0 / 1470.96s**（`rootdir: D:\面试项目\plane172`），BASE（同一平面、断言本门文件不存在）**collected 3394 / 3389 passed / 5 skipped / 0 red / rc=0 / 1292.15s**（`rootdir: D:\面试项目\plane172base`）。差值 **+8 collected、−0 collected、+0 red**，且这 8 个名字**逐名**是本门的 8 个案例（`test_the_probe_found_a_real_vocabulary_on_every_side` 到 `test_no_page_compares_a_status_the_console_cannot_emit`），非本门的新增 = 0、消失 = 0，红名多重集两侧 identical。平面身份按 §#146 那条教训实测过而不是推理：在两平面各自用同一入口（`cd 平面 && venv python -m …`）打印 `api.agent_runtime` / `craft.loop` / `storage.agent_jobs` 的 `__file__`，三个都落在该平面目录下——venv 的 editable-install `.pth` 没有把「干净平面」偷偷换成带并发脏文件的工作副本。耗时不进口径（§#146 已立此规：冻结平面无共享缓存、机器上还有别的会话），只有 rc 与逐名归因是读数。
- 一个测量隐患就此登记：`tests/unit/test_audit_disposition_labels::test_the_declared_shape_accepts_the_ids_the_platform_writes` 的案例名带真实审计行的 uuid，两趟各 10 例但**成员名字不同**（WITH 有 8 个 BASE 没有、BASE 有 8 个 WITH 没有）。按原始名比对会把它印成「双侧各 8 条意外」，第一版归因脚本正是这样拒了我的 +8。归因脚本因此改成先剥 `[参数化 id]` 折成 family，再按 (family, count) 比对，并且**显式**区分「同 family 同计数的名字旋转」与「计数变化」——后者仍然拒。顺带第二个坑：junit 的 `classname` 是**模块名**，用文件名 `..._parity.py` 去匹配永远匹配不到，「没匹配到」看起来跟「新增不是我」一模一样。
- 中途平面漂移的处理：WITH 构建之后有两个文件又被并发车道改过，于是把这两个文件重新叠加到 plane172、用 `cmp` 证明字节一致，再在该平面重跑读它们的两道门（`rootdir: D:\面试项目\plane172`，12 passed）。归因 claim 只引用干净平面上的数字。

**#173 种子（已量，未修）**

1. `_CANCELLABLE_STATUSES` 是一份**死声明**（HEAD 全仓只有声明自身）：要么把 `_require_cancellable` 改成按它判定，要么删掉它。现在它既不做判定，又被本门当作前端活跃词表的镜像源——这个不对称本门已在话术里明说「钉的是词表，不是那条死集合的行为」，但真正修它需要 `api/routes/agent_console.py` 从并发车道手里空出来。
2. `api/routes/agent_console.py:120 STATUS_LABELS`（六词中文/英文标签，注释自称 "mirrored by the SPA timeline"）是同一份 console 词表的**第三份枚举**，而那句 mirrored 没有任何门守着：`agent/util.ts::AGENT_STATUS_META` 是渲染权威，后端这份唯一的读点是 `:798` 的查询参数校验（不参与渲染），两者谁也不读谁。本门扫的是前端目录，后端这份不在普查范围内；把它接进 `console_mapped_tokens ↔ AGENT_STATUS_META ↔ STATUS_LABELS` 三方对账是下一号最便宜的活。注意别和 `apps/web/src/ui/StatusPill.tsx:19` 的同名 `STATUS_LABELS` 混为一份——那是 verify-job 通道，已由 `test_job_status_channel_parity.py` 看着。
3. `AgentJobDetail.tsx` 的取消按钮仍用「非终态 ⇒ 可点」的口径，与服务端 `_require_cancellable` 一致，但 `:105` 那个 `disabled` 只看集合，没有覆盖「已在取消中」以外的失败回读；这一条要改得先有真实 409 的回读路径，暂时只刻画。

## #173-2 落地：后端自己那份 `STATUS_LABELS` 的「mirrored by the SPA timeline」第一次有了证人

**起点（#172 的 #173 种子第 2 条，原话是"下一号最便宜的活"）。** `api/routes/agent_console.py` 里还有**两份**本通道的枚举，而 #172 那道门两份都不读：它普查的是 `apps/web/src`，读前端的是 `web_status_meta_keys`。于是：

- `STATUS_LABELS`（六词中文/英文标签）的注释自称 *"Human-readable status labels mirrored by the SPA timeline"* —— **一句没有任何门守着的声称**。实测今天它确实是逐字节镜像的（后端 `"已完成 Completed"` == 前端 `AGENT_STATUS_META.COMPLETED.label`），但"今天恰好一致"与"有人保证它一致"是两件事；任一侧单独改词，两个界面就会用不同的名字称呼同一个状态，而所有门照绿。
- `_CONSOLE_TO_STORE_STATUS`（console 词 → 存储状态的过滤映射）是**唯一**把控制台筛选翻译成存储状态的地方：词表里有而这里没有的词会**静默筛不出任何东西**，不是词表的键则会接受一个控制台永远显示不出来的筛选。

**改法（只加门，不动产品代码）。** 在 #172 那道门里补两个助手 + 两条断言，复用它的解析（`console_mapped_tokens()` 是映射权威，`_source`/`_string_literals` 同源）：

- `backend_label_maps()`：AST 读 `STATUS_LABELS` 与 `_CONSOLE_TO_STORE_STATUS`（两份都是 `AnnAssign`，所以 `AnnAssign` 与 `Assign` 都要认；`_dict_pairs` 取键值对——`_string_literals` 对 Dict **只返回键**，这正是它读不出镜像关系的原因）。两个都要解析到，否则拒（"扫到 0 条"不能绿）。
- `web_status_meta_labels()`：新正则 `_META_LABEL_RE` 读 `AGENT_STATUS_META` 的 **key → label**（#172 已有的 `_META_KEY_RE` 只读键，读不出"渲染的是哪个词"）。

**两条门。**
1. `test_the_backends_labels_are_the_ones_the_spa_renders`：`set(STATUS_LABELS) == console_mapped_tokens()`、`set(AGENT_STATUS_META) == console_mapped_tokens()`，**并且逐词** `STATUS_LABELS[t] == AGENT_STATUS_META[t].label`。第三句就是把那句 mirrored 从声称变成事实。
2. `test_the_store_filter_map_covers_exactly_the_console_vocabulary`：`set(_CONSOLE_TO_STORE_STATUS) == console_mapped_tokens()`，双向。

**四臂变异（预测先写后跑；`agent_console.py` 在并发车道的禁改清单里，所以四条臂全部只在冻结平面 `D:/面试项目/plane173` 上做，工作副本一字未碰）。**

| 臂 | 变异 | 预测 | 实测 |
|---|---|---|---|
| M1 | 后端 `STATUS_LABELS["COMPLETED"]` 改成「完成 Completed」 | 门1 红 | **1 red**，正是门1 ✅ |
| M2 | 前端 `AGENT_STATUS_META.COMPLETED.label` 改成「完成 Completed」 | 门1 红 | **1 red**，正是门1 ✅ |
| M3 | 给 `STATUS_LABELS` 塞一个映射从不产出的 `PAUSED` | 门1 红 | **1 red**，正是门1 ✅ |
| M4 | 从 `_CONSOLE_TO_STORE_STATUS` 删掉 `CANCELLED` | 门2 红 | **1 red**，正是门2 ✅ |

**过程中我自己制造过一次假警报，值得记下来。** 第一版臂脚本被 SIGTERM 打断，`finally` 没跑到，平面被留在**已变异**状态；下一次跑出来的 baseline 是红的（报 `labelled-but-unmapped ['PAUSED']`）。我差点把它当成"平面抓到一个真缺陷"——复核 `git show HEAD:api/routes/agent_console.py` 后确认 HEAD 里根本没有 `PAUSED`，是我自己的残留。修法是让每臂**从 `git show HEAD:<rel>` 重建原始字节**再施加变异（而不是依赖上一臂的还原），于是被杀掉的进程再也毒不到下一轮。重建后 baseline 绿、M4 也从"2 red"回到预测的"1 red"。

**门证。** 平面身份实测：`PYTHONPATH` 钉平面根后 `api.agent_runtime.__file__` 与 `craft.loop.__file__` 都落在 `D:/面试项目/plane173` 内（venv 的 editable `.pth` 没有把它偷偷换回工作副本）。平面 baseline **10 passed / rc=0**；主树同文件 **10 passed**（#172 的 8 例 + 本批 2 例）；`ruff` All checks passed、`mypy` Success。臂脚本落在仓库外 `D:/面试项目/_arm173.py`。

**#173 剩余两条（复核后仍挂起）**：① `_CANCELLABLE_STATUSES` 死声明要改 `_require_cancellable` 或删掉，仍需要 `api/routes/agent_console.py` 从并发车道手里空出来——**本批复核：该文件仍有未提交改动（+32/−9），继续不动**；③ `AgentJobDetail.tsx` 的取消按钮失败回读仍只刻画不修。

## #173-1 落地：`_CANCELLABLE_STATUSES` 是一份没人读的声明——删掉它，并把规则真正的那一半钉住

**起点（#172 的 #173 种子第 1 条）。** `api/routes/agent_console.py` 里两份集合并排躺着：

```python
_CANCELLABLE_STATUSES = frozenset({"PLANNING", "AWAITING_APPROVAL", "EXECUTING"})   # 无消费者
_TERMINAL_CONSOLE_STATUSES = frozenset({"COMPLETED", "FAILED", "CANCELLED"})        # 活规则用它

def _require_cancellable(job):           # :685
    if _console_status(job) in _TERMINAL_CONSOLE_STATUSES:   # ← 真正在跑的判定
        raise ApiError(409, ...)
```

`git grep` 实测：`_CANCELLABLE_STATUSES` 在全仓**只有它自己的声明这一处**。#172 的门之所以还读它，只是因为前端的活跃集合"镜像"着它——**一份没有任何消费者的声明，无法被发现与真正在跑的规则不一致**，这正是本批要消掉的东西。

**为什么选"删掉"而不是"改成按它判定"。** 计划给的两条路，实测后只有一条成立。两份集合在词表上互补（六词的划分），所以对**词表内的每个 token** 两种写法给出同一个答案；它们**只在一个地方不同：词表外的状态**。改成 `status not in _CANCELLABLE_STATUSES ⇒ 拒绝` 会把"未知状态可取消"翻成"不可取消"——这是**行为变更**，而且是产品决策（一个状态读不出来的行，要不要留一根取消杠杆？），不该由本批顺手翻掉。于是走另一条：**删掉声明**，让前端的活跃集合改去对**规则本身**（终态集合的补集）负责，这比对着"一份副本"更强——副本可以是错的，规则不会。

**顺带钉住规则真正的那一半。** 删掉声明后，"词表外 ⇒ 可取消"这半边就没有任何东西看着了（声明从来只覆盖三个词表内的 token）。新增
`test_cancel_accepts_a_status_outside_the_vocabulary`（`tests/unit/test_agent_console_api.py`）：造一行 `status="archived"`（旧写入者/人工修库的形状，与既有的 `test_get_agent_job_reports_unknown_status_verbatim` 同一个手法），断言 cancel 返回 **202**。理由写进 docstring：状态读不出来的行正是操作者最需要取消杠杆的那种卡死作业，拒绝等于让人无计可施。**要改成更严的读法，必须先在这里红。**

**门这边的改动（`test_agent_console_terminal_vocabulary_parity.py`）。**
- `backend_sets()` → `backend_terminal_set()`：只读那份活权威；`_CANCELLABLE_STATUSES` 没了就不该再要求解析到两份。
- `test_the_active_set_mirrors_the_declared_cancellable_vocabulary` → **`test_the_active_set_is_the_complement_of_the_live_cancel_rule`**：断言 `前端活跃集合 == console_mapped_tokens() − 终态集合`。对着规则而不是对着副本。
- `test_the_two_backend_sets_are_disjoint_and_cover_the_mapping` → **`test_the_terminal_and_active_sets_partition_the_vocabulary`**：终态 ∩ 活跃 == ∅ 且 终态 ∪ 活跃 == 词表（覆盖语义保留）。
- 新增 `test_the_dead_cancellable_declaration_stays_deleted`：**声明**不许回来。
- `apps/web/src/agent/util.ts` 的注释按实情改口（原文说"活跃集合镜像那份死声明"）。

**过程中我自己踩的一个坑（值得记）。** 那条"不许回来"的 clause 第一版写成 `"_CANCELLABLE_STATUSES" not in 源码`，当场被我自己**刚写的注释**（"There used to be a matching `_CANCELLABLE_STATUSES` here; it was deleted"）判红。这正是 #109/#172 一路记下来的"散文不是代码"：探针必须读**绑定**（AST 的 `Assign`/`AnnAssign` 目标），不能读文本。改成 AST 后通过。

**四条变异臂（预测先写后跑；文件已不在并发车道的禁改清单里，所以在工作副本上做，每臂从**运行前快照**还原——不是从上一臂的还原结果，这正是 #173-2 里让我吃过假警报的那个坑）。**

| 臂 | 变异 | 预测 | 实测 |
|---|---|---|---|
| N1 | 把 `_CANCELLABLE_STATUSES` 声明塞回来 | 恰"不许回来"那条红 | **1 red**，正是它 ✅ |
| N2 | 前端活跃集合删掉一个 token | 补集条 + 划分条 + 探针下限 | **3 red**（`..._is_the_complement_...`、`..._partition_...`、`..._probe_found_a_real_vocabulary...`）✅ |
| N3 | 后端终态集合丢掉 `CANCELLED` | 终态条 + 补集条 + 划分条 + 探针 | **4 red**，四条都在预测里 ✅ |
| N4 | 让判定恒不拒绝（`if False`） | API 套件里的取消生命周期 409 | **1 red**（`test_cancel_agent_job_lifecycle`）✅ |

**门证。** `ruff` All checks passed；`mypy` Success（改动的两个文件）；
`test_agent_console_api.py` + `test_agent_console_terminal_vocabulary_parity.py` + `test_agent_console_status_mirror.py` 共 **55 passed**（基线 49，新增 1 例 + 门由 8 例变 11 例）；
前端 `tsc --noEmit` 0 错、`vitest run src/agent` **12 文件 / 92 通过**。臂脚本落在仓库外 `D:\面试项目\_arm173b.py`。
另记一次环境事故：追加测试时 heredoc 被执行了两遍，同一个测试函数进了文件两次（`ruff` F811 抓住），已去重——**这个坑在本项目里已出现过，追加多行内容后必须数一次函数名出现次数**。

**#173 至此收口**（①②已落地；③ `AgentJobDetail.tsx` 的取消按钮失败回读仍只刻画不修，需要先有真实 409 的回读路径）。

## #174 repo-safety 遍历剪掉 vendored 依赖树——venv 里的 pem 文件不是仓库密钥

**背景。** 开发者主机上 prepare 全被拒、同一仓库在干净 CI checkout 上却通过：检出位置决定了判决。根因是检出目录里可以带着**已安装**的依赖树（`.venv`/`node_modules`/`.m2`），这些树 vendor 出密钥材料形状的第三方文件——certifi 自带的 `cacert.pem` 是公开 CA bundle，任何 virtualenv 都把它放在 `site-packages` 下。密钥普查把它们当仓库密钥，于是主机上每次遍历都红；而且这些目录 git 忽略、根本不会进沙箱 worktree，体积检查也不该量它们。

**修法。** `agent/repo_safety.py`（+67/-2）：`_VENDOR_DIR_EXACT`（venv/virtualenv/node_modules/site-packages/dist-packages/__pycache__/.tox/.nox/.m2/.gradle/.pypoetry/.mypy_cache/.ruff_cache/.pytest_cache 共 14 个无歧义名）+ 前缀 `.venv`/`.virtualenv`（盖住 `.venv312` 这类）；`_iter_repo_walk` 剪枝。**剪枝永不静默**：每次跳过记录目录名，受影响检查把清单写进 detail——"没找到禁文件"不得在"有一棵子树根本没读"时不说。`env/` 有意不剪（Python 项目里它是合理的**源**目录名）。

**门证。** ruff/mypy 清；单测含 vendored 剪枝分支（fake 树 + 披露断言）。

## #175 被吊销的缓存证书永远不再以 VERIFIED 服务——accept 重跑闭包、签发新证

**背景。** `craft/accept.py` 的幂等键命中（同 job_id+head_sha+bundle digest）直接返回已存证书、不重跑——但证书可能在签发后被吊销（#149 的吊销日志）。缓存层绕过了 `evidence/certificate.py` 的强制条款："Verification MUST check the revocation log before trusting a certificate"。结果：吊销只拦住重验路径，拦不住幂等命中路径——VERIFIED 徽章可以来自一张已被吊销的证书。

**修法。** 命中缓存后先算缓存证书的 canonical sha256（同时接受 in-toto 信封 `{"payload":...}` 与裸 `to_dict()` 两种盘上形状），查吊销日志：**不可读 = 视同吊销**（fail-closed，绝不服务）；日志文件不存在 = 无物可吊销，且**询问本身不得创建空日志文件**（`revocation_log.py` 新增无 I/O 的 `default_log_path()`，读路径先 `exists()` 再问）。被吊销/不可读则穿透缓存，闭包重跑、验证仍过就签发**新**证书——被吊销的字节永不返回。

**门证。** `test_craft_accept.py` +105（吊销命中→重跑重签、不可读缓存→fail-closed、无日志不落文件等）；ruff/mypy 清。

## #176 同仓关联键落库——repo_path 持久列 + 服务端过滤，面板读 store 不读内存

**背景。** §30.2 登记的缺口收口：AI 任务面板的"同仓关联"此前是客户端过滤 + 进程内 metadata——重启即失忆，且列表接口不封顶时客户端过滤只看得到第一页。关联键（repo_path）是产品事实，却活在最易失的层。

**修法。** 全链落地（8 文件 +359/-77）：迁移 `0011_agent_jobs.sql` 加 `repo_path` 列；`storage/agent_jobs.py` create 时写**分隔符归一化**的值、list 支持同归一化的服务端 `repo_path` 过滤；`api/routes/agent_console.py` 的 `_job_view`/`_summary_view` 以持久列为权威（journal 与 spec-embedded options 降为 pre-column 旧行的 fallback，且不把旧行谎报为 durable 匹配）；`GET /jobs` 新增 `repo_path` 查询参数并在响应 `filter` 里如实回显；前端 `SameRepoCraftPanel` 改读服务端过滤。顺带把 `util.ts` 的 `AWAITING_APPROVAL` 文案与后端对齐（"等待计划审批"，#173 种子之一）。注：本号与并行车道共享 `agent_console.py`/`agent_jobs.py`/`apps/web`——这是车道自己的号，禁碰清单所指是**别人的**未提交改动，本号提交时一并落库。

**门证。** `test_agent_console_terminal_vocabulary_parity.py` +117（含 service 端过滤与列权威语义）；`SameRepoCraftPanel.test.tsx` 更新；ruff/mypy/tsc/vitest 清。

## #177 ES round trip 获得专属延迟梯度与面板——golden-tag 验证器批量 parent 查询

**背景。** §8.10 "ES 延迟"：`storage/elasticsearch.py` 的 16 个 client 调用点此前零观测——ES 请求落在毫秒到秒带（带 refresh 的 bulk、delete_by_query 可达秒级，ping 亚毫秒），而注册表默认梯度 60s 起步（为分钟级 job 设计），分位数不可测；顶格还必须有限：client 自己 `request_timeout=30`，超时请求若落 +Inf，分位数返回 NaN。

**修法。** 模块级 `_ES_BUCKETS` 12 桶（0.005..30s，顶格对齐 request_timeout）；`_timed_es(op)` 上下文管理器 **finally 语义计时**（失败请求也计数——失败延迟是真实的延迟），名字 `es_request_seconds_<op>`（拼接族，同 worker stage 族形状），16 个调用点全包（op 词表：search/index/bulk/delete_by_query/count/ping/indices）。parity 门 `CONCATENATED_FAMILIES` 加 `es_op`——**词表不手抄**：派生测试从 `self.client.<op>` 调用点提取，新 op 强制门与族一起动；selector 防漂移测试钉 `__name__=~"specproof_es_request_seconds_[a-z_]+_bucket"` 与 0.95/0.50 两个分位数（拼错的选择器 = 静默空面板）。面板 23（per-op p50/p95，x=0,y=79）；OBSERVABILITY §8.10 未接线清单移出 ES 延迟。捎带：`scripts/verify_golden_tags.py` parent 查询批量、`apps/web/src/ui/errorHints.ts` 验收原因细分文案、DRILLS.md 重排。注：代码注释里的 "#169" 指 §8.10 清单条目语境，提交号 #169 已先行被验收原因文案占用——编号双关，如实登记。

**门证。** 定向 pytest **16 passed**（`test_es_store` 4 含 `test_es_requests_are_timed_per_op`——断言五族 bounds 全等 `_ES_BUCKETS` 且 per-op count delta 精确：bulk/search/count/ping 各 1、indices 4（ensure+delete+re-ensure+exists 守卫）；parity 门 4；metrics_http 8）；ruff All checks passed；mypy `storage/elasticsearch.py` Success；面板 JSON 解析 23 panels、panel 23 双 target 均 `__name__=~` 选择器；exposition 端到端实测——真实 `_timed_es("search")` 落 `le="0.005"` 首桶、`observe_duration(..., 30.0)` 落 `le="30"` 有限顶桶、45s 落 +Inf、per-op 族名全部渲染。

## #178 工具执行时长与超时进 /metrics——Executor.run 咽喉点的 per-stem 直方图族与超时计数

**背景。** §8.10 "Tool Timeout"（§9 限制清单"每个工具 Timeout"）：craft 管线每个白名单工具（run_test/run_build/run_lint/run_typecheck 四个 handler 全走 `_run_command` → `Executor.run`）的执行此前零观测——一次 pytest/mvn 跑几分钟，超时死在沙箱里只留下 error 文案，操作者既看不到时长分布也看不到"死因是超时"的计数。沙箱层（sandbox/）按 #168 边界属 sandbox 子代理职责，不在本号动。

**修法。** `craft/executor.py`：模块级 `_TOOL_BUCKETS` 13 桶（0.5..3600s，顶格对齐工具 API 的 timeout 上限 `Param max_value=3600`——超时执行也落有限桶，分位数不落 +Inf）；`_timed_tool(stem)` 上下文管理器 finally 语义计时（失败执行也记墙钟），名字 `tool_run_seconds_<stem>`（拼接族，同 stage/es 族形状；词表 = `ALLOWED_COMMANDS` 白名单 mvn/gradle/npm/pytest/python/cargo，`CRAFT_EXTRA_COMMANDS` 运行时扩展的词干同样进族）；`Executor.run` 里 `run_sandboxed` 全包。超时另计 `tool_timeouts_total`：判据取两类沙箱超时文案的**公共子串** "timed out after"（docker: "sandbox execution timed out after {t}s"、local: "execution timed out after {t}s"）——spawn 错误等其他沙箱失败不冒充超时。parity 门 EMIT_DIRS 增 craft/（对账模块五改六）；`CONCATENATED_FAMILIES` 加 `tool_stem`——词表不手抄：派生测试 **import `ALLOWED_COMMANDS`** 生成期望正则（import 而非 AST 读：常量即权威，门钉的是产品发布词表而非环境扩展）；面板 24（per-stem p50/p95，x=12,y=79，`__name__=~"specproof_tool_run_seconds_[a-z0-9_]+_bucket"` 通配选择器——覆盖 extra 词干）；selector 防漂移测试钉精确选择器与 0.95/0.50 两个分位数；OBSERVABILITY §8.10 未接线清单移出 Tool Timeout。

**门证。** ruff All checks passed（三文件）；mypy `craft/executor.py` Success；定向 pytest **50 passed**（`test_craft_tools` 38 含新增 `test_executor_run_times_each_whitelisted_execution`——真实子进程执行断言 bounds 全等 `_TOOL_BUCKETS` 且 count delta 1；`test_executor_counts_sandbox_timeouts_but_not_spawn_errors`——mock 沙箱两臂：超时文案 → 计数 +1、spawn 错误文案 → 计数 +0；parity 门 5 含新派生与 selector 钉；metrics_http 8）；门证插曲：parity 主门当场红——`tool_timeouts_total` 在面板描述里被引用而 craft/ 不在 EMIT_DIRS，扫描看不到 emission 点，证明门按设计工作；面板 JSON 解析 24 panels、panel 24 双 target 均含精确选择器；exposition 端到端实测——真实 `python -c pass` 走咽喉点落族、mock 超时后 `specproof_tool_timeouts_total 1` 渲染、顶格 3600 有限。

## #179 证书签发与拒绝进 /metrics——evidence 咽喉点的三个计数器

**背景。** §8.10 "Certificate 签发率"：`evidence/certificate.py` 的 `issue_certificate` 在非 VERIFIED 时静默返回 None、`build_rejection_notice` 零观测——签发多少、拒绝多少、拒绝单写了多少，只能翻日志。诚实契约里"证书缺席有意义"，但"从没人请求过"和"全被拒了"在无指标时长得一模一样；签发率（issued / (issued+refused)）无法计算。

**修法。** 咽喉点三个计数器：`certificates_issued_total`（`MergeCertificate` 签发前）、`certificates_refused_total`（非 VERIFIED 拒绝出口，注释明言 refusal is observable——静默拒绝与"没人请求"不可区分）、`rejection_notices_total`（`RejectionNotice` 构造点）。语义边界如实声明：判定词表 VERIFIED/BLOCKED/FAILED 封闭（verdict.py:245、verdict_channels.py:80），refused 即 blocked+failed 之和；notices 与 refused 分开计——调用者可以判定未过而不写拒绝单，两个计数各自诚实，不得互相冒充。parity 门 EMIT_DIRS 增 evidence/（对账模块六改七）；面板 25（三条 15m rate：issued/s、refused/s、notices/s，x=0,y=87，unit ops）；OBSERVABILITY §8.10 未接线清单移出 Certificate 签发率、inventory 增 evidence/certificate.py bullet。§14 无证书阈值故无告警（如实不做）。

**门证。** ruff All checks passed（certificate.py + test_verdict_policy.py + parity 门三文件）；mypy `evidence/certificate.py` Success；定向 pytest **53 passed**（`test_verdict_policy` 41 含新增 `test_certificate_issuance_is_observable`——issued/refused 两臂 delta 各精确 1、`test_rejection_notice_counts_when_written`——notices delta 1；parity 门 4；metrics_http 8）；exposition 端到端实测——真实 `issue_certificate` 两臂（全 PASS → 证书、含 FAIL → None）+ `build_rejection_notice`，`specproof_certificates_issued_total 1`、`specproof_certificates_refused_total 1`、`specproof_rejection_notices_total 1` 全部渲染。门证插曲：实测首跑按 `specproof_` 前缀查 snapshot 计数得 0——注册表存裸名、前缀是 render_text 加的，改裸名后三计数即现；另 test_metrics_http.py 在并行车道脏文件清单中（别人的未提交改动），本次提交不含它。

## #180 Review Court 判定分布进 /metrics——run_review_court 节点边界的 findings_court_* 词族

**背景。** §6 "BLOCKER/MAJOR Precision>=90%"（§8.10 未接线清单 "Finding Precision"）：法庭是应用层唯一按 Finding 判定聚合的点，但零观测——候选进多少、确认多少、多少被归因保护驳回、多少转人工，只能翻 court_audit。真精度需要评测集 ground truth（bench_replay 离线评测），但法庭判定分布是线上可测的 Precision 前置：确认率 = confirmed/candidates 的 rate 比可算，needs_confirmation 的人工回流规模可见。

**修法。** 计数放节点边界、policy 层保持 pure：`agent/review_court/policy.py` 把封闭判定词表提为模块常量（`COURT_OUTCOME_CONFIRMED/NEEDS_CONFIRMATION/SKIPPED` + 既有 `NOT_ATTRIBUTED_STATUS`，汇成 `COURT_OUTCOMES` frozenset，分支里的字面量全部改引常量——值不变，既有断言字面量的测试照旧绿）；`agent/nodes/review_court.py` 的 `run_review_court` 在 policy_recalculate 返回后计 `findings_court_candidates_total`（进入法庭的候选数）+ 每条 audit 的 `findings_court_<final_status>_total`（四词拼接族）。词表不手抄：`FINDINGS_COURT_WORDS = {"candidates", *COURT_OUTCOMES}`，对账门派生测试 import 该 frozenset 生成期望正则——policy 出新判定词强制门与族一起动。面板 26（五条 15m rate，x=12,y=87）；agent/ 本就在对账门 EMIT_DIRS，无需扩目录；无告警（§14 的 90% 是 Precision 阈值，确认率是不同量纲，不冒充）。

**门证。** ruff All checks passed（四文件）；mypy `policy.py` + `review_court.py` Success；定向 pytest **65 passed**（court policy 34 含新增 `test_court_outcomes_are_counted_at_the_node_boundary`——三臂 delta 精确：AMBIGUOUS 同败 → not_attributed、REGRESSION 仅 head 败 → confirmed、解析失败 → needs_confirmation；no_evidence_blocker 19；parity 门 4 含 court 词族派生；metrics_http 8）；exposition 端到端实测——三次真实 run_review_court（confirmed/not_attributed/needs_confirmation）后 candidates 3、confirmed 1、not_attributed 1、needs_confirmation 1 全部渲染。门证插曲：实测脚本首跑把 confirmed 期望写成 2（三臂里只有一臂 confirmed，needs_confirmation 不计入 confirmed）——断言修正即过；注册表存裸名的前缀教训（#179）已直接吸收，计数助手按裸名查 snapshot。

## #181 Base/Head 沙箱失败进 /metrics——JavaMavenAdapter.run 咽喉点的运行/失败/超时三计数

**背景。** §8.10 未接线清单倒数第二项（除 Redis 命中）：Base/Head 沙箱执行零观测——差分差一个"沙箱起不来/超时"的可数信号都没有。执行点勘察：Base/Head 差分与 self-test 的沙箱运行不走 craft Executor（#178 只覆盖 craft 车道），全走 `experiments/adapters.py` 的 ExecutionAdapter → `JavaMavenAdapter.run`——产品树里唯一的 `run_sandboxed` 调用点。sandbox/ 本体无指标注册且 OBSERVABILITY.md 明文"属 sandbox 子代理职责"——所有权边界不动，计数放产品树咽喉。

**修法。** `JavaMavenAdapter.run` 在 run_sandboxed 返回后计数（失败的运行也是运行）：`sandbox_runs_total`（每次到达沙箱）、`sandbox_failures_total`（error 非空 = 沙箱 runner 自己的"无法跑完"契约）、`sandbox_timeouts_total`（判据 = 两类沙箱后端超时文案的公共子串 "timed out after"，与 #178 tool_timeouts_total 同源同判据——spawn 错误计入失败不冒充超时）。parity 门 EMIT_DIRS 增 experiments/（对账模块七改八），顺手修正门 docstring 里过时的"四棵树"口径（清单即 EMIT_DIRS，随接线号增长）。面板 27（三条 15m rate，x=0,y=95）。无告警（§14 无沙箱失败率阈值，如实不做）。

**门证。** ruff All checks passed（adapters.py 经 --fix 修 import 分组空行）；mypy `experiments/adapters.py` Success；定向 pytest **40 passed**（test_adapters 28 含新增 `TestSandboxRunCounters` 三臂——成功 runs+1/failures+0、spawn 失败 failures+1/timeouts+0、超时 failures+1 且 timeouts+1（超时也是失败）；parity 门 4；metrics_http 8）；exposition 端到端实测——真实 `JavaMavenAdapter.prepare`+`run` 三臂（沙箱调用打桩，同单测口径），runs=3 / failures=2 / timeouts=1 全部渲染。门证插曲：①PowerShell 侧 `[regex]::Escape` 计数 marker 假 0 而 Python 侧恒中——read_text 通用换行翻译使 \n marker 恒匹配，patch 计数一律 Python 侧做；②文件里首个 refId "E" 属更早的多 target 面板，面板尾锚点必须 LastIndexOf；③expo 脚本 lambda `**k, _f=v` 语法错（具名参数不能跟在 kwargs 后）改工厂函数，且 experiments 包不在脚本 sys.path 需补 repo 根。

## #182 无证据严重评论拒发进 /metrics——build_review_comments 证据门的可对账拒发计数

**背景。** §6 质量目标"无证据严重评论=0"是清单上唯一标着"由证据门禁保证, 不可观测"的行——门禁真实存在（BLOCKER 六条件 + 锚定策略），但"拒发"这件事零观测：门坏掉（新严重级漏进 severe 集合、渲染缺省变化）不会有任何信号，SLO 无法对账。评论构造咽喉点勘察：产品树唯一出口在 `integrations/inline_comments.py` 的 `build_review_comments`（GitHub review comments 的唯一组装点，纯函数模块——无网络无 env）。

**修法。** 证据门做成可计数：severity ∈ {BLOCKER, MAJOR}（_SEVERE_LEVELS）且 evidence_type ∈ {"", "unknown", "?"}（_NO_EVIDENCE_KINDS——"" 是调用方未填，"unknown"/"?" 是模块自己的渲染缺省）的 finding 在 locate 之前 `incr("severe_comments_without_evidence_total")` + continue 拒发。拒绝即策略（与锚定失败的静默丢弃同一诚实族），SLO 就是这条计数恒 0；首个 critical 告警 SpecproofNoEvidenceSevereComment（>0, for 1m）。parity 门 EMIT_DIRS 增 integrations/（八改九）。面板 28（15m rate，x=12,y=95）。

**门证。** ruff All checks passed；mypy `integrations/inline_comments.py` Success；定向 pytest **16 passed**（test_inline_comments 12 含新增四臂——BLOCKER+unknown 拒发且计数+1、BLOCKER+"" 拒发且计数+1、MINOR+"" 照发计数不动、BLOCKER+真实证据照发计数不动；parity 门 4）；exposition 端到端实测——真实 `build_review_comments` 拒发臂 comments==[] 且 `specproof_severe_comments_without_evidence_total` 渲染（# TYPE counter 行）；alerts-slo.yml 解析 14 rules 含新告警；dashboard 28 panels、面板 28 target 接线。

**门证插曲。** ①Part B 的 dashboard 替换串吞掉 panel 27 target C 的闭合 `}`（锚点只到 refId 行没含对象闭合）→ JSONDecodeError line 2530；Python probe 定位后补 `        }` 修复——教训：跨对象替换串必须含前一个对象的完整闭合括号。②expo 探针首跑把面板 27 当成自己的——27 是 #181 沙箱面板，#182 是 28；断言面板属性前先核对身份。③Edit 工具故障延续（old_string 注入 ": " 前缀），全部改动走 .scratch patch 脚本（fix182/gate182b/expo182，用完即删）。

## #183 Capsule Replay 产品化进 /metrics——replay --run 经沙箱执行与 verdict 词族

**背景。** §6 "Capsule Replay>=95%" 是清单上最后一行 ❌（除 PR 归因）：`cli/specproof/commands/replay.py` 只解压 capsule + 写 report(status="extracted") + 提示用户手动 `bash run.sh`——自动化执行只存在于评测工具 scripts/bench_replay.py，产品命令从不执行 run.sh，成功率无从谈起。执行面契约：capsule 内容（生成的测试、run.sh）与目标 repo 代码都不可信——host 上唯一允许的执行物是 git 二进制（clone），run.sh 一律进沙箱。

**修法。** 三件套：①`sandbox/runner.py` 增 `REPLAY_PROFILE`（profile 是数据不是 argv——新执行面走 profile 不复制安全关键 argv；默认 maven 镜像，镜像无 git 时沙箱内诚实失败，操作员用 SPECPROOF_REPLAY_IMAGE 钉 git-capable 变体；host 先 clone 到 <workspace>/repo，可写 sub-mount bind 的是真 clone，run.sh 在里面 checkout base/head；不加 cache_dir/cache_manifest，未验证的依赖缓存绝不装作已验证）；②新模块 `evidence/capsule_replay.py`：host 侧 git clone → `run_sandboxed(["bash","run.sh","repo"], mode="docker", profile=REPLAY_PROFILE)`——mode="docker" 钉死（无 Docker 是诚实报错，绝不本地回退跑不可信代码，与 adapters 的 Node/Python 车道同一纪律）；计数族 capsule_replay_runs_total（到达沙箱即计，失败也是运行）/ exec_errors_total（runner 的 error 非空契约）/ timeouts_total（"timed out after" 公共子串，与 #178/#181 同源）/ verdict_<word>_total 四词族——词表 = create_capsule 模板的 REGRESSION CONFIRMED / UNEXPECTED FIX / AMBIGUOUS / COMPLIANT（run.sh 的 verdict 只在 stdout、exit code 恒 0），stdout 首个命中、仅沙箱跑完且 exit 0 才解析、解析不出不计族（诚实缺席）；clone 失败从未到沙箱不计 runs；③`replay.py` 加 `--run <repo>` 显式 opt-in + `--timeout`（默认 900s），report 并入执行结果、status 如实（replayed/clone_failed），无 --run 时行为与报告逐字节不变。parity 门 CONCATENATED_FAMILIES 增 replay_verdict（派生测试 import VERDICTS 钉词表）+ 模板防漂移测试（四 marker 必须出现在 _build_sh_script 产物里）。面板 29（三条 rate，x=0,y=103）+ 告警 SpecproofCapsuleReplayRateLow（成功率 <95% for 15m，warning——质量目标非可用性，无请求时无序列不触发）。

**门证。** ruff All checks passed（runner/replay/capsule_replay/parity/test 五文件）；mypy `evidence/capsule_replay.py` Success；定向 pytest **37 passed**（test_capsule_replay 10——成功臂 runs+1/verdict 族+1/exec_errors+0 且断言 argv/mode="docker"/profile.name="replay"、COMPLIANT 词臂、超时臂三计数+1 而 verdict 不计、spawn 臂 exec_errors+1/timeouts+0、解析不出不计族、非零 exit 不计族、clone 失败 runs+0、模板防漂移、CLI --run 接线、CLI 无 --run 回归锁；parity 门 4 含 replay_verdict 派生；test_object_metadata 23 回归）；exposition 端到端实测——真实 `run_capsule_replay` 三臂（沙箱打桩，同单测口径）runs=3 / exec_errors=2 / timeouts=1 / verdict_regression_confirmed=1 全部渲染（含 # TYPE counter 行），verdict 解析器四词全过、无 marker 返回 None；alerts-slo.yml 解析 15 rules；dashboard 29 panels、面板 29 三 target。

**门证插曲。** ①派生测试词序——family 正则按模板声明序写，派生测试按 sorted 比对，主门当场红 = 按设计工作，正则改字母序即绿；②expo 探针首跑把 `# TYPE specproof_capsule_replay_verdict_regression_confirmed counter` 当期望——render_text 的 # TYPE 行带全名（含 _total），修断言非产品；③全部改动仍走 .scratch patch 脚本（p183/p183fix/expo183，用完即删）。

## #184 PR 归因判定分布进 /metrics——court 边界的归因比较计数与信号词族

**背景。** §6 "PR 归因准确率>=90%"（§8.10 未接线清单最后一项）：归因判定真实存在——policy 层 `_preexisting_check` 对双侧同败的比较（ADR-004 BLOCKER 六条件之 3；att-08 场景：Base 同样失败时，只有 Head 行为差异才保留归因，否则既有缺陷拒归因保护），但零观测——比较了多少次、多少保留、多少被拒、靠什么信号保留，court_audit 里有数据无聚合。真准确率需评测集 ground truth（同 #180 的 Precision 边界），但归因判定分布是线上可测的前置。

**修法。** 计数放节点边界、policy 保持 pure：①`policy.py` 把 `_head_only_behavior_difference` 的四个信号字面量提为模块常量并汇成 `HEAD_ONLY_SIGNALS` frozenset（值不变 byte-compat——audit entry 里的信号字符串逐字节不动）；②`run_review_court` 在既有 #180 计数循环里追加：audit entry 携带 preexisting_check.applicable 即归因比较发生——`findings_attribution_compared_total` / `kept_total`（head_only_difference=True 保留归因）/ `rejected_total`（False 拒归因）+ `findings_attribution_signal_<word>_total` 四词族（kept 的 WHY）。词表不手抄：parity 门 CONCATENATED_FAMILIES 增 attribution_signal，派生测试 import HEAD_ONLY_SIGNALS 生成期望正则。面板 30（三条 rate：kept/rejected/compared，x=12,y=103）；无告警（kept/compared 是分布不是准确率，§14 的 90% 是 ground truth 阈值，不冒充——同 #180 纪律）。

**门证。** ruff All checks passed（policy/nodes/parity/test 四文件）；mypy `policy.py` + `review_court.py` Success；定向 pytest **49 passed**（test_review_court_policy 35 含新增 `test_attribution_decisions_are_counted_at_the_node_boundary` 三臂——同败同签名 rejected+1/kept+0/信号+0、exit codes 差异 kept+1 且 exit_code_differs 信号恰 1 个、base 过则不计；parity 门 5 含 attribution_signal 派生；test_capsule_replay 10 回归）；exposition 端到端实测——真实 `run_review_court` 三臂 compared=2 / kept=1 / rejected=1 / signal_exit_code_differs=1 全部渲染（含 # TYPE counter 行）；dashboard 30 panels、面板 30 三 target（alerts-slo.yml 本号未动，仍 15 rules）。

**门证插曲。** ①#183 的教训复发成例：family 正则按信号声明序写、派生测试按 sorted 比对，主门当场红（head_db_state_differs < head_extra_failure_count 字母序）——修正则非产品；②patch 锚点笔误把 #183 插入文本的行首 "vocabulary" 误记为 "the vocabulary"（"the" 实属上一行行尾跨行字符串），count 0 断言当场拦住——probe repr 定位后修正则；③全部改动走 .scratch patch 脚本（p184/p184fix/p184fix2/expo184，用完即删）。

## #185 差分验证执行进 /metrics——run_differential 节点边界的 runs/skipped/errors/outcomes 词族

**背景。** Phase 2「多语言验证能力」的核心节点 run_differential（1598 行）此前零观测——跑了多少次差分、多少被跳过（workspace 未备好/无生成测试/注入失败）、多少执行出错、各 verdict 分布如何，全不可见。真差分覆盖率需结合下游证据（§2.1 的 Node/Python 生成器缺口），但执行面计数是线上可测的前置。

**修法（#185b 订正后）。** 计数放节点边界、内部 helper 保持 pure：①`agent/nodes/run_differential.py` 顶部只导入 `from observability.metrics import incr`（原文记录里的 observe_duration/_DIFF_BUCKETS 从未被落地使用——`_DIFF_BUCKETS` 是死常量，#185b 已删）；②定义 `DIFF_OUTCOMES = frozenset({"regression", "compliant", "ambiguous", "unexpected_fix", "skipped"})`；③三条未执行路径（workspace 未备好 / 无生成测试 / 注入失败）各 `incr("differential_runs_total")` + `incr("differential_outcomes_skipped_total")`；④主执行点 `incr("differential_runs_total")`；⑤执行出错（Base/Head 结果 error 非空）`incr("differential_errors_total")`（#185b 起独立计数——outcomes_ambiguous 保持词表声明的 base_fail+head_fail 义，不吸收基础设施错误）；⑥返回前遍历 primary_entries，按 verdict 词表递增对应 `differential_outcomes_<word>_total`。词表不手抄：parity 门 CONCATENATED_FAMILIES 增 diff_outcome，派生测试 import DIFF_OUTCOMES 生成期望正则。面板 31（七条 rate：runs/skipped/errors + regression/compliant/ambiguous/unexpected_fix，x=0,y=111）；无告警（outcomes 是分布不是准确率，§2 的多语言能力成熟度阈值不冒充——同 #180/#184 纪律）。

**门证（#185b 订正后重跑，2026-10-07）。** ruff All checks passed（nodes/parity/test 三文件）；mypy `agent/nodes/run_differential.py` Success；定向 pytest **14 passed**＝parity 门 4＋本文件 10（六例臂：全路径 runs+1 且 seam 调用序 maven_base→maven_head→maven_probe、workspace 未备好 runs+1/skipped+1、无生成测试与注入失败各 runs+1/skipped+1 且 seam 0 调用、执行出错 errors+1 且 ambiguous 恰 0、四 outcome 参数化各 +1；词汇漂移门 1 例断言 parity regex words == DIFF_OUTCOMES declaration）；dashboard 31 panels、面板 31 七 target（B 改 outcomes_skipped、C 的 errors 修复后真实存在；alerts-slo.yml 本号未动，仍 15 rules）。

**账实订正（#185b，2026-10-07）。** 本号原记录的"门证"与其落地字节多处不符（#186/#187 之前的账实错位，a87129e 平面实测）：①代码——skip 三条路径实际发出 `differential_runs_total` + `differential_outcomes_skipped_total`（记录里的 `differential_skipped_total` 从未被发出）；execution error 计进 `differential_outcomes_ambiguous_total`（无独立 errors 计数器，记录里的 ⑤ 与落地不符）；`observe_duration` 从未导入（只导 `incr`）；`_DIFF_BUCKETS` 是死常量。②仪表盘——target B/C 引用 `specproof_differential_skipped_total` / `specproof_differential_errors_total` 两个全库无发射点的名字，a87129e 平面上 parity 门实测 1 红 3 绿、点名恰 `['differential_errors_total', 'differential_skipped_total']`。③测试——a87129e 测试文件 import 不存在的 `run_differential`（真实名 `run_differential_node`）并只断言两个非落地计数名，平面上实测 5 红 1 绿——原记录"定向 pytest 6 passed"在该平面不成立；`git diff a87129e HEAD -- run_differential.py 与测试文件` 为空（#186/#187 未触碰这两文件，错位一直存续到 #185b 动手前）。#185b 三面校正到设计：删死常量、execution error 独立计 `differential_errors_total`（仪表盘 C 从此真实）、B 改指 `differential_outcomes_skipped_total`、测试整篇重写为 10 例（真实 seam `run_with_cancel_checks(job_id, stage, fn)`，断言调用序 maven_base→maven_head→maven_probe；执行出错 errors+1 且 ambiguous 恰 0）。两臂变异先写预测、逐一还原后复绿（14 passed）：臂 A（errors 回退成 ambiguous）实测 **2 红**——预测 1 红、多出的 1 红是 parity 门点名 `['differential_errors_total']`（同一改动在仪表盘 C 引用处被第二见证，预测错因如实记录）；臂 B（B 回退成 `skipped_total`）实测 1 红＝parity 点名 `['differential_skipped_total']`，与预测一致。词汇顺序遗产（原插曲②）保留在重写的漂移门（提取 alternation group 后 set 比对）；原插曲①的 UP037 注记随旧测试文件重写而消亡。**归属说明**：本节 背景/修法/门证 三段与 OBSERVABILITY.md 的 run_differential 条目在 #185b 码面落地前被并发会话 4cbce1d（#188）的整文件暂存顺带提交（共享工作树无隔离）——码面/测试/仪表盘与本段订正由 #185b 提交补足，归属如实记录。

### #173 控制台词表五份手抄的对账门（已落地）

**量到的事实（HEAD `bfc63af`，全部来自源码）**

- `_TERMINAL_CONSOLE_STATUSES` / `_CANCELLABLE_STATUSES`（`api/routes/agent_console.py:110-111`）、`STATUS_LABELS`（`:120`）、`_CONSOLE_TO_STORE_STATUS`（`:145`）、`console_status_label`（`api/agent_runtime.py:106`）、`AGENT_STATUS_META`（`apps/web/src/agent/util.ts:1`）——同一份 console 词表的五处枚举。
- `GET /agent/jobs?status=` 的过滤走 `status not in STATUS_LABELS` 然后 `_CONSOLE_TO_STORE_STATUS[status]` ——直接下标进另一个字典；两个 key 集合一致是唯一的防线。
- 翻译函数的返回类型标注 `cast("Literal['pending', …]", …)` 是第六份手抄，藏在函数体内。
- 中文标签已漂移：API 说「等待计划审批 Awaiting approval」，前端说「等待审批」。

**改法**

- 一处导出（`apps/web/src/agent/util.ts`）：`AGENT_ACTIVE_STATUSES` / `AGENT_TERMINAL_STATUSES` / `agentRunPhase()` / `isAgentTerminal()` / `agentUnknownNotice()`。
- 四个站点全部改成调用导出（`components.tsx` 删掉自己那份 `new Set`）。
- 真正改行为的只有第三支：`AgentResult` 的两个面板与 `AgentToolStream` 的尾标对 `unknown` 明确说「这一轮上报的状态不在本页词表里」，既不按「仍在执行」也不按「已终态」。
- 新门（`tests/unit/test_agent_console_status_mirror.py`，6 例）：五个来源各读各的源码，断言四个方向：终态集合双向 ==、活跃集合 == 声明、两后端集合互斥且覆盖映射、透传与「不认识」分支同生共死。

**见证：6 臂，全部 MATCHED，控制位改前改后都绿**

- `A1` 前端终态集合丢 `FAILED` ⇒ 恰 2 红（下限 + 终态双向）。
- `A2` `components.tsx` 重新声明第六份 ⇒ 恰 1 红（普查）。
- `A3` 把 `return str(job.status)` 折成 `return "CANCELLED"` ⇒ 恰 1 红（透传/分支同生）。
- `A4` 给 `AGENT_STATUS_META` 加一条没有生产者的 `PAUSED` ⇒ 恰 2 红（下限 + 每词有值）。
- `A5` 把一处 `job.status === "EXECUTING"` 改成 `"ARCHIVED"` ⇒ 恰 1 红（比较位置）。
- `A6` 把两处 `agentUnknownNotice(job.status)` 换成裸字符串 ⇒ 恰 1 红（读者消失）。
- `A7` 前端活跃集合丢 `AWAITING_APPROVAL` ⇒ 恰 2 红（下限 + 活跃双向）。
- `A8` 给 `_TERMINAL_CONSOLE_STATUSES` 塞进 `PLANNING` ⇒ 恰 3 红（下限 + 终态双向 + 互斥）。
- `A9` 修正预测：`test_the_api_and_the_console_gloss_each_status_with_the_same_words` 不仅钉词汇，还钉 key 集合的双向差集 ⇒ 预测从 2 红改为 3 红，重跑全表 9/9 MATCHED。

**读数**

- `pytest` 本门 **6 passed / 0 红**；`mypy` Success、`ruff` All checks passed。
- `npx vitest run src/agent` **12 files / 92 passed**。
- `npx tsc --noEmit` rc=0（0 行输出）。
- 两平面全量：WITH plane173 **3403 passed / 5 skipped / 0 red** in 1003.25s；BASE plane173base **3397 passed / 5 skipped / 0 red** in 969.74s；+6 collected 逐名归属，全部是本门，0 red 家族相同。
- 平面自检：`rootdir: D:\面试项目\plane173`，本门在平面上 6 passed。

### #174 SSE 事件帧与事件种类词表（replay_gap 不再变成幽灵行，已落地）

**量到的事实（HEAD `7145990`，全部来自源码）**

- 后端在补发缺口时发 `event: replay_gap` + `data: {"requested_after":N,"first_available":M}`（无 seq/type 字段）；前端 `openAgentEventStream` 把 `_type` 丢掉，`onEvent(data as AgentEvent)` 盲转成事件行。
- 唯一消费者 `components.tsx` 直接 `setEvents(prev=>[...prev,ev])` ⇒ 读者看到的是一条幽灵行（`ev.type` undefined ⇒ `eventKindLabel(undefined)`、key 用 `ev.seq` undefined），而「日志中间缺了 N 条」这句话永远读不到。
- 全仓只有 `tests/unit/test_agent_console_persistence.py:95` 断言字符串 `"event: replay_gap"` 出现在生成器输出里——没有任何读者。
- 词表普查：emitter 的 API 名不止 `record_event`——工具事件走 `self._emit("tool_call", {...})`，arg 0 才是类型；把 callee 集合设成 {record_event(1), _emit(0), emit_event(1), publish(0)} 后 produced=7 = `EVENT_TYPES` 声明 7 = 前端 `eventKindLabel` 内联 labels 7。

**改法**

- 一处导出（`apps/web/src/agent/util.ts`）：把 `eventKindLabel` 的函数内 `labels` 提成模块级导出常量 `EVENT_KIND_LABELS`（现在每次调用重建且结构门读不到）。
- `apps/web/src/api.ts`：`openAgentEventStream` 新增 `onGap?: (gap: AgentReplayGap) => void` 参数，对 `type === "replay_gap"` 的帧分流到该回调而非事件列表。
- `apps/web/src/agent/components.tsx`：`useAgentJob` 追踪 `replayGap` 状态并在 SSE 处理器里传入 gap 回调。
- `apps/web/src/agent/pages/AgentToolStream.tsx`：渲染缺口披露（「日志缺口 replay_gap：请求 seq>N，首个可用 seq=M，中间缺了 X 条」）。
- 新门（`tests/unit/test_agent_event_kind_vocabulary_parity.py`，4 例）：produced ⊆ UI 词表、UI 词表 ⊆ produced、`EVENT_TYPES` 声明与 produced 相等、消费者必须有形状分流。

**见证：4 臂，全部 MATCHED**

- 所有 7 个后端产生的事件种类都有对应的 UI 标签（无原始 token 泄漏）。
- 所有 UI 标签都有生产者（无死词汇）。
- `EVENT_TYPES` 声明等于实际产生集合（收敛围栏）。
- `replay_gap` 帧被形状区分（api.ts 分流到 onGap，components.tsx 追踪 replayGap 状态）。

**读数**

- `pytest` 本门 **4 passed / 0 红**。
- `npx vitest run src/agent` **12 files / 92 passed**。
- `npx tsc --noEmit` rc=0（0 行输出）。


### #188 eval 评测集 ground truth 严重度对账——「BLOCKER/MAJOR Precision」的 🟡 收口（已落地）

**量到的事实（HEAD `bafd22f`，全部来自源码与数据）**

- §6 SLO 表两行 🟡 的堵点都写着「真(准)精度需评测集 ground truth」：BLOCKER/MAJOR
  Precision 行（#180 线上判定聚合可算确认率，但判级对错没有 ground truth 对账）与
  PR 归因准确率行（#184 分布可算，真准确率需 ground truth）。
- ground truth 评测基建早已存在且在跑：golden-cases/ 100 case 每个带 ground-truth.json
  （expected_severity 全量覆盖：BLOCKER 16 / MAJOR 47 / NONE 37；should_detect
  63 True / 37 False；probe_expectation 仅 3 个执行探针），`specproof eval --cases`
  走完整管线按 contract-id 匹配，CI eval-golden-cases job 跑 4-case 代表子集 grep 门。
- 但 eval 的对账只算 case 级 recall/precision（evidence/acceptance.py score）：
  判级对错在 results 记录里带了 expected_severity 与 matched_severities 两个字段，
  却从不比较——判级漂移（MAJOR 判成 MINOR）在所有输出面（CLI/HTML/sidecar）不可见。
- 归因准确率在现评测集上不可测：100 case 全是 head 引入缺陷（scenario.json 的
  base→head 构造 diff），没有 base-已含缺陷探针，ground truth 无 preexisting 声明
  ——诚实边界升级记录（OBSERVABILITY 两处），而非硬造指标。

**改法**

- `evidence/acceptance.py` 两个纯函数（单一诚实源，零 I/O 离线可测）：
  - `severity_match_of(record)` 三态——True: matched 正例判级与 expected 完全一致
    （单值）；False: 判级漂移/多值；None: 无判级可评（recall MISS 是召回失败不进
    判级分母；负例错误已由 false_positives 计）。
  - `severity_reconciliation(results)` 两个口径——`severity_agreement` = matched
    正例判级一致率；`severe_precision` = severe call 认可率：分母 = expected
    BLOCKER/MAJOR 的 matched 正例（无论报什么级别，MAJOR 漂成 MINOR 仍是错的
    severe call）+ FALSE_POSITIVE 负例（与 case 级 precision 的 FP 同源：clean PR
    上任何 confirmed finding 都是错判），分子 = 其中判级一致的；expected 低级别的
    matched 正例不进分母（没做 severe call）；分母 0 → None，永不假 100。
- `cli/specproof/commands/eval.py`：results 每 case 附 `severity_match` 三值字段；
  汇总区新两行 `Severity agreement:` / `Severe precision:` + drift 明细行；
  sidecar JSON 新增 `severity_reconciliation` 块（机器可读，baseline/CI 可消费）。
- `evidence/report.py` render_eval_report：汇总卡新两张（Severity Agreement /
  Severe Precision，同款 fmt_metric——None 渲染「样本不足」不假 100）；
  表格 Severities 列漂移 case 红标。
- OBSERVABILITY.md：§6 行 🟡→✅（对账落地，90% 阈值仍未 pin——acceptance.default()
  同款先例，由维护者从全量跑数 pin）；正文前置说明同步；归因两处补勘察边界。

**读数**

- 新门 tests/unit/test_acceptance_gate.py 6 例：一致率份额、三态判定与漂移、
  无判级时双 None、severe 分母盖漂移+FP 且低级别正例不入分母、完美跑恰 100、
  多值判级=漂移不崩。全套 18 passed；ruff/mypy 三文件全绿。
- 实测（两轮 eval，no-llm 确定性，本机 local mode——SPECPROOF_ALLOWED_ROOT
  未配置走 local_fallback）：
  - 轮一 tuning 池 2 case（holdout 隔离按 #77 生效，case-01/56 被排除）：
    case-17 MISS（325s）、case-10 负例无 FP；轮二 --include-holdout 单跑
    case-01 MISS（356s）。三 case 全 MISS → Recall 0.0%，对账指标诚实渲染
    「无法评估 (n=0)」（agreement 分母=0 matched 正例；severe 分母=0 severe
    call）——空样本不假 100 的机制恰好被真数据证明。CLI 两新行、sidecar
    `severity_reconciliation` 块、HTML 双卡+红标三输出面全部落盘验证。
  - 观测到 specproof-nightly-eval 连续 4 天 1 分钟级 failure（10-03..10-06，
    runner 初始化后即挂，log 显示 UNKNOWN STEP）——评测 job 配置层问题，
    ci.yml 属并行车道禁碰文件，根因排查留给该车道；本机全 MISS 与之呼应
    （管线召回 or 环境差异）留下一号候选：对照 CI eval-golden-cases job
    的最近绿跑复核 case-17/01 的 matched 语义。
- 提交本号的码面（acceptance/eval/report 三文件 + 测试）与对账机制门证均
  不改变 findings 产出——纯聚合， MISS 现象非本号引入。


### #186 intake 节点执行面计数（已落地 306687d；#186b 补行为证人）

**落地面（306687d）。** `agent/nodes/intake.py` 四个计数：intake_runs_total（每次执行）、intake_repo_missing_total / intake_spec_missing_total（两个检查各自的失败）、intake_spec_read_total（成功读取）；同名 parity 家族（intake_validation）、仪表盘面板、OBSERVABILITY 条目随行落地。**落地时没有任何行为测试**——当时的"门证"只有 parity 门的名字对账（+10 行），与 #185 同型（见上文 #185b 账实订正）。

**#186b 补行为见证（2026-10-07 提交）。** 新测试 `tests/unit/test_intake_execution_is_observable.py` 5 例直接驱动真节点（intake 只读文件系统，无需任何 stub；计数器用 delta 断言，注册表是进程全局）：①成功——runs+1、spec_read+1、requirement_text 与 errors 全断言；②缺仓库——runs+1、repo_missing+1、**spec_read 也 +1**；③缺需求——spec_missing+1、spec_read 恰 0、文本空串；④双缺——两个失败计数同一次运行同记、errors 恰 2 条；⑤上游 errors 存活（节点是追加不是替换）。实测 **5 passed**。

**订正（行为测试证伪的散文，全部副本已改）。** 落地散文称"repo missing / spec missing / success 是互斥的（mutually exclusive）失败模式"——②与④实测否证：仓库与需求两个检查彼此独立（缺仓库不短路需求读取，一次运行可同时记 repo_missing 与 spec_read；两个失败计数亦可同记）。真实史实：任一记录错误都会让作业在 preflight 守卫（`agent/graph.py:_abort_on_preflight` 读累积 errors）处中止——"解释为何作业从未到达后续节点"半边成立，故保留。订正副本（单行 regex 曾漏掉换行的 intake.py 版本，逐处人工核对）：`intake.py` docstring＋两处行内注释、parity 家族描述、OBSERVABILITY.md 条目、仪表盘面板 description。

### #187 publish_report 节点执行面计数（已落地 bafd22f；#187b 补行为证人）

**落地面（bafd22f）。** `agent/nodes/publish_report.py` 两个计数：runs（每次尝试，在渲染前）、success（HTML + lineage 两个产物都写盘后）；parity 家族、仪表盘面板、OBSERVABILITY 条目随行落地。**落地时没有任何行为测试**（parity 门 +8 行）。

**#187b 补行为见证（2026-10-07 提交）。** 新测试 `tests/unit/test_publish_report_execution_is_observable.py` 2 例驱动真节点——渲染器、lineage 构建、两次写盘全真跑；只 stub 元数据 sink（真 sink 连共享对象库）：①成功——runs+1、success+1、两产物都在盘上、lineage 文件名是 8 位 job slug（`job-185b-lineage.json`）而非时间戳、sink 恰见一对 replay_report 且 job_id 正确；②lineage 构建抛错——runs+1、success 不变、**HTML 已落地**（glob 非空）、无 lineage 文件、sink 0 调用。实测 **2 passed**。

**订正（行为测试证伪的散文，全部副本已改）。** 落地散文称"lineage/replay 构建失败或元数据管道故障会在 **HTML 落地前**丢弃作业"——②实测两点否证：①HTML 写盘发生在 lineage 构建**之前**，lineage 失败时 HTML 已落地（不是"落地前丢弃"）；②元数据管道丢不了作业：`record_file_object_best_effort` 内部吞掉一切异常（object_metadata.py 文档即 "never raising"，288-306 行），且调用点在两个计数之后。订正副本：parity 家族描述、OBSERVABILITY.md 条目、仪表盘面板 description。

**门证（#186b/#187b 合计，HEAD 5b84116）。** 定向 pytest **11 passed**＝intake 5＋publish 2＋parity 4（55.88s）；ruff 四 py 文件 All checks passed；仪表盘 JSON 仍可解析（33 panels）且 parity 门全绿（名字未动，仅 description 散文订正）。


### #189 #171 遗留四红重测——全部复绿，零码面收口（已落地）

**背景**

#171 弧（HEAD `0932ebe`）的合并门读数记了 4 条「不归本弧」的红：
`tests/integration/test_differential.py:129`（`'NoneType' object has no attribute
'lower'`）、`tests/integration/test_phase_acceptance.py:109`（`argument of type
'NoneType' is not iterable`）、同文件 `:226`（`AssertionError: Matrix has no
rows`）、`tests/unit/test_metrics_http.py:108`（histogram ladder 断言）。当时的
成因线索：并发会话未提交的 `api/routes/agent_console.py`(+41) 与
`craft/accept.py`(+51) 把 witness 指向的行挪走——是测量平面的污染而非持久缺陷。
本号对这 4 条做重测定性并归档，不留悬账。

**修法（无码面改动——量先于动，量完即收）**

- `tests/integration/test_differential.py::TestStaticAnalysisDetection`
  （即 :129 所在类，3 例）：**3 passed / 2.97s**。
- `tests/unit/test_metrics_http.py`（:108 histogram ladder 所在文件，8 例）：
  **8 passed / 6.95s**——该文件随后被并行车道接线批次（#166-#188 间）正经
  修改过，红早已消。
- `tests/integration/test_phase_acceptance.py::TestPhaseAcceptance::
  test_eval_generates_html_report`（:109）与 `::test_full_pipeline_produces_
  all_artifacts`（:226）：**2 passed / 717.92s（11m57s）**——两个都是真管线
  慢测（4-case eval 子集 + 全管线 artifacts），本号后台实测跑通。
- 成因判定：#171 测量时工作树有并发车道脏文件（witness 行号被挪）+ 沙箱/
  环境瞬时态；此后码面经 #180-#188 正经演进，四红全部不复现。与 #188 实测
  观测互洽：eval 4-case 在本机 no-llm 下 findings 全 MISS 但 exit 0，
  test_eval_generates_html_report 的断言面（returncode/HTML 存在/含 SpecProof）
  本就不含 Recall——两轮测量说的是同一件事的不同侧面。findings 召回层
  （MISS vs CI 绿）的根因排查另行立号，不入本账。

**读数**

- 四红全绿（3+8+2 例，合计 ~12 分钟），零文件改动之外的账：本号只追加本节。
- 下一号候选：#190 评测集 preexisting 缺陷探针构造（base tag 带既有缺陷 +
  head 再引入，ground truth 双声明，eval 侧对账消费 review court 的
  preexisting_check——收 §6 最后一行 🟡「PR 归因准确率」的评测基建）；
  或 findings 召回层 MISS 根因排查（本机 no-llm 3/3 MISS vs CI Recall 门）。
