# SpecProof 长期执行开发路线图

> 目标：把 SpecProof 从"能演示的框架"打磨成"团队每天都愿意用的验收产品"。
> 本文档基于对当前代码库的实测诊断，给出分阶段、可验证、可执行的开发计划。
> 维护方式：每个阶段有明确的验收标准（Definition of Done）。完成即勾选，未完成不进入下一阶段的主线。

---

## 0. 现状诊断（实测证据）

本节结论来自实际运行，不是主观印象。

| 检查项 | 命令 | 结果 |
|---|---|---|
| 前端类型检查 | `tsc --noEmit` | ✅ 通过 |
| 前端单测 | `vitest run` | ✅ **39 文件 / 250 用例全绿**（本路线图持续扩充：错误可诊断化、Craft 去术语、demo 标签对齐、去脆弱化文案、开发→验收衔接、预检卡 + 8 处产品表格迁到设计系统 Table + 实时通道统一 + 降级原因中文化 + 术语内联化 + 需求覆盖矩阵"改前/改后"列与**执行面披露**等） |
| 后端测试规模 | `pytest tests/` | 收集 2754 用例，整套 >6 分钟，依赖 Docker/MySQL 的部分会挂起。**快速内循环**（见 §6.6）：`pytest tests/unit -m "not integration and not slow"` ≈ 3 分钟 |
| 差分集成测试（全新克隆） | `pytest tests/integration/test_differential.py` | ❌ 曾 5 失败（`base`/`head-v1` git 标签不存在即报错）→ ✅ 本路线图 Phase 1.1 已修复为清晰跳过 |

代码库规模：Python ≈11.3 万行、前端 React/TS 约 130 个源文件，含完整的 UI kit、主题、多租户、命令面板、引导页。**工程质量不低**，但"不好用、不友好"的根源不在代码整洁度，而在下面几类产品级问题。

### 核心痛点（按对用户"上手→用起来"的阻塞程度排序）

1. **上手成本高（阻塞第一次体验）**
   - 首次运行需要 Python 3.12 + Node 18 + Docker Desktop + MySQL/Mongo/ES/Redis/RabbitMQ/MinIO + 真实模型 Key + Java/Maven。任何一个缺失即卡住。
   - 全新克隆后跑测试是红的（已在 1.1 修复），第一印象受损。

2. **验证能力窄，与"任意代码变更"的心智不符（阻塞核心价值）**
   - README 已诚实说明：Verify 检查能力主要围绕 Java/Spring。非 Java 仓库大量落到 `UNVERIFIED`，用户会觉得"没用"。
   - 进度（见 §6.7）：**JavaScript/TypeScript 已可在真实 Docker 沙箱内跑"仓库自带测试差分"**（默认即可，无需开关），Python 仍默认降级为 `UNVERIFIED`（需显式开关且诚实标注宿主执行）。
   - **"跑完看不见"已收口**：Base/Head 差分归因与**执行面**（沙箱 / 宿主无沙箱 / 未确认）现已贯通到需求覆盖页——归因见 §6.8，执行面披露见 §7。用户现在能看到"改前通过 / 改后失败"以及**这次到底有没有沙箱**。
   - 剩余真实短板：**Node 的实际覆盖面窄于"支持 JS/TS"**（缺离线依赖卷，装依赖的仓库仍判 `NON_REPRODUCIBLE`，任务 #56）；**Python 沙箱未建**（任务 #26）。两者都需 Docker 在线窗口。

3. **反馈链路慢且不透明（阻塞"爽感"）**
   - 一次验收从排队到出结果，进度、耗时、失败原因在前端不够实时、不够可诊断。

4. **术语负担重（阻塞理解）**
   - Spec/Proof/契约/Capsule/矩阵/Merge Certificate…引导页虽然存在，但主流程里仍频繁假设用户懂这些词。

5. **AI 开发与验收两条链路体验割裂**
   - `craft/`（开发）与 `agent/`（验收）是两套心智，用户在页面间跳转时对不上号。

---

## 1. 产品北极星与"完美产品"定义

**一句话**：任何开发者提交一个变更，都能在几分钟内拿到"这次改动到底有没有满足需求"的、可点开看证据的可信结论——且**不限语言、不依赖重型环境**。

"完美产品"的可衡量终态（GA 标准）：
- **10 分钟首跳**：全新机器从 `git clone` 到看到第一个真实验收结论 ≤10 分钟，无需 Docker。
- **≥3 种语言栈**开箱即验：Java/Spring、Python、TypeScript/Node；Go/Rust 通过通用检查器适配。
- **结论可解释**：每个 VERIFIED/BLOCKED 都能一键看到"依据哪条需求、跑了哪些检查、证据在哪、哪些没覆盖"。
- **可信度可量化**：golden-cases 上 Recall/Precision 有持续回归门禁。
- **多租户可交付**：团队权限、审计、用量在真实部署里可用，而非仅单用户本地。

---

## 2. 分阶段执行计划

图例：`[x]` 已完成并验证 · `[~]` 进行中 · `[ ]` 未开始

### Phase 1 —— 稳定与"第一小时体验"（P0，1–2 周）
让"克隆 → 跑起来 → 看到结果"这条路径不再劝退。

- [x] **1.1 全新克隆测试套件的绿色基线**：为依赖 demo git 标签的差分测试加清晰跳过门禁，消除误红与虚假通过。（已完成并验证：8 passed / 8 skipped，ruff 全绿）
- [x] **1.2 轻量本地模式（零 Docker）**：新增 `scripts/start_local_light.ps1`，仅用 SQLite 作业库 + SQLite 对象元数据起 API + Vite，无需 Docker Desktop。已端到端实测：脚本退出码 0，`/health` 返回 ok，`:8016` API 就绪、`:5176` Vite 返回 200；空库下 `/agent/jobs`、`/jobs` 均 200。README 已补"想先快速体验，不想装 Docker？"入口。
  - 边界（诚实标注）：轻量模式支持工作台/AI 开发助手/模型连接/历史浏览；需 RabbitMQ + Worker 的 Java/Spring 差分验收任务投递仍走全栈 `start_local.ps1`。下一步：为该 worker 增加进程内/轻量执行选项，把差分验收也并入零 Docker。
- [~] **1.3 演示仓库自动化**：`specproof demo`（CLI 一键初始化演示仓库 git 历史 + 可选 `--run` 真实验证）已存在；`prepare_demo_repo.ps1` 提供等价脚本路径。**本轮修复关键不一致**：`cli/specproof/commands/demo.py` 与 `scripts/prepare_demo_repo.ps1` 此前创建标签 `head-v1-bug`，而全仓其余部分（`agent/worker.py` 与所有 agent 节点默认 `head_ref`、`golden-cases/scenario.json`、`seed_demo.py`、`build_golden_scenarios.py`、CLAUDE.md/docs 速查命令、`tests/integration/test_differential.py`）一律使用 `head-v1`——导致 ① 差分集成测试 `_demo_tags_present()` 永远为假、跑完 bootstrap 仍 vacuous skip；② 文档里的旗舰命令 `verify --head head-v1` 对刚初始化的演示仓库失效。已将两个 bootstrap 工具对齐到 `head-v1`。端到端实测：`specproof demo` 现输出 `base -> head-v1`，`git tag -l base head-v1` 两标签齐全。
  - ✅ 首次运行钩子已落地：`start_local.ps1`（seed 之后、前端之前）与 `start_local_light.ps1`（前端之后、总结之前）各新增幂等「准备演示仓库 git 版本」步骤，直接调用 `cli.specproof.commands.demo.prepare_demo_repo()`（引用已存在时打印 `exists` 并跳过），git 缺失或失败仅 `Write-WarnMsg` 不阻断启动。效果：全栈模式一启动，网页「填入演示案例 → 开始验证」即开箱可跑（API 工作目录=仓库根，相对路径 `demo/spring-backend` 可解析且 `base`/`head-v1` 就位）；轻量模式则为其推荐的命令行回退预置引用。顺带修复 `prepare_demo_repo.ps1` 缺失 UTF-8 BOM 的问题（同目录其余 5 个 .ps1 均有 BOM；无 BOM 时 Windows PowerShell 5.1 按 GBK 误读其中文注释/字符串而解析失败，本文件内容经 UTF-8 解码后语法完全有效），补齐 BOM、保留 CRLF。已验证：`powershell 5.1 Parser::ParseFile` 对 `prepare_demo_repo.ps1`/`start_local.ps1`/`start_local_light.ps1`（及 `stop_local`/`build_web`/`seed_sandbox_cache`）共 6 个脚本全部 OK；`.venv(3.12)` 实跑钩子内联命令输出 `exists`、退出码 0、demo 仓库 `base`/`head-v1` 齐全且工作树干净（新建路径已由上一轮 `specproof demo` 实测 `base -> head-v1`）。
  - 待办（下一步）：网页「新建验证」在缺标签时给"一键创建演示仓库"按钮（后端端点触发 prepare），而非依赖 `start_local` 钩子或让用户手敲 CLI。
- [x] **1.4 失败可诊断化**：所有基础设施缺失（Docker/模型 Key/Maven）在前端映射为"下一步做什么"的行动卡，而非堆栈。（**已收口**：语言感知的环境预检接入管线 + 透出网页，见下方"本会话后段追加"）
  - 已完成：`summary.errors` 与 `job.last_error` 现均经 `describePipelineError` 映射（JobDetail.tsx）——已知 git/依赖错误签名（引用无法解析、路径不存在、检出失败、demo-only 反例缺口、无 pom.xml、模型不可用等）显示可操作的中文行动卡，原始英文串保留在 `title`（悬停/审计可见、绝不作为可见文本泄漏）；未识别的错误**逐字透传**，不臆造语义。新增测试锁定「worker last_error 诊断 + 原文留在 title」行为。
  - 已完成（同一映射复用到 Craft）：把 `describePipelineError` 提取为共享模块 `apps/web/src/ui/errorHints.ts`，VERIFY 与 CRAFT 两条流程同源；开发助手失败横幅（AgentJobDetail.tsx）与结果页 `result.reason`（AgentResult.tsx）现同样先给中文行动卡、原文保留在 `title`/折叠的「完整执行记录」JSON。新增 `ui/__tests__/errorHints.test.ts` 锁定已知签名→中文、未知/空串逐字透传。前端门禁全绿（tsc / 144 vitest / vite build）。
  - 已完成（签名按后端**实际产出**的 `state["errors"]` 字符串校准，非臆测）：遍历 `agent/nodes/*.py` 的 `errors.append(...)` 全部字面量，补齐此前未覆盖者——`No head workspace - cannot generate tests`、`Error preparing base/head workspace`（工作区准备失败）、`Fallback template failed to compile on Head` / `COMPILATION ERROR`（以**中性、不下结论**的措辞映射：既提示可能是版本与需求不符，也可能是构建环境问题）、`LLM contract compilation failed`（并入模型服务类）、并把 git-diff 签名扩展为逐文件形式 `git diff for X failed`。`ui/__tests__/errorHints.test.ts` 覆盖以上并保留「未知串逐字透传」不变式。前端门禁全绿（tsc / 149 vitest / vite build）。
  - 已完成（提交前失败的传输层翻译）：`NewVerification` 提交时若 `fetch` 被拒（后端未启动 / API 地址错误 / 离线 / CORS），此前会把浏览器英文直接抛给用户。现已**下沉到共享客户端 `api.ts`**：新增 `doFetch` 包裹 `apiGet/apiPost/apiDelete/downloadCapsule` 的 `fetch`，把无 `status`/`code` 的传输 reject 统一转成 `ApiError(0, 中文行动卡)`，并**原样重抛 AbortError**（避免把用户取消误报为断网）——因此所有写/读操作一次性受益。`NewVerification.describeSubmitError` 保留自身网络分支作纵深防御（生产下现收到已翻译的中文 `ApiError`，二者不冲突）。新增 `__tests__/api.net.test.ts` 锁定「reject→中文 ApiError(0)」与「AbortError 透传」。前端门禁全绿（tsc / 153 vitest / 29 文件 / vite build）。
  - 说明（已核实）：`agent/preflight.py` 的 `run_preflight` / `format_preflight_report`（JDK21 / JAVA_HOME / Maven-wrapper / Docker / 磁盘 检查）**全仓零调用点**（grep 仅命中定义处）——即当前是未接线的诊断代码，其友好文案既不经 web、也不经 CLI 呈现给用户。因此未把这几类文案纳入 web 映射（避免死签名）；真正的 JDK/Maven 环境失败目前多以 worker 子进程的原始 stderr 形式落入 `last_error`，已被上面的通用签名兜底。
  - ✅ **已完成（本会话，Phase 1.4 主线收口）**：`run_preflight` 已真正接入管线并端到端透出到网页。
    - **痛点根因**：旧 `run_preflight` 无条件检查 JDK / JAVA_HOME / Maven-wrapper / Docker——正因如此它一旦接进管线就会挡死所有非 Java 作业，于是长期处于"零调用点"状态。**本次先把实现改成语言感知，再接线**，这是顺序上不可颠倒的一步。
    - **`agent/preflight.py` 重写**：新增 `detect_language()`（按 marker 文件识别 java/node/python/go，Java 优先，因为 Java 仓库常同时带 package.json）；按语言只跑相关检查（Java→java/javac/JAVA_HOME/maven_wrapper；Node→node/包管理器/`scripts.test`；Python→解释器/pytest；Go→go），通用项仅磁盘空间；新增 `skipped` 字段显式记录"因项目类型不适用而故意没跑的检查"，避免看起来像静默通过。
    - **三处真实缺陷顺带修掉**：① `JAVA_HOME` 缺省从**阻断性 error 降为 warning**（PATH 上的 java 可用即足以继续，多数环境并未设 JAVA_HOME，此前的判定会误挡合法环境）；② **wrapper-less Maven 仓库**在 `mvn` 可用时不再报错（改为 PASS + 记录 system mvn 版本），只有 mvnw 与 mvn 都没有才阻断；③ **Windows 上 `npm`/`yarn`/`pnpm` 探测失败**——Python subprocess 不解析 PATHEXT，而 npm 实际以 `npm.cmd` 提供，导致健康的 Node 工具链被报"包管理器缺失"。新增 `_probe_variants()` 按 `.cmd/.exe/.bat/原样` 依次尝试，并用**真实的 npm 探测**验证（本机由 FAIL 变为 `npm 10.9.7` PASS）。
    - **`agent/nodes/preflight.py`（新）**：位于 `intake` 之后、`compile_contracts` 之前。上游 intake 已有错误时**跳过自身**（`not_run=upstream_errors`），不给真正的病因叠加环境噪音；探测自身异常时 fail-open（`not_run=probe_error`）并只记 warning；提供 `SPECPROOF_PREFLIGHT=0` 关闭开关（供隔离 CI 与单测）；阻断原因以稳定前缀 `Preflight: ` 写入 `state["errors"]`。
    - **`agent/graph.py`**：新增 `preflight` 节点与 `_abort_on_preflight` 条件边——工具链缺失时**在跑任何构建之前**短路到 `publish_report`。效果从"几分钟后吐出原始 Maven stderr"变为"几秒内给出该装什么"。
    - **透出到网页**：`agent/worker.py` 的 `_state_summary` 增加 `preflight` 字段（结构化 checks/warnings/skipped）；前端新增 `apps/web/src/ui/preflight.ts`（check id/status/语言的展示层翻译，未知值原样透传）+ `PreflightCard.tsx`，接入 `JobDetail` 概览；`ui/errorHints.ts` 把 `Preflight: ` 前缀路由到专用中文行动卡映射；`ui/stages.ts` 补 `preflight` 步骤中文名。
    - **已验证**：`tests/unit/test_preflight.py` **26 passed**（含红线用例：Node/Python 仓库在**没有 JDK** 时必须仍 PASS；wrapper-less + 有 mvn 必须 PASS；JAVA_HOME 缺失只 warning；旧 JDK 阻断；未知语言不被阻断；探测超时/probe 崩溃不抛异常）。`tsc --noEmit` 干净、`vite build` 通过、全量 vitest **173 passed / 31 文件**（新增 `ui/__tests__/preflight.test.ts` 14 例与 JobDetail 2 例）。后端相邻子集 `test_preflight + test_api_jobs + test_worker_cancel_points + test_worker_error_classify` **64 passed**；`ruff` 对 `agent/` 全绿。
    - 剩余（诚实标注）：预检结果尚未出现在 **HTML 报告**与 CLI 输出中（目前只在任务详情的 summary 通道）；`agent/preflight.py` 的 JDK 版本门限仍是 21（演示仓库要求），未来目标仓库 JDK 版本从构建配置读取后应改为动态判定。
- [x] **1.7 Python 版本门槛显性化（实测新增，已完成并验证）**：在默认 `python` 为 **3.11.1** 时，`tests/unit` 多个模块（含 `agent/job_control.py`、`experiments/minimize.py` 等使用 **PEP 695 泛型语法**的源文件）在收集期抛 `SyntaxError: expected '('`，既不指向"版本不对"也不列受影响模块，对新人极具劝退性。修复：`tests/conftest.py` 新增 `pytest_configure` 版本门禁——低于 3.12 时用 `ast.parse` 扫描源码树、统计真正需要新语法模块数，并以**一条可操作的 `pytest.exit`（USAGE_ERROR/exit 4）**取代成堆语法错误；≥3.12 短路、零影响。已验证：3.11 下 `test_minimize.py` 从"13 例 SyntaxError 墙"变为单行提示（点名 `agent\job_control.py, experiments\minimize.py` + `py -3.12 -m pytest` 指引）；ruff 全绿（mypy 的 `tests/` 已被 `pyproject` 排除，非门禁）。
- [x] **1.5 单测提速（第一步）**：按目录自动为 `tests/integration`、`tests/e2e` 打 `integration` 标记，`pytest -m 'not integration'` 可从 2754 例降到 2662 例（92 个慢测试排除）。（已完成并验证：ruff 全绿、收集正确分区）
- [x] **1.5 单测提速（第二步，已完成并实测）**：在 unit 内引入 `slow` 标记，把 21 个由 `pytest --durations` 实测出来的重负载模块（完整 agent 运行时 / 多步 LLM 循环 / benchmark 模拟）自动打标，贡献者可用 `-m 'not integration and not slow'` 走快速内循环。
  - **设计纠正（诚实）**：本项原写"并**默认排除**"，实做时改为**不默认排除、只供按需选择**。原因：CI 的合并门是 `python -m pytest tests/unit tests/security tests/fault -q`（**裸跑、无 `-m` 过滤**）。若在 `addopts` 里塞进 deselect，会让这 275 例覆盖从合并门**静默消失**——为了"体验更快"而牺牲"门是真的"，不可接受。故快速路径是**贡献者显式 opt-in**，CI 覆盖不变。
  - 度量与前后对比见 §6.6。
- [~] **1.6 网页版 Verify 的后端解耦**：实测发现 `POST /jobs` 在 `api/routes/jobs.py` 里**硬编码 `MySQLStore`（Outbox）+ `RedisStore`（SSE）**，与 Craft 侧可插拔的 `AgentJobStore`（InMemory/SQLite/MySQL）不一致——这正是"轻量模式无法跑网页版差分验收"的根因。
  - 本轮已落地（可验证）：把该路径的 503 从"直吐原始异常"改为**可操作的行动指引**（提示需要 MySQL/Redis，或改用 CLI `specproof verify`），异常细节仅进日志；前端 `NewVerification` 将 503/`PROVIDER_UNAVAILABLE` 翻译成中文行动提示，不再把英文堆栈抛给用户。已验证：`tests/unit/test_api_jobs.py` 19 passed（含 `NOT accepted` 断言不破）、`NewVerification.test.tsx` 4 passed、`api/routes/jobs.py` ruff+mypy 全绿。
  - 待办（属较大重构，需评估范围后再动）：为 Verify 作业引入可插拔存储 + 进程内执行器/进度通道，使零 Docker 也能跑网页版验收，与 Craft 对齐。

### Phase 2 —— 多语言验证能力（P1，3–6 周）
兑现"任意变更"的价值承诺，这是"好不好用"的分水岭。

- [x] **2.0 现实校正**：执行层其实已具备适配器架构 `experiments/adapters.py`（`ExecutionAdapter` 协议 + registry + 兼容矩阵），且 **Python/pytest 适配器已实现**（local-first，无 Docker）。真正缺的是把"仅 Java"的对外口径与体验补齐。
- [x] **2.3 JavaScript/TypeScript 一等支持**：新增 `NodeAdapter`——`detect` 认 `package.json` + `scripts.test`，`run` 执行项目自带 `npm test --silent`，`collect` 解析 Jest/Vitest/node:test 汇总，无法识别时计数为 0 并以 exit_code 为准（绝不伪造通过）。registry 注册、兼容矩阵 + `EXECUTION_COMPATIBILITY.md` 同步为"已支持 (local-first)"。已验证：新增 `tests/unit/test_node_adapter.py` 17 passed/1 skipped、ruff+mypy 全绿、并**用真实 `node --test --test-reporter=tap` 输出验证解析器**（tests:2/passed:2）。
- [ ] **2.1 差分链路贯通**：让 `run_differential` 的"基线跑/待验跑"对比对 Node/Python workspace 也产出 base_pass_head_fail 级证据（目前生成 JUnit 反例仍偏 Java）。
  - **实测发现（2026-09-21，故此时序上尚不可动工）**：真正的拦路点在**上游的 `generate_counterexamples`**，不在 `run_differential`——生成器整体是 JUnit/Spring/演示仓库专用：LLM prompt 写死"Java security test engineer / Spring Boot"，`_TEST_SCHEMA_REQUIRED` 校验的是 `import org.junit...`/`MockMvc`，落盘路径写死 `src/test/java/com/specproof/demo/SpecProofGeneratedTest.java`，`_is_demo_repo` 之外的仓库诚实返回"无测试生成"。因此 Node/Python 侧根本没有反例可跑，`run_differential` 的语言无关化只是后半程。多语言贯通需要先做**分语言的测试生成（prompt + schema 校验 + review 规则 + 落盘布局）**，且必须接**真实模型**才能端到端验证——属较大、离线不可完全验证的工作，暂缓以免留下半成品。适配器层（Node/Python detect/prepare/run/collect）已就绪，是这条链路的下游地基。
  - **本轮可落地的替代（诚实降级，见 2.4）**：把"当前语言/仓库无法生成可执行反例→差分不可复现"这条既成事实，在前端用中文讲清楚原因与下一步，而非暴露英文枚举/堆栈。
- [x] **2.4 "无构建配置的诚实降级"**：统一"跳过≠通过"呈现，避免误导为绿灯。落地见任务 #9 / #28（语言感知的差分回退：非 Java 仓库明说"无法生成可执行反例"并给下一步，而不是留一条空绿线）。
- [ ] **2.5 需求→可执行检查对齐**：无法编译为检查的需求标注覆盖不足并给补充建议。
- [ ] **2.6 更多语言**：Go、Java/Gradle 适配器（矩阵中的 planned 行）。

### Phase 3 —— 验收体验与实时性（P1，并行推进）
- [ ] **3.1 实时进度与流式日志**：SSE 事件粒度到"节点级"，前端时间线展示每步耗时/产物/失败点。
- [~] **3.2 结论页重做**：首屏三问——通过没？风险在哪？我下一步做什么？证据折叠可展开。
  - 本轮（可验证）：`JobDetail` 首屏"验证结论"大数字卡此前直显英文枚举（`VERIFIED`/`BLOCKED`/`NEEDS REVIEW`…）。新增 `verdictLabel()`：已知枚举译成中文（通过/受阻/执行失败/需复核/待验证/已过期/已取消），**未知值原样透传不臆测**（错误的友好标签会误导合并决策）。已验证：`JobDetail.test.tsx` 4 passed（含新用例断言显示"受阻"且无裸"BLOCKED"）、`tsc` 干净、全量 vitest 119 passed。
