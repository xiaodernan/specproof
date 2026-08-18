# SpecProof 深度能力开发记录 (2026-08-17, 第五轮)

对应宏伟目标的 P3/P4/P5 与可观测性部分。

## 本轮新增

### 1. Ed25519 签名证书 (P5 核心)
- evidence/signing.py: Ed25519 密钥装载 (env/文件, hex seed, 32B 校验),
  in-toto 风格签名语句 (canonical JSON → sha256 subject digest →
  Ed25519 sig + keyid), 验证函数, 密钥生成工具;
- verify CLI: 证书与拒绝通知在配置密钥后自动产出签名语句
  (signed-<job>-<doc>.json); 无密钥 = 明确说明 unsigned, 绝不假装签名;
- 5 个单测 (往返/篡改拒绝/错钥拒绝/缺钥/非法长度)。

### 2. 生产配置守卫 (P0-A4)
- storage/config_guard.py: SPECPROOF_ENV=production 时校验全部凭据
  (默认口令/未设密钥) 并 fail-fast; API 启动即强制执行; 3 个单测。

### 3. 全栈状态差分实验室 (P3 核心)
- experiments/state_snapshot.py: MySQL 表快照 + Redis 键/TTL 快照 +
  RabbitMQ 队列深度快照 (passive declare) → 语义 diff (added/removed/
  changed, 逐键归因) → 文本报告; 快照失败按子系统标记 incomplete,
  绝不伪造; 4 个集成测试 (真实 compose 基础设施, 实测 Redis 变更
  与过期被正确归因)。

### 4. 源码级变异测试 (P4 核心)
- experiments/mutation.py: 4 类变异算子 (注解删除/布尔翻转/空检查删除/
  返回值翻转), 变异体生成 (上限可控), 变异战役执行器 (测试击杀=KILLED,
  通过=SURVIVED=测试弱点), mutation_score 报告;
  5 个单测。按 spec: 存活变异体报告为 TEST WEAKNESS, 不当 Bug。

### 5. 可观测性深化 (C1/C2)
- observability/logging.py: JSON 结构化日志 (ts/level/logger/message/
  job_id/trace_id, contextvar 传播); worker 每个 job 的日志自动带 job_id;
- observability/middleware + tracing: API 启动接入 OTel 插桩 (无 SDK
  时 NoOp); worker 启动初始化 tracer (service=specproof-worker)。

## 实测
- 新增 17 个测试全部通过 (signing 5 + config_guard 3 + snapshot 4 +
  mutation 5)
- ruff / mypy 全绿 (71 源文件)
- 全套回归见本轮最终 pytest 运行
