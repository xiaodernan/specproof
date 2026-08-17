# SpecProof 全盘设计评审报告

日期: 2026-08-17
评审范围: D:\experim 全仓 (含 specproof-phase0 与 specproof-clean-clone-gate 两代实现,
以 specproof-clean-clone-gate / feature/interview-hardening 为当前主线)
评审方法: 通读全部文档 (PRODUCTION_SPEC 4x9、PROMPT_PACK、CLAUDE.md)、62 个 Python 模块、
23 个测试文件、10 个 golden case、demo Spring Boot 工程; 并实测运行 verify 管线、
节点级插桩、pytest 全量、git 结构核验。

---

## 1. 这个项目是什么

SpecProof = **AI 变更验收防火墙 (AI Change Acceptance Firewall)**。
一句话: "实现 Agent 不能给自己签字; SpecProof 用可执行证据证明一个 AI PR 是否真的完成需求。"

输入: Requirement + Acceptance Criteria + 一个 AI 生成的 PR (Base/Head 两个 commit)。
处理: 需求 → Contract 编译 → Base/Head 隔离 worktree → 静态 Contract Checker →
LLM/模板生成 JUnit 反例测试 → 真实 Maven 差分执行 (Base 通过/Head 失败) →
H2 文件级 DB 状态取证 → Review Court (Prosecutor/Defender/Judge 三审) →
Requirement-to-Evidence Matrix → Bug Capsule (可重放 zip) → HTML 报告 + 证书/拒绝通知。
输出: 每个 Contract 有 PASS/FAIL/UNVERIFIED + 证据引用; BLOCKER 必须带可重放证据。

区别于普通 AI Code Review: 输出不是"评论", 而是**每一条需求的执行证据**;
验证 Agent 与实现 Agent 隔离; Base/Head 差分归因; 高等级结论必须有可重放实验支撑。

## 2. 当前真实状态 (实测)

| 项 | 实测结果 |
|---|---|
| 单元+安全测试 | 108 passed, 13 skipped (跳过的是需要真实 MySQL 的状态机 DB 测试) |
| 全量测试 (排除差分) | **182 passed, 3 failed, 27 skipped** (3 个失败在 test_phase_acceptance.py) |
| 端到端 verify (base→head-v1 旗舰案例) | **0 findings, 6 合约全 UNVERIFIED, 判定 NEEDS REVIEW —— 检测核心是坏的** |
| eval 上次结果 (eval-run.log) | Recall 62.5% (5/8), Precision 100%, 3 个 MISS: case-01/05/09 |
| 节点级插桩 | compile 6 合约正常; collect_diff 找到 @PreAuthorize 移除; 但 static_findings=0 |
| Docker | Docker Desktop 已安装但 daemon 未启动 → 所有真实基础设施集成测试被 skip |

**结论: 项目的"诚实"设计非常好, 但当前主线检测核心有两个实锤 bug,
旗舰演示跑不出结果; 验收测试红; P1 生产内核代码齐全但从未真实跑过。**

## 3. 设计优点 (值得保留, 也是面试亮点)

1. **产品定位锋利**: 不是"更多 AI 评论", 而是"独立验收证据"。护城河清晰 (Requirement-to-Evidence
   Matrix、Proof-Carrying Finding、Semantic Differential Execution、Bug Capsule)。
2. **证据政策严格且全链路一致**: BLOCKER 需 6 条件 (approved contract + 真实 Base/Head 执行 +
   Head 归因 + DB 证据 + 可重放 + confidence>=0.90); 静态分析封顶 MAJOR; UNVERIFIED 绝不伪造为 PASS;
   SHA-256 只叫 digest 不叫 signature。这条政策贯彻在 checker、court、matrix、certificate、CLI verdict 各处。
3. **Base/Head 差分是真实执行**: 注入同一 JUnit 测试到两个 worktree, 真跑 Maven, 并读 H2
   文件库做 DB 状态取证 —— 这是"可执行证据", 不是模型感觉。
4. **评测纪律**: 10 golden case 划分 holdout/negative/adversarial, 支持确定性模式 (LLM off) 复现;
   每次 eval 用 scenario.json 固定 ref, 结束后清理 worktree。
5. **Provider 防御性工程**: 10 维能力探测、lazy probe、JSON Action Envelope 降级、
   thinking/tool-call 分场景开关 —— 符合"第三方网关不可信"的原则。
6. **P1 可靠性内核代码完整**: MySQL 状态机 (CAS 迁移)、Transactional Outbox (SKIP LOCKED)、
   RabbitMQ Publisher Confirm + DLQ + 重试 + 幂等、Redis Stream/lease/budget、MongoDBSaver
   checkpoint 恢复、MinIO digest、SSE Last-Event-ID、10 场景故障注入测试 —— 设计正确, 代码在。
7. **安全姿态**: 无真实 Key、canary 自检、subprocess 参数列表无 shell 注入、仓库内容视为不可信输入。

## 4. 实测发现的问题清单

### P0 — 检测核心坏了 (旗舰案例跑不出结果)

