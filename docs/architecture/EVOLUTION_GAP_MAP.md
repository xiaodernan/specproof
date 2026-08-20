# 持续演进终极目标与链路计划 — 对照差距地图 (EVOLUTION_GAP_MAP)

> 更新: 2026-08-20 最终复核

依据: docs/持续演进终极目标与链路计划.md (1276 行, 已通读) × 两份需求文档 × 当前主线真实状态。
状态: ✅ 已实现+有证据 · 🚧 车道在途 · ⏳ 已排队/待派 · ◐ 部分 (注明缺什么)。本表随每轮回填。

## A. §十二 最终验收清单对照

### 产品闭环
| 项 | 状态 | 缺口 |
|---|---|---|
| CLI/Web/MCP/GitHub 发起 Verify Job | ◐ | MCP 发起验证作业未实装 (MCP 6 工具为查询类) |
| Job 全态可查 | ✅ | — |
| Contract 批准/拒绝/撤销/版本追踪 | ✅ W38 | — |
| 每 Contract 见实验/结果/证据/回放入口 | ◐ | 矩阵行字段待补 (最低证据等级/未验证原因/下一步) |
| 严重 Finding 无证据不升级/签发 | ✅ | — |
| Capsule 干净环境重放 + replay record | ✅ | 25/25=100.0% (Go/No-Go #4 PASS; docs/eval/replay-results.md 六轮 28.57→35.71→42.86→82.14→92.0→100.0%; scripts/bench_replay.py 两层+排除+probe 重放) |
| 证书离线验证 (摘要/签名/工具链/撤销) | ◐ | 撤销状态缺 (阶段5) |

### 开发 Agent 闭环 → ✅ 全达标 (W26-W35: 计划审批/工具治理/原子编辑/五道门/强制 accept/取消恢复 10/10)

### 安全与隔离
| 项 | 状态 | 缺口 |
|---|---|---|
| 凭据零入代码/日志/Prompt/Capsule/报告 | ✅ | — |
| 租户/角色/对象访问自动化测试 | ✅ W37 | — |
| Webhook 验签/重放/限流/路径/脱敏 | ✅ | — |
| 沙箱非 root/无网络/资源受限/无宿主秘密/无 docker.sock | ◐ | Linux 非 root 沙箱 ⏳ (仍为真实缺口) |
| 注入/恶意脚本/符号链接/输出洪水/缓存投毒测试 | ◐ | 注入 24 矩阵 ✅; 恶意构建脚本/输出洪水/缓存投毒 ⏳ |

### 可靠性与运维
| 项 | 状态 | 缺口 |
|---|---|---|
| 五存储 + 状态机真实故障演练 | ◐ | 恢复演练 ✅ (W89 DRILLS: Drill1/2/4 真实执行); 五存储全量故障演练仍部分 |
| Worker kill 后 checkpoint 恢复不重复副作用 | ✅ | W89 Drill1 真实 worker kill 6 检查点 → 9.09s resume → BLOCKED=control (docs/operations/DRILLS.md) |
| SSE 断线重连 | ✅ Last-Event-ID | — |
| 迁移空库安装/备份恢复/删除导出 | ◐ | 迁移 ✅ (至 0008, W84); 删除导出 ⏳; 主机备份工具 ⏳ (DRILLS 4 需开发) |
| 观测覆盖全链 | ◐ | 指标扩展 ⏳; Grafana/SLO 面板 ⏳ (真实缺口) |

### 评测与商业
| 项 | 状态 | 缺口 |
|---|---|---|
| Golden/holdout/负样本/跨语言/攻击样本分层 | ◐ | golden 100 ✅ = 100.0% (63/63, FP 0; docs/eval/eval-100-segments.md)/负样本 ✅/攻击 20 ✅/holdout ✅; 跨语言 ⏳ (aider polyglot 1/3=33.3% 已立 W98; 样本扩展待) |
| Recall/Precision/归因/回放/成本/延迟/恢复率原始结果 | ◐ | 回放率 ✅ 100.0% (25/25); 归因准确率 ◐ 88.9% (8 案例集实测, Go/No-Go #3 PARTIAL, att-08 修复在途); 成本 ⏳ (每作业成本会计未建) |
| 用量账本可重建/配额可解释 | ✅ W40 | — |
| 恢复演练 + 安全响应演练 | ✅ | W89 DRILLS 已执行: Drill1 真实 kill/Drill2 provider outage 真实 (3× APITimeoutError, breaker open, degrade_reasons)/Drill4 outbox 崩溃→exactly-once/Drill3 安全桌面推演 9 可执行 4 需开发 (docs/operations/DRILLS.md) |
| 对外材料只用证实数字 | ✅ | — |

## B. §十四 逐目录任务对照 (节选高价值缺口)

### agent/ 验证内核
| 任务 | 状态 | 车道 |
|---|---|---|
| compile_contracts 编译报告 | ⏳ | 待派 |
| prepare_base/head 仓库安全检查抽取+崩溃回收器 | ⏳ | 待派 |
| collect_diff 文件/符号/语义三级范围 | ◐ | 符号级有 (W29); 语义候选 ⏳ |
| run_static_checks 检查器注册表+兼容矩阵+CHECKER_FAILED+路径规范化 | ⏳ | 待派 |
| generate_counterexamples 四阶段拆分 | ◐ | 部分; 反例最小化 ✅ (W105 experiments/minimize.py ddmin); 审查阶段 ⏳ |
| run_differential 采集器/稳定判定 | ◐ | 探针采集器 ✅ (W36); 稳定/偶发判定 ⏳ |
| review_court 模型/政策分层+预存缺陷+审计 | ◐ | 分层落地 (W49); 无证据 BLOCKER 不变式测试 ⏳ (真实缺口) |
| build_matrix 纯函数+竞争写测试+完整行字段 | ⏳ | 待派 |

### 其余目录 (要点)
storage: Outbox 死信+指标 ✅ (W84 DLQ+metrics) · RabbitMQ 可观测事件 ◐ · Redis 租约最大持有+心跳 ⏳ · Mongo checkpoint schema 版本 ⏳ · MinIO 命名/生命周期 ✅ (W84 对象路径治理) · ES 租户过滤 ✅ (W84) / ES 投影删除清理 ⏳
api: Job 创建白名单 (禁任意命令/env/docker) ⏳ · SSE 序列号/保留策略/终态幂等 ◐ · 错误 retryable 字段 ⏳
apps/web: 向导第一步全信息 ✅ (W101) · 健康页五类状态 ⏳ · 权限页来源/失效 ✅ (W101)
providers/retrieval/craft: 统一网络客户端+日志脱敏 ◐ · 检索结果带提交/行号 ◐ · Craft 工具可取消点 ◐ (node 级取消检查点 ✅ W106) · 成本函数 ◐ (每作业成本会计 ⏳)

## C. 车道落地状态 (2026-08-20 最终复核)
- ✅ W48 (1233964a): 段1 缺口修复 — 100 金案例 Recall/Precision/F1 = 100.0% (63/63, FP 0); 五 chunk 修复后全重跑 (docs/eval/eval-c1-rerun.results.json / eval-c2-rerun / eval-c3-rerun / eval-c4-rerun / eval-rem3-rerun); 段1 六案例 25/33/29 → 100/100/100 (docs/eval/eval-seg1-fixed.results.json)
- ◐ W49 (668a62ba): Review Court 模型/政策分层 + 预存缺陷规则 — 剩余: 无证据 BLOCKER 不变式测试 ⏳
- ✅ W50 (b87257e5): SWE-bench LLM 十一轮 v1-v11 诚实实录 (docs/eval/swebench-llm-results-v1..v11.json); 每轮消一类失败 (envelope/venv → test-file edits (W112) → edit anchors+verify target (W113) → 判据重建 (W114) → 依赖漂移 werkzeug url_quote → venv 复用 (W147) → 后缀路径 (W143) → 测试收集 (W156) → 重复提案 (W161) → 瞬时超时 (W165)); resolved 0% 诚实记录, harness 层障碍清完剩模型能力层; official-docker 范围 (docs/eval/SWEBENCH_PLAN.md §8.6)
- ⏳ W51 (839d6d6d): 检索 RRF 融合 (目标超 BM25 82.2%) — 本轮事实清单未确认落地
- ⏳ W52 (ebfc3954): compile_contracts 编译报告 (14.1) — 本轮事实清单未确认落地
- ⏳ W53 (768328aa): prepare_base/head 仓库安全检查抽取+崩溃回收器 (14.1) — 本轮事实清单未确认落地
- ✅ W54 → W101: 向导第一步全信息+权限页来源/失效 ✅ (W101: 19 文件 90 测试+typecheck+build 全绿); 健康页五类状态 ⏳
- ✅ 阶段0 治理: 治理文档落盘 (W103: DATA_DICTIONARY.md + STATE_MACHINES.md + DEPENDENCY_LOCK.md + README)
- ✅ 后台 pwsh-22 段1 c4: 段1 六案例 25/33/29 → 100/100/100 (docs/eval/eval-seg1-fixed.results.json)
- ✅ 其他落地车道: W102 Policy DSL+豁免流 (agent/policy_dsl.py + agent/waiver.py, 42 测试) · W104 SWE-bench 排行榜实时拉取 (docs/eval/SWE_BENCH_LEADERBOARD.md, 180 Verified) · W110 租户中间件修复 · W106 node 级取消检查点 · W107 capsule 注入修复 · W105/W108 收尾 · W125/W128/W133 回放分层 · W89 演练 (docs/operations/DRILLS.md) · W96/W123/W126/W129/W132/W134 回放测量 (25/25=100.0%) · W84 存储治理 (Outbox DLQ+指标/MinIO 治理/ES 租户过滤/迁移 0008) · W78/W105 PythonAdapter local-first + ddmin (experiments/adapters.py + experiments/minimize.py)

## D. 待派队列 (按优先级, 2026-08-20 复核)
1. run_static_checks 检查器注册表+兼容矩阵
2. build_matrix 完整行字段+纯函数
3. ✅ 独立归因准确率指标已建并实测 88.9% (Go/No-Go #3 PARTIAL; att-08 both-fail 归因修复在途)
4. 生产试点 (3 仓库 2 周)
5. 自动 RUNNING-job 回收器 + WAITING_FOR_PROVIDER 接线
6. 跨语言案例样本 (TS/Go; Python ✅ W78/W105)
7. 恶意构建脚本/输出洪水/缓存投毒测试
8. Job 创建白名单 (禁任意命令/env/docker)
9. 错误 Envelope retryable 字段 + SSE 序列号/保留策略
10. ES 投影删除清理 ⏳ (Outbox DLQ+指标/MinIO 治理/ES 租户过滤 ✅ W84, 迁移 0008)
11. Grafana/SLO 面板 · Python 依赖锁 snapshot · 每作业成本会计 · court 无证据 BLOCKER 不变式测试