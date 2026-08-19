# 双文档逐节完成度地图 (COMPLETION_MAP) — 持续更新

依据: docs/工业化商业化终极开发指南.md (727 行) + docs/代码开发Agent商业化终极计划书.md (1005 行), 已逐节通读。
状态图例: ✅ 已完成且有真实证据 · 🚧 车道在途 · ⏳ 已设计/排队 · ◐ 部分完成 (证据注明)。
证据链: 提交 W13..W40 见 git log; 门禁数字全部来自真实运行 (队长逐项复跑)。

## A. 工业化商业化终极开发指南 (727 行)

| 节 | 内容 | 状态 | 证据/备注 |
|---|---|---|---|
| §0-2 | 阅读结论/现状/产品定义 | ✅ | README + SALES_PITCH + STACK_INVENTORY |
| §3.1 领域划分 | ✅ | docs/architecture/domain-model.md |
| §3.2 服务边界 | ✅ | STACK_INVENTORY (specproof-* 服务) |
| §3.3 数据分层 | ◐ | MySQL/Mongo/ES/Redis/MinIO 适配器全有; 完整数据字典 ⏳ |
| §3.4 事件 Envelope | ✅ | W28 contracts/events.py (12 字段/脱敏/sha256) |
| §4.1 身份租户权限 | ✅ | W37 (OIDC+sp_*+RBAC 4×4+跨租户 404+迁移 0005) |
| §4.2 Job 状态机 | ✅ | 状态机+SSE+取消 (W14/P) |
| §4.3 提交验证 API | ✅ | POST /jobs + OpenAPI 差分门禁 (W28) |
| §4.4 Contract 领域增强 | 🚧 | W38: checker_version+不可变版本+对象元数据 (在途) |
| §4.5 执行沙箱 | ✅ | DooD 沙箱+15 测试; Linux 非root ⏳ (P6 遗留) |
| §4.6 LLM Provider 治理 | ◐ | V4 Pro 适配+TokenBudget ✅; 租户预算/路由 🚧 W40 |
| §4.7 证据签名重放 | ◐ | Ed25519+血缘+胶囊重放 ✅; KMS/撤销 ⏳ 阶段5 |
| §5.1-5.6 前端 | ◐ | 9 页验证控制台+20 路由工作台+登录/租户/Token 页 ✅; e2e 🚧 W39; 弱网/性能 ⏳ |
| §6.1 证据图谱血缘 | ✅ | evidence/lineage.py + 证书 extension |
| §6.5 AI 修复闭环 | ✅ | W35 craft_accept 强制闭环 |
| §6.2-6.4,6.6-6.10 复杂能力 | ⏳ | 自适应编排/状态机/策略即代码/法庭/私有化/效能/插件市场 → 阶段3-8 |
| §7.1 核心关系表 | ◐ | MySQL 迁移 0001-0005 (job/outbox/identity 等); 全量数据字典 ⏳ |
| §7.2 用量账本 | ✅ | W40: usage_ledger 三后端+event_id 幂等+LLM 四类计量+配额预检+发票对账 (195 测试) |
| §8.1 API 兼容 | ✅ | OpenAPI diff 门禁 (CI job) |
| §8.2 MCP | ◐ | 服务端 6 工具 stdio JSON-RPC ✅; MCP 客户端 ⏳ |
| §8.3 GitHub/GitLab | ◐ | GitHub App/webhook/checks/fix ✅; GitLab ⏳ 阶段3 |
| §9 测试评测 | ✅ | unit 990+/security 36/fault 45/contract 27/golden 100 (双段 eval 实录) |
| §10 安全合规 | ◐ | 威胁矩阵/密钥 env-only/注入 24 矩阵 ✅; SOC2 路线 ⏳ |
| §11 可观测运维 | ◐ | Grafana+SLO+告警 ✅; 恢复演练 ⏳ 阶段5 |
| §12 阶段0-8 | ◐ | 0/1/2/7 核心完成; 3/5 排队; 4 部分 (W36 探针在途); 6 🚧 W40; 8 部分 |
| §13 团队配置 | ✅ | 车道制 (每轮审计→实现→全绿验证) |
| §14 首批 15 任务 | ◐ | 11.5/15: 5 🚧 W39, 6/7 🚧 W38, 8 (取消检查点) ⏳, 13 (httpx 弃用) ⏳, 14 ⏳ 阶段5 |
| §15 验收清单 | ◐ | 见 GUIDE_GAP_AUDIT §C (代码/功能/安全 ✅ 大部分; 运营商业 🚧 W40) |
| §16 结语 | ✅ | 持续对齐本表 |

