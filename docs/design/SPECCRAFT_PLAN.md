# SpecCraft — 自主开发 Agent (P7) 设计与实施计划

版本 1.0 · 2026-08-18 · 状态: 已批准, 按里程碑实施中 · 归属: SpecProof 平台新工作流

## 0. 一句话定位

SpecCraft 是 SpecProof 平台内置的自主开发 Agent (写代码 Agent): 接收自然语言需求或代码任务,
自主完成 任务理解 → 规划 → 改代码 → 构建 → 测试 → 自校验 → 交付 的完整闭环;
产出的变更交给同平台的 SpecProof 验收 Agent 独立验证并签发 Ed25519 Merge Certificate。
一句话: SpecCraft 负责"把事做成", SpecProof 负责"证明做得对"。

## 1. 为什么加进 SpecProof 而不是另起项目

1. 闭环价值: 现有 SpecProof 是"验收方", 缺"生产方"。单独验收 Agent 只能等外部 Coding Agent
   (Claude Code / Codex / Cursor) 产出 PR; 有了 SpecCraft, 平台第一次拥有
   "需求进来 → 代码出来 → 证据签收" 的自持循环, 产品从"防火墙"升级为
   "AI 开发 + 独立验收一体化平台"。
2. 复用 80% 基础设施: 沙箱执行、Maven/JUnit 解析、Provider 抽象与能力探测、
   代码符号图谱 RAG、MySQL 状态机、审计、预算、脱敏全部现成, 增量集中在
   "规划 + 编辑 + 自愈循环" 三层。
3. 互相增强: SpecCraft 自校验复用 SpecProof 的 contract/checker;
   SpecProof 的验收结果 (finding) 又回灌给 SpecCraft 作为修复任务 (fix 闭环)。
4. 商业叙事: "实现 Agent 不能给自己签字" 的反面是 "同一个平台先帮你实现,
   再独立验收" — 单兵演示效应更强: 一条命令现场造一个功能, 再现场拦截一个回归,
   最后签一份机器可验证的证书。

## 2. 产品形态与使用方式

### 2.1 CLI 本地模式 (最先交付, M1 起步)
    specproof craft plan "给 UserService 加一个按邮箱查询用户的 REST 端点, 带分页和缓存" --repo .
        → 输出 .specraft/plan.json + 终端计划摘要 (步骤/风险/预计改动文件)
    specproof craft run SPEC --repo . [--max-iterations N] [--no-llm] [--budget-tokens N] [--timeout MIN]
        → 执行计划, 输出: 变更 diff、构建/测试结果、自校验结论、.specraft/{plan,checkpoint,report}
    specproof craft resume --job JOB_ID   → 断点续跑
    specproof craft explain STEP_ID       → 解释某一步的决策依据 (审计可读)
    specproof craft accept JOB_ID         → 把 craft 产物交给 SpecProof verify 验收 (M7 闭环)

### 2.2 API / Control Plane (第二阶段)
POST /api/v1/craft/jobs {spec, repo, budget} → 复用 verification_jobs 10 态状态机 (job_kind=craft);
SSE 进度流; 完成后自动触发 SpecProof verify, 一次交付 code + evidence。

### 2.3 GitHub App 模式 (第三阶段)
issue 描述或 /specproof craft 命令触发; SpecCraft 在隔离 worktree 开发, 推 fix 分支, 开 PR;
SpecProof 自动验证并发布 Check Run / Inline Findings / Merge Certificate。

## 3. 总体架构

需求/任务输入 (自然语言 spec / issue / TODO 描述 / 既有 spec.md)
        │
        ▼
┌─ CraftPlanner (规划层) ──────┐   复用 providers/ (LLM + 能力探测 + JSON Envelope 降级)
│ 任务理解 → 步骤图 (DAG)       │   复用 agent/repo_graph (符号图谱邻域)
│ 风险分类 → 预算分配           │   复用 storage/mysql (状态机 + 审计)
└──────────────┬──────────────┘
               ▼
