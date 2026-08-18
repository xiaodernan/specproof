# SpecCraft 代码开发 Agent 商业化终极计划书

## 面向 Codex、Claude Code、Cursor、Devin 级代码能力的工业化建设路线

版本：1.0

日期：2026-08-18

适用项目：`D:\experim\specproof-clean-clone-gate`

文档类型：产品定义、技术架构、完整前后端需求、Agent 能力规格、商业化方案、测试体系、研发计划与逐步执行手册

---

## 一、先给结论

这份文档的主题不是普通聊天机器人，也不是在现有 CLI 上增加一个“让模型生成代码”的按钮，而是把当前仓库中的 SpecCraft 建设成一个真正可用于软件研发的代码开发 Agent：它能够理解真实仓库、读取项目规则、规划任务、检索代码、修改多个文件、运行命令和测试、诊断失败、修复回归、管理预算、保存记忆、恢复中断、委派并行子任务、提出 Pull Request，并且在交付前把结果交给独立的 SpecProof 验收。写代码的 Agent 不能给自己签发最终合格证，这是整个产品的可信边界。

目标产品应当具备类似 Codex、Claude Code、Cursor、Devin 的代码行动能力，同时形成自己的差异化：

1. 代码行动能力：可以在真实仓库中完成跨文件、跨模块、跨测试层的中小型研发任务。
2. 工程判断能力：不仅生成代码，还能理解依赖、接口、数据模型、构建系统、部署配置和回归风险。
3. 可控执行能力：每次读文件、改文件、执行命令、调用网络、创建分支和提交都受到权限、预算和沙箱策略约束。
4. 可恢复能力：模型超时、机器重启、Worker 崩溃、Provider 不可用、测试失败，都能从持久化状态继续，而不是重新猜测。
5. 可解释能力：用户能看到为什么选择这些文件、为什么执行这些命令、为什么认为任务完成、哪些内容没有验证。
6. 独立验收能力：SpecCraft 的产物必须经过 SpecProof 的需求契约、Base/Head 差分、运行时实验、证据胶囊和证书流程，不能由同一 Agent 自我宣布成功。
7. 商业化能力：支持个人、团队、企业 SaaS 和私有化部署，具备组织、权限、配额、计费、审计、集成、运维和合规边界。

本项目当前已经有一部分 Agent 内核：`craft/spec.py` 解析任务、`craft/planner.py` 生成确定性或 LLM 计划、`craft/editor.py` 提供原子编辑和审计、`craft/executor.py` 执行受控命令、`craft/loop.py` 负责迭代收敛、`craft/budget.py` 管理预算、`craft/memory.py` 提供任务记忆、`craft/llm.py` 提供模型调用与流式能力、CLI 的 `craft plan/run/resume/explain` 提供入口。当前的主要缺口不是“完全没有 Agent”，而是距离 Codex/Claude Code 级别还缺少大规模仓库理解、稳定工具协议、并行子代理、持久化任务服务、IDE 和 Web 产品、复杂语言生态、长期记忆、自动化交付、企业治理和大规模评测。

文档后半部分给出可以一步步执行的研发计划。每个阶段都有交付物、验收条件和不能伪造的边界。普通开发迭代不要求反复构建 Windows 安装包或 Docker 镜像；只有发布候选、集成验收和明确部署任务才进入这些耗时线。

---

## 二、产品定位：不是聊天窗口，而是受治理的研发执行系统

### 2.1 产品一句话

SpecCraft 是一个能够在授权范围内独立完成软件工程任务的代码开发 Agent；它通过仓库理解、计划执行、工具行动、测试修复、记忆和协作提高研发速度，通过 SpecProof 的独立验收保证结果不被 Agent 自己的乐观判断污染。

### 2.2 与普通代码补全的区别

代码补全主要回答局部编辑位置，成功标准通常是“语法看起来合理”。代码开发 Agent 的成功标准是“目标行为在真实仓库中成立，并且没有破坏既有约束”。因此 Agent 必须处理以下问题：

- 用户说“加一个接口”，需要查找路由、服务、模型、迁移、鉴权、文档和测试，而不是只写 Controller。
- 用户说“修复 bug”，需要复现、定位、修改、添加回归测试、跑相关测试和判断是否扩大影响。
- 用户说“重构模块”，需要知道哪些公共 API、序列化格式、数据库结构和部署脚本不能破坏。
- 用户说“升级依赖”，需要读取锁文件、变更日志、兼容矩阵、漏洞报告和构建结果。
- 用户说“实现一个需求”，需要把自然语言拆成可观察的验收标准，并在完成后交给独立验证系统。

### 2.3 与 Codex、Claude Code、Cursor、Devin 的对标方式

不能用品牌宣传语对比品牌宣传语。必须按照可执行能力比较：

| 能力面 | 目标对标 | SpecCraft 的建设要求 |
|---|---|---|
| 终端行动 | Codex / Claude Code | 受控 shell、文件系统、Git、测试、构建、日志和超时回收 |
| 多文件编辑 | Claude Code / Cursor | 唯一匹配、原子写入、补丁预览、冲突检测、回滚和审计 |
| 仓库理解 | Cursor / Devin | 符号索引、调用图、依赖图、文档图、Contract 图和混合检索 |
| 长任务执行 | Codex / Devin | 计划 DAG、checkpoint、租约、重试、取消、断点恢复和预算 |
| 自动修复 | Codex / Claude Code | 测试失败诊断、最小补丁、受控重试、变更范围限制 |
| 人机协作 | Claude Code / Cursor | 权限审批、危险命令确认、计划审阅、Diff 审阅、撤销和交付批准 |
| 并行 Agent | Codex / Devin | 子任务 DAG、文件所有权、冲突合并、失败隔离和最终综合 |
| 外部工具 | MCP 生态 | MCP 客户端、工具注册、Schema 版本、权限、预算和不可信结果隔离 |
| 质量证明 | 当前主流产品较弱 | SpecProof Contract、差分实验、Capsule、签名证书和独立裁决 |
| 企业治理 | 企业版能力 | 多租户、SSO、审计、数据域、私有模型、计费、SLO 和灾备 |

对标不意味着复制所有产品设计。SpecCraft 应该借鉴行业产品的交互效率和工具广度，把自己的优势放在“Agent 写完以后有证据地验收”上。

---

## 三、当前 Agent 基线与差距

### 3.1 当前已经存在的内核

仓库中已经存在一个相当清晰的 Craft 分层：

```text
TaskSpec
  -> Plan / Step / SuccessCriteria
  -> CraftLoop
      -> Repository inspection
      -> LLM planning or deterministic fallback
      -> Editor atomic changes
      -> Executor command/test
      -> Diagnose failure
      -> Iterate under budget
      -> Checkpoint / TaskMemory
  -> Craft report
  -> optional SpecProof verify
```