- [x] **3.3 术语内联化**：矩阵/契约/Capsule 首次出现处悬浮解释，引导页关键步骤做成产品内 checklist（进度持久化）。
  - **2026-09-23 完成"悬浮解释"这一半**：见文末 `2026-09-23` 条目——术语表抽成共享 `ui/glossary.ts`（上手指南与页面内 `<Term>` 读同一份数据），内联 `<Term>` 已落在 需求覆盖 / 验收规则 / 任务详情 / 风险详情 / 新建验证 五处主流程。
  - **2026-09-24 完成 checklist 这一半**：见 §9。四步各有"判断依据"注脚，系统可检测的两步由一次真实工作区探测回答，只有用户能确认的两步永不由系统打勾；进度存本机 `localStorage`，并区分"读不出来"与"没做过"。
  - **仍不在范围内**：Craft/AI 开发通道的第一步体验（§9.6 第 1 条）、跨设备进度。
- [ ] **3.4 开发与验收链路缝合**：一次 AI 开发完成后可"就地发起独立验收"，产物与结论互相跳转。

### Phase 4 —— 可信度工程与评测（P2）
- [ ] **4.1 Golden-case 回归门禁**：每次改动跑 Recall/Precision 阈值，跌破即红。
- [ ] **4.2 反例生成质量**：counterexample 从"能编译"到"真能复现回归"。
- [ ] **4.3 Merge Certificate 签名**：Ed25519（现为 SHA-256 哈希占位）。

### Phase 5 —— 团队化与生产化（P2）
- [ ] **5.1 多租户与权限落地**：`identity/` 在真实存储下可用，RBAC 前后端一致。
- [ ] **5.2 用量与账单准确**：模型 token/成本核算对齐真实 provider。
- [ ] **5.3 可观测性默认开启**：`observability/` + compose 指标看板开箱可用。
- [ ] **5.4 部署形态**：单二进制/容器一键部署、迁移与回滚脚本。

### Phase 6 —— 差异化与生态（P3）
- [ ] 6.1 IDE/CI 集成（PR 上自动验收评论）。
- [ ] 6.2 MCP/插件生态成熟。
- [ ] 6.3 Capsule 分享与协作评审。

---

## 3. 执行节奏与验收标准

- **每个 PR**：前端 `tsc + vitest` 全绿；后端 **全量** unit 全绿（CI 合并门裸跑 `pytest tests/unit tests/security tests/fault`，含 `slow` 标记的 275 例）；`ruff` + `mypy` 通过。
  - **开发内循环 ≠ 验收门**：本地迭代可先跑 `pytest tests/unit -m "not integration and not slow"`（实测约 3 分钟，vs 全量约 16 分钟），但**推送前必须补跑全量**——快速路径是便利，不是标准。
- **每个 Phase 结束**：更新本文件勾选状态 + 在 `docs/operations/` 留实测记录（命令、输出、结论），杜绝"声称完成但无证据"。
- **优先级原则**：先降低上手摩擦（Phase 1），再扩验证能力（Phase 2），体验与可信度并行。

## 4. 本次会话已落地
- Phase 1.1：`tests/integration/test_differential.py` 引入 `requires_demo_repo` 跳过门禁，全新克隆下差分集成测试从"5 失败"变为"清晰跳过"，并消除一处 `git show` 空输出导致的虚假通过。已验证：`8 passed, 8 skipped`，`ruff` 全绿。
- Phase 0：本路线图（实测诊断 + 分阶段计划 + 验收标准）。
- Phase 1.5（第一步）：`tests/conftest.py` 新增按目录自动打 `integration` 标记的收集钩子，`-m 'not integration'` 可排除 92 个慢测试。已验证收集分区正确、`ruff` 全绿。
- Phase 1.2：新增 `scripts/start_local_light.ps1`（零 Docker 轻量启动），端到端实测通过（脚本退出 0、`/health` ok、Vite 200、SQLite 后端读接口 200），README 补充入口。
- Phase 2.3：`experiments/adapters.py` 新增可工作的 `NodeAdapter`（detect/prepare/run/collect/cleanup + Jest/Vitest/node:test 汇总解析），注册进 registry、兼容矩阵与 `EXECUTION_COMPATIBILITY.md` 改为"已支持 (local-first)"；新增 `tests/unit/test_node_adapter.py`（17 passed/1 skipped），ruff + mypy 全绿，并用真实 `node --test` 输出验证解析器。同步更新受影响的既有矩阵/计划适配器测试。README 如实更新支持语言范围。
- Phase 1.6（第一步，可验证）：`POST /jobs` 的 503 从"直吐 MySQL 异常堆栈"改为**可操作的中文/英文行动指引**（异常细节仅进日志），前端 `NewVerification` 把 503/`PROVIDER_UNAVAILABLE` 翻译成"轻量模式请改用 CLI 或启动依赖服务"的中文提示，并新增对应测试。已验证：`test_api_jobs.py` 19 passed、`NewVerification.test.tsx` 4 passed、ruff+mypy 全绿。同时顺手修掉 `providers/openai_compatible.py` 一处真实的 `kwargs` 重复定义 mypy 报错（mypy strict 门禁恢复绿色）。
- Phase 2.1（实测校正，暂缓）：确认多语言差分的真正阻塞在上游 `generate_counterexamples`（LLM prompt/`_TEST_SCHEMA_REQUIRED`/落盘路径整体写死 JUnit+Spring+`com.specproof`，`_is_demo_repo` 之外诚实返回"无测试"），非 `run_differential`；分语言生成需接真实模型端到端验证，属离线不可完整验证的较大改造，故不做半成品，适配器层作为已就绪的下游地基保留。
- Phase 3.2（第一步，可验证）：`apps/web` 新增 `verdictLabel()` 并在 `JobDetail` 首屏"验证结论"卡本地化英文枚举（通过/受阻/需复核/待验证…，未知值原样透传不臆测）。已验证：`JobDetail.test.tsx` 4 passed（新用例断言显示"受阻"、无裸"BLOCKED"）、`tsc --noEmit` 干净、全量 vitest 119 passed。
- Phase 1.7（已完成并验证）：`tests/conftest.py` 新增 `pytest_configure` Python 版本门禁——低于 3.12 时 `ast.parse` 扫描源码、以一条可操作的 `pytest.exit`（exit 4，点名 `agent/job_control.py` 等 PEP 695 模块 + `py -3.12 -m pytest` 指引）取代成堆 `SyntaxError` 收集错误；≥3.12 短路零影响。README 补 `python --version` 前置校验与旧解释器重建 venv 提示。已验证：3.11 下 `test_minimize.py` 单行清晰提示、ruff 全绿；provider/jobs/adapters 等既有可跑子集在加门禁前已分别 54/19/17 passed。
  - **顺带纠正一处自伤**：本机同时存在全局 `python`（3.11.1）与项目 `.venv`（3.12.14）；之前的"13 例收集错误"正是误跑 3.11 所致。改用 `.venv/Scripts/python` 后同批测试 89 passed/1 skipped，版本门禁在 3.12 下确认为无害短路。以后所有后端命令一律走 `.venv/Scripts/python`（已写入项目记忆）。
- Phase 2.4（第一步，可验证）：`apps/web/src/pages/JobDetail.tsx` 新增 `describePipelineError()`，把流水线记录的多语言/构建相关的英文错误串（仅支持 demo 仓库、无法生成反例/非可复现、缺 `pom.xml`、模型不可用四类）翻译为带**下一步动作**的中文说明，未知字符串原样透传不臆测；`title` 仍保留原始串供悬浮/审计。同面板标签"证据与产物 Artifacts/Report/Retrieval/Pipeline Errors"一并中文化。已验证：`JobDetail.test.tsx` 5 passed（新用例断言显示"演示仓库/接入对应检查器后重新验证"、无裸英文枚举、悬浮 title 保留原文）、`tsc --noEmit` 干净、全量 vitest 120 passed。
- Phase 3.2（第二步，可验证）：`JobDetail` 首屏横幅新增**状态感知的"下一步"行动按钮**（`nextAction`）：BLOCKED 且有风险 → "查看 N 条风险并处理" 跳到风险发现页；VERIFIED → "查看验证报告" 跳报告页；UNVERIFIED/覆盖不足 → "了解如何补全验证" 跳引导页；替代此前忽略结果、恒为"查看需求覆盖"的单一 CTA。配套 `.next-action` 样式。已验证：`JobDetail.test.tsx` 6 passed（新增用例断言 BLOCKED+3 风险时出现"查看 3 条风险并处理"、点击后概览内容卸载）、`tsc --noEmit` 干净、全量 vitest 121 passed。
- Phase 3.x（术语负担，痛点#4，可验证）：新建共享术语对照 `src/ui/toneMap.ts` 的 `severityHint()`/`evidenceLabel()`（保留英文规范值作可追溯 token，未知值原样透传不臆造），从 `ui/index` 导出。`FindingDetail` 全量去英文化：风险 pill 下加"该怎么办"中文提示、证据方式中文化、面板/字段/按钮标签（严重程度/验收条件/证据方式/置信度/代码位置/问题类型/复现包/基本信息/问题描述/影响路径/证据来源/下载复现包）本地化，**保留红线测试**（tone class、绝不显绿、`findByText("BLOCKER")` pill 仍可定位）。`JobDetail` 风险发现表：表头中英→纯中文、证据列用 `evidenceLabel` 加中文注、严重度 pill 悬浮 `title` 显示中文提示。已验证：`tsc --noEmit` 干净、`vite build` 通过、全量 vitest **125 passed**（toneMap +3、FindingDetail +1、JobDetail 用例增强断言中文表头与证据注）。
- Phase 3.x 续（执行阶段，痛点#3/#4，可验证）：新建 `src/ui/stages.ts` 的 `stageLabel()`/`STAGE_LABELS`，覆盖 `agent/graph.py` 全部 15 个节点 id（intake…publish_report → 中文步骤名），`JobDetail` 执行进度行用中文步骤名展示、原始 id 移入 `title` 供审计，未知节点原样透传真实 id；实时日志行的 `[stage]` 前缀同样走 `stageLabel`。合并证书面板标签去中英混排（证书文件/签名文件/签名声明（in-toto 风格）/证书内容（原始 JSON）/复现包下载），**保留原始签名 JSON 不美化**、无密钥时如实说明"不伪造可信签名"。已验证：`tsc` 干净、`vite build` 通过、全量 vitest **129 passed**（新增 `stages.test.ts` 4 例：已知映射、未知透传、空值破折号、覆盖全 15 节点）。
- Phase 1.3 / 3.x（上手 + 术语，痛点#1/#3/#4，可验证）：`describePipelineError()` 扩充对 git 引用/检出/差异/路径不存在四类底层错误的中文翻译（覆盖 `agent/repo_safety.py`/`prepare_*`/`collect_diff` 实际产出的串，如 `does not belong to the repository: fatal: unknown revision`、`Repository path does not exist`、`Failed to checkout`、`git diff failed`），每条给"确认分支/标签/提交 SHA""换可检出引用""确认是 Git 仓库"等可操作下一步，原始串保留在 `title`；未识别串仍原样透传不臆测。新增共享 `checkerLabel()`/`CHECKER_CN`（http/sql/redis/openapi/rabbitmq/constitution/tests），应用于 `Matrix` "检查方式"单元格（原 token 移入 `title`）。已验证：`tsc` 干净、`vite build` 通过、全量 vitest **131 passed**（JobDetail 新增引用错误中文用例断言无裸 git stderr + title 保留；toneMap 新增 checkerLabel 用例含未知透传/空值）。
- Phase 3.x（后端降级原因，痛点#3，可验证）：`api/routes/web.py` 三处面向用户的降级串原为英文，直接落到中文 `Degraded` 组件里——改为可操作中文（风险数据/验收检查项/验证摘要暂时无法读取，提示刷新重试）；`logger.warning` 仍保留英文供运维。已验证：`.venv(3.12)` 下 `tests/unit/test_web_api.py` **35 passed**（相关用例仅断言 `degraded_reason` 真值，未锁英文），`ruff`、`mypy` 对该文件均绿。
- Phase 3.x（Craft/agent 控制台去术语，痛点#5，可验证）：把 SpecCraft 控制台里此前"算了但没显示"或裸英文的 token 改为共享中文标签、原始 token 移入 `title` 供审计、未知值原样透传不臆测。`agent/util.ts` 新增 `diffFileStatusLabel`/`diffModeLabel`/`approvalDecisionLabel`/`approvalTargetLabel`/`sseStateLabel`；应用面：`AgentJobShell` 状态 pill 与概览行用 `agentStatusMeta().label`、事件表 `ev.type`→`eventKindLabel`、Diff 页 status/mode/文件数、JobDetail StatCard 状态 + Repo/Task/Worker 标签、PlanStep 决策 + 状态说明、审批收件箱筛选下拉与 `ApprovalCard` target/job/by 前缀、ToolStream SSE 连接态、Edits 文件数、Result eyebrow。已验证：`tsc --noEmit` 干净、`vite build` 通过、全量 vitest **138 passed**（`util.test.ts` 新增 diff/approval/sse 三组用例，含未知透传；`AgentApprovalsInbox` 按 value 而非 label 筛选故仍绿；`AgentToolStream` 只锁"已结束 closed"后缀故安全）。
- Phase 1.3（演示 bootstrap 一致性，痛点#1，可验证）：发现并修复 `cli/specproof/commands/demo.py` 与 `scripts/prepare_demo_repo.ps1` 创建演示标签名 `head-v1-bug` 与全仓默认 `head-v1` 不一致的问题——该不一致使差分集成测试 `_demo_tags_present()` 永假（bootstrap 后仍 vacuous skip）、文档旗舰命令 `verify --head head-v1` 对新初始化演示仓库失效。两处统一改为 `head-v1`（含 docstring/注释/help 文案）。**并同步前端 `apps/web/src/demo.ts`**：`DEMO_VERIFY.head_ref` 原为 `head-v1-bug`，若不对齐，网页「填入演示案例」会提交已不存在的引用而报"引用无法解析"——改为 `head-v1`，注释/`DEMO_VERIFY_REPO_NOTE` 一并补上 `specproof demo` 入口（`Guide.tsx`/`NewVerification.tsx` 消费该常量故自动跟随）。已验证：`.venv(3.12)` 下 `py_compile` 通过、`ruff check` 全绿、`mypy` 对 `demo.py` 无新错（仅 `evidence/verdict.py:160` 既有无关错误）；实跑 `specproof demo` 输出 `base -> head-v1`，`git -C demo/spring-backend tag -l base head-v1` 两标签齐全；`grep -rn head-v1-bug` 全仓（除本文档历史条目外）已无引用；PS1 仅做 ASCII token 替换、中文与行尾未受影响（原文件本就无 BOM，与 `git show HEAD` 一致）。
- 本会话后段追加（Phase 1.4 失败可诊断化主线，痛点#1/#3，可验证）：
  - `describePipelineError()` 提取为共享模块 `apps/web/src/ui/errorHints.ts`，VERIFY 与 CRAFT 同源；`JobDetail` 的 `job.last_error` 此前**裸输出**英文，现与 `summary.errors` 一样先出中文行动卡、原文留 `title`。Craft 侧 `AgentJobDetail`（FAILED 横幅）与 `AgentResult`（`result.reason`）同步接入。
  - 签名按后端**实际** `state["errors"]` 字面量校准（遍历 `agent/nodes/*.py` 的 `errors.append`）：补齐 `No head workspace`、`Error preparing base/head workspace`、`Fallback template failed to compile on Head`/`COMPILATION ERROR`（中性措辞、不下结论）、`LLM contract compilation failed`、逐文件 `git diff for X failed`。未知串仍逐字透传。
  - **实测发现**：`agent/preflight.py` 的 `run_preflight`/`format_preflight_report`（JDK21/JAVA_HOME/Maven-wrapper/Docker/磁盘）**全仓零调用点**=未接线诊断代码，其友好文案既不上 web 也不上 CLI。故未把这几类文案塞进 web 映射（避免死签名）；真正的 JDK/Maven 失败目前以 worker 子进程 stderr 落入 `last_error`，已被通用签名兜底。
  - 传输层兜底**下沉到 `api.ts`**：新增 `doFetch` 包裹 `apiGet/apiPost/apiDelete/downloadCapsule` 的 `fetch`，把无 `status`/`code` 的 reject（后端未起/地址错/离线/CORS）统一转 `ApiError(0, 中文行动卡)`，且**原样重抛 AbortError**（取消≠断网）——所有读写操作一次性受益；`NewVerification.describeSubmitError` 保留自身分支作纵深防御。
  - 文案去脆弱化：`demo.ts` 的首运行提示拆为具名 `DEMO_VERIFY_PREPARE_NOTE`+`DEMO_VERIFY_ABS_PATH_NOTE` 组合，`Guide.tsx` 不再对整串 `split("; ")[1]`（改写文案即静默丢句的隐患）。
  - 开发→验收衔接（痛点#5）：Craft 结果页「新建独立验收」由空白 `#/jobs/new` 改为 `#/jobs/new?repo=<job.repo_path>`，复用 `NewVerification` 的 `?repo=` 预填契约，免去重填绝对路径。
  - 门禁累计：前端 `tsc --noEmit` 干净、`vite build` 通过、全量 vitest **157 passed / 30 文件**（新增 `errorHints.test.ts`、`api.net.test.ts`、`demo.test.ts` 与 Craft/Verify 用例）。
  - 2026-09-22 追加（Phase 1.4 核实 + Phase 1.9 表格收敛，痛点#3，可验证）：**核实并纠正两处"计划与代码不符"**——(a) `experiments/adapters.py` 模块 docstring 原谎称 Node 适配器"未实现/抛 AdapterNotImplemented"，实为 `NodeAdapter.detect/run` 已落地（local-first `npm test`），改为如实清单（Java/Maven、Python/venv+pytest、Node/npm 已实现；Gradle/Go 才 raise）。(b) "下一步"里的 ①「HTML 报告与 CLI 输出补预检」经阅读 `evidence/report.py::_render_preflight`（报告已渲染预检区块，`test_report_preflight.py` 10 例覆盖）与 `cli/specproof/commands/verify.py:406-421`（CLI 已 `format_preflight_report` 且在 `not passed` 时 `SystemExit(1)`）确认**早已完成**，标记为已交付而非待办。**真实增量**：把 `apps/web/src/ui/PreflightCard.tsx` 里手写的 `<table className="data">` 迁到设计系统 `Table`（用 `render` 回调保留状态配色 STATUS_TONE、原始 check id 移入单元格 `title` 供审计、未知 id 原样透传），并补 `ui/__tests__/PreflightCard.test.tsx` 5 例（该卡此前无组件级测试）。已验证：`tsc` 干净、全量 vitest **181 passed / 32 文件**、`vite build` 通过。多语言真正阻塞仍记于 2.1（`generate_counterexamples` 写死 JUnit/Spring，非适配器层）。
  - 2026-09-22 追加（Phase 2.4 诚实化延伸，痛点#2/#4，可验证）：`agent/nodes/run_differential.py` 在"无生成的可执行反例"分支此前对所有仓库一律回一句含糊的"nothing to run"，对 Node/Python 仓库既误导又暴露英文。改为复用**已接线**的 `agent.preflight.detect_language`：当目标语言非 Java 时，DIFF-01 明细如实说明"可执行 base-vs-head 差分仅支持 Java/JUnit，此 <language> 变更由上述源码/静态检查覆盖，差分记为 UNVERIFIED 而非通过"，并附 `language` 字段；Java 仓库仍走通用明细。关键红线不破：绝不把不可复现的差分谎报为 PASS。新增 `tests/unit/test_differential_language_honesty.py` 3 例（Node→honest+language=node、Java→通用明细、Python→language=python 且不误标 node），且断言 `contract_results==[]`。已验证：`.venv(3.12)` 下新例 + 既有 `test_probe_differential` 共 **25 passed**；`ruff` 对两文件全绿（顺带 `--fix` 修了新 import 的排序）、`mypy` 对节点干净。注意：这是**诚实降级**而非多语言贯通——真正让 Node/Python 产出 base_pass_head_fail 级证据仍需 2.1 的分语言生成器。
  - 2026-09-22 追加（roadmap ④ 的安全地基：沙箱镜像/挂载参数化，可离线验证）：为 4a「为 Node/Python 建等价 Docker 沙箱」铺路——把 `sandbox/runner.py` 里 Maven 专用的镜像/环境变量/缓存卷/可写子挂载**硬编码**抽成一个 `SandboxProfile` 冻结数据类，并把 `docker run` argv 组装拆成**纯函数** `build_docker_argv(command, workspace, profile)`。安全不变量（`--user 1000:1000`/`--network none`/`--cap-drop ALL`/`--security-opt no-new-privileges`/`--pids-limit`/`--tmpfs /tmp`/只读 `/work:ro`/无 docker.sock）对所有 profile 一致施加，只有镜像名、`-e` 环境变量组、缓存卷名与容器内挂载点、可写子挂载随 profile 变化。**刻意只落地 `MAVEN_PROFILE` 一个 profile**（`_profile_from_env()` 目前恒返回它），不投产后尚无法在本机离线验证的 Node/Python 沙箱镜像，也**不把任何宿主执行接进差分流水线**——4a 的红线（`api/routes/jobs.py`"验证 API 绝不可成为远程执行面"）不动。已验证：`test_sandbox_runner.py` **18 passed**，新增的合成 `_NODE_PROFILE` 用例逐条断言同一套硬化旗标施加到非 Maven profile 上、缓存卷名可被环境变量覆盖、命令落在镜像名之后；Maven profile 的 argv 与重构前**逐字节一致**（回归锁）。`ruff`+`mypy` 对 `runner.py` 干净。另：本次发现 `test_bench_craft.py::test_recovery_tasks_ship_seeded_checkpoint` 因工作副本缺 10 个 recovery 任务的 `.specraft`（plan/checkpoint/memory）种子夹具而红——经 `bench_gen_tasks.py --check` 核实漂移**全部是"生成表有、落盘缺失"**（无内容冲突、无手工新增），确认 `write_suite` 此处纯增量后跑一次生成器补齐 30 个确定性夹具，`--check` 复绿、该文件 37 passed。**更正一条早前的错误结论**：补齐 bench 夹具后我曾据 `-x` 局部运行的 "362 passed" 误判全量已绿；实际跑完 `tests/unit`（166 模块，**2538 passed / 4 failed / 2 skipped，耗时 15:33**）显示仍有 4 处红，且都与本轮沙箱改动无关——见下一条。
  - 2026-09-22 追加（Phase 1.1 续：让"干净克隆即全绿"成立，可验证）：全量单测暴露 4 个此前被 `-x` 早停掩盖的失败，逐一修复。① `test_craft_tools::test_git_status_and_diff_on_real_repo`：gitpython 的 `index.commit` 会执行 git 的 pre-commit 钩子，而本机 `core.hooksPath` 被设为**全局** `.codex/git-hooks`，其脚本从临时仓库目录解析失败（exit 127）→ 在临时仓库写入 repo 级 `core.hooksPath=<空目录>` 覆盖全局，测试不再受开发者机器配置左右。② `test_state_channels::test_diff_by_file_survives_graph_invoke`：该"LangGraph 通道不被丢弃"的回归锁把 `repo_path` 写成仓库根、`base`/`head-v1` 标签**根本不存在于干净克隆**（根仓库无任何 tag），diff 为空 → 判"通道被丢弃"是假阳。改为在 `tmp_path` 自建一个含真实 `.java` base→head-v1 变更的 git 夹具（提交同样 `-c core.hooksPath=` 免钩子），通道守卫得以确定性验证。③④ `test_provider_accounting::test_cancelling_model_call_stops_pending_request` 与 `test_dashboard_performance` 两条：功能正确但在**多 agent 并发满载**的本机上因 1–2 秒固定等待上限（`Event.wait(1/2)`/`join(2)`）被判失败——把调度等待放宽到 10 秒、并把 dashboard 的 mock store 从"固定 1 秒"改为"显式释放前一直阻塞"（消除 `not dashboard.done()` 与 store 自然到期的竞态）。放宽仅吸收调度延迟，失败检测力不变（被取消/被阻塞的操作真实耗时远大于上限）。已验证：四个文件隔离重跑 **39 passed + 15 passed**、`ruff` 对四文件全绿（mypy 按 `pyproject.toml` 排除 `tests/`）。这是"上手即绿"痛点#1 的实质推进。
  - 2026-09-22 追加（roadmap ④/4a 安全的纯逻辑地基，可离线验证）：新增 `agent/self_test_diff.py`——"跑仓库自带测试"差分的**纯判定 + 默认关开关**，为多语言真证据铺路但**不碰任何执行面**。`self_test_verdict(base_counts, head_counts)` 吃三种 adapter 汇总口径（surefire 的 `failures`、pytest/node 的 `failed`，统一并入 `errors`）映射为 REGRESSION/COMPLIANT/AMBIGUOUS/UNEXPECTED_FIX，**零测试或解析不到汇总一律 NON_REPRODUCIBLE 绝不粉饰为通过**（诚实红线）；`self_test_execution_allowed()` 只在 `SPECPROOF_ALLOW_LOCAL_TEST_EXEC` 显式为真时放行、其余一律 fail-closed。关键：本模块**不 import adapter、不 spawn 进程、不接 `run_differential`**——在 Node/Python 等价 Docker 沙箱（依赖本轮 `sandbox/runner.py` 参数化地基）就绪前，**真实接线保持缺席**，避免"未信任 PR 自带测试在宿主执行"撞 `api/routes/jobs.py` 红线。已验证：`tests/unit/test_self_test_diff.py` **23 passed**（含三键口径、no-evidence 不可 laundering、gate 默认关/仅显式真值放行）、`ruff`+`mypy` 对模块干净。