┌─ CraftExecutor (执行循环) ────────────────────┐
│ ① 读代码 (只读, 图谱邻域注入)                  │
│ ② 生成编辑 (整文件原子写 / 精确 edit)          │
│ ③ 沙箱构建 + 测试 (复用 sandbox/runner, 非root)│
│ ④ 失败诊断: 解析 JUnit/编译错误 → 定位文件/行   │
│ ⑤ 重试收敛 (max_iterations / 预算闸门 / stuck) │
└──────────────┬────────────────────────────────┘
               ▼
┌─ CraftVerifier (自校验层, 可选但默认开) ──┐
│ 复用 SpecProof checkers/契约 + 安全扫描    │
└──────────────┬───────────────────────────┘
               ▼
       交付: 分支/PR + diff + 报告
               │
               ▼ (平台闭环, M7)
   SpecProof verify → Merge Certificate (Ed25519)

## 4. 核心模块设计 (详细)

### 4.1 任务理解与规格解析 craft/spec.py
输入归一化, 三种输入形态: 纯文本任务描述 / 结构化 JSON (验收条件列表) / 既有 spec.md。
输出统一 TaskSpec:
{
  "title": "按邮箱查询用户端点",
  "description": "在 UserController 增加 GET /users/by-email?email=... 支持分页与缓存",
  "acceptance_criteria": ["200 返回 UserResponse", "未知邮箱 404", "命中缓存不查库"],
  "forbidden_changes": ["不得移除既有端点的 @PreAuthorize", "不得改 UserResponse 字段名"],
  "affected_area_hint": "controller/service/repository"
}
确定性解析器先行 (编号/关键词规则), LLM 富化可选; 与 SpecProof requirement parser
共享 schema 约定 — 同一份 spec 既能驱动开发又能驱动验收 (闭环关键设计: craft 的 spec
原样可喂给 verify)。

### 4.2 计划生成 craft/planner.py
Plan schema:
{
  "steps": [
    {"id": "s1", "kind": "understand|modify|add|test|verify",
     "target_files": ["UserController.java"], "intent": "增加查询端点",
     "success_criteria": {"type": "compile|test_green|grep", "value": "..."},
     "deps": []}
  ],
  "risk_classification": {"auth": true, "migration": false, "mq": false, "public_api": true},
  "budget_alloc": {"iterations": 8, "tokens": 40000}
}
规则引擎: 按任务类型 (加端点/修 bug/重构/迁移/加测试) 映射步骤模板 (步骤数上限 12);
LLM 模式: 单次调用输出 JSON Action Envelope 计划, schema 校验失败退回规则模板;
硬约束: 每步 success_criteria 必须可机械判定 (编译退出码 / 指定测试名 / grep 断言), 无循环依赖。

### 4.3 代码编辑 craft/editor.py
工具集与语义:
- read_file(path, offset, limit) → 带行号内容 (上限 2000 行/次);
- write_file(path, content) → 整文件原子写: 临时文件 + os.replace, 保留行尾约定, 写前备份到 .specraft/backup/;
- apply_edit(path, old, new) → 精确子串替换, old 必须唯一命中, 否则报错不落盘 (防止漂移编辑);
- move/delete → 同样先备份;
- 编辑事务: 一个步骤的多文件编辑全部落盘后再构建; 构建失败保留现场供诊断;
  同一步骤连续 N 次失败 → 回滚该步骤 (git 语义可用 worktree 的 reset)。

### 4.4 执行与反馈 craft/executor.py + craft/loop.py
执行器: 命令白名单 (mvn / gradle / npm / pytest / cargo 等, 配置可扩), 一律经
sandbox.run_sandboxed (非 root / 断网 / 资源限额 / 超时 / 输出截断);
解析 surefire/JUnit XML (defusedxml, 复用现有解析器) 提取失败用例与堆栈前 N 行。
循环: while iterations < N and not all_green: 诊断失败 → 生成修复编辑 → 重跑。
收敛规则: 同类错误连续 3 次 → 标记 stuck 并诚实上报 (不无限烧预算);
每轮迭代把 (诊断, 编辑, 结果) 写入 checkpoint, resume 从最后一个绿步骤之后继续。

