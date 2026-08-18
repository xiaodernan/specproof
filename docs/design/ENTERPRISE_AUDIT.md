# SpecProof 企业级差距审计 (Enterprise Gap Audit)

版本: 1.0 · 日期: 2026-08-17
方法: 对照 PRODUCTION_SPEC 4×9、OWASP/生产部署实践与真实攻击面逐项核验
(代码 + 实测), 每项给出严重度 (P0=上线阻断 / P1=上线前必须 / P2=快速迭代)。

---

## A. 安全漏洞 (攻击面实测)

### A1. [P0] 实验执行没有沙箱 — 不可信 PR 代码在宿主机上执行
当前 run_differential / generate_counterexamples 在宿主机临时目录里直接跑
mvnw test。Maven 构建会执行 build 插件、测试代码、@Test 生命周期钩子 —
一个恶意 PR 的 pom.xml/测试代码即可在**宿主机权限**下执行任意代码/读取
环境变量(含 LLM_API_KEY)/外发网络。这是与 spec §12 威胁模型直接冲突的
最高危漏洞。
修复: sandbox/runner.py — Docker 容器内执行 (--network none、--memory/--cpus
限额、cap-drop ALL、只读挂载源码、独立 tmpfs、无 docker.sock、无密钥注入),
本地执行仅作显式开发模式 (SPECPROOF_SANDBOX=local)。

### A2. [P0] API 无鉴权、无速率限制
POST /jobs 任何人可提交任意任务 (任意 repo 路径/ref), GET /jobs 泄露任务
元数据, CORS allow_origins=["*"]。这是完整 SSRF/资源滥用入口: 任务参数
repo_path/spec_path 由调用方控制, 管线会对其执行 git/maven。
修复: X-API-Key 鉴权中间件 (密钥仅环境变量, 常数时间比较) +
Redis 令牌桶限流 + CORS 白名单; 未认证一律 401。

### A3. [P0] 缺 Secret 脱敏与最小上下文传输
repo 源码/文档直接拼进 LLM prompt (compile_contracts/retrieve), 无脱敏层;
若仓库含历史密钥/私钥, 会被送出。security_scanner 只扫自家产物。
修复: prompt 组装前统一脱敏 (sk-/Bearer/私钥块/PAT 正则替换) + 记录
transmitted bytes; 文档化"私有代码默认不训练"边界。

### A4. [P1] 默认口令未做生产校验
所有 storage dataclass 默认 specproof_pass/minioadmin; 生产环境若忘设环境
变量会带着默认口令上线。
修复: 配置层生产模式校验 (SPECPROOF_ENV=production 时拒绝默认口令) +
启动时显式警告。

### A5. [P1] audit_logs 缺失
spec 要求全状态变化写审计日志; 目前只有 contract_approvals 有审计,
job 状态迁移无审计表。
修复: mysql.audit_logs 表 + transition_job_status 写审计行 (who/from/to/ts)。

### A6. [P2] 仓库文本即数据的注入防护未成文
Prompt 注入威胁模型只在 spec 描述, 代码无结构化解耦 (无 tool gateway 鉴权)。
修复: 文档化 data/instruction 边界 + LLM 调用统一走带注入提示的封装。

## B. 数据与可靠性

### B1. [P0] 无版本化迁移
ensure_tables 的 CREATE IF NOT EXISTS 不是迁移系统: 无版本号、无回滚、
无冲突检测 (列变更需手动 DROP)。企业级数据库演进必备。
修复: schema_migrations 表 + 迁移执行器 + migrations/0001..000N.sql,
DDL 全部迁入版本化迁移, ensure_tables 仅做兼容入口。

### B2. [P1] 状态机缺 CANCELLED / WAITING_FOR_PROVIDER
spec P1 定义 10 态; 现 8 态。Provider 故障应进 WAITING_FOR_PROVIDER (可恢复),
用户取消应进 CANCELLED; 目前一律 FAILED。
修复: 状态机扩 10 态 + 迁移 SQL + worker/provider 路径接入。

### B3. [P1] Job 取消路径缺失
无 cancel API; STALE 只能被动标记。
修复: POST /jobs/{id}/cancel (CAS RUNNING/QUEUED→CANCELLED) +
worker 周期检查取消标志。

