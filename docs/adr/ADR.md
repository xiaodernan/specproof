# ADR-001 — 为什么不是普通 AI Code Review

状态: 已接受 (2026-08)

背景: 市场上已有大量"AI 给代码提意见"的产品, 输出评论/风险/建议。

决策: SpecProof 输出的是每一条需求的**可执行证据** (Requirement-to-Evidence Matrix、
可重放 Bug Capsule、Base/Head 差分结果), 而不是意见。

理由:
- 评论无法验证真伪, 证据可以重放;
- 实现 Agent 与验证 Agent 必须隔离, 否则是自签自证;
- "测试通过 ≠ 需求完成"—— 只有对照需求逐条验证才有意义。

后果: 高等级 Finding 必须携带证据; 无证据的严重评论视为缺陷 (SLO: 0 容忍)。

# ADR-002 — 为什么先只支持 Spring Boot 后端

状态: 已接受

决策: v1.0 只支持 Java 21 + Spring Boot 3.x + Maven/Gradle + JUnit 5 + MySQL/Redis/
RabbitMQ + OpenAPI 3.x。

理由: 差分执行、契约检查器、变异测试都需要深度的框架语义; 一次性支持所有语言
会稀释每个检查器的质量。先在一个栈上把"证据密度"做满, 再横向复制。

后果: 检查器注册表按框架组织; 第二阶段 FastAPI/Node/PG/Kafka。

# ADR-003 — 为什么实现 Agent 与验证 Agent 隔离

状态: 已接受

决策: SpecProof 只读需求、用户批准的 Contract、Base/Head SHA 与工具输出;
不读实现 Agent 的自我评价, 不接受 PR 描述中未经验证的声明。

理由: 同一个模型既实现又验收, 相当于自己给自己签发合格证; 利益分离是验收的
基本前提 (参考编译器的独立测试、金融的独立审计)。

后果: 系统默认不信任实现方叙事; 一切结论来自实验。

# ADR-004 — 为什么高等级 Finding 必须带可执行证据

状态: 已接受

决策: BLOCKER 必须满足 6 条件: 已批准 Contract + 真实 Base/Head 执行 + Head 归因 +
DB/行为证据 + Capsule 可重放 + confidence ≥ 0.90; 静态分析封顶 MAJOR。

理由: 静态正则只能证明"看起来像问题", 差分执行才能证明"问题由这个 PR 引入";
可重放性把结论从模型判断变成事实陈述。

后果: 检测管道必须真实执行测试; 没有执行能力的结论自动降级。

# ADR-005 — 为什么 MySQL 与 MongoDB 同时存在

状态: 已接受

决策: MySQL 存业务事实 (job/contract/finding/outbox), 强事务 + 状态机 + 唯一约束;
MongoDB 存结构复杂、频繁演进的实验工件 (checkpoint/evidence_packs/differential_runs)。

理由: 业务状态需要 ACID 与 CAS; 分析工件 schema 不稳定、体积大、需要嵌套结构。
让"事实"与"工件"分离, 审计视图可按 job_id 从工件重建。

后果: MySQL 是唯一事实源; MongoDB 损坏不影响业务结论 (工件可重放重建)。

# ADR-006 — 为什么关键任务不用 Redis Pub/Sub 而用 RabbitMQ

状态: 已接受

决策: 可靠任务走 RabbitMQ (Publisher Confirm + Manual Ack + DLQ + 幂等消费 +
Transactional Outbox); Redis 只做锁/租约/预算/进度流 (全 TTL)。

理由: Pub/Sub 断线丢消息, 不可靠投递会把"任务不丢不重"的 SLO 毁掉;
Redis Stream 只服务"进度"这种可丢失的实时数据。

后果: 生产拓扑固定三个 exchange (commands/events/dlx); 消息含 trace_id 与 attempt。

# ADR-007 — 为什么做 Base/Head 差分而不是只看 Head

状态: 已接受

决策: 同一测试在 Base 与 Head 两个隔离 worktree 真跑, 比较 HTTP/DB/异常/事件。

理由: 只看 Head 无法归因 (问题是本来就存在还是 PR 引入?); 差分把结论绑定到
具体变更, 正是验收评审要回答的问题。

后果: 每个案例必须携带 base_ref/head_ref; 判定四分类 (REGRESSION/COMPLIANT/
AMBIGUOUS/UNEXPECTED_FIX)。

# ADR-008 — 为什么 Contract 必须人工批准

状态: 已接受

决策: 从 Issue/ADR/文档提取的候选 Contract 必须经用户批准后才进入验证计划。

理由: 需求永远有歧义; 把需求编译成可执行契约是"解释性"动作, 解释错了
验收就全错。人工批准把产品责任边界划清楚。

后果: Contract 有版本与审批记录; 未批准的契约只做建议, 不参与判定。

# ADR-009 — 为什么 Phase 0 用 SHA-256 digest 而不是签名

状态: 已接受

决策: Phase 0/1 的产物只声称 evidence_digest / manifest_digest (SHA-256),
严禁自称"签名证书"; Ed25519 + in-toto 风格证明留到 Phase 2+。

理由: 哈希只能证明内容未被篡改 (需要信任通道), 签名才提供发起人身份与不可抵赖;
把一个 digest 叫成 signature 是安全产品的致命信用问题。

后果: 命名规范写入证据政策; 证书输出字段按 in-toto Statement 风格预留。

# ADR-010 — 为什么第三方 OpenAI-compatible 网关不可信

状态: 已接受

决策: 任何新网关先跑 10 维能力探测 (models/chat/streaming/json/tool_calls/
strict_tool_calls/thinking/thinking+tools/usage/错误码与限流头); 按能力降级:
tool_calls 不可用→JSON Action Envelope; thinking+tool 不稳→计划/判断用思考,
工具循环不用; JSON 空内容→重试后退 Schema Parser。

理由: 网关普遍"部分兼容"; 假设完整兼容会在生产随机失败且难以定位。

后果: provider_capabilities 持久化并缓存; 探测结果进入 Job 记录。
