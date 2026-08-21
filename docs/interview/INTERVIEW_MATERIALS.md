# SpecProof / SpecCraft — 面试答辩材料 (量化成果与叙事)

> 用途: 面试讲项目用。所有数字来自真实运行 (仓库 docs/eval/* 与 git log 可查证),
> 绝无估计值; 待补项明确标注 [待补]。更新日期: 2026-08-20。

## 0. 一句话

**SpecProof 是"AI 代码变更的验收防火墙", SpecCraft 是"被它审判的自主开发 Agent"** —
把"AI 写完代码"变成"AI 写完、被独立验证、出加密证据、才能合并"的受治理研发闭环,
本地全栈 (FastAPI + React + MySQL/ES/Redis/MinIO + Docker 沙箱) + 远程 LLM API。

## 1. 核心量化成果 (面试直接报)

### 1.1 检测能力 (金案例评测)
| 指标 | 数字 | 证据 |
|---|---|---|
| 100 金案例段2 (78-100) 最终 | **Precision 100%, Recall 100%, F1 100%, 0 误报** (探针全开复跑, 13/13) | docs/eval/eval-report-rem3.results.json |
| 3 个 rel 类 MISS 修复 (执行探针: 故障注入/发布计数/载荷捕获) | 修复后 3/3 = **Precision/Recall/F1 100%** | docs/eval/eval-report-rel.results.json (Docker DooD 实测) |
| 100 案例全量 (段1 c1-c4 + 段2 探针全开, 修复后最终重跑) | **Recall 100.0% / Precision 100.0% / F1 100.0%, 误报 0** (63/63; 五块重跑 c1/c2/c3/c4/rem3 全 100%, 修复路径逐案例可查) | docs/eval/eval-c1-rerun / eval-c2-rerun / eval-c3-rerun / eval-c4-rerun / eval-rem3 + eval-report-rem3 |
| LLM 基线对比 | 通用 LLM strict-id 召回 0% → SpecProof 检测 100% (**+100pp**) | docs/eval/llm-baseline-100-live.md |
| PR 归因准确率 (Go/No-Go #3) | **100.0%** (8 案例归因集: 正确归因 7/7, 错归因 0/2, 漏归因 0/7; att-08 both-fail 拆分+失败签名差异化归因) | docs/eval/attribution-results.json |

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
- 单元测试: 644 → 990 → 1086 → 1158 → 1981 → 2069 → 2369 → **2530 passed, 3 skipped** (终门禁全绿, 2026-08-20 实测)
- ruff / mypy strict (19 文件) / bandit Medium+=0 — 全绿
- 密钥泄漏门禁: 全仓库 **0 真实 key** (扫描器拦截 + 假密钥拼接纪律)
- 前端: vitest **90/90** (19 文件), Playwright e2e **9/9** (向导/详情/权限/降级, 真实应用非 mock)
- 设计系统: 21 组件 Aurora 语言, 暗/亮双主题, ⌘K 命令面板; bundle JS 269KB (gzip 83KB)
- Go/No-Go 15 门槛: **12/15 PASS · 0 PARTIAL · 3 PENDING** — #3 归因 100.0% (att-08 both-fail 拆分+签名差异化归因) / #4 回放 25/25=100% / #5 无证据 BLOCKER 不变式 19 例 / #6 p95 161.1s / #9+#11 真实演练 / #14 LLM 基线 +100pp (docs/eval/go-nogo.md)

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
| SWE-bench | harness 已落地 (W45: 真实 craft 管道+honest unresolved 契约, HF 数据真实下载); 真实跑 v1-v12 十二轮每轮消一类障碍 (信封→venv→测试文件误改→编辑锚点→判据退化→依赖漂移→venv 复用→后缀路径→测试收集→重复提案→瞬时超时), resolved 率诚实 0% — harness 层清完, 剩余模型能力层 (v12 实测网关仅 v4-flash/v4-pro 两档, 无更强档) | v13: 官方 Docker 口径 / 网关外更强模型 |
| OpenHands/Devin 多智能体 | ParallelRunner 只读并行 + 写集冲突 fail-closed | 防覆盖是硬约束不是建议 |
| Mem0 记忆 | TaskMemory + checkpoint 恢复 10/10 | 副作用幂等有账本证明 |
| 变异测试 | 变异杀死率测量已落地 (W47) | 离线样本实测杀死率 83.3% (5/6; 1 幸存为规格外行为, 诚实记录); 真实仓库模式走 experiments.mutation+契约检查+沙箱 |

## 4. 待补数字清单 (冲刺项)
1. ~~100 案例总表~~ ✅ **100.0/100.0/100.0** (63/63, 误报 0; 段1 三块重跑实录, eval-100-segments.md)
2. SWE-bench-Lite 解决率 ◐ 真实跑 v1-v12 十二轮全部诚实 0% (harness 障碍逐轮清完; v12 实测网关仅 v4-flash/v4-pro 两档无更强档; v13 = 官方 Docker 口径/网关外更强模型在途); 官方全量数字待 Docker 环境
3. 变异杀死率 ✅ 83.3% (离线样本, W47; 真实仓库数字待补跑)
4. 双模型路由成本对比 (本地小模型 vs 远程强模型, 每作业 token 成本)
5. p50/p95 验证延迟