`planner.py` 已经有任务分类、目标文件推导、成功标准、步骤上限、DAG 校验和 LLM 计划回退；`editor.py` 已经有唯一匹配、原子文件写入、备份和审计；`executor.py` 已经有命令白名单和测试报告抽取；`loop.py` 已经有步骤状态、迭代、失败诊断、停滞判定和恢复入口；`budget.py` 负责时间、token、工具调用或步骤级预算；`memory.py` 保存任务级事实；CLI 已经有计划、运行、恢复和解释命令。

这部分内核的价值在于它不是把模型放进一个无限循环。它已经承认 Agent 需要计划、预算、审计和终态。这是继续工业化的正确起点。

### 3.2 与行业先进 Agent 的差距

#### 差距 A：仓库理解深度不够

单次读取几个文件无法支撑大型仓库。需要构建索引、符号图、依赖图、测试覆盖图、配置图、数据库迁移图和历史变更图。Agent 需要回答“这个函数被谁调用”“这个 DTO 由哪些接口返回”“这个数据库字段在哪些查询中使用”“这个配置在生产环境如何覆盖”。

#### 差距 B：工具面不完整

生产 Agent 不只是 `read_file`、`write_file` 和 `run_test`。它需要 tree、glob、grep、symbol_search、find_references、find_definition、git_diff、git_log、git_blame、read_config、inspect_env、run_targeted_test、run_full_test、package_manager、browser_optional、issue、PR、review 和证据工具。工具越多，越需要统一 Schema、权限和结果回喂防注入。

#### 差距 C：长任务持久化不足

本地 checkpoint 可以支持开发，但商业服务需要 Job 事实源、Worker 租约、消息幂等、节点级 checkpoint、对象工件、取消和重试。浏览器关闭、进程崩溃、模型网关挂掉、测试运行 30 分钟，都不能让用户丢失任务。

#### 差距 D：并行子代理缺失

大型需求通常可以拆成后端、前端、测试、文档和审计几个相对独立车道。没有子代理，主 Agent 要串行处理所有内容，成本和上下文压力都会快速增长。并行不是简单 `asyncio.gather`，还需要文件所有权、依赖 DAG、冲突检测、结果验证和失败重试。

#### 差距 E：仓库规则和组织规则摄取不足

Claude Code 类工具会读取项目规则文件。SpecCraft 必须读取 `AGENTS.md`、`CLAUDE.md`、README、贡献指南、构建脚本和 CI 配置，并建立来源与优先级：组织策略高于仓库策略，仓库策略高于任务默认，用户明确指令高于普通建议，但不能越过安全策略。

#### 差距 F：编辑正确性和冲突处理需要大幅扩展

唯一匹配编辑适合小任务，但复杂重构需要基于 AST、符号引用、结构化补丁和三方合并。Agent 必须知道文件在它读取以后是否被人修改，必须发现 stale context，避免覆盖用户新改动。

#### 差距 G：自校验还需要独立化

Agent 自己跑过测试不代表需求完成。必须把构建、单元测试、契约检查、静态安全、迁移检查、API 兼容、变异测试和 SpecProof 独立验收串起来，输出“已验证”和“未验证”边界。

### 3.3 目标量化指标

建议以真实任务而不是模型主观评价作为门槛：

- 10 个内部微基准任务完成率不低于 90%，陷阱变体自校验拦截率 100%。
- 50 个中型仓库任务中，至少 80% 能在预算内完成编译、定向测试和需求验收。
- 代码编辑成功率不低于 98%，stale context 覆盖率 100%，用户改动被覆盖次数为 0。
- 工具参数 Schema 校验通过率不低于 99.9%，危险命令误执行率为 0。
- 任务重启恢复率不低于 99.9%，消息重复不产生重复业务副作用。
- 对相同仓库、相同任务和相同模型版本，计划关键步骤的漂移率有监控，不能只看最终 PASS。
- 预算超限任务必须进入明确终态，不能无限循环或静默截断。
- SpecProof 高风险 Finding 的证据完整率 100%，证书只在所有必要 Contract 有真实证据时签发。

---

## 四、完整产品工作流

### 4.1 用户第一次使用

用户登录工作台，连接 GitHub/GitLab 或上传一个受控仓库，选择一个任务模板或输入自然语言任务。系统进行仓库预检：语言、构建系统、测试命令、默认分支、规则文件、敏感文件、工作区状态和权限。预检不修改仓库。

系统将任务解析为：目标、非目标、约束、验收标准、风险标记、预计文件范围、预计命令、预算和需要审批的动作。用户可以审阅和修改计划，然后选择“仅计划”“执行但每次危险动作需确认”“全自动执行”三种模式。

### 4.2 Agent 计划阶段

计划阶段必须产出结构化 DAG，而不是只输出自然语言：

```json
{
  "plan_id": "plan_01",
  "task_id": "task_01",
  "goal": "为订单接口增加幂等保护",
  "non_goals": ["不修改支付供应商协议"],
  "risk_flags": ["database", "concurrency", "api_compatibility"],
  "steps": [
    {
      "id": "inspect-1",
      "kind": "inspect",
      "depends_on": [],
      "owned_paths": ["src/order/**", "db/migrations/**"],
      "success": ["找到请求入口、持久化写入点和已有幂等键"]
    },
    {
      "id": "implement-1",
      "kind": "edit",
      "depends_on": ["inspect-1"],
      "owned_paths": ["src/order/**", "db/migrations/**"],
      "success": ["重复请求只产生一次业务副作用"]
    },
    {
      "id": "test-1",
      "kind": "verify",
      "depends_on": ["implement-1"],
      "owned_paths": [],
      "success": ["新增并发与重复请求测试通过"]
    }
  ],
  "approval_required": ["migration", "external_network"],
  "budget": {"minutes": 20, "tool_calls": 80}
}
```

计划必须能被机器执行、恢复、解释和审计。自然语言解释可以附加，但不能替代 Schema。

### 4.3 探索与上下文准备

Agent 按风险而不是按文件数量读取上下文。第一轮只读取入口和规则；第二轮围绕符号和依赖扩展；第三轮读取测试、迁移和部署配置。每次上下文都记录来源、摘要和 digest。超出预算时自动压缩中间知识，不简单从尾部截断。

探索结果应形成仓库事实卡：

```text
语言与版本：Python 3.12 / React 18 / Java 21
构建入口：pyproject.toml / package.json / mvnw
测试入口：pytest / npm test / mvnw test
规则文件：AGENTS.md、CLAUDE.md、CONTRIBUTING.md
高风险区域：auth、migration、message consumer、billing
外部依赖：MySQL、Redis、RabbitMQ、S3、LLM Gateway
当前工作区：clean / dirty / user_changes_present
不可修改路径：generated、vendor、secrets、lock policy
```

### 4.4 执行阶段

每个步骤都有状态：`PENDING`、`READY`、`RUNNING`、`WAITING_APPROVAL`、`SUCCEEDED`、`FAILED`、`BLOCKED`、`SKIPPED`、`CANCELLED`。步骤开始前检查依赖和文件新鲜度；步骤结束后保存输入 digest、工具调用、修改列表、输出摘要和成功标准结果。

