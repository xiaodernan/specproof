# SpecProof 面试指南

目标: 用 5-10 分钟讲清"我造了一个什么样的 Agent 系统", 并接住 15 类追问。

## 1. 60 秒开场叙事

"现在 Coding Agent 写代码越来越快, 问题不再是缺少第二个会评论代码的模型,
而是**实现者不能给自己签发合格证**。

我做的是 SpecProof, 一个 AI 变更验收防火墙。它接收原始需求和 PR,
把需求编译成经过人工批准的 Contract, 然后在 Base 与 Head 两个隔离环境里
对 HTTP、MySQL、Redis、RabbitMQ 行为做差分验证。高等级问题必须附带失败测试
或可重放反例, 否则不允许报 BLOCKER。

系统用 LangGraph 控制 12 节点验证流程; MySQL 存业务事实; MongoDB 存 checkpoint
和实验工件; Redis 做锁、租约和实时进度; RabbitMQ 承载可靠长任务; MinIO 存证据包;
Outbox 与幂等保证任务不丢不重; 最后用 SHA-256 证据摘要绑定需求版本、Commit 和证据。

它不是告诉我代码可能有问题, 而是证明这个 AI PR 是否真正完成了任务。"

## 2. 现场演示脚本 (面试前练两遍)

```bash
cd specproof-clean-clone-gate
python -m cli.specproof.main verify --repo . --app-dir demo/spring-backend \
    --base base --head head-v1 --spec demo/requirement.txt --no-llm
# 指着输出讲: 6 条 Contract → 静态检查 → Maven 差分执行 Base 过 Head 挂 →
# H2 库 DB 状态取证 → BLOCKER/MAJOR → capsule zip → 拒绝通知

python -m cli.specproof.main eval --cases golden-cases --repo . --no-llm
# 指着讲: 10 个金案例, holdout 3 个 (开发时从没看过), Recall 100%

python -m cli.specproof.main replay capsules/capsule-*.zip
# 指着讲: 证据包在另一台机器重放, 得到相同结论
```

## 3. 十五类追问与回答要点

1. 和普通 Code Review Bot 区别? → 输出是证据不是意见; 验证/实现 Agent 隔离;
   Base/Head 差分归因; 高等级结论可重放。
2. 静态正则和 LLM 谁说了算? → LLM 只提议 (Prosecutor/Defender), 判定由证据政策
   硬规则执行; 静态证据封顶 MAJOR, BLOCKER 必须真跑。
3. 为什么 Contract 要人工批准? → 需求歧义; 把需求编译成可执行契约是解释性动作,
   解释权必须留给用户。
4. 任务不丢怎么保证? → 建 job 与 outbox 同事务; relay 用 SKIP LOCKED 轮询 +
   Publisher Confirm 后才标记已发布。
5. 任务不重怎么保证? → RabbitMQ at-least-once + Redis 幂等键 + MySQL 状态机 CAS;
   重投不产生重复 Finding。
6. Worker 崩了怎么办? → MongoDBSaver 每节点 checkpoint, 用 job_id 当 thread_id
   重入从断点续跑; lease 过期被其他 worker 接管。
7. 为什么 MySQL 和 MongoDB 都要? → 事实源需要 ACID/CAS; 分析工件 schema 不稳定
   且大, 分开后工件可重放重建, 审计视图不丢。
8. Redis 怎么用? → 只做锁/租约/预算/进度流, 全 TTL, 绝不当事实源; 关键任务
   走 RabbitMQ 而不是 Pub/Sub。
9. 模型网关不兼容怎么办? → 10 维能力探测 + 降级矩阵 (JSON Action Envelope 等),
   探测结果落库。
10. Prompt 注入怎么防? → 仓库文本全部当数据; 工具网关独立鉴权; 实验沙箱断网、
   非 root、只读源码。
11. 怎么证明自己不是刷出来的指标? → 金案例 holdout 划分, 开发期不看; eval 用
   确定性模式可复现; 证据摘要确定性 sha256。
12. 误报怎么办? → 负样本 (clean PR/comment-only) 要求 0 误报; Review Court 有
   Defender 角色专攻反证; 静态发现封顶 MAJOR。
13. 为什么先只支持 Spring Boot? → 差分/契约/变异都要深框架语义, 先在一个栈上
   把证据密度做满再复制。
14. 为什么不直接用 K8s? → v1.0 单机 (16-32GB) 足够 1-2 个 DEEP job 并发;
   先把 MySQL/对象存储/队列切托管, 吞吐不足再上 K8s。
15. 你在这个项目里最难的决定是什么? → 诚实性政策: 宁可 UNVERIFIED 也不伪造
   PASS; 把 digest 叫 signature 的诱惑; 以及把静态证据封顶 MAJOR 的产品取舍。

## 4. 诚实边界 (面试官会欣赏)

- Phase 0/1 还没有: Ed25519 签名、GitHub App、变异测试、状态机 fuzzing、
  100 案例评测 —— 都在 ROADMAP 里, 不要现场编。
- 确定性检查器只覆盖 demo 语义 (注解/事务/唯一性/事件/字段), 不宣称任意代码。
- 真实基础设施集成测试需要 Docker; 没有时诚实 skip, 不拿 mock 冒充。
