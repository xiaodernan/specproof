# W170+ 待办与 Go/No-Go 缺口展开 (BACKLOG)

> 生成: 2026-08-21 · 单一事实源链: EVOLUTION_GAP_MAP.md §D + go-nogo.md + SWEBENCH_PLAN.md §8.6
> 状态约定: ⬜ 待做 · 🔨 在途 · ✅ 完成 · ⛔ 仓库外依赖 (如实报告, 不编造)

## 0. 抢救状态 (上个会话中断处)

| 项 | 状态 | 说明 |
|---|---|---|
| scripts/bench_cost.py + cost-results.json | ✅ | 已随 W171/W172 提交 (#15 仓库内半程) |
| SWE-bench v12 (最强档 v4-pro 重测) | ✅ | 已随 W172 提交 (诚实 0%, v13=官方 Docker/网关外) |
| agent/nodes/run_differential.py P2 both-fail 拆分 | 🔨 | 工作树 +338/-93, 单测 98/98 绿, 待全案例 eval 复核后提交 (W176) |
| tests/unit/test_attribution_att08.py | 🔨 | 11 例随 W176 提交 |

## 1. Go/No-Go 缺口

### 1.1 #3 归因准确率 PARTIAL→PASS (att-08 both-fail)

- **缺口**: Base/Head 各自失败时整轮折叠为 AMBIGUOUS severity-NONE, 掩盖 head 侧
  EVENT_ONCE-01 回归 (实测 88.9% < 90%, 唯一漏归因)。
- **修复 (已在工作树)**: surefire XML 逐方法结果 → head_only/base_only/both 三组拆分;
  head_only → REGRESSION 归因 head; base_only → UNEXPECTED_FIX 永不归因 head;
  both → AMBIGUOUS 不变。Review Court 按 method-scoped 出口码走预存缺陷规则。
- **验收**: scripts/attribution_cases.py run + eval --cases golden-cases-attribution
  归因准确率 ≥ 90% (预期 100%) → 更新 go-nogo.md #3 → 提交 W176。

### 1.2 #15 成本 PENDING (仓库内半程)

- **缺口**: 无端到端每作业成本测量; 现仅预算机制。
- **仓库内可做**: bench_cost.py 按真实 craft report 的 token 四分类折算 USD
  (示例价表, 真实账单才是唯一事实源) + token 预算对照 + cost-results.json 落盘。
- **仓库外 (⛔)**: 真实网关账单对账 + 沙箱/DB 资源成本 → 门槛保持 PENDING 直至有真实账单。

### 1.3 #12 试点 / #13 用户 PENDING

- **仓库内可做**: ✅ PILOT_RUNBOOK 已落地 (docs/operations/PILOT_RUNBOOK.md);
  ✅ 反馈机制已落地 (W174: migration 0009 + POST/GET feedback 端点 + 统计,
  5 例单测)。
- **仓库外 (⛔)**: 真实试点运行与用户反馈数据 — 无法在仓库内产生。

## 2. DevMind 能力移植对照 (分析/修Bug/生成测试/文档/架构/安全/性能)

| DevMind 能力 | SpecProof 现状 | 处置 |
|---|---|---|
| 修 Bug | ✅ cli fix/approve (agent/fixes.py 确定性修复+编译验证) + Craft LLM 修复循环 | 已存在, 更强 |
| 生成测试 | ✅ generate_counterexamples 节点 (JUnit 生成, LLM+回退) | 已存在, 更强 |
| 安全审计 | ✅ security_scanner + 密钥 canary + 注入负样本 + 沙箱 | 已存在, 更强 |
| 性能分析 | ✅ 差分执行性能语义 (p95 161.1s 实测) + DB 状态取证 | 已存在, 更强形态 |
| 代码分析 (质量评分/异味) | ⬜ 仅契约检查器, 无通用质量评分/圈复杂度/异味 | **✅ devtools quality 已落地 (W173)** |
| 文档生成 | ⬜ 无 | **✅ devtools docs 已落地 (W173)** |
| 架构审查 | ⬜ 无 | **✅ devtools archreview 已落地 (W173)** |

## 3. SWE-bench v12 (台账方向: 更强模型档位 / 官方 Docker 口径)

- **仓库内可做**: ✅ bench_swebench.py --model CLI 覆盖已落地 (§8.8, W175);
  v12 实测已随 W172 入库 (最强档 v4-pro, 诚实 0%)。
- **官方 Docker 口径**: §3.4 文档化手工步骤保持不变 (逐实例镜像+官方 log-parser);
  仓库内不伪造任何官方数字。

## 4. 待派队列 (EVOLUTION_GAP_MAP §D, 优先级序)

1. run_static_checks 检查器注册表+兼容矩阵 (⬜)
2. build_matrix 完整行字段+纯函数 (⬜)
3. att-08 both-fail 归因修复 (🔨 见 1.1)
4. 生产试点 3 仓库 2 周 (⛔ 见 1.3)
5. RUNNING-job 回收器 + WAITING_FOR_PROVIDER 接线 (⬜)
6. 跨语言案例样本 TS/Go (⬜; Python ✅ W78/W105)
7. 恶意构建脚本/输出洪水/缓存投毒测试 (⬜)
8. Job 创建白名单 (禁任意命令/env/docker) (⬜)
9. Envelope retryable 字段 + SSE 序列号/保留策略 (⬜)
10. ES 投影删除清理 (⬜)
11. Grafana/SLO 面板 · Python 依赖锁 · 每作业成本会计 (✅ W171) · court 无证据 BLOCKER 不变式测试 (✅ W157)

## 5. 诚实边界

- #12/#13 的 PASS 需要真实试点与真实用户, #15 的 PASS 需要真实账单 — 仓库内只能完成
  机制与手册, 测量保持 PENDING 不编造。
- SWE-bench 官方口径数字只能在官方 Docker 流程上产生; harness 口径数字必须标注
  "harness 口径, 非官方口径"。
- 本清单随每轮进度回填, 与 EVOLUTION_GAP_MAP.md / go-nogo.md 保持一致。