Agent 不应让模型直接拼 shell 字符串。模型发出结构化工具请求，执行层验证参数、命令白名单、路径范围、网络权限和预算，随后才启动进程。工具结果限制长度并标记为不可信数据，回喂模型时与系统指令严格分段。

### 4.5 自校验与修复

最小自校验链路是：格式检查 -> 静态检查 -> 编译 -> 受影响测试 -> 全量测试或合理子集 -> 安全扫描 -> API/Schema 兼容 -> 需求 Contract -> SpecProof 独立验收。失败时先分类：环境失败、测试失败、实现失败、需求歧义、工具失败、预算不足或外部服务失败。不同类别使用不同恢复策略，不能所有错误都继续调用模型。

修复循环最多执行有限轮次。每轮必须产生新证据，否则判定 STUCK。相同错误连续出现、修改范围超过预算、Agent 试图反复改回原文件、测试结果不稳定时，进入人工确认或 FAILED，而不是无限重试。

### 4.6 交付阶段

交付前生成 ChangeBundle：任务、计划版本、修改文件、Diff、测试命令和结果、依赖变化、迁移说明、风险、未验证项、回滚方法和 SpecProof 结果。用户可以选择只导出补丁、创建本地分支、创建 GitHub PR、添加 Check Run 或请求人工 Reviewer。默认不允许自动合并。

---

## 五、Agent 内核架构

### 5.1 分层

```text
Web / CLI / IDE / MCP Client
          |
Task API + Auth + Policy + Quota
          |
Agent Job Orchestrator
          |
Planner -> Context Engine -> Tool Router -> Execution Runtime
   |            |                |                |
Memory     Repository Graph   Approvals       Sandbox
          |
Verifier / SpecProof / Evidence / Delivery
```

每层职责如下：

- **Task API**：身份、租户、任务、幂等、配额和用户可见状态。
- **Orchestrator**：DAG 调度、租约、checkpoint、取消、重试、并发和优先级。
- **Planner**：任务解析、风险分类、计划生成、成功标准和依赖关系。
- **Context Engine**：规则摄取、符号索引、检索、摘要、压缩和上下文预算。
- **Tool Router**：工具注册、Schema、权限、预算、执行策略和结果包装。
- **Execution Runtime**：本地开发沙箱、容器沙箱、远程 Worker、进程回收和工件收集。
- **Memory**：会话、任务、仓库、组织和跨任务记忆，带来源和过期。
- **Verifier**：测试、自校验、SpecProof、证据和交付门禁。

### 5.2 Agent 状态模型

Agent 的 LangGraph 状态适合做步骤编排，但商业服务还需要关系型 Job 投影：

```text
agent_jobs
agent_steps
agent_tool_calls
agent_file_observations
agent_memory_entries
agent_checkpoints
agent_approvals
agent_artifacts
agent_deliveries
```

Mongo 或文件 checkpoint 适合保存复杂状态，MySQL/关系库保存任务事实、状态迁移、权限、时间和索引。Redis 只保存短期租约和流式进度。每个 checkpoint 引用 `repo_snapshot_digest` 和 `policy_version`，恢复时重新检查仓库是否改变。

### 5.3 计划 DAG 与调度

计划步骤必须有明确的 `depends_on`、`owned_paths`、`read_paths`、`resource_class`、`risk_class`、`timeout`、`retry_policy`、`approval_policy` 和 `success_criteria`。调度器只运行依赖已完成且文件范围不冲突的步骤。对同一个文件有写权限的步骤不能并行；只读检索可以并行；测试和文档可以在代码修改完成后并行。

计划变更必须版本化。如果模型在执行中修改计划，系统记录旧计划、新计划、原因、用户是否批准和新增预算。不能让模型通过修改计划绕过原有审批。

---

## 六、工具系统：Agent 的手和眼睛

### 6.1 工具分类

建议按风险分层，而不是把所有工具平铺：

**只读工具**：`tree`、`glob`、`grep`、`read_file`、`symbol_search`、`find_definition`、`find_references`、`git_status`、`git_diff`、`git_log`、`read_rules`、`inspect_test_config`。

**低风险写工具**：`apply_patch`、`create_file`、`format_file`、`update_test`，只允许在计划的 owned paths 内操作。

**受控执行工具**：`run_test`、`run_lint`、`run_build`、`run_typecheck`、`run_migration_check`，需要使用仓库声明的命令模板。

**高风险工具**：`shell`、`network_request`、`install_dependency`、`database_write`、`git_commit`、`git_push`、`create_pr`、`merge_pr`。默认需要用户或组织策略批准。

**验证工具**：`run_specproof`、`build_capsule`、`replay_capsule`、`verify_certificate`。这些工具产生证据，不能被普通 Agent 结果覆盖。

**外部工具**：MCP、Issue、Jira、Slack、浏览器、云资源。每个连接器必须声明数据范围、网络目的地、权限和计费影响。

### 6.2 工具 Schema

工具请求统一使用版本化结构：

```json
{
  "tool": "apply_patch",
  "version": "2",
  "call_id": "call_123",
  "arguments": {
    "path": "src/service.py",
    "patch": "*** Begin Patch ...",
    "expected_digest": "sha256:...",
    "reason": "实现任务中的幂等检查"
  },
  "budget_cost": {"seconds": 1, "bytes": 4096},
  "requires_approval": false
}
```

执行结果也必须结构化：状态、退出码、摘要、输出头尾、截断标记、产物引用、耗时、资源消耗和安全标签。模型不应收到无限长度的终端输出。

### 6.3 工具结果防注入

仓库文件、测试输出、编译错误、Issue 内容和外部网页都可能包含“请忽略系统指令”的文本。工具层对结果做四件事：标记来源为 untrusted data；限制长度；保留完整结果到工件存储；在 prompt 中使用明确的数据分隔；对命令输出中的疑似秘密进行脱敏。不能因为文本来自本地文件就认为可信。

### 6.4 工具批准模型

审批请求要显示具体动作，而不是只显示“Agent 要求权限”：

```text
动作：执行 npm install
目录：apps/web
网络：registry.npmjs.org
预计影响：修改 package-lock.json，下载约 80MB
原因：新增测试依赖
风险：供应链变化、锁文件变动
替代方案：使用已有 node_modules，或仅运行 tsc
```

用户可以批准一次、批准本任务、批准仓库规则范围或拒绝。组织策略可以比用户更严格。批准记录进入审计，任务重试时不能自动继承已经过期的危险批准。

---

## 七、上下文工程、代码理解和记忆

### 7.1 仓库摄取流程

首次进入仓库时建立以下索引：

1. 文件清单、语言、大小、生成文件、二进制文件和敏感文件。
2. 规则文件和优先级。
3. AST、函数、类、接口、模块、导入和导出。
4. 调用图、引用图、继承图、路由图和配置引用图。
5. 测试到生产代码的覆盖关系。
6. 数据库表、迁移、查询、序列化模型和 API Schema。
7. Git 历史、最近高风险变更和责任人。
8. 构建和测试命令、CI 步骤、容器配置和部署清单。

