# SpecProof — AI 变更验收防火墙 + SpecCraft 自主开发 Agent

> 代码是 AI 写的, 谁签字? — 我们把"验收"变成机器可验证的事实。

SpecProof 是 AI 生成代码的**独立验收平台**: 把需求编译成可执行契约, 在修改前后
两个隔离沙箱里真实运行 (HTTP/MySQL/Redis/RabbitMQ 全栈差分 + 变异测试), 拦截
回归并产出**可重放证据**; 全部通过则签发 **Ed25519 签名 Merge Certificate**。
SpecCraft 是同平台的**自主开发 Agent** (规划→编辑→执行→自校验→交付),
与验收 Agent 组成 开发→验收→签发 闭环。

## 一句演示 (真实拦截)

```bash
pip install -e ".[dev]"
python -m cli.specproof.main verify --repo demo/spring-backend --base base --head head-v1 --spec demo/requirement.txt
# → BLOCKER AUTH-01 (@PreAuthorize 被移除) + 可重放 Bug Capsule
```

## 核心能力

- **契约编译器**: 需求 → 11+ 契约族 (AUTH/UNIQUE/EVENT/TRANSACTION/ATOMICITY/
  CONCURRENCY/CACHE/MIGRATION/OPENAPI/NPLUSONE/TEST_STRENGTH…) + 人工审批 + 版本化
- **全栈差分实验室**: Base/Head 隔离执行, HTTP/MySQL/Redis/RabbitMQ 状态快照与语义归因
- **变异测试**: 源码级算子 + 战役 + KILLED/SURVIVED 分类
- **证据链**: 可重放 Bug Capsule + Ed25519 in-toto 风格证书 + **契约血缘** (篡改可证伪)
- **SpecCraft 开发 Agent**: 规划/诊断由真实 LLM 驱动 (thinking 分层 + KV 缓存友好
  模板 + TokenBudget), 编辑器原子写/唯一匹配/审计, 断点续跑, 记忆与流式交互
- **RAG 2.0**: BM25+向量 → RRF → 符号图谱邻域 → 重排 (三层诚实降级)
- **MCP 工具服务**: 任何外部 Agent (Claude Code/Codex) 可直接调用我们的验证工具
- **完整平台**: React SPA 9 页 + FastAPI + Spring Boot Control Plane + 沙箱 Worker
  + 5 层中间件 + Prometheus/Grafana SLO 看板 + 审计 + Outbox/幂等

## 实测数字 (全部真实运行)

| 指标 | 结果 |
|---|---|
| 100 金案例 | Recall/Precision/F1 100/100/100, 0 误报 |
| 裸 DeepSeek V4 Pro 看 Diff 基线 | 发现率 100% / 严格归因 0% / 5 误报 / 被注入影响 |
| SpecCraft 微基准 (10 任务, 真实 LLM) | 完成率 90% / 迭代 1.1 / 陷阱拦截率 100% |
| 真实网关能力探测 | 8/11, 按能力自动降级 |
| 测试规模 | 867 机器可判用例 (unit 626/security/fault/integration/golden/bench) |

## 快速开始

60 分钟完整体验: **[docs/operations/EXPERIENCE_GUIDE.md](docs/operations/EXPERIENCE_GUIDE.md)**
架构与对标: [docs/architecture/STACK_INVENTORY.md](docs/architecture/STACK_INVENTORY.md) ·
[docs/design/AGENT_STATE_OF_ART.md](docs/design/AGENT_STATE_OF_ART.md)
产品规格: [docs/PRODUCTION_SPEC.txt](docs/PRODUCTION_SPEC.txt) ·
[docs/design/GRAND_PLAN_V2.md](docs/design/GRAND_PLAN_V2.md)

## 安全纪律

密钥只经环境变量注入 (0 密钥泄漏门禁实测); 推理内容不落盘 (ADR-017);
沙箱非 root/断网/只读; 仓库文本一律视为数据 (注入免疫实测 0 影响)。
