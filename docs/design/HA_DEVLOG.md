# SpecProof 高可用/双服务/深度实验开发记录 (2026-08-18, 第八轮)

对应宏伟目标: DEEP 档验证、双服务架构、GitHub App、高并发高可用。

## 本轮新增

### 1. DEEP 验证档接线 (P3+P4 进管线)
- agent/nodes/run_deep_experiments.py: 第 14 个管线节点 (run_differential 之后)。
  DEEP 档执行: (1) 变异战役 — 对 Head workspace 变更文件施加 4 类变异体,
  用生成的反例测试逐一运行, KILLED/SURVIVED 分类 (存活=测试弱点);
  (2) 全栈状态差分 — MySQL/Redis/RabbitMQ 快照 (测试运行前后) → 语义
  diff (逐键归因)。结果写 deep-report.json 与 state.deep_results。
- verify --depth 扩展为 FAST/DEEP。默认 FAST 保持 eval 速度不变。

### 2. Spring Boot Control Plane 起步 (双服务架构)
- services/control-plane/: Spring Boot 3.4.3 + JPA + MySQL, 自包含 mvnw:
  - Tenant 实体 + 仓库 + REST (POST/GET /api/v1/tenants, 409 冲突语义,
    Java record DTO);
  - /health 就绪探针; schema.sql (tenants/control_plane_users/
    github_installations, 租户隔离外键);
  - 测试: H2 profile 下 Spring 上下文启动 + 租户 API 往返 — **Maven 实测
    构建与测试通过**。
- 架构意义: 业务事实源服务 (Java) 与 Agent Runtime (Python) 分离,
  与 4x9 规格第 7 节一致。

### 3. GitHub Webhook 验签 (P5)
- integrations/github.py: X-Hub-Signature-256 HMAC 验签 (常数时间比较,
  fail-closed — 未配置 secret 直接拒绝), sign_payload 测试工具;
  6 个单测 (合法/错钥/篡改/缺头/坏头/缺配置)。

### 4. 高并发高可用验证
- tests/unit/test_concurrency_ha.py: (1) 20 事件 × 3 次重复投递, 4 线程
  并发消费, 恰好一次处理; (2) 租约互斥 — 3 worker 抢同一 job, 恰一个
  赢; (3) ack 前崩溃 → 重投 → 单次确认 (at-least-once + effectively-once)。

### 5. 指标下沉与仪表
- 指标注册表移至 observability/metrics.py (api.metrics 兼容再导出);
  worker 完成时计数 (jobs_completed_total, jobs_<verdict>_total) + 处理
  时长 gauge; outbox relay 每轮发布 outbox_pending gauge (积压可观测);
  MySQLStore.count_pending_outbox。

## 实测
- 新增 14 个测试 (concurrency 3 + webhook 6 + 既有回归) 通过;
- Control Plane: mvnw test 实测通过 (H2 上下文 + 租户 API 往返);
- ruff / mypy 全绿 (79 源文件);
- 全套回归见本轮最终 pytest。