- Phase 1.4（**已收口**，见上）——语言感知预检接入管线并透出网页。
- Phase 1.8（启动链路可见性，本轮新增并完成，可验证）：修掉三个"静默失败"缺陷。
  - **`stop_local.ps1` 不覆盖轻量模式**：只停 `api.pid`/`web.pid`，而 `start_local_light.ps1` 写的是 `api-light.pid`/`web-light.pid`，脚本却提示"停止用 stop_local" ⇒ 轻量实例残留、端口被占、下次启动被跳过。已补齐两个 light PID，并增加 `*-light.pid` 通配兜底（将来新增轻量进程不会再漏）。
  - **worker / outbox 静默失败**：启动失败原来只 `Write-WarnMsg`，脚本仍打印"全部就绪"并退出 0，用户随后只看到任务永远停在 QUEUED。现引入 `$degradedServices` 登记簿：Worker 60 秒未监听 9100、进程启动异常、Outbox 启动后立刻退出（新增 3 秒存活探测，因为 outbox 没有 metrics 端口可试）都会登记；总结段改为醒目的"启动完成，但验证管道不可用"，逐条给出原因与处理命令，并以 **exit 1** 结束（可被脚本/CI 感知）。
  - **`/health` 失真**：原实现只探 Redis，**MySQL 挂了仍返回 `status: ok`**，`Wait-ApiReady` 因此误判就绪，而真实的 `/jobs` 早已 503。现同时探 MySQL 与 Redis 并返回逐项布尔值；`status` 反映 Verify 链路（MySQL+Redis）是否就绪；新增 `agent_jobs` 探针，轻量模式（`sqlite:` 前缀）独立判定，避免"MySQL 不在就当开发助手也坏了"的误报。保持**始终 HTTP 200**（探针自身失败不得让轮询器失联），由 payload 说明真相。
  - 已验证：`tests/unit/test_api_jobs.py` 新增 `test_health_reports_degraded_when_mysql_is_down`（断言 200 + `status: degraded` + 两项 false），`test_middleware.py` 同步，合计 **35 passed**；`ruff` 对 `api/` 目标文件全绿；四个 PS1（`start_local`/`stop_local`/`start_local_light`/`prepare_demo_repo`）经 `Parser::ParseFile` 语法校验全部 OK（BOM/CRLF 未破坏）。
- Phase 3.1（向导空转步骤，本轮完成，可验证）：`AgentWizard` 的**第 3 步"门禁 Gates"没有任何可编辑控件**，用户只能点一次"下一步"空转——而 `WizardDraft.gates/budget_minutes/max_steps` 既不渲染也不提交。
  - **判定**：预算与最大步数在后端只由 `craft/budget.py` 的环境变量（`CRAFT_MAX_STEPS` 等）决定，**加开关等于放假控件**。因此正确的修法不是把控件补上，而是**把空转的步骤砍掉**：向导 4 步 → 3 步，原步骤里诚实的说明（"批准前不会改动仓库""未执行的检查不算通过""不提供预算开关""不会自动切换 Base/Head"）并入提交前的审阅页。旧路由 `#/agent/new/gates` 保留并落到审阅页，历史链接与书签不会 404。
  - 同步清理：`WizardStep` 类型、`STEPS`、命令面板条目（移除"新建任务 · 门禁"）、审阅页标题改为"步骤 3/3"。
  - 已验证：`AgentWizard.test.tsx` 更新为"下一步 → `#/agent/new/review`"、"步骤 3/3"、并保留"页面不得出现 checkbox"的断言；`tsc` 干净、全量 vitest **173 passed**。
- Phase 1.9（设计系统落地，本轮起步，可验证）：审计发现 `ui/Table`（自带排序、粘性表头、空态）**只被 UiKit 样式页使用**，13 处产品页各自手写 `<table className="data">`。本轮把最常用的 **验证历史列表 `Jobs.tsx`** 迁到 `Table`：列定义驱动、**项目名 / 验证状态 / 更新时间均可点表头排序**（此前完全不可排序）、操作列右对齐。仓库名提取抽成 `repoName()` 供排序与渲染共用，避免两处漂移。
  - 已验证：`Jobs.test.tsx` 新增排序用例（首次点击升序 → 再次点击降序），合计 **3 passed**；`tsc` 干净。
  - 2026-09-22 续迁（本轮，全部经 `tsc`/`vitest`/`vite build` 三门禁验证）：**`TenantUsers` / `TenantTokens` / `Health`（依赖矩阵）/ `Eval`（案例明细）** 四处只读/交互表格迁到设计系统 `Table`——此前**均不可排序**，现列定义驱动、可点表头排序、内置空态。`Health.test.tsx` 新增排序用例锁进行为（9→10 passed）。
    - `TenantUsers`：邮箱/角色/状态可排序，操作列（角色下拉 + 停用/启用）经 `render` 保留；空态文案「暂无用户」。
    - `TenantTokens`：名称/用户/过期/最近使用可排序（时间戳列用 `sortValue ?? 0` 让 null 稳定排前）；`expires_at`/`last_used_at` 仍渲染 ISO。
    - `Health`：抽 `DepRow` + 模块级 `DEP_COLUMNS`（依赖名经 `DEP_NAMES` 中文化、状态 pill、延迟右对齐）；`ok` 列 `sortValue` 让 OK<未知<DOWN。
    - `Eval`：抽 `EvalCase` 类型 + `CASE_COLUMNS`，Case/Verdict/应检出/期望 Severity/期望 Contract 可排序，pill 逻辑抽 `pillClass()` 供测试复用。
    - **刻意保留手写（已逐个复核为非"可排序数据集"）**：`Dashboard` 的「最近验收」表——产品化富样式预览（`table-scroll` 外层、`job-title` 链接、`demo-label`、`job-refs` 前后版本行、`sr-only` 表头、图标按钮列、仅取最近 N 条），机械套 `Table` 会降级定制排版，判定为**不迁**。
  - 2026-09-22 续迁（本轮，全部经 `tsc`/`vitest`/`vite build` 三门禁验证）：**`AgentOverview`（Agent 任务列表）/ `JobDetail`（风险发现表）** 迁到设计系统 `Table`，并顺带**扩展共享 `Table` 增加可选 `onRowClick`**（整行可点 + `tabIndex=0` + Enter/Space 键盘激活，仅在有回调时生效），惠及整套设计系统。
    - `AgentOverview`：任务/仓库/状态可排序（状态 pill 仍把原始枚举留在 `title` 供审计），步骤/事件/审批计数右对齐可排序，更新时间可排序；整行点击导航到 `#/agent/jobs/{id}`，改由 `onRowClick` 统一承担（原 `onClick` 移到行上）。空态 `Empty` 保留。
    - `JobDetail` 风险发现：抽模块级 `SEVERITY_RANK` + `sevRank()`（未知/缺失严重度沉底、不臆造标签）与 `findingColumns(jobId)`——严重程度按 rank 排序（BLOCKER/CRITICAL→…→NONE，识别不出的值给 9、空给 99），验收条件/证据方式/置信度/描述可排序（置信度 `sortValue ?? -1`），复现包列渲染下载按钮。原 pill/`evidenceLabel`/`fmtPct`/`downloadCapsule` 行为与审计 `title` 全部保留。
    - `Table.test.tsx` 新增 2 例锁定 `onRowClick`：鼠标点击 + 键盘 Enter 均触发、无回调时行不可聚焦（4→6 passed）。
  - **Phase 1.9 收口判定**：全仓 `<table className="data">` 手写表格仅剩 `FindingDetail`（2 列 kv 明细块，非表格数据集）、`AgentEventLog`（按 seq 时间序的流式日志，排序会破坏时间线）、`AgentPlanReview`（严格有序的计划步骤）、`Dashboard`（富样式预览）四处，**均为语义上不应排序的表**，保留手写合理。`Matrix`/`Contracts` 早已用 `Table`。**可排序数据集已全部落地设计系统 `Table`。**
- 下一步（优先级，已按现状校正）：① **预检透出到 HTML 报告与 CLI 输出 —— 2026-09-22 核实：已完成，非待办**：`evidence/report.py::render_verification_report` 经 `_render_preflight()` 已渲染"Environment Preflight"区块（检测语言 / PASS-FAIL-WARN 明细 / 阻断项 / 警告 / 刻意跳过项，未运行时如实说明原因），`tests/unit/test_report_preflight.py` 10 例覆盖；CLI `cli/specproof/commands/verify.py` 在建流水前 `run_preflight` 后 `click.echo(format_preflight_report(...))`，`not preflight.passed` 时打印行动提示并 `SystemExit(1)`。**预检已贯通 web 详情 + HTML 报告 + CLI 三处。** ② **其余手写表格迁到设计系统 `Table` —— 2026-09-22 收口，已完成**：`Jobs`/`TenantUsers`/`TenantTokens`/`Health`/`Eval`/`AgentOverview`/`JobDetail` 共 7 处可排序数据集全部落地列定义驱动的 `Table`（点表头排序 + 内置空态 + 右对齐），共享 `Table` 顺带新增可选 `onRowClick`（整行可点 + 键盘激活）。剩余 `<table className="data">` 仅 `FindingDetail`（kv 明细）、`AgentEventLog`（时间序日志）、`AgentPlanReview`（有序步骤）、`Dashboard`（富样式预览）四处，语义上不应排序，保留手写合理。③ **统一 `JobDetail` 与 Agent 控制台的实时通道 —— 2026-09-22 收口，已完成**：早期 `useAgentJob` 仅轮询，与验证详情页的 SSE+轮询双通道不一致。现已统一到一个健壮共享的 `api.ts::openEventStream`（带 Authorization 头、命名事件、`Last-Event-ID` 断线重放、指数退避重连）：`useAgentJob` 打开 `openAgentEventStream` 累积 `events`/`streamState`，AgentJobDetail/AgentToolStream 消费同一份。本轮再收掉**最后一处分歧**：`AgentEventLog` 原本无视 `useAgentJob.events`、自己用 `fetch(...?key=<API Key>)` 开第二条更弱的流（把密钥泄漏进 URL 查询串、无重连）——改为直接消费共享通道的 `events`/`streamState`（终态 `done`→"已同步"，否则"实时更新中…"）。新增 `AgentEventLog.test.tsx` 3 例锁定：事件经共享通道渲染、done 后切"已同步"、**断言绝不向 `/events` 直接 fetch**（守住密钥不外泄 URL）。全量 `tsc`/`vitest`(**33 文件 / 187 例**)/`vite build` 三门禁绿。④ **Phase 2.1 多语言差分（拆成两步降风险）**：**4a 离线可做、价值最高**——为 Node/Python 增加"跑仓库自带测试套件"的差分模式（base 全绿 / head 有挂 → 直接产出 `base_pass_head_fail` 真证据），复用已就绪的 `PythonAdapter`/`NodeAdapter` + `parse_pytest_summary`/`parse_node_test_summary`，无需模型即可离线端到端验证逻辑。**⚠️ 2026-09-22 安全核实（关键，勿盲接）**：`PythonAdapter`/`NodeAdapter` 是 **local-first（宿主直接跑 `pytest`/`npm test`，无容器沙箱）**，且审计确认它们**从未被生产差分流水线触达**（`run_differential` 只在拿到 Java 生成测试类时才经 `registry.get` 执行）。把 4a 直接接进 `run_differential` = **首次让未信任的 PR 自带测试在宿主上执行**，正面对撞 `api/routes/jobs.py` 记档的"验证 API 绝不可成为远程执行面"红线。因此 4a 落地**必须**满足其一：(i) 先为 Node/Python 建等价 Docker 沙箱（对齐 `JavaMavenAdapter` 的 `--network none`/只读/非 root），或 (ii) 置于**默认关闭**的显式开关（如 `SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1`）之后并在 UI 诚实标注"本地执行、无沙箱"。逻辑可先用假 adapter 离线单测（验证 verdict/digest/解析），但**真实接线到 pipeline 前不得在无沙箱宿主执行任意仓库测试**。**4b** 分语言**可执行反例生成**（LLM）需真实模型 + Docker 联调窗口，后置。⑤ **把降级原因的中文翻译下沉 —— 2026-09-22 完成 UI 侧切片**：`web.py` 的 `degraded_reason`/`degraded_reasons` 会把 `redis: {exc}`/`mysql: {exc}`/`job NOT accepted - persistence failed` 这类**技术串**直送前端 `<Degraded>`，此前原样显示英文子系统名。沿用全站一致的去术语范式（保留原始串于 `title` 供审计、命中已知子系统才加中文、**未知一律透传不臆造**），在 `ui/errorHints.ts` 新增 `describeDegradedReason()`（Redis/MySQL/持久化失败三类），`ui/Degraded.tsx` 渲染中文并把 raw 留在 `title`；`errorHints.test.ts` +4 例（含"未知子系统原样透传"）。`AgentEventLog` 断线提示也一并中文化。**遗留（低优先，需后端契约评审）**：更彻底的做法是 API 侧改吐**稳定错误码**（如 `degraded_code: "REDIS_UNAVAILABLE"`）而非 `f"redis: {exc}"` 字符串匹配——但会改动 `test_web_api.py` 断言的响应形状，属跨栈契约变更，暂缓。⑥ （低优先，安全受限）网页「一键创建演示仓库」若要做，必须置于默认关闭的显式环境变量开关（如 `SPECPROOF_DEMO_ALLOW_REPO_PREPARE=1`）之后并通过安全评审——它触及 `api/routes/jobs.py` 记档的"验证 API 绝不可成为远程执行面"红线。
- 2026-09-22 追加（FE 批次 FE-1..FE-7：主路径友好性/中文化收口，痛点#1/#3/#5，可验证）：延续"保留英文枚举/原文于 `title`、命中才加中文、未知一律透传不臆造、错误≠空态"的红线，做了一轮**面向用户的高频页**修补：
  - **FE-1 `AgentWizard` 步骤数纠偏**：向导此前标"4 步含门禁"却无门禁步（Phase 3.1 已把 4 步砍成 3 步，标题漏改），误导主创建路径。改为"3 步: 仓库 → 需求 → 提交"、`步骤 1/3`/`2/3`，并加"不得出现 `步骤 x/4`、不得出现幻影门禁步"的断言。
  - **FE-2 `Dashboard` 降级原因中文化**：首页 `degraded_reasons` 复用 `describeDegradedReason()` 出中文、raw 留 `title`，未知原因透传（新增 `Dashboard.test.tsx` 2 例）。
  - **FE-3 `Eval` 页**：逐案 verdict 经新 `evalVerdictLabel()`（PASS=判定正确 / MISS=漏检 / FALSE_POSITIVE=误报）中文化且防"token·token"重复；期望严重度走 `severityPill`+`severityHint`；**纠正把 404/读取失败与"尚无报告"混为一谈**——`ApiError(404)` 显空态、其余显 `ErrorBox`+「重新加载」（新增 `Eval.test.tsx` 5 例）。
  - **FE-4 a11y**：把裸 `placeholder`/无标签控件改为 `htmlFor`+`id` 或 `aria-label`（`AgentGates`/`AgentPlanStep`/`TenantUsers`/`TenantTokens`/`AgentOverview`/`AgentApprovalsInbox`/`TenantSwitcher`），并给租户"×"移除按钮命名。
  - **FE-5 状态术语归一**：`StatusPill` 抽出 `STATUS_LABELS`+`statusLabel()` 单一来源，`Jobs` 去掉本地重复 map 与冗余标签 span（同一状态此前既显"正在验收"又显"正在验证"）。
  - **FE-6 `Health` 去字段术语**：把面向机器的 `checks/capabilities/degraded 字段`、`/api/v1/health`、`degraded: false` 从可见文案移到新增的 `HealthCategory.detailTitle`（渲染为 `title`），可见文案改口语中文；页头横幅与降级提示改中文、`DEGRADED`/`FIVE-CATEGORY HEALTH` 原 token 留 `title`。诚实语义（缺字段=未知、降级 reason 逐字）全保留，`Health.test.tsx` 新增 1 例锁"原文仅在 tooltip、可见区无字段名"。
  - **FE-7 Identity 枚举/时间中文化**：新增 `identity/labels.ts` 的 `roleLabel`/`userStatusLabel`（viewer/operator/auditor/admin、active/disabled 出"中文 · token"，未知透传），应用到 `TenantUsers` 角色 pill + 状态列（原 token 留 `title`）；`TenantTokens` 的 `expires_at`/`last_used_at` 由裸 `toISOString()` 改为 `tsCell()`（友好本地时间 `fmtTime`、精确 ISO 留 `title`），"Scopes"表头→"权限范围 Scopes"、scopes 值留 `title`。`identity.test.tsx` 新增 2 例（枚举中文化+未知透传、时间戳友好化+ISO 留 tooltip）。
  - 门禁累计：全量 `tsc --noEmit` 干净、`vite build` 通过、vitest **35 文件 / 205 例全绿**（本批次净增 6 例：Health +1、identity +2、及 FE-1/2/3 既有用例扩充）。所有改动**未提交**（本会话全部本地未 commit）。
  - **FE-8 `AgentEdits` 密钥外泄修复（承接 roadmap ③ 实时通道收口的漏网之鱼，可验证）**：survey 发现 `pages/AgentEdits.tsx` 仍自行 `fetch(apiBase + "/agent/jobs/:id/events?key=" + getApiKey())`——把 API 明文密钥拼进 **URL 查询串**（泄漏到浏览器历史 / 代理 / 服务端访问日志），且与已统一的 `openAgentEventStream` 重复开第二条更弱的流。改为直接消费共享 `useAgentJob()` 的 `events`（`useMemo` 过滤 `type === "edit"`），连接态错误经 `sseStateLabel(streamState)` 提示。诚实空态（"尚无文件编辑事件…未接线"）与 `#seq / 变更包 / N 个文件 / 时间 / 查看差异` 行为全保留。**红线**：全站唯一 SSE = `api.ts::openEventStream`，绝不再向 `/events` 直接 fetch。新增 `AgentEdits.test.tsx` 2 例锁定：编辑事件经共享通道渲染且忽略非 edit 事件、**断言从不向 `/events` fetch 且 URL 不含 `key=`**。已验证：`tsc` 干净、`vite build` 通过、vitest **36 文件 / 207 例全绿**（含 `AgentEventLog`/`AgentPolling` 同族实时测试无回归）。
  - **FE-9 加载失败≠空态（诚实红线#3 的最严重变体，可验证）**：survey（Explore 只读排查）发现多处把"读取失败（网络/5xx）"渲染成"诚实 404 / 暂无数据"空态——比术语问题更糟，因为它**断言了一个自己并不知晓的良性状态**，正撞"绝不用一个大绿勾掩盖缺陷"红线。先加共享判据 `ui/errorHints.ts::isNotFound(err)`（鸭子类型读 `err.status===404`，不引 `ApiError` 以免成环）与 `loadFailed(err)`（有错且非 404=真失败）。本轮修三处最尖锐的"谎报 404/吞错"：① `AgentDiffViewer`（`!diff` 无脑显示"诚实 404 空态"，改为 `loadFailed` 时显示"暂时无法加载（请求失败）— 并非没有改动，请稍后重试"，真 404 仍保留原诚实串）；② `AgentApprovalDetail`（同上，失败时不再谎报"审批记录不存在"）；③ `AgentResult` 审批子请求 `.catch(() => {})` **静默吞错→面板消失**，改为记 `approvalsError` 并诚实显示"暂时无法加载…请稍后重试"（空审批仍不显示面板）。新增/改测试：`AgentDiffViewer.test.tsx` 补"5xx 不得谎报 404"一例；**顺带发现**该测试原 404 桩缺 `headers` 字段，致 `handleResponse` 在 `resp.headers.get` 处抛非-ApiError 的 TypeError（真 404 用例被旧代码无脑分支掩盖），已给两个错误桩补 `headers: new Headers()` 使夹具贴近真实。已验证：`tsc` 干净、`vite build` 通过、vitest **36 文件 / 208 例全绿**。**遗留（已建任务 FE-10/FE-11）**：`AgentOverview`/`AgentApprovalsInbox`/`TenantTokens`/`AgentJobApprovals`/`AgentGates`/`JobDetail` 标签页仍存同类空态掩盖；以及剩余裸枚举/时间戳（Billing 状态、TenantSwitcher 角色 pill、`{ev.at}` 等）。
  - **FE-10 加载失败≠空态（续 FE-9，把同一诚实红线推到其余列表/标签页，可验证）**：承接 FE-9 遗留清单，用共享判据 `loadFailed()` 收口剩余"把请求失败谎报为暂无数据/干净扫描"的页面：
    - `AgentOverview`：`listAgentJobs` 真失败（非 404）时，主区不再显示"暂无 Agent 任务"，改显"任务列表暂时无法加载（请求失败）— 这不代表没有任务"。新增 `AgentOverview.test.tsx` 2 例锁定失败态与"干净空列表仍诚实显示空态"两分支。
    - `AgentApprovalsInbox`：两处吞错——① 任务列表整体失败（原显示"尚无审批记录"）；② **逐任务审批读取被 `.catch(() => ({approvals: []}))` 静默吞掉**（原会把部分失败伪装成"无审批"）。新增 `failedJobReads` 计数，失败或部分失败时以错误框取代"尚无"文案。新增 2 例（整体 500、单任务 503 部分失败），错误桩均带 `headers`。
    - `AgentJobApprovals` / `AgentGates`：此前**同时**渲染 `errorbox` 与"尚无审批/门禁审批记录"空态（自相矛盾）。把错误改存 `Error | string`（保留 `ApiError.status`），`loadFailed` 时只显失败提示（raw 留 `title`）、不再叠空态；真 404 才回落诚实空态。
    - `TenantUsers` / `TenantTokens`：`reload()` 现先清 error+置 loading；列表读取失败时不再把空 `Table`（"暂无用户/Token"）当结论，改显失败提示 + 「重试 Retry」按钮。
    - `JobDetail`（**最尖锐的一条：失败的风险扫描被渲染成干净扫描**）：`loadArtifacts` 用 `Promise.allSettled`，新增按产物粒度 `summaryLoadFailed`/`findingsLoadFailed`（经 `loadFailed(reason)` 判定）。风险发现页读取失败时显示"无法确认是否存在风险，请勿据此判定为安全"，**覆盖**原"暂未发现已确认的问题"文案；验证结果概览读取失败时显示"暂时无法读取…请点击刷新重试"而非"尚未生成"。真 404/成功空集仍走原诚实空态。新增 `JobDetail.test.tsx` 1 例锁定"findings 读取失败 ≠ 干净扫描"。
    - 已验证：`tsc --noEmit` 干净、`vite build` 通过、vitest **37 文件 / 213 例全绿**（本批净增 5 例：Overview +2、Inbox +2、JobDetail +1）。所有改动**未提交**（本会话全部本地未 commit）。
  - **FE-11 剩余裸枚举 / 裸时间戳 / 一处 a11y（承接 FE-10，把中文化与诚实范式推到最后一批角落，可验证）**：
    - `Billing`：新增模块级 `subscriptionLabel()`/`invoiceLabel()`（`glossEnum()` 助手，命中出"中文 · token"、未命中透传），应用到期/账单状态 pill，raw 同时留 `title`；`Billing.test.tsx` 把原 `getByText("active")`/`getByText("draft")` 两处断言改为正则 `/生效中 · active/`、`/草稿 · draft/`（**仍强制裸 token 可见**，守诚实红线）。`fmtEpoch()` 经核对输出已是 `toLocaleString()` 友好格式（与 `fmtTime` 同形），不再无谓改动。
    - `JobDetail`：新增 `DEPTH_LABELS`+`depthLabel()`（FAST/STANDARD/DEEP→"快速/标准/深度验证 · token"，未知透传、空→"—"）替换原"仅 FAST 出中文、其余裸值直显"的写法。新增 2 例锁定"STANDARD 出中文且裸 token 可见""未知深度 PARANOID 原样透传"。
    - `TenantSwitcher`：角色 pill 改用 `identity/labels.ts::roleLabel()`（此前裸显 `principal.roles`），raw 留 `title`；`identity.test.tsx` 对应断言由 `getByText("operator")` 改为 `/操作员 · operator/`（token 仍可见）。
    - 裸 ISO 时间戳统一走 `ui/util.tsx::fmtTime`（可见友好本地时间、原始 ISO 留 `title`）：`AgentEventLog` 时间列、`AgentEdits` 编辑行时间、`AgentJobDetail` 时间线条目与"最近事件"值（后者原有 `title`，改可见部分）。
    - a11y：`TenantUsers` 每行的角色 `<select>` 补 `aria-label`（"用户角色 Role — {email}"，逐行唯一）。
    - **刻意保留（经复核，判定不改动）**：`Health` 依赖矩阵的错误列（`mono` 技术表格内的探针异常串）——`describeDegradedReason` 只认 `redis:`/`mysql:` 前缀，对 `connect timeout`/`ECONNREFUSED` 是透传（无收益），且该列本就是刻意留给工程师查看的原始诊断面；强行套映射反可能盖住被测试锁定的原串。
    - 已验证：`tsc --noEmit` 干净、`vite build` 通过、vitest **37 文件 / 215 例全绿**（本批净增 2 例：JobDetail 深度 +2）。所有改动**未提交**（本会话全部本地未 commit）。**至此 FE 批次（FE-1..FE-11）的高频页友好性 / 中文化 / 诚实性收口全部完成。**
  - **FE-12 契约审核状态 pill 不再隐藏裸枚举（承接 FE-11 的"未知透传"红线，扫尾 Contracts 页，可验证）**：
    - 缺陷：`pages/Contracts.tsx` 的"审核状态" pill 原来是 `STATUS[code] || "状态未知"` —— ① 命中已知值只出中文、丢弃英文枚举原值（与全站"中文 · token"约定不符）；② 后端若返回新的未知状态（如 `pending_legal_review`），被吞成"状态未知"，评审者看不到真实 token，违反"未知一律透传、绝不臆造措辞掩盖"红线。
    - 修法：在单一来源 `ui/toneMap.ts` 新增 `CONTRACT_STATUS_CN`（APPROVED/PROPOSED/REJECTED/REVOKED）与 `contractStatusLabel()`（命中→"中文 · 大写 token"、未知→原样透传大写、空→"—"），与 `statusLabel`（job 状态）是**不同枚举**故不复用；`ui/index.ts` 导出。`Contracts.tsx` 删除本地私有 `STATUS` 地图（消除"同状态两套中文"漂移风险），pill 改用 `contractStatusLabel(rule.status)` 并把 raw 留 `title={rule.status}`；筛选下拉复用 `CONTRACT_STATUS_CN`（下拉保持纯中文更简洁，pill 作为审计面才带 token）。
    - `toneMap.test.ts` 新增 3 例：已知值"中文+token 双显"、未知 `pending_legal_review` 透传且 `not.toContain("状态未知")`、空值→"—"。
    - 已验证：`tsc --noEmit` 干净、`vite build` 通过、vitest **39 文件 / 229 例全绿**（含本会话树内既有未提交用例，FE-12 净增 3 例）。所有改动**未提交**（本会话全部本地未 commit）。
  - **FE-13 首次上手文案里的裸 `BLOCKED` 枚举补中文（承接 de-jargon 红线，可验证）**：`pages/NewVerification.tsx` 演示说明原文"预期结论为 `<code>BLOCKED</code>`"直接把英文枚举丢给第一次使用的人（不知道 BLOCKED 意味着什么，正是"不友好"）。改为"预期结论为 **发现风险**（`<code>BLOCKED</code>`）"——中文 gloss 取自单一来源 `STATUS_LABELS.BLOCKED`，`<code>` 里的规范 token 仍保留供追溯（此处是固定演示结论、非运行期值，故直接内联中文不算臆造）。`NewVerification.test.tsx`（6 例）无对旧文案的锁定，未动；`tsc` 干净、`vite build` 通过。经复核 `Matrix.tsx`/`Jobs.tsx`/`AgentEventLog.tsx` 均无需改动：前两者错误≠空态已正确分流；AgentEventLog 的 `JSON.stringify(ev.data)` 是刻意保留给工程师的原始事件面（设计系统 Table 已记其"seq 有序流式日志"不迁移），强套映射反而臆造。