索引必须按 repository、commit SHA 和语言工具版本隔离。索引失败时明确降级到文件级检索，不把空结果误认为“仓库没有相关代码”。

### 7.2 混合检索

检索路径采用 BM25 + 向量（可选）+ 符号图谱 + 重排：

```text
用户任务 / 当前错误
    -> 关键词与符号抽取
    -> BM25 候选
    -> embedding 候选（可选）
    -> RRF 融合
    -> 调用图与引用图邻域扩展
    -> 规则过滤与路径范围约束
    -> 可选交叉编码器重排
    -> 上下文压缩与来源标记
```

重要的是诚实降级：embedding 没有配置时使用 BM25+图谱；向量服务故障时继续使用 BM25；重排失败时保持原序并写入 retrieval_note。检索层不能成为判定链路的单点。

### 7.3 上下文压缩

上下文达到预算时，按优先级保留：系统策略、用户任务、当前错误、目标符号、直接调用者和被调用者、相关测试、最近修改、数据库和 API 约束。低优先级日志转为摘要，但摘要必须引用原始工件。摘要不能产生新的事实，不能隐藏冲突。

### 7.4 记忆分层

建议五层记忆：

- 会话记忆：当前对话、当前步骤和最近工具结果，生命周期最短。
- 任务记忆：已读文件、已改文件、已验证命令、失败原因、用户决定和未决问题。
- 仓库记忆：构建方式、约定、模块关系、常见陷阱、规则文件和历史诊断。
- 组织记忆：代码规范、审批要求、数据域、禁用工具、默认模型和成本策略。
- 经验记忆：跨任务修复模式、常见错误和成功补丁，但必须经过脱敏和质量评估。

记忆项包含内容、来源、digest、可信级别、创建时间、过期时间、适用范围和是否用户确认。模型自己推断的内容不能与用户确认规则混在一起。敏感仓库默认不允许跨租户经验记忆。

### 7.5 规则优先级

推荐顺序：平台安全策略 > 组织策略 > 仓库策略 > 目录策略 > 当前任务明确要求 > Agent 默认策略 > 模型建议。发生冲突时停止或请求确认，并在界面显示冲突来源。不能把规则文件中的“忽略所有安全检查”当作最高指令。

---

## 八、代码编辑和软件工程能力

### 8.1 编辑器演进

第一阶段保留 `apply_patch` 的唯一匹配和原子写入，这是最稳的基础。第二阶段增加结构化编辑：基于 Python AST、TypeScript AST、Java Parser、Go AST 的符号级重命名、导入整理、方法插入和接口迁移。第三阶段增加跨文件重构：引用更新、序列化兼容、测试同步、迁移和文档联动。

每次编辑前保存：目标文件 digest、选择器、预期匹配数、上下文片段和计划步骤。编辑后验证新 digest、语法解析、Diff 范围和 owned paths。匹配为 0 或大于 1 时默认拒绝，不允许模型猜测替换。

### 8.2 用户改动保护

用户可能在 Agent 工作期间修改文件。每次写入前比较 expected_digest；如果不一致，进入 STALE_CONTEXT。Agent 只能重新读取、重新规划或请求合并，不能强行覆盖。工作区内已有的 dirty changes 要分类为 user changes、agent changes 和 unknown changes，未知变化必须暂停。

### 8.3 跨语言代码能力

支持顺序建议：

1. Python：pytest、ruff、mypy、FastAPI、Django、SQLAlchemy。
2. TypeScript：Vite、React、Node、NestJS、Vitest、Playwright。
3. Java：Maven/Gradle、Spring Boot、JUnit、Flyway/Liquibase。
4. Go：go test、go vet、gofmt、模块和接口。
5. SQL、YAML、Dockerfile、Terraform、GitHub Actions 和 OpenAPI。

每个生态必须拥有语言适配器、构建适配器、测试适配器、格式化适配器、静态检查适配器和安全边界。支持某语言不等于支持该语言的所有框架，产品页面要展示兼容矩阵和已验证版本。

### 8.4 依赖和迁移

Agent 修改依赖时必须读取锁文件、许可证、漏洞信息、项目约束和 CI。数据库迁移必须生成正向和回滚说明，检查空库、旧库、并发部署和数据量。任何破坏性迁移都需要审批和备份确认。

### 8.5 Git 和交付

默认工作在临时分支或隔离 worktree。Agent 可以生成 commit message、创建 commit 和 PR，但 `push`、合并和发布默认需要批准。交付前生成变更摘要、测试矩阵、风险列表、未验证项、回滚命令和关联 Issue。Agent 不应篡改用户已有 commit，不应重写公共分支历史。

---

## 九、测试、自校验和独立验收

### 9.1 自校验分层

```text
层 0：语法与格式
层 1：类型、lint、静态安全
层 2：受影响单元测试
层 3：模块集成测试
层 4：全量测试与构建
层 5：Contract 与需求矩阵
层 6：SpecProof Base/Head 差分
层 7：Capsule 重放与证书
```

低风险任务可以在层 0-3 结束，高风险任务必须由策略提升到层 5-7。每层结果独立记录，不能因为层 0-4 通过就覆盖层 5 的 UNVERIFIED。

### 9.2 失败诊断

失败分类器应综合退出码、日志、栈、变更范围、历史错误和环境状态：

- `ENVIRONMENT_FAILURE`：工具链、依赖、服务、网络或权限问题。
- `IMPLEMENTATION_FAILURE`：代码编译或测试行为失败。
- `REGRESSION`：既有测试或 Base/Head 差分证明被破坏。
- `SPEC_AMBIGUITY`：需求无法形成唯一验收标准。
- `TOOL_FAILURE`：工具参数、服务返回或解析失败。
- `SECURITY_BLOCK`：秘密、越权、沙箱或策略违规。
- `BUDGET_EXHAUSTED`：时间、token、工具调用或修改范围超限。

诊断结果必须告诉 Agent 下一步是否允许重试。如果同一错误属于环境失败，继续修改代码没有意义；如果是实现失败，可以读取相关上下文、生成最小修复和重新跑定向测试。

### 9.3 SpecProof 交接协议

SpecCraft 完成后提交一个 ChangeBundle：Base SHA、Head SHA、需求、计划、修改列表、测试结果、模型信息摘要、策略版本和未验证项。SpecProof 独立读取仓库和需求，重新编译 Contract，执行差分和证据收集。SpecCraft 不得传入“我认为已经完成”的信任标记替代真实实验。

### 9.4 评测基准

开发 Agent 需要自己的基准，不只依赖 SWE-bench。建议建立：

- 基础修复：单文件 bug、边界条件、异常处理、日志和测试。
- 多文件功能：API、服务、模型、迁移、测试和文档。
- 重构：接口迁移、模块拆分、类型升级、依赖升级。
- 真实工程：CI 失败、构建脚本、容器、配置和跨平台问题。
- 对抗任务：错误 Issue、恶意 README、过时测试、隐藏的禁止变更和提示注入。
- 交付任务：生成 PR、变更说明、回滚方案和证据包。

