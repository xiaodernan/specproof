# SpecProof

**AI 变更验收防火墙 (AI Change Acceptance Firewall)** — 独立验证 AI 生成的 PR 是否真的完成需求。

> 实现 Agent 不能给自己签字。SpecProof 用可执行证据证明一个 AI PR 是否完成需求、破坏了什么、证据在哪里。

[![Phase]](https://img.shields.io/badge/phase-0%2FP1-58a6ff)
[![Python](https://img.shields.io/badge/python-3.12-blue)]()
[![LangGraph](https://img.shields.io/badge/langgraph-1.x-orange)]()

---

## 一句话

输入: Requirement + Acceptance Criteria + 一个 AI 生成的 PR (Base/Head 两个 commit)。
输出: 每条需求的**可执行证据** (Requirement-to-Evidence Matrix)、可重放 Bug Capsule、
HTML 验证报告、Merge Certificate 或拒绝通知。

不是"代码看起来怎么样"的评论机器人，而是回答:
"它是否完成了任务、破坏了什么、证据在哪里？"

## 核心演示 (30 秒)

```bash
# 1. 安装
pip install -e ".[dev]"

# 2. 端到端验证: Base 有鉴权, Head (AI PR) 删掉了 @PreAuthorize
python -m cli.specproof.main verify --repo . --app-dir demo/spring-backend \
    --base base --head head-v1 --spec demo/requirement.txt --depth FAST

# 3. 评估 10 个金案例 (确定性模式, 可复现)
python -m cli.specproof.main eval --cases golden-cases --repo . --no-llm

# 4. 重放证据包
python -m cli.specproof.main replay capsules/capsule-*.zip
```

运行一次 verify 会发生什么: 需求被编译成 6 条 Contract → Base/Head 两个隔离 worktree →
静态 Contract Checker + LLM/模板生成 JUnit 反例测试 → **真实 Maven 差分执行** (Base 通过,
Head 失败) → 读取 H2 文件库做 DB 状态取证 → Review Court 三审 (Prosecutor/Defender/Judge) →
矩阵 + Bug Capsule + HTML 报告 + 拒绝通知。

## 架构

```
CLI (verify/eval/probe/replay)
        │
        ▼
LangGraph 管线 (12 节点, 错误短路)
  intake → compile_contracts → prepare_base → prepare_head
  → collect_diff → run_static_checks → generate_counterexamples
  → run_differential → review_court → build_matrix
  → create_capsule → publish_report
        │
        ▼
证据: HTML 报告 + Requirement-to-Evidence Matrix + Bug Capsule + 证书/拒绝通知

P1 生产内核 (可靠任务):
  FastAPI API (POST /jobs, GET /jobs, GET /jobs/{id}, SSE /jobs/{id}/progress)
  → MySQL Outbox (同事务) → Outbox Relay → RabbitMQ (Confirm + DLQ + 幂等)
  → Worker (Redis lease + MongoDBSaver checkpoint 崩溃恢复)
  → 终态按真实结果: VERIFIED / BLOCKED / FAILED
```

存储职责: MySQL=业务事实源 · MongoDB=checkpoint 与实验工件 · Redis=锁/预算/SSE 进度 ·
RabbitMQ=可靠任务 · MinIO=大对象 · Elasticsearch=仓库检索

## 证据政策 (产品灵魂)

- BLOCKER 必须同时满足 6 个条件: 已批准 Contract + 真实 Base/Head 执行证据 + Head 归因 +
  DB/行为证据 + Capsule 可重放 + confidence ≥ 0.90
- 静态源码分析封顶 MAJOR，永远不能当 BLOCKER
- 只有真实跑过的实验才能写 PASS/FAIL，其余一律 UNVERIFIED — 绝不伪造
- SHA-256 只叫 evidence_digest，不叫"签名" (Ed25519 签名是后续阶段)
- 证书只在全部 Contract 带证据 PASS 时签发；否则写拒绝通知

## 目录

```
agent/            LangGraph 管线: graph、state、12 nodes、contract checkers、worker、Mongo saver
providers/        ModelProvider 抽象 + OpenAI-compatible 实现 + 10 维能力探测
evidence/         HTML 报告渲染、Merge Certificate / Rejection Notice
storage/          MySQL(状态机+Outbox)、MongoDB、ES、Redis、RabbitMQ、MinIO 适配器
api/              FastAPI: 任务提交/查询/SSE 进度
cli/              Click CLI: verify / eval / probe / replay
demo/spring-backend/  Spring Boot 3.4 + JUnit5 + H2 演示仓库 (base/head-v1/case-* tags)
golden-cases/     10 个金案例 (holdout/negative/adversarial 划分见 split.json)
tests/            unit / integration / security / fault 四层测试
docs/             设计评审、架构、ADR、面试指南、路线图
```

## 质量门槛 (实测)

- pytest: 单元/安全全绿; 集成/故障注入在无 Docker 时诚实 skip，绝不静默跳核心路径
- eval: holdout recall 目标 100%，negative 0 误报 (见 docs/eval/eval-report.html)
- 安全: 无真实 Key；canary 自检；capsule zip 内容也扫描
- ruff + mypy(strict) 通过

## 环境

- Python ≥ 3.12；JDK 21 (JAVA_HOME)；演示仓库自带 Maven Wrapper
- 可选: Docker Compose (compose.phase0.yml 起 MySQL/MongoDB/ES/Redis/RabbitMQ/MinIO)
- LLM 可选: .env.example 配置 OpenAI-compatible 网关；无 Key 时自动走确定性检查器

## 文档

- docs/design/DESIGN_REVIEW.md — 全盘设计评审 (问题清单)
- docs/design/REDESIGN_PLAN.md — 改进后的全局设计
- docs/architecture/ARCHITECTURE.md — 架构说明
- docs/adr/ — 关键架构决策记录
- docs/interview/INTERVIEW_GUIDE.md — 面试叙事与演练脚本
- docs/ROADMAP.md — 后续阶段路线

## License

MIT