### 4.5 自校验 craft/verify.py
每次迭代后跑三层: ① 构建 + 全量单测 (硬门, 退出码 0, 由 loop 的 compile/test_green
criteria 保证); ② 复用 SpecProof checker 家族做静态契约检查 (安全注解/事务/事件/唯一
约束, 只读调用); ③ 安全扫描 (canary/密钥)。自校验不过不交付, 结论写进 report (可重放)。

M3 实现 (2026-08-18):
- 入口 `craft.verify.self_verify(changed_files, workspace, *, base_files=None)`
  → `{"status": "passed"|"failed"|"skipped", "findings": [...], "note": "..."}`,
  全部只读; `base_files` 为可选的 Base 快照 (loop 从 Editor 备份目录还原每次改动的
  原始内容, 供 diff 型 Java 检查器观察回归)。
- ①安全层: 复用 `agent.security_scanner.scan_directory` (公开函数) 全仓扫描并过滤到
  改动文件; 另对每个改动文件做 canary 哨兵 (SPECPROOF_CANARY_) 子串检查 (扫描器按
  设计跳过 canary 命中, 哨兵检查由 verify 显式执行)。CRITICAL/HIGH 密钥或 canary 命中
  → failed; MEDIUM/LOW 记入 findings 但不拦门 (与扫描器自身 passed 口径一致)。
- ②契约层: 改动含 Java 文件且 agent/checkers 可用时, 调用 `run_contract_checks`
  (checker 家族注册表公开入口) 跑 Base→Head 差分; 任一契约 finding → failed。
  无 Base 快照 / 检查器不可用 / 检查器抛错 → 记 note, 不伪造通过 (skipped+原因)。
- ③其他语言文件跳过契约检查器, note 标注。
- loop 接线: `CraftLoop(skip_self_verify=False)` 默认开; `_finish()` 写 report 前跑
  门, `self_verify.status=failed` 时终态 DONE 覆盖为 FAILED (证据留痕), 编辑不回滚
  (report 诚实说明); `--no-self-verify` → status=skipped + 原因。
- CLI: `craft run --self-verify/--no-self-verify` (默认 --self-verify), 终态打印
  self_verify 结论 (status + findings 数)。
- 已知限制: 位于扫描器策略排除路径 (tests/ 等) 的改动文件仅做 canary 检查; 契约层
  无 Base 快照时对新增 Java 文件无可观察对象 (诚实 skipped)。

### 4.6 上下文与检索 craft/context.py
只读复用 repo_graph: 改动文件的调用者/被调用者邻域注入 LLM 上下文 (默认 2 跳),
避免把整个仓库塞进 prompt; 无 LLM 时用 grep 邻域兜底; 上下文按 token 预算截断。

### 4.7 状态机与持久化 craft/job.py + storage/
状态机 (复用 10 态语义, job_kind=craft):
QUEUED → PLANNING → PLAN_READY → EXECUTING → SELF_VERIFYING →
DONE | FAILED | CANCELLED | STUCK | EXPIRED
(PLAN_READY 支持人工确认后进入执行 — 与"Contract 必须人工批准"的哲学一致: 计划可审、可改、可拒)
持久化: MySQL 行 (job/stages/audit) 为业务事实, .specraft/ 本地 checkpoint 为运行副本;
审计每次编辑/命令/LLM 调用 (谁、何时、为什么); kill 后 resume 续跑。

### 4.8 预算与安全 craft/budget.py
默认预算表 (环境变量可覆盖):
- max_iterations = 12; max_tool_calls = 40; max_steps = 12;
- token 预算 = 200000/任务; 时间 deadline = 60 分钟/任务; 费用上限按 provider usage 折算;
超限 → 停止并交付当前状态 + 诚实报告 (绝不静默截断)。
安全 (与 §0/§12 一致): 编辑只发生在 throwaway worktree 拷贝; 无宿主环境变量、
无 docker.sock、无密钥注入; prompt injection 防护: 仓库文本一律视为数据, 不得进入系统指令位。