## B. 代码开发Agent商业化终极计划书 (1005 行)

| 节 | 内容 | 状态 | 证据/备注 |
|---|---|---|---|
| 一-二 结论/定位 | ✅ | SALES_PITCH + README |
| 三 基线与差距 | ◐ | 差距矩阵 AGENT_STATE_OF_ART; 指标: 完成率 98.0% ✅ / 陷阱 100% ✅ / 恢复率 ⏳ 未量化 / 预算超限终态 100% ✅ |
| 四 工作流 4.1-4.6 | ✅ | 向导+计划 DAG+探索 (symbol/retrieval)+执行 (13 工具)+自校验 (W26/W34)+交付 (W35) |
| 五 内核架构 | ✅ | 分层/AgentTask 状态/Schema W33/计划 DAG |
| 六 工具系统 | ✅ | W33: 13 工具 v1/风险四级/审批/防注入 envelope/12 错误码 |
| 七 上下文工程记忆 | ◐ | 仓库摄取 W33 rules ✅ / 混合检索 W29 ✅ / 上下文压缩 ⏳ / 记忆分层 ✅ / 规则优先级 7 级 ✅ |
| 八 编辑能力 | ◐ | stale 保护+改动分类 ✅; AST 编辑+结构化 Diff ⏳ M4; 跨语言适配 ⏳ (Q 协议已立); Git 交付 ✅ |
| 九 测试自校验交接 | ✅ | M3 verify + W34 五道门 + W35 SpecProof 交接协议 (accept) |
| 十 并行子代理 | ◐ | W34 只读并行 (写集 fail-closed) ✅; 可写并行 ⏳ M7+ |
| 十一 前端需求 | ✅ | 9 页+20 路由+权限体验 (W31+W37); e2e 🚧 W39 |
| 十二 后端需求 | ◐ | 任务 API ✅; 事件/SSE ✅; 数据安全 ✅; 配额成本 🚧 W40 |
| 十三 安全信任 | ◐ | 沙箱/注入/凭据 ✅; 供应链 SBOM ⏳ |
| 十四 商业化收费 | ◐ | 后端 ✅ W40 (账本/配额/发票/RBAC); 计费 UI+月账单 cron+签发流 ⏳ |
| 十五 M0-M11 | ◐ | M0-M8 核心 ✅; M9 (模型路由) ⏳; M10 (生态) ⏳; M11 持续 |
| 十六 每周模板 | ✅ | 每轮审计→实现→全绿验证 (本表+ledger) |
| 十七 门禁 | ✅ | 质量门 (test/build/typecheck)/正确性门/安全门 全机检 |
| 十八 运维部署 | ◐ | compose.phase0 实测起 ✅; 生产部署/K8s 指南 ⏳ |
| 十九 创新能力 8 项 | ◐ | 19.1 Contract-aware ✅ (血缘) / 19.2 Mutation-guided ✅ / 19.3 Falsifiable ◐ / 19.8 Attention Router ◐ (审批路由); 19.4-19.7 ⏳ |
| 二十 风险禁止 8 条 | ✅ | 逐条有对策 (fail-closed/白名单/写集锁/预算/STUCK/范围守卫/单体/实证纪律) |
| 二十一 最终交付标准 | ◐ | 逐条映射本表; 剩余见队列 |
| 二十二 首批 12 任务 | ◐ | 10.5/12 完成 (1-5,7-10 ✅; 6 半项; 11 半项; 12 半项) |
| 二十三 总结 | ✅ | |

## C. 剩余工作队列 (按依赖排序)

