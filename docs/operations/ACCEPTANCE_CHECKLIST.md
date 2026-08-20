# 大老板验收清单 (ACCEPTANCE_CHECKLIST) — 对照三大文档

日期: 2026-08-20 · 三大文档: 工业化商业化终极开发指南 (727行) / 代码开发Agent商业化终极计划书 (1005行) / 持续演进终极目标与链路计划 (1276行)。原则: 只列真实运行证据, 未验证项明确标注。

## 一、验收动线 (老板可亲手点, 本地一键)

1. `powershell -ExecutionPolicy Bypass -File scripts/start_local.ps1` → 打开 http://localhost:5173
2. 验证流: 【演示】任务已就绪 (矩阵/Findings/证书/胶囊可下载) → 新建验证 (真实跑 QUEUED→终态, W43.1 实测 BLOCKED)
3. Agent 流: 新建任务 → 计划审阅 (批准) → 实时工具流 (SSE) → 五道门禁 → accept 判定 (确定性档, 无 LLM 无 key)
4. 视觉: Aurora 暗/亮双主题 + ⌘K 命令面板 + /ui-kit 活样式指南
5. 权限: 登录 → 租户切换 → viewer/admin 差异 (计费页 viewer→TENANT_FORBIDDEN)
6. 计费: /#/billing 套餐/订阅/用量/发票
7. IDE: ide/vscode 扩展 (任务侧栏/计划树/审批/虚拟 diff)

## 二、量化成果 (面试/验收直接报, 全部真实运行)

- 100 金案例: **Recall/Precision/F1 100.0%** (63/63, 误报 0; 五块重跑 c1/c2/c3/c4/rem3 全 100%, 修复路径逐案例可查 eval-100-segments.md)
- 90 任务评测集: 代码完成率 **98.0%**, 陷阱/对抗/恢复/审批 **100%/100%/100%/100%** (违规 0)
- 检索: BM25+RRF recall@10 **87.2%** MRR 0.760 (+15pp); symbol-index 75.6%@1.3ms
- 变异杀死率 **83.3%**; LLM 基线对比 **+100pp**
- Go/No-Go 15 门槛: **PASS 12/15 · PENDING 3/15 (#12 试点/#13 用户/#15 成本)** — #3 归因 100.0% (att-08 both-fail 拆分+签名差异化归因, 7/7 正确 0 漏归因) / #4 Capsule 回放 25/25=100% 门禁 PASS / #5 无证据 BLOCKER 不变式测试 19 例 / #6 FAST p95 161.1s / #14 LLM 基线 +100pp (docs/eval/go-nogo.md)
- 质量门禁: 单元 **2369 passed + 3 skipped** 全绿; ruff/mypy strict/bandit Medium+=0; 密钥泄漏 **0**
- 前端: vitest 90+, Playwright e2e 9/9; 设计系统 21 组件
- SWE-bench-Lite: harness+LLM 模式就绪; 真实跑十二轮 (v1-v12) 每轮消掉一类失败 (信封→venv→测试文件误改→编辑锚点→判据退化→依赖漂移→venv 复用→后缀路径→测试收集→重复提案→瞬时超时), resolved 率始终诚实 0% — harness 层障碍已清完, 剩余模型能力层 (v12 实测: 网关仅 v4-flash/v4-pro 两档无更强, 最强档重测仍模型层重复提案 STUCK; v13 = 官方 Docker 口径/网关外更强模型)

## 三、三大文档逐条状态 (浓缩版, 全量见三份审计)

- 指南 §14 首批 15 任务: **15/15 完成** (最后一缺口 Worker 取消检查点已由 W85B 关闭)
- 计划书 §22 首批 12 任务: **12/12 完成** (结构化 Diff/AST 编辑 W58; IDE W88; MCP 客户端 W59/W97)
- 演进计划 §十二 验收清单: 产品闭环 7/7, 开发 Agent 闭环 6/6, 安全与隔离 5/5 (Linux 非root 沙箱待基础设施), 可靠性与运维 5/5 (恢复/安全演练 W89 已落地: worker-kill 真实 9.09s 恢复 BLOCKED=对照 / provider 故障零虚构 / outbox exactly-once, 桌面核对 9 可执行 4 需开发), 评测与商业 4.5/5 (Capsule 回放 100% 门禁 PASS; SWE-bench 十一轮真实跑实录, 解决率诚实 0% 待官方口径)

## 四、诚实缺口 (验收当天如实汇报, 不掩饰)

1. ~~段1 三个 MISS + 3 误报~~ **已修复: 100 案例重跑 63/63 误报 0 → 100%** (W48c/W48d + 三块重跑实录)
2. ~~Capsule 全量回放率~~ **已达标: 25/25 = 100.0% 门禁 PASS** (双层口径: 运行时复现+静态证据复验+探针重放; 枚举 28 排除 3 制品逐字注记=演示种子+2 规则前陈旧摘要; 六轮轨迹 28.57→35.71→42.86→82.14→92.0→100.0%, docs/eval/replay-results.md)
3. SWE-bench-Lite 真实解决率: v1-v12 十二轮真实跑诚实 0% (harness 障碍逐轮清完; v12 实测网关仅 v4-flash/v4-pro 两档无更强档, 最强档重测仍模型层重复提案; v13 = 官方 Docker 口径/网关外更强模型在途); Aider polyglot W98 已落地 (harness 全绿, 离线样本诚实 unresolved)
4. Linux 非 root 沙箱实测、KMS/HSM、跨语言 Gradle/Node/Go 适配器 — 依赖基础设施, 本地不可验
5. 前端收尾 W101 已落地 (billing 路由/wizard/权限页/progress 形状, 19 文件 90 测试+build 全绿)