### 4.9 交付 craft/deliver.py
输出: git diff + 提交建议 (不自动 push 主分支); .specraft/report.json (步骤/结果/诊断链/审计);
可选: 自动创建分支; GitHub 模式: 开 PR + 触发 SpecProof verify。

### 4.10 与 SpecProof 的闭环接线 (M7)
craft accept JOB_ID → 自动调 verify → BLOCKED 时 finding 转成 craft 新任务 (修复循环, 最多 3 轮)
→ 通过后签发 Ed25519 Merge Certificate。这是 SpecCraft 相对独立 CLI 工具的核心差异。

## 5. 复用清单 (不重造)
providers/ (LLM 客户端 + 能力探测 + JSON Envelope); sandbox/runner (执行隔离);
agent/repo_graph + storage/elasticsearch (检索); agent/checkers (自校验);
storage/mysql + storage/migrations (状态机/审计); integrations/github_checks (PR/Check Run);
observability/ (结构化日志/metrics/trace); evidence/ (报告/证书格式)。

## 6. 里程碑与实施步骤

M1 骨架 (本轮启动): craft/ 包 + 确定性计划器 + 编辑器 + 沙箱执行 + 最小循环 +
CLI (craft plan/run) + 单元测试; 验收: 单测全绿 + fixture 仓库演示
"改一个方法让失败测试转绿" 的确定性收敛 (无 LLM)。
M2 LLM 接线: planner/诊断走 provider (Envelope 降级); 无 key 诚实降级为规则模式;
验收: mock provider 单测 + 真实端点冒烟 (若有可用端点)。
✅ M2 状态 (2026-08-19): 已接线 — craft/llm.py (LLMClient: TokenBudget 闸门 500000
默认/CRAFT_TOKEN_BUDGET/--budget-tokens, reasoning 只进内存 journal, ADR-017);
planner.compile_plan_llm 真实现 (assemble 稳定前缀 + JSON 输出契约 + Plan/Step schema
校验 + 步骤上限 12 + 无循环依赖, 任何失败退回确定性并记 llm_fallback_reason);
loop 诊断-修复 (diagnose 模板 + JSON 编辑提案 apply_edit/write_file 经 Editor 落盘,
非法输出按 M1 语义 FAILED); CLI craft plan/run --llm/--no-llm (默认有 key 则 llm,
无 key 打印 "LLM unavailable ... falling back to deterministic"); 单元测试
tests/unit/test_craft_llm.py; 真实端点冒烟已通过 (2026-08-18, speccraft-demo):
真实 V4 Pro 计划 mode=llm 4 步 (grep "def double" → compile → test_green →
test_green); run 由模型诊断并 apply_edit 修复 calc 后 1 次迭代收敛 DONE;
usage 2 calls / prompt 1620 / completion 7090 / reasoning 6574 / cache-hit 512
(plan 调用命中稳定前缀 KV 缓存) / 计费 16443.2 / 上限 500000; 产物零
reasoning 泄漏 (ADR-017 扫描通过)。
✅ M3 状态 (2026-08-18): 已交付 — craft/verify.py 自校验硬门 (密钥/canary 扫描 +
Java 契约检查器, 全只读复用 agent/security_scanner 与 agent/checkers 公开入口);
loop._finish 默认跑门, failed → 终态 FAILED (编辑不回滚, 报告诚实说明);
CLI craft run --self-verify/--no-self-verify (默认开, 跳过时 report 标注 skipped);
单元测试 tests/unit/test_craft_verify.py (17 例, 含密钥/canary/契约回归拦截、
检查器不可用/抛错诚实 skipped、loop 覆盖 FAILED、CLI 两档); 门禁 ruff/mypy/bandit
全绿; 真实冒烟: speccraft-demo craft run --no-llm --fix-module → DONE 且
self_verify.status=passed; 植入假密钥 fixture → self_verify failed 拦下
(result=FAILED, 退出码 1)。验收: 植入回归的 fixture 被自校验拦下 (0 交付)。
M4 持久化: MySQL job 行 + checkpoint resume + 审计表; 验收: kill 后 resume 续跑通过。
M5 检索注入: repo_graph 邻域注入 + ES 检索 (可选); 验收: 上下文命中率指标。
M6 交付: 分支/PR/diff 报告 + GitHub App 触发; 验收: E2E (issue → PR → Check Run)。
M7 闭环: craft accept → verify → certificate → fix 循环; 验收: 旗舰场景一条命令出"代码+证书"。
M8 评测与试点: 10 个微型任务集 + 指标 + "裸 LLM 直接改"基线对比 + 3 个真实仓库试点。