## 5. 2026-09-23 会话：状态核实 + Phase 3.3（术语内联化）第一片

### 5.1 状态核实（先查证，再动工）

本轮先做只读核实，避免"照着过期计划做已完成的活"：

| 核实项 | 方法 | 结论 |
|---|---|---|
| 前端门禁 | `tsc --noEmit` / `vitest run` / `vite build` | ✅ 干净 / **39 文件 226 例全绿** / 通过 |
| 计划与代码是否一致（Phase 1.9 表格） | 全仓 grep `<table className="data">` | ✅ 一致：仅剩 `FindingDetail`/`AgentEventLog`/`AgentPlanReview`/`Dashboard` 四处，**均为语义上不应排序的表**（与文末判定吻合），可排序数据集确已全部落地设计系统 `Table` |
| `Tooltip` 组件是否同样闲置 | grep `<Tooltip` | ⚠️ 只有 `ui-kit/UiKit.tsx` 的 4 处样式预览在用，产品页 0 处 —— 与当初 `Table` 的处境相同，是"已有能力没被用起来" |
| 内部链接是否有死链 | 抽取全部 `#/...` href 与 `App.tsx::renderRoute` 对照 | ✅ 无死链（14 个一级前缀全部有对应路由） |
| `/health` 与 `/api/v1/health` 是否打架 | 读 `api/server.py` 与 `api/routes/web.py` | ✅ **不是缺陷**：两者是不同契约（前者给启动轮询器，返回 `status/mysql/redis/agent_jobs`；后者给前端健康页，返回 `status/degraded/checks` 六依赖明细）。前端 `Health.tsx` 打的是 `/api/v1/health`，字段对得上 |
| Phase 1.6（轻量模式跑验收）是否可直接动工 | 读 `scripts/start_local_light.ps1` | ❌ **确认"较大重构"的判断成立**：轻量模式只起 `uvicorn api.server:app` + Vite，**根本不起 Verify worker**。因此只把 `api/routes/jobs.py` 的 `MySQLStore` 换成可插拔存储**不够**——任务会永远停在 QUEUED，等于造一个假控件。必须连"进程内执行器 + 进度通道"一起做，维持暂缓 |
| Docker 是否可用 | `docker info` | ❌ 守护进程未运行 → 本机**无法**验证 Node/Python 沙箱镜像，故本轮不碰 ④ 的镜像落地（只在文档标注） |

### 5.2 修掉一处真实的英文枚举泄漏（`Health` 整体状态）

`Health` 页「整体状态」指标卡原为 `data.status.toUpperCase()`，把 `/api/v1/health` 的 `ok`/`degraded` 直接喊成 **"OK" / "DEGRADED"**——与全站"英文枚举译中文、原文留 `title` 供审计"的约定（`verdictLabel`/`statusLabel`/`checkerLabel`/`evalVerdictLabel`…）不一致，也正是痛点#4"术语负担重"的典型。

- `ui/toneMap.ts` 新增 `healthStatusLabel()`：`ok→正常`、`degraded→降级`；**未知值原样透传**（绝不把没见过的状态说成"正常"）、**缺失→未知**。经 `ui/index.ts` 导出。
- `pages/Health.tsx` 改用它，原始值留在 `title`。
- 该页 `buildHealthCategories()` 的诚实语义（缺字段=未知、降级 reason 逐字）**完全未动**。
- 已验证：`ui/__tests__/toneMap.test.ts` 新增 3 例（两个已知值含大小写、未知透传且断言 `!== "正常"`、缺失→未知）。

### 5.3 Phase 3.3 第一片：把"术语解释"从独立页面搬到使用现场

**问题**：`需求矩阵 / 契约 / 风险发现 / 证据包 / 合并证书 / 开发助手` 只在「上手指南」页面解释过一次。用户在主流程遇到这些词时无处可查——要么离开当前页去翻指南，要么凭上下文猜。这是痛点#4 的根因，而 `Tooltip` 组件明明已经存在却只有样式预览页在用。

- **新增 `ui/glossary.ts`（全站唯一来源）**：`GLOSSARY` 8 条（原 6 条 + 新增 `preflight` 环境预检、`evidence` 证据），每条 `{ id, label, en, definition }`；`glossaryEntry(id)` 查不到返回 `undefined`。**不臆造**：未知 id 由 `<Term>` 原样透传 children。
- **新增 `ui/Term.tsx`**：`<Term id="capsule">证据包</Term>` —— 可见文案由各页自己决定（同一概念各页措辞可不同），悬浮/键盘聚焦时才展开定义与英文原名。复用已有 `Tooltip`（其 `cloneElement` 已自动补 `aria-describedby`，CSS 已支持 `:focus-within`），故**没有新造一套提示机制**。未知 id 直接渲染 children、不包壳。
- **`pages/Guide.tsx` 改为渲染共享术语表**：`<dl className="guide-glossary">{GLOSSARY.map(...)}` —— 指南与内联提示读同一份数据，**再也不会两边措辞漂移**（此前定义硬编码在 JSX 里，改一处忘一处）。顺带给"需求矩阵"补了一句"导航里的「需求覆盖」就是它"，把导航标签与术语接上。
- **落地位置（5 处主流程，覆盖用户第一次遇到这些词的地方）**：
  - `Matrix`（需求覆盖）：已提取**规则** → `contract`、缺少**证据** → `evidence`
  - `Contracts`（验收规则）：提取**契约** → `contract`
  - `NewVerification`（新建验证，用户最先看到的一页）：可追溯的**证据** → `evidence`、每条**验收条件** → `contract`、**风险发现** → `finding`
  - `JobDetail`：面板标题 **合并证书 / 拒绝通知** → `certificate`、**复现包下载** → `capsule`
  - `FindingDetail`：**复现包** 字段 → `capsule`、**证据来源** 面板 → `evidence`
- **顺带的小幅类型放宽（向后兼容）**：`ui/Panel.tsx` 的 `title: string` → `ReactNode`、`ui/util.tsx` 的 `kv(label: string, …)` → `label: ReactNode`，让面板/字段标题也能挂内联术语（与 `right?: ReactNode` 一致）。
- **样式**：`styles/base.css` 新增 `.ui-term` 一组——虚线可交互下划线 + `cursor: help` + `:focus-visible` 焦点环；并把基础 tooltip 的 `white-space: nowrap` 在 `.ui-term` 作用域内改为**可换行、`max-width: 300px`**（一句定义不能挤成一行）。基础 tooltip 保持原有单行紧凑形态不受影响。
- **已验证**：新增 `ui/__tests__/glossary.test.ts` 4 例（id 唯一且可反查、指南原有的 6 个 id 不得丢、label/definition 非空、未知 id 返回 `undefined`）与 `ui/__tests__/Term.test.tsx` 4 例（可见文案是调用方的、定义在 tooltip 里、`aria-describedby` + `role=tooltip` + `tabindex=0` 可键盘触达、英文原名呈现、**未知 id 原样透传且不产生 `.ui-term`/`.ui-tooltip`**）；`tsc --noEmit` 干净、`vite build` 通过、全量 vitest **39 文件 / 226 例全绿**。
- **诚实标注（未做）**：3.3 的另一半——"引导页关键步骤做成产品内 checklist（进度持久化）"——本轮未动，仍挂在 Phase 3.3。术语目前覆盖主流程 5 页，`Dashboard` / `Eval` / 团队与权限等页未挂（这些页本身不出现上述术语，属刻意不加）。

### 5.4 下一步（本轮校正后）

优先级不变，仅补两条已核实结论：

1. **Phase 3.3 收尾**：引导页 checklist（进度持久化）。纯前端、可离线验证，风险低。
2. **Phase 1.5 第二步**：`tests/unit` 引入 `slow` 标记并默认排除——**本轮实测再次确认该缺口真实**：`pytest tests/unit -m 'not integration'` 在本机跑了 7 分钟仍未结束（远超 Phase 1 定下的"60s 反馈"标准）。这是贡献者体验的硬伤，且完全可离线度量（改完前后各测一次墙钟时间即可作为证据）。
3. ~~**④ 4a 多语言差分**~~ ✅ 已落地（见 §6.7）：**"本机 Docker 未运行"这一判断已失效**——本轮实测 Docker 可用，Node 差分已改为容器沙箱执行并默认接线；Python 仍为宿主面、仍由 #50 的默认关开关兜住。
4. **Phase 1.6 轻量模式跑验收**：已确认"只换存储不够、必须连进程内执行器一起做"，维持暂缓。
5. ⑤ API 侧稳定降级错误码（跨栈契约变更）、⑥ 一键创建演示仓库（安全受限）——均维持暂缓。

## 6. 2026-09-23 会话：后端里程碑收口 + 一处真实潜伏缺陷

### 6.1 后端里程碑（语言感知预检 + 诚实非 Java 差分降级 + Node adapter + 沙箱参数化 + 轻量模式 503）

本会话把 `agent/`、`api/`、`evidence/`、`experiments/`、`sandbox/`、`cli/`、`scripts/` 及对应单测的改动作为一个后端里程碑提交推送。要点已在 §4/§5 记档：`run_preflight` 语言感知节点接入、非 Java 项目差分诚实降级为 UNVERIFIED（而非模糊英文）、Node adapter、`SandboxProfile` 参数化、light-mode 友好 503（去掉 `{exc}` 原文外泄）。安全红线复核：`api/routes/jobs.py` 的 `JOB_CREATE_ALLOWLIST` 未动，`run_differential` 仅在存在 Java 生成测试类时经 `registry.get` 执行（Node/Py local-first adapter 从未被生产差分触达）。

> **⚠ 本段末句已被 §6.7 取代**：自 #54 起 Node 差分默认经容器沙箱执行，"适配器从未被生产差分触达"不再成立，也不再是安全前提；现在的安全前提是 `EXECUTION_SURFACE` 显式声明 + 宿主面适配器在门关闭时 `prepare`/`run` 零调用（单测锁定）。`JOB_CREATE_ALLOWLIST` 仍未改动。

### 6.2 潜伏缺陷修复：`MinIOClient.list_job_objects` 此前根本不存在（可验证，非臆造）

- **现象**：仓库自带的 `mypy .` CI 门（`.github/workflows/ci.yml`）在我接手时其实是**红的**——唯一一处错误 `ops/data_lifecycle.py:128: "MinIOClient" has no attribute "list_job_objects"`。
- **根因**：数据生命周期删除报告调用 `minio.list_job_objects(job_id)`，但真实 `MinIOClient` **从未实现**该方法。`tests/unit/test_data_lifecycle.py` 用 `monkeypatch` 换上一个**自带该方法**的 `FakeMinIO`，于是单测**永远掩盖**了这个洞：真实客户端在运行时走到那一步会抛 `AttributeError`，被外层 `except` 吞掉、把 minio 步骤永久记成 `ok:False` —— 也就是说**生产里这一"列证据供人工确认"的步骤从来没有真正列出过任何东西**，且没人发现。这正是"问题很大"的一个典型样本：门是红的、测试是绿的、缺陷是潜伏的。
- **修复**：`storage/minio.py::list_job_objects` 落地真实现——按治理路径 `tenant/repo/job/type/version` 用**校验过的单段**（复用 `validate_path_segment`，`".."`/`"/"`/空格在触达客户端前即拒）跨三桶过滤出该 job 的对象，返回 `bucket/object-name` 字符串；**单个桶不可达只跳过、绝不清零其它桶已发现的证据**。新增 `test_list_job_objects_filters_by_job_segment_and_guards_traversal`（真客户端、桶感知假件），锁定三件事：只命中目标 job 段、不可达桶被跳过而不抹掉别处证据、越界 job id 抛 `InvalidObjectPathError`。
- **门证**：`mypy .` 由 1 错转**全绿（209 文件）**；`ruff` 干净；`test_storage_governance.py + test_data_lifecycle.py` 共 **34 passed**。

### 6.3 下一步（本轮新增候选）

1. ~~**Phase 1.5 第二步**~~ ✅ 已落地（见 §6.6）：`slow` 标记已引入并实测提速。**但"默认排除"这一条被实测否决**——CI 合并门裸跑 `tests/unit`，默认排除会让 275 例覆盖静默消失；最终形态是**贡献者 opt-in 快速路径**。
2. ~~**Recall/Precision 可执行量化门**（任务 #51）~~ ✅ 已落地（见 §6.4）。
3. ~~**默认关闭的本地测试执行差分门**（任务 #50，红线合规路径 ii）~~ ✅ 已落地（见 §6.5）。
4. **同类"潜伏缺陷"扫查**：本轮暴露了一种失败模式——**假件自带真实实现没有的方法 ⇒ 单测绿、生产红、静态门红**。值得专门排查其余 `ops/`、报告/删除类路径里对存储客户端的调用是否都有真实实现兜底。（注：`mypy .` 现已全仓库绿，这一扫查的边际价值已大幅下降。）
5. ~~**多语言差分的真正沙箱（路径 i）**~~ **Node 半边已落地**（见 §6.7）：Node 现声明容器沙箱执行面并默认接线。**Python 半边仍待做**——`PythonAdapter` 仍为宿主面，#50 的默认关开关对它仍然有效；给 Python 建等价沙箱的难点不是镜像，而是"复用项目 `.venv`"这一离线策略在容器里不成立（venv 绑定宿主绝对路径与解释器），需先设计容器内的依赖落地方式。
6. ~~**#55 的遗留项：`execution_surface` 未透出**~~ ✅ 已落地（见 §7）——此前 `execution_surface` 产出后在**合并层被静默丢弃**（`_merge_group` 用固定键字典拼行），用户看不到"这次差分有没有沙箱"。现已四层贯通到需求覆盖页，合并取**最不安全的一个**（宿主 > 未确认 > 沙箱）。
7. **Node 差分的实际覆盖面**（任务 #56，§6.7 实测暴露）：需要 Node 版离线依赖卷（对应 Maven 的 `scripts/seed_sandbox_cache.ps1`），否则装依赖的仓库仍 `NON_REPRODUCIBLE`。**需 Docker 在线窗口。**

### 6.4 Recall/Precision 可执行量化验收门（任务 #51，本轮落地）

- **要消灭的真实缺陷**：评测指标此前在**样本分母为 0**时会算出**伪满分 100%**（`detected/(detected+fp)`、`detected/should_detect`、`f1` 三处空集兜底都返回 `100.0`）。一个"没有任何正样本"的评测集会显示 Recall=100%、且能**通过**任意 `--min-recall` 下限——门越小越"绿"，这是可被"缩小评测集"作弊的假门，也正是"问题很大"的又一例。
- **单一来源纯模块 `evidence/acceptance.py`**：`MetricCounts`→`score()` 产出 `float | None` 指标（分母为 0 ⇒ `None`=无法评估，**绝不用 0.0 冒充、也绝不用 100 冒充**；`f1` 只有在 recall 与 precision 都有定义时才有定义）；`AcceptanceCriteria` + `evaluate()` 先做**样本充分性**判定（正/负样本数不足下限 ⇒ `INSUFFICIENT`，早于任何数值门），再做数值门 ⇒ `PASS`/`FAIL`；`fmt_metric(None)` 渲染为"无法评估 (n=0)"。默认 `AcceptanceCriteria.default()` **钉死样本下限（正≥10、负≥5）但不钉死任何数值下限**（诚实：仓库当前无足够真实数据支撑一个具体 Recall 阈值）。
- **接线**：`cli/specproof/commands/eval.py` 用共享打分器替换内联公式，新增 `--gate`（非 PASS 即 `SystemExit(1)`，可进 CI）与 `--min-recall/--min-precision/--min-f1/--min-positive-cases/--min-negative-cases` 选项，并统计 `negative_cases`；sidecar JSON 现把三指标写为**可空**、附 `acceptance` 块。`evidence/report.py` 的 HTML 统计卡改走 `fmt_metric`（`None`→"样本不足"，不再 `:.0f}%` 伪满分）。`cli/specproof/commands/baseline.py` 的 `summarize` 委托 `score()`、`_opt_float/_delta_pp/_pp_or_dash` 让基线对比在指标未定义时诚实显示"无法判定"，而非用 `float(None or 0)` 造出假的 +pp 判定。
- **端到端诚实**：`/api/v1/eval/latest` 原样透传 sidecar，`apps/web/src/api.ts` 的 `EvalData.report` 三指标类型改 `number | null` 并补 `negative_cases/acceptance`（契约与现实一致）；`Eval.tsx` 的 `!= null` 兜底已把 `null` 渲染为"—"。新增前端锁：空样本集下三张统计卡显示"—"、且页面**不出现**"100.0%"。
- **门证**：`ruff` 干净；`mypy .` 全绿（210 文件）；`tests/unit/test_acceptance_gate.py`（12 例，锁定伪满分回归、`None` vs `0.0` 之分、空/小集判 `INSUFFICIENT` 而非 `PASS`、下限 PASS/FAIL、默认仅样本门、`to_dict` JSON 安全）+ `test_baseline.py` 共 **43 passed**；`apps/web` `tsc --noEmit` 干净、`Eval.test.tsx` **6 passed**。
- **意义**：这是退出标准里"量化 Recall/Precision 门"的一项从**纸面**变成**可执行、不可被缩小评测集绕过**的实门。