每个任务必须有机器判定和人工解释。指标包括 patch correctness、测试通过、回归率、工具效率、平均迭代、预算、人工介入次数、未验证率和安全违规率。

---

## 十、并行子代理和协作系统

### 10.1 角色模型

建议提供有限的专用 Agent 角色：

- Planner：理解需求、拆分 DAG，不直接改代码。
- Explorer：读取仓库、建立上下文、找到符号和影响范围。
- Implementer：在分配的文件所有权范围内编辑。
- Test Engineer：编写和运行测试，不能修改生产代码，除非获得升级权限。
- Reviewer：审阅 Diff、契约和风险，提出反例。
- Security Agent：扫描秘密、注入、越权、依赖和沙箱边界。
- Release Agent：生成 ChangeBundle、版本说明、迁移和回滚计划。
- SpecProof：独立验收，不能接受实现 Agent 的最终结论。

角色不是为了制造更多模型调用，而是为了分离责任，减少一个 Agent 同时规划、实现和自我批准导致的偏差。

### 10.2 文件所有权

每个并行步骤声明 `owned_paths`。只读探索可以共享；写操作必须独占。两个步骤修改同一个文件时，调度器自动串行化，或使用临时分支并做三方合并。合并冲突不能交给模型直接“解决后继续”，必须通过语法、测试和人工审阅。

### 10.3 结果综合

子代理返回结构化报告：完成步骤、修改文件、测试、发现的问题、未完成原因、依赖、建议和工件引用。主 Agent 只综合报告和必要上下文，不把所有子代理完整对话塞入上下文。子代理失败不应让整个任务丢失，可重新分配或降级为串行执行。

### 10.4 并行的商业价值

并行可以减少大型任务的墙钟时间，但会增加 token、沙箱和冲突成本。调度器要根据租户并发额度、文件重叠、步骤风险和预算动态决定并发，不把“最大并发”作为默认越大越好。前端显示并行车道、每个 Agent 的进度和资源消耗。

---

## 十一、前端完整项目需求

### 11.1 产品端形态

最终需要三种客户端：

1. Web Control Room：任务、计划、Diff、审批、日志、证据、组织和运营。
2. CLI：开发者在终端快速计划、执行、恢复、解释和回放。
3. IDE 扩展：在 VS Code/JetBrains 中查看计划、选中代码发起任务、接受 Diff、批准工具和查看测试。

三者共享同一个 Task API 和事件模型，不要为每个客户端重复实现 Agent 逻辑。

### 11.2 Web 页面清单

```text
/login
/organizations
/repositories
/repositories/:id/overview
/tasks
/tasks/new
/tasks/:id/plan
/tasks/:id/live
/tasks/:id/diff
/tasks/:id/tests
/tasks/:id/memory
/tasks/:id/approvals
/tasks/:id/delivery
/verifications/:id
/evidence
/policies
/models
/integrations
/members
/usage
/audit
/settings
```

### 11.3 关键交互

任务页面必须区分“模型思考摘要”“工具行动”“文件变更”“测试结果”“人工决定”和“系统策略”。不要默认显示可能包含秘密或过长的原始推理文本；显示可审计的决策摘要、证据和工具参数。每个危险动作显示范围、影响和撤销方式。

计划页面支持拖拽调整依赖、修改成功标准、锁定文件范围、标记需要审批的步骤和估算成本。Diff 页面支持按文件、符号、步骤和 Agent 过滤，显示用户改动保护、潜在冲突和测试覆盖。Live 页面使用 SSE 实时更新，但断线后从 REST 恢复。

### 11.4 组件和状态

共享组件包括 StatusPill、StageTimeline、PlanGraph、ToolCallRow、DiffViewer、TestResult、ApprovalDialog、BudgetMeter、MemoryEntry、EvidenceLink、ErrorBoundary、DegradedBanner 和 EmptyState。所有组件必须有 loading、empty、error、degraded、permission denied 和 stale 状态。

### 11.5 权限体验

用户看不到无权限的仓库和任务；对于有权限查看但无权限操作的资源，按钮显示禁用原因。审批对话框不能通过前端隐藏按钮实现安全，后端必须再次校验。管理员可以查看审计和用量，但默认不能查看私有源代码内容，除非拥有明确权限。

### 11.6 前端测试和性能

使用 Vitest/Testing Library 做组件和状态机测试，Playwright 做关键工作流。测试浏览器刷新、SSE 断线、API Key/Session 过期、任务取消、权限切换、长日志、5000 个文件列表、移动端和键盘操作。生产包要做 bundle 预算，日志和 Diff 使用虚拟列表，避免把完整仓库一次性加载到浏览器。

---

## 十二、后端完整项目需求

### 12.1 控制面与运行时分工

Spring Control Plane 负责登录、组织、成员、仓库连接、策略、计费和外部集成；Python Agent Runtime 负责计划、上下文、工具、执行、模型和 SpecProof。控制面不直接运行不可信代码，运行时不直接决定账单和组织权限。

### 12.2 任务 API

建议提供：

```text
POST   /api/v1/agent/tasks
GET    /api/v1/agent/tasks
GET    /api/v1/agent/tasks/{task_id}
POST   /api/v1/agent/tasks/{task_id}/cancel
POST   /api/v1/agent/tasks/{task_id}/pause
POST   /api/v1/agent/tasks/{task_id}/resume
POST   /api/v1/agent/tasks/{task_id}/approve
GET    /api/v1/agent/tasks/{task_id}/events
GET    /api/v1/agent/tasks/{task_id}/plan
GET    /api/v1/agent/tasks/{task_id}/diff
GET    /api/v1/agent/tasks/{task_id}/artifacts
POST   /api/v1/agent/tasks/{task_id}/deliver
POST   /api/v1/agent/tasks/{task_id}/verify
```

任务创建请求至少包括 repository_id、base_sha、task_text、execution_mode、budget、desired_checks、network_policy、model_policy 和 idempotency_key。服务器不能接受任意宿主机路径作为 SaaS 请求参数。

### 12.3 事件和消息

事件包括 `agent.task.created.v1`、`agent.plan.ready.v1`、`agent.step.started.v1`、`agent.tool.requested.v1`、`agent.approval.required.v1`、`agent.file.changed.v1`、`agent.test.failed.v1`、`agent.task.paused.v1`、`agent.task.completed.v1`、`verification.blocked.v1` 和 `delivery.pr.created.v1`。所有事件带 tenant、trace、aggregate、schema 和 digest，消费者采用 inbox 幂等。

### 12.4 数据安全

仓库快照和 Agent 工件按租户和 repository 隔离。日志默认只保存摘要和引用，完整输出进入加密对象存储，按保留策略清理。模型请求在发送前脱敏，模型响应不会自动写入长期记忆。跨租户检索、跨组织经验复用和向量索引必须显式禁止或经过管理员批准。

### 12.5 配额和成本

