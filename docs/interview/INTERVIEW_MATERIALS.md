# SpecProof / SpecCraft — 面试答辩材料 (量化成果与叙事)

> 用途: 面试讲项目用。所有数字来自真实运行 (仓库 docs/eval/* 与 git log 可查证),
> 绝无估计值; 待补项明确标注 [待补]。更新日期: 2026-08-19。

## 0. 一句话

**SpecProof 是"AI 代码变更的验收防火墙", SpecCraft 是"被它审判的自主开发 Agent"** —
把"AI 写完代码"变成"AI 写完、被独立验证、出加密证据、才能合并"的受治理研发闭环,
本地全栈 (FastAPI + React + MySQL/ES/Redis/MinIO + Docker 沙箱) + 远程 LLM API。

## 1. 核心量化成果 (面试直接报)

### 1.1 检测能力 (金案例评测)
| 指标 | 数字 | 证据 |
|---|---|---|
| 100 金案例段2 (78-100) 初测 | Precision 100%, Recall 76.9%, F1 87.0%, 0 误报 | docs/eval/eval-report-rem.results.json |
| 3 个 rel 类 MISS 修复 (执行探针: 故障注入/发布计数/载荷捕获) | 修复后 3/3 = **Precision/Recall/F1 100%** | docs/eval/eval-report-rel.results.json (Docker DooD 实测) |
| 段2 全量复跑 / 段1 分块跑 | [待补 — pwsh-37 / pwsh-22 完成后回填 100 案例总表] | |
| LLM 基线对比 | 通用 LLM strict-id 召回 0% → SpecProof 检测 100% (**+100pp**) | docs/eval/llm-baseline-100-live.md |

### 1.2 Agent 能力 (90 任务评测集, 确定性档全量实测)
| 指标 | 数字 |
|---|---|
| 代码任务完成率 (50 题) | **98.0%** (49/50, trap 按口径 INTERCEPTED) |
| 陷阱拦截率 | **100%** (21/21) |
| 对抗任务 (误导 Issue/注入/过时测试/隐藏禁止) | **20/20 INTERCEPTED** |
| 断点恢复 | **10/10 RECOVERED** (副作用账本恰好 1 行, 幂等) |
| 危险动作审批 | **10/10 APPROVAL_REFUSED**, 违规 **0** |
| 平均迭代次数 | **1.23** (单次收敛) |
| 微基准 (legacy 口径) | 完成率 90.0%, 平均 1.1 迭代 |

### 1.3 检索 (30 查询黄金集, 真实 Docker ES)
| 系统 | recall@10 | MRR | 延迟 |
|---|---|---|---|
| BM25 | 82.2% | 0.656 | 50.5ms |
| symbol-index (四语言符号查表) | 75.6% | 0.683 | **1.3ms** |
| BM25+图谱插值 | 48.9% (消融结论: 待向量/RRF 重排) | 0.528 | 89.6ms |

### 1.4 工程质量门禁
- 单元测试: 644 → 990 → 1086 → **1158+ passed** (持续增长, 每轮真实复跑)
- ruff / mypy strict (19 文件) / bandit Medium+=0 — 全绿
- 密钥泄漏门禁: 全仓库 **0 真实 key** (扫描器拦截 + 假密钥拼接纪律)
- 前端: vitest **55/55**, Playwright e2e **9/9** (向导/详情/权限/降级, 真实应用非 mock)
- 设计系统: 21 组件 Aurora 语言, 暗/亮双主题, ⌘K 命令面板; bundle JS 269KB (gzip 83KB)

### 1.5 架构与安全
- DeepSeek V4 Pro 网关实测适配: 8/11 能力 (chat/流式/JSON/工具调用/thinking/用量);
  strict_tool_calls 400 → JSON Action Envelope 降级; KV-cache 友好 prompt 实测命中 512 tokens
- 安全: 注入 24 矩阵全过; 规则摄取 7 级优先级 + "忽略安全"冲突降级; 工具结果数据段隔离;
  跨租户访问 404+审计 (不泄露存在性); 4×4 RBAC; Ed25519 Merge Certificate 签名 fail-closed
- 可审计: 契约不可变版本 (id,version 追加式, 复合主键 SQL 层禁止就地改); 对象元数据查询;
  血缘链 contracts→findings→ChangeBundle; 审计日志含 before/after digest

## 2. 面试叙事模板 (按方向)

### 华为 Agent / 评测方向
"我做了受治理的代码 Agent 闭环: Agent 完成修改后必须通过五道门禁 (测试/构建/类型/安全/自校验),
再被独立防火墙做 Base/Head 差分执行与契约判定, 出具 Ed25519 证书才算验收。
量化: 90 任务评测集代码完成率 98%、陷阱拦截 100%; 金案例段2 修复执行探针后 Recall 100%。"

### 华为安全方向
"我的产品把 OWASP LLM Top 10 里的注入问题工程化: 24 类注入矩阵测试、仓库规则冲突降级
(含'忽略安全'的规则绝不获得高优先级)、工具输出数据段隔离、密钥零落盘门禁、跨租户 404+审计。"

### 华为昇腾/推理方向
"Provider 层做了 DeepSeek V4 Pro 网关的深度适配 (8/11 能力实测), KV-cache 友好 prompt
实测命中 512 tokens, 预算治理含 reasoning/cache 四类 token 记账 — 这套多模型路由经验
可直接平移到国产卡部署的模型网关。"

### 华为 RAG 方向
"我的检索有量化基线: BM25 recall@10 82.2%, 符号索引 75.6% @1.3ms, 并发现 4000 字符
截断盲区用符号索引找回 — 混合检索不是拍脑袋, 每个决策有消融数字。"

## 3. 与行业热点的对标 (面试加分点)

| 热点 | 我们的对应物 | 差异优势 |
|---|---|---|
| Hermes 类 Agent 模型 (工具调用强/不拒绝) | 13 工具注册表 + JSON Envelope + 确定性档 | 我们多了"裁判层": 模型必须被独立验证 (fail-closed) |
| MCP | 已有服务端 6 工具; [待补: 客户端] | 生态互操作 |
| SWE-bench | harness 已落地 (W45: 真实 craft 管道+honest unresolved 契约, 内置样本实测 resolved 1/2=50%, HF 数据获取真实下载) | 官方全量数字 = 文档化手动步骤 (需 per-instance 仓库+docker 镜像) |
| OpenHands/Devin 多智能体 | ParallelRunner 只读并行 + 写集冲突 fail-closed | 防覆盖是硬约束不是建议 |
| Mem0 记忆 | TaskMemory + checkpoint 恢复 10/10 | 副作用幂等有账本证明 |
| 变异测试 | 变异杀死率测量已落地 (W47) | 离线样本实测杀死率 83.3% (5/6; 1 幸存为规格外行为, 诚实记录); 真实仓库模式走 experiments.mutation+契约检查+沙箱 |

## 4. 待补数字清单 (冲刺项)
1. 100 案例总表 (段1 c1-c4 + 段2 复跑 → 全量 Recall/Precision/F1)
2. SWE-bench-Lite 解决率 ◐ harness 就绪 (W45), 样本 50% (1/2, 全证据); 官方全量数字待手动仓库+docker 步骤
3. 变异杀死率 ✅ 83.3% (离线样本, W47; 真实仓库数字待补跑)
4. 双模型路由成本对比 (本地小模型 vs 远程强模型, 每作业 token 成本)
5. p50/p95 验证延迟