### 6.5 默认关闭的本机自测差分门（任务 #50，本轮落地，红线合规路径 ii）

- **背景**：#34 已落地纯函数地基（`self_test_execution_allowed()` 门策略 + `self_test_verdict()` 判定），但**故意不接线**——因为 Node/Python 的 `ExecutionAdapter` 是 local-first（宿主执行、无容器沙箱），直接接线会在宿主上跑未信任的 PR 自带测试，正面撞 `api/routes/jobs.py` 的"验收 API 绝不能变成远程执行面"红线。本轮按路径 (ii) 完成受控接线。
- **接线（默认关，绝不在默认流水线执行宿主测试）**：`agent/nodes/run_differential.py` 在"非 Java 且无生成测试"分支里，**先查 `self_test_execution_allowed()`**；仅当运维显式 `SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1` 时，才经 `_run_self_tests_on_workspace`（detect→prepare→run）在 Base/Head 跑仓库自带测试、按语言选对应 summary 解析器、用 `self_test_verdict` 出判定；否则保留原诚实 UNVERIFIED 降级，并在文案里点明"默认关闭 + 如何显式开启"。**门关闭时适配器一次都不会被构造**——这是被单测锁死的安全不变式。
- **诚实透出**：自测差分结果带 `evidence_type=self_test_diff` 与 `execution_surface`（local adapter ⇒ `local_host_no_sandbox`），detail 前缀"⚠ 本机执行·无沙箱"；任何一侧适配器缺失/崩溃/零测试汇总都判 `NON_REPRODUCIBLE`，**绝不当作通过**。前端 `toneMap.ts::EVIDENCE_CN` 给 `self_test_diff` 加了诚实中文标签"仓库自带测试差分（本机执行·无沙箱）"（保留原始 token），FindingDetail/JobDetail 的证据方式列据此诚实标注。
- **门证**：`test_differential_language_honesty.py` 新增 4 例（默认关⇒`registry.get_calls==0` 且不执行；开⇒base green/head fail⇒REGRESSION+本机无沙箱标签；开⇒空汇总⇒NON_REPRODUCIBLE 非 pass；开⇒无适配器⇒诚实降级）；连同 #34 的 `test_self_test_diff.py` 纯函数 23 例，共 **30 passed**。既有非 Java 诚实降级 3 例不回归。`ruff check .` 干净、`mypy .` 全绿（210 文件）；前端 `tsc` 干净、`toneMap`+`FindingDetail`+`JobDetail` **36 passed**。
- **仍未做（诚实边界）**：本轮是**路径 (ii) 默认关开关**，不是真正的 Node/Python **沙箱**（路径 i）。要默认安全地跑多语言差分，仍需 roadmap ④ 的 Node/Python 容器镜像；在那之前开启此门仍属"运维知情同意的宿主执行"。

> **⚠ 本段三处已被 §6.7 取代，阅读时请注意**：(1) "门关闭时适配器一次都不会被构造"——现已**不再成立**（判定执行面需要构造适配器，但它不执行任何代码），不变式已改述为"宿主面适配器在门关闭时 `prepare`/`run` 调用数为 0"；(2) "local adapter ⇒ `local_host_no_sandbox`"——现在只有真的在宿主跑完才是这个值，跑了但没跑成 ⇒ `unconfirmed`；(3) 前端标签"仓库自带测试差分（本机执行·无沙箱）"——**已删去执行面断言**（对沙箱执行是谎话）。本节其余结论（默认关、NON_REPRODUCIBLE 不粉饰）**依然有效**，只是适用范围从"Node+Python"缩到"仅宿主面语言（当前 Python）"。

### 6.6 单测快速内循环落地 + 两处计时假红根治（任务 #53，本轮落地）

- **要消灭的真实缺陷**：Phase 1 定的"60s 内反馈"一直是纸面——§5.4 实测 `pytest tests/unit -m 'not integration'` 跑 7 分钟未完。"改一行等 16 分钟"是贡献者体验的头号硬伤，也是"不好用"的一部分。
- **不猜、先量**：用 `pytest --durations=0` 真跑一次全量 unit（**970.06s / 2581 passed**，另有 1008s、1136s 两次历史样本），按模块聚合后得到一条清晰结论：慢不是均匀分布的，而是**一簇约 700s 的"完整 agent 运行时 / 多步 LLM 循环 / benchmark 模拟"模块**（头部：`test_craft_loop_metrics.py` 83.1s、`test_craft_loop_jobs.py` 69.9s、`test_agent_runtime.py` 65.0s）。顺带纠正了一个臆测：**名字里带 bench/offline/mock 的模块大多其实很快**，不能凭名字打标。最终 `SLOW_TEST_MODULES` 取 **21 个实测模块**（`tests/conftest.py`，按文件名自动打标，无需逐个装饰）。
- **设计纠正（拒绝"默认排除"）**：原计划写"引入 `slow` 标记并**默认排除**"。实做时**否决**了这条——CI 合并门是 `.github/workflows/ci.yml:71` 的裸跑 `python -m pytest tests/unit tests/security tests/fault -q`（无 `-m` 过滤）。若把 deselect 塞进 `addopts`，那 **275 例覆盖会从合并门静默消失**：用"更快"换掉"门是真的"，不可接受。故最终形态是**贡献者显式 opt-in 的快速路径**，CI 一字未改。
- **实测前后对比（同机、同样有并发负载）**：
  | 路径 | 命令 | 结果 |
  | --- | --- | --- |
  | 全量 unit（改前） | `pytest tests/unit` | 2581 passed · **970.06s (16:10)** |
  | 快速内循环（改后） | `pytest tests/unit -m "not integration and not slow"` | 2308 passed, 1 skipped, 277 deselected · **176.78s (2:56)** |
  | 同路径另两次采样 | 同上 | 239.73s / 202.99s |
  即约 **4–5.5 倍**提速，**绝不是**当初承诺的"60s 内"。诚实记录：**Phase 1 的"60s 反馈"目标未达成**，本轮达成的是"3–4 分钟可用内循环"；要进一步到 60s 需要并行化，而本机未装 `pytest-xdist`，且这些模块大量使用线程/临时端口/临时文件，**盲目 -n auto 会把真红变成假绿**——故未做，留作待评估项。
- **顺手根治两处计时假红（这是本轮真正的产品价值）**：快速路径改完头两次各带 **1 个 failed**，且**每次是不同的测试**（一次 `test_dashboard_performance`、一次 `test_provider_accounting`），单独跑均绿——这是负载争用的签名，不是回归。但"快速内循环默认红"比"慢"更毒：它会训练贡献者忽略红灯。根因两处：
  - `test_health_times_out_and_closes_clients_when_probes_finish` 把探针预算 `monkeypatch` 成 **0.02s** 只为省时间——于是忙机上**连"立即就绪"的 mock 都会超预算**，打破 `checks["redis"]["ok"] is True`。修法：慢探针改为阻塞在"断言之后才 release"的事件上 ⇒ 它超过**任何**有限预算，从而允许把 patched 预算放宽到 2.0s；契约（"永不返回的探针被判超时 + 客户端仍被 close"）一字未松，只是不再拿 20ms 去赌调度。
  - `test_cancelling_model_call_stops_pending_request` 的 `thread.join(10)`/`finished.wait(10)` 在全套件争抢 CPU 时会不够。修法：上限 10s→30s，并把"被测契约是 cancel() 最终能解开调用线程，不是 10 秒内"写进注释；断言补了失败消息。**没有**改成"跳过"或删断言。
- **回归锁**：新增 `tests/unit/test_slow_marker_tagging.py`（2 例，**离线、只 `--collect-only`**）——已知慢模块必须真带上 `slow`、已知快模块（`test_baseline.py`）必须**不**带上（否则打标是扫射，快速路径就在说谎）、且用 `--strict-markers` 证明标记已注册。**过程中踩到一个真实陷阱**：仓库 `addopts = "-v --tb=short"` 会抵消命令行的 `-q`，使 `--collect-only` 输出树而非 node id；探针须 `-o addopts=` 清空才能读到选定集，同时容忍 exit 5（零选定是快模块的**预期**结果）。
- **门证**：`ruff check` 干净；快速路径 **2308 passed / 1 skipped / 176.78s**；受影响模块单独复跑 17 passed。CI 的 `ci.yml` 与慢标记的关系不变（裸跑⇒慢例照进合并门）。`README.md` §开发与运维 补了快速命令，并明确写"它只是开发便利，不是新的验收标准"。

### 6.7 Node 仓库自带测试差分进入真实 Docker 沙箱（任务 #54，本轮落地，红线合规路径 i）

- **要消灭的真实缺陷**：§6.5 的"默认关开关"只是路径 (ii)——开了门就在**宿主**上跑不受信的 PR 自带测试，属于"运维知情同意的越界"，不是能力。§5.4 当时记录的阻塞理由是"**本机 Docker 未运行**"。本轮先复核这条前提：Docker 守护进程在线，`node:22-alpine` 可拉——**该理由已失效**，于是按路径 (i) 真正建沙箱。
- **执行面成为唯一判据（核心设计）**：新增 `experiments/adapters.py::EXECUTION_SURFACE`（每个适配器显式声明 `SURFACE_DOCKER_SANDBOX` 或 `SURFACE_HOST`），配 `execution_surface_of()` / `runs_in_sandbox()`。判定**fail-closed**：适配器忘记声明 ⇒ `host` ⇒ 默认不执行。`run_differential` 的非 Java 分支由此变成 `if sandboxed or self_test_execution_allowed():`——**沙箱面适配器无需任何开关即可默认执行**，宿主面仍要显式开关。安全不变式随之从"门关闭时适配器一次都不构造"（判定执行面本身需要构造适配器并 detect，旧锁在逻辑上无法保留）改述为**"宿主面适配器在门关闭时 `prepare`/`run` 调用计数为 0"**，并由计数器锁死而非靠观察（`test_gate_off_host_adapter_is_never_executed` 断言 `get_calls==1`、`prepare_calls==run_calls==0`）。
- **诚实的三态执行面标签**：结果里的 `execution_surface` 只从**已完成的运行**取值——两侧 `mode` 均为 `docker` ⇒ `docker_sandbox`（"容器沙箱执行 (非 root uid 1000 · --network none · 源码只读)"）；任一 `mode` 含 `local` ⇒ `local_host_no_sandbox`；否则 ⇒ **`unconfirmed`**（"执行面未确认"）。这堵住了一个真实的谎：此前"声明了沙箱但进程崩了"会被报成 `docker_sandbox`。`test_surface_label_comes_from_the_run_not_the_declaration`（`mode=""` ⇒ `unconfirmed`）锁住它。
- **顺手修掉一处会让整条新链路永久失能的潜伏缺陷**：`_self_test_parse_for()` 原来用**精确相等**比较语言，而适配器 `detect()` 返回的是 `"javascript/typescript"`，常量却是 `"node"` ⇒ Node 运行的 TAP 汇总会被喂给 **Surefire** 解析器，于是沙箱即便真跑成功也永远输出"无证据"。修复为按 `_LANGUAGE_ALIASES` 归一（node/javascript/typescript、python/pip/pytest、java/maven/junit 各自映射到对应解析器）。**验证方式不是"看起来对"**：把 `==` 临时改回去重跑，**恰好 4 例**红（`test_sandboxed_adapter_runs_the_self_test_with_the_gate_off`、`test_self_test_gate_on_computes_honest_regression`、`test_self_test_parser_covers_both_vocabularies`、`test_real_node_profile_language_parses_a_real_tap_summary`），恢复后全绿——证明这些锁真的在守护这条路径。测试假件的 `detect()` 也刻意返回适配器词汇 `"javascript/typescript"` 而非 `"node"`，以免假件再次掩盖真缺陷（§6.2 记录的同一种失败模式）。
- **真实 Docker 实测（不是纸面声明）**：临时 Node 仓库、`npm test` 走 node:test。绿跑 3/3 通过 exit 0；把实现改坏后 2/1 exit 1。容器内 `id -u` = 1000，`--network none`，`/work` 只读。**但这条实测同时暴露了自己的代表性边界**（见下条），不能拿它当"Node 仓库已可验收"的证据。捕获的实际 `docker run` argv 已逐字写入 `docs/architecture/EXECUTION_COMPATIBILITY.md` §验证记录（修掉了文档初稿里两处凭记忆的错误：`no_new_privileges` 应为 `--security-opt no-new-privileges`，以及漏记 `-e npm_config_update_notifier=false`）。`NodeAdapter.IMAGE`/`IMAGE_DIGEST` 提升为常量并回填矩阵文档，`test_adapter_declarations_match_matrix_doc` 现在同时锁 image、digest、以及"Node 行不得再出现 `local-first`"。
- **提交前自审抓到的过度声明（本轮最重要的一个修正）**：README 的按语言表最初写"JavaScript/TypeScript ⇒ 是（npm test）"，这**夸大了实际覆盖面**。三条已核实事实在一起：(a) `prepare_base/head` 用 `git worktree add --detach` 检出（`docs/architecture/ARCHITECTURE.md` §3），worktree **不带未跟踪文件** ⇒ 仓库的 `node_modules` 不在工作区；(b) 沙箱 `--network none` ⇒ 装不了依赖；(c) `NodeAdapter.KNOWN_LIMITS` 明确"不安装依赖"。合起来的结论是：**当前真能跑的只有零依赖的 `node:test` 项目**，用 Jest/Vitest 的真实仓库会 `Cannot find module` → 非零退出 → `NON_REPRODUCIBLE`（判定上诚实，但等于能力够不到用户）。已把这条写进 README 表格单元、`EXECUTION_COMPATIBILITY.md` 的"实际覆盖面（诚实边界）"段与 Node 行 known-limits、以及 `NodeAdapter.KNOWN_LIMITS`，并登记为任务 **#56（Node 版离线依赖卷，对应 Maven 的 `scripts/seed_sandbox_cache.ps1`）**。教训：**一次成功的端到端冒烟只证明"那条路径通了"，不证明"它覆盖用户的仓库"——实测样本的形态必须和被声称覆盖面一致，否则就是在给自己发假证书。**
- **文档一致性收口（把已被取代的话标出来，而不是悄悄删）**：`README.md` 的能力段改为**按语言的执行面表**（Java=沙箱 / JS-TS=`node:22-alpine` 沙箱 / Python=默认否 + 需显式开关 + 诚实标注"本机执行·无沙箱"），并明确"未在无沙箱宿主上执行不受信仓库测试是安全红线，因此表中的『默认否』是设计而非缺陷"。`EXECUTION_COMPATIBILITY.md` 新增"执行面决定能否默认跑仓库自带测试"策略段；§接线现状里"适配器从未被生产差分触达"这句话**已标注为不再成立**。`RUNBOOK.md` §5 补 `node:22-alpine` 预拉指引，并说明**镜像缺失 ⇒ 执行面判为 host ⇒ 默认不执行，绝不静默回退宿主**。
- **前端去谎**：`toneMap.ts::EVIDENCE_CN` 的 `self_test_diff` 标签从"仓库自带测试差分（本机执行·无沙箱）"改为中性的"仓库自带测试差分"（保留英文 token）——旧标签对沙箱执行是**错的**。执行面中文释义**没有**在本轮加入：API 目前不把 `execution_surface` 作为字段透出，加了就是无消费者的死代码，已归入任务 #55。
- **门证**：`ruff check .` 干净；`mypy .` 全绿（210 文件）；`apps/web` `tsc --noEmit` 干净、`vitest run` **39 文件 / 230 用例全绿**、`vite build` 成功；定向 `test_adapters.py + test_python_adapter.py + test_node_adapter.py + test_differential_language_honesty.py` **85 passed / 2 skipped**；`test_differential_language_honesty.py` 重写为 **14 例 / 2.2s** 全离线（沙箱路径用假适配器，真 Docker 只在实测记录里出现，不进 CI）。
- **仍未做（诚实边界）**：(0) **Node 差分的实际覆盖面窄于"支持 JS/TS"**——缺 Node 版离线依赖卷，需装依赖的仓库仍判 `NON_REPRODUCIBLE`（任务 #56，是本轮实测暴露的、原先没列进计划的新缺陷）；(1) **Python 沙箱未建**——项目的 `.venv` 绑定宿主绝对路径与解释器，Maven 那套"命名缓存卷 + 离线策略"无法照搬进容器，需要单独设计（任务 #26）；(2) 差分证据**基本到不了 UI**（`review_court.py:187-189` 只提升 REGRESSION/AMBIGUOUS、`build_matrix.py` 丢弃未编译的 `DIFF-01`；更彻底的是——`storage/mysql.py:1073-1081` 的 `insert_contract` 列清单里**根本没有** base/head/attribution 列，`api/routes/web.py:362-366` 只 SELECT 那 6 列，`apps/web/src` 对 `base_result`/`head_result`/`attribution` **零引用**）——本轮修的是"能不能安全地跑"，不是"跑完看不看得到"（任务 #55）。

### 6.8 需求覆盖矩阵从"演示专用"变成真实任务的逐条证据（任务 #55，本轮落地）

- **要消灭的真实缺陷（比 §6.7 记录的更严重）**：`grep -rn "\.insert_contract(\|\.insert_finding(" 全仓` 只有一个生产调用点——`scripts/seed_demo.py:394/403`。也就是说 `/api/v1/jobs/{id}/matrix` 读取的 `contracts` 表**只被演示种子写过**；真实验收任务在 worker 侧只落 `save_job_summary`（`agent/worker.py:180`），而 `_state_summary` 当年只塞了 `matrix_passed/failed/unverified` 三个**计数**。结论：对任何真跑过的任务，"需求覆盖"页计数说 3 条通过、表格却空空如也，页面还理直气壮地写"这次验证尚无逐条结果"。差分归因（`attribution`/`base_result`/`head_result`）在 `apps/web/src` 里**零引用**，因为它们从没到过前端。
- **为什么选"随摘要走"而不是"给表加列"**：另一条路是给 `contracts` 表加差分列 + 迁移 + 让 worker 写表。但 `infra/mysql/migrations/0003_job_summary.sql` 把 `summary` 定义成 **`JSON NULL`**，容量不是问题，而且仓库里**已经有一个完全同形的正确设计**——`/jobs/{id}/findings` 就是"表格行 + 摘要行"按 id 合并并如实标注来源（`api/routes/web.py:417-471`）。于是复用该模式：零迁移、CLI/轻量模式同样受益（它们没有这张表可写）、并且不新增任何能伪造判定的写路径。
- **落点**：`agent/worker.py` 新增 `_matrix_rows_for_summary()`，把 `state["matrix"]["rows"]` 投影成固定 15 个键（含 `attribution`/`base_result`/`head_result`/`unverified_reason`/`next_action`），**按 60 行封顶且封顶时如实报告**（`matrix_rows_total` / `matrix_rows_truncated`），长文本截到 400 字符。`api/routes/web.py::job_matrix` 改为双源合并：**摘要行是判定的唯一权威**，表格行只能补它没有的描述字段（`expected_behavior` 等），**永远不能覆盖 `result`**；未观测的字段保持"缺席"而不是 `null`，因为页面要区分"没做差分实验"和"某侧有判定"。响应新增 `sources` / `counts_source` / `rows_total` / `rows_truncated`。
- **诚实细节**：行数被截断时，`counts` 改取管线自己算的总数（`counts_source="pipeline_summary"`），否则"只显示 1 行"会把"共 20 条"报成 1 条——用展示条数冒充统计量是新造的假红。前端 `Matrix.tsx` 新增"改前 / 改后对照"列（`PASS → FAIL` 各自带 tone，归因走新加的 `toneMap.ts::attributionLabel()`，"中文 · 原 token"、未知值原样透传），无差分数据的行显示**"未做改前/改后差分实验"**而不是破折号（破折号会被读成"看过但没问题"）；并新增"计数与逐条自相矛盾"的空态文案，替换掉原来那句在这种情况下是假话的"这次验证尚无逐条结果"。
- **顺手纠正一处契约谎报**：`api/routes/jobs.py:226` 的 docstring 一直写着摘要含 `(matrix/findings/capsules)`，而 `matrix` 在改动前**根本不在**摘要里——现在这句话第一次为真。
- **反向验证（防止"测试绿但门是假的"）**：三层变异各跑一次并还原——(1) 让 `_matrix_rows_for_summary` 直接返回空 ⇒ **8 例红**；(2) 让 `job_matrix` 忽略摘要行 ⇒ 3 例红，而合并权威那一例**没红**，因为它的名字不含 `matrix` 被 `-k matrix` 静默剔除（**"我的筛选条件刚好把它排除了"也是一种假绿**），遂改名 `test_matrix_summary_verdict_wins_over_a_disagreeing_table_row`；(3) 把合并方向改成"表格覆盖摘要" ⇒ 改名后该例**如期独红**。另有一处生产缺陷是新测试自己抓出来的：空白 `contract_id`（`"  "`）能穿过投影，改为 strip 判定。
- **最强的一条锁是本轮补的：往返锁，不是两侧各自的锁。** 生产端与消费端各测各的时，任何一处键名笔误都能"双双绿"——worker 写 `contract_id`/`base_result`，端点把它改名成 `contract_id_str`/…，两边单测互不相干。新增 `test_matrix_round_trips_from_the_worker_summary`：直接把真实 `_state_summary(...)` 的输出塞进假存储，再走 `/jobs/{id}/matrix` 读出，逐字段断言 `base_result`/`head_result`/`attribution` 真的到了 API。这才是"用户看得见"的等价断言。
- **门证**：`ruff check .` 干净；`mypy .` 全绿（210 文件）；`tests/unit/test_summary_matrix_rows.py`（新增文件，9 例）+ `tests/unit/test_web_api.py`（新增 6 例矩阵用例，含往返锁）共 **50 passed**；`apps/web` `tsc --noEmit` 干净、`vitest run` **39 文件 / 240 用例**（+10）、`vite build` 成功。
- **全量合并门（1984s / 2776 passed / 1 failed）与一个非本轮引入的真实竞态**：唯一红是 `test_agent_runtime.py::test_create_auto_start_then_poll_get_to_terminal`，且失败点是 `assert job.accept_json is not None` **而不是超时**——单独跑 43s 通过，故这是**顺序竞态**而非计时余量不足。读 `api/agent_runtime.py` 尾部证实：存储行进入终态 → 写 `change-bundle.json`（真文件 I/O）→ 发终态 SSE 事件 → **最后**才 `persist_accept_result`（`craft/accept.py:126`）。于是存在一段"succeeded 但验收投影还没落库"的可观察窗口，空闲机上亚秒级、争用时被拉长到能被观测——**这正是"慢机器上偶发红灯"背后的真问题**，与 §6.6 修掉的两处计时假红同类但成因不同。处理：测试改为**按运行时文档化的顺序**在同样的 180s 预算内等待验收落库（状态与 `accept_json` 两个断言一个都不放宽，`test_agent_runtime.py` 11 passed），并把"是否该把 attach 提到终态事件之前"作为产品决策登记为任务 **#57**（本轮不擅自改 Craft 运行时时序）。
- **提交后终树复跑（无并发争用）**：`pytest tests/unit tests/security tests/fault -q` ⇒ **2778 passed / 5 skipped，1029.44s (17:09)，exit 0 全绿**（含等待验收投影的那条竞态用例）。同一门在本轮内的三次耗时是 1417s → 1984s → 1029s，用例数还从 2763 涨到 2778——**慢的主因是争用而不是代码**，这把 §6.6 的结论又确认了一次（那轮测的是 `tests/unit` 单独口径的 970s，与此处三门合并口径不可直接比较）。

