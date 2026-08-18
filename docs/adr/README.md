# ADR 索引 (SpecProof)

本目录保存 SpecProof 的关键架构决策记录, 按 PRODUCTION_SPEC §22 的 17 项要求
逐份独立成文。状态列含义: 已接受 = 决策生效并已在代码中实现 (实现程度在
各文件内如实注明局限); 已取代 = 被后续决策取代, 原文存档。

| 编号 | 主题 | 状态 | PRODUCTION_SPEC §22 |
|---|---|---|---|
| [ADR-001](ADR-001.md) | 为什么不是普通 Code Review | 已接受 | ADR-001 |
| [ADR-002](ADR-002.md) | 为什么先只支持 Spring Backend | 已接受 | ADR-002 |
| [ADR-003](ADR-003.md) | 为什么实现 Agent 与验证 Agent 隔离 | 已接受 | ADR-003 |
| [ADR-004](ADR-004.md) | 为什么高等级 Finding 必须带可执行证据 | 已接受 | ADR-004 |
| [ADR-005](ADR-005.md) | 为什么同时使用 MySQL 与 MongoDB | 已接受 | ADR-005 |
| [ADR-006](ADR-006.md) | 为什么 Redis Stream 不替代 RabbitMQ | 已接受 | ADR-006 |
| [ADR-007](ADR-007.md) | 为什么使用 Elasticsearch Hybrid Search | 已接受 (向量通道预留) | ADR-007 |
| [ADR-008](ADR-008.md) | 为什么做 Base/Head 差分 | 已接受 | ADR-008 |
| [ADR-009](ADR-009.md) | 为什么 Mutation 只跑影响范围 | 已接受 (模块级范围, diff 级未接入) | ADR-009 |
| [ADR-010](ADR-010.md) | 为什么 Contract 必须人工批准 | 已接受 | ADR-010 |
| [ADR-011](ADR-011.md) | 为什么 Certificate 绑定需求版本和 Commit | 已接受 (P5 Ed25519) | ADR-011 |
| [ADR-012](ADR-012.md) | 第三方 OpenAI-Compatible 网关兼容策略 | 已接受 | ADR-012 |
| [ADR-013](ADR-013.md) | Sandbox 威胁模型 | 已接受 | ADR-013 |
| [ADR-014](ADR-014.md) | 为什么自动修复需要审批 | 已接受 | ADR-014 |
| [ADR-015](ADR-015.md) | Bug Capsule 可重放格式 | 已接受 | ADR-015 |
| [ADR-016](ADR-016.md) | 为什么 v1.0 不使用 Kubernetes | 已接受 | ADR-016 |
| [ADR-017](ADR-017.md) | LLM 私有推理不保存 | 已接受 | ADR-017 |

## 历史文件

- [LEGACY-ADR-000-010-combined.md](LEGACY-ADR-000-010-combined.md) — 拆分前的
  10 份合并 ADR 原稿 (原 docs/adr/ADR.md), 已标注被取代, 仅作历史存档。
  其中旧 ADR-009 (Phase 0 用 SHA-256 digest 而非签名) 已过时: P5 在
  evidence/signing.py 实现了 Ed25519 签名, 由新 ADR-011 取代并写明演进过程。

## 旧编号 -> 新编号映射

| 旧 (合并文件) | 新 (独立文件) |
|---|---|
| 001 为什么不是普通 AI Code Review | ADR-001 |
| 002 为什么先只支持 Spring Boot 后端 | ADR-002 |
| 003 为什么实现 Agent 与验证 Agent 隔离 | ADR-003 |
| 004 为什么高等级 Finding 必须带可执行证据 | ADR-004 |
| 005 为什么 MySQL 与 MongoDB 同时存在 | ADR-005 |
| 006 为什么关键任务不用 Redis Pub/Sub 而用 RabbitMQ | ADR-006 |
| 007 为什么做 Base/Head 差分而不是只看 Head | ADR-008 |
| 008 为什么 Contract 必须人工批准 | ADR-010 |
| 009 为什么 Phase 0 用 SHA-256 digest 而不是签名 | 被 ADR-011 取代 |
| 010 为什么第三方 OpenAI-compatible 网关不可信 | ADR-012 |
| — (新撰写) | ADR-007 / ADR-009 / ADR-013 / ADR-014 / ADR-015 / ADR-016 / ADR-017 |