## 7. 评测与门槛
craft 自身: 任务完成率 ≥ 70% (10 任务集); 平均迭代 ≤ 6; 预算内完成率 ≥ 80%;
自校验拦截率 = 100% (注入回归必被拦); 0 密钥泄露。
平台红线: 不降低 SpecProof 15 项 Go/No-Go 任何一项; 100 金案例评测不回归。

## 8. 目录结构
craft/{__init__,spec,planner,editor,executor,loop,verify,context,job,budget,deliver}.py
cli/specproof/commands/craft.py
tests/unit/test_craft_{spec,planner,editor,loop}.py
.specraft/ (运行时产物, 进 .gitignore)
docs/design/SPECCRAFT_PLAN.md (本文档)

## 9. 风险与诚实降级
模型不可用 → 规则模式 (确定性模板) 兜底, 报告标注 craft_mode=deterministic;
循环发散 → stuck 上报; 构建环境缺失 → 明确报错, 不伪装成功;
任何"完成"声明必须附带: 构建退出码 0 + 全部单测绿 + 自校验无 high finding (可重放)。

## 10. 总验收标准 (全部完成后)
一条命令: specproof craft run "..." --accept 在 demo 仓库完成一个新功能并拿到 SpecProof
Merge Certificate; 全量门禁 (ruff/mypy/bandit/pytest) 全绿; SpecProof 15 门槛与
100 金案例评测不回归; 使用/架构/运维文档齐全。

## 附录 A. CLI 参数全表 (M1 交付)
craft plan SPEC_TEXT | SPEC_FILE   --repo PATH [--llm|--no-llm] [--output DIR]
craft run  SPEC_TEXT | SPEC_FILE   --repo PATH [--max-iterations N] [--budget-tokens N]
                                   [--timeout MIN] [--llm|--no-llm]
                                   [--self-verify|--no-self-verify] [--dry-run]
craft resume --job JOB_ID          [--max-iterations N]
craft explain STEP_ID --job JOB_ID
craft accept JOB_ID                [--depth FAST|DEEP|RELEASE]   (M7)

## 附录 B. 关键产物 schema
checkpoint.json (每次迭代追加):
{ "job_id", "step_id", "iteration", "diagnosis", "edits_applied": [...],
  "build_result": {"exit_code", "failed_tests": [...], "log_tail": "..."},
  "verdict": "progress|green|stuck", "timestamp" }
report.json (终态):
{ "job_id", "mode": "deterministic|llm", "result": "DONE|FAILED|STUCK|CANCELLED|EXPIRED",
  "steps": [{"id","kind","status","iterations","evidence"}],
  "diff_stat": {...}, "self_verify": {...}, "budget_used": {"tokens","iterations","seconds"},
  "audit_trail": [...] }

## 附录 C. 状态机转移表 (job_kind=craft)
QUEUED → PLANNING (plan 生成中)
PLANNING → PLAN_READY (计划可审) | FAILED (无法成计划)
PLAN_READY → EXECUTING (批准/自动批准策略) | CANCELLED
EXECUTING → SELF_VERIFYING (全绿) | FAILED | STUCK | CANCELLED | EXPIRED
SELF_VERIFYING → DONE | FAILED (自校验不过)
终态 DONE/FAILED/STUCK/CANCELLED/EXPIRED 不可变 (与 verification_jobs 一致)