## 7. 2026-09-24 会话：把"执行面"披露补完（任务 #55 的遗留项）

### 7.1 状态核实（先查证再动工）

| 核实项 | 方法 | 结论 |
|---|---|---|
| 工作区是否干净 | `git status --short` + `git diff --numstat` | **本会话开工时**：429 个 "M" 全是 **LF/CRLF 行尾元数据**（`numstat` 全为 `0 0`），唯一真实内容改动是 `docs/eval/aider-results.md` 一行；**上轮改动已提交**（`51e408f feat(web): 高频页中文化/诚实性收口 FE-1..FE-13`）。（本节写作时该数字已随本轮改动增长，故结论只描述开工那一刻，不适用于读它时的树。） |
| Docker 是否可用 | `docker info` | ❌ 守护进程未运行 ⇒ **任务 #56（Node 离线依赖卷）与 #26（Python 沙箱）本轮仍不可做**（§6.7 当时在线，现已离线） |
| §6.6 的 `slow` 快速路径是否真的存在 | 读 `tests/conftest.py::SLOW_TEST_MODULES` + `tests/unit/test_slow_marker_tagging.py` | ✅ 存在且**有回归锁**（已知慢模块必须带 `slow`、已知快模块必须不带） |
| §6.5/#50 的门是否真的默认关 | `grep self_test_execution_allowed` | ✅ 在 `run_differential` 非 Java 分支里按声明执行面 + 显式开关判定 |

### 7.2 要消灭的真实缺陷（两个：主目标 + 顺带挖出的同族缺陷）

**缺陷 A：跑了宿主测试，却没人告诉你**

**背景**：§6.5 与 §6.7 一起确立了——**宿主面适配器（当前是 Python）会在你的机器上直接跑不受信变更自带的测试**，需要 `SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1` 才放行；沙箱面（Java、Node）则关在容器里。这条是产品的安全承诺。

**缺陷**：`run_differential` 确实产出了 `execution_surface`（三态：`docker_sandbox` / `local_host_no_sandbox` / `unconfirmed`），但**它死在半路上**：

1. `agent/nodes/build_matrix.py` 构造 diff 条目时**没有带上**这个字段；
2. 更隐蔽的是——即便带上了，`agent/matrix_policy.py::_merge_group` 的行是**用固定键字典字面量拼出来的**，不认识的键会被**静默丢弃**（这是本轮最重要的发现：改完第 1 处后测试仍然不会红，因为丢在了合并层）；
3. `agent/worker.py::_SUMMARY_MATRIX_ROW_KEYS` 的 15 个键里没有它；
4. `apps/web/src` 对 `execution_surface` **零引用**。

结果：用户看到"仓库自带测试差分 → REGRESSION"，却**无法知道这次运行有没有沙箱**——即无法知道自己有没有被暴露。§6.7 把这条记为"已归入任务 #55"，但 §6.8（#55 的落地）只交付了矩阵归因，**没有交付执行面**，所以它一直悬着。

### 7.3 落点（四层一起改，缺一层就等于没做）

- **`agent/nodes/build_matrix.py`**：diff 条目带上 `execution_surface`（空值不带，保持"未观测即缺席"）。
- **`agent/matrix_policy.py`**：新增 `_merged_execution_surface(group)`，并把 `execution_surface` 提升为**规范字段**（`CANONICAL_FIELDS`，紧随 `attribution`）。合并规则**fail-closed**：
  - 全组都没有 ⇒ 返回 `""`（"没做差分实验"必须与"在沙箱里跑过"可区分）；
  - 取值**最不安全的一个**：`local_host_no_sandbox` > `unconfirmed` > `docker_sandbox`。理由：一条宿主运行就意味着代码真的在你的机器上跑过，用同组另一条沙箱证据把它盖过去是**假保证**；
  - 认不出的取值按字典序取第一个并**原样透传**（确定性，保持纯函数；绝不四舍五入成"安全"）。
- **`agent/worker.py`**：`_SUMMARY_MATRIX_ROW_KEYS` 加入该字段，随摘要落库。
- **`apps/web/src`**：
  - `api.ts::MatrixRow` 补 `execution_surface?: string`（注释写明这是安全披露，未知值必须原样显示）；
  - `toneMap.ts` 新增 `executionSurfaceLabel()`（三态中文 + 保留原 token，未知透传，**缺失返回空串**——不是"容器沙箱执行"）与 `executionSurfaceTone()`（只有 `docker_sandbox` 给 `ok`，宿主与"未确认"都给 `warn`，与后端 fail-closed 一致）；
  - `Matrix.tsx` 在"改前/改后对照"单元格里加一行徽标，`title` 保留原 token；`quality.css` 新增 `.quality-execution-surface` 三档配色（**始终是可见文字，不靠颜色单独表意**，无沙箱给警示色）。

### 7.4 反向验证（三个变异探针，最后在终树上重新测过一遍）

**探针 A — 把披露埋在合并层**：删掉 `_merge_group` 里那行 `"execution_surface": ...` 重跑
`tests/unit/test_matrix_policy.py + test_matrix_pure.py + test_summary_matrix_rows.py + test_web_api.py`
⇒ **9 例红**（`9 failed, 81 passed`）：
`test_execution_surface_is_empty_when_no_differential_ran`、
`..._reports_the_least_safe_run`、`..._treats_an_unattributable_run_as_unsafe`、
`..._passes_an_unknown_value_through`、`..._is_blank_not_missing_on_every_row`、
`test_report_shows_the_differential_and_where_it_ran`（HTML 报告侧）、
`test_execution_surface_reaches_the_row_from_a_diff_result`（节点侧），
外加两条字段完整性锁（`test_every_row_carries_all_canonical_fields`、
`test_every_row_carries_complete_field_set`）。恢复后全绿。
**说明这些锁真的在守护这条链路**，而不是"测试绿但门是假的"。
（本小节前一版写的是 8 例——那是加报告锁之前的测量；终树重测为 9 例，数字以本节为准。）

**探针 B — 把 §7.7 的修法退回去**：让 `_merged_side_verdict` 无条件走 `_merge_verdict`
⇒ **4 例红**（`4 failed, 86 passed`）：
`test_contract_without_any_experiment_is_unverified_with_reason`（就是那条"既有断言编码了错误假设"）、
`test_report_says_not_run_instead_of_implying_a_pass`、
`test_no_differential_leaves_both_sides_empty_not_unverified`、
`test_a_one_sided_differential_keeps_the_side_that_ran`。
注意 `test_an_inconclusive_differential_still_reports_both_sides` **不红**——这是对的：
它锁的是相反方向（真·无结论仍须显示两侧），一个只往"空"方向退化的变异不该动它。

**探针 C — 把安全配色改成装饰**：让 `executionSurfaceTone()` 不再给
`local_host_no_sandbox` 警示色 ⇒ `vitest run` **2 个文件红**
（`Matrix.test.tsx > Matrix execution-surface disclosure` 与
`toneMap.test.ts > only grants the ok tone to a confirmed container run`）。
即"宿主执行必须显眼看出来"这条是被锁住的，不是靠注释约束。

三个探针均**改后立即从备份还原**，并用 `git diff --numstat` 对账确认行数回到改动前（防止用
`git checkout --` 误丢本轮未提交的工作）。

### 7.5 门证（终树重新测过）

- 后端静态：`ruff check .` ⇒ `All checks passed!`；`mypy .` ⇒ `Success: no issues found in 210 source files`（全仓库口径，不是只测三个文件）。
- 后端定向回归：`pytest` 跑 **13 个文件**（`test_matrix_policy`、`test_matrix_pure`、`test_summary_matrix_rows`、`test_web_api`、`test_verdict_policy`、`test_verdict_stability`、`test_review_court_policy`、`test_court_no_evidence_blocker`、`test_acceptance_gate`、`test_compile_report`、`test_report_preflight`、`test_client_policy`、**`test_verification_coverage`**）⇒ **253 passed / 12.56s**。
  最后一份是本轮补进集合的：§7.7 给 HTML 报告矩阵表**加了一列**，而它恰好是唯一会数报告表格列的测试，不加进定向集合就等于漏掉最容易被打断的下游。
- 前端：`tsc --noEmit` 干净；`vitest run` **39 文件 / 250 例全绿**（本批净增 10 例：toneMap +4、Matrix +6）；`vite build` 通过。
- 新增锁：`test_web_api.py` 的**往返锁**补上 `execution_surface` 断言（worker 摘要 → `/jobs/{id}/matrix`，防止键名笔误造成"两侧各自绿"）。
  顺带查实：`_matrix_rows_from_summary` 的第一段循环本来就**按 worker 白名单整行透传**，`_SUMMARY_MATRIX_EXTRA` 只是二次兜底 ⇒ 真正决定字段能否出站的是 `agent/worker.py::_SUMMARY_MATRIX_ROW_KEYS`。这条判断本身也是读代码读出来的，靠往返锁兜住。

### 7.6 仍未做（诚实边界）

1. **#56 Node 离线依赖卷** / **#26 Python 沙箱**：需 Docker 在线窗口，本轮守护进程未运行 ⇒ 不可做、不可验证。
2. **执行面到了需求覆盖页与 HTML 报告，但没到风险详情页**：风险详情页的"证据方式"列只显示 `self_test_diff` 的中文标签，不带执行面（该字段在 findings 上不存在，属另一条数据路径）。
3. **#57 Craft 运行时时序**（attach 与终态事件的顺序）仍待产品决策。本轮未动运行时时序，但已把它**在页面上的可见后果**消掉：终态任务若还没有验收投影，结果页现在说"这次运行还没有独立验收记录"并给出 `specproof craft accept --job <id>`，而不是继续显示"任务还在处理中"（详见 §8）。
4. Phase 3.3 的另一半（引导页 checklist + 进度持久化）仍待办。
5. §5.4 的 ⑤（API 侧稳定降级错误码）、⑥（一键创建演示仓库）仍暂缓。

### 7.7 追加：顺带挖出的第二个缺陷——"没跑差分"被显示成"差分跑了但无结论"

写报告测试时发现 `test_report_says_not_run_instead_of_implying_a_pass` 变红，追下去是**产品缺陷而不是测试写错**：

- `agent/matrix_policy.py::_merge_verdict([])` 返回 `"UNVERIFIED"`（对**总体** verdict 是正确的：没有实验的规则必须是 UNVERIFIED，绝不能空白）。但它同时被用来算 `base_result`/`head_result`，于是**任何没跑差分的规则**，这两个字段都是 `"UNVERIFIED"`。
- 后果：需求覆盖页把 `!row.base_result && !row.head_result` 当作"未做差分实验"的判据（§6.8 的设计），而这个条件**永远不会成立** ⇒ 每条没跑差分的规则都被渲染成 `UNVERIFIED → UNVERIFIED`，即**断言了一次并不存在的比较**。§6.8 想要的"区分没做实验 vs 某侧有判定"实际没做到。
- **为什么 §6.8 没发现**：它的往返锁与前端用例都是**手工构造 payload**（不带 `base_result`/`head_result`），恰好绕开了真实产出路径。这正是 §6.8 自己记录过的失败模式（"假件掩盖真缺陷"）的另一种形态——这次是"手工 payload 掩盖真缺陷"。
- **修法**：新增 `_merged_side_verdict()`，**空集返回 `""`**，与 `_merge_verdict` 的语义刻意相反，注释写明理由。`_merge_group` 的两个侧面改用它。
- **两处既有断言编码了这个错误假设**，已连同"为什么原来是错的"一起改正（**不是放宽断言**）：
  - `test_contract_without_any_experiment_is_unverified_with_reason`：`base_result/head_result` 由 `"UNVERIFIED"` 改为 `""`（`result`/`unverified_reason`/`next_action` 等断言一字未动）；
  - `test_every_row_carries_all_canonical_fields`：字段域补上 `""` 这个合法值。
- **新增 6 条锁**（后端 3 + 前端 3），成对锁定两个方向：
  `test_no_differential_leaves_both_sides_empty_not_unverified`、
  `test_an_inconclusive_differential_still_reports_both_sides`（真·无结论仍要显示两侧）、
  `test_a_one_sided_differential_keeps_the_side_that_ran`（半次比较也是事实），
  以及前端同名三例（空对 → "未做改前/改后差分实验"且**只出现 1 个 pill**、真无结论 → 3 个 pill、单侧 → 保留已观测侧并标"无观测"）。
- 报告侧同步：`evidence/report.py` 的矩阵表新增 **Differential** 列（`PASS → FAIL (head)` + 换行的执行面 token；无差分显示 `not run`），并补 `.diff`/`.surface`/`.muted` 样式。**HTML 报告是用户会附到 PR 上的产物**，披露必须在那里也在。
- **CLI 未改（诚实边界）**：`cli/specproof/commands/verify.py` 只打印矩阵的**计数**（passed/failed/unverified/total），没有逐行输出，因此没有可挂执行面的位置；要加需先让 CLI 输出逐行矩阵，属另一件事。

## 8. 2026-09-24 会话（续）：独立验收结论终于能从 Web 读到（任务 #59）

### 8.1 状态核实（先查证再动工）

- 动工前 HEAD 仍是 `a3d815b`，#58 的改动整批留在工作区未提交（未出现并发写入者的痕迹：本仓库无其他会话）。
- **写入侧本来就是完整的**：`docs/architecture/DATA_DICTIONARY.md:303` 记录 `accept_json` "仅 succeeded/failed 可挂, first-write-wins"，`docs/architecture/STATE_MACHINES.md:178` 记录 `attach_accept_result` 的幂等语义，`storage/agent_jobs.py` 用 `COALESCE` 实现、`craft/accept.py::persist_accept_result` 是唯一写入者。⇒ 缺的不是数据，是**读取路径**。
- 读取侧查证：`api/routes/agent_console.py::_job_view` 返回 `status / plan / progress / result`，**从不返回 `job.accept_json`**；且 `_job_view` 全仓库只有一个调用点（`GET /agent/jobs/{job_id}`），所以不存在"别的端点已经给了"这种可能。前端 `api.ts::AgentJob` 也因此根本没有这个字段。

### 8.2 要消灭的缺陷，以及一个会把"直接暴露"变成误导的陷阱

- **主缺陷**：结果页写着"开发完成不等于独立验收通过"，但**同一页面拿不出那句区分所依据的结论**——验收结论、门禁明细、发现列表、证书路径全都只存在数据库列和 CLI 打印里。用户必须离开界面去跑 `specproof craft accept`，才能看到系统早就算完并落库的东西。
- **陷阱（先读代码才发现，否则会做出一个主动误导用户的界面）**：`api/agent_runtime.py::_gate_accept_projection` **永不产出 `VERIFIED`**。它写出的 BLOCKED 附带的是"完整 accept 闭包（SpecProof 验证 + 证书 + 签名）需 git base/head 与签名密钥，交由 craft accept CLI 执行"。也就是说这条通道上的 `BLOCKED` = **"还没签发合并证书"**，不是"检查没过"。若按 `passed/failed` 的直觉把它涂成红色失败，就是凭空造出一个假失败结论。**这个陷阱还有一个反方向的孪生兄弟，本轮同样踩到了，见 §8.7**。
- 顺带修掉一个同族缺陷（#57 的可见后果）：任务已进入 `COMPLETED/FAILED/CANCELLED` 但 `result` 为空时，页面原来固定显示"任务还在处理中"——对终态任务是假陈述。

### 8.3 落点

- **后端 `api/routes/agent_console.py`**：新增 `_accept_view(job)`，把 `accept_json` 投影成响应里的 `accept`，并**保持三态可分辨**——未挂载 ⇒ `null`；已挂载 ⇒ 结构化摘要；**已挂载但读不出来 ⇒ `{"attached": true, "malformed": true}`**（一条解析失败的记录绝不能渲染成"没有验收记录"）。
  细节上守两条既有红线：**缺失保持缺失**（`rolled_back`/`idempotent` 只有在真是布尔值时才出现，证书/通知路径只有非空字符串才出现；不填 `null`、不填 `—`），**截断必须自报**（门禁与发现各 20 条上限，同时给 `total` 与 `truncated`，因为"显示 20 条"永远不能被读成"只有 20 条"）。
- **前端**：`api.ts` 加 `AgentAccept` 等类型（注释写清 `null` 与 `malformed` 的区别）；`agent/util.ts` 把原本散在页面里的门禁标签表提为共享的 `gateLabel / gateStatusLabel / gateStatusPillClass`，并新增 `acceptVerdictLabel()`（`VERIFIED` 绿、`ERROR` 红、未知值原样透传）与 **`acceptBlockedMeaning()` / `acceptBlockedNotice()`**——`BLOCKED` 的颜色与说明**取自投影里的 `gates.overall`，不取自 token**（理由见 §8.7）；`AgentResult.tsx` 新增 `AcceptProjection` 面板，挂在 result 分支**之外**（否则没有执行结果的终态任务连验收都看不到）。

### 8.4 反向验证（四个变异探针）

新增的锁不测一遍就等于没测。逐个改坏源码 ⇒ 跑测试 ⇒ 用 `cp` 还原 ⇒ 核对 `git diff --numstat` 回到本轮真实改动量：

- **A：把投影里的 `verdict` 键改名** ⇒ `2 failed`（往返锁 + 证书路径锁）。
- **B：让 `malformed` 走 `return None`**（即"读不出来"伪装成"没有记录"）⇒ `1 failed`（`test_unreadable_accept_projection_is_not_reported_as_missing`）。
- **C：`"truncated": total > len(entries)` 改成硬编码 `False`** ⇒ `1 failed`（截断自报锁）。
- **D：把 `BLOCKED` 的 tone 从 `warn` 改成 `bad`**（就是 §8.2 那个陷阱）⇒ 前端 `2 files / 2 tests failed`。
- **E：让投影不再转发 `gates.overall`（硬编码成空串）** ⇒ 后端 `2 failed`（往返锁 + §8.7 新增的"两种 BLOCKED 必须可分辨"锁）。
- **F：让 `acceptBlockedMeaning()` 永远判成 `closure_deferred`**（即"门禁真挂了"被读成"只是闭包没跑"）⇒ 前端 `2 files / 2 tests failed`。
- 一处踩坑值得记下：**A 的第一次尝试是假探针**——我的锚点串带 `\n`，而这些文件是 CRLF，`count()==0` 的断言直接失败，脚本没写进去，随后的"6 passed"测的是未变异的源码。改成不含换行的锚点后才是真正的 2 红。**"探针跑绿了"必须先证明探针确实改了字节**。

### 8.5 门证（终树实测）

- 后端静态：`ruff check .` ⇒ `All checks passed!`（中途我自己的新测试写崩过一次 E501，改正后复跑）；`mypy .` ⇒ `Success: no issues found in 210 source files`。
- 后端定向回归：`pytest tests/unit/test_agent_console_api.py tests/unit/test_agent_jobs.py -q -p no:randomly` ⇒ **102 passed / 22.44s**；`-k accept` ⇒ **6 passed, 27 deselected**；单文件复跑 ⇒ **33 passed / 5.38s**。
- 前端：`tsc --noEmit` 无输出；`vitest run` ⇒ **40 文件 / 263 例全绿**（相对 §7.5 的 39/250，本批净增 1 文件 13 例：`AgentResult.test.tsx` 9 例——该页面此前**零测试**——+ `util.test.ts` 4 例）；`vite build` 通过。
- 变异还原后复验：`vitest run src/agent` ⇒ 12 文件 / 72 例绿，后端 accept 文件 33 例绿 ⇒ 工作区确实回到绿色。
- **全量合并门**（`pytest tests/unit tests/security tests/fault -q`）：改后终树第一次全量跑 ⇒ **1 failed, 2795 passed, 5 skipped, 1 warning in 1379.33s (22:59)**。唯一红点是 `tests/unit/test_provider_accounting.py::test_cancelling_model_call_stops_pending_request`（`cancel()` 之后 30s 线程仍存活）——**与 #58/#59 无关**，根因与修复见 §10。这条不是可以放宽超时结案的偶发噪声，而是取消功能本身的竞态。

### 8.6 仍未做（诚实边界）

1. **本轮只做了"读出来"，没做"跑起来"**：Web 控制台现在展示 runtime 通道写下的验收摘要，但**不会**从界面触发完整 accept 闭包（那需要 git base/head 与签名密钥，仍归 CLI）。面板里给出的就是这条命令本身。
2. **`VERIFIED` 在这一层目前不可达**：因为 `_gate_accept_projection` 永不产出它，`acceptVerdictLabel("VERIFIED")` 是**为 CLI 闭包写入的投影**准备的；它的正确性由 `craft.accept.AcceptResult.to_dict()` 的往返锁保证，而不是由"界面上见过这个值"保证。
3. 验收投影**只在任务详情端点**上出现；列表页、SSE 事件流都没有它（列表要显示验收结论需要先决定"摘要里放什么"，属另一件事）。
4. #57 的运行时时序本身仍未改（ attach 仍晚于终态事件），本轮只是让这段窗口在页面上显示为"还没有独立验收记录 + 怎么补"，而不是假装它不存在。
5. #56 / #26 仍需 Docker 在线窗口，本机守护进程本轮未运行。

### 8.7 追加：BLOCKED 有两种含义，把其中一种说成另一种同样是假陈述

给 README 写"BLOCKED 只代表尚未签发合并证书"之前，回去核 `_gate_accept_projection` 的**全部**出口，发现它有四个：

| 入口条件 | verdict | 真实含义 |
| --- | --- | --- |
| `report["gates"]` 不是 dict | `ERROR` | 没有可判的摘要 |
| `gates.overall == "error"` | `ERROR` | 门禁管线自身出错 |
| `gates.overall == "failed"` | **`BLOCKED`** | **内部门禁真的挂了**，且会把 failed/error 门禁下的 findings 汇总带上 |
| 其余（overall 通过 / 跳过） | **`BLOCKED`** | 门禁都过了，只是**合并证书闭包**留给 `craft accept` CLI |

