# SpecProof Phase 0 — AI Change Acceptance Firewall

## 项目概述

SpecProof 是一个 AI 变更验收防火墙。它独立验证 AI 生成的 PR，对照需求规范检查代码变更，在合并前拦截回归问题。

Phase 0 是 7 天原型：一个 Spring Boot 演示项目、一个需求、Base/Head 隔离、差分执行、HTML 矩阵、Bug Capsule、Capsule Replay。

## 架构

```
cli/specproof/main.py          ← Click CLI 入口
agent/graph.py                 ← LangGraph StateGraph (12 节点线性管道)
agent/state.py                 ← Phase0State (MessagesState 扩展)
agent/nodes/                   ← 12 个节点: intake → publish_report
evidence/                      ← 矩阵构建、HTML 报告、合并证书
providers/                     ← DeepSeek/OpenAI 兼容 Provider + 能力探测
storage/                       ← MySQL/MongoDB/ES/Redis/RabbitMQ/MinIO 适配器
demo/spring-backend/           ← Spring Boot 3.4 演示项目 (base/head-v1 tags)
tests/                         ← 单元/集成/安全/验收测试
golden-cases/                  ← 10 个金案例用于评估
```

## 常用命令

```bash
# 安装
pip install -e ".[dev]"

# Lint
python -m ruff check .
python -m ruff check --fix .

# 测试
python -m pytest tests/ -v

# CLI
python -m cli.specproof.main probe --base-url <url> --api-key <key>
python -m cli.specproof.main verify --repo <path> --base <ref> --head <ref> --spec <file>
python -m cli.specproof.main replay <capsule.zip>
python -m cli.specproof.main eval --cases golden-cases/
```

## 关键约束

- 所有文件中绝对不能有真实 API Key，`.env.example` 只用 `replace_me` 占位符
- 不能有 TODO/pass/占位符端点
- Windows 环境：PowerShell 语法、git worktree 在 NTFS 上
- `demo/spring-backend` 使用 Maven Wrapper (mvnw) 自包含构建

## Phase 0 已知限制

- LLM 集成已通过真实 DeepSeek 端点验证（lazy probe → 7/10 capabilities，chat/JSON output/streaming 均可用）
- compile_contracts / generate_counterexamples / review_court 均已添加 LLM fallback，LLM 不可用时自动退回 rule-based
- 存储适配器存在但未连接真实服务
- Merge Certificate 使用 SHA-256 哈希，Ed25519 签名计划 Phase 1+
- DeepSeek gateway 始终返回 reasoning_content（always-on thinking），需额外 token 预算
- strict_tool_calls 在 gateway 上返回 HTTP 400，已通过 JSON Action Envelope 降级处理

## P0.5 改进 (2026-07-10)

### 已完成
- **B1**: Maven Wrapper (mvnw) + JDK 21 环境搭建，Maven 3.9.9 自动下载
- **B2**: Provider lazy probe — 首次 API 调用时自动探测能力，无需手动 run_probe()
- **B3**: Capability probe max_tokens 调整（always-on thinking 消耗 token 预算）
- **B4**: reasoning_content 支持 — LLMResponse 新增 reasoning_content 字段
- **C5**: Maven 测试执行不再是空操作 — _run_maven_test() 真正运行 JUnit
- **C6**: DeepSeek 生成 JUnit → 编译 → Base/Head 差分执行 → 真实回归检测
  - SecurityConfig 改为 permitAll()，使 @PreAuthorize 成为主要认证点
  - Base (有 @PreAuthorize): changeEmailWithoutAuth → 401 → PASS
  - Head (无 @PreAuthorize): changeEmailWithoutAuth → 200 → FAIL
  - 综合证据：静态 diff + 运行时 JUnit 双重确认
- **C7**: LLM 合约编译验证通过（DeepSeek 从需求中提取 6 个合约）
- **E8**: Capsule run.sh/run.ps1 包含实际可执行回放命令（git checkout + mvnw test + 结果对比）

### 关键约束
- 所有文件中绝对不能有真实 API Key，`.env.example` 只用 `replace_me` 占位符
- 无 TODO/pass/占位符端点
- Windows 环境：PowerShell 语法、git worktree 在 NTFS 上
- `demo/spring-backend` 现在使用 Maven Wrapper 自包含构建，无需系统安装 Maven