### B4. [P1] SSE 无鉴权 + 无心跳 + 无 backpressure
SSE 端点可匿名读任意 job 进度; 无 keep-alive 注释; xread 无上限。
修复: SSE 走同一 API Key 鉴权; 每 15s 注释心跳; count 上限已有。

### B5. [P2] Outbox 无死信监控/积压告警
relay 有指数退避但无指标; 积压只能手工查。
修复: 指标 outbox_pending + 告警阈值文档化 (P6 Dashboard)。

### B6. [P2] 无数据保留/删除策略
jobs/findings/artifacts 永久增长; spec 要求保存期限与仓库删除。
修复: cleanup worker + TTL 配置 (P6)。

## C. 可观测性与运维

### C1. [P1] OTel 模块存在但未接入
observability/ 未被任何路径调用; 无 trace 传播 (webhook→outbox→MQ→worker→LLM)。
修复: 接入 API/worker/relay + trace_id/job_id 注入日志上下文。

### C2. [P1] 无 /metrics 端点与结构化日志
无 Prometheus 指标; 日志是 print/默认格式, 无 job_id 关联。
修复: /metrics (Prometheus 文本) + 结构化 JSON 日志 (logging 配置)。

### C3. [P1] 无应用服务部署物
compose 只有基础设施; API/worker/relay 无 Dockerfile, 无生产 compose。
修复: docker/ 目录 (Dockerfile.api/worker + compose.production.yml)。

### C4. [P1] CI 有缺陷 + 无夜间评测
现 CI eval gate grep eval-run.log, 但 eval 命令不写该文件 (gate 恒失败/空跑)。
修复: eval 写 eval-run.log + CI 修正 + 每日夜间 100 案例评测 workflow。

### C5. [P2] 无备份/恢复与压测
无 MySQL/对象存储备份脚本、无 soak test、无故障演练手册。
修复: ops/ 目录脚本 + 文档 (P6)。

## D. 产品功能完整性 (spec 4×9 对照)

### D1. [P1] 无 Control Plane (Java)
spec 主架构是 Spring Boot Control Plane (租户/用户/GitHub App/Outbox/审计),
当前只有 Python API 承担部分职责; 多租户模型 (tenants/users/repositories)
完全缺失。
修复: services/control-plane (Spring Boot 3.4) 最小可运行形态: 健康检查 +
tenant/user 表 + 转发 agent-runtime; 与 Python API 并存过渡。

### D2. [P1] 无 GitHub App (P5)
webhook 验签/Check Run/评论/capsule 链接全部未做。
修复: P5 阶段: X-Hub-Signature-256 验签 + Check Run SDK + 评论。

### D3. [P1] 无 Dashboard
jobs/进度/矩阵/证书无 UI。
修复: P6: FastAPI 托管静态面板 + SSE 实时刷新。

### D4. [P2] 无 Fix 工作流
/specproof fix → 补丁 → 人工批准 → PR 未实现。
修复: P5.5: fix_jobs 表 + 补丁生成 (LLM) + 审批流。

### D5. [P2] 验证档位只有 FAST
DEEP/RELEASE (fuzz/变异/全量契约) 未实现 (P3/P4 阶段)。

## E. 评测与质量

### E1. [P1] 金案例只有 10 个, 无基线对照
Go/No-Go 需要 100 案例 + "直接给模型看 Diff" 基线 (+25pp 语义回归发现率)。
修复: 案例生成器扩展 (transaction/concurrency/migration/redis/mq/perf/
prompt-injection 类) + baseline runner。

### E2. [P2] 无模型/提示词版本追踪
eval 结果不含 provider/model/prompt hash。
修复: eval 元数据 + model_usage 表接入。

## 修复优先级 (本轮起)

P0: A1 沙箱 · A2 API 鉴权限流 · A3 脱敏 · B1 版本化迁移
P1: B2/B3 状态机与取消 · A4 默认口令校验 · A5 审计表 · C1/C2 观测 · C3 部署物 · C4 CI
P2: D 系列功能 · E 评测扩充 · A6/B5/B6/C5