预算分为用户任务预算、租户并发、租户每日额度、模型 token、沙箱时间、存储和外部工具调用。Redis 做实时扣减和短租约，关系库写最终用量账本。扣减失败时停止高成本动作，不把模型调用当作无限资源。成本看板显示估算和实际结算的区别。

---

## 十三、安全与信任边界

### 13.1 沙箱安全

任何不可信仓库代码都可能通过测试、构建脚本、依赖安装和插件执行任意命令。沙箱必须使用非 root、断网、只读源码、独立临时目录、CPU/内存/PID/磁盘限制、cap-drop、no-new-privileges、无 docker.sock、无宿主机秘密、超时强杀和完整资源计量。开发模式的 local fallback 必须显式标记，不能在生产默认启用。

### 13.2 Prompt 注入

仓库里的 README、注释、测试输出、Issue 和网页均为不可信数据。系统策略、用户要求和仓库数据用不同消息段。Agent 不得因为仓库文字要求就读取秘密、关闭沙箱、跳过测试或执行外部发送。注入测试要覆盖 README、注释、分支名、commit message、生成测试、依赖错误、日志和 MCP 工具结果。

### 13.3 代码和凭据

API Key、GitHub App 私钥、模型 Key、签名 Key 不进入 prompt、日志、Diff、Capsule、长期记忆和前端 localStorage。Git 操作使用短期凭据或受控连接器。Provider 访问采用最小权限、区域限制、审计和轮换。

### 13.4 供应链

依赖安装和构建必须使用锁文件、可信仓库、镜像 digest、SBOM 和漏洞扫描。Agent 不可以因为构建失败自行切换到未知镜像或下载脚本。插件必须签名、声明权限并经过静态和运行时安全扫描。

---

## 十四、商业化产品与收费设计

### 14.1 版本

**Community**：本地 CLI、确定性计划、基础编辑、基础测试和 SpecProof replay。适合个人和开源。

**Team**：Web 控制台、团队共享仓库、GitHub App、任务队列、基础并行、预算和角色管理。

**Enterprise Cloud**：SSO、SCIM、审计、策略即代码、私有连接、签名证书、用量账本、SLA、多区域和高级模型路由。

**Enterprise Private**：代码不出域、内网模型、私有对象存储、HSM/KMS、定制执行器、离线升级、灾备演练和现场支持。

### 14.2 计费单位

对外建议使用席位、Agent 执行分钟、并发槽位、仓库数量和存储保留期组合。对内记录 token、模型成本、沙箱 CPU、磁盘、网络和工具调用。不要只按 token 收费，因为用户购买的是完成任务的能力和交付可信度。

### 14.3 企业销售所需能力

采购前需要提供数据流图、威胁模型、权限矩阵、SLA、支持等级、备份策略、删除流程、模型数据处理说明、私有化部署架构、升级回滚和审计示例。没有这些材料，技术能力再强也很难通过企业采购。

---

## 十五、逐步开发计划

### M0：现状冻结，1-2 周

交付：Agent 代码地图、接口清单、当前测试基线、依赖锁定、风险清单、任务状态机和工具 Schema 初版。

具体步骤：

1. 固定 `craft`、`agent`、`api`、`mcp`、`sandbox`、`storage` 责任边界。
2. 统一 TaskSpec、Plan、Step、ExecResult、MemoryEntry 和 Evidence 引用结构。
3. 对现有 CLI 任务做 10 个可重复基准，记录成功率和失败类别。
4. 记录工作区 dirty changes，禁止以清理方式破坏用户改动。
5. 为危险动作补审计和审批模型。

验收：新机器可以完成确定性 `craft plan`、`craft run`、`craft resume`；已有 unit、ruff、mypy 基线全绿。

### M1：工具协议和执行器，2-4 周

交付：版本化工具注册表、参数 Schema、工具结果 Envelope、命令白名单、路径沙箱和批准服务。

步骤：

1. 实现 read/tree/glob/grep/diff/status/log 工具。
2. 实现 apply_patch、create_file、format_file 的 digest 和 stale 检查。
3. 实现 test/build/lint/typecheck 的适配器。
4. 增加工具超时、输出截断、资源统计和失败分类。
5. 增加危险命令批准 API 和前端确认面板。

验收：工具参数错误不会执行；越权路径、危险命令和过长输出都有自动化测试。

### M2：仓库理解和上下文工程，4-7 周

交付：规则摄取、符号索引、调用图、依赖图、BM25+图谱检索、上下文预算和压缩。

步骤：

1. 读取 AGENTS/CLAUDE/README/CI/构建文件，生成规则来源图。
2. 为 Python、TypeScript、Java、Go 建立语法和符号索引。
3. 接入引用和调用图扩展。
4. 加入可选 embeddings 和 RRF，保持 BM25 降级。
5. 建立 30 条检索查询基准，测 recall、precision、来源完整性和延迟。

验收：对每个目标符号能展示来源、调用者、被调用者、相关测试和规则；检索服务故障不阻断确定性流程。

### M3：稳定的计划和执行循环，4-6 周

交付：结构化计划 DAG、风险识别、步骤状态机、checkpoint、预算和 STUCK 判定。

步骤：

1. 统一确定性和 LLM 计划输出 Schema。
2. 验证依赖无环、步骤上限、文件所有权和审批标记。
3. 每步持久化开始、结束、工具和文件状态。
4. 支持暂停、恢复、取消和重试。
5. 相同错误三次或没有新证据时停止。

验收：杀死 Worker 后任务可从最近 checkpoint 继续；恢复不会重复危险副作用；预算耗尽进入明确终态。

### M4：代码编辑与跨语言工程能力，6-10 周

交付：AST/符号级编辑、跨文件重构、依赖升级、迁移保护和多生态适配器。

步骤：

1. Python AST 和 TypeScript AST 结构化编辑。
2. Java/Go 符号级编辑和格式化。
3. 接入 Maven、Gradle、npm/pnpm、pytest、go test。
4. 建立 stale context、冲突和用户改动保护。
5. 对依赖和数据库迁移增加人工审批。

验收：100 个跨文件编辑案例中，不能覆盖用户变更；格式、类型、编译和目标测试通过率达到目标。

### M5：自校验和 SpecProof 闭环，4-6 周

交付：Craft 完成后自动生成 ChangeBundle，调用 SpecProof 进行独立验收。

步骤：

1. 统一 Base/Head、Specification、Contract 和 Agent 结果引用。
2. 增加构建、测试、安全、API 兼容和证据门禁。
3. 高风险任务自动升级 DEEP 或 RELEASE。
4. 为 Blocked、Unverified 和 Failed 提供不同的 UI 和通知。
5. 只允许 SpecProof 产生 Merge Certificate。

验收：Agent 不能通过伪造字段获得 VERIFIED；高风险 Finding 缺少真实证据时自动降级或阻断。

### M6：Web 控制台和 IDE，6-9 周

交付：任务向导、实时工作台、计划图、Diff、工具批准、记忆、测试和交付页面；VS Code 第一版。

