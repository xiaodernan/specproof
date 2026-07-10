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
- Maven 未安装在 Windows 上，差分测试执行跳过实际 JUnit 运行

## Phase 0 已知限制

- LLM 集成仅通过 capability probe 测试，未使用真实 DeepSeek 端点
- Review Court 使用简化版规则，非完整 LLM-based 三方辩论
- generate_counterexamples 使用模板生成，非 LLM 动态生成
- compile_contracts 使用正则规则解析，非 LLM-based 编译
- 存储适配器存在但未连接真实服务
- Merge Certificate 使用 SHA-256 哈希，Ed25519 签名计划 Phase 1+