- 所以 §8.2 只修掉了一半：把 BLOCKED 一律涂红是**假失败**；一律解释成"不代表下方门禁未通过"是**假安心**，而且更危险——它恰好发生在测试真挂了的那条分支上，页面会一边列出 findings 一边告诉读者"这不算挂"。
- **我为什么先写错**：第一版只读了 docstring（"The runtime lane never claims VERIFIED … the verdict is BLOCKED"），没读函数体里的 `if overall == "failed"` 分支。**docstring 说的是作者设想的正常路径，不是全部出口**，与 §6.8 / §7.7 记过的"用读注释代替读代码"同类。
- **修法**：判别**不取自 token，而取自同一份投影里的 `gates.overall`**——`failed` ⇒ 红色"门禁未通过，未签发合并证书"；通过 / 跳过 ⇒ 琥珀色"门禁摘要已过，尚未签发合并证书"；**摘要缺失或为 `error` ⇒ 明说"无法区分原因"**，两种都不猜。判据落在两个纯函数 `acceptBlockedMeaning()` / `acceptBlockedNotice()` 里，页面只渲染。
- **既有断言里也编码了这个错误假设**，一并改正而不是放宽：`AgentResult.test.tsx` 的第一例原本喂的就是 `overall: "failed"`，却断言琥珀色 + "不代表下方门禁未通过"——等于把 §8.2 的反向假陈述锁进了测试。现拆成三例（闭包延后 / 真失败 / 无摘要不可判）。
- 另加一条**真生产者锁** `test_the_two_blocked_flavors_reach_the_console_apart`：直接调 `AgentRuntime._gate_accept_projection` 生成两种 BLOCKED，断言两者在 HTTP 上的 `gates.overall` **不相等**。若投影哪天丢了该字段，前端就彻底没有可判别的依据——这正是探针 E 要买下的风险。

## 9. 2026-09-24 会话（续）：引导页从"一段说明文"变成"能自查的清单"（任务 #60）

### 9.1 要消灭的真实问题

引导页（`Guide.tsx`）原来是一篇静态四步说明：读者读完不知道自己走到第几步，也得不到"这一步到底做完没有"的反馈——产品对"第一次使用"这件事没有任何状态。这是"不友好"诊断里 §0 记的那条：**新手路径全靠脑补**。

### 9.2 落点

- **`apps/web/src/ui/onboarding.ts`（新增，纯逻辑）**：把"做到没有"拆成两类依据——
  - **系统能检测的**：连接（一次真实 `/jobs?limit=1` 探测）、是否已发起验证（同一探测带回的 `total`/`jobs.length`）；
  - **只有用户自己知道的**：需求是否写成了可验收的句子、是否读懂了结论。这类**永远不由系统打勾**，只能用户亲手勾选。
  - 进度落在 `localStorage`（键 `specproof_onboarding_v1`），路由到达结果页时由 `App.tsx` 记一次访问（`recordRouteVisit`）。
- **`apps/web/src/pages/Guide.tsx`**：渲染清单 + 每步一条 `basis`（这句判断凭什么下的），原文四段说明一字未删，收在 `STEP_DETAIL` 里继续展示。
- **`apps/web/src/pages/onboarding.css`**：只用已存在的 token（`--warning*` / `--success*` / `--color-surface-3` 等），零 `!important`。

### 9.3 四条诚实性判据（本节的主体）

1. **读不出来 ≠ 没有记录**。`loadOnboardingProgress()` 是三态：`ok` / `absent`（确实没有这个键）/ `unreadable`（解析或结构失败）。只有 `absent` 才允许显示"未完成"；`unreadable` 时全部降级为 `unknown`（"无法确认"），并显示一条明确的横幅。半条记录（`manual` 在、`visited` 不在）按 `unreadable` 处理——**静默丢掉读不出的一半，等于擦掉用户真的勾过的东西**。
2. **探测没回来 ≠ 探测失败**。`connection` 有 `pending`，此时既不打勾也不打叉，页面显示"正在检测工作区连接…"。同理 `verificationCount === null` ⇒ 该步 `unknown`，不能因为"列表是空的"就说"你还没验证过"——**空列表和读不到列表是两件事**。
3. **一个未被观察到的东西不能因为顺手就被写成 `null`/`—`**。`routeKeyFor("#/jobs/new")` 返回 `null`（那是创建表单，不是结果页），这条是自己写测试时抓到的真 bug：初版把 `new` 当成了某个 job 的 id，于是"打开新建表单"会被记成"已经看过结果"。
4. **"没登录"是被观察到事实，不是"探测失败"**。引导页是免登录可访问的（`App.tsx` 对 `guide` 路由放行），所以它的**主要读者恰恰是还没连接工作区的人**。第一版对这类人显示"无法确认"——那是最没用的回答。现引入 `credential: "present" | "absent"`（读 `getBearerToken() || getApiKey()`，两者都在存储不可用时安全返回空串）：凭据缺席时**根本不发那次注定 401 的探测**，第一步直接显示"未完成 · 这个浏览器里还没有工作区凭据"。但这条判据**只覆盖到"这台设备"**，所以"是否已发起验证"仍保持 `unknown`——别的设备可能早就跑过，本机看不见不等于没有。

### 9.4 反向验证（每个探针都先证明它改了字节，再看是否变红）

| 探针 | 改动 | 结果 |
|---|---|---|
| G | `connection === "ok" ? "done" : "unknown"` → `: "todo"`（把"没探测出来"说成"没做"） | **4 failed** / 16 passed |
| H | `!isStringMap(manual) \|\| !isStringMap(visited)` → `&&`（接受半条记录） | **1 failed** / 19 passed |
| I | 去掉 `recordRouteVisit` 里的 `unreadable` 守卫（一次导航覆盖损坏存储） | **1 failed** / 19 passed |
| J | 让 `credential === "absent"` 分支失效（对没登录的读者回退成"无法确认"） | **2 failed** / 20 passed（`onboarding.test.ts` 与 `Guide.test.tsx` 各一处） |

三个探针均在跑完后从 `/tmp/onb_orig.ts` 还原并 `grep` 复核锚点计数，未使用任何 git 破坏性命令。上一轮记过的教训在这里再兑现一次：**第一次试探针时锚点含 `\n`，而仓库文件是 CRLF，`count()==0` ⇒ 什么都没改，随后那次"变红"是假的**；本轮改成无换行锚点，并在替换前先断言命中数为 1。

### 9.5 门禁（本轮实测值，不抄历史）

| 门 | 命令 | 结果 |
|---|---|---|
| 类型 | `npx tsc --noEmit` | exit 0 |
| 单测 | `npx vitest run` | **42 files / 288 tests 全绿**（新增 `onboarding.test.ts` 15 例、`Guide.test.tsx` 7 例） |
| 构建 | `npx vite build` | ✓ built in 2.21s，`dist/assets/Guide-*.js` 9.92 kB（gzip 4.96 kB） |
| 后端 | `ruff check .` / `mypy .` | 沿用 §8.5 的读数：#60 **未改任何 Python 文件**，故无新增后端面 |

（上表探针 G/H/I 跑在加入 `credential` 判据之前的 20 例上，J 跑在其后的 22 例上；"n passed"是各次运行的当场读数，不是同一基线。）

### 9.6 仍未做（诚实边界）

1. 清单只有四步，覆盖"第一次跑通验证"，**不含** Craft/AI 开发通道——那条通道的"做完了吗"仍无产品内状态。
2. 进度只存在本机浏览器：换设备、清缓存即回到 `absent`。做多设备需要后端用户级存储，属另一件事。
3. "验证是否通过"不计入完成度——清单只回答"你是否走到了能看结论的那一步"，不对结论好坏下判断。

## 10. 2026-09-24 会话（续）：一次"偶发红"其实是取消功能的真缺陷（任务 #61）

### 10.1 现象

§8.5 的那次全量合并门里，唯一失败的是 `test_cancelling_model_call_stops_pending_request`：断言 `assert not thread.is_alive()` 在 `cancel()` 之后、`join(30)` 用满 30 秒时仍然红。30 秒不是"调度抖动"能解释的量级——被测的桩函数是 `await asyncio.sleep(60)`，即取消**根本没生效**，线程在等那次 60 秒的调用自然结束。

### 10.2 根因（错在两个动作的顺序）

`craft/llm.py::chat_sync` 原先是：先 `future = asyncio.run_coroutine_threadsafe(self.chat(...), loop)`（协程交出去，loop 线程立刻开跑），**之后**才 `with self._pending_lock: self._pending.add(future)`。

`cancel()` 的语义是"取消 `_pending` 里的每一个 future"。于是存在一个真实窗口：**协程已经在另一条线程上执行了，但它对 `cancel()` 还不可见**。用户在这时点"取消"，`cancel()` 拿到锁、看到空集合、如实报告"没有可取消的东西"，然后调用方继续等完整轮模型调用。窗口只有几条指令宽，所以空闲机器上几乎不复现、全量套件负载下周期性复现——正是"偶发红"的形状。

### 10.3 顺带挖出的第二条：流式调用从未登记

`stream_chat_sync` 连登记都没有：它的 `future` 从未进 `_pending`（只在生成器 `finally` 里 `future.cancel()`，那表达的是"调用方不再读了"，不是"用户按了取消"）。也就是说 **`cancel()` 对正在流式输出的模型调用完全无效**。

### 10.4 修法

- 把"提交"和"登记"**放进同一把 `_pending_lock`**：`cancel()` 需要同一把锁，因此它要么排在登记之后（看得见 future，能取消），要么完全在该调用提交之前（该调用还没开始）。中间态被结构性消除，而不是靠"再多等一会儿"。
- `stream_chat_sync` 同样登记，并在 `finally` 里 `discard`（否则集合只增不减）。
- `_pending` 元素类型从 `Future[LLMResponse]` 放宽为 `Future[Any]`（流式那条是 `Future[None]`），mypy 干净。

### 10.5 反向验证：探针 K，以及一条必须记下的错诊

- **探针 K**：只把 `chat_sync` 的 `with self._pending_lock:` 换成 `if True:`（等价于回到"提交与注册不互斥"），其余一字未动 ⇒ 新测试 `test_cancel_racing_the_submit_window_still_stops_the_call` **和**那个"偶发"的老测试 `test_cancelling_model_call_stops_pending_request` **一起变红**（2 failed, 9 passed / 44.36s）。跑完从备份还原并 `grep` 复核（0 命中），未使用任何 git 破坏性命令。
- **由此得到一条纠正**：`386a525`（标题 "root-fix two load flakes"）把这个测试的等待从 10s 放宽到 30s。**它既没有 root-fix，也不是 load flake**——放大超时只是把同一个竞态从"经常红"改成"偶尔红"，缺陷一直留在生产路径上。教训：**"偶发红"先问"哪个断言只在负载下成立"，不要用放大超时来结案**；测试里那段自证式注释（"Generous ceilings … only absorb scheduling latency"）读起来像理由，但它陈述的是作者的假设，不是代码的全部时序。与 §8.7 的"docstring 说的是什么"同族。
- 新测试**不靠负载**复现窗口：把 `asyncio.run_coroutine_threadsafe` 包一层，在"已经提交、尚未登记"这个位置停住提交线程，再从另一条线程调 `cancel()`。改前这个交错必然出现（红）；改后 `cancel()` 阻塞在锁上、等登记完成才继续，于是调用被真正取消（绿）。老测试原样保留，作为真实路径的哨兵。

### 10.6 门证（本批）

- `ruff check .` ⇒ All checks passed!；`mypy .` ⇒ Success: no issues found in 210 source files。
- `pytest tests/unit/test_provider_accounting.py -q -p no:randomly` ⇒ **11 passed / 3.07s**（新增 1 例）。
- **终树全量合并门（补记，实测）**：`pytest tests/unit tests/security tests/fault -q` ⇒ **2797 passed, 5 skipped, 1 warning in 851.25s (0:14:11)**，**0 失败**。计数对账：上一轮是 1 failed + 2795 passed = 2796 条非跳过，本轮 2797 = 2796 + 本批新增 1 例，且那个红点转绿。**两轮耗时（1379.33s vs 851.25s）差异未归因**——只有取消测试那一处能确定省下约 90s，其余只能归到主机负载不同，不得当提速证据写进任何文档。

### 10.7 仍未做（诚实边界）

1. `cancel()` 是"尽力而为"：协程内的 `finally`（例如已发出的 HTTP 请求收尾）仍会在 loop 线程上跑完。产品语义上"已取消"指**不再等待结果**，不等于对端已停止计费——界面上若写成"已停止"需要另改。
2. `close()` 里那条 `run_coroutine_threadsafe(provider.close(), self._loop).result(...)` 不走 `_pending`，属关闭路径而非取消路径，本批未动。
3. 探针 K 只证伪了 `chat_sync` 这一处；**流式登记目前没有独立测试覆盖**（需要 SSE 桩），是已知缺口。
4. 同一形状的"先使用后登记"若出现在别的注册表里（例如任务级取消表），本批未系统排查。

## 11. 2026-09-25 会话（续）：终态事件不再跑在验收摘要之前（任务 #57）

### 11.1 这条记录一开始是被当成"设计"接受的

#57 是 §6.8 那一步（真实任务的逐条证据）留下的登记项：那次全量合并门 2776 passed / 1 failed，唯一红点就是 `test_create_auto_start_then_poll_get_to_terminal` 的 `assert job.accept_json is not None` **而不是超时**，且单独跑 43s 通过——典型的交错窗口，不是时钟余量不足。当时的处置是"按运行时文档化的顺序再等一会儿"，把顺序当作事实写进注释：`store 终态 → 写 bundle → 终态 progress 事件 → 才 persist_accept_result`，并把"是否该把 attach 提到终态事件之前"作为产品决策登记为 #57（那一轮不擅自改 Craft 运行时时序）。本批重新追问的正是这条被接受的顺序：**它是设计，还是仅仅是实现的偶然？**

### 11.2 为什么"先宣告完成、后写证据"是产品缺陷

`_post_run` 原本的尾巴（`api/agent_runtime.py`）：

1. `write_json_atomic(... change-bundle.json)` —— 真实文件 I/O；
2. `state.record_event(job_id, "progress", {status: COMPLETED/FAILED, ...})` —— SSE 的最后一帧；
3. 之后才 `persist_accept_result(store, job_id, accept)`。

读端行为决定了这不是小事：**看到终态事件的正常反应就是立刻重取** `GET /agent/jobs/{id}`。落进 2→3 之间的读者取到的是"作业已完成，但没有任何验收记录"，而 `AgentResult.tsx` 面对 `accept == null` 只能显示"这次运行还没有独立验收记录（可能仍在写入）"。也就是说，运行时**自己发出的那个事件把读者推进了一个读者无法自证的窗口**——它不是"慢"，是一段时间内可被观察到的假陈述。窗口平时亚秒级，机器越忙（第 1 步的写盘越慢）越宽，这正好解释了"全量门里红、单跑绿"。

### 11.3 修法：只换顺序，不改语义

- 持久化块整体移到终态 `record_event` **之前**，原地留注释写明原因（重取者不得看见"完成而无证据"）。
- 模块 docstring 增加一句可被检验的保证：投影在终态 `progress` 事件记录之前落库。
- `cancelled` 分支保持提前 `return`、永不补投影（cancel wins；`attach_accept_result` 对 cancelled 永久拒绝，`storage/agent_jobs.py` 的文档写明）。
- 事件之间的相对顺序未动：gate 事件仍先于终态事件（`_watch_progress` 承诺的那条）。

### 11.4 反向验证：探针 L，以及一个新测试怎么才算"判顺序"而不是"判有无"

新测试的关键是 `_RecordingState`：**在 `record_event` 内部**采样 `store.get(job_id).accept_json`。断言因此衡量的是"事件发布那一刻存储的真实状态"，而不是事后回看。

- **变异 L**：把持久化块原样搬回 `record_event` 之后（只移动，不删改任何一行）。结果 `test_terminal_event_never_outruns_the_accept_projection[succeeded-COMPLETED]` 与 `[failed-FAILED]` **两例变红**，而取消那例 `test_cancelled_terminal_event_keeps_its_closed_projection` **仍绿**——正是想要的判据差异：新测试红的不是"投影不存在"，而是"投影存在得太晚"。
- 跑完从备份 `cp`（绝对路径目标）还原，再 `grep -n` 复核：持久化调用在第 672 行、终态事件在第 677 行，顺序回到修正后状态；全程未使用任何 git 破坏性命令。

### 11.5 门证（本批实测）

- `ruff check .` ⇒ All checks passed!；`mypy .` ⇒ Success: no issues found in 210 source files。
- `pytest tests/unit/test_agent_runtime.py -q -o addopts= -p no:randomly` ⇒ **14 passed / 57.11s**（本批新增 3 例：终态顺序参数化 2 例 + 取消终态 1 例；此前该文件 11 例）。
- **终树全量合并门**：`pytest tests/unit tests/security tests/fault -q -p no:randomly` ⇒ **2800 passed, 5 skipped, 1 warning in 1021.03s (0:17:01)**，**0 失败**。计数对账：上轮 2797 + 本批 3 = 2800；那条曾经靠"再等一会儿"过关的轮询测试仍绿，区别是它现在等的是 §11.6 第 1 条那条**已登记的窗口**，而不是被当作设计接受的语义。
- **耗时不作证据**：本轮 1021.03s vs 上轮 851.25s。等待期间本机 `tasklist` 里同时存在多个 python 进程（同一台机器上还有别的会话在跑），因此这 170 秒既不能写成回归也不能写成别的——两轮之间可比的只有"0 失败"与用例计数。探针 L 的判红发生在单文件范围（`-k` 选中 3 例，2 failed / 1 passed / 11 deselected / 5.93s），不受整机负载影响。

### 11.6 仍未做（诚实边界）

1. **只关闭了"事件驱动重取"这条路，没有关闭"纯轮询状态"那条**：存储行仍在 `CraftLoop._finish`（`craft/loop.py:2439`）里就翻成终态，那一刻 `_post_run` 根本还没开始。因此只看 `job.status` 的轮询者短暂看见"已终态、无投影"依然可能。真正原子地关闭需要"终态 + accept 一次写"的存储原语（要同时落在 SQLite 与 MySQL 两个后端上），本批没做，也没有假装做了。
2. 由此，那个既有轮询测试**继续保留等待**，但注释改了账：它等的不再是"文档规定的后补语义"，而是上面这条已知窗口。
3. UI 端把"终态且无投影"显示成"可能仍在写入，稍后刷新"（#59 落地的三态）在窗口内是对的，但同一句话目前被 **cancelled / 崩溃终态 / 写入窗口** 三种原因共用，其中前两种**永远不会再来投影**——已登记为 #62，本批只记录不动。
4. `_crash_terminal`（`api/agent_runtime.py:822`）写出的 FAILED 终态**永远没有投影**（门禁流水线从未跑完）。它该补一条 `ERROR` 判决的投影、还是应该显式声明"无门禁结论"，与 #62 一起决策；本批未改，以免把"没有"和"没跑"继续混在一个文案里。

## 12. 2026-09-25 会话（续）：验证车道的终态与证据合成一次写（任务 #63）

### 12.1 同一族缺陷在验证车道上更严重，而且多一条越权写

§11 关掉的是 Craft 车道的"宣告先于证据"。同一轮把同样的问法拿到验证车道（`agent/worker.py`）走了一遍，读到的是同形但更强的三处：

1. 终态判定与证据是**两次写**：`transition_job_status(job_id, verdict)` 之后才 `save_job_summary(...)`；
2. 第二次写整个包在 `contextlib.suppress(Exception)` 里——于是那条缝不是"短暂可见"，而是**可以永久存在**（写失败没人知道，行永远缺另一半）；
3. 第一次写的返回值被丢弃。需要区分两种"写没成功"：行已经是终态时 `transition_job_status` 会 `raise InvalidStateTransition`，这条旧代码本来就有 `except` 接住（只记日志、不宣告）；**被忽略的是返回 False 那一支**——先读到 RUNNING、UPDATE 时行已被 reclaimer 改回 QUEUED 或被取消改动，这一支旧代码照样发 `publish_report completed` 帧、照样计费、照样发 GitHub Check。

读码时另外发现的一条（此前没有任何文档提过）：`save_job_summary` 的 WHERE 只有 `id`（`storage/mysql.py:619-626`），不带状态条件。所以一个已经失去所有权的 worker 会**把摘要写进别人正在拥有的行**。#63 之后摘要只能随带 CAS 的那条 UPDATE 落库，这类越权写在结构上不再可能。

### 12.2 为什么不能反过来做（先写证据、后翻状态）

先记一个被否掉的方向：把两次写交换顺序——先 `save_job_summary` 再翻终态——会把"短暂缺证据"换成另一种更坏的东西：崩溃时留下一个仍然 RUNNING 的行、身上挂着一份看起来已完成的 `VERIFIED` 摘要；supervisor 之后把它翻成 FAILED，那份证据还在，读者会拿它当结论。**窗口不能靠挪位置关闭，只能靠合并成一次写。**

### 12.3 修法：一个存储原语 + 三处按同一形状改写

- `storage/mysql.py::transition_job_status` 新增 `summary: dict | None = None`，与 status 在**同一条 UPDATE** 里；序列化沿用 `_json.dumps(summary, default=str)`，与 `save_job_summary` 完全一致，所以列形状不变、零迁移。`None` 表示"没有新的要说"，**不发 `summary = NULL`**——"未提供"与"清空"是两句不同的陈述，docstring 里写明了。
- `agent/worker.py`：`summary = _state_summary(final_state, verdict)` 从 best-effort 变成终止路径的一部分；终态写成 `if not transition_job_status(job_id, verdict, summary=summary): 记 warning + incr("worker_terminal_cas_lost_total") + return`。这个 `return` 的语义是"被拒 ⇒ 剩余副作用一个都不做"：不发 completed 帧、不计费、不发 GitHub Check、不写 `jobs_completed_total`（已在 return 之后，逐行核对过）。`suppress` 里剩下的只有 metrics 上报——观测后端挂了不得改变持久记录说了什么。
- `ops/drills.py`：崩溃恢复演练的 replay 用同一条语句；协议 `JobAuditStore` 加 `summary` 成员并**删掉 `save_job_summary` 声明**（生产已无人调用的协议成员是假守卫）。`scripts/drill_worker_kill.py` 传的是真 `MySQLStore`，签名兼容，无需改。
- `save_job_summary` 保留：CLI（`cli/specproof/commands/verify.py:543`）与 demo 种子（`scripts/seed_demo.py:415`）从不翻状态，它们写的本来就是"只有证据"那一半，没有窗口可关。

### 12.4 反向验证：探针 M（三个变异，各自判红）

| 变异 | 生产含义 | 结果 |
| --- | --- | --- |
| M1 worker 终态调用删掉 `summary=summary` | 回到"宣告与证据分离" | `test_terminal_verdict_carries_its_summary_in_the_same_write` + `test_worker_records_lease_and_stage_duration_metrics` 同时红（2 failed / 29 passed / 55.70s） |
| M2 被拒分支删掉 `return` | CAS 输了照样宣告完成 | `test_refused_terminal_cas_announces_no_completion` 红（1 failed / 30 passed / 43.57s） |
| M3 storage 的 `if summary is not None:` 变 `if False and ...` | 原语退化，摘要永不落列 | `test_summary_rides_in_the_status_statement` 红（1 failed / 30 passed / 44.90s） |

M1 的第二条红是**改账的结果而不是意外**：那条既有测试原先断言的是"`save_job_summary` 被调用过"（kwargs 侧），本批把它改成断言"落到行上的摘要内容"（`mysql.written_summaries()`），因此它现在测的是可见结果。三条变异各自跑完立刻按备份字节还原，脚本末尾再逐锚点复核 `count == 1`（输出 `restored; verifying anchors are back / OK`）；未使用任何 git 破坏性命令。