步骤：

1. 将现有 React Dashboard 扩展为 Agent 工作台。
2. 接入任务 API、SSE、断线恢复、分页和错误码。
3. 实现计划审阅和危险动作批准。
4. 实现 Diff、测试、证据和交付页面。
5. IDE 支持选中代码发起任务、查看计划、接受/拒绝变更和查看测试。

验收：用户不用 CLI 就能创建任务、批准动作、查看修改、取消任务、恢复页面和导出报告。

### M7：并行子代理，5-8 周

交付：角色 Agent、DAG 调度、文件所有权、并发池、结果综合和冲突处理。

步骤：

1. 先实现只读 Explorer 并行。
2. 增加 Test Agent、Security Agent 和 Reviewer Agent。
3. 为写入步骤增加 owned_paths 和临时分支。
4. 实现冲突检测和人工合并。
5. 根据租户预算动态控制并发。

验收：无文件冲突的步骤可并行；有冲突的步骤自动串行或暂停；一个子代理失败不会破坏其他结果。

### M8：企业身份、租户和策略，5-8 周

交付：Organization、RBAC、OIDC/SAML、SCIM、Service Account、策略即代码、审计和租户隔离。

验收：跨租户读写测试全绿；所有危险动作可追溯到人或服务账号；策略版本进入任务和证据。

### M9：Provider、模型路由和经济性，4-6 周

交付：模型注册、Capability Probe、路由、熔断、缓存、token 账本、预算和私有模型适配器。

验收：Provider 429/500/超时可恢复或诚实降级；模型成本可从账本重建；模型请求不泄露秘密。

### M10：Git、PR、CI 和生态，4-7 周

交付：分支、commit、PR、GitHub/GitLab、CI 回调、MCP 客户端和通知连接器。

验收：重复 Webhook 幂等；Push、PR、合并和发布都有权限门；外部工具输出不能改变系统策略。

### M11：评测和发布候选，持续 6-10 周

交付：200 个 Agent 任务、50 个对抗任务、跨平台兼容矩阵、性能基准、故障注入、供应链和发布门禁。

验收：完成率、回归率、预算、人工介入、安全违规、恢复和证据指标达到发布目标；至少完成三类真实仓库试点。

---

## 十六、每周执行模板

每一个开发车道采用相同节奏：

**周一：定义验收**。写用户故事、数据契约、权限、错误路径、测试案例和不做事项。

**周二：实现最小纵向切片**。先打通 API/服务/存储/前端一条真实链路，不做孤立框架。

**周三：补失败路径**。测试超时、取消、重复、权限、空数据、依赖故障和旧版本兼容。

**周四：接入可观测和文档**。指标、日志、审计、运维说明和用户界面同步完成。

**周五：验收和回顾**。运行静态检查、unit、目标集成和基准；记录已验证、跳过、失败和下一步。

不要把 Docker 镜像、Windows 安装包、推送和发布作为每天的默认动作。它们应在阶段出口集中验证，避免开发时间被低价值构建占用。

---

## 十七、测试和发布门禁

### 17.1 Agent 质量门

- 计划 Schema 校验 100%。
- 工具参数错误 0 次执行。
- 目录越界和用户改动覆盖 0 次。
- 危险动作未经批准 0 次。
- 预算超限进入终态 100%。
- Worker 崩溃恢复率不低于 99.9%。
- 相同任务的无效重复工具调用持续下降。
- 失败诊断类别与人工标注的一致率达到目标。

### 17.2 代码正确性门

- 编译、格式、类型、lint 和受影响测试通过。
- 全量测试结果有明确范围，不允许只跑一个容易通过的测试。
- 需求 Contract 有对应测试或真实证据。
- 数据库、消息和权限变更有专门测试。
- SpecProof 报告和 Agent 报告相互独立。

### 17.3 安全门

- Prompt 注入矩阵通过。
- 沙箱无网络、非 root、无 docker.sock、资源限制生效。
- API Key、OAuth、Webhook、服务账号和租户隔离通过。
- 源码、日志、工件和模型 payload 秘密扫描通过。
- 依赖、镜像、SBOM 和插件签名通过。

---

## 十八、运维和部署指南

### 18.1 开发环境

开发者可以先只运行本地确定性 Agent：Python 3.12、Node、项目自身工具链和测试。LLM 不可用时使用确定性规划和规则诊断，结果标注 fallback。此阶段重点是编辑器、执行器、状态机、测试和 API，不要求启动全套基础设施。

### 18.2 团队环境

团队环境启用 FastAPI、Worker、MySQL、Redis、RabbitMQ、对象存储和可选 Mongo/ES。提供一键初始化但不把默认密码带入生产。任务执行在专用 sandbox Worker，Agent API 与控制面分离。

### 18.3 生产环境

生产最少需要：TLS、OIDC、密钥系统、租户隔离、私有对象存储、消息可靠性、沙箱执行、备份、监控、告警、审计、数据保留、恢复演练和升级回滚。高合规客户需要内网模型和 KMS/HSM。

### 18.4 关键指标

任务：排队时长、计划时长、工具调用数、步骤重试、模型延迟、测试时长、恢复次数、人工批准时长、最终完成率和回归率。

资源：CPU、内存、磁盘、沙箱数量、队列深度、对象存储、token、缓存命中和外部 API 调用。

质量：Patch correctness、测试通过率、SpecProof Blocked/Verified、Unverified 率、证据重放、证书签发、误报和漏报。

### 18.5 事故处理

出现错误补丁、越权、秘密泄露、证书错误或沙箱逃逸时，立即暂停新 Agent 任务和证书签发，隔离受影响租户或执行器，保留日志和对象版本，撤销外部集成，通知客户，完成影响评估和回归测试。正确性事故必须有证书撤销或重新验证方案。

---

## 十九、复杂创新能力清单

### 19.1 Contract-aware Coding

Agent 在编写代码时直接读取已批准 Contract，自动为每条 Contract 生成实现任务、测试任务和证据任务。代码完成后显示哪些 Contract 已覆盖、哪些只通过静态分析、哪些尚未验证。

### 19.2 Mutation-guided Agent

SpecProof 生成存活变异体后，把它们转换成 SpecCraft 的测试强化任务。Agent 自动增加测试，重新运行变异战役；如果仍存活，向 Reviewer 提示“当前测试没有证明这个行为”。

### 19.3 Falsifiable Plan

计划不只写成功标准，还写失败条件和反例：什么现象会证明当前方案错误、哪个旧行为必须保持、哪个观察值可以推翻 Agent 假设。Agent 只有在反例检查通过后才能进入交付。

### 19.4 Repository Digital Twin

为大型仓库建立可查询的数字孪生：模块、依赖、API、数据库、消息、部署、责任人、历史回归和运行指标。Agent 在修改前先模拟影响范围，修改后更新图谱并比较风险变化。

### 19.5 Continuous Repair Queue