1. 🚧 W36: 三个 rel 金案例 MISS 的探针修复 (故障注入/发布计数/载荷捕获) — 完成后段2 Recall 76.9%→100%
2. 🚧 W38: 契约不可变版本+对象元数据查询 (指南任务 6/7)
3. 🚧 W39: Playwright e2e (向导/详情/权限/降级) — 指南任务 5
4. 🚧 W40: 计费账本+配额 (阶段 6, 计划书任务 11 配额部分/任务 12 计费部分)
5. ⏳ 任务 8: Worker 取消检查点 (Maven/LLM 前) + 租约指标 (等 W36 释放 agent/nodes)
6. ⏳ 任务 13: httpx/TestClient 弃用警告处理 (小任务, 队长直做)
7. ⏳ M4: AST 编辑 + 结构化 Diff (计划书任务 6 第三项)
8. ⏳ 阶段 3: GitLab 集成 + Policy DSL + 豁免流
9. ⏳ 阶段 4: Gradle/Node/Python/Go 适配器 + 状态机验证 + 反例最小化 + 200 案例路线表
10. ⏳ 阶段 5: KMS/HSM + 证书撤销 + 对象加密 + 恢复演练
11. ⏳ M6 残留: IDE 插件 (VSCode/JetBrains); M9: 模型路由/成本; M10: MCP 客户端/通知连接器/插件市场
12. ⏳ 运维: 数据字典全量/生产部署指南/SOC2 合规路线
13. ⏳ VERIFIED 路径 Java E2E 手动补跑 (W35 已留命令); 100 案例段1 (pwsh-51 跑完) 合并总表
14. ⏳ GitHub PR 创建 (需 PAT 增加 Pull requests 权限或用户手动点击)

原则: 每完成一项, 本表+两份审计文档同步回填; 数字只写真实运行结果。

## D. 本地体验最终态 (Local-First, 用户 2026-08-19 指令)

战略调整: 不部署公网; 一切以本机流畅体验为第一优先级, 交付一个用户可以真实点完的最终态, 体验后按用户反馈迭代。

架构定性 (用户确认): LLM 推理走远程 API (DeepSeek 网关, 已实测适配), 其余全部本地 — 后端/前端/基础设施/Agent 运行时/评测全部在本机 Docker+进程内运行; 产品本身不部署公网。LLM 凭据仅经环境变量注入 (LLM_BASE_URL/LLM_API_KEY/LLM_MODEL), 绝不落盘; 未配置时自动降级确定性档 (无 LLM 也能点完全流程)。

验收目标 (用户可直接体验):
1. 一键启动: scripts/start_local.ps1 (Docker infra → 种子数据 → FastAPI → Vite → 浏览器);
2. 首次打开即有内容: 预置 2-3 个已完成验证作业 (矩阵/证书) + 1 个进行中 Agent 作业;
3. 验证流闭环可点: 新建验证 → 进度 SSE → 判定矩阵 → 证书下载/验签;
4. Agent 流闭环可点: 新建任务 → 计划审阅 → 实时工具流 (SSE) → 门禁五道 → accept 判定 (确定性档, 无需 LLM 无 key);
5. 视觉顶级: W41 设计系统 ✅ 阶段1 地基 (Aurora 紫青渐变/暗亮双主题/21 组件/⌘K//ui-kit, 55 测试全绿已推) + 🚧 阶段2 全页面铺开 (已派: 壳层→verify 9 页→agent 14 页→identity 页, 保 testid/ErrorBoundary/e2e 全绿);
6. 权限体验: 登录 → 租户切换 → viewer/admin 差异可见 (W37);
7. 体验文档: docs/operations/LOCAL_EXPERIENCE.md (用户视角步骤+预期画面+已知限制);
8. e2e 冒烟: ✅ W39 Playwright 9 用例全绿 (向导/详情/权限/降级 四场景, 真实 Vite+API fixture, 无 DOM mock) — 已合流 1adfa98。

新增工作 (本地态专用, 置顶优先级):
- W42: Agent 运行时接线 (api/agent_runtime.py: 后台线程跑真实 CraftLoop 确定性档 → _ConsoleState 事件 → SSE; agent_jobs 投影; 取消/租约) — 让工作台活起来;
- W43: 一键启动脚本 + 演示种子数据 (start_local.ps1 + seed 脚本, 幂等);
- W41 阶段2: 设计系统全页面铺开 (等 W39 落盘后派);
- 队长: LOCAL_EXPERIENCE.md 体验指南 + 本地态验收自测。

降级 (不再阻塞本地态): 公网部署/K8s、SOC2 路线、插件市场、MCP 客户端、阶段5 KMS、GitLab/Policy DSL — 保留在远期队列, 本地态交付后再议。
