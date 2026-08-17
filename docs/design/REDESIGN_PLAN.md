# SpecProof 改进后的全局设计方案

版本: v0.2 (基于 DESIGN_REVIEW.md 的 P0/P1/P2/P3 结论)
原则: 保持"证据优先"的产品灵魂不动; 修检测核心; 补内核闭环; 清理诚实性死角; 补齐文档。

---

## 1. 改进后的总体架构 (不变 vs 新增)

保持: 需求→Contract→静态检查→反例生成→Base/Head 差分执行→Review Court→矩阵→Capsule→报告/证书。

新增/加固 (本次落地的改动):

CLI (verify/eval/probe/replay)
   - 新增: --llm/--no-llm 开关; verify 结束自动清理 worktree
LangGraph 管线 (12 节点)
   - compile_contracts    规则解析 + LLM 富化 (不变)
   - prepare_base/head    worktree 隔离 (不变, 补 cleanup)
   - collect_diff         符号/注解 diff (不变)
   - run_static_checks    [修复] 注解切分 (嵌套括号) → AUTH 检测恢复
   -                      [修复] token_invalidation 升级为方法级调用点比对
   - generate_counterexamples   LLM→schema→编译 3 次重试 → 确定性模板 fallback (不变)
   - run_differential     [修复] 源码差分证据与测试生成解耦 (测试失败也保留 MAJOR 证据)
   - review_court         [修复] contract_results 合并语义 (不再被覆盖)
   - build_matrix         [修复] 基于合并后的 contract_results 诚实聚合
   - create_capsule / publish_report   (不变)
P1 生产内核 (已有代码, 本次补齐闭环)
   FastAPI /api/v1:  [新增] POST /jobs (Outbox 同事务入库)  [新增] GET /jobs 列表
                     [新增] GET /jobs/{id} 状态  GET /jobs/{id}/progress (SSE, 已有)
   OutboxRelay → RabbitMQ (Publisher Confirm) → Worker (lease + MongoDBSaver checkpoint)
   Worker 终态映射 [修复] 按真实结果: VERIFIED / BLOCKED / FAILED (不再无条件 VERIFIED)
   MySQL=事实源 / Redis=进度与幂等 / MongoDB=checkpoint与工件 / MinIO=大对象 / ES=检索

## 2. 检测核心的正确性模型 (本次修复后)

每个 Contract 的结果只能由"真正跑过的实验"写:
- 静态 checker 只能写 PASS(观察到护栏完好)/FAIL(发现违规)/UNVERIFIED(无对应构造);
- 差分执行只能写 AUTH/http 家族的 PASS/FAIL;
- build_matrix 对多实验做逐合约合并, 合并规则: 任一实验 FAIL→FAIL;
  有 PASS 且无 FAIL→PASS; 全无→UNVERIFIED; 证据引用取 FAIL 证据优先。
- 任何节点不得整表覆盖其他节点的 contract_results (LangGraph 逐节点 merge)。

## 3. 修复清单 (与 DESIGN_REVIEW 编号对应)

| 编号 | 问题 | 修复 | 验证方式 |
|---|---|---|---|
| B1 | 注解切分嵌套括号 | _SPLIT_RE 注解组支持一层嵌套括号; 单测覆盖 @PreAuthorize("isAuthenticated()") | checkers 单测 + 插桩脚本 |
| B2 | contract_results 覆盖 | run_differential 只返回自己实验结果, build_matrix 统一合并 | verify 端到端结果不丢失 |
| B3 | 差分证据耦合 | run_differential 无条件执行源码对比, 与测试执行解耦 | 无 LLM/编译失败时仍有 MAJOR finding |
| B4 | token checker 字符串判断 | 方法级调用点比对 | case-05 eval PASS |
| B5 | 验收测试过期 | 修 test_phase_acceptance (eval 传 --repo); 全量绿 | pytest |
| B6 | 死代码伪造 PASS | 删除 evidence/matrix.py 旧实现 | import 无残留 |
| B7 | worktree 泄漏 | verify 结束/异常时 cleanup | git worktree list 空 |
| B8 | RuntimeWarning | main.py 导入顺序修正 | 运行无警告 |
| B9 | canary 未接线 | 写入 canary_found_in_scan; capsule zip 解包扫描 | 安全测试 |
| B10 | probe extra_body | 原生 HTTP thinking 探测改为 body 内 thinking 字段 | probe 单测 |
| B11 | worker 终态不诚实 | 按管线结果映射 VERIFIED/BLOCKED/FAILED | worker 单测 |
| B12 | API 缺 POST /jobs | 新增 POST /jobs + GET /jobs + GET /jobs/{id}; Outbox 同事务 | TestClient 测试 |
| B13 | README/ADR/CI 缺失 | README.md + docs/adr + docs/architecture + docs/interview + CI workflow | 文件存在 |
| B14 | 文档漂移 | probe docstring、CLAUDE.md 同步为真实行为 | grep 核验 |

## 4. 验收标准 (本次工作结束必须全绿)

1. pytest 全量: 0 failed (需要 Docker 的保持 skip, 不打折扣);
2. ruff check 0 error; mypy strict 通过;
3. eval 10 case: holdout recall 100% (case-01/05/09 全部检出), negative 0 误报,
   adversarial 全检出 → Recall 100%, Precision 100%;
4. 端到端 verify (base→head-v1): 至少 1 个 BLOCKER 带 base_pass_head_fail + H2 DB 证据
   (或 MAJOR 兜底), 6 合约无 UNVERIFIED 丢失, 生成 HTML 报告 + capsule + 拒绝通知;
5. capsule replay 回路 (zip 完整、manifest digest 存在);
6. 安全扫描: canary PASS, 无 CRITICAL/HIGH 泄漏;
7. API 层: POST /jobs → GET /jobs/{id} → SSE 进度 (TestClient 级, 不依赖 Docker);
8. Docker 若可启动: compose.phase0.yml 起 6 服务, 跑真实内核集成测试。
