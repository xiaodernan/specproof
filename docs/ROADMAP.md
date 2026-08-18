# SpecProof Roadmap

## 已完成 (Phase 0 + P1 内核 + P2 契约编译器)

- [x] P0 演示闭环: 需求→Contract→Base/Head 差分→反例测试→矩阵→Capsule→报告/证书
- [x] P0.5 诚实化: 证据政策、digest 命名、Maven Wrapper、真实差分、金案例划分
- [x] P1 内核: MySQL 状态机+Outbox、RabbitMQ 可靠性、Redis lease/Stream/预算、
  MongoDBSaver checkpoint、MinIO digest、SSE Last-Event-ID、10 故障场景测试
- [x] 检测核心修复: 嵌套括号注解切分、方法级 token 调用比对、contract_results
  合并、源码差分与测试生成解耦 (2026-08-17)
- [x] 内核闭环: POST /jobs + GET /jobs + 状态查询 + worker 诚实终态 (2026-08-17)
- [x] P2-1 结构化需求解析器 agent/contracts/parser.py:
  编号章节/验收标准/禁止变更/优先级, LLM 富化 + schema 校验
- [x] P2-2 契约候选编译器 agent/contracts/compiler.py:
  需求→checker 家族映射、仓库宪法规则提取、去重、family id 映射
- [x] P2-3 契约注册表与人工审批 agent/contracts/registry.py + specproof contract CLI:
  propose/list/approve/reject/revoke, 审计表, spec_digest 版本隔离
- [x] P2-4 Checker 注册表扩充: OPENAPI-01 端点面检查器 (7 个检查器)
- [x] P2-5 ES 仓库级检索: symbol 级分块索引 + BM25 检索 +
  retrieve_repository_context 节点接入 13 节点管线 (诚实降级)
- [x] P2-6 审批契约接入证据政策: verify --use-approved-contracts,
  Review Court 条件 1 检查 approved 标志
- [x] 企业级加固 (P0/P1): 实验沙箱、API 鉴权限流、传输脱敏、版本化迁移、
  10 态状态机+任务取消、审计表、CI 修复+夜间评测 (2026-08-17)
- [x] 企业级差距审计: docs/design/ENTERPRISE_AUDIT.md (A/B/C/D/E 全量清单)
- [x] P2-b 宪法检查器: forbidden_changes 条款确定性执行 (constitution_check)
- [x] 代码符号图谱 RAG: 调用图邻域扩展 + LLM 契约编译接入 (端到端)
- [x] Job 摘要持久化 + Web Dashboard (静态前端 + SSE 实时进度)
- [x] 可观测性基线: /metrics (Prometheus) + 请求计数中间件
- [x] 部署物: Dockerfile.api/worker + compose.production.yml
- [x] P5 核心: Ed25519 签名证书 (in-toto 风格, 签名/验证/密钥管理)
- [x] P0-A4: 生产配置守卫 (默认口令 fail-fast)
- [x] P3 核心: 全栈状态差分实验室 (MySQL/Redis/RabbitMQ 快照+语义归因)
- [x] P4 核心: 源码级变异测试 (4 算子+战役+KILLED/SURVIVED 分类)
- [x] C1/C2: JSON 结构化日志 (job_id/trace_id) + OTel 插桩接入
- [x] DEEP 档接线: 变异战役 + 全栈状态差分进 14 节点管线 (--depth DEEP)
- [x] Spring Boot Control Plane 起步 (租户实体/REST/探针, mvnw 实测通过)
- [x] P5: GitHub webhook 验签 (X-Hub-Signature-256, fail-closed)
- [x] 高并发高可用验证: 恰好一次消费/租约互斥/ack 前崩溃重投
- [x] 指标下沉 observability: worker 完成计数/时长 + outbox 积压 gauge
- [x] RELEASE 档收口: capsule manifest_digest canonical 校验语义统一
  (producer/verifier/测试三处一致, 存储格式与完整性校验解耦)
- [x] 负样本扩展: case-11 重构重命名 / case-12 纯注释 - 端点表面降为
  (verb, path); eval 12 案例 Recall/Precision/F1 全 100%, 0 误报
- [x] 安全扫描门禁: bandit Medium+ 归零 (B608/B104/B108 修复),
  CI 新增 security job
- [x] Control Plane 扩展: ControlPlaneUser/UserController +
  VerificationJobView 只读投影/JobController (租户 scoped)
- [x] GitHub App Check Runs 端到端: RS256 JWT 双步认证 + create/update
  接线 (webhook 建单 → worker 终态 → CLI --publish-check), 迁移 0004