两处值得单独记的判据设计：

- **存储层断言必须后端无关**。`tests/unit/test_job_state_machine.py::TestStateMachineWithDB` 在没有 MySQL 的机器上整类 `pytest.skip`，而"status 与 summary 同语句"正是那种**必须在笔记本上也能被检验**的陈述。新类 `TestTerminalWriteIsOneStatement` 用 recording fake connection 只断言 SQL 形状与参数位置（`params[0] == "VERIFIED"`、`params[1]` 能 `json.loads` 回原 dict、WHERE 的 id 与 from_status 在末尾），第二条断言"不带 summary 时 SQL 里根本不出现 `summary` 字样"——后者正是 12.3 里"None 不清空"那条承诺的可执行形式。
- **假守卫清账**：`_FakeMysql` 不提供 `save_job_summary`（生产若还留着两次写路径，就会 `AttributeError` 响，而不是被一个没人调用的桩悄悄放过）；`test_drill_helpers.FakeJobStore` 把 `"summary": "stored"` 的副作用从 `save_job_summary` 搬进 `transition_job_status` 的 `summary` 分支；`test_worker_error_classify` 与 `test_job_reclaimer` 两个 stub 的同名死方法删掉。

### 12.5 门证（本批实测）

- `ruff check .` ⇒ All checks passed!；`mypy .` ⇒ Success: no issues found in 210 source files。
- `pytest tests/unit/test_worker_cancel_points.py tests/unit/test_job_state_machine.py -q -o addopts= -p no:randomly` ⇒ **31 passed / 16.85s**（本批新增 5 例：worker 侧 3 例——同写/被拒/摘要造不出来；storage 侧 2 例——SQL 形状与"不带 summary 就不出现该列"）。
- `pytest tests/unit/test_drill_helpers.py tests/unit/test_worker_error_classify.py tests/unit/test_job_reclaimer.py -q -o addopts= -p no:randomly` ⇒ **56 passed / 9.75s**（改账不改计数：`FakeJobStore` 的 `summary` 分支、两条被拒路径各加一条"什么都没留下"的断言、两个死 stub 删除）。
- 探针 M 的三轮判红见 12.4 表格，每轮还原后逐锚点复核 `count == 1` 通过。
- 同批顺带修掉一处**文档自身的假陈述**：`docs/operations/OBSERVABILITY.md` 的"已接线指标名（全部真实注册）"清单漏了 worker 生命周期整侧与 outbox relay 的 8 个名字。因为本项目没有静态注册表（名字只在第一次上报时才出现），"清单全不全"只能靠取上报点核对，于是把方法连同结果一起写进那一节：三个 `incr/set_gauge/observe_duration` 调用模块 + 常量解析 + 拼接族用正则匹配。`api/auth.py:91` 与 `storage/redis.py:112` 的 `client.incr(...)` 是 Redis 命令、不是指标，已排除并写明，免得下一次又把它当指标收录进来。
- **终树全量合并门**：`pytest tests/unit tests/security tests/fault -q -p no:randomly` ⇒ **2805 passed, 5 skipped, 1 warning in 2460.48s (0:41:00)**，**0 失败**。计数对账：上轮 2800 + 本批新增 5（12.5 第二条那 5 例）= 2805；被改账的既有测试（`written_summaries` 断言、`FakeJobStore.summary` 分支、两条"被拒不留下任何东西"）不新增用例，因此不出现在这个差值里。
- **耗时不作证据**：本轮 2460.48s vs §11.5 的 1021.03s。这台机器在本轮期间同时存在多个别的 python 会话，两轮之间可比的只有"0 失败"与用例计数；这 1400 秒既不能写成回归，也不能写成别的。探针 M 的三轮判红发生在单文件/单类范围，不受整机负载影响。

### 12.6 仍未做（诚实边界）

1. **只影响新落库的终态写**。改动之前写完的作业里，"终态但 summary 为空"的行仍然存在于表中（旧代码的第二写被 suppress 过时就是这样），而且这类行**永远不会再补上证据**。Web 验证车道对它们说的是另一回事：`apps/web/src/pages/JobDetail.tsx:327` 在 `summary == null` 且请求没失败时渲染 `Empty text="验证结果尚未生成。执行完成后，这里会展示结论、需求覆盖与风险证据。"`——一句"再等一会儿就有了"的承诺，而任务**已经完成了**。Craft 侧 `AgentResult.tsx` 的"可能仍在写入，稍后刷新"同形。两处都属 #62 要区分的"终态 + 无证据"，登记完不动文案。

2. **Craft 车道（SQLite `agent_jobs.accept_json`）仍是两次写**。§11.6 第 1 条登记的纯轮询窗口**没有**因为本批的原语而关闭：原语只落在 `verification_jobs` 上，`accept_json` 侧要同样的合并得再做一个后端的等价改动。
3. `ops/drills.py::side_effect_counts` 的 `summary_writes` 数的是"行上有没有摘要"（`1 if job.get("summary") else 0`），不是"写了几次"。这个 looseness 在本批之前就存在、本批也没改；后果是"崩溃恢复不产生重复副作用"的演练断言在摘要这一项上**看不见重复写**（只能看见缺失）。改法要么真计数，要么改名成 `summary_present`。
4. **失败分支的对外宣告仍未与持久记录对齐，而且更糟**：`agent/worker.py` 的通用 `except Exception` 里，`xadd_progress(..., "failed")` 在落库之前无条件发出；终态写的返回值不看；`_maybe_publish_github_check(job_id, "FAILED", {"contracts_total": 0, "findings": []})` 把**现场造的零统计**发到 GitHub Check Run——`integrations/github_checks.py::check_summary_text`（155-178 行）会渲染成 `Contracts: 0 total — 0 passed, 0 failed, 0 unverified.`。流水线根本没数过契约，0 不是"没有契约"而是"未得出统计"。已登记为 #64。
5. 取消与 lease-lost 两处 `_mark_*` 的语义（"这条事件说的是本 worker 停了"，不是"行归谁"）已经写在 docstring 里并有测试覆盖，属已界定而非遗漏。

## 13. 2026-09-25 会话（续）：失败路径不再伪造统计，宣告跟随落库结果（任务 #64）

### 13.1 起点是上一批自己写下的一条"更糟"

12.6 第 4 条把 `agent/worker.py` 的通用 `except Exception` 登记为"仍未做，而且比终态那条更糟"。本批回去读它，确认了三件同时发生的事：

1. `xadd_progress(job_id, job_id, "failed", ...)` 在落库**之前**无条件发出，而且第二个位置参数（node 名）填的是 job id 本身——前端的阶段时间线因此在"阶段"列表里插入一个 UUID，`stageLabel` 认不出来就原样透传，用户看到一行 `3f2a…c81` 以为是某个执行阶段。
2. 终态写的返回值被丢掉：CAS 输了（行已被 reclaimer 或 cancel 挪走）也照样发"failed"帧、照样更新 GitHub Check Run。这与 #63 修的是同一件事，只是发生在失败分支。
3. `_maybe_publish_github_check(job_id, "FAILED", {"contracts_total": 0, "findings": [], "errors": [str(exc)[:200]]})`——第三个参数是**当场手搓的假摘要**。

### 13.2 为什么第 3 条是这一批的主线：`0` 是一种陈述，不是"没有数据"

`integrations/github_checks.py::check_summary_text` 见 `contracts_total` 就渲染 `Contracts: 0 total — 0 passed, 0 failed, 0 unverified.`。这句话读起来是一次**完整的清点结果**（数过了，共 0 条，全过），而真相是流水线在统计之前抛了异常，压根没数过契约。产品红线里"缺失保持缺失"在这里被违反了两次：一次由 worker 造出键，一次由渲染器把缺键也画成 0。

同一族缺陷在 `integrations/notify/templates.py` 里有第二个实例：`*Contracts:* 0` 与 `*Matrix:* 0 passed / 0 failed / 0 unverified` 各自独立地用 `.get(key, 0)` 兜底，所以"只写了 total、没写 matrix"这种半截摘要会渲染成"总数 4，通过 0/失败 0/未验证 0"——两个字段互相拆台。

因此本批的修法分成两半：**渲染侧只有一个说了算的地方**，**发送侧不再有凭空造的键**。

### 13.3 修法

- 新增 `integrations/contract_counts.py`：`COUNT_KEYS` 四个键、`counted()` 要求**四个全在且都是非负整数**才返回值（`bool` 不算整数、`"3"` 不算、`-1` 与 `1.5` 不算；JSON 里 `4.0` 是整数所以算），`count_sentence()` 在缺任一键时输出 `not counted — this run recorded no contract statistics`。注意"0"仍然合法：真数出来 0 条就写 0 条，缺的才是缺的。
- `github_checks.py::check_summary_text` 与 `notify/templates.py` 的两个渲染函数改为调用同一个模块；`blocks_for_summary` 只算一次 `counted()`，让 Contracts 与 Matrix 两个字段**一起移动**（要么都有具体数字，要么都写 not counted）。findings 与 capsules 补上"键不存在"与"空列表"的区分（`not recorded for this run` vs `none`），errors 渲染并如实截断（`… N more`）。
- worker 的失败分支改成与 #63 同一个形状：先由 `_provider_wait_allowed` 决定去向，再写，**只有写成功才宣告**。`written` 为假 ⇒ 记 `worker_terminal_cas_lost_total`、日志、`return`，进度帧与 GitHub Check 都不发。429 暂停落库成功时，帧的 status 从 `failed` 改成 `waiting_for_provider`（行状态是什么，事件就说什么）。
- `_failure_summary(exc, classification)` 取代手搓字典：只有 `verdict` 与一条 `errors`，**不含任何 `COUNT_KEYS` 键、不含 `findings` 键**——即"这一轮没数过"由数据结构本身表达，而不是靠渲染器记住。
- 失败/暂停帧的 node 名固定为 `terminal`；`apps/web/src/ui/stages.ts` 为它和 `lease`、`cancel_checkpoint` 三条 worker 事件补中文说明，并明写"不是某个执行阶段"。`StatusPill.tsx` 补 `COMPLETED`（时间线每一行的 status 都是它，之前满屏裸 token）。

一处**顺序决定**要记下来：本批没有把 `notify/templates.py` 接进生产。它是先存在的第二个渲染者，改它可以顺手接线，但接线属于新功能（要选事件源、要管密钥、要有失败策略），而本批的目标是"对外说的每句话都能追溯到落库的那一行"。于是只统一它的语义，并把它**未接线**这一事实作为发现登记在 13.6。

### 13.4 反向验证：探针 N（四个变异，各自判红）

| 变异 | 它模拟的旧行为 | 判红结果 |
|---|---|---|
| N1 被拒分支的 `if not written:` 变 `if False:` | 落库被拒仍宣告失败 | 3 failed / 13 passed（`tests/unit/test_worker_cancel_points.py`） |
| N2 把 `_failure_summary(...)` 换回字面量零统计 | GitHub Check 又拿到现场造的 0 | 1 failed / 15 passed（同上） |
| N3 `count_sentence` 的 `None` 分支返回 `"0 total — 0 passed…"` | 缺失渲染成零清点 | 3 failed / 32 passed（`test_contract_counts.py` + `test_notify_connector.py`） |
| N4 在决定与落库之前先插一帧 `xadd_progress` | 宣告跑在写入前面 | 5 failed / 11 passed（`test_worker_cancel_points.py`） |

N1/N2/N4 的红**分布在不同测试**上：N1 与 N4 都会踩到"宣告顺序/宣告存在"断言，N4 额外踩到既有 `_completion_announces` 那条（#63 建立的判据），说明这批的断言不是只认某一种错法。四轮均按备份字节还原，脚本末尾逐锚点复核 `count == 1`（`restored; anchors back: OK`），未使用任何 git 破坏性命令。

新增测试里有一条是**双向**的：`tests/unit/test_progress_event_labels.py` 用 AST 取 `agent/worker.py` 中 `xadd_progress` 的第 1/2 位置参数字面量（含三元表达式的两个分支）、用 AST 取 `agent/graph.py` 的 `add_node(...)` 名字，再用正则取 `stages.ts` 的 `STAGE_LABELS` 与 `StatusPill.tsx` 的 `STATUS_LABELS` 键集合，然后要求"生产出来的都必须有中文注释"和"注释里不得有生产者已不存在的死条目"同时成立。它是本批**唯一能真正抓住"文案漂移"的门**——单向门只会漏掉新增事件，不会报错辞典里的僵尸。

### 13.5 门证（本批实测）

- `ruff check .` ⇒ All checks passed!；`mypy .` ⇒ Success: no issues found in **211** source files（+1 是本批新增的 `contract_counts.py`）。
- `pytest` 九文件定向跑（worker 取消点 / 状态机 / contract_counts / progress labels / notify / github_checks / drills / reclaimer / error_classify）⇒ **133 passed / 30.93s**。
- 其中 `tests/unit/test_worker_cancel_points.py` + `tests/unit/test_job_state_machine.py` ⇒ **36 passed**（12.5 记录的同类跑是 31，本批 worker 侧新增 5 例：成功宣告、被拒不宣告、非法转移不宣告、暂停帧状态、假摘要不含统计键）。
- 新增两文件各自：`test_contract_counts.py` **11 passed**、`test_progress_event_labels.py` **3 passed**。
- 前端三门禁（`apps/web`）：`npx tsc --noEmit` 无输出通过；`npx vitest run` ⇒ **43 files / 293 tests passed**（上批 42/288，本批新增 `statusPill.test.tsx` 4 例 + `stages.test.ts` 1 例）；`npx vite build` ⇒ `✓ built in 4.18s`，`assets/index-*.js 200.81 kB │ gzip: 69.60 kB`。
- 探针 N 的四轮判红见 13.4 表格。
- **终树全量合并门**（`pytest tests/unit tests/security tests/fault -q -p no:randomly`，本批 13 文件全部落定后跑）⇒ **2824 passed, 5 skipped**。这条与 13.3 记录的上一轮 2805 对得上账：`2805 + 11 (test_contract_counts) + 3 (test_progress_event_labels) + 5 (worker 侧新增宣告例) = 2824`。三项相加恰好等于差值，说明本批没有静默改掉任何既有断言，新增例数与计划一致；如果哪个旧断言被"顺手放宽"了，这里会少掉对不上的那几例。
- **耗时不作证据**：同一道门这次 2063.68s（34:23），上批记录约 41 分钟——机器负载不同而已，两者都不能用来说明"变快/变慢"。要谈耗时必须固定并发条件后重测；本节只把 pass/skip 计数当结论。

### 13.6 仍未做（诚实边界）

1. **`integrations/notify` 整个包在生产里没有调用点**。实测依据：`webhook_connector_from_env` 的引用只出现在它自己的定义与 `integrations/notify/**` 的 `__init__` 重导出、以及文档字符串里；`text_for_summary` / `blocks_for_summary` 的调用点只有包内 `notification_for_summary` 与 `tests/unit/*`。也就是说本批"统一了两个对外渲染器"，而其中**只有一个真的对外**（GitHub Check Run）。要么把通知接进终态事件（需要 outbox/事件源与密钥策略的决策），要么把这整包删掉——留着会让下一个人以为 webhook 已通。
2. **`lease` 与 `cancel_checkpoint` 两帧仍写 status=`failed`**。前者与落库的 FAILED 一致；后者不一致（同一段代码把行写成 CANCELLED）。这两处的写包在 `contextlib.suppress(Exception)` 里且没读回结果，所以不能在不复制 #63/#64 形状的前提下改成"跟随行状态"。已在 `docs/operations/OBSERVABILITY.md` §6 明写为未修不一致，避免文档先替它作证。
3. **`_failure_summary` 只带一条 error，仍不含"跑到哪一步才炸的"**。GitHub Check 上现在会说"这一轮没数过契约"，但不会说"在 `run_differential` 之前就没了一半"。阶段信息在 Redis 进度流里有，在持久行里没有，所以对外通道拿不到——属 #62 家族的"终态但证据不完整"。
4. **worker 的异常失败路径不进入 `jobs_<verdict>_total` 族**。`agent/worker.py:197-206` 的这段计数只在图跑完并成功落终态之后执行，所以 `jobs_failed_total` 数到的是"图跑完了、结论是 FAILED"那部分，**抛异常的轮次一次也不计**（它们只 +`worker_provider_wait_total`，或在被拒时 +`worker_terminal_cas_lost_total`，否则什么都不加）；`jobs_completed_total` 同理不含异常轮。也就是说看板上按 verdict 族算的"失败率"会**系统性低估**——分子缺，分母也缺。本批没改它，因为补计数会改变既有告警查询的口径（`jobs_failed_total` 之前一直是"结论级失败"），要先确认没有看板/规则依赖旧语义；这属于口径决策，不是漏写一行 `incr`。
5. 12.6 第 1–3 条（历史空摘要行、Craft 车道仍两次写、`side_effect_counts.summary_writes` 数的是存在性）本批一律未动，仍然有效。

## 14. #62：同一句"稍后刷新"覆盖了四种不同的事实（2026-09-24）

### 14.1 起点

两个页面各有一句"没有证据"的通用文案：验证详情页 `JobDetail.tsx` 写"验证结果尚未生成。执行完成后，这里会展示结论、需求覆盖与风险证据。"（断言了一个"稍后就会有"的状态），Craft 结果页 `AgentResult.tsx` 更进一步写"结果投影在状态落库之后写入，**稍后刷新即可**"（一个明确的行动建议）。但读代码发现，同样的"没有"至少对应四种互斥的事实，而它们的正确建议完全不同：有的刷新会补上，有的永远不会补上，有的根本还没有结论可补，有的连"是什么状态"都不知道。把四种事实压成一句承诺，等于对其中三种说谎——用户会一直刷新一个永远不会变的页面。

### 14.2 判据来自读存储层，不是猜（本批实测的三条事实）

1. **执行终态与结果投影是同一条写入**：`storage/agent_jobs.py:371` 与 `:378`（`_UPDATE_STATUS_TERMINAL_SQL` / `_UPDATE_STATUS_NON_TERMINAL_SQL`）都带 `result_json = COALESCE(?, result_json)`。所以 Craft 侧"status=COMPLETED 但没有 result"**不是时序窗口**，"稍后刷新会补出结果"是假承诺——只能说明这一行的终态不是本轮执行写下的（被回收、supervisor 置位，或该规则之前完成的历史行）。
2. **验收摘要是另一次写入，且只挂在执行完的轮次上**：`_ATTACH_ACCEPT_SQL`（`storage/agent_jobs.py:354-356`）的 WHERE 是 `status IN ('succeeded','failed')`。所以"已取消"永远不会等到验收投影，而"刚成功/刚失败"确实可能还在写——这两种"没有"必须分开说。
3. **FAILED 在验证车道不是终态**：`storage/mysql.py:46-65` 的 `TERMINAL_STATUSES = {VERIFIED, BLOCKED, STALE, CANCELLED, ERROR}` 不含 FAILED，而 `"FAILED": {"QUEUED","CANCELLED","ERROR"}` 说明它还能被重排或取消。因此 JobDetail 的前端集合 `apps/web/src/pages/JobDetail.tsx:31-32`（`ACTIVE` / `TERMINAL`）与后端逐值对齐，并把 FAILED 单独成支——既不能并进"仍在执行"，也不能并进"已终态"。

### 14.3 改了什么

- `apps/web/src/pages/JobDetail.tsx`：摘要缺失处原来只有一支通用文案（"验证结果尚未生成。执行完成后，这里会展示…"），现按事实分四支（读失败那支是 FE-10 既有的 `summaryLoadFailed`，排在最前、不计入这四支）：仍在执行（`ACTIVE`）、这一轮以失败结束（`FAILED`，指向"最近执行错误/执行进度"）、已进入终态但没有摘要（`TERMINAL`，明说"同一条写入 ⇒ 不会随刷新补上"）、以及**未识别状态原样透出**（`任务状态为 X，这是本页面未识别的状态` + "既不等于已终态，也不等于仍在执行，所以这里不下结论"）。空状态值显示为 `（空）`，不伪装成任何一个已知 token。
- `apps/web/src/agent/pages/AgentResult.tsx`：`AcceptProjection` 把"没有验收记录"分成未进终态 / 已取消（永远不会有）/ 执行完但还没挂上（这一次"可稍后刷新"是真的，因为它确实是两次写入）；缺结果投影分成 COMPLETED（**同一条写入** ⇒ 明说"稍后刷新不会补出结果"）与 FAILED/CANCELLED（这一轮本来就不产结果投影，指引去看失败原因）。改动的两条依据以代码注释钉在原地，避免下一个人把它"顺手改回"通用刷新提示。

### 14.4 顺带根因掉一个"偶发红"：`Guide.test.tsx`（不是超时）

引导页 checklist 的探针是异步的。原写法是"先等一个数量代理，再同步取具体文案"：`await waitFor(() => expect(getAllByText("无法确认").length).toBe(2))` 之后紧跟**非 await** 的 `screen.getByText(/这不等于没有连接/)`。实测红的正是后者，报错原文 `Unable to find an element with the text: /这不等于没有连接/`（本批回捞了会话记录里的那行才写下这句，不凭印象）。也就是说：**数量代理成立，并不蕴含它想代理的那句文案已经可见**，两者不是同一个渲染条件。并行负载把窗口拉开时就红。

⚠️ 至于 `length===2` 为何能先于该句文案成立，本批**没有**把渲染次序钉死（要钉得给 `Guide.tsx` 的每步状态更新加插桩）；这里只登记"可复现的红断言 + 修复 + 复验"，不把未证实的机制当结论写。修复与既有纪律一致：**改判据，不放宽超时**——两条兄弟断言各用 `await screen.findByText(/…/)` 等自己要的那句话，门只等自己，不看别人的进度。改后 `Guide.test.tsx` 隔离连跑 3 次各 **7 passed**，随后并入全量门。

### 14.5 门证（本批实测）

- `npx tsc --noEmit` 无输出通过；`npx vitest run` ⇒ **43 files / 302 tests passed**；`npx vite build` ⇒ `✓ built`。
- 302 与 13.5 记录的 293 的差是**本批新增 9 例**（`JobDetail.test.tsx` 新 describe 4 例 + `AgentResult.test.tsx` 新增 5 例、另有 1 例改账不增数）：`293 + 9 = 302`。13.5 的 293 是在这 9 例进树之前对同一棵树测的，两个数都是当时的真话，不是互相打脸。
- 本轮 `vite build` 在后台合并门并行跑的条件下耗时 9.74s（13.5 记 4.18s）——**耗时不作证据**，只有 `✓ built` 与产物哈希存在才算。

### 14.6 仍未做（诚实边界）

1. **Craft 侧的"未识别状态"分支实际到不了**：`api/routes/agent_console.py::_console_status` 末尾是 `return "CANCELLED"`，任何未映射的存储层状态在 API 层就已经被折成"已取消"。前端这条分支是给验证车道（状态面宽得多）用的；要让 Craft 也如实，得先让 `_console_status` 原样透传未知 token——已开任务 #69。
2. FAILED 非终态（14.2 第 3 条）意味着"这一轮以执行失败结束"这句话在重排发生后会过期；页面不承诺永久，也不承诺"失败已定"。
3. 13.6 第 3 条仍然成立：对外通道拿不到"炸在哪一步"的阶段信息（Redis 进度流里有，持久行里没有）。




