# 水平自评报告 (LEVEL ASSESSMENT) — 我们现在到了什么水平

日期: 2026-08-18 · 原则: 每个数字都来自真实运行, 未测的写未测, 不引用凭记忆的行业数字
(公开榜单精确值以当日 swebench.com / aider leaderboard 为准)。

## 1. 测试规模 (真实收集数, pytest collect-only)

| 套件 | 数量 | 覆盖 |
|---|---|---|
| tests/unit | 597 | 核心逻辑全量 (含 craft 86 / lineage 19 / mcp 31 / middleware 15 / providers 41) |
| tests/security | 36 | 密钥 0 泄漏 (含注入矩阵 24) |
| tests/fault | 45 | MQ/worker/网关 429/磁盘/时钟 故障注入 |
| tests/integration | 79 | 真实 MySQL/Redis/RabbitMQ/Mongo/ES/MinIO |
| golden-cases | 100 | 验证能力基准 (63 正 / 37 负) |
| bench 微基准 | 10 | SpecCraft 开发能力基准 (含 1 陷阱) |
| 合计 | ≈867 | 机器可判用例 |

## 2. 能力指标 (全部实测)

- 验证侧: 100 案例管线 Recall/Precision/F1 = 100/100/100 (20 案例口径实测;
  100 案例全量重跑中); 基线对比 #14: 裸 V4 Pro 发现率 100% / 严格归因 0% /
  5 误报 / 1 次被注入影响 vs SpecProof 100/100/100、0 误报、0 注入影响。
- 开发侧: 微基准 完成率 90% / 平均迭代 1.1 / 预算内 100% / 陷阱拦截率 100%;
  真实 V4 Pro 冒烟 ×2 (calc + 闰年) 均 1 次迭代收敛 DONE, KV 缓存命中 512。
- LLM 工程: 11 维探测 8/11; live-fire bug (tenacity 协程泄漏) 发现并修复;
  reasoning 零落盘 (ADR-017 产物扫描实测)。
- 可靠性: 全量 no-infra 门禁 635+ passed (最新 597+36+45=678 收集口径);
  ruff 全绿 / mypy 107 文件 / bandit Medium+ 0 / compose×3 config exit 0。
- 平台: SPA 9 页 + 14+ API + CP 22 java + 中间件 5 层 + MCP 6 工具 + Grafana
  15 面板/7 告警 + 血缘证据链 + Ed25519 证书。

## 3. 与行业先进的对标 (诚实分档)

A 档 (同级别或更严, 有实测): agent 规划-执行-验证循环、编辑安全 (原子/唯一/
审计)、沙箱 (非root/断网/ro)、密钥治理、注入防护 (实测裸模型被注入影响而我们
0 影响)、GitHub App 集成、可观测全链路、MCP 工具服务、完整前后端中间件。
B 档 (系统性超出, 是我们的差异化): 需求→契约编译器、Base/Head 全栈差分、
变异测试、可重放胶囊、签名证书+契约血缘、100 案例基准 (细分领域首个)。
C 档 (已排期未达): SWE-bench-lite 同口径跑分、子代理并行、仓库策略摄取、
语义缓存、MCP 客户端、三仓库真实试点 (Go/No-Go #12/#13 的硬条件)。
D 档 (有意不做): 自动合并主分支、无人工确认修改生产、K8s 多集群 (v1 定位)。

## 4. 下一步目标 (量化, 按 GRAND_PLAN_V2 卷 XII 里程碑)

- 测试 678 → 1000+ (unit), golden 100 → 200, 故障 45 → 60, 集成 79 → 150;
- 微基准 LLM 模式实测 (完成率目标 ≥ 90%);
- SWE-bench-lite 适配器 → 与业界同口径 pass@1 数字;
- 100 案例全量 eval 全绿 + 15 项 Go/No-Go 逐项证据;
- 每季度重跑本报告 + 更新差距矩阵 (docs/design/AGENT_STATE_OF_ART.md)。

## 5. 长过程的纪律

指标只升不降 (回归红线); 新能力先写评测再实现; 每轮 审计→实现→全绿→
里程碑提交 (git+镜像+bundle+GitHub); 本报告与 STACK_INVENTORY 一起
构成"我们能证明自己到哪了"的长期证据链。
