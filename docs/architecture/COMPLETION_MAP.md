# 双文档逐节完成度地图 (COMPLETION_MAP) — 持续更新

> 更新: 2026-08-20 最终复核

依据: docs/工业化商业化终极开发指南.md (727 行) + docs/代码开发Agent商业化终极计划书.md (1005 行), 已逐节通读。
状态图例: ✅ 已完成且有真实证据 · 🚧 车道在途 · ⏳ 已设计/排队 · ◐ 部分完成 (证据注明)。
证据链: 提交 W13..W197 见 git log; 门禁数字全部来自真实运行 (2026-08-20 最终复核: unit 2530 passed/3 skipped)。

## A. 工业化商业化终极开发指南 (727 行)

| 节 | 内容 | 状态 | 证据/备注 |
|---|---|---|---|
| §0-2 | 阅读结论/现状/产品定义 | ✅ | README + SALES_PITCH + STACK_INVENTORY |
| §3.1 领域划分 | ✅ | docs/architecture/domain-model.md |
| §3.2 服务边界 | ✅ | STACK_INVENTORY (specproof-* 服务) |
| §3.3 数据分层 | ✅ | MySQL/Mongo/ES/Redis/MinIO 适配器全有; 数据字典 ✅ (W103 DATA_DICTIONARY.md); 迁移至 0008 (W84) |
| §3.4 事件 Envelope | ✅ | W28 contracts/events.py (12 字段/脱敏/sha256) |
| §4.1 身份租户权限 | ✅ | W37 (OIDC+sp_*+RBAC 4×4+跨租户 404+迁移 0005) |
| §4.2 Job 状态机 | ✅ | 状态机+SSE+取消 (W14/P) |
| §4.3 提交验证 API | ✅ | POST /jobs + OpenAPI 差分门禁 (W28) |
| §4.4 Contract 领域增强 | ✅ | W38: checker_version+不可变版本+对象元数据 (已落地; GUIDE_GAP_AUDIT §A 任务 6/7) |
| §4.5 执行沙箱 | ✅ | DooD 沙箱+15 测试; Linux 非 root 沙箱 ⏳ (真实缺口) |
| §4.6 LLM Provider 治理 | ◐ | V4 Pro 适配+TokenBudget ✅; 租户预算 ✅ (W40); 模型路由 ⏳ (M9) |
| §4.7 证据签名重放 | ◐ | Ed25519+血缘 ✅; 胶囊重放 ✅ 25/25=100.0% (Go/No-Go #4 PASS; docs/eval/replay-results.md); KMS/HSM ⏳ + 证书撤销 ⏳ (DRILLS 4 需开发) |
| §5.1-5.6 前端 | ◐ | 9 页验证控制台+20 路由工作台+登录/租户/Token 页 ✅; e2e ✅ W39 (Playwright 9 用例全绿); 向导第一步全信息+权限页+计费路由 ✅ W101 (19 文件 90 测试+typecheck+build 绿); 弱网/性能 ⏳ |
| §6.1 证据图谱血缘 | ✅ | evidence/lineage.py + 证书 extension |
| §6.5 AI 修复闭环 | ✅ | W35 craft_accept 强制闭环 |
| §6.2-6.4,6.6-6.10 复杂能力 | ⏳ | 自适应编排/状态机/策略即代码/法庭/私有化/效能/插件市场 → 阶段3-8 |
| §7.1 核心关系表 | ✅ | MySQL 迁移 0001-0008 (0008 = W84 存储治理); 数据字典 ✅ (W103 DATA_DICTIONARY.md) |
| §7.2 用量账本 | ✅ | W40: usage_ledger 三后端+event_id 幂等+LLM 四类计量+配额预检+发票对账 (195 测试) |
| §8.1 API 兼容 | ✅ | OpenAPI diff 门禁 (CI job) |
| §8.2 MCP | ◐ | 服务端 6 工具 stdio JSON-RPC ✅; MCP 客户端 ⏳ |
| §8.3 GitHub/GitLab | ◐ | GitHub App/webhook/checks/fix ✅; GitLab ⏳ 阶段3 |
| §9 测试评测 | ✅ | unit 2530 passed/3 skipped + security 36/fault 45/contract 27 + golden 100 = 100.0% (63/63, FP 0; docs/eval/eval-100-segments.md); SWE-bench LLM 十二轮 v1-v12 诚实实录 (resolved 0%, harness 障碍逐轮清完剩模型能力层, v12 实测网关仅 v4-flash/v4-pro 无更强档); Capsule 重放 25/25=100.0%; aider polyglot 1/3=33.3% (W98) |
| §10 安全合规 | ◐ | 威胁矩阵/密钥 env-only/注入 24 矩阵 ✅; 密钥泄漏 0 + bandit Medium+=0 ✅; SOC2 路线 ⏳ |
| §11 可观测运维 | ◐ | 恢复演练 ✅ (W89 DRILLS: Drill1 真实 kill 6 检查点→9.09s resume→BLOCKED=control / Drill2 provider outage 真实 / Drill4 outbox 崩溃→exactly-once / Drill3 桌面 9 可执行 4 需开发); Grafana/SLO 面板 ⏳ (真实缺口) |
| §12 阶段0-8 | ◐ | 0/1/2/6/7 核心完成 (6 = W40 后端 + W101 计费路由); 3 部分 (Policy DSL+豁免流 ✅ W102; GitLab ⏳); 4 部分 (探针 ✅ W36, 100 案例 ✅ 100.0%, Python 适配器+ddmin ✅ W78/W105; Gradle/Node/Go ⏳); 5 ⏳ (KMS/HSM+证书撤销); 8 部分 |
| §13 团队配置 | ✅ | 车道制 (每轮审计→实现→全绿验证) |
| §14 首批 15 任务 | ◐ | 5 ✅ W39 e2e; 6/7 ✅ W38; 8 ✅ W85B+W106 (node 级取消检查点+classify_job_error {system|repo|provider|policy|unknown}); 13 ✅ httpx 弃用已消解; 14 ◐ (W89 演练已执行; 删除/导出/主机备份工具 ⏳); 12 ◐ (100 案例 ✅ 100.0%; 200 案例路线表 ⏳) |
| §15 验收清单 | ◐ | 见 GUIDE_GAP_AUDIT §C (代码/功能/安全 ✅ 大部分; 运营商业: 账本 ✅ W40+计费路由 ✅ W101, Grafana/SLO ⏳, 恢复演练 ✅ W89) |
| §16 结语 | ✅ | 持续对齐本表 |

## B. 代码开发Agent商业化终极计划书 (1005 行)

| 节 | 内容 | 状态 | 证据/备注 |
|---|---|---|---|
| 一-二 结论/定位 | ✅ | SALES_PITCH + README |
| 三 基线与差距 | ◐ | 差距矩阵 AGENT_STATE_OF_ART; 指标: 完成率 98.0% ✅ / 陷阱 100% ✅ / 恢复率: 真实 kill 演练 ✅ (W89 Drill1 9.09s resume→BLOCKED=control), ≥99.9% 长期统计未量化 ⏳ / 预算超限终态 100% ✅ |
| 四 工作流 4.1-4.6 | ✅ | 向导+计划 DAG+探索 (symbol/retrieval)+执行 (13 工具)+自校验 (W26/W34)+交付 (W35) |
| 五 内核架构 | ✅ | 分层/AgentTask 状态/Schema W33/计划 DAG |
| 六 工具系统 | ✅ | W33: 13 工具 v1/风险四级/审批/防注入 envelope/12 错误码 |
| 七 上下文工程记忆 | ◐ | 仓库摄取 W33 rules ✅ / 混合检索 W29 ✅ / 上下文压缩 ⏳ / 记忆分层 ✅ / 规则优先级 7 级 ✅ |
| 八 编辑能力 | ◐ | stale 保护+改动分类 ✅; AST 编辑+结构化 Diff ⏳ M4; 跨语言适配: Python ✅ (W78/W105 PythonAdapter local-first), Gradle/Node/Go ⏳; Git 交付 ✅ |
| 九 测试自校验交接 | ✅ | M3 verify + W34 五道门 + W35 SpecProof 交接协议 (accept) |
| 十 并行子代理 | ◐ | W34 只读并行 (写集 fail-closed) ✅; 可写并行 ⏳ M7+ |
| 十一 前端需求 | ✅ | 9 页+20 路由+权限体验 (W31+W37); 向导第一步全信息+权限页+计费路由 ✅ (W101, 19 文件 90 测试); e2e ✅ W39 (Playwright 9 用例全绿) |
| 十二 后端需求 | ◐ | 任务 API ✅; 事件/SSE ✅; 数据安全 ✅; 配额成本 ✅ (W40 后端 + W101 计费路由); 每作业成本会计 ⏳ |
| 十三 安全信任 | ◐ | 沙箱/注入/凭据 ✅; 供应链 SBOM ⏳ |
| 十四 商业化收费 | ◐ | 后端 ✅ W40 (账本/配额/发票/RBAC) + 计费路由 ✅ W101; 月账单 cron+签发流 ⏳; 每作业成本会计 ⏳ |
| 十五 M0-M11 | ◐ | M0-M8 核心 ✅; M9 (模型路由) ⏳; M10 (生态) ⏳; M11 持续 |
| 十六 每周模板 | ✅ | 每轮审计→实现→全绿验证 (本表+ledger) |
| 十七 门禁 | ✅ | 质量门 (test/build/typecheck)/正确性门/安全门 全机检 |
| 十八 运维部署 | ◐ | compose.phase0 实测起 ✅; 生产部署/K8s 指南 ⏳ |
| 十九 创新能力 8 项 | ◐ | 19.1 Contract-aware ✅ (血缘) / 19.2 Mutation-guided ✅ / 19.3 Falsifiable ◐ / 19.8 Attention Router ◐ (审批路由); 19.4-19.7 ⏳ |
| 二十 风险禁止 8 条 | ✅ | 逐条有对策 (fail-closed/白名单/写集锁/预算/STUCK/范围守卫/单体/实证纪律) |
| 二十一 最终交付标准 | ◐ | 逐条映射本表; 剩余见队列 |
| 二十二 首批 12 任务 | ◐ | 11.5/12 完成 (1-5,7-11 ✅; 6 半项 [AST 编辑待]; 12 半项 [GitLab/IDE/MCP 客户端/私有化 ⏳]) |
| 二十三 总结 | ✅ | |

## C. 剩余工作队列 (按依赖排序)

1. ✅ W36+W48: 探针修复完成 — 100 金案例 Recall/Precision/F1 = 100.0% (63/63, FP 0); 五 chunk 全重跑 (docs/eval/eval-c1-rerun.results.json / eval-c2-rerun / eval-c3-rerun / eval-c4-rerun / eval-rem3-rerun); 总表 docs/eval/eval-100-segments.md; 段1 六案例 25/33/29 → 100/100/100 (docs/eval/eval-seg1-fixed.results.json)
2. ✅ W38: 契约不可变版本+对象元数据查询 (指南任务 6/7; GUIDE_GAP_AUDIT §A)
3. ✅ W39: Playwright e2e 9 用例全绿 (向导/详情/权限/降级, 已合流 1adfa98) — 指南任务 5
4. ✅ W40: 计费账本+配额 (阶段 6 后端) + W101 计费路由 (前端)
5. ✅ 任务 8 (W85B+W106): node 级取消检查点 (Maven/LLM 前) + classify_job_error {system|repo|provider|policy|unknown}; 租约指标 ⏳
6. ✅ 任务 13: httpx/TestClient 弃用已消解 (2026-08-19 多轮定向+全量运行无警告)
7. ⏳ M4: AST 编辑 + 结构化 Diff (计划书任务 6 第三项)
8. ⏳ 阶段 3: GitLab 集成 (Policy DSL+豁免流 ✅ W102: agent/policy_dsl.py + agent/waiver.py, 42 测试)
9. ⏳ 阶段 4: Gradle/Node/Go 适配器 + 状态机验证 + 200 案例路线表 (Python 适配器 ✅ W78/W105 PythonAdapter local-first; 反例最小化 ✅ W105 experiments/minimize.py)
10. ⏳ 阶段 5: KMS/HSM + 证书撤销 (DRILLS 4 需开发) + 对象加密 (恢复演练 ✅ W89 DRILLS)
11. ⏳ M6 残留: IDE 插件 (VSCode/JetBrains); M9: 模型路由/每作业成本会计; M10: MCP 客户端/通知连接器 (notify wiring, DRILLS 4 需开发)/插件市场
12. ⏳ 运维: 生产部署指南/SOC2 合规路线 + Grafana/SLO 面板 (数据字典 ✅ W103 DATA_DICTIONARY.md)
13. ⏳ VERIFIED 路径 Java E2E 手动补跑 (W35 已留命令); 100 案例段1 ✅ 已合并总表 (docs/eval/eval-100-segments.md)
14. ⏳ GitHub PR 创建 (需 PAT 增加 Pull requests 权限或用户手动点击)
15. ⏳ 自动 RUNNING-job 回收器 + WAITING_FOR_PROVIDER 接线
16. ⏳ 生产试点 (3 仓库 2 周); ✅ Python freeze 快照已提交 (W177, 干净 venv 审计待); ✅ 独立归因准确率指标已建并实测 **100.0%** (W182, Go/No-Go #3 PASS); ✅ court 无证据 BLOCKER 不变式测试 19 例 (Go/No-Go #5 PASS)

原则: 每完成一项, 本表+两份审计文档同步回填; 数字只写真实运行结果。

## D. 本地体验最终态 (Local-First, 用户 2026-08-19 指令)

战略调整: 不部署公网; 一切以本机流畅体验为第一优先级, 交付一个用户可以真实点完的最终态, 体验后按用户反馈迭代。

架构定性 (用户确认): LLM 推理走远程 API (DeepSeek 网关, 已实测适配), 其余全部本地 — 后端/前端/基础设施/Agent 运行时/评测全部在本机 Docker+进程内运行; 产品本身不部署公网。LLM 凭据仅经环境变量注入 (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL), 绝不落盘; 未配置时自动降级确定性档 (无 LLM 也能点完全流程)。

验收目标 (用户可直接体验):
1. 一键启动: ✅ W43 + ✅ W43.1 (1f34f44 已在链): worker/outbox 随 start/stop 启停 — 实测新建验证 QUEUED→BLOCKED 确定性档零 LLM (relay 发布→worker 消费→6 分钟终态, findings AUTH-01 静态拦截); 后续已落地: node 级取消检查点 ✅ (W106) + classify_job_error 五类 ✅ (W85B); 剩余: RUNNING-job 自动回收器 ⏳ + WAITING_FOR_PROVIDER 接线 ⏳;
2. 首次打开即有内容: 预置 2-3 个已完成验证作业 (矩阵/证书) + 1 个进行中 Agent 作业;
3. 验证流闭环可点: ✅ 新建验证 → QUEUED→终态 (W43.1 worker/outbox 实测) → 判定矩阵/Findings; 证书页对 Worker 产出的作业诚实 404 (已知限制, 证书由 CLI/CP 落盘);
4. Agent 流闭环可点: 新建任务 → 计划审阅 → 实时工具流 (SSE) → 门禁五道 → accept 判定 (确定性档, 无需 LLM 无 key);
5. 视觉顶级: ✅ W41 全部完成 (W41.2 壳层+样式采纳 + W41.3 全页面铺开: verify 9 页+agent 15 页+identity 2 页 全 Aurora 化, legacy components.tsx/styles.css 退役 0 悬空引用, ⌘K 命令面板+深浅双主题全站可用; 队长复跑 typecheck/55 测试/build/Playwright 9-9 全绿) — 美轮美奂达成;
6. 权限体验: 登录 → 租户切换 → viewer/admin 差异可见 (W37);
7. 体验文档: docs/operations/LOCAL_EXPERIENCE.md (用户视角步骤+预期画面+已知限制);
8. e2e 冒烟: ✅ W39 Playwright 9 用例全绿 (向导/详情/权限/降级 四场景, 真实 Vite+API fixture, 无 DOM mock) — 已合流 1adfa98。

新增工作 (本地态专用, 置顶优先级):
- W42: Agent 运行时接线 (api/agent_runtime.py: 后台线程跑真实 CraftLoop 确定性档 → _ConsoleState 事件 → SSE; agent_jobs 投影; 取消/租约) — 让工作台活起来;
- ✅ W43 (4996d65): 一键启动/停止脚本 + 幂等演示种子 + LOCAL_EXPERIENCE.md 中文体验指南 (15 测试+PS ParseFile 0, 6 容器实测);
- ✅ W43.1: worker/outbox 并入一键启动 (验证流新建任务闭环);
- ✅ W41 阶段2: 设计系统全页面铺开 (全站 Aurora 化, 0 悬空引用);
- 队长: LOCAL_EXPERIENCE.md 体验指南 + 本地态验收自测。

降级 (不再阻塞本地态): 公网部署/K8s、SOC2 路线、插件市场、MCP 客户端、阶段5 KMS、GitLab — 保留在远期队列, 本地态交付后再议。