- [x] Outbox 信封契约修复: relay 拍平 wire 消息 (嵌套 payload 字符串
  从未被 worker 扁平读端消费 - 真 MQ 路径的潜在洞) + wire-contract 测试
- [x] Control Plane × Runtime 端到端: GitHub webhook → CP 验签/去重/
  事务性建单 → CP outbox 中继 (publisher confirm) → RabbitMQ → Python
  worker → CP 只读回读; mvnw test 9/9 绿
- [x] 运维手册: docs/operations/RUNBOOK.md
- [x] specproof baseline 命令: "只看 Diff" 基线对照 (Go/No-Go #14),
  确定性 diff-reader + LLM 模式, 同口径判定, delta/门槛报告
- [x] 金案例 12 → 17: adversarial 负样本 ×4 (等价组合注解/接口级安全/
  纯重缩进/收紧角色) + execution-only 正样本 ×1 (守卫取反),
  标签以 honest base 为父隔离构建, head 编译实测通过;
  eval 17 案例 100/100/100, 0 误报
- [x] 检测器等价性加固: 自定义安全注解等价集 + 接口级方法安全回退
- [x] 执行级检测升级: 契约驱动的差分测试 (UNIQUE duplicate/fresh),
  surefire 失败方法 → 契约归属; 差分层委托共享 AUTH checker
- [x] 基线对照实测: 20 案例 +41.7pp recall / +12.5pp precision -
  **Go/No-Go #14 门槛通过** (baseline-report.md)
- [x] execution-only 正样本 ×3 (错误路由键/静默损坏/校验放宽) +
  EVENT 差分测试 (mock RabbitTemplate 调用断言) + 存储行断言 +
  Review Court NONE 过滤; eval 20 案例 100/100/100
- [x] P5 GitHub App 余项: Inline Finding 评论 (integrations/inline_comments,
  hunk 锚点/去重/上限) + Fix 审批流 (agent/fixes + specproof fix/approve,
  drift guard + 编译验证门)
- [x] 第十轮全量审计 (2026-08-18): 拆穿"20 案例 100%"自欺 - 修复后
  真实重跑 12/12; 沙箱 Maven 缓存卷预置 (断网沙箱依赖解析根因) +
  -o 离线模式 + CI 预置; 状态通道 diff_by_file/generation_record 入
  schema (worker 行内评论与证据溯源从死路变通路); ruff/mypy 全绿;
  测试经济学 (slow_eval marker + 子集 HTML 验收)
- [x] P6 阶段一 (金案例 20 -> 100, 文件与管线就绪): demo 基座扩展
  (cache-aside 用户读/TTL/邮箱变更驱逐 + orders/products 域含 @Version
  乐观锁与 requestId 幂等 + SqlQueryCounter 查询计数面 + schema.sql);
  构建器 v3 数据表驱动 80 案例 (case-21..100) + base 重指向改造 +
  require_clean 收窄 demo/; 11 个新契约族 + 17 个差分模板 +
  MIGRATION-01/TEST_STRENGTH-01 静态检查器 + H2 三表取证 +
  Base 构建产物复用 (Maven 调用 3->2, head_run 复用 + base 源码冻结
  skipMain + head 增量播种; 3 案例小样本实测 53-65s/case 本地模式);
  100 案例目录/split.json 就绪; 验收测试 100 目录断言 + 新代表子集 +
  slow_eval 实测依据注释; docs/eval/p6-100-case-eval.md
- [ ] P6 阶段二 (进行中): 队长已提交 demo/ 基座 (eeeb9e2) 并运行
  builder (101 tags, case-21..100-head 均挂新基座); 待全量 100 案例
  隔离评测 -> 复核 +25pp 门槛

## 下一步 (按顺序)

- [ ] P6 评测与试点 (阶段二): 100 案例全量隔离评测 (标签已重建)、
  Dashboard 压测、3 个真实仓库试点 (runbook 已就绪)
- [ ] P6 安全项: worker DooD (/var/run/docker.sock) 与 §12 冲突,
  改隔离 runner / rootless dind; 沙箱非 root 运行 (Linux)
- [ ] P6 可观测/SLO: Grafana dashboard 化、SLO 看板与告警、备份恢复演练
- [ ] P5 增补: LLM 基线 ("直接让 DeepSeek 看 Diff") 实测补测

## 关键指标 (Go/No-Go)

- BLOCKER/MAJOR Precision ≥ 90% · 语义回归 Recall ≥ 80% · PR 归因 ≥ 90%
- Capsule Replay ≥ 95% · 无证据严重评论 = 0 · FAST 小 PR p95 ≤ 8 分钟
- 与"直接让模型看 Diff"基线相比, 语义回归发现率 ≥ +25 个百分点