## 附录 D. 预算默认值 (环境变量 CRAFT_* 可覆盖)
CRAFT_MAX_ITERATIONS=12, CRAFT_MAX_STEPS=12, CRAFT_MAX_TOOL_CALLS=40,
CRAFT_TOKEN_BUDGET=200000, CRAFT_TIMEOUT_MINUTES=60, CRAFT_MAX_PARALLEL_JOBS=2
(单机 16-32GB 目标: 同时 1-2 个 craft 任务, 与 DEEP 档验证共用预算)

## 附录 E. 10 个微型评测任务集 (M8, 每个都能在 demo 仓库上机器判定)
1 加只读查询端点 (分页); 2 加写端点 (含校验与事务); 3 修逻辑反转 bug;
4 修错误路由键 bug; 5 移除死代码并保持测试全绿; 6 给既有方法补 JUnit;
7 把重复逻辑抽公共方法 (等价重构, 零行为变化); 8 加 Redis 缓存 (cache-aside + TTL);
9 修 N+1 (批量查询); 10 给公开端点补 @PreAuthorize 并写授权测试。
判定: 编译+测试+自校验三绿 = 完成; 每个任务配 1 个"陷阱变体" (需求里埋一个会导致回归的诱导),
测自校验拦截率。

## 附录 F. Prompt 设计与注入防御
系统指令固定且不含仓库文本; 仓库代码/README/issue 只作为"数据段"拼接,
并以哨兵行分隔, 数据段内任何"忽略之前的指令"类文本都不得改写系统段;
规划/诊断两步使用 thinking 模式, 工具循环使用非思考模式 (与 provider 能力探测降级一致);
每步 LLM 输出过 JSON schema 校验, 失败重试一次后回退规则模板。

## 附录 G. 可观测指标 (新注册, 命名沿用 observability/metrics.py 约定)
specproof_craft_jobs_total{result}, specproof_craft_iterations_total{step_kind},
specproof_craft_edit_files_total, specproof_craft_llm_tokens_total,
specproof_craft_loop_seconds{step_kind}, specproof_craft_stuck_total

## 附录 H. 与既有代码的精确接口点
sandbox.run_sandboxed(command, workspace, timeout, mode) — 执行所有构建/测试;
providers.get_provider() + chat(json_envelope) — LLM 规划/诊断;
agent.repo_graph.build_graph / expand_hits — 上下文邻域;
agent.checkers (family 注册表) — 自校验静态层;
storage.mysql 状态机行 (job_kind='craft') + storage/outbox (M4 起);
integrations.github_checks.create_check_run / inline comments — M6。

## 附录 I. 风险表
| 风险 | 概率 | 影响 | 缓解 |
| 模型幻觉改坏代码 | 高 | 高 | 全部改动走沙箱验证, 自校验硬门, 回滚机制 |
| 循环发散烧预算 | 中 | 高 | 预算闸门 + 同类错误×3 stuck + 时间 deadline |
| prompt 注入 | 中 | 高 | 数据/指令分段 + 白名单命令 + 沙箱非root |
| 断点续跑状态漂移 | 中 | 中 | checkpoint 双写 (MySQL + 本地), 恢复时校验 hash |
| 与验收 Agent 口径不一致 | 低 | 中 | 共享 spec/contract schema (4.1/4.5) |
| 评测集过拟合 | 中 | 高 | 陷阱变体 + holdout 子集 (沿用 split.json 纪律) |

## 附录 J. 实施顺序与依赖
M1 (本轮) → M2 依赖 M1 → M3 依赖 M2 的诊断输出 → M4 依赖 M1 状态机雏形 →
M5 可与 M3/M4 并行 → M6 依赖 M4 → M7 依赖 M3+M6 → M8 收口。
每里程碑收口: 全量门禁 (ruff/mypy strict/bandit Medium+=0/pytest) 必须全绿,
禁止把"下个里程碑"的东西伪装成"已完成"。
