# SpecProof+SpecCraft 对标 Claude Code / Codex — 能力差距矩阵与路线

日期: 2026-08-18 · 目的: 诚实对标行业最先进 coding agent 的能力面, 逐项给出
"已有 / 差距 / 补齐动作", 禁止自欺 (每一项标注实测状态)。

## 1. Agent 核心循环

| 能力 | Claude Code / Codex | SpecProof+SpecCraft | 差距与动作 |
|---|---|---|---|
| 规划→执行→验证循环 | ✓ Plan mode / task lists | ✓ craft loop (M1 确定性 + 预算/断点) | 接近; M2 接 V4 Pro 规划/诊断 (I 进行中) |
| 文件编辑安全 | ✓ apply_patch 唯一匹配/原子写 | ✓ editor 原子写+备份+唯一性+审计 | 平级 |
| 命令执行 | ✓ 沙箱 (Codex cloud sandbox) | ✓ sandbox 非root/断网/限额/ro 工作区 | 平级 (更严格: 证据链要求) |
| 自校验 | 部分 (测试运行) | ✓ 构建+单测+契约检查器+安全扫描 | 超出 (契约编译器是差异化) |
| 断点续跑 | ✓ checkpoint | ✓ checkpoint.json (M4 接 MySQL) | 接近 |
| 子代理委派 | ✓ Subagents / parallel fan-out | ✗ | 缺: craft 计划步骤的并行子代理执行 (M5) |
| 记忆文件 | ✓ CLAUDE.md / AGENTS.md | ✗ (设计有 load_repository_policy 节点未实现) | 缺: craft 摄取仓库 AGENTS.md 策略 (M2b) |

## 2. 上下文工程

| 能力 | 对标 | 我们 | 动作 |
|---|---|---|---|
| 仓库检索 | ✓ RAG | ✓ BM25+符号图谱 (ES) | 平级; 向量通道预留 |
| 上下文压缩/自动摘要 | ✓ auto-compact | 部分 (图谱邻域 + 预算截断) | 可加: 超预算时中间摘要 (M5) |
| 稳定前缀缓存 | ✓ (各家均有 KV 优化) | ✓ prompt_templates 稳定前缀自检 | 平级 |
| 推理分层 | 各家策略不一 | ✓ thinking 分层 (plan_only/auto/off) 实测 8/11 | 平级 |

## 3. 工具与协议生态

| 能力 | 对标 | 我们 | 动作 |
|---|---|---|---|
| MCP 服务端 (工具被外部 agent 调用) | ✓ MCP server | ✗ | 【本轮启动 J】mcp/ 包: 把 verify/contracts/eval/replay/craft/health 暴露为 MCP tools (stdio JSON-RPC, mcp 1.28.0 SDK 可用) |
| MCP 客户端 (调用外部工具) | ✓ | ✗ | 后续: craft 可消费外部 MCP 工具 (M5) |
| Web 检索 | ✓ web search | ✗ (BYOK 定位, 默认不开) | 记录为有意不提供 |
| GitHub 集成 | ✓ GitHub bot | ✓ GitHub App (webhook/checks/评论/fix PR) | 平级 |
| IDE 集成 | ✓ 插件 | ✗ (CLI 优先) | 记录: CLI + GitHub 模式覆盖主场景 |

## 4. 安全与治理

| 能力 | 对标 | 我们 | 动作 |
|---|---|---|---|
| 人工审批门 | ✓ 权限确认 | ✓ 计划 PLAN_READY 审批态 + fix 审批流 + 工具白名单 | 平级 |
| 沙箱 | ✓ | ✓ (更硬: 证据链 + 非root + 断网) | 平级 |
| 密钥治理 | ✓ | ✓ (0 密钥门禁 + 脱敏 + canary) | 平级 |
| 注入防护 | 部分 | ✓ (数据/指令分段 + 实测: 裸模型被注入影响, 我们 0 影响) | 超出 |

## 5. 验证与质量 (我们的差异化, 对方没有的)

| 能力 | 对标 | 我们 |
|---|---|---|
| 需求→契约编译器 | ✗ | ✓ 11+ 契约族, 人工审批, 版本化 |
| Base/Head 全栈差分实验室 | ✗ | ✓ HTTP/MySQL/Redis/RabbitMQ 快照+归因 |
| 源码级变异测试 | ✗ | ✓ 4 算子+战役+KILLED/SURVIVED |
| 证据链 + 签名证书 | ✗ | ✓ Ed25519 Merge Certificate + capsule 重放 |
| 评测体系 | 部分 (SWE-bench 等) | ✓ 100 金案例 + 双口径基线 + Go/No-Go 15 门槛 |