把 CI 失败、Dependabot、Sentry、生产告警、用户工单和安全扫描统一成受控修复队列。每个修复任务有优先级、SLA、风险、预算和独立验收，Agent 可以自动处理低风险任务，把高风险任务升级给人工。

### 19.6 Learning from Rejections

被 Reviewer 拒绝的补丁、被 SpecProof 阻断的任务和用户手工修正可以转化为脱敏规则和评测案例，而不是直接训练模型。系统记录拒绝原因、错误假设和有效修复路径，用于未来规划和提示词改进。

### 19.7 Cross-agent Neutral Attestation

任何外部 Agent 生成的 ChangeBundle 都可以送入 SpecProof 验收。这样 SpecProof 不绑定单一模型或单一代码 Agent，成为跨 Agent 的独立质量层；SpecCraft 可以是第一方实现，但不是唯一实现。

### 19.8 Human Attention Router

Agent 根据风险和不确定性决定何时打扰人：低风险重复格式化不打断；修改权限、迁移、删除数据、增加网络、发布和证书签发必须请求确认。审批请求只携带能做决策的信息，不把几千行日志扔给人。

---

## 二十、主要风险与禁止事项

### 风险 1：把模型输出当作事实

解决：所有关键结论必须引用工具结果、测试、Diff、Contract 和证据。模型意见使用 `hypothesis` 标签。

### 风险 2：工具越来越多但不可控

解决：统一注册表、Schema、权限、预算、超时和审计；工具越界直接失败。

### 风险 3：并行 Agent 互相覆盖

解决：文件所有权、临时分支、冲突检测、串行化和人工合并。

### 风险 4：上下文膨胀导致质量下降

解决：符号检索、优先级、摘要、来源和预算；不把完整历史对话无限回喂。

### 风险 5：无限修复循环

解决：错误分类、最大轮次、无新证据判 STUCK、预算和人工升级。

### 风险 6：Agent 擅自扩大任务范围

解决：计划的 non-goals、owned paths、Diff 范围门禁和变更前审批。

### 风险 7：商业化过早拆微服务

解决：先用模块化单体 + 独立 Worker 打通纵向闭环，出现明确吞吐和隔离需求后再拆服务。

### 风险 8：只展示成功 Demo

解决：公开失败、降级、未验证和不支持矩阵；用 holdout、对抗样本和故障注入证明能力。

禁止事项：

- 不把默认密码、真实 Key 或私有代码写入文档、代码、日志和测试工件。
- 不让 Agent 默认 push、merge、发布、删除数据或修改生产环境。
- 不让静态猜测升级为 BLOCKER。
- 不把 Redis、缓存或模型输出当作业务事实源。
- 不以全量格式化或大范围重构掩盖真实任务失败。
- 不在没有用户明确要求时反复构建 Windows 安装包、Docker 镜像、提交或推送。

---

## 二十一、最终交付标准

当 SpecCraft 达到商业化目标时，客户应能完成以下流程：

1. 登录组织并连接仓库。
2. 选择一个 PR 或输入任务描述。
3. 查看 Agent 解析出的目标、非目标、风险和结构化计划。
4. 批准或拒绝文件范围、网络、依赖和高风险动作。
5. 实时查看检索、工具、编辑、测试和修复进度。
6. 在发生错误时看到分类、证据和下一步，而不是只看到“模型失败”。
7. 刷新页面、关闭浏览器或重启 Worker 后继续任务。
8. 审阅 Diff、测试矩阵、依赖变化、迁移、回滚和未验证项。
9. 创建 PR 或导出 ChangeBundle。
10. 由 SpecProof 独立验证并生成 Matrix、Finding、Capsule 或 Certificate。
11. 在 Web、CLI、IDE、GitHub Check Run 和 API 中看到一致结果。
12. 在审计、账单、备份、删除和恢复场景中获得可验证记录。

这 12 步全部成立，才可以称为“完整前端后端商业化代码开发 Agent”。仅仅能调用模型、能修改文件、能跑一个测试，不能达到这个标准。

---

## 二十二、立即执行的第一批任务

为了让文档可以落地，推荐从以下顺序开始：

1. 给 `craft` 定义稳定的 `AgentTask`、`Plan`、`Step`、`ToolCall`、`Approval`、`Artifact` 和 `ChangeBundle` Schema。
2. 为工具建立注册表和版本化 Envelope，先覆盖 read、search、diff、patch、test、build、git_status。
3. 给 `craft/loop.py` 接入持久化 Job 投影、取消、租约和恢复，不先做并行。
4. 把仓库规则摄取写成独立模块，先支持 `AGENTS.md`、`CLAUDE.md`、README 和 CI 配置。
5. 为 Python、TypeScript、Java、Go 建立最小符号索引和 30 条检索基准。
6. 为 `craft/editor.py` 增加 stale digest、用户改动分类和结构化 Diff。
7. 把测试、构建、类型检查、安全扫描和 SpecProof 组成自校验门禁。
8. 在 Web 前端加入任务向导、计划审阅、实时工具流、审批和 Diff 页面。
9. 用只读 Explorer、Test Agent、Security Agent 做第一批并行，不立即允许多 Agent 同时改同一文件。
10. 增加 50 个代码任务、20 个对抗任务、10 个断点恢复任务和 10 个危险动作审批任务。
11. 接入 OIDC、租户、RBAC、审计和配额，再做企业集成。
12. 最后再做 GitHub/GitLab PR 自动化、IDE、MCP 客户端、计费和私有化包装。

第一阶段的正确目标不是“做出一个看起来像 Claude 的聊天页面”，而是交付一条可靠的纵向链路：一个真实任务进入系统，Agent 能计划、读取、修改、测试、恢复、解释并把 ChangeBundle 交给独立验收。只要这条链路可重复，后续工具、模型、前端和商业功能才有稳固的承载面。

---

## 二十三、总结

Codex、Claude Code、Cursor 和 Devin 级别的开发 Agent，本质上不是一个模型，而是模型、工具、上下文、执行环境、状态机、记忆、权限、评测、用户界面、基础设施和产品治理的组合系统。真正的技术难点在于：模型犯错时系统不会失控，任务很长时系统不会丢失，仓库很大时系统不会盲目，用户改动时系统不会覆盖，测试失败时系统不会无限循环，外部工具不可信时系统不会被注入，结果交付时系统不会把自己的判断当成证明。

SpecCraft 已经具备一部分正确的内核，下一阶段应该从“能跑的 Agent”进化到“可持续交付的 Agent 平台”。路线必须坚持纵向闭环、先验收后实现、证据优先、明确降级、保留用户改动、限制危险动作、独立验收和真实评测。最终产品不应只追求像行业产品，而应在代码行动效率接近行业先进的同时，凭借 SpecProof 形成更强的可验证性、审计性和企业信任。

当 Agent 能够把一个自然语言任务转化为有边界的计划，把计划转化为受控文件变更，把变更转化为测试和证据，把证据转化为可重放的独立验收，再由人或组织策略决定是否交付时，这个项目才真正进入了工业化和商业化阶段。