**B1. 注解切分正则无法处理嵌套括号 → AUTH 检测失效。**
agent/checkers/java_source.py 的 `_SPLIT_RE` 注解组 `@\w+(?:\([^)]*\))?`
遇到 `@PreAuthorize("isAuthenticated()")` (括号嵌套) 无法吞掉注解,
导致 Base 方法的注解被丢弃: base 的 changeEmail 块只剩方法体 (无 @PutMapping/@PreAuthorize),
checker 的 mutating+secured 条件永远不满足 → 0 finding, base_observed 也为 false。
实测: 节点级插桩显示 static_findings=0, AUTH-01 永远 UNVERIFIED。
(讽刺的是 @Transactional 无参数所以没事, 这也是 eval 里 case-02/08 能过而 01/09 不过的原因。)

**B2. contract_results 跨节点互相覆盖。**
run_differential 返回自己的 contract_results (只含 AUTH/http 实验), LangGraph 用它
**整体替换** run_static_checks 已经写好的 5 条 PASS。CLI 实测: 6 条合约全部 UNVERIFIED,
而节点级插桩证明静态检查明明 5 PASS。矩阵在最后一步把证据丢了。

**B3. 源码差分证据与测试生成耦合。**
run_differential 里 `_check_http_diff` 只有在"生成了测试且跑完"之后才执行;
测试生成/编译失败时, 连静态源码级回归证据也一并丢弃 → 报告中什么都不剩。

**B4. token_invalidation 检查器是整文件字符串存在性判断。**
case-05 的 Head 只删了调用 `invalidateOldTokens(userId);` 而保留了私有方法定义,
检查器 (全文件 contains) 判"未删除" → MISS。需要方法级调用点比对。

### P1 — 测试与验收失配

**B5. 验收测试过期**: test_phase_acceptance.py 用旧签名调 eval (缺 --repo) → 2 个失败;
test_full_pipeline_produces_all_artifacts 因 B1 而 0 findings → 失败。当前主线 3 red。

### P2 — 工程卫生 / 死代码 / 小 bug

**B6.** evidence/matrix.py 是死代码, 且语义与诚实政策相反 (无 finding 的合约直接 PASS);
build_matrix 节点已用自己的实现, 该模块应删除或对齐语义, 避免面试审代码时被抓。
**B7.** verify 命令不清理 worktree (每次运行泄漏 2 个 worktree + 临时目录; 只 eval 有清理)。
**B8.** 每次运行出现 RuntimeWarning: 'cli.specproof.main' found in sys.modules —— 导入顺序问题。
**B9.** 安全扫描器: canary 结果从未写入 SecurityScanResult.canary_found_in_scan
(报告永远打印 Canary test: FAIL); _EXCLUDE_PATTERNS 排除 *.zip, 而 capsule 本身就是 zip,
宣称"扫描 capsule"实际没扫 zip 内容。
**B10.** capability_probe 的 thinking 检查把 `extra_body` 放进了 httpx 的 JSON body
(那是 OpenAI SDK 概念), 原生 HTTP 探测会误报 thinking 能力。
**B11.** worker._handle_job 完成后无条件 transition VERIFIED —— 无视管线实际判定
(有 BLOCKER 结果时应该 BLOCKED, 有 errors 应该 FAILED)。终态不诚实。
**B12.** api/server.py 只有 /health 和 SSE, 没有 POST /jobs (无法通过内核创建任务),
GET /jobs/{id} 状态查询也没有; P1 内核闭环缺一半。
**B13.** 没有 README.md (pyproject 的 readme 指向不存在的文件, sdist 会失败);
spec 第 22 节要求 17 个 ADR 一个都没有; 没有 CI workflow。
**B14.** 文档漂移: capability_probe docstring 声称结果写 MySQL provider_capabilities +
Redis 缓存, 实际未实现; CLAUDE.md 与代码多处不一致。

### P3 — 结构性设计意见 (不改也能跑, 改后更强)

**S1.** 管线是纯线性 12 节点; spec 的 P1 设计 (parallel_static_checks、条件分支、
风险调度三档 FAST/DEEP/RELEASE) 尚未体现 —— 面试要讲"深度 agent"时, 可以在后续加
并行 fan-out 与条件路由 (LangGraph 天然支持)。
**S2.** use_llm 默认值: state 默认 True, eval 显式 False, verify CLI 无开关 —— 确定性面不一致。
**S3.** 错误守卫只在 prepare_head 之后短路; 后续节点错误只记录不中断 (可接受, 但不对称)。
**S4.** 硬编码 demo 假设 (测试注入路径 com/specproof/demo、H2 路径候选) 未参数化 —— Phase 0 可接受。
**S5.** split.json 的 holdout 标准 (recall=1.0, blocker_confidence>=0.90) 没有在 eval 输出中计算执行。
**S6.** observability 模块存在但管线未接入 OTel; 无结构化日志。

## 5. 修复优先级 (已按此执行, 见 REDESIGN_PLAN.md)

P0: B1→B4 (检测核心)  → P1: B5 (验收绿) → P2: B6→B14 (卫生/内核闭环) → P3: 文档与演进路线。