## 6. 中间件完整性 (用户点名要求)

FastAPI: auth (fail-closed) ✓ / rate limit ✓ / CORS ✓ / SSE ✓ / 结构化日志 ✓ /
metrics ✓ / OTel ✓。补齐项: Request-ID 传播、请求体大小限制 (§13 payload 限制)、
响应缓存策略文档。CP (Spring Boot): webhook 验签 ✓ / 审计 ✓ / outbox ✓。
动作: 本轮 J 顺带做 Request-ID + payload 限制 + docs/operations/MIDDLEWARE.md 盘点。

## 7. 结论

对标结论 (诚实): 在 agent 循环/上下文/安全治理上与 Claude Code / Codex 同级或
更严; 在验证深度 (契约/差分/变异/证据/证书) 上系统性超出 (这是产品定位差异);
主要缺口 = 生态互操作 (MCP 双向) + 子代理并行 + 仓库策略摄取 — 均已排期。

## 8. 行业竞争基准与我们的评测战略 (2026-08-18 增补)

### 8.1 行业先进水平的量化口径 (以公开榜单为准)
- 通用 coding agent: SWE-bench Verified (解决率), Aider Polyglot (编辑正确率),
  LiveCodeBench (代码生成), terminal-bench (终端任务)。前沿产品 (Claude Code /
  Codex / Cursor / Devin / Aider) 在这些榜单的头部区间逐年抬升;
  (注: 本机 web 检索被会话密钥策略拦截, 本节不引用具体数值 — 精确数字以
   swebench.com / aider leaderboard 当日榜单为准, 禁止凭记忆写入。)
- 我们所在细分 (AI 变更验收 / 独立验证) 没有现成公开基准 — 这正是我们的机会:
  把 100 金案例 + Go/No-Go 15 门槛做成该细分第一个可复现基准。

### 8.2 评测战略 (向行业先进看齐)
1. 验证侧 (SpecProof): 100 金案例 (已建) → 200 案例路线 (合同/序列/反注入扩充);
   双口径基线 (diff-reader + LLM, 已实测); 15 门槛逐步全绿; 后续接入
   SWE-bench 风格的外部任务集做交叉验证 (私有部署优先, 公开集可选)。
2. 开发侧 (SpecCraft): 附录 E 的 10 任务微基准 (机器判定: 编译+测试+自校验三绿),
   加陷阱变体测自校验拦截率; 后续对接 SWE-bench-lite 适配器 (M5+)。
3. 测试金字塔持续扩量 (见 §9): 目标 1000+ 单测 / 200 金案例 / 30 故障注入场景。

## 9. 测试用例扩张路线 (用户点名: 强测试才配强项目)

| 层级 | 现状 (实测) | 目标 | 动作 |
|---|---|---|---|
| 单元测试 | 504 passed | 1000+ | 每新特性强制新测试; 属性测试 (hypothesis) 用于 checker/editor/parser 核心 |
| 安全测试 | 13 (密钥/脱敏) | 30+ | 注入矩阵 (README/注释/spec/分支名/commit message)、越权矩阵 |
| 故障注入 | 10 场景 (MQ/worker/outbox) | 30 | 网关故障 (429/超时/空 JSON)、磁盘满、僵尸租约、时钟回拨 |
| 集成测试 | 112 (真基础设施) | 150 | 三服务 compose 组合、CP×Runtime E2E 矩阵 |
| 金案例 | 100 (63正/37负) | 200 | 序列化状态机案例、更多注入负样本、跨契约组合案例 |
| 前端测试 | 33 (web_api) | 60+ | SPA 路由/降级视图断言 |
| MCP 一致性 | J 进行中 | 完整 | 协议消息矩阵 (initialize/tools/call/错误路径) |
| 微基准 | 附录 E 设计 | 10 任务落地 | K 本轮起 (见下) |

## 10. 持续演进机制 (长过程的方法论)
- 每轮: 审计 (门禁+评测+安全) → 实现 → 全绿验证, 指标只能升不能降 (回归红线);
- 季度口径: 重跑全部基准 + 更新差距矩阵 + 重新对标榜单;
- 新能力上马前先写评测 (test-first), 禁止"先实现后补测"。
