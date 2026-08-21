# W170+ 待办与 Go/No-Go 缺口展开 (BACKLOG)

> 生成: 2026-08-21 · 单一事实源链: EVOLUTION_GAP_MAP.md §D + go-nogo.md + SWEBENCH_PLAN.md §8.6
> 状态约定: ⬜ 待做 · 🔨 在途 · ✅ 完成 · ⛔ 仓库外依赖 (如实报告, 不编造)

## 0. 抢救状态 (上个会话中断处)

| 项 | 状态 | 说明 |
|---|---|---|
| scripts/bench_cost.py + cost-results.json | ✅ | 已随 W171/W172 提交 (#15 仓库内半程) |
| SWE-bench v12 (最强档 v4-pro 重测) | ✅ | 已随 W172 提交 (诚实 0%, v13=官方 Docker/网关外) |
| agent/nodes/run_differential.py P2 both-fail 拆分 | ✅ | 修复+实测 100.0% 已随 W182 提交 |
| tests/unit/test_attribution_att08.py | ✅ | 随 W182 提交 (FQN surefire 形状钉死) |

## 1. Go/No-Go 缺口

### 1.1 #3 归因准确率 PARTIAL→PASS ✅ (att-08 both-fail, W182)

- **缺口**: Base/Head 各自失败时整轮折叠为 AMBIGUOUS severity-NONE, 掩盖 head 侧
  EVENT_ONCE-01 回归 (首测 88.9% < 90%, 唯一漏归因)。
- **根因二连**: (1) surefire 报告是 FQN 文件名 (TEST-com.specproof.demo.….xml),
  旧 `_test_outcomes` 只找 bare 名 → 永远空 → 拆分从未真正生效; (2) 修复后发现
  att-08 是「遮蔽型」场景: base 侧 UNIQUE 缺陷让 EVENT 测试在 base 同样失败 →
  同方法 both-fail, 但 base/head 失败签名不同。
- **修复**: `_surefire_report` 直名+包后缀 glob; both 组增加失败签名差异化归因
  (签名不同 → court 归因 head, MINOR/0.65 诚实降置信; 签名相同保持 AMBIGUOUS)。
- **验收 (实测)**: attribution_accuracy = **100.0%** (正确归因 7/7, 错归因 0/2,
  漏归因 0/7; att-08: EVENT_ONCE-01 归因 head, UNIQUE-01 base 预存未归因) →
  go-nogo.md #3 PARTIAL→PASS。

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

1. run_static_checks 检查器注册表+兼容矩阵 (✅ W189: 10 检查器全条目+元数据+矩阵 10×8+fail-closed 查询, 15+70 测试)
2. build_matrix 完整行字段+纯函数 (✅ W180: 11 court 字段补齐+渲染时间戳纯函数化, 16+72+47 测试)
3. att-08 both-fail 归因修复 (✅ W182, 见 1.1)
4. 生产试点 3 仓库 2 周 (⛔ 见 1.3)
5. RUNNING-job 回收器 + WAITING_FOR_PROVIDER 接线 (✅ W179: CAS 回收+provider 停放, 23+70 测试)
6. 跨语言案例样本 TS/Go (✅ W188: TS node --test 真实运行 + Go 无工具链如实标注, 管线 unsupported 诚实记录; 跨语言执行器属 P6 基础设施)
7. 恶意构建脚本/输出洪水/缓存投毒测试 (✅ W181: 45 例+三真实缺陷修复, 176+2 测试)
8. Job 创建白名单 (禁任意命令/env/docker) (✅ W178: /jobs 已 fail-closed 审计确认; /agent/jobs 补白名单 422 点名字段, 44 新测试)
9. Envelope retryable 字段 + SSE 序列号/保留策略 (✅ W186: retryable 已存在 (W83) 审计确认; SSE 补绝对 sequence 计数器+保留策略常量/env 配置, 34+79 测试)
10. ES 投影删除清理 (✅ W185 库层 + 🔨 lane 0c607774 生产接线在途)
11. Grafana/SLO 面板 · Python 依赖锁 · 每作业成本会计 (✅ W171) · court 无证据 BLOCKER 不变式测试 (✅ W157)

## 5. 诚实边界

- #12/#13 的 PASS 需要真实试点与真实用户, #15 的 PASS 需要真实账单 — 仓库内只能完成
  机制与手册, 测量保持 PENDING 不编造。
- SWE-bench 官方口径数字只能在官方 Docker 流程上产生; harness 口径数字必须标注
  "harness 口径, 非官方口径"。
- 本清单随每轮进度回填, 与 EVOLUTION_GAP_MAP.md / go-nogo.md 保持一致。
